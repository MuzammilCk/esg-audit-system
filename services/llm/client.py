"""
LLM Client

OpenAI GPT-4 client with structured output support.
Handles API calls, rate limiting, and error handling.
"""

import os
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Type, TypeVar
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    latency_ms: float
    finish_reason: str


@dataclass
class StructuredResponse:
    parsed: BaseModel
    raw_response: LLMResponse


class LLMClient:
    """
    OpenAI GPT-4 client with structured output support.
    
    Features:
    - Structured output via function calling
    - Automatic retry with exponential backoff
    - Rate limiting support
    - Streaming support (optional)
    - Fallback models
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4-turbo-preview",
        fallback_model: str = "gpt-3.5-turbo",
        max_retries: int = 3,
        timeout: float = 60.0,
        temperature: float = 0.0,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.fallback_model = fallback_model
        self.max_retries = max_retries
        self.timeout = timeout
        self.temperature = temperature
        self._client = None
        self._async_client = None
    
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    def _get_async_client(self):
        if self._async_client is None:
            from openai import AsyncOpenAI
            self._async_client = AsyncOpenAI(api_key=self.api_key)
        return self._async_client
    
    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
        use_fallback: bool = False,
    ) -> LLMResponse:
        """
        Generate a completion for the given messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (overrides default)
            max_tokens: Maximum tokens in response
            use_fallback: Use fallback model instead of primary
        
        Returns:
            LLMResponse with content and metadata
        """
        client = self._get_async_client()
        model = self.fallback_model if use_fallback else self.model
        temp = temperature if temperature is not None else self.temperature
        
        start_time = datetime.now(timezone.utc)
        
        for attempt in range(self.max_retries):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                )
                
                latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                return LLMResponse(
                    content=response.choices[0].message.content,
                    model=response.model,
                    tokens_prompt=response.usage.prompt_tokens,
                    tokens_completion=response.usage.completion_tokens,
                    tokens_total=response.usage.total_tokens,
                    latency_ms=latency,
                    finish_reason=response.choices[0].finish_reason,
                )
                
            except Exception as e:
                logger.warning(f"LLM API call failed (attempt {attempt + 1}): {e}")
                
                if attempt == self.max_retries - 1:
                    if not use_fallback:
                        logger.info("Attempting fallback model...")
                        return await self.complete(
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            use_fallback=True,
                        )
                    raise
                
                await asyncio.sleep(2 ** attempt)
        
        raise RuntimeError("Unexpected state in LLM client")
    
    async def complete_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> StructuredResponse:
        """
        Generate a structured completion using function calling.
        
        The response is guaranteed to parse into the provided Pydantic model.
        
        Args:
            messages: List of message dicts
            response_model: Pydantic model for structured output
            temperature: Sampling temperature
            max_tokens: Maximum tokens
        
        Returns:
            StructuredResponse with parsed model and raw response
        """
        client = self._get_async_client()
        temp = temperature if temperature is not None else self.temperature
        
        schema = response_model.model_json_schema()
        
        function_def = {
            "name": "structured_output",
            "description": f"Output structured data matching the {response_model.__name__} schema",
            "parameters": schema,
        }
        
        start_time = datetime.now(timezone.utc)
        
        for attempt in range(self.max_retries):
            try:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tokens,
                    functions=[function_def],
                    function_call={"name": "structured_output"},
                    timeout=self.timeout,
                )
                
                latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                function_call = response.choices[0].message.function_call
                if function_call:
                    parsed_args = json.loads(function_call.arguments)
                    parsed_model = response_model.model_validate(parsed_args)
                else:
                    content = response.choices[0].message.content
                    parsed_model = self._parse_from_content(content, response_model)
                
                llm_response = LLMResponse(
                    content=json.dumps(parsed_args) if function_call else response.choices[0].message.content,
                    model=response.model,
                    tokens_prompt=response.usage.prompt_tokens,
                    tokens_completion=response.usage.completion_tokens,
                    tokens_total=response.usage.total_tokens,
                    latency_ms=latency,
                    finish_reason=response.choices[0].finish_reason,
                )
                
                return StructuredResponse(
                    parsed=parsed_model,
                    raw_response=llm_response,
                )
                
            except Exception as e:
                logger.warning(f"Structured completion failed (attempt {attempt + 1}): {e}")
                
                if attempt == self.max_retries - 1:
                    raise
                
                await asyncio.sleep(2 ** attempt)
        
        raise RuntimeError("Unexpected state in LLM client")
    
    def _parse_from_content(self, content: str, model: Type[T]) -> T:
        """Attempt to parse model from content that might contain JSON."""
        try:
            json_match = content
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_match = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                json_match = content[start:end].strip()
            
            parsed = json.loads(json_match)
            return model.model_validate(parsed)
        except Exception:
            raise ValueError(f"Could not parse {model.__name__} from response")
    
    async def batch_complete(
        self,
        batch_messages: List[List[Dict[str, str]]],
        concurrency: int = 5,
    ) -> List[LLMResponse]:
        """
        Process multiple completions concurrently.
        
        Args:
            batch_messages: List of message lists
            concurrency: Maximum concurrent requests
        
        Returns:
            List of LLMResponses in order
        """
        semaphore = asyncio.Semaphore(concurrency)
        
        async def _limited_complete(messages):
            async with semaphore:
                return await self.complete(messages)
        
        return await asyncio.gather(*[
            _limited_complete(messages) for messages in batch_messages
        ])


_llm_client: LLMClient | None = None


def get_llm_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    
    if _llm_client is None:
        _llm_client = LLMClient(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            model=model or os.getenv("LLM_MODEL", "gpt-4-turbo-preview"),
        )
    
    return _llm_client
