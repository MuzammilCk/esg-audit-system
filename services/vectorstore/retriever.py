"""
RAG Retriever

Retrieval-Augmented Generation component for ESG compliance analysis.
Provides context-aware retrieval for the Compliance Analysis Agent.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from services.vectorstore.qdrant_client import (
    QdrantVectorStore,
    get_vector_store,
    SearchResult,
    HybridSearchResult,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievedContext:
    query: str
    documents: List[Dict[str, Any]]
    total_score: float
    retrieval_method: str
    metadata_filters: Dict[str, Any]


@dataclass
class RegulatoryContext:
    regulation_code: str
    relevant_chunks: List[Dict[str, Any]]
    compliance_hints: List[str]
    related_requirements: List[str]


class RAGRetriever:
    """
    RAG retriever for ESG compliance analysis.
    
    Features:
    - Hybrid search (dense + sparse)
    - Metadata-filtered retrieval
    - Regulation-specific context
    - Cross-referencing with historical documents
    - Context ranking and deduplication
    """
    
    def __init__(
        self,
        vector_store: Optional[QdrantVectorStore] = None,
        default_limit: int = 10,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
    ):
        self._vector_store = vector_store
        self.default_limit = default_limit
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
    
    @property
    def vector_store(self) -> QdrantVectorStore:
        if self._vector_store is None:
            self._vector_store = get_vector_store()
        return self._vector_store
    
    async def retrieve(
        self,
        query: str,
        limit: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        method: str = "hybrid",
    ) -> RetrievedContext:
        """
        Retrieve relevant documents for a query.
        
        Args:
            query: The search query
            limit: Maximum number of results
            filters: Metadata filters (e.g., supplier_id, region)
            method: "dense", "sparse", or "hybrid"
        
        Returns:
            RetrievedContext with documents and metadata
        """
        limit = limit or self.default_limit
        
        try:
            if method == "hybrid":
                results = await self.vector_store.hybrid_search(
                    query=query,
                    limit=limit,
                    dense_weight=self.dense_weight,
                    sparse_weight=self.sparse_weight,
                    filters=filters,
                )
                documents = [
                    {
                        "id": r.id,
                        "content": r.content,
                        "score": r.hybrid_score,
                        "dense_score": r.dense_score,
                        "sparse_score": r.sparse_score,
                        "metadata": r.metadata,
                    }
                    for r in results
                ]
                total_score = sum(r.hybrid_score for r in results)
            elif method == "dense":
                results = await self.vector_store.search(
                    query=query,
                    limit=limit,
                    filters=filters,
                )
                documents = [
                    {
                        "id": r.id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata,
                    }
                    for r in results
                ]
                total_score = sum(r.score for r in results)
            else:
                results = await self.vector_store.search_sparse(
                    query=query,
                    limit=limit,
                    filters=filters,
                )
                documents = [
                    {
                        "id": r.id,
                        "content": r.content,
                        "score": r.score,
                        "metadata": r.metadata,
                    }
                    for r in results
                ]
                total_score = sum(r.score for r in results)
        except Exception as e:
            logger.warning(f"Vector store retrieval failed: {e}")
            documents = []
            total_score = 0.0
        
        return RetrievedContext(
            query=query,
            documents=documents,
            total_score=total_score,
            retrieval_method=method,
            metadata_filters=filters or {},
        )
    
    async def retrieve_for_regulation(
        self,
        regulation_code: str,
        supplier_id: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 5,
    ) -> RegulatoryContext:
        """
        Retrieve context specific to a regulation code.
        
        Args:
            regulation_code: E.g., "ESRS E1", "SEC-GHG"
            supplier_id: Filter by supplier
            region: Filter by region
            limit: Max results per query
        
        Returns:
            RegulatoryContext with relevant chunks and hints
        """
        filters = {}
        if supplier_id:
            filters["supplier_id"] = supplier_id
        if region:
            filters["region"] = region
        
        regulation_queries = self._build_regulation_queries(regulation_code)
        
        all_chunks = []
        seen_ids = set()
        
        for query in regulation_queries:
            context = await self.retrieve(
                query=query,
                limit=limit,
                filters=filters,
                method="hybrid",
            )
            
            for doc in context.documents:
                if doc["id"] not in seen_ids:
                    seen_ids.add(doc["id"])
                    all_chunks.append(doc)
        
        all_chunks.sort(key=lambda x: x["score"], reverse=True)
        all_chunks = all_chunks[:limit * 2]
        
        compliance_hints = self._extract_compliance_hints(all_chunks, regulation_code)
        related_requirements = self._get_related_requirements(regulation_code)
        
        return RegulatoryContext(
            regulation_code=regulation_code,
            relevant_chunks=all_chunks,
            compliance_hints=compliance_hints,
            related_requirements=related_requirements,
        )
    
    async def retrieve_similar_documents(
        self,
        document_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Find documents similar to a given document.
        
        Uses the document's chunks to find similar content.
        """
        filters = {"document_id": document_id}
        
        doc_chunks = await self.vector_store.search(
            query="",
            limit=3,
            filters=filters,
        )
        
        if not doc_chunks:
            return []
        
        combined_content = " ".join([c.content for c in doc_chunks])
        
        similar = await self.retrieve(
            query=combined_content[:1000],
            limit=limit + 1,
            method="hybrid",
        )
        
        return [
            doc for doc in similar.documents
            if doc["metadata"].get("document_id") != document_id
        ][:limit]
    
    async def retrieve_cross_reference(
        self,
        text: str,
        regulation_codes: List[str],
        limit: int = 5,
    ) -> Dict[str, RetrievedContext]:
        """
        Cross-reference text against multiple regulations.
        
        Returns a mapping of regulation_code -> relevant context.
        """
        results = {}
        
        for code in regulation_codes:
            query = f"{code} {text[:500]}"
            context = await self.retrieve(
                query=query,
                limit=limit,
                method="hybrid",
            )
            results[code] = context
        
        return results
    
    def _build_regulation_queries(self, regulation_code: str) -> List[str]:
        """Build search queries for a regulation code."""
        queries = []
        
        code_upper = regulation_code.upper()
        
        if "ESRS E1" in code_upper:
            queries = [
                "GHG emissions scope 1 scope 2 scope 3 carbon footprint",
                "climate transition plan net zero target",
                "energy consumption renewable energy mix",
                "climate risk physical transition",
            ]
        elif "ESRS E2" in code_upper:
            queries = [
                "pollution air water soil hazardous substances",
                "waste management effluents emissions",
            ]
        elif "ESRS E3" in code_upper:
            queries = [
                "water consumption withdrawal stress",
                "marine resources ocean ecosystem",
            ]
        elif "ESRS E4" in code_upper:
            queries = [
                "biodiversity ecosystem species habitat",
                "deforestation nature conservation",
            ]
        elif "ESRS E5" in code_upper:
            queries = [
                "circular economy recycling waste reduction",
                "resource efficiency material reuse",
            ]
        elif "ESRS S1" in code_upper:
            queries = [
                "workforce employees health safety",
                "diversity inclusion training compensation",
            ]
        elif "ESRS G1" in code_upper:
            queries = [
                "governance board ethics corruption",
                "business conduct compliance transparency",
            ]
        elif "SEC" in code_upper:
            queries = [
                f"{regulation_code} climate disclosure emissions",
                "SEC climate risk governance board oversight",
            ]
        else:
            queries = [regulation_code]
        
        return queries
    
    def _extract_compliance_hints(
        self,
        chunks: List[Dict[str, Any]],
        regulation_code: str,
    ) -> List[str]:
        """Extract compliance hints from retrieved chunks."""
        hints = []
        
        for chunk in chunks:
            content = chunk.get("content", "").lower()
            keywords = chunk.get("metadata", {}).get("keywords", [])
            
            if "disclosed" in content or "reported" in content:
                hints.append(f"Document contains disclosure language for {regulation_code}")
            
            if "target" in content or "goal" in content:
                hints.append(f"Document may contain targets relevant to {regulation_code}")
            
            for keyword in keywords[:3]:
                hints.append(f"Relevant keyword found: {keyword}")
        
        return list(set(hints))[:5]
    
    def _get_related_requirements(self, regulation_code: str) -> List[str]:
        """Get related regulation requirements for cross-referencing."""
        related = {
            "ESRS E1": ["ESRS E2", "ESRS E3", "SEC-GHG"],
            "ESRS E2": ["ESRS E1", "ESRS E5"],
            "ESRS E3": ["ESRS E1", "ESRS E4"],
            "ESRS E4": ["ESRS E3", "ESRS E5"],
            "ESRS E5": ["ESRS E2", "ESRS E4"],
            "ESRS S1": ["ESRS G1"],
            "ESRS G1": ["ESRS S1", "SEC-GOVERNANCE"],
            "SEC-GHG": ["ESRS E1", "SEC-CLIMATE-RISK"],
            "SEC-CLIMATE-RISK": ["SEC-GHG", "SEC-GOVERNANCE"],
            "SEC-GOVERNANCE": ["ESRS G1", "SEC-CLIMATE-RISK"],
            "SEC-TARGETS": ["SEC-GHG", "ESRS E1"],
        }
        
        return related.get(regulation_code, [])


_retriever: RAGRetriever | None = None


def get_rag_retriever() -> RAGRetriever:
    """Get or create the global RAG retriever instance."""
    global _retriever
    
    if _retriever is None:
        _retriever = RAGRetriever()
    
    return _retriever
