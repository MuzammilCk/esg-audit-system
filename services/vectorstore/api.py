"""
Vector Store API Service

FastAPI service for document indexing and RAG retrieval.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.vectorstore import (
    get_vector_store,
    get_document_indexer,
    get_rag_retriever,
    QdrantVectorStore,
    DocumentIndexer,
    RAGRetriever,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_vector_store: QdrantVectorStore | None = None
_indexer: DocumentIndexer | None = None
_retriever: RAGRetriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _vector_store, _indexer, _retriever
    
    _vector_store = get_vector_store()
    await _vector_store.initialize()
    
    _indexer = get_document_indexer(_vector_store)
    _retriever = get_rag_retriever(_vector_store)
    
    logger.info("Vector store initialized")
    yield
    
    await _vector_store.close()


app = FastAPI(
    title="ESG Vector Store",
    version="1.0.0",
    description="Qdrant-based vector store for ESG document retrieval",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IndexRequest(BaseModel):
    content: str = Field(..., description="Document content to index")
    document_id: str = Field(..., description="Unique document identifier")
    source_url: str = Field(default="", description="Source URL")
    original_filename: str = Field(default="", description="Original filename")
    mime_type: str = Field(default="text/plain", description="MIME type")
    supplier_id: Optional[str] = Field(default=None, description="Supplier ID")
    region: Optional[str] = Field(default=None, description="Geographic region")
    reporting_period: Optional[str] = Field(default=None, description="Reporting period")


class IndexResponse(BaseModel):
    document_id: str
    chunks_indexed: int
    total_tokens: int
    errors: List[str] = []


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    limit: int = Field(default=10, description="Maximum results")
    method: str = Field(default="hybrid", description="dense, sparse, or hybrid")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Metadata filters")
    dense_weight: float = Field(default=0.7, description="Dense vector weight for hybrid")
    sparse_weight: float = Field(default=0.3, description="Sparse vector weight for hybrid")


class SearchResult(BaseModel):
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_score: float
    retrieval_method: str


class RegulationContextRequest(BaseModel):
    regulation_code: str = Field(..., description="E.g., ESRS E1, SEC-GHG")
    supplier_id: Optional[str] = Field(default=None)
    region: Optional[str] = Field(default=None)
    limit: int = Field(default=5)


class RegulationContextResponse(BaseModel):
    regulation_code: str
    relevant_chunks: List[Dict[str, Any]]
    compliance_hints: List[str]
    related_requirements: List[str]


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok", "service": "vector-store"}


@app.get("/api/stats")
async def get_stats() -> Dict[str, Any]:
    """Get collection statistics."""
    if _vector_store is None:
        raise HTTPException(status_code=503, detail="Vector store not initialized")
    
    return await _vector_store.get_collection_stats()


@app.post("/api/index", response_model=IndexResponse)
async def index_document(request: IndexRequest):
    """
    Index a document into the vector store.
    
    The document will be:
    1. Split into overlapping chunks
    2. Enriched with metadata
    3. Embedded using the configured embedding model
    4. Indexed into Qdrant
    """
    if _indexer is None:
        raise HTTPException(status_code=503, detail="Indexer not initialized")
    
    metadata = {
        "document_id": request.document_id,
        "source_url": request.source_url,
        "original_filename": request.original_filename,
        "mime_type": request.mime_type,
        "supplier_id": request.supplier_id,
        "region": request.region,
        "reporting_period": request.reporting_period,
    }
    
    result = await _indexer.index_document(
        content=request.content,
        metadata=metadata,
    )
    
    return IndexResponse(
        document_id=result.document_id,
        chunks_indexed=result.chunks_indexed,
        total_tokens=result.total_tokens,
        errors=result.errors,
    )


@app.delete("/api/index/{document_id}")
async def delete_document(document_id: str) -> Dict[str, bool]:
    """Delete a document and all its chunks from the index."""
    if _indexer is None:
        raise HTTPException(status_code=503, detail="Indexer not initialized")
    
    success = await _indexer.delete_document(document_id)
    return {"success": success}


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Search the vector store.
    
    Methods:
    - dense: Semantic similarity search using embeddings
    - sparse: BM25-style keyword matching
    - hybrid: Combines dense and sparse using reciprocal rank fusion
    """
    if _retriever is None:
        raise HTTPException(status_code=503, detail="Retriever not initialized")
    
    context = await _retriever.retrieve(
        query=request.query,
        limit=request.limit,
        filters=request.filters,
        method=request.method,
    )
    
    results = [
        SearchResult(
            id=doc["id"],
            content=doc["content"],
            score=doc["score"],
            metadata=doc["metadata"],
        )
        for doc in context.documents
    ]
    
    return SearchResponse(
        query=context.query,
        results=results,
        total_score=context.total_score,
        retrieval_method=context.retrieval_method,
    )


@app.post("/api/regulation-context", response_model=RegulationContextResponse)
async def get_regulation_context(request: RegulationContextRequest):
    """
    Get context specific to a regulation code.
    
    Retrieves relevant documents and compliance hints
    for analyzing compliance with a specific regulation.
    """
    if _retriever is None:
        raise HTTPException(status_code=503, detail="Retriever not initialized")
    
    context = await _retriever.retrieve_for_regulation(
        regulation_code=request.regulation_code,
        supplier_id=request.supplier_id,
        region=request.region,
        limit=request.limit,
    )
    
    return RegulationContextResponse(
        regulation_code=context.regulation_code,
        relevant_chunks=context.relevant_chunks,
        compliance_hints=context.compliance_hints,
        related_requirements=context.related_requirements,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8004")))
