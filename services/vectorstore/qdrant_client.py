"""
Qdrant Vector Store Client

Manages Qdrant collections, indexing, and hybrid search.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4, UUID

from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
    SparseVectorParams,
    SparseIndexParams,
    Modifier,
    HnswConfigDiff,
)
from qdrant_client.http.models import SparseVector

from services.vectorstore.embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)

COLLECTION_NAME = "esg_documents"
SPARSE_COLLECTION_NAME = "esg_documents_sparse"


@dataclass
class DocumentChunk:
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    sparse_embedding: Optional[Dict[int, float]] = None


@dataclass
class SearchResult:
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]


@dataclass
class HybridSearchResult:
    id: str
    content: str
    dense_score: float
    sparse_score: float
    hybrid_score: float
    metadata: Dict[str, Any]


class QdrantVectorStore:
    """
    Qdrant vector database client with hybrid search capabilities.
    
    Features:
    - Dense vector search (semantic similarity)
    - Sparse vector search (BM25-style keyword matching)
    - Hybrid search (combining dense + sparse)
    - Metadata filtering
    - Multi-tenant support via payload filtering
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        grpc_port: int = 6334,
        api_key: Optional[str] = None,
        prefer_grpc: bool = False,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self.host = host
        self.port = port
        self.grpc_port = grpc_port
        self.api_key = api_key
        self.prefer_grpc = prefer_grpc
        
        self._client: Optional[AsyncQdrantClient] = None
        self._embedding_service = embedding_service
    
    @property
    def embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service
    
    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=self.host,
                port=self.port,
                grpc_port=self.grpc_port,
                api_key=self.api_key,
                prefer_grpc=self.prefer_grpc,
            )
        return self._client
    
    async def initialize(self) -> None:
        """Initialize collections if they don't exist."""
        client = await self._get_client()
        
        dimensions = self.embedding_service.dimensions
        
        try:
            await client.get_collection(COLLECTION_NAME)
            logger.info(f"Collection {COLLECTION_NAME} already exists")
        except Exception:
            await client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=dimensions,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(
                        m=16,
                        ef_construct=100,
                    ),
                ),
                sparse_vectors_config={
                    "text": SparseVectorParams(
                        index=SparseIndexParams(
                            on_disk=False,
                        )
                    )
                },
            )
            logger.info(f"Created collection {COLLECTION_NAME}")
    
    async def upsert_documents(
        self,
        chunks: List[DocumentChunk],
        batch_size: int = 100,
    ) -> int:
        """
        Index document chunks with dense and sparse vectors.
        
        Returns the number of points indexed.
        """
        client = await self._get_client()
        
        contents = [chunk.content for chunk in chunks]
        embedding_result = await self.embedding_service.embed_documents(contents)
        
        sparse_vectors = self._compute_sparse_vectors(contents)
        
        points = []
        for i, chunk in enumerate(chunks):
            point = PointStruct(
                id=chunk.id,
                vector={
                    "": embedding_result.embeddings[i],
                    "text": SparseVector(
                        indices=list(sparse_vectors[i].keys()),
                        values=list(sparse_vectors[i].values()),
                    ),
                },
                payload={
                    "content": chunk.content,
                    "metadata": chunk.metadata,
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                    "embedding_model": embedding_result.model,
                },
            )
            points.append(point)
        
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch,
            )
        
        logger.info(f"Indexed {len(points)} document chunks")
        return len(points)
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Perform dense vector search (semantic similarity).
        """
        client = await self._get_client()
        
        query_embedding = await self.embedding_service.embed_query(query)
        
        filter_obj = None
        if filters:
            filter_obj = self._build_filter(filters)
        
        results = await client.search(
            collection_name=COLLECTION_NAME,
            query_vector=("", query_embedding),
            limit=limit,
            score_threshold=score_threshold,
            query_filter=filter_obj,
        )
        
        return [
            SearchResult(
                id=str(result.id),
                content=result.payload.get("content", ""),
                score=result.score,
                metadata=result.payload.get("metadata", {}),
            )
            for result in results
        ]
    
    async def search_sparse(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """
        Perform sparse vector search (BM25-style keyword matching).
        """
        client = await self._get_client()
        
        query_sparse = self._compute_sparse_vectors([query])[0]
        
        filter_obj = None
        if filters:
            filter_obj = self._build_filter(filters)
        
        results = await client.search(
            collection_name=COLLECTION_NAME,
            query_vector=SparseVector(
                indices=list(query_sparse.keys()),
                values=list(query_sparse.values()),
            ),
            using="text",
            limit=limit,
            query_filter=filter_obj,
        )
        
        return [
            SearchResult(
                id=str(result.id),
                content=result.payload.get("content", ""),
                score=result.score,
                metadata=result.payload.get("metadata", {}),
            )
            for result in results
        ]
    
    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[HybridSearchResult]:
        """
        Perform hybrid search combining dense and sparse vectors.
        
        Uses reciprocal rank fusion (RRF) for score combination.
        """
        dense_results = await self.search(query, limit=limit * 2, filters=filters)
        sparse_results = await self.search_sparse(query, limit=limit * 2, filters=filters)
        
        dense_scores = {r.id: r for r in dense_results}
        sparse_scores = {r.id: r for r in sparse_results}
        
        all_ids = set(dense_scores.keys()) | set(sparse_scores.keys())
        
        k = 60
        combined_results = []
        
        for doc_id in all_ids:
            dense_rank = float('inf')
            sparse_rank = float('inf')
            
            if doc_id in dense_scores:
                dense_rank = next(
                    i for i, r in enumerate(dense_results) if r.id == doc_id
                )
            
            if doc_id in sparse_scores:
                sparse_rank = next(
                    i for i, r in enumerate(sparse_results) if r.id == doc_id
                )
            
            rrf_score = (
                1.0 / (k + dense_rank) * dense_weight +
                1.0 / (k + sparse_rank) * sparse_weight
            )
            
            doc = dense_scores.get(doc_id) or sparse_scores.get(doc_id)
            if doc:
                combined_results.append(HybridSearchResult(
                    id=doc_id,
                    content=doc.content,
                    dense_score=1.0 / (k + dense_rank) if dense_rank != float('inf') else 0,
                    sparse_score=1.0 / (k + sparse_rank) if sparse_rank != float('inf') else 0,
                    hybrid_score=rrf_score,
                    metadata=doc.metadata,
                ))
        
        combined_results.sort(key=lambda x: x.hybrid_score, reverse=True)
        
        return combined_results[:limit]
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete all chunks belonging to a document."""
        client = await self._get_client()
        
        try:
            await client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.document_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                ),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection."""
        client = await self._get_client()
        
        info = await client.get_collection(COLLECTION_NAME)
        
        return {
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "segments_count": info.segments_count,
            "status": info.status.value,
        }
    
    def _build_filter(self, filters: Dict[str, Any]) -> Filter:
        """Build Qdrant filter from dictionary."""
        conditions = []
        
        for key, value in filters.items():
            if isinstance(value, dict):
                if "$in" in value:
                    for v in value["$in"]:
                        conditions.append(
                            FieldCondition(
                                key=f"metadata.{key}",
                                match=MatchValue(value=v),
                            )
                        )
                elif "$gte" in value:
                    pass
            else:
                conditions.append(
                    FieldCondition(
                        key=f"metadata.{key}",
                        match=MatchValue(value=value),
                    )
                )
        
        return Filter(must=conditions) if conditions else None
    
    def _compute_sparse_vectors(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Compute sparse vectors (BM25-style) for texts.
        
        Simple tokenization with TF-IDF-like scoring.
        """
        import re
        from collections import Counter
        
        sparse_vectors = []
        
        for text in texts:
            tokens = re.findall(r'\b\w+\b', text.lower())
            token_counts = Counter(tokens)
            
            sparse = {}
            for token, count in token_counts.items():
                token_id = hash(token) % (2 ** 31)
                sparse[token_id] = count / len(tokens) if tokens else 0
            
            sparse_vectors.append(sparse)
        
        return sparse_vectors
    
    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None


_vector_store: QdrantVectorStore | None = None


def get_vector_store(
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> QdrantVectorStore:
    """Get or create the global vector store instance."""
    global _vector_store
    
    if _vector_store is None:
        _vector_store = QdrantVectorStore(
            host=host or os.getenv("QDRANT_HOST", "localhost"),
            port=port or int(os.getenv("QDRANT_PORT", "6333")),
            api_key=os.getenv("QDRANT_API_KEY"),
        )
    
    return _vector_store
