"""
Mock Time Controller for testing and fallback when real hardware is unavailable.
Returns random values between 20000 and 100000 to simulate real measurements.
"""
import random
import numpy as np
import logging

logger = logging.getLogger(__name__)


class MockTimeController:
    """
    Mock time controller that simulates a real time controller
    Returns random numbers to simulate real measurements when hardware is unavailable
    """
    def __init__(self):
        print("⚠️ Using MockTimeController - returning random values between 20000 and 100000")
        logger.warning("MockTimeController initialized - using simulated data")
        self._is_mock = True
        # Simulate some internal state for more realistic behavior
        self._base_values = [random.randint(40000, 80000) for _ in range(4)]
    
    def send_string(self, command: str) -> None:
        """Mock send_string method (does nothing)"""
        logger.debug(f"Mock send_string: {command}")
        pass
    
    def recv_string(self) -> str:
        """Mock recv_string - returns random counter value"""
        value = random.randint(20000, 100000)
        logger.debug(f"Mock recv_string: {value}")
        return str(value)
    
    def __getattr__(self, name):
        """Return a callable that returns random numbers for any method call"""
        def mock_method(*args, **kwargs):
            # Return realistic random values with some variation
            if name in ['send_string', 'recv_string']:
                return random.randint(20000, 100000)
            return random.randint(20000, 100000)
        return mock_method
    
    def close(self, *args, **kwargs):
        """Mock close method"""
        logger.debug("Mock close called")
        pass


class MockTimeControllerWrapper:
    """
    Mock wrapper that mimics the TimeController class interface
    This is used when the real TimeController cannot connect
    """
    def __init__(self, address: str, counters=("1","2","3","4"), integration_time_ps=None):
        logger.warning("MockTimeControllerWrapper initialized for %s", address)
        self.address = address
        self.counters = counters
        self.integration_time_ps = integration_time_ps
        self.tc = MockTimeController()
        self._is_mock = True
    
    def connect(self):
        """Mock connect - already 'connected'"""
        logger.info(f"MockTimeControllerWrapper 'connected' to {self.address}")
        return self
    
    def query_counter(self, idx: int) -> int:
        """Return random counter value for the given index"""
        value = random.randint(20000, 100000)
        logger.debug(f"Mock query_counter({idx}): {value}")
        return value
    
    def query_all_counters(self):
        """Return random values for all 4 counters"""
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
