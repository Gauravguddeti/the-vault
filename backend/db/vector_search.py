"""
Vector similarity search — RLS-enforced pgvector cosine search.
"""
import logging
from typing import List, Dict

import asyncpg
from core.config import settings

logger = logging.getLogger(__name__)


async def vector_search(
    conn: asyncpg.Connection,
    query_embedding: List[float],
    limit: int = None,
    min_score: float = None,
) -> List[Dict]:
    """
    Perform cosine similarity search over chunks table.
    RLS is already active on `conn` — results are automatically user-scoped.

    Returns list of {chunk_id, document_id, chunk_index, text, score, document_name}.
    """
    limit = limit or settings.MAX_CHUNKS
    min_score = min_score if min_score is not None else settings.MIN_SIMILARITY_SCORE

    # pgvector cosine distance: 1 - cosine_similarity
    # So similarity = 1 - distance
    rows = await conn.fetch(
        """
        SELECT
            c.id::text        AS chunk_id,
            c.document_id::text,
            c.chunk_index,
            c.text,
            d.original_name   AS document_name,
            1 - (c.embedding <=> $1::vector) AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE 1 - (c.embedding <=> $1::vector) >= $2
        ORDER BY c.embedding <=> $1::vector
        LIMIT $3
        """,
        str(query_embedding),
        min_score,
        limit,
    )

    return [dict(r) for r in rows]
