
import pytest
from unittest.mock import Mock, patch, MagicMock
from services.verification.c2pa_validator import C2PAValidator, ValidationStatus
from services.verification.models import ProvenanceReport
import json

class TestC2PAValidator:

    @pytest.fixture
    def validator(self):
        return C2PAValidator()

    @pytest.fixture
    def mock_c2pa_reader(self):
        with patch("c2pa.Reader") as mock_reader:
            yield mock_reader

    def test_valid_signed_document(self, validator, mock_c2pa_reader):
        # Setup mock for a valid signed document
        mock_instance = mock_c2pa_reader.from_file.return_value
        
        # Mock manifest store data
        manifest_store = {
            "active_manifest": "urn:uuid:1234",
            "manifests": {
                "urn:uuid:1234": {
                    "claim": {
                        "claim_generator": "Adobe Photoshop",
                        "claim_generator_info": {"time": "2023-01-01T12:00:00Z"}
                    },
                    "signature_info": {"issuer": "Adobe"},
                    "validation_status": "VALID",
                    "assertions": [
                        {"label": "c2pa.actions", "data": {"actions": [{"action": "c2pa.created"}]}}
                    ],
                    "ingredients": []
                }
            }
        }
        mock_instance.json.return_value = manifest_store

        report = validator.validate_provenance(b"fake_pdf_bytes")

        assert report.status == ValidationStatus.VERIFIED
        assert report.trust_score == 1.0
        assert report.issuer == "Adobe"
        assert report.software_agent == "Adobe Photoshop"

    def test_unsigned_document(self, validator, mock_c2pa_reader):
        # Setup mock to raise C2paError
        import c2pa
        # We need to act as if c2pa.C2paError is raised.
        # Since we mock c2pa.Reader, the side_effect should be an instance of C2paError.
        # However, C2paError might need args. Let's assume string message.
        mock_c2pa_reader.from_file.side_effect = c2pa.C2paError("Manifest not found")

        report = validator.validate_provenance(b"unsigned_bytes")

        assert report.status == ValidationStatus.UNSIGNED
        assert report.trust_score == 0.0
        assert "No C2PA manifest found" in report.errors[0]

    def test_ai_generated_content(self, validator, mock_c2pa_reader):
        # Setup mock for AI generated content
        mock_instance = mock_c2pa_reader.from_file.return_value
        
        manifest_store = {
            "active_manifest": "urn:uuid:ai-content",
            "manifests": {
                "urn:uuid:ai-content": {
                    "claim": {"claim_generator": "Midjourney"},
                    "assertions": [
                        {
                            "label": "c2pa.actions", 
                            "data": {
                                "actions": [
                                    {
                                        "action": "c2pa.created",
                                        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }
        mock_instance.json.return_value = manifest_store

        report = validator.validate_provenance(b"ai_image_bytes")

        assert report.status == ValidationStatus.SYNTHETIC_AI
        # Trust score logic might be 0.5 or 0.0 depending on strictness, we set 0.5 in code
        assert report.trust_score == 0.5 

    def test_missing_active_manifest(self, validator, mock_c2pa_reader):
        mock_instance = mock_c2pa_reader.from_file.return_value
        mock_instance.json.return_value = {"manifests": {}}

        report = validator.validate_provenance(b"broken_manifest_bytes")

        assert report.status == ValidationStatus.UNSIGNED # Or TAMPERED, logic currently maps to UNSIGNED/TAMPERED based on error
        assert "No active manifest" in report.errors[0]
