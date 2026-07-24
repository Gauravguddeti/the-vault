"""
Embedding service — generates vector embeddings for text chunks.
Supports Ollama (nomic-embed-text) and OpenAI (text-embedding-3-small).
"""
import asyncio
import logging
from typing import List

import httpx
from core.config import settings

logger = logging.getLogger(__name__)


async def embed_single(text: str) -> List[float]:
    """Embed a single text string. Returns a float vector."""
    results = await embed_chunks([text])
    return results[0]


async def embed_chunks(texts: List[str]) -> List[List[float]]:
    """
    Embed a list of text strings.
    Returns a list of float vectors (one per input text).
    """
    if not texts:
        return []

    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "ollama":
        return await _embed_ollama(texts)
    elif provider == "openai":
        return await _embed_openai(texts)
    else:
        raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")


async def _embed_ollama(texts: List[str]) -> List[List[float]]:
    """Embed using Ollama nomic-embed-text."""
    embeddings = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for text in texts:
            response = await client.post(
                f"{settings.OLLAMA_ENDPOINT}/api/embeddings",
                json={"model": settings.EMBEDDING_MODEL, "prompt": text},
            )
            response.raise_for_status()
            data = response.json()
            embeddings.append(data["embedding"])
    return embeddings


async def _embed_openai(texts: List[str]) -> List[List[float]]:
    """Embed using OpenAI text-embedding-3-small."""
    import openai
    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts,
    )
    # Sort by index to preserve order
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]
