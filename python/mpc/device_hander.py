import time
import logging
from typing import Optional, Tuple, Sequence
import threading
from functions import PaddleOptimizer

import clr

# Global lock to prevent simultaneous Kinesis device connections (not thread-safe)
_kinesis_connection_lock = threading.Lock()

clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.PolarizerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.IntegratedStepperMotorsCLI.dll")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI, DeviceConfiguration
from Thorlabs.MotionControl.PolarizerCLI import Polarizer, PolarizerPaddles
from Thorlabs.MotionControl.IntegratedStepperMotorsCLI import CageRotator
from System import Decimal

from utils.common import connect as tc_connect, zmq_exec
from utils.acquisitions import setup_input_counts_over_time_acquisition


logger = logging.getLogger(__name__)


class MPC320Controller:
    def __init__(self, serial_no: str, tc_input_to_watch: int):
        self.serial_no = str(serial_no)
        self.device = None
        self.tc_input_to_watch = tc_input_to_watch
        self.optimiser = PaddleOptimizer()

    def connect(self):
        logger.info("Connecting to MPC320 device - serial number: %s", self.serial_no)
        
        # Use lock to prevent simultaneous connections (Kinesis is not thread-safe)
        with _kinesis_connection_lock:
            DeviceManagerCLI.BuildDeviceList()
            self.device = Polarizer.CreatePolarizer(self.serial_no)
            self.device.Connect(self.serial_no)
            time.sleep(0.25)
            self.device.StartPolling(250)
            time.sleep(0.25)
            self.device.EnableDevice()
            time.sleep(0.25)
            if not self.device.IsSettingsInitialized():
                self.device.WaitForSettingsInitialized(10000)
        
        logger.info("MPC320 device connected - serial number: %s", self.serial_no)
        return self

    def get_paddles(self) -> Tuple:
        return (
            PolarizerPaddles.Paddle1,
            PolarizerPaddles.Paddle2,
            PolarizerPaddles.Paddle3,
        )

    def move_to(self, angle_deg: float, paddle) -> None:
        logger.info("MoveTo paddle=%s angle=%.2f deg", str(paddle), angle_deg)
        d = Decimal(angle_deg)
        self.device.MoveTo(d, paddle, 8000)

    def move_to_three(self, angles_deg) -> None:
        p1, p2, p3 = self.get_paddles()
        # Note: Kinesis COM calls are synchronous and not thread-safe; run sequentially
        for paddle, angle in ((p1, angles_deg[0]), (p2, angles_deg[1]), (p3, angles_deg[2])):
            logger.info("MoveTo (sequential) paddle=%s angle=%.2f deg", str(paddle), angle)
            d = Decimal(angle)
            self.device.MoveTo(d, paddle, 60000)

    def search_for_optimal_roations(self):
        # start up the paddle optimization process
        # start from the best prev
        # periodically call the next step
        # move paddle to the calculated pos
        # get live updates from tc
        # when finshed turn paddles to optimised step
        # do this on a different thread

        if self.device is None:
            raise RuntimeError("MPC320 device is not connected. Call connect() first.")
        self.optimiser.reset()
        
        # while not optimised:
        angles = self.optimiser._get_next_paddle_state()
            # update live from tc
        self.move_to_three(angles)

        # then
        opt_angles = self.optimiser._get_optimum_paddle_state()
        self.move_to_three(opt_angles)

    def disconnect(self):
        if self.device is None:
            return
        try:
            logger.info("Stopping polling")
            self.device.StopPolling()
        except Exception:
            pass
        time.sleep(0.1)
        try:
            logger.info("Disconnecting device (force=True)")
            self.device.Disconnect(True)
        except Exception:
            try:
                logger.info("Disconnecting device (force=False)")
                self.device.Disconnect()
            except Exception:
                pass
        finally:
            logger.info("Disconnected MPC320 %s", self.serial_no)
            self.device = None

    def home_all(self):
        """Home all three paddles sequentially"""
        if self.device is None:
            raise RuntimeError("MPC320 device is not connected. Call connect() first.")
        p1, p2, p3 = self.get_paddles()
        for paddle in (p1, p2, p3):
            try:
                logger.info("Homing paddle=%s", str(paddle))
                self.device.Home(paddle)
            except Exception:
                logger.warning("Home failed for paddle=%s; moving to 0 deg fallback", str(paddle))
                try:
                    self.device.MoveTo(Decimal(0), paddle, 60000)
                except Exception:
                    logger.exception("Fallback move to 0 failed for paddle=%s", str(paddle))


class TimeController:
    def __init__(self, address: str, counters=("1","2","3","4"), integration_time_ps: Optional[int] = None):
        self.address = address
        self.counters = counters
        self.integration_time_ps = integration_time_ps
        self.tc = None

    def connect(self):
        self.tc = tc_connect(self.address)
        if self.integration_time_ps is not None:
            setup_input_counts_over_time_acquisition(self.tc, self.integration_time_ps, list(self.counters))
        return self

    def query_counter(self, idx: int) -> int:
        ans = zmq_exec(self.tc, f"INPUt{idx}:COUNter?")
        try:
            return int(ans)
        except Exception:
            logger.warning("Invalid counter value: %s", ans)
            return 0

    def query_all_counters(self) -> Tuple[int, int, int, int]:
        return tuple(self.query_counter(i) for i in range(1, 5))

    def close(self):
        if self.tc is None:
            return
        try:
            self.tc.close(0)
        except Exception:
            try:
                self.tc.close()
            except Exception:
                pass
        finally:
            self.tc = None


