"""
Embedding Service

Generates vector embeddings for ESG documents.
Supports OpenAI embeddings and local sentence transformers.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    embeddings: List[List[float]]
    model: str
    dimensions: int
    tokens_used: int = 0


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def dimensions(self) -> int:
        pass
    
    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> EmbeddingResult:
        pass
    
    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings using text-embedding-3-small or text-embedding-3-large."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
    ):
        self._model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._dimensions = 1536 if "small" in model else 3072
        self._client = None
    
    @property
    def model_name(self) -> str:
        return self._model
    
    @property
    def dimensions(self) -> int:
        return self._dimensions
    
    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client
    
    async def embed_documents(self, texts: List[str]) -> EmbeddingResult:
        client = self._get_client()
        
        response = await client.embeddings.create(
            model=self._model,
            input=texts,
        )
        
        embeddings = [item.embedding for item in response.data]
        tokens = response.usage.total_tokens if response.usage else 0
        
        return EmbeddingResult(
            embeddings=embeddings,
            model=self._model,
            dimensions=len(embeddings[0]) if embeddings else 0,
            tokens_used=tokens,
        )
    
    async def embed_query(self, text: str) -> List[float]:
        result = await self.embed_documents([text])
        return result.embeddings[0]


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local embeddings using sentence-transformers."""
    
    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self._model_name = model
        self._model = None
        self._dimensions = 384
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @property
    def dimensions(self) -> int:
        return self._dimensions
    
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self._dimensions = self._model.get_sentence_embedding_dimension()
        return self._model
    
    async def embed_documents(self, texts: List[str]) -> EmbeddingResult:
        import asyncio
        
        model = self._get_model()
        
        def _encode():
            return model.encode(texts, convert_to_numpy=True).tolist()
        
        embeddings = await asyncio.to_thread(_encode)
        
        return EmbeddingResult(
            embeddings=embeddings,
            model=self._model_name,
            dimensions=self._dimensions,
            tokens_used=0,
        )
    
    async def embed_query(self, text: str) -> List[float]:
        result = await self.embed_documents([text])
        return result.embeddings[0]


class EmbeddingService:
    """
    Main embedding service that orchestrates embedding generation.
    
    Supports:
    - OpenAI embeddings (text-embedding-3-small/large)
    - Local sentence-transformers models
    - Automatic batching for large document sets
    """
    
    def __init__(
        self,
        provider: str = "openai",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        batch_size: int = 100,
    ):
        self.provider_name = provider
        self.batch_size = batch_size
        
        if provider == "openai":
            self._provider: EmbeddingProvider = OpenAIEmbeddingProvider(
                model=model or "text-embedding-3-small",
                api_key=api_key,
            )
        elif provider == "local":
            self._provider = LocalEmbeddingProvider(
                model=model or "sentence-transformers/all-MiniLM-L6-v2",
            )
        else:
            raise ValueError(f"Unknown embedding provider: {provider}")
    
    @property
    def model_name(self) -> str:
        return self._provider.model_name
    
    @property
    def dimensions(self) -> int:
        return self._provider.dimensions
    
    async def embed_documents(self, texts: List[str]) -> EmbeddingResult:
        """Embed a list of documents with automatic batching."""
        all_embeddings = []
        total_tokens = 0
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            result = await self._provider.embed_documents(batch)
            all_embeddings.extend(result.embeddings)
            total_tokens += result.tokens_used
        
        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self._provider.model_name,
            dimensions=self._provider.dimensions,
            tokens_used=total_tokens,
        )
    
    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query for retrieval."""
        return await self._provider.embed_query(text)


_embedding_service: EmbeddingService | None = None


def get_embedding_service(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    
    if _embedding_service is None:
        provider = provider or os.getenv("EMBEDDING_PROVIDER", "openai")
        model = model or os.getenv("EMBEDDING_MODEL")
        _embedding_service = EmbeddingService(provider=provider, model=model)
    
    return _embedding_service
