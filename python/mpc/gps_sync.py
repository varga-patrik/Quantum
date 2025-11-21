"""GPS clock synchronization and drift measurement utilities."""

import socket
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# FS740 connection timeout (matches C++ implementation)
FS740_TIMEOUT = 5  # seconds


def parse_gps_time(time_str: str) -> Optional[int]:
    """
    Parse GPS time string to picoseconds since midnight.
    
    Format: "HH,MM,SS.pppppppppppp" where p is picoseconds (12 digits)
    Example: "14,23,45.123456789012"
    
    Returns:
        int: Picoseconds since midnight, or None if parsing fails
    """
    try:
        # Remove any whitespace and newlines
        time_str = time_str.strip()
        
        # Split by comma: HH,MM,SS.picoseconds
        parts = time_str.split(',')
        if len(parts) != 3:
            logger.error(f"Invalid GPS time format: {time_str}")
            return None
        
        hours = int(parts[0])
        minutes = int(parts[1])
        
        # Split seconds and picoseconds
        sec_parts = parts[2].split('.')
        if len(sec_parts) != 2:
            logger.error(f"Invalid seconds format: {parts[2]}")
            return None
        
        seconds = int(sec_parts[0])
        pico_str = sec_parts[1]
        
        # Normalize to 12 digits (pad with zeros if needed)
        pico_str = pico_str.ljust(12, '0')[:12]
        picoseconds = int(pico_str)
        
        # Convert to total picoseconds since midnight
        total_pico = (hours * 3600 + minutes * 60 + seconds) * 1_000_000_000_000 + picoseconds
        
        return total_pico
        
    except Exception as e:
        logger.error(f"Failed to parse GPS time '{time_str}': {e}")
        return None


def calculate_time_diff(time1_str: str, time2_str: str) -> Optional[int]:
    """
    Calculate time difference between two GPS timestamps.
    
    Args:
        time1_str: First GPS time string (format: "HH,MM,SS.pppppppppppp")
        time2_str: Second GPS time string (format: "HH,MM,SS.pppppppppppp")
    
    Returns:
        int: Time difference in picoseconds (time1 - time2), or None if parsing fails
    """
    pico1 = parse_gps_time(time1_str)
    pico2 = parse_gps_time(time2_str)
    
    if pico1 is None or pico2 is None:
        return None
    
    return pico1 - pico2


def format_time_diff(pico_diff: int) -> Tuple[str, str]:
    """
    Format picosecond time difference into human-readable string.
    
    Args:
        pico_diff: Time difference in picoseconds
    
    Returns:
        Tuple of (formatted_string, unit)
        Example: ("123.456", "ns") or ("1.234", "μs")
    """
    abs_diff = abs(pico_diff)
    sign = "-" if pico_diff < 0 else "+"
    
    if abs_diff < 1_000:  # < 1 nanosecond
        return f"{sign}{abs_diff}", "ps"
    elif abs_diff < 1_000_000:  # < 1 microsecond
        return f"{sign}{abs_diff / 1_000:.3f}", "ns"
    elif abs_diff < 1_000_000_000:  # < 1 millisecond
        return f"{sign}{abs_diff / 1_000_000:.3f}", "μs"
    elif abs_diff < 1_000_000_000_000:  # < 1 second
        return f"{sign}{abs_diff / 1_000_000_000:.3f}", "ms"
    else:
        return f"{sign}{abs_diff / 1_000_000_000_000:.3f}", "s"


