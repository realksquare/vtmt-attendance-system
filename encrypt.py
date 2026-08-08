"""
AES-256 GCM Encryption and Decryption for Biometric Face Embeddings.
Stores secret key securely and converts NumPy vectors to/from encrypted bytes.
"""

import os
import numpy as np
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from config import SECRET_KEY_PATH


def get_or_create_key(key_path: str = SECRET_KEY_PATH) -> bytes:
    """Load existing AES key or generate a new 256-bit key."""
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            key = f.read()
            if len(key) == 32:
                return key
    
    # Generate new 32-byte (256-bit) AES key
    key = get_random_bytes(32)
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(key)
    return key


def encrypt_embedding(embedding: np.ndarray, key: bytes) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt a 512-D float32 face embedding NumPy array using AES-256-GCM.
    
    Returns:
        (ciphertext, nonce, tag)
    """
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding, dtype=np.float32)
    
    raw_bytes = embedding.astype(np.float32).tobytes()
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(raw_bytes)
    return ciphertext, cipher.nonce, tag


def decrypt_embedding(ciphertext: bytes, nonce: bytes, tag: bytes, key: bytes) -> np.ndarray:
    """
    Decrypt AES-256-GCM ciphertext back into a 512-D float32 NumPy array in memory.
    """
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    raw_bytes = cipher.decrypt_and_verify(ciphertext, tag)
    return np.frombuffer(raw_bytes, dtype=np.float32)
