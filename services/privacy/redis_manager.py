import os
import json
import logging
import redis
from cryptography.fernet import Fernet
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, encryption_key: str = None):
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=False) # Keep binary for encryption
        
        # Ensure we have a valid key. In production, this must be provided.
        if not encryption_key:
            logger.warning("No encryption key provided. Generating a temporary one. DATA WILL BE LOST ON RESTART IF KEY IS NOT PERSISTED.")
            self.fernet = Fernet(Fernet.generate_key())
        else:
            try:
                self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
            except Exception as e:
                logger.error(f"Invalid encryption key: {e}")
                raise

    def store_mapping(self, doc_id: str, mapping: Dict[str, str], ttl_seconds: int = 86400) -> bool:
        """
        Stores the PII mapping for a document, encrypted.
        TTL defaults to 24 hours.
        """
        try:
            json_data = json.dumps(mapping)
            encrypted_data = self.fernet.encrypt(json_data.encode())
            
            key = f"pii:{doc_id}"
            self.redis.set(key, encrypted_data, ex=ttl_seconds)
            return True
        except Exception as e:
            logger.error(f"Failed to store mapping for {doc_id}: {e}")
            return False

    def get_mapping(self, doc_id: str) -> Optional[Dict[str, str]]:
        """
        Retrieves and decrypts the PII mapping for a document.
        """
        try:
            key = f"pii:{doc_id}"
            encrypted_data = self.redis.get(key)
            
            if not encrypted_data:
                return None
            
            decrypted_data = self.fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to retrieve/decrypt mapping for {doc_id}: {e}")
            return None