class CageRotatorController:
    """Controller for Thorlabs K10CR1 Cage Rotator"""
    
    def __init__(self, serial_no: str):
        self.serial_no = str(serial_no)
        self.device = None
        logger.info("Initialized CageRotatorController with serial: %s", self.serial_no)
    
    def connect(self):
        """Connect to the cage rotator device"""
        try:
            logger.info("Connecting to CageRotator device - serial number: %s", self.serial_no)
            DeviceManagerCLI.BuildDeviceList()
            
            # Create and connect device
            self.device = CageRotator.CreateCageRotator(self.serial_no)
            self.device.Connect(self.serial_no)
            time.sleep(0.25)
            
            # Start polling
            self.device.StartPolling(250)
            time.sleep(0.25)
            
            # Enable device
            self.device.EnableDevice()
            time.sleep(0.25)
            
            # Get device information
            device_info = self.device.GetDeviceInfo()
            logger.info("Connected to device: %s", device_info.Description)
            
            # Wait for settings to initialize
            if not self.device.IsSettingsInitialized():
                self.device.WaitForSettingsInitialized(10000)  # 10 second timeout
                assert self.device.IsSettingsInitialized() is True
            
            # Load motor configuration
            m_config = self.device.LoadMotorConfiguration(
                self.serial_no,
                DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings
            )
            m_config.DeviceSettingsName = "K10CR1"
            m_config.UpdateCurrentConfiguration()
            self.device.SetSettings(self.device.MotorDeviceSettings, True, False)
            
            logger.info("CageRotator device connected and configured - serial number: %s", self.serial_no)
            return self
            
        except Exception as e:
            logger.exception("Failed to connect to CageRotator %s: %s", self.serial_no, e)
            raise
    
    def move_to(self, angle_deg: float, timeout_ms: int = 60000):
        """
        Move the cage rotator to a specific angle in degrees
        
        Args:
            angle_deg: Target angle in degrees
            timeout_ms: Timeout in milliseconds (default: 60000 = 60 seconds)
        """
        if self.device is None:
            raise RuntimeError("CageRotator device is not connected. Call connect() first.")
        
        try:
            d = Decimal(angle_deg)
            logger.info("Moving CageRotator %s to position %.2f degrees", self.serial_no, angle_deg)
            self.device.MoveTo(d, timeout_ms)
            logger.info("Move completed for CageRotator %s", self.serial_no)
        except Exception as e:
            logger.exception("Failed to move CageRotator %s to %.2f degrees: %s", 
                           self.serial_no, angle_deg, e)
            raise
    
    def home(self, timeout_ms: int = 60000):
        """
        Home the cage rotator
        
        Args:
            timeout_ms: Timeout in milliseconds (default: 60000 = 60 seconds)
        """
        if self.device is None:
            raise RuntimeError("CageRotator device is not connected. Call connect() first.")
        
        try:
            logger.info("Homing CageRotator %s", self.serial_no)
            self.device.Home(timeout_ms)
            logger.info("Homing completed for CageRotator %s", self.serial_no)
        except Exception as e:
            logger.warning("Home failed for CageRotator %s: %s. Attempting fallback to 0 degrees", 
                         self.serial_no, e)
            try:
                self.move_to(0.0, timeout_ms)
                logger.info("Fallback move to 0 degrees succeeded for CageRotator %s", self.serial_no)
            except Exception as fallback_e:
                logger.exception("Fallback move to 0 failed for CageRotator %s: %s", 
                               self.serial_no, fallback_e)
                raise
    
    def get_position(self) -> float:
        """
        Get the current position of the cage rotator in degrees
        
        Returns:
            float: Current position in degrees
        """
        if self.device is None:
            raise RuntimeError("CageRotator device is not connected. Call connect() first.")
        
        try:
            # Convert .NET Decimal to Python float via string
            position = float(str(self.device.Position))
            logger.debug("Current position of CageRotator %s: %.2f degrees", self.serial_no, position)
            return position
        except Exception as e:
            logger.exception("Failed to get position for CageRotator %s: %s", self.serial_no, e)
            raise
    
    def disconnect(self):
        """Disconnect from the cage rotator device"""
        if self.device is None:
            logger.info("CageRotator %s already disconnected", self.serial_no)
            return
        
        try:
            logger.info("Stopping polling for CageRotator %s", self.serial_no)
            self.device.StopPolling()
        except Exception as e:
            logger.warning("Error stopping polling for CageRotator %s: %s", self.serial_no, e)
        
        time.sleep(0.1)
        
        try:
            logger.info("Disconnecting CageRotator %s (force=True)", self.serial_no)
            self.device.Disconnect(True)
        except Exception:
            try:
                logger.info("Disconnecting CageRotator %s (force=False)", self.serial_no)
                self.device.Disconnect()
            except Exception as e:
                logger.warning("Error disconnecting CageRotator %s: %s", self.serial_no, e)
        finally:
            logger.info("Disconnected CageRotator %s", self.serial_no)
            self.device = None
    
    def __enter__(self):
        """Context manager entry"""
        return self.connect()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
        return False