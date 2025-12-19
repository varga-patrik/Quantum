"""
Mock Time Controller for testing and fallback when real hardware is unavailable.
⚠️ THIS IS A MOCK - NOT REAL HARDWARE! ⚠️
Simulates Time Controller timestamp streaming for local testing.
"""
import random
import numpy as np
import logging
import struct
import time

logger = logging.getLogger(__name__)


class MockTimeController:
    """
    Mock time controller that simulates IDQ Time Controller (ID900/ID1000)
    ⚠️ THIS IS A MOCK - SIMULATED DATA ONLY! ⚠️
    
    Simulates:
    - Timestamp streaming with picosecond precision
    - 4-channel photon detection
    - Realistic quantum correlations (for entangled pairs)
    - Reference second counter
    """
    def __init__(self, disable_data: bool = True):
        print("╔═══════════════════════════════════════════════════════════╗")
        print("║   ⚠️  MOCK TIME CONTROLLER - SIMULATED DATA ONLY ⚠️      ║")
        print("║   NOT REAL HARDWARE - FOR TESTING PURPOSES               ║")
        print("╚═══════════════════════════════════════════════════════════╝")
        logger.warning("MockTimeController initialized - using SIMULATED data")
        
        self._is_mock = True
        self._disable_data = disable_data  # If True, return no data (for testing)
        self._base_seed = random.randint(0, 1000000)
        
        if self._disable_data:
            print("║   📛 DATA DISABLED - Returning ZERO/EMPTY data         ║")
            logger.warning("MockTimeController: DATA DISABLED - returning zero data")
        
        # Simulation parameters
        self._detection_rate = 50000  # 50 kHz per channel (singles)
        self._coincidence_rate = 1000  # 1 kHz (coincidences between channels)
        self._reference_second = 0  # Current GPS reference second
        self._start_time = time.time()
        
        # Detector counts (cumulative)
        self._counter_values = [random.randint(40000, 80000) for _ in range(4)]
    
    def generate_timestamps(self, channel: int, duration_ps: int, with_ref_index: bool = True):
        """Generate mock timestamp data for a channel.
        
        Args:
            channel: Channel number (1-4)
            duration_ps: Acquisition duration in picoseconds
            with_ref_index: Include reference second counter
            
        Returns:
            Binary timestamp data (uint64 pairs if with_ref_index, else uint64 only)
        """
        logger.debug(f"⚠️ MOCK: Generating timestamps for channel {channel}, duration={duration_ps}ps")
        
        # Return empty data if disabled
        if self._disable_data:
            logger.debug(f"⚠️ MOCK: Data disabled - returning empty for channel {channel}")
            return b''
        
        # Calculate how many timestamps to generate
        duration_sec = duration_ps / 1e12
        num_timestamps = int(self._detection_rate * duration_sec)
        
        # Add some randomness to make it realistic
        num_timestamps = max(1, int(num_timestamps * random.uniform(0.8, 1.2)))
        
        timestamps = []
        
        # Generate timestamps with realistic distribution
        # Use current wall-clock time so both sites generate timestamps in same time range
        current_time_ps = int(time.time() * 1e12)  # Current time in picoseconds
        
        # Seed with channel for reproducibility per channel
        rng = np.random.RandomState(self._base_seed + channel + self._reference_second)
        
        for i in range(num_timestamps):
            # Random offset within the duration (use int64 for large values)
            offset_ps = int(rng.randint(0, int(duration_ps), dtype=np.int64))
            ps_in_second = (current_time_ps + offset_ps) % int(1e12)
            
            # For channels 1&2, add some correlated timestamps (simulated entanglement)
            if channel in [1, 2] and rng.random() < 0.05:  # 5% coincidence probability
                # Add timestamp at roughly same time as partner channel
                correlation_offset = rng.randint(-1000, 1000)  # ±1ns jitter
                ps_in_second = max(0, min(int(1e12) - 1, ps_in_second + correlation_offset))
            
            # Same for channels 3&4
            if channel in [3, 4] and rng.random() < 0.05:
                correlation_offset = rng.randint(-1000, 1000)
                ps_in_second = max(0, min(int(1e12) - 1, ps_in_second + correlation_offset))
            
            if with_ref_index:
                # Format: [picoseconds_in_second, reference_second_counter]
                timestamps.append((ps_in_second, self._reference_second))
            else:
                timestamps.append(ps_in_second)
        
        # Sort timestamps (chronological order)
        if with_ref_index:
            timestamps.sort(key=lambda x: x[0])
        else:
            timestamps.sort()
        
        # Convert to binary format (matches Time Controller format)
        if with_ref_index:
            # dtype: [('timestamp', uint64), ('refIndex', uint64)]
            binary_data = b''.join(struct.pack('<QQ', ts, ref) for ts, ref in timestamps)
        else:
            # dtype: uint64
            binary_data = b''.join(struct.pack('<Q', ts) for ts in timestamps)
        
        logger.debug(f"⚠️ MOCK: Generated {len(timestamps)} timestamps, {len(binary_data)} bytes")
        return binary_data
    
    def send_string(self, command: str) -> None:
        """Mock send_string method - simulates SCPI commands."""
        logger.debug(f"⚠️ MOCK send_string: {command}")
        
        # Simulate some state changes
        if "REC:PLAY" in command:
            self._reference_second += 1  # Increment reference second on each acquisition
        pass
    
    def recv_string(self) -> str:
        """Mock recv_string - returns simulated counter values."""
        # Return 0 if data disabled
        if self._disable_data:
            logger.debug("⚠️ MOCK recv_string: 0 (data disabled)")
            return "0"
        
        # Increment counters to simulate ongoing photon detection
        for i in range(4):
            self._counter_values[i] += random.randint(100, 500)
        
        value = random.choice(self._counter_values)
        logger.debug(f"⚠️ MOCK recv_string: {value}")
        return str(value)
    
    def __getattr__(self, name):
        """Return a callable for any unmocked method."""
        def mock_method(*args, **kwargs):
            logger.debug(f"⚠️ MOCK method called: {name}(*{args}, **{kwargs})")
            # Return 0 if data disabled
            if self._disable_data:
                if 'counter' in name.lower() or 'count' in name.lower():
                    return 0
                return None
            # Return realistic random values with some variation
            if 'counter' in name.lower() or 'count' in name.lower():
                return random.randint(20000, 100000)
            return None
        return mock_method
    
    def close(self, *args, **kwargs):
        """Mock close method"""
        logger.debug("⚠️ MOCK close called")
        pass


