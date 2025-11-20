"""Secure communication channel with automatic encryption."""

import os
import json
import base64
import logging
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

# Pre-shared authentication password (change this for production!)
AUTH_PASSWORD = "MPC320_SECURE_2025"


class SecureChannel:
    """
    Provides encrypted communication using hybrid encryption:
    1. RSA key exchange for establishing shared AES key
    2. AES-256-GCM for fast symmetric encryption of all messages
    3. Password-based authentication to prevent unauthorized connections
    """
    
    def __init__(self):
        self.aes_key: Optional[bytes] = None
        self.authenticated = False
        
        # Generate RSA key pair for key exchange
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()
        
        logger.info("SecureChannel initialized with RSA-2048 + AES-256")
    
    def get_public_key_pem(self) -> str:
        """Get public key in PEM format for exchange."""
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode('utf-8')
    
    def set_peer_public_key(self, pem_data: str):
        """Set peer's public key from PEM format."""
        self.peer_public_key = serialization.load_pem_public_key(
            pem_data.encode('utf-8'),
            backend=default_backend()
        )
    
    def generate_session_key(self) -> Tuple[bytes, str]:
        """
        Generate AES session key and encrypt it with peer's public key.
        Returns: (raw_key, encrypted_key_base64)
        """
        self.aes_key = os.urandom(32)  # 256-bit AES key
        
        # Encrypt key with peer's RSA public key
        encrypted_key = self.peer_public_key.encrypt(
            self.aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return self.aes_key, base64.b64encode(encrypted_key).decode('utf-8')
    
    def receive_session_key(self, encrypted_key_base64: str):
        """Decrypt received AES session key using our private key."""
        encrypted_key = base64.b64decode(encrypted_key_base64)
        
        self.aes_key = self.private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        logger.info("Session key established")
    
    def encrypt_message(self, message: dict) -> str:
        """
        Encrypt message using AES-256-GCM.
        Returns base64-encoded: nonce + tag + ciphertext
        """
        if not self.aes_key:
            raise RuntimeError("Session key not established")
        
        # Serialize message
        plaintext = json.dumps(message).encode('utf-8')
        
        # Generate random nonce (12 bytes for GCM)
        nonce = os.urandom(12)
        
        # Encrypt with AES-GCM
        cipher = Cipher(
            algorithms.AES(self.aes_key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        # Package: nonce + tag + ciphertext
        package = nonce + encryptor.tag + ciphertext
        return base64.b64encode(package).decode('utf-8')
    
    def decrypt_message(self, encrypted_base64: str) -> dict:
        """
        Decrypt message using AES-256-GCM.
        Returns decrypted message dict.
        """
        if not self.aes_key:
            raise RuntimeError("Session key not established")
        
        # Unpackage
        package = base64.b64decode(encrypted_base64)
        nonce = package[:12]
        tag = package[12:28]
        ciphertext = package[28:]
        
        # Decrypt with AES-GCM
        cipher = Cipher(
            algorithms.AES(self.aes_key),
            modes.GCM(nonce, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        return json.loads(plaintext.decode('utf-8'))
    
    def create_auth_challenge(self) -> str:
        """Create authentication challenge (hash of password + random nonce)."""
        nonce = os.urandom(16)
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(AUTH_PASSWORD.encode('utf-8'))
        digest.update(nonce)
        challenge = digest.finalize()
        
        self.auth_nonce = nonce
        return base64.b64encode(nonce).decode('utf-8')
    
    def verify_auth_response(self, response_base64: str) -> bool:
        """Verify authentication response."""
        response = base64.b64decode(response_base64)
        
        # Compute expected response
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(AUTH_PASSWORD.encode('utf-8'))
        digest.update(self.auth_nonce)
        expected = digest.finalize()
        
        self.authenticated = (response == expected)
        return self.authenticated
    
    def create_auth_response(self, challenge_base64: str) -> str:
        """Create authentication response to challenge."""
        nonce = base64.b64decode(challenge_base64)
        
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(AUTH_PASSWORD.encode('utf-8'))
        digest.update(nonce)
        response = digest.finalize()
        
        return base64.b64encode(response).decode('utf-8')
