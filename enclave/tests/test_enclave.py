"""
Tests for Enclave Components
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from enclave.attestation import AttestationService, AttestationDocument, PCRPolicy
from enclave.communication import VSocketServer, VSocketClient, EnclaveMessage, MessageType
from enclave.crypto import EnclaveCrypto, EncryptedPayload


class TestAttestationService:
    """Tests for attestation service."""
    
    def test_mock_attestation_generation(self):
        service = AttestationService()
        
        doc = service.generate_attestation(
            user_data=b"test_data",
            nonce=b"test_nonce",
        )
        
        parsed = json.loads(doc)
        assert "moduleId" in parsed
        assert "timestamp" in parsed
        assert "pcrs" in parsed
    
    def test_attestation_verification_success(self):
        service = AttestationService()
        
        doc = service.generate_attestation()
        
        result = service.verify_attestation(doc)
        assert result is True
    
    def test_attestation_verification_with_expected_pcrs(self):
        service = AttestationService()
        
        doc = service.generate_attestation()
        parsed = service._parse_attestation_document(doc)
        
        service.expected_pcrs = {0: parsed.pcrs[0]}
        
        result = service.verify_attestation(doc)
        assert result is True
    
    def test_attestation_verification_pcr_mismatch(self):
        service = AttestationService()
        
        doc = service.generate_attestation()
        service.expected_pcrs = {0: "invalid_pcr_value"}
        
        result = service.verify_attestation(doc)
        assert result is False


class TestPCRPolicy:
    """Tests for PCR policy."""
    
    def test_pcr_policy_creation(self):
        policy = PCRPolicy()
        policy.add_pcr_requirement(0, "expected_pcr0_value")
        policy.add_pcr_requirement(1, "expected_pcr1_value")
        
        assert policy.required_pcrs[0] == "expected_pcr0_value"
        assert policy.required_pcrs[1] == "expected_pcr1_value"
    
    def test_kms_policy_generation(self):
        policy = PCRPolicy()
        policy.add_pcr_requirement(0, "abc123")
        policy.add_pcr_requirement(2, "def456")
        
        kms_policy = policy.to_kms_policy()
        
        assert kms_policy["Version"] == "2012-10-17"
        assert len(kms_policy["Statement"]) == 1
        assert "Condition" in kms_policy["Statement"][0]


class TestEnclaveMessage:
    """Tests for enclave message structure."""
    
    def test_message_serialization(self):
        message = EnclaveMessage(
            type=MessageType.REQUEST,
            request_id="test-123",
            payload={"key": "value"},
            timestamp="2024-01-01T00:00:00Z",
        )
        
        json_str = message.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["type"] == "REQUEST"
        assert parsed["request_id"] == "test-123"
        assert parsed["payload"]["key"] == "value"
    
    def test_message_deserialization(self):
        json_str = json.dumps({
            "type": "RESPONSE",
            "request_id": "test-456",
            "payload": {"result": "success"},
            "timestamp": "2024-01-01T00:00:00Z",
            "signature": None,
        })
        
        message = EnclaveMessage.from_json(json_str)
        
        assert message.type == MessageType.RESPONSE
        assert message.request_id == "test-456"
        assert message.payload["result"] == "success"


class TestEnclaveCrypto:
    """Tests for enclave cryptography."""
    
    def test_key_generation(self):
        key = EnclaveCrypto.generate_key()
        assert len(key) == 32
    
    def test_encryption_decryption(self):
        crypto = EnclaveCrypto()
        key = EnclaveCrypto.generate_key()
        crypto.set_key(key)
        
        plaintext = b"This is sensitive ESG data"
        
        encrypted = crypto.encrypt(plaintext)
        
        assert encrypted.ciphertext != plaintext
        assert len(encrypted.iv) == 12
        assert len(encrypted.tag) == 16
        
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == plaintext
    
    def test_dict_encryption(self):
        crypto = EnclaveCrypto()
        key = EnclaveCrypto.generate_key()
        crypto.set_key(key)
        
        data = {
            "document_id": "doc-123",
            "compliance_score": 0.85,
            "findings": ["ESRS E1", "SEC-GHG"],
        }
        
        encrypted_json = crypto.encrypt_dict(data)
        
        decrypted = crypto.decrypt_dict(encrypted_json)
        
        assert decrypted["document_id"] == "doc-123"
        assert decrypted["compliance_score"] == 0.85
        assert len(decrypted["findings"]) == 2
    
    def test_key_derivation(self):
        salt = b"random_salt_value"
        
        key1 = EnclaveCrypto.derive_key("password123", salt)
        key2 = EnclaveCrypto.derive_key("password123", salt)
        
        assert key1 == key2
        assert len(key1) == 32
        
        key3 = EnclaveCrypto.derive_key("different_password", salt)
        assert key1 != key3


class TestVSocketServer:
    """Tests for vsocket server."""
    
    def test_handler_registration(self):
        server = VSocketServer(port=5005)
        
        def test_handler(payload):
            return {"result": "ok"}
        
        server.register_handler("TEST", test_handler)
        
        assert "TEST" in server._handlers
        assert server._handlers["TEST"] == test_handler


class TestVSocketClient:
    """Tests for vsocket client."""
    
    def test_client_creation(self):
        client = VSocketClient(
            enclave_cid=3,
            port=5005,
            timeout=10.0,
        )
        
        assert client.enclave_cid == 3
        assert client.port == 5005
        assert client.timeout == 10.0
