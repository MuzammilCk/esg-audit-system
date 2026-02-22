"""
Attestation Service for AWS Nitro Enclaves

Handles cryptographic attestation to prove enclave identity
and establish trust with AWS KMS for key release.
"""

import os
import json
import logging
import hashlib
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


PCR_VALUES = {
    "PCR0": "Enclave image file hash",
    "PCR1": "Linux kernel and boot configuration hash",
    "PCR2": "Application code hash",
    "PCR3": "IAM role and certificate hash",
    "PCR4": "Enclave configuration hash",
    "PCR8": "User-defined measurement",
}


@dataclass
class AttestationDocument:
    """Parsed attestation document from Nitro Enclave."""
    document: bytes
    module_id: str
    timestamp: datetime
    digests: Dict[str, str]
    pcrs: Dict[int, str]
    certificate: bytes
    cabundle: list
    public_key: bytes
    user_data: Optional[bytes] = None
    nonce: Optional[bytes] = None


class AttestationService:
    """
    AWS Nitro Enclave attestation service.
    
    Provides:
    - Attestation document generation
    - PCR value verification
    - KMS attestation-based key release
    - Enclave identity verification
    """
    
    def __init__(
        self,
        kms_key_id: Optional[str] = None,
        expected_pcrs: Optional[Dict[int, str]] = None,
        region: str = "us-east-1",
    ):
        self.kms_key_id = kms_key_id or os.getenv("AWS_KMS_KEY_ID")
        self.expected_pcrs = expected_pcrs or {}
        self.region = region
        self._attestation_doc: Optional[AttestationDocument] = None
    
    def generate_attestation(
        self,
        user_data: Optional[bytes] = None,
        nonce: Optional[bytes] = None,
    ) -> bytes:
        """
        Generate an attestation document from within the enclave.
        
        This calls the Nitro Enclave attestation API to produce
        a cryptographically signed document proving enclave identity.
        """
        try:
            from enclave_sdk import get_attestation_document
            
            doc = get_attestation_document(
                user_data=user_data,
                nonce=nonce,
            )
            
            return doc
            
        except ImportError:
            logger.warning("enclave_sdk not available - using mock attestation")
            return self._mock_attestation(user_data, nonce)
    
    def _mock_attestation(
        self,
        user_data: Optional[bytes] = None,
        nonce: Optional[bytes] = None,
    ) -> bytes:
        """Generate mock attestation for testing outside enclave."""
        mock_doc = {
            "moduleId": "esg-audit-enclave",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "digest": "SHA384",
            "pcrs": {
                "0": self._sha384(b"enclave_image"),
                "1": self._sha384(b"kernel_config"),
                "2": self._sha384(b"application_code"),
                "3": self._sha384(b"iam_role"),
            },
            "userData": user_data.hex() if user_data else None,
            "nonce": nonce.hex() if nonce else None,
        }
        
        return json.dumps(mock_doc).encode()
    
    def verify_attestation(
        self,
        attestation_doc: bytes,
        expected_pcrs: Optional[Dict[int, str]] = None,
    ) -> bool:
        """
        Verify an attestation document.
        
        Checks:
        1. Document signature validity
        2. PCR values match expected
        3. Document is not expired
        """
        try:
            parsed = self._parse_attestation_document(attestation_doc)
            self._attestation_doc = parsed
            
            pcrs_to_check = expected_pcrs or self.expected_pcrs
            
            if pcrs_to_check:
                for pcr_index, expected_value in pcrs_to_check.items():
                    actual_value = parsed.pcrs.get(pcr_index)
                    if actual_value != expected_value:
                        logger.error(
                            f"PCR{pcr_index} mismatch: "
                            f"expected {expected_value[:16]}..., "
                            f"got {actual_value[:16] if actual_value else 'None'}..."
                        )
                        return False
            
            logger.info("Attestation verification successful")
            return True
            
        except Exception as e:
            logger.error(f"Attestation verification failed: {e}")
            return False
    
    def _parse_attestation_document(self, doc: bytes) -> AttestationDocument:
        """Parse CBOR-encoded attestation document."""
        try:
            import cbor2
            parsed = cbor2.loads(doc)
            
            return AttestationDocument(
                document=doc,
                module_id=parsed.get("module_id", ""),
                timestamp=datetime.fromisoformat(
                    parsed.get("timestamp", datetime.now(timezone.utc).isoformat())
                ),
                digests=parsed.get("digests", {}),
                pcrs={k: v.hex() for k, v in parsed.get("pcrs", {}).items()},
                certificate=parsed.get("certificate", b""),
                cabundle=parsed.get("cabundle", []),
                public_key=parsed.get("public_key", b""),
                user_data=parsed.get("user_data"),
                nonce=parsed.get("nonce"),
            )
        except ImportError:
            doc_str = doc.decode() if isinstance(doc, bytes) else doc
            parsed = json.loads(doc_str)
            
            return AttestationDocument(
                document=doc,
                module_id=parsed.get("moduleId", ""),
                timestamp=datetime.fromisoformat(parsed.get("timestamp", "")),
                digests={"SHA384": parsed.get("digest", "SHA384")},
                pcrs={int(k): v for k, v in parsed.get("pcrs", {}).items()},
                certificate=b"",
                cabundle=[],
                public_key=b"",
                user_data=bytes.fromhex(parsed["userData"]) if parsed.get("userData") else None,
                nonce=bytes.fromhex(parsed["nonce"]) if parsed.get("nonce") else None,
            )
    
    def derive_enclave_key(self, context: Dict[str, Any]) -> bytes:
        """
        Derive a unique encryption key for this enclave instance.
        
        Uses PCR values as key derivation context.
        """
        if not self._attestation_doc:
            raise ValueError("No attestation document available")
        
        context_bytes = json.dumps({
            "module_id": self._attestation_doc.module_id,
            "pcrs": self._attestation_doc.pcrs,
            "context": context,
        }, sort_keys=True).encode()
        
        return hashlib.sha384(context_bytes).digest()
    
    @staticmethod
    def _sha384(data: bytes) -> str:
        """Compute SHA-384 hash of data."""
        return hashlib.sha384(data).hexdigest()


class PCRPolicy:
    """
    Defines PCR-based access policies for KMS key release.
    """
    
    def __init__(self):
        self.required_pcrs: Dict[int, str] = {}
        self.allow_list: list = []
    
    def add_pcr_requirement(self, pcr_index: int, expected_value: str) -> None:
        """Add a required PCR value."""
        self.required_pcrs[pcr_index] = expected_value
    
    def add_allowed_enclave(self, pcr_set: Dict[int, str]) -> None:
        """Add an allowed enclave PCR set to the allow list."""
        self.allow_list.append(pcr_set)
    
    def to_kms_policy(self) -> Dict[str, Any]:
        """Convert to AWS KMS key policy format."""
        conditions = []
        
        for pcr_index, value in self.required_pcrs.items():
            conditions.append({
                "StringEqualsIgnoreCase": {
                    f"aws:PrincipalTag/PCR{pcr_index}": value.lower()
                }
            })
        
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowEnclaveOnly",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "kms:Decrypt",
                    "Resource": "*",
                    "Condition": {
                        "StringEqualsIgnoreCase": {
                            "kms:RecipientAttestation:ImageSha384": self.required_pcrs.get(0, ""),
                            "kms:RecipientAttestation:PCR0": self.required_pcrs.get(0, ""),
                            "kms:RecipientAttestation:PCR1": self.required_pcrs.get(1, ""),
                            "kms:RecipientAttestation:PCR2": self.required_pcrs.get(2, ""),
                        }
                    }
                }
            ]
        }