class FS740Connection:
    """
    Direct connection to FS740 GPS clock via TCP socket.
    Matches C++ FSUtil implementation.
    """
    
    def __init__(self, ip: str, port: int = 5025, timeout: int = 5):
        """
        Connect to FS740 GPS clock.
        
        Args:
            ip: FS740 IP address
            port: SCPI port (default 5025)
            timeout: Socket timeout in seconds
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.connected = False
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((ip, port))
            self.connected = True
            logger.info(f"Connected to FS740 at {ip}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to FS740: {e}")
            self.connected = False
    
    def write(self, command: str) -> bool:
        """Send SCPI command to FS740."""
        if not self.connected or not self.sock:
            return False
        
        try:
            if not command.endswith('\n'):
                command += '\n'
            self.sock.sendall(command.encode('ascii'))
            return True
        except Exception as e:
            logger.error(f"FS740 write error: {e}")
            self.connected = False
            return False
    
    def read(self, buffer_size: int = 1024) -> Optional[str]:
        """Read response from FS740."""
        if not self.connected or not self.sock:
            return None
        
        try:
            data = self.sock.recv(buffer_size)
            if data:
                return data.decode('ascii').strip()
            return None
        except socket.timeout:
            logger.warning("FS740 read timeout")
            return None
        except Exception as e:
            logger.error(f"FS740 read error: {e}")
            self.connected = False
            return None
    
    def query(self, command: str) -> Optional[str]:
        """Send query and read response."""
        if self.write(command):
            return self.read()
        return None
    
    def get_gps_time(self) -> Optional[str]:
        """Get GPS time from FS740 (matches C++ print_gpstime())."""
        return self.query("SYST:TIME?")
    
    def close(self):
        """Close connection to FS740."""
        if self.sock:
            try:
                self.sock.close()
                logger.info("Closed FS740 connection")
            except Exception:
                pass
        self.connected = False


def get_gps_time(fs740) -> Optional[str]:
    """
    Query GPS time from FS740 GPS clock (matches C++ implementation).
    
    Args:
        fs740: FS740Connection object
    
    Returns:
        str: GPS time string or None if query fails
    """
    try:
        if isinstance(fs740, FS740Connection):
            return fs740.get_gps_time()
        else:
            # Fallback: try Time Controller via ZMQ (for backward compatibility)
            from utils.common import zmq_exec
            time_str = zmq_exec(fs740, "SYST:TIME?")
            return time_str.strip()
    except Exception as e:
        logger.error(f"Failed to get GPS time: {e}")
        return None


def get_precise_computer_time() -> str:
    """
    Get computer time in GPS format with nanosecond precision.
    
    Note: Python's datetime only provides microsecond precision,
    so the last 6 digits (picoseconds) will always be 000000.
    This matches C++ implementation which uses nanoseconds.
    
    Returns:
        str: Time in GPS format "HH,MM,SS.pppppppppppp"
    """
    import time
    
    # Get time with nanosecond precision using time.time_ns()
    now_ns = time.time_ns()
    
    # Convert to hours, minutes, seconds
    total_seconds = now_ns // 1_000_000_000
    hours = (total_seconds // 3600) % 24
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    # Get nanoseconds within the second
    nanoseconds = now_ns % 1_000_000_000
    
    # Convert nanoseconds to 9-digit string, pad with 000 for picoseconds
    return f"{hours},{minutes},{seconds}.{nanoseconds:09d}000"


def measure_local_drift(fs740, samples: int = 10) -> list:
    """
    Measure drift between computer clock and GPS clock (matches C++ measure_timedrift()).
    
    Args:
        fs740: FS740Connection object or Time Controller ZMQ socket
        samples: Number of samples to take
    
    Returns:
        list: List of drift measurements in picoseconds
    """
    import time
    
    drifts = []
    
    for i in range(samples):
        try:
            # Get computer time with nanosecond precision
            computer_time = get_precise_computer_time()
            
            # Get GPS time
            gps_time = get_gps_time(fs740)
            
            if gps_time:
                drift = calculate_time_diff(gps_time, computer_time)
                if drift is not None:
                    drifts.append(drift)
                    logger.debug(f"Sample {i+1}: drift = {drift} ps")
        
        except Exception as e:
            logger.error(f"Error measuring drift: {e}")
        
        if i < samples - 1:
            time.sleep(1)
    
    return drifts


def calculate_peer_offset(local_gps: str, remote_gps: str) -> Optional[int]:
    """
    Calculate time offset between two GPS clocks on different computers.
    
    Args:
        local_gps: Local GPS time string
        remote_gps: Remote GPS time string received via peer connection
    
    Returns:
        int: Offset in picoseconds (local - remote), or None if calculation fails
    """
    return calculate_time_diff(local_gps, remote_gps)


def write_diff_to_file(drift: int, filename: str = "diff_data.csv"):
    """
    Write time drift measurement to CSV file (matches C++ implementation).
    
    Args:
        drift: Time drift in picoseconds
        filename: Output CSV filename
    """
    import os
    
    try:
        # Convert to seconds (like C++ does: drift / 1e12)
        drift_seconds = drift / 1_000_000_000_000.0
        
        # Append to file
        with open(filename, 'a') as f:
            f.write(f"{drift_seconds}\n")
        
        logger.debug(f"Wrote drift {drift_seconds}s to {filename}")
    except Exception as e:
        logger.error(f"Failed to write drift to file: {e}")


def is_earlier_time(time1_str: str, time2_str: str) -> bool:
    """
    Check if time1 is earlier than time2 (matches C++ implementation).
    
    Args:
        time1_str: First GPS time string
        time2_str: Second GPS time string
    
    Returns:
        bool: True if time1 < time2
    """
    diff = calculate_time_diff(time1_str, time2_str)
    return diff is not None and diff < 0


def wait_until(fs740, target_time_str: str, poll_interval: float = 0.001):
    """
    Wait until GPS clock reaches target time (matches C++ polling implementation).
    
    This provides microsecond-accurate waiting by polling the GPS clock,
    which is more precise than time.sleep().
    
    Args:
        fs740: FS740Connection object or Time Controller ZMQ socket
        target_time_str: Target GPS time string to wait for
        poll_interval: Polling interval in seconds (default 1ms)
    """
    import time
    
    logger.info(f"Waiting until GPS time: {target_time_str}")
    
    while True:
        current_time = get_gps_time(fs740)
        if current_time is None:
            logger.error("Failed to get GPS time during wait_until")
            break
        
        # Check if we've reached or passed target time
        if not is_earlier_time(target_time_str, current_time):
            break
        
        time.sleep(poll_interval)
    
    logger.info(f"Target time reached: {target_time_str}")
