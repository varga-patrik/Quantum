"""Peer-to-peer TCP connection for distributed MPC320 control."""

import socket
import threading
import json
import logging
import time
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

# Protocol constants
DEFAULT_PORT = 27015
BUFFER_SIZE = 4096
HEARTBEAT_INTERVAL = 5.0  # seconds
CONNECTION_TIMEOUT = 10.0  # seconds


class PeerConnection:
    """
    Bidirectional peer-to-peer TCP connection.
    Each instance acts as both server (listening) and client (connecting).
    """
    
    def __init__(self, local_ip: str = "0.0.0.0", server_port: int = DEFAULT_PORT):
        self.local_ip = local_ip
        self.server_port = server_port
        self.peer_ip: Optional[str] = None
        self.peer_port: int = DEFAULT_PORT  # Will be set in connect_to_peer
        
        # Connection state
        self.connected = False
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.peer_socket: Optional[socket.socket] = None
        
        # Threading
        self.server_thread: Optional[threading.Thread] = None
        self.receiver_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Message handling
        self.command_handlers: Dict[str, Callable] = {}
        self.last_heartbeat = time.time()
        
        logger.info("PeerConnection initialized on %s:%d", local_ip, server_port)
    
    def register_command_handler(self, command: str, handler: Callable):
        """Register a handler function for a specific command type."""
        self.command_handlers[command] = handler
    
    def start_server(self):
        """Start listening for incoming peer connections."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.local_ip, self.server_port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)  # Non-blocking accept
            
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            
            # Give server thread time to start
            time.sleep(0.1)
            
            logger.info("Server started listening on %s:%d", self.local_ip, self.server_port)
        except Exception as e:
            logger.exception("Failed to start server: %s", e)
            raise
    
    def connect_to_peer(self, peer_ip: str, peer_port: int = DEFAULT_PORT, timeout: float = CONNECTION_TIMEOUT, retries: int = 3) -> bool:
        """Connect to a remote peer as client with retry logic."""
        self.peer_ip = peer_ip
        self.peer_port = peer_port
        
        for attempt in range(retries):
            try:
                # Check if we already connected via server
                if self.connected and self.peer_socket is not None:
                    logger.info("Already connected to peer via server, skipping client connection")
                    return True
                
                if attempt > 0:
                    wait_time = 1.0 * attempt  # Exponential backoff
                    logger.info("Retry attempt %d/%d after %.1fs delay", attempt + 1, retries, wait_time)
                    time.sleep(wait_time)
                
                logger.info("Attempting to connect to peer at %s:%d (attempt %d/%d)", 
                           peer_ip, self.peer_port, attempt + 1, retries)
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.settimeout(timeout)
                
                # Connect to peer's server port
                self.client_socket.connect((peer_ip, self.peer_port))
                
                self.peer_socket = self.client_socket
                self.connected = True
                
                # Start receiver and heartbeat threads
                self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
                self.receiver_thread.start()
                
                self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                self.heartbeat_thread.start()
                
                logger.info("Successfully connected to peer at %s:%d (via client)", peer_ip, self.peer_port)
                return True
                
            except socket.timeout:
                logger.warning("Connection attempt %d timed out after %.1f seconds", attempt + 1, timeout)
            except ConnectionRefusedError:
                logger.warning("Connection refused on attempt %d (peer not ready yet)", attempt + 1)
            except Exception as e:
                logger.warning("Connection attempt %d failed: %s", attempt + 1, e)
        
        logger.error("Failed to connect to peer after %d attempts", retries)
        return False
    
    def _server_loop(self):
        """Server thread: accept incoming connection from peer."""
        while not self.stop_event.is_set():
            try:
                conn, addr = self.server_socket.accept()
                
                if self.peer_socket is None and not self.connected:
                    self.peer_socket = conn
                    self.peer_ip = addr[0]
                    self.connected = True
                    
                    # Start receiver and heartbeat threads
                    self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
                    self.receiver_thread.start()
                    
                    self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                    self.heartbeat_thread.start()
                    
                    logger.info("Peer connected from %s (via server)", addr)
                else:
                    conn.close()
                    
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error("Server error: %s", e)
                break
    
    def _receiver_loop(self):
        """Receiver thread: continuously receive and process messages."""
        buffer = ""
        
        while not self.stop_event.is_set() and self.connected:
            try:
                if self.peer_socket is None:
                    break
                
                self.peer_socket.settimeout(1.0)
                data = self.peer_socket.recv(BUFFER_SIZE)
                
                if not data:
                    logger.warning("Peer disconnected")
                    self.connected = False
                    break
                
                buffer += data.decode('utf-8')
                
                # Process complete messages (terminated by newline)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        self._process_message(line.strip())
                        
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error("Receiver error: %s", e)
                self.connected = False
                break
    
    def _process_message(self, message: str):
        """Process a received message."""
        try:
            data = json.loads(message)
            command = data.get('command')
            
            if command == 'HEARTBEAT':
                self.last_heartbeat = time.time()
                return
            
            handler = self.command_handlers.get(command)
            if handler:
                handler(data)
                
        except Exception as e:
            logger.error("Message processing error: %s", e)
    
    def _heartbeat_loop(self):
        """Heartbeat thread: periodically send keep-alive messages."""
        while not self.stop_event.is_set() and self.connected:
            try:
                self.send_command('HEARTBEAT', {})
                time.sleep(HEARTBEAT_INTERVAL)
                
                # Check if peer is alive
                if time.time() - self.last_heartbeat > HEARTBEAT_INTERVAL * 3:
                    logger.warning("Peer heartbeat timeout")
                    self.connected = False
                    break
                    
            except Exception:
                if not self.stop_event.is_set():
                    self.connected = False
                break
    
    def send_command(self, command: str, data: Dict[str, Any]) -> bool:
        """Send a command to the peer."""
        if not self.connected or self.peer_socket is None:
            return False
        
        try:
            message = {'command': command, **data}
            self.peer_socket.sendall((json.dumps(message) + '\n').encode('utf-8'))
            return True
        except Exception:
            self.connected = False
            return False
    
    def is_connected(self) -> bool:
        """Check if peer connection is active."""
        return self.connected
    
    def get_peer_ip(self) -> Optional[str]:
        """Get the IP address of the connected peer."""
        return self.peer_ip
    
    def close(self):
        """Close all connections and stop threads."""
        self.stop_event.set()
        self.connected = False
        
        for sock in [self.peer_socket, self.client_socket, self.server_socket]:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        
        # Wait for threads to finish
        for thread in [self.server_thread, self.receiver_thread, self.heartbeat_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=2.0)