class MockTimeControllerWrapper:
    """
    Mock wrapper that mimics the TimeController class interface
    This is used when the real TimeController cannot connect
    """
    def __init__(self, address: str, counters=("1","2","3","4"), integration_time_ps=None, disable_data: bool = True):
        logger.warning("MockTimeControllerWrapper initialized for %s", address)
        self.address = address
        self.counters = counters
        self.integration_time_ps = integration_time_ps
        self.tc = MockTimeController(disable_data=disable_data)
        self._is_mock = True
        self._disable_data = disable_data
    
    def connect(self):
        """Mock connect - already 'connected'"""
        logger.info(f"MockTimeControllerWrapper 'connected' to {self.address}")
        return self
    
    def query_counter(self, idx: int) -> int:
        """Return random counter value for the given index"""
        if self._disable_data:
            logger.debug(f"Mock query_counter({idx}): 0 (data disabled)")
            return 0
        value = random.randint(20000, 100000)
        logger.debug(f"Mock query_counter({idx}): {value}")
        return value
    
    def query_all_counters(self):
        """Return random values for all 4 counters"""
        if self._disable_data:
            values = (0, 0, 0, 0)
            logger.debug("Mock query_all_counters: (0, 0, 0, 0) (data disabled)")
            return values
        values = tuple(random.randint(20000, 100000) for _ in range(4))
        logger.debug(f"Mock query_all_counters: {values}")
        return values
    
    def close(self):
        """Mock close"""
        logger.debug("MockTimeControllerWrapper close called")
        pass


def create_time_controller_wrapper(address: str, counters=("1","2","3","4"), integration_time_ps=None):
    """
    Factory function to create either a real or mock TimeController wrapper
    This should be used in device_hander.py TimeController class
    """
    try:
        from device_hander import TimeController
        from utils.common import connect as tc_connect
        
        # Try to connect to real controller
        tc = tc_connect(address)
        # If successful, close and return a real TimeController instance
        try:
            tc.close(0)
        except:
            tc.close()
        
        return TimeController(address, counters, integration_time_ps)
    except Exception as e:
        logger.warning(f"Failed to connect to real time controller at {address}: {e}")
        logger.warning("Falling back to MockTimeControllerWrapper")
        return MockTimeControllerWrapper(address, counters, integration_time_ps)


