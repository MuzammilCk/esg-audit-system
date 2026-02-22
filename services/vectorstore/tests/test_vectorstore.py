"""
Tests for Vector Store Components
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio

from services.vectorstore.embeddings import (
    EmbeddingService,
    EmbeddingResult,
    OpenAIEmbeddingProvider,
    LocalEmbeddingProvider,
)
from services.vectorstore.indexer import (
    DocumentIndexer,
    TextChunker,
    ChunkMetadata,
    IndexingResult,
)


class TestEmbeddingService:
    """Tests for the embedding service."""
    
    @pytest.fixture
    def mock_openai_provider(self):
        provider = Mock(spec=OpenAIEmbeddingProvider)
        provider.model_name = "text-embedding-3-small"
        provider.dimensions = 1536
        provider.embed_documents = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536, [0.2] * 1536],
            model="text-embedding-3-small",
            dimensions=1536,
            tokens_used=100,
        ))
        provider.embed_query = AsyncMock(return_value=[0.1] * 1536)
        return provider
    
    @pytest.mark.asyncio
    async def test_embed_documents_batching(self, mock_openai_provider):
        service = EmbeddingService(provider="openai")
        service._provider = mock_openai_provider
        service.batch_size = 2
        
        texts = ["text1", "text2", "text3", "text4", "text5"]
        result = await service.embed_documents(texts)
        
        assert mock_openai_provider.embed_documents.call_count == 3
    
    @pytest.mark.asyncio
    async def test_embed_query(self, mock_openai_provider):
        service = EmbeddingService(provider="openai")
        service._provider = mock_openai_provider
        
        embedding = await service.embed_query("test query")
        
        assert len(embedding) == 1536
        mock_openai_provider.embed_query.assert_called_once()


class TestTextChunker:
    """Tests for the text chunker."""
    
    @pytest.fixture
    def chunker(self):
        return TextChunker(
            chunk_size=200,
            chunk_overlap=50,
            respect_sentence_boundary=True,
        )
    
    def test_chunk_empty_text(self, chunker):
        chunks = chunker.chunk_text("", {})
        assert chunks == []
    
    def test_chunk_short_text(self, chunker):
        text = "This is a short text that fits in one chunk."
        chunks = chunker.chunk_text(text, {"document_id": "doc1"})
        
        assert len(chunks) == 1
        assert chunks[0].content == text
    
    def test_chunk_long_text(self, chunker):
        text = ". ".join([f"Sentence {i} with some content" for i in range(20)])
        chunks = chunker.chunk_text(text, {"document_id": "doc1"})
        
        assert len(chunks) > 1
        
        for i, chunk in enumerate(chunks):
            assert chunk.metadata["chunk_index"] == i
    
    def test_extract_regulation_codes(self, chunker):
        text = """
        This document covers ESRS E1 climate change requirements.
        It also references ESRS S1 workforce disclosures.
        Scope 1 and Scope 2 emissions are reported.
        SEC-GHG compliance is addressed.
        """
        
        codes = chunker._extract_regulation_codes(text)
        
        assert "ESRS E1" in codes
        assert "ESRS S1" in codes
        assert "Scope 1" in codes or "Scope 2" in codes
    
    def test_extract_keywords(self, chunker):
        text = """
        Our company is committed to net zero targets.
        We report on GHG emissions and sustainability metrics.
        Climate change is a key focus area.
        """
        
        keywords = chunker._extract_keywords(text)
        
        assert "net zero" in keywords
        assert "ghg emissions" in keywords
        assert "sustainability" in keywords


class TestDocumentIndexer:
    """Tests for the document indexer."""
    
    @pytest.fixture
    def mock_vector_store(self):
        store = Mock()
        store.initialize = AsyncMock()
        store.upsert_documents = AsyncMock(return_value=5)
        store.delete_document = AsyncMock(return_value=True)
        return store
    
    @pytest.mark.asyncio
    async def test_index_document(self, mock_vector_store):
        indexer = DocumentIndexer(vector_store=mock_vector_store)
        
        content = "This is a test document. " * 50
        metadata = {
            "document_id": "doc-123",
            "source_url": "https://example.com/doc.pdf",
            "original_filename": "report.pdf",
        }
        
        result = await indexer.index_document(content, metadata)
        
        assert result.document_id == "doc-123"
        assert result.chunks_indexed == 5
        mock_vector_store.upsert_documents.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_index_empty_document(self, mock_vector_store):
        indexer = DocumentIndexer(vector_store=mock_vector_store)
        
        result = await indexer.index_document("", {"document_id": "empty"})
        
        assert result.chunks_indexed == 0
        assert "No content to index" in result.errors


class TestChunkMetadata:
    """Tests for chunk metadata model."""
    
    def test_metadata_creation(self):
        metadata = ChunkMetadata(
            document_id="doc-1",
            chunk_index=0,
            total_chunks=5,
            source_url="https://example.com/doc.pdf",
            original_filename="report.pdf",
            mime_type="application/pdf",
            supplier_id="SUPP-001",
            region="EU",
            regulation_codes=["ESRS E1"],
            keywords=["ghg emissions"],
        )
        
        assert metadata.document_id == "doc-1"
        assert metadata.chunk_index == 0
        assert len(metadata.regulation_codes) == 1
