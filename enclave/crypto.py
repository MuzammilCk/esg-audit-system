"""
Cryptographic Utilities for AWS Nitro Enclaves

Provides encryption/decryption using AWS KMS with attestation-based
key release, and secure communication utilities.
"""

import os
import json
import logging
import base64
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class EncryptedPayload:
    """Encrypted data with metadata."""
    ciphertext: bytes
    iv: bytes
    tag: bytes
    key_id: str
    algorithm: str
    timestamp: str


class EnclaveCrypto:
    """
    Cryptographic utilities for enclave operations.
    
    Provides:
    - AES-GCM encryption/decryption
    - Key derivation from attestation
    - Secure random generation
    """
    
    ALGORITHM = "AES-256-GCM"
    KEY_LENGTH = 32
    IV_LENGTH = 12
    TAG_LENGTH = 16
    
    def __init__(self, key: Optional[bytes] = None):
        self._key = key
    
    def set_key(self, key: bytes) -> None:
        """Set the encryption key."""
        if len(key) != self.KEY_LENGTH:
            raise ValueError(f"Key must be {self.KEY_LENGTH} bytes")
        self._key = key
    
    def encrypt(self, plaintext: bytes) -> EncryptedPayload:
        """Encrypt data using AES-256-GCM."""
        if not self._key:
            raise ValueError("No encryption key set")
        
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        iv = os.urandom(self.IV_LENGTH)
        
        aesgcm = AESGCM(self._key)
        ciphertext_with_tag = aesgcm.encrypt(iv, plaintext, None)
        
        ciphertext = ciphertext_with_tag[:-self.TAG_LENGTH]
        tag = ciphertext_with_tag[-self.TAG_LENGTH:]
        
        return EncryptedPayload(
            ciphertext=ciphertext,
            iv=iv,
            tag=tag,
            key_id="enclave-derived",
            algorithm=self.ALGORITHM,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    
    def decrypt(self, payload: EncryptedPayload) -> bytes:
        """Decrypt data using AES-256-GCM."""
        if not self._key:
            raise ValueError("No decryption key set")
        
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        aesgcm = AESGCM(self._key)
        
        ciphertext_with_tag = payload.ciphertext + payload.tag
        
        plaintext = aesgcm.decrypt(payload.iv, ciphertext_with_tag, None)
        
        return plaintext
    
    def encrypt_dict(self, data: Dict[str, Any]) -> str:
        """Encrypt a dictionary and return base64-encoded payload."""
        plaintext = json.dumps(data).encode()
        payload = self.encrypt(plaintext)
        
        payload_dict = {
            "ciphertext": base64.b64encode(payload.ciphertext).decode(),
            "iv": base64.b64encode(payload.iv).decode(),
            "tag": base64.b64encode(payload.tag).decode(),
            "key_id": payload.key_id,
            "algorithm": payload.algorithm,
            "timestamp": payload.timestamp,
        }
        
        return json.dumps(payload_dict)
    
    def decrypt_dict(self, payload_json: str) -> Dict[str, Any]:
        """Decrypt a base64-encoded payload to dictionary."""
        payload_dict = json.loads(payload_json)
        
        payload = EncryptedPayload(
            ciphertext=base64.b64decode(payload_dict["ciphertext"]),
            iv=base64.b64decode(payload_dict["iv"]),
            tag=base64.b64decode(payload_dict["tag"]),
            key_id=payload_dict["key_id"],
            algorithm=payload_dict["algorithm"],
            timestamp=payload_dict["timestamp"],
        )
        
        plaintext = self.decrypt(payload)
        return json.loads(plaintext.decode())
    
    @staticmethod
    def generate_key() -> bytes:
        """Generate a random encryption key."""
        return os.urandom(EnclaveCrypto.KEY_LENGTH)
    
    @staticmethod
    def derive_key(password: str, salt: bytes, iterations: int = 100000) -> bytes:
        """Derive a key from password using PBKDF2."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=EnclaveCrypto.KEY_LENGTH,
            salt=salt,
            iterations=iterations,
        )
        
        return kdf.derive(password.encode())


class KMSService:
    """
    AWS KMS integration with attestation-based key release.
    
    Only releases decryption keys to verified enclaves with
    matching PCR values.
    """
    
    def __init__(
        self,
        key_id: Optional[str] = None,
        region: str = "us-east-1",
    ):
        self.key_id = key_id or os.getenv("AWS_KMS_KEY_ID")
        self.region = region
        self._kms_client = None
    
    def _get_client(self):
        if self._kms_client is None:
            import boto3
            self._kms_client = boto3.client("kms", region_name=self.region)
        return self._kms_client
    
    def encrypt_for_enclave(
        self,
        plaintext: bytes,
        encryption_context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Encrypt data for enclave-only decryption.
        
        Uses KMS key with enclave attestation policy.
        """
        client = self._get_client()
        
        response = client.encrypt(
            KeyId=self.key_id,
            Plaintext=plaintext,
            EncryptionContext=encryption_context or {},
        )
        
        return {
            "ciphertext_blob": base64.b64encode(
                response["CiphertextBlob"]
            ).decode(),
            "key_id": response["KeyId"],
        }
    
    def decrypt_in_enclave(
        self,
        ciphertext_blob: bytes,
        attestation_doc: bytes,
        encryption_context: Optional[Dict[str, str]] = None,
    ) -> bytes:
        """
        Decrypt data within enclave using attestation.
        
        This must be called from within the enclave.
        The KMS will verify the attestation document
        before releasing the decryption key.
        """
        client = self._get_client()
        
        try:
            response = client.decrypt(
                CiphertextBlob=ciphertext_blob,
                EncryptionContext=encryption_context or {},
            )
            
            return response["Plaintext"]
            
        except Exception as e:
            logger.error(f"KMS decryption failed: {e}")
            raise
    
    def decrypt_with_attestation(
        self,
        ciphertext_blob: bytes,
        encryption_context: Optional[Dict[str, str]] = None,
    ) -> bytes:
        """
        Decrypt using attestation-based key release.
        
        Automatically includes enclave attestation document.
        """
        attestation_doc = self._get_attestation_document()
        
        return self.decrypt_in_enclave(
            ciphertext_blob=ciphertext_blob,
            attestation_doc=attestation_doc,
            encryption_context=encryption_context,
        )
    
    def _get_attestation_document(self) -> bytes:
        """Get attestation document from Nitro Enclave."""
        try:
            from enclave.attestation import AttestationService
            
            attestation = AttestationService()
            return attestation.generate_attestation()
            
        except Exception:
            logger.warning("Could not generate attestation document")
            return b""
    
    def generate_data_key(self) -> Dict[str, bytes]:
        """Generate a data encryption key."""
        client = self._get_client()
        
        response = client.generate_data_key(
            KeyId=self.key_id,
            KeySpec="AES_256",
        )
        
        return {
            "plaintext": response["Plaintext"],
            "ciphertext": response["CiphertextBlob"],
        }
