"""GPS clock connection utilities for FS740."""

import socket
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# FS740 connection timeout
FS740_TIMEOUT = 5  # seconds


class FS740Connection:
    """
    Direct connection to FS740 GPS clock via TCP socket.
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
        """Get GPS time from FS740."""
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
    Query GPS time from FS740 GPS clock.
    
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
