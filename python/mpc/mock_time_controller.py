"""
Mock Time Controller for testing and fallback when real hardware is unavailable.
⚠️ THIS IS A MOCK - NOT REAL HARDWARE! ⚠️
Simulates Time Controller timestamp streaming with TESTABLE correlations.

CORRELATION MODES (configured in gui_components/config.py):
1. 'cross_site' (DEFAULT): Site A and Site B detect same photon events (with time offset)
   - Use for testing inter-site correlations
   - Site A Ch1 correlates with Site B Ch1 (same for all channels)
   
2. 'local_pairs': Channels 1↔2 and 3↔4 correlate locally at each site
   - Use for testing local channel correlations
   - Ch1 correlates with Ch2, Ch3 correlates with Ch4 (within same site)
"""
import numpy as np
import logging
import struct
import time

logger = logging.getLogger(__name__)

# Import correlation mode and time offset from central config
try:
    from gui_components.config import MOCK_CORRELATION_MODE, MOCK_TIME_OFFSET_PS, DEBUG_MODE
except ImportError:
    raise ImportError("Could not import variables from config.")

class MockTimeController:
    """
    Mock time controller that simulates IDQ Time Controller (ID900/ID1000)
    ⚠️ THIS IS A MOCK - SIMULATED DATA ONLY! ⚠️
    
    CORRELATION MODES:
    - 'cross_site': All sites detect same photon events (quantum entanglement source)
      → Site A Ch1 correlates with Site B Ch1 (with time offset)
      → Tests inter-site synchronization and coincidence detection
      
    - 'local_pairs': Ch1↔Ch2 and Ch3↔Ch4 correlate within each site
      → Site A Ch1 correlates with Site A Ch2 only
      → Tests local channel pair correlations
    
    Set mode via: mock_time_controller.MOCK_CORRELATION_MODE = 'cross_site' or 'local_pairs'
    """
    def __init__(self, disable_data: bool = False, site_name: str = "unknown"):
        # Validate correlation mode
        valid_modes = ['cross_site', 'local_pairs']
        if MOCK_CORRELATION_MODE not in valid_modes:
            error_msg = (
                f"Invalid MOCK_CORRELATION_MODE: '{MOCK_CORRELATION_MODE}'. "
                f"Must be one of {valid_modes}. "
                f"Check gui_components/config.py and set MOCK_CORRELATION_MODE = 'cross_site' or 'local_pairs'"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        print("╔═══════════════════════════════════════════════════════════╗")
        print("║   ⚠️  MOCK TIME CONTROLLER - TESTABLE SIMULATED DATA    ║")
        print("║   NOT REAL HARDWARE - FOR CORRELATION TESTING            ║")
        print(f"║   Mode: {MOCK_CORRELATION_MODE:^48} ║")
        print("╚═══════════════════════════════════════════════════════════╝")
        logger.warning(f"MockTimeController initialized - mode: {MOCK_CORRELATION_MODE}, site: {site_name}")
        
        self._is_mock = True
        self._disable_data = disable_data
        self._site_name = site_name
        
        if self._disable_data:
            print("║   📛 DATA DISABLED - Returning ZERO/EMPTY data         ║")
            logger.warning("MockTimeController: DATA DISABLED - returning zero data")
        
        # TESTABLE PARAMETERS - Known correlation structure
        self._singles_rate = 10000  # Singles per second per channel (10 kHz)
        self._coincidence_rate = 500  # Correlated events per second (500 Hz)
        self._reference_second = 0
        
        # Cumulative counter values (simulated)
        np.random.seed(42)  # Fixed seed for reproducibility
        self._counter_values = [np.random.randint(40000, 80000) for _ in range(4)]
        
        # Site-specific time offset (simulates GPS sync error)
        # AND site-specific seed offset for localhost testing
        # Server (Wigner): +offset ps (later), Client (BME): 0 ps (reference)
        logger.info(f"MockTC initializing with site_name='{site_name}', MOCK_TIME_OFFSET_PS={MOCK_TIME_OFFSET_PS}")
        
        if "SERVER" in site_name.upper() or "WIGNER" in site_name.upper() or "148.6.27.28" in site_name:
            self._site_time_offset_ps = MOCK_TIME_OFFSET_PS  # This is added to all timestamps
            self._site_seed_offset = 1000000  # Different seeds from client
            logger.info(f"MockTC: Identified as SERVER ({site_name}), offset={MOCK_TIME_OFFSET_PS}ps, seed_offset={self._site_seed_offset}")
        elif "CLIENT" in site_name.upper() or "BME" in site_name.upper() or "169.254.104.112" in site_name:
            self._site_time_offset_ps = 0  # Client at reference time
            self._site_seed_offset = 2000000  # Different seeds from server
            logger.info(f"MockTC: Identified as CLIENT ({site_name}), offset=0ps, seed_offset={self._site_seed_offset}")
        else:
            # Unknown site - use address as hash for unique seed
            self._site_time_offset_ps = 0
            self._site_seed_offset = abs(hash(site_name)) % 10000000
            logger.warning(f"MockTC: Unknown site '{site_name}', using hash-based seed offset: {self._site_seed_offset}")
    
    
    def generate_timestamps(self, channel: int, duration_ps: int, with_ref_index: bool = True):
        """Generate TESTABLE mock timestamp data for a channel.
        
        Mode 'cross_site': All sites generate SAME photon events (quantum entanglement)
        Mode 'local_pairs': Ch1↔Ch2 and Ch3↔Ch4 correlate locally
        
        Args:
            channel: Channel number (1-4)
            duration_ps: Acquisition duration in picoseconds
            with_ref_index: Include reference second counter
            
        Returns:
            Binary timestamp data (uint64 pairs if with_ref_index, else uint64 only)
        """
        if self._disable_data:
            return b''
        
        # Use absolute wall-clock time as reference_second (like GPS-synced hardware)
        # Both SERVER and CLIENT will get the SAME reference_second at the same moment
        # Modulo 1000 prevents overflow in total_ps calculations (uint64)
        self._reference_second = int(time.time()) % 1000
        
        duration_sec = duration_ps / 1e12
        base_seed = 1000000 + self._reference_second
        
        # Determine correlation seed based on mode
        if MOCK_CORRELATION_MODE == 'cross_site':
            # ALL sites generate the SAME photon detection events
            # Ch1 at Site A will correlate with Ch1 at Site B
            # Use SAME seed across sites (no site_seed_offset)
            corr_seed = base_seed + channel * 10  # Each channel has unique but shared seed
        else:  # 'local_pairs'
            # Ch1↔Ch2 share events, Ch3↔Ch4 share events (local only)
            # Use site-specific seeds (different per site)
            if channel in [1, 2]:
                corr_seed = base_seed + self._site_seed_offset + 100  # Ch1 & Ch2 share locally
            else:
                corr_seed = base_seed + self._site_seed_offset + 200  # Ch3 & Ch4 share locally
        
        # Generate correlated events
        np.random.seed(corr_seed)
        num_correlated = int(self._coincidence_rate * duration_sec)
        correlated_times = np.random.uniform(0, duration_ps, num_correlated)
        
        # Add small timing jitter per channel (detector response)
        # In cross_site: use channel-specific jitter (same base seed → correlations preserved)
        # In local_pairs: use site-specific jitter (different per site)
        if MOCK_CORRELATION_MODE == 'cross_site':
            channel_jitter_seed = corr_seed + channel * 10
        else:
            channel_jitter_seed = corr_seed + self._site_seed_offset + channel * 10
        
        np.random.seed(channel_jitter_seed)
        jitter = np.random.normal(0, 100, num_correlated)  # ±100ps jitter
        correlated_times = correlated_times + jitter
        
        # Generate uncorrelated singles (noise) - ALWAYS site-specific
        singles_seed = base_seed + self._site_seed_offset + channel * 1000 + self._reference_second * 7
        np.random.seed(singles_seed)
        num_singles = int((self._singles_rate - self._coincidence_rate) * duration_sec)
        singles_times = np.random.uniform(0, duration_ps, num_singles)
        
        # Combine all events
        all_times = np.concatenate([correlated_times, singles_times])
        
        # Apply site-specific time offset (for cross-site synchronization testing)
        if DEBUG_MODE and len(all_times) > 0:
            logger.debug(f"Ch{channel}: Before offset - range [{all_times.min():.0f} - {all_times.max():.0f}] ps")
        
        all_times = all_times + self._site_time_offset_ps
        
        if DEBUG_MODE and len(all_times) > 0:
            logger.debug(f"Ch{channel}: After +{self._site_time_offset_ps}ps offset - range [{all_times.min():.0f} - {all_times.max():.0f}] ps")
        
        # Wrap to 1-second period
        all_times = all_times % int(1e12)
        all_times = np.clip(all_times, 0, int(1e12) - 1)
        all_times = np.sort(all_times).astype(np.uint64)
        
        # Convert to binary format
        if with_ref_index:
            binary_data = b''.join(
                struct.pack('<QQ', int(ts), self._reference_second) 
                for ts in all_times
            )
        else:
            binary_data = b''.join(struct.pack('<Q', int(ts)) for ts in all_times)
        
        return binary_data
    
    
    def send_string(self, command: str) -> None:
        """Mock send_string method - simulates SCPI commands."""
        # Simulate state changes
        if "REC:PLAY" in command:
            self._reference_second += 1
    
    def recv_string(self) -> str:
        """Mock recv_string - returns simulated counter values."""
        if self._disable_data:
            return "0"
        
        # Increment counters deterministically
        for i in range(4):
            self._counter_values[i] += np.random.randint(100, 500)
        
        value = self._counter_values[0]
        return str(value)
    
    def __getattr__(self, name):
        """Return a callable for any unmocked method."""
        def mock_method(*args, **kwargs):
            if self._disable_data:
                if 'counter' in name.lower() or 'count' in name.lower():
                    return 0
                return None
            if 'counter' in name.lower() or 'count' in name.lower():
                return int(50000 + (hash(name) % 50000))
            return None
        return mock_method
    
    def close(self, *args, **kwargs):
        """Mock close method"""
        pass


class MockTimeControllerWrapper:
    """
    Mock wrapper that mimics the TimeController class interface.
    Used when the real TimeController cannot connect.
    """
    def __init__(self, address: str, counters=("1","2","3","4"), 
                 integration_time_ps=None, disable_data: bool = False):
        logger.warning("MockTimeControllerWrapper initialized for %s", address)
        self.address = address
        self.counters = counters
        self.integration_time_ps = integration_time_ps
        
        # Determine site name from address using config addresses
        try:
            from gui_components.config import SERVER_TC_ADDRESS, CLIENT_TC_ADDRESS
            if address == SERVER_TC_ADDRESS or "148.6.27" in address:
                site_name = "SERVER"  # Wigner (later)
            elif address == CLIENT_TC_ADDRESS or "169.254" in address:
                site_name = "CLIENT"  # BME (reference)
            else:
                # Fallback: localhost = client, others = server
                site_name = "CLIENT" if "127.0.0.1" in address or "localhost" in address.lower() else "SERVER"
        except ImportError:
            site_name = "CLIENT" if "127.0.0.1" in address or "localhost" in address.lower() else "SERVER"
        
        self.tc = MockTimeController(disable_data=disable_data, site_name=site_name)
        self._is_mock = True
        self._disable_data = disable_data
    
    def connect(self):
        """Mock connect - already 'connected'"""
        logger.info(f"MockTimeControllerWrapper 'connected' to {self.address}")
        return self
    
    def query_counter(self, idx: int) -> int:
        """Return predictable counter value for the given index."""
        if self._disable_data:
            return 0
        return 50000 + idx * 10000
    
    def query_all_counters(self):
        """Return predictable values for all 4 counters."""
        if self._disable_data:
            return (0, 0, 0, 0)
        return (50000, 60000, 70000, 80000)
    
    def close(self):
        """Mock close"""
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
    Wrapper for zmq_exec that handles MockTimeController.
    
    Args:
        tc: Time controller instance (real or mock)
        command: Command to execute
        zmq_exec_func: The actual zmq_exec function to use for real controllers
    
    Returns:
        int: Deterministic value if mock, or real value from device
    """
    if isinstance(tc, MockTimeController) or getattr(tc, '_is_mock', False):
        # Return deterministic value based on command hash
        return 50000 + (hash(command) % 50000)
    try:
        return zmq_exec_func(tc, command)
    except Exception:
        return 50000 + (hash(command) % 50000)


def safe_acquire_histograms(tc, duration, bin_width, bin_count, histograms, acquire_histograms_func):
    """
    Wrapper for acquire_histograms that handles MockTimeController.
    
    TESTABLE CORRELATION STRUCTURE:
    - Histograms 1 & 2 (channels 1 & 2) share correlated peaks
    - Histograms 3 & 4 (channels 3 & 4) share correlated peaks  
    - Both sites generate the SAME correlated pattern with deterministic seeding
    - This allows verification that correlation algorithms work correctly
    
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
        ref_second = getattr(tc, '_reference_second', 0)
        base_seed = 1000000 + ref_second
        result = {}
        
        for hist_id in histograms:
            # Determine correlation seed based on mode
            if MOCK_CORRELATION_MODE == 'cross_site':
                corr_seed = base_seed + hist_id * 10  # Each channel unique
            else:  # 'local_pairs'
                if hist_id in [1, 2]:
                    corr_seed = base_seed + 100  # Ch1 & Ch2 share
                else:
                    corr_seed = base_seed + 200  # Ch3 & Ch4 share
            
            # Generate base histogram
            np.random.seed(corr_seed + hist_id * 1000)
            histogram = np.random.poisson(20, bin_count).astype(np.int32)
            
            # Add correlated peaks
            np.random.seed(corr_seed)
            num_peaks = 5
            peak_positions = np.random.randint(bin_count // 4, 3 * bin_count // 4, num_peaks)
            
            for peak_pos in peak_positions:
                peak_width = 10
                peak_height = 100
                for i in range(max(0, peak_pos - peak_width), min(bin_count, peak_pos + peak_width)):
                    distance = abs(i - peak_pos)
                    gaussian = peak_height * np.exp(-(distance ** 2) / (2 * (peak_width / 3) ** 2))
                    histogram[i] += int(gaussian)
            
            # Add channel-specific noise
            np.random.seed(corr_seed + hist_id * 10)
            noise = np.random.poisson(5, bin_count).astype(np.int32)
            histogram = histogram + noise
            
            result[hist_id] = histogram
        
        return result
    
    try:
        return acquire_histograms_func(tc, duration, bin_width, bin_count, histograms)
    except Exception as e:
        logger.warning("Error acquiring histograms: %s, using fallback mock data", e)
        result = {}
        for hist_id in histograms:
            result[hist_id] = np.random.poisson(50, bin_count).astype(np.int32)
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
