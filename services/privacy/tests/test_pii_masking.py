
import pytest
from unittest.mock import Mock, patch, MagicMock
from services.privacy.presidio_masker import PIIMasker
from services.privacy.redis_manager import RedisManager

class TestPIIMasking:
    
    @pytest.fixture
    def mock_redis_manager(self):
        manager = Mock(spec=RedisManager)
        manager.store_mapping.return_value = True
        return manager

    @pytest.fixture
    def masker(self, mock_redis_manager):
        # Patch AnalyzerEngine to avoid loading spacy model in unit tests if possible 
        # or use a mock. Loading model takes time.
        with patch("services.privacy.presidio_masker.AnalyzerEngine") as mock_analyzer_cls, \
             patch("services.privacy.presidio_masker.AnonymizerEngine") as mock_anonymizer_cls:
             
            mock_analyzer = mock_analyzer_cls.return_value
            mock_anonymizer = mock_anonymizer_cls.return_value
            
            # Setup default behavior
            masker = PIIMasker(mock_redis_manager)
            masker.analyzer = mock_analyzer 
            masker.anonymizer = mock_anonymizer
            
            yield masker, mock_analyzer

    def test_mask_text_with_pii(self, masker):
        masker_instance, mock_analyzer = masker
        
        # Mock analysis results
        # "Report by Jane Doe at Berlin facility"
        # Jane Doe: PERSON (10, 18)
        # Berlin: LOCATION (22, 28)
        
        from presidio_analyzer import RecognizerResult
        
        mock_results = [
            RecognizerResult("PERSON", 10, 18, 0.85),
            RecognizerResult("LOCATION", 22, 28, 0.85)
        ]
        mock_analyzer.analyze.return_value = mock_results
        
        text = "Report by Jane Doe at Berlin facility"
        doc_id = "test-doc-1"
        
        masked_text, success = masker_instance.mask_text(text, doc_id)
        
        assert success is True
        # Check expected format: placeholders should be present
        assert "<PERSON_1>" in masked_text
        assert "<LOCATION_1>" in masked_text
        assert "Jane Doe" not in masked_text
        assert "Berlin" not in masked_text
        
        # Verify mapping storage
        masker_instance.redis_manager.store_mapping.assert_called_once()
        call_args = masker_instance.redis_manager.store_mapping.call_args
        assert call_args[0][0] == doc_id
        mapping = call_args[0][1]
        assert mapping["<PERSON_1>"] == "Jane Doe"
        assert mapping["<LOCATION_1>"] == "Berlin"

    def test_mask_text_no_pii(self, masker):
        masker_instance, mock_analyzer = masker
        mock_analyzer.analyze.return_value = []
        
        text = "No PII here"
        masked_text, success = masker_instance.mask_text(text, "doc-2")
        
        assert masked_text == text
        assert success is True
        masker_instance.redis_manager.store_mapping.assert_not_called()

    def test_redis_encryption(self):
        from cryptography.fernet import Fernet
        
        # Integrated test logic for RedisManager (mocking redis client)
        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = mock_redis_cls.return_value
            
            # Mock enc/dec
            mock_redis.get.return_value = None # Assume empty first
            
            key = Fernet.generate_key()
            manager = RedisManager(encryption_key=key)
            
            mapping = {"<PERSON_1>": "John"}
            manager.store_mapping("doc-1", mapping)
            
            # Check if redis.set was called with bytes (encrypted)
            mock_redis.set.assert_called_once()
            args = mock_redis.set.call_args[0]
            assert args[0] == "pii:doc-1"
            assert isinstance(args[1], bytes)
            assert args[1] != b'{"<PERSON_1>": "John"}' # Should be encrypted
