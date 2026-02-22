"""
Document Indexer

Indexes ESG documents into Qdrant with metadata enrichment.
Handles chunking, metadata extraction, and batch processing.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from services.vectorstore.qdrant_client import QdrantVectorStore, get_vector_store, DocumentChunk

logger = logging.getLogger(__name__)


@dataclass
class IndexingResult:
    document_id: str
    chunks_indexed: int
    total_tokens: int
    errors: List[str] = field(default_factory=list)


@dataclass
class ChunkMetadata:
    document_id: str
    chunk_index: int
    total_chunks: int
    source_url: str
    original_filename: str
    mime_type: str
    supplier_id: Optional[str] = None
    region: Optional[str] = None
    reporting_period: Optional[str] = None
    regulation_codes: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TextChunker:
    """
    Splits documents into semantically meaningful chunks.
    
    Strategies:
    - Fixed-size with overlap
    - Sentence-boundary aware
    - Paragraph-based
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        respect_sentence_boundary: bool = True,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.respect_sentence_boundary = respect_sentence_boundary
    
    def chunk_text(self, text: str, metadata: Dict[str, Any]) -> List[DocumentChunk]:
        """Split text into overlapping chunks."""
        if not text or not text.strip():
            return []
        
        chunks = []
        
        if self.respect_sentence_boundary:
            sentences = self._split_sentences(text)
            chunks = self._chunk_by_sentences(sentences, metadata)
        else:
            chunks = self._chunk_fixed_size(text, metadata)
        
        return chunks
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(sentence_pattern, text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _chunk_by_sentences(
        self,
        sentences: List[str],
        metadata: Dict[str, Any],
    ) -> List[DocumentChunk]:
        """Create chunks that respect sentence boundaries."""
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            
            if current_length + sentence_length > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append(self._create_chunk(chunk_text, len(chunks), metadata))
                
                overlap_sentences = self._get_overlap_sentences(current_chunk)
                current_chunk = overlap_sentences
                current_length = sum(len(s) for s in overlap_sentences)
            
            current_chunk.append(sentence)
            current_length += sentence_length
        
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(self._create_chunk(chunk_text, len(chunks), metadata))
        
        return chunks
    
    def _chunk_fixed_size(
        self,
        text: str,
        metadata: Dict[str, Any],
    ) -> List[DocumentChunk]:
        """Create fixed-size chunks with overlap."""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]
            
            if end < len(text):
                last_space = chunk_text.rfind(' ')
                if last_space > self.chunk_size // 2:
                    chunk_text = chunk_text[:last_space]
                    end = start + last_space
            
            chunks.append(self._create_chunk(chunk_text.strip(), len(chunks), metadata))
            start = end - self.chunk_overlap
        
        return chunks
    
    def _get_overlap_sentences(self, sentences: List[str]) -> List[str]:
        """Get sentences for overlap based on chunk_overlap size."""
        overlap_sentences = []
        overlap_length = 0
        
        for sentence in reversed(sentences):
            if overlap_length + len(sentence) > self.chunk_overlap:
                break
            overlap_sentences.insert(0, sentence)
            overlap_length += len(sentence)
        
        return overlap_sentences
    
    def _create_chunk(
        self,
        text: str,
        index: int,
        metadata: Dict[str, Any],
    ) -> DocumentChunk:
        """Create a DocumentChunk with enriched metadata."""
        document_id = metadata.get("document_id", str(uuid4()))
        
        chunk_metadata = ChunkMetadata(
            document_id=document_id,
            chunk_index=index,
            total_chunks=0,
            source_url=metadata.get("source_url", ""),
            original_filename=metadata.get("original_filename", ""),
            mime_type=metadata.get("mime_type", "text/plain"),
            supplier_id=metadata.get("supplier_id"),
            region=metadata.get("region"),
            reporting_period=metadata.get("reporting_period"),
            regulation_codes=self._extract_regulation_codes(text),
            keywords=self._extract_keywords(text),
        )
        
        return DocumentChunk(
            id=f"{document_id}_chunk_{index}",
            content=text,
            metadata={
                "document_id": document_id,
                "chunk_index": index,
                "source_url": metadata.get("source_url", ""),
                "original_filename": metadata.get("original_filename", ""),
                "mime_type": metadata.get("mime_type", "text/plain"),
                "supplier_id": metadata.get("supplier_id"),
                "region": metadata.get("region"),
                "reporting_period": metadata.get("reporting_period"),
                "regulation_codes": chunk_metadata.regulation_codes,
                "keywords": chunk_metadata.keywords,
            },
        )
    
    def _extract_regulation_codes(self, text: str) -> List[str]:
        """Extract regulation codes from text."""
        codes = []
        
        esrs_pattern = r'ESRS\s+[ESG]\d+'
        codes.extend(re.findall(esrs_pattern, text, re.IGNORECASE))
        
        sec_pattern = r'SEC[-\s]*(?:GHG|CLIMATE|GOVERNANCE|TARGETS)'
        codes.extend(re.findall(sec_pattern, text, re.IGNORECASE))
        
        scope_pattern = r'Scope\s+[123]'
        codes.extend(re.findall(scope_pattern, text, re.IGNORECASE))
        
        return list(set(codes))
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract relevant ESG keywords from text."""
        keywords = []
        
        esg_terms = [
            "ghg emissions", "carbon footprint", "net zero", "sustainability",
            "climate change", "renewable energy", "biodiversity", "circular economy",
            "esg", "climate risk", "transition plan", "scope 1", "scope 2", "scope 3",
            "decarbonization", "greenhouse gas", "carbon neutral", "science-based target",
        ]
        
        text_lower = text.lower()
        for term in esg_terms:
            if term in text_lower:
                keywords.append(term)
        
        return keywords[:10]


class DocumentIndexer:
    """
    Main indexer that orchestrates document indexing into Qdrant.
    
    Features:
    - Intelligent chunking with overlap
    - Metadata enrichment
    - Regulation code extraction
    - Keyword extraction
    - Batch processing
    """
    
    def __init__(
        self,
        vector_store: Optional[QdrantVectorStore] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        self._vector_store = vector_store
        self._chunker = TextChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    
    @property
    def vector_store(self) -> QdrantVectorStore:
        if self._vector_store is None:
            self._vector_store = get_vector_store()
        return self._vector_store
    
    async def initialize(self) -> None:
        """Initialize the vector store collection."""
        await self.vector_store.initialize()
    
    async def index_document(
        self,
        content: str,
        metadata: Dict[str, Any],
    ) -> IndexingResult:
        """
        Index a single document into the vector store.
        
        Args:
            content: The document text content
            metadata: Document metadata (document_id, source_url, etc.)
        
        Returns:
            IndexingResult with stats and any errors
        """
        errors = []
        document_id = metadata.get("document_id", str(uuid4()))
        
        try:
            chunks = self._chunker.chunk_text(content, metadata)
            
            if not chunks:
                return IndexingResult(
                    document_id=document_id,
                    chunks_indexed=0,
                    total_tokens=0,
                    errors=["No content to index"],
                )
            
            for i, chunk in enumerate(chunks):
                chunk.metadata["total_chunks"] = len(chunks)
            
            points_indexed = await self.vector_store.upsert_documents(chunks)
            
            logger.info(f"Indexed {points_indexed} chunks for document {document_id}")
            
            return IndexingResult(
                document_id=document_id,
                chunks_indexed=points_indexed,
                total_tokens=len(content.split()),
                errors=errors,
            )
            
        except Exception as e:
            logger.exception(f"Failed to index document {document_id}")
            errors.append(str(e))
            return IndexingResult(
                document_id=document_id,
                chunks_indexed=0,
                total_tokens=0,
                errors=errors,
            )
    
    async def index_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[IndexingResult]:
        """
        Index multiple documents in batch.
        
        Args:
            documents: List of dicts with 'content' and 'metadata' keys
        
        Returns:
            List of IndexingResults
        """
        results = []
        
        for doc in documents:
            result = await self.index_document(
                content=doc.get("content", ""),
                metadata=doc.get("metadata", {}),
            )
            results.append(result)
        
        return results
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and all its chunks from the index."""
        return await self.vector_store.delete_document(document_id)


_indexer: DocumentIndexer | None = None


def get_document_indexer() -> DocumentIndexer:
    """Get or create the global document indexer instance."""
    global _indexer
    
    if _indexer is None:
        _indexer = DocumentIndexer()
    
    return _indexer
