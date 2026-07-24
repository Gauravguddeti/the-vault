"""
Text chunker — splits document text into overlapping chunks for embedding.
Uses tiktoken for accurate token counting.
"""
import re
from typing import List, Dict

import tiktoken

# Target tokens per chunk and overlap
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        # cl100k_base works for both OpenAI and nomic-embed-text
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def chunk_text(text: str) -> List[Dict]:
    """
    Split text into overlapping chunks of ~CHUNK_SIZE tokens.
    Returns list of {chunk_index, text, token_count}.
    """
    if not text or not text.strip():
        return []

    enc = _get_encoder()
    tokens = enc.encode(text)
    total_tokens = len(tokens)

    if total_tokens == 0:
        return []

    chunks = []
    start = 0
    chunk_index = 0

    while start < total_tokens:
        end = min(start + CHUNK_SIZE, total_tokens)
        chunk_tokens = tokens[start:end]
        chunk_text_str = enc.decode(chunk_tokens)

        # Clean up chunk text
        chunk_text_str = chunk_text_str.strip()
        if chunk_text_str:
            chunks.append({
                "chunk_index": chunk_index,
                "text": chunk_text_str,
                "token_count": len(chunk_tokens),
            })
            chunk_index += 1

        if end >= total_tokens:
            break

        # Slide window with overlap
        start = end - CHUNK_OVERLAP

    return chunks
