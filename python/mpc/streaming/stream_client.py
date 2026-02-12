"""
Time Controller streaming client integration.

This module wraps the IDQ Time Controller StreamClient for receiving
timestamp streams over ZMQ.
"""

import logging
import threading
from typing import Callable, Optional
from gui_components.config import STREAM_PORTS_BASE
import zmq

logger = logging.getLogger(__name__)


class TimeControllerStreamClient:
    """
    Manages streaming connections to Time Controller channels.
    
    Each channel (1-4) streams on its own port (4242-4245).
    """
    
    def __init__(self, tc_address: str, is_mock: bool = False, site_role: str = None):
        """
        Initialize stream client.
        
        Args:
            tc_address: Time Controller IP address
            is_mock: If True, use mock streaming (for testing)
            site_role: Site role ("SERVER" or "CLIENT") for mock timestamp generation
        """
        self.tc_address = tc_address
        self.is_mock = is_mock
        self.site_role = site_role
        self.stream_threads = {}  # channel -> thread
        self.stream_clients = {}  # channel -> StreamClient instance
        self.running = {}  # channel -> bool
        
        if is_mock:
            logger.warning("⚠️ MOCK STREAMING MODE - Using simulated timestamp streams")
        else:
            logger.info(f"TimeControllerStreamClient initialized for {tc_address}")
    
    def start_stream(self, channel: int, callback: Callable[[bytes], None], port: int = None):
        """
        Start streaming timestamps from a channel.
        
        Args:
            channel: Channel number (1-4)
            callback: Function to call with binary timestamp data
            port: Optional custom port number (from DLT acquisition ID)
        """
        if channel in self.stream_threads and self.stream_threads[channel].is_alive():
            logger.warning(f"Stream already running for channel {channel}")
            return
        
        if self.is_mock:
            logger.warning(f"⚠️ MOCK: Starting simulated stream for channel {channel}")
            self._start_mock_stream(channel, callback)
        else:
            self._start_real_stream(channel, callback, port)

    def _detect_stream_socket_type(self, addr: str) -> tuple[int, str]:
        """Try to detect the ZMQ socket type used by the DLT stream endpoint."""
        # Important: do NOT "probe" PAIR by connecting a temporary socket.
        # ZMQ PAIR is strictly 1:1, and a probe can occupy the only connection
        # and prevent the real StreamClient from receiving anything.
        candidates: list[tuple[int, str]] = [
            (zmq.PULL, "PULL"),
            (zmq.SUB, "SUB"),
        ]

        ctx = zmq.Context.instance()
        for socket_type, name in candidates:
            sock = None
            try:
                sock = ctx.socket(socket_type)
                sock.setsockopt(zmq.LINGER, 0)
                if socket_type == zmq.SUB:
                    sock.setsockopt(zmq.SUBSCRIBE, b"")
                sock.connect(addr)

                poller = zmq.Poller()
                poller.register(sock, zmq.POLLIN)
                events = dict(poller.poll(timeout=300))
                if sock in events and events[sock] & zmq.POLLIN:
                    # Consume one message to confirm actual traffic.
                    parts = sock.recv_multipart(flags=zmq.NOBLOCK)
                    payload = parts[-1] if len(parts) > 0 else b""
                    if len(payload) > 0:
                        return socket_type, name
            except Exception:
                # Ignore and try next type.
                pass
            finally:
                try:
                    if sock is not None:
                        sock.close(linger=0)
                except Exception:
                    pass

        # Fall back to PAIR (without having touched the endpoint with a PAIR probe).
        return zmq.PAIR, "PAIR"
    
    def _start_real_stream(self, channel: int, callback: Callable[[bytes], None], port: int = None):
        """Start real Time Controller stream via DLT service."""
        try:
            # Use the existing StreamClient from utils.acquisitions.streams
            from utils.acquisitions.streams import StreamClient
            
            # DLT runs on localhost and streams data on the ports from acquisition IDs
            # The acquisition ID format is "tc_address:port" (e.g., "169.254.104.112:5556")
            # but DLT's streaming OUTPUT is on localhost:port, not on the TC's IP!
            if port is None:
                from gui_components.config import STREAM_PORTS_BASE
                port = STREAM_PORTS_BASE + channel
                logger.info(f"Using default TC streaming port {port} for channel {channel}")
            
            # Connect to localhost since DLT is running locally and streams on localhost:port
            addr = f"tcp://localhost:{port}"
            
            logger.info(f"Starting stream on {addr} for channel {channel}")

            socket_type, socket_type_name = self._detect_stream_socket_type(addr)
            logger.info(
                f"Detected stream socket type {socket_type_name} for channel {channel} ({addr})"
            )
            
            # Create stream client
            client = StreamClient(addr, socket_type=socket_type)
            client.message_callback = callback
            
            self.stream_clients[channel] = client
            self.running[channel] = True
            
            # Start the client thread
            client.start()
            
            logger.info(f"Stream started for channel {channel}")
            
        except ImportError as e:
            logger.error(f"Failed to import StreamClient: {e}")
            logger.error("Make sure utils.acquisitions module is available")
        except Exception as e:
            logger.error(f"Failed to start stream for channel {channel}: {e}")
    
    def _start_mock_stream(self, channel: int, callback: Callable[[bytes], None]):
        """Start mock stream for testing."""
        import time
        import random
        
        def mock_stream_worker():
            logger.warning(f"⚠️ MOCK stream worker started for channel {channel}")
            self.running[channel] = True
            
            # Import here to avoid circular dependency
            from mock_time_controller import MockTimeController
            
            # Pass site_role as site_name so mock can differentiate client vs server
            # This ensures correct time offset is applied for each site
            site_name = self.site_role if self.site_role else self.tc_address
            mock_tc = MockTimeController(site_name=site_name)
            
            try:
                while self.running.get(channel, False):
                    # Generate 0.1 seconds worth of timestamps
                    duration_ps = int(0.1 * 1e12)
                    binary_data = mock_tc.generate_timestamps(channel, duration_ps, with_ref_index=True)
                    
                    # Call the callback with mock data
                    callback(binary_data)
                    
                    # Wait before next batch (simulate 10 Hz batch rate)
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"⚠️ MOCK stream error on channel {channel}: {e}")
            finally:
                logger.warning(f"⚠️ MOCK stream stopped for channel {channel}")
                self.running[channel] = False
        
        thread = threading.Thread(target=mock_stream_worker, daemon=True, name=f"MockStream-Ch{channel}")
        self.stream_threads[channel] = thread
        thread.start()
        
        logger.warning(f"⚠️ MOCK stream thread started for channel {channel}")
    
    def stop_stream(self, channel: int):
        """
        Stop streaming from a channel.
        
        Args:
            channel: Channel number (1-4)
        """
        if channel not in self.running or not self.running[channel]:
            logger.debug(f"Stream not running for channel {channel}")
            return
        
        logger.info(f"Stopping stream for channel {channel}")
        self.running[channel] = False
        
        if not self.is_mock and channel in self.stream_clients:
            # Stop the real StreamClient (calls join() internally)
            try:
                self.stream_clients[channel].join()
            except Exception as e:
                logger.error(f"Error stopping StreamClient for channel {channel}: {e}")
        
        # For mock mode, wait for thread to finish (with timeout)
        if self.is_mock and channel in self.stream_threads:
            self.stream_threads[channel].join(timeout=2.0)
            
            if self.stream_threads[channel].is_alive():
                logger.warning(f"Stream thread for channel {channel} did not stop cleanly")
    
    def stop_all_streams(self):
        """Stop all active streams."""
        logger.info("Stopping all streams")
        
        for channel in list(self.running.keys()):
            if self.running[channel]:
                self.stop_stream(channel)
    
    def is_streaming(self, channel: int) -> bool:
        """
        Check if a channel is currently streaming.
        
        Args:
            channel: Channel number (1-4)
        
        Returns:
            True if streaming, False otherwise
        """
        return self.running.get(channel, False)
    
    def __del__(self):
        """Cleanup on deletion."""
        self.stop_all_streams()