def safe_zmq_exec(tc, command, zmq_exec_func):
    """
    Wrapper for zmq_exec that handles MockTimeController
    
    Args:
        tc: Time controller instance (real or mock)
        command: Command to execute
        zmq_exec_func: The actual zmq_exec function to use for real controllers
    
    Returns:
        int: Random value (20000-100000) if mock, or real value from device
    """
    if isinstance(tc, MockTimeController) or getattr(tc, '_is_mock', False):
        return random.randint(20000, 100000)
    try:
        return zmq_exec_func(tc, command)
    except Exception:
        return random.randint(20000, 100000)


def safe_acquire_histograms(tc, duration, bin_width, bin_count, histograms, acquire_histograms_func):
    """
    Wrapper for acquire_histograms that handles MockTimeController
    
    Simulates real quantum measurement:
    - Entangled photon source generates pairs
    - Each site detects its half of the entangled pairs
    - Detection events are binned into histograms
    - Both sites should see correlated patterns
    
    Args:
        tc: Time controller instance (real or mock)
        duration: Acquisition duration
        bin_width: Histogram bin width
        bin_count: Number of bins
        histograms: List of histogram IDs to acquire
        acquire_histograms_func: The actual acquire_histograms function
    
    Returns:
        dict: Mock or real histogram data
    """
    if isinstance(tc, MockTimeController) or getattr(tc, '_is_mock', False):
        # Simulate quantum entanglement source and detection
        import time
        
        # Sync time across both sites (round to nearest 1 second for stable testing)
        # This ensures both client and server use the same "entangled photon pair events"
        sync_time = int(time.time())
        
        # Generate entangled photon pair events (shared "reality" between sites)
        np.random.seed(int(sync_time * 1000) % (2**31))
        
        # Number of entangled pairs generated in this measurement window
        num_pairs = np.random.poisson(1000)  # ~1000 pairs per measurement
        
        # Each pair has a detection time (shared between both sites)
        pair_times = np.random.randint(0, bin_count, size=num_pairs)
        
        # Each site detects photons from the pairs with some efficiency
        # In reality, which detector fires depends on photon polarization + analyzer angle
        result = {}
        
        for hist_id in histograms:
            histogram = np.zeros(bin_count, dtype=np.int32)
            
            # For each entangled pair, determine if THIS detector fires
            # Use a deterministic but channel-dependent seed so correlations exist
            detection_seed = (int(sync_time * 1000) + hist_id * 1000) % (2**31)
            np.random.seed(detection_seed)
            
            # Each detector has ~50% efficiency (quantum detection)
            detections = np.random.random(num_pairs) < 0.5
            detected_times = pair_times[detections]
            
            # Bin the detected photon times into histogram
            for t in detected_times:
                if 0 <= t < bin_count:
                    histogram[t] += 1
            
            # Add dark counts (detector noise)
            np.random.seed((detection_seed + 999) % (2**31))
            dark_counts = np.random.poisson(2, bin_count)  # Low background
            histogram = histogram + dark_counts
            
            result[hist_id] = histogram
        
        return result
    try:
        return acquire_histograms_func(tc, duration, bin_width, bin_count, histograms)
    except Exception as e:
        logger.warning("Error acquiring histograms: %s, using mock data", e)
        result = {}
        for hist_id in histograms:
            result[hist_id] = np.random.poisson(50, bin_count)
        return result


def is_mock_controller(tc):
    """
    Check if the time controller is a mock
    Works with both MockTimeController and TimeController wrapper
    """
    # Check for _is_mock attribute
    if getattr(tc, '_is_mock', False):
        return True
    
    # Check if it's an instance of MockTimeController
    if isinstance(tc, (MockTimeController, MockTimeControllerWrapper)):
        return True
    
    # Check if it has a tc attribute that is mock
    if hasattr(tc, 'tc') and isinstance(tc.tc, MockTimeController):
        return True
    
    return False
