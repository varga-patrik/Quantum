"""Peer-to-peer TCP connection for distributed MPC320 control."""

import socket
import threading
import json
import logging
import time
from typing import Optional, Callable, Dict, Any
from secure_channel import SecureChannel
from gui_components.config import DEBUG_MODE

logger = logging.getLogger(__name__)

# Protocol constants
DEFAULT_PORT = 27015
BUFFER_SIZE = 4096
HEARTBEAT_INTERVAL = 5.0  # seconds
CONNECTION_TIMEOUT = 10.0  # seconds
HANDSHAKE_TIMEOUT = 30.0  # seconds - longer for real network conditions
SEND_TIMEOUT = 3.0  # seconds - socket send timeout for individual operations


class PeerConnection:
    """
    TCP connection supporting both pure server and pure client modes.
    
    Server mode: Only listens for incoming connection (for static IP with port forwarding)
    Client mode: Only connects to server (for NAT/router behind setup)
    """
    
    def __init__(self, mode: str = "server", server_ip: str = "0.0.0.0", port: int = DEFAULT_PORT):
        """
        Initialize connection.
        
        Args:
            mode: "server" (listen only) or "client" (connect only)
            server_ip: For server mode: IP to bind to (0.0.0.0 = all interfaces)
                      For client mode: Server IP to connect to
            port: Port number (server listens on this, client connects to this)
        """
        self.mode = mode
        self.server_ip = server_ip
        self.port = port
        self.peer_ip: Optional[str] = None
        
        # Connection state
        self.connected = False
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.peer_socket: Optional[socket.socket] = None
        
        # Security
        self.secure_channel = SecureChannel()
        self.encryption_ready = False
        
        # Threading
        self.server_thread: Optional[threading.Thread] = None
        self.receiver_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Message handling
        self.command_handlers: Dict[str, Callable] = {}
        self.last_heartbeat = time.time()
        
        if DEBUG_MODE:
            logger.info("PeerConnection initialized: mode=%s, server_ip=%s, port=%d (encrypted)", mode, server_ip, port)
    
    def register_command_handler(self, command: str, handler: Callable):
        """Register a handler function for a specific command type."""
        self.command_handlers[command] = handler
    
    def start(self) -> bool:
        """
        Start connection based on mode.
        
        For server mode: Start listening for incoming connection
        For client mode: Connect to server
        
        Returns:
            bool: True if started successfully
        """
        if self.mode == "server":
            return self._start_server()
        else:
            return self._connect_to_server()
    
    def _start_server(self) -> bool:
        """Start listening for incoming peer connections (server mode only)."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.server_socket.bind((self.server_ip, self.port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)  # Non-blocking accept
            
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            
            # Give server thread time to start
            time.sleep(0.1)
            if DEBUG_MODE:
                logger.info("Server listening on %s:%d (waiting for client...)", self.server_ip, self.port)
            return True
        except Exception as e:
            logger.exception("Failed to start server: %s", e)
            return False
    
    def _send_raw(self, data: dict) -> bool:
        """Send raw unencrypted message (only for handshake)."""
        try:
            message = json.dumps(data) + '\n'
            self.peer_socket.sendall(message.encode('utf-8'))
            # Disable Nagle's algorithm to send immediately
            try:
                self.peer_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except:
                pass  # May already be set
            if DEBUG_MODE:
                logger.info("Sent %s message (%d bytes)", data.get('type', 'UNKNOWN'), len(message))
            return True
        except Exception as e:
            logger.error("Failed to send raw message: %s", e)
            return False
    
    def _receive_raw(self, timeout: float = HANDSHAKE_TIMEOUT) -> Optional[dict]:
        """Receive raw unencrypted message (only for handshake)."""
        try:
            self.peer_socket.settimeout(timeout)
            buffer = ""
            start_time = time.time()
            logger.debug("Waiting to receive message (timeout=%.1fs)...", timeout)
            
            while '\n' not in buffer:
                data = self.peer_socket.recv(BUFFER_SIZE)
                if not data:
                    logger.error("Connection closed while receiving")
                    return None
                buffer += data.decode('utf-8')
            
            line = buffer.split('\n', 1)[0]
            msg = json.loads(line.strip())
            elapsed = time.time() - start_time
            if DEBUG_MODE:
                logger.info("Received %s message (%.2fs)", msg.get('type', 'UNKNOWN'), elapsed)
            return msg
        except socket.timeout:
            logger.error("Timeout after %.1fs waiting for message", timeout)
            return None
        except Exception as e:
            logger.error("Failed to receive raw message: %s", e)
            return None
    
    def _perform_server_handshake(self) -> bool:
        """Perform server side of secure handshake."""
        try:
            # Step 1: Receive client's public key
            msg = self._receive_raw()
            if not msg or msg.get('type') != 'PUBLIC_KEY':
                return False
            
            self.secure_channel.set_peer_public_key(msg['public_key'])
            
            # Step 2: Send our public key
            self._send_raw({
                'type': 'PUBLIC_KEY',
                'public_key': self.secure_channel.get_public_key_pem()
            })
            
            # Step 3: Generate and send encrypted session key
            _, encrypted_key = self.secure_channel.generate_session_key()
            self._send_raw({
                'type': 'SESSION_KEY',
                'encrypted_key': encrypted_key
            })
            
            # Step 3.5: Wait for client acknowledgment that session key was received
            msg = self._receive_raw()
            if not msg or msg.get('type') != 'SESSION_KEY_ACK':
                logger.error("Did not receive SESSION_KEY_ACK")
                return False
            
            # Step 4: Authentication challenge
            challenge = self.secure_channel.create_auth_challenge()
            self._send_raw({
                'type': 'AUTH_CHALLENGE',
                'challenge': challenge
            })
            
            # Step 5: Verify authentication response
            msg = self._receive_raw()
            if not msg or msg.get('type') != 'AUTH_RESPONSE':
                logger.error("Invalid auth response")
                return False
            
            if not self.secure_channel.verify_auth_response(msg['response']):
                logger.error("Authentication failed - wrong password")
                return False
            
            self.encryption_ready = True
            return True
            
        except Exception as e:
            logger.exception("Server handshake error: %s", e)
            return False
    
    def _perform_client_handshake(self) -> bool:
        """Perform client side of secure handshake."""
        try:
            # Step 1: Send our public key
            self._send_raw({
                'type': 'PUBLIC_KEY',
                'public_key': self.secure_channel.get_public_key_pem()
            })
            if DEBUG_MODE:
                logger.info("Sent client public key")
            
            # Step 2: Receive server's public key
            msg = self._receive_raw()
            if not msg or msg.get('type') != 'PUBLIC_KEY':
                return False
            
            self.secure_channel.set_peer_public_key(msg['public_key'])
            if DEBUG_MODE:
                logger.info("Received server public key")
            
            # Step 3: Receive encrypted session key
            msg = self._receive_raw()
            if not msg or msg.get('type') != 'SESSION_KEY':
                logger.error("Did not receive SESSION_KEY")
                return False
            
            self.secure_channel.receive_session_key(msg['encrypted_key'])
            if DEBUG_MODE:
                logger.info("Received and decrypted session key")
            
            # Step 3.5: Send acknowledgment that we received the session key
            self._send_raw({
                'type': 'SESSION_KEY_ACK'
            })
            if DEBUG_MODE:
                logger.info("Sent session key acknowledgment")
            
            # Step 4: Receive authentication challenge
            if DEBUG_MODE:
                logger.info("Waiting for authentication challenge...")
            msg = self._receive_raw()
            if not msg or msg.get('type') != 'AUTH_CHALLENGE':
                logger.error("Did not receive AUTH_CHALLENGE")
                return False
            
            # Step 5: Send authentication response
            if DEBUG_MODE:
                logger.info("Received challenge, sending authentication response")
            response = self.secure_channel.create_auth_response(msg['challenge'])
            self._send_raw({
                'type': 'AUTH_RESPONSE',
                'response': response
            })
            
            self.encryption_ready = True
            self.secure_channel.authenticated = True
            return True
            
        except Exception as e:
            logger.exception("Client handshake error: %s", e)
            return False
    
    def _connect_to_server(self, timeout: float = CONNECTION_TIMEOUT, retries: int = 3) -> bool:
        """Connect to remote server (client mode only)."""
        for attempt in range(retries):
            try:
                if attempt > 0:
                    wait_time = 1.0 * attempt  # Exponential backoff
                    if DEBUG_MODE:
                        logger.info("Retry attempt %d/%d after %.1fs delay", attempt + 1, retries, wait_time)
                    time.sleep(wait_time)
                
                if DEBUG_MODE:
                    logger.info("Connecting to server at %s:%d (attempt %d/%d)", 
                               self.server_ip, self.port, attempt + 1, retries)
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.client_socket.settimeout(timeout)
                
                # Connect to server
                self.client_socket.connect((self.server_ip, self.port))
                
                self.peer_socket = self.client_socket
                self.peer_ip = self.server_ip
                self.connected = True
                
                # Perform secure handshake (client initiates)
                if not self._perform_client_handshake():
                    logger.error("Secure handshake failed")
                    self.connected = False
                    self.peer_socket.close()
                    self.peer_socket = None
                    continue
                
                # Start receiver and heartbeat threads
                self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
                self.receiver_thread.start()
                
                self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                self.heartbeat_thread.start()
                
                if DEBUG_MODE:
                    logger.info("Successfully connected to server at %s:%d (encrypted)", self.server_ip, self.port)
                return True
                
            except socket.timeout:
                logger.warning("Connection attempt %d timed out after %.1f seconds", attempt + 1, timeout)
            except ConnectionRefusedError:
                logger.warning("Connection refused on attempt %d (server not ready yet)", attempt + 1)
            except Exception as e:
                logger.warning("Connection attempt %d failed: %s", attempt + 1, e)
        
        logger.error("Failed to connect to server after %d attempts", retries)
        return False
    
    def _server_loop(self):
        """Server thread: accept incoming connection from peer."""
        while not self.stop_event.is_set():
            try:
                conn, addr = self.server_socket.accept()
                
                if self.peer_socket is None and not self.connected:
                    # Configure socket for low-latency communication
                    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    
                    self.peer_socket = conn
                    self.peer_ip = addr[0]
                    self.connected = True
                    
                    # Perform secure handshake (server responds)
                    if not self._perform_server_handshake():
                        logger.error("Secure handshake failed")
                        self.connected = False
                        self.peer_socket.close()
                        self.peer_socket = None
                        continue
                    
                    # Start receiver and heartbeat threads
                    self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
                    self.receiver_thread.start()
                    
                    self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                    self.heartbeat_thread.start()
                    
                    if DEBUG_MODE:
                        logger.info("Peer connected from %s (encrypted)", addr)
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
                        self._process_encrypted_message(line.strip())
                        
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    logger.error("Receiver error: %s", e)
                self.connected = False
                break
    
    def _process_encrypted_message(self, encrypted_message: str):
        """Process an encrypted received message."""
        try:
            if not self.encryption_ready:
                logger.warning("Received message before encryption ready")
                return
            
            # Decrypt message
            data = self.secure_channel.decrypt_message(encrypted_message)
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
        """Send an encrypted command to the peer with timeout protection."""
        if not self.connected or self.peer_socket is None or not self.encryption_ready:
            return False
        
        try:
            message = {'command': command, **data}
            encrypted = self.secure_channel.encrypt_message(message)
            payload = (encrypted + '\n').encode('utf-8')
            
            # Set socket to non-blocking temporarily with timeout
            old_timeout = self.peer_socket.gettimeout()
            self.peer_socket.settimeout(SEND_TIMEOUT)
            
            try:
                self.peer_socket.sendall(payload)
                return True
            finally:
                # Restore original timeout
                self.peer_socket.settimeout(old_timeout)
                
        except socket.timeout:
            logger.error("Send command timeout after %.1fs for command: %s", SEND_TIMEOUT, command)
            return False
        except Exception as e:
            logger.error("Send command error: %s", e)
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
