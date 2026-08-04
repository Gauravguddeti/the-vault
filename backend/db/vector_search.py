"""
Hybrid search — combines vector (pgvector cosine) and keyword (Postgres FTS/BM25)
search via Reciprocal Rank Fusion (RRF).

Why hybrid:
  - Dense embeddings handle paraphrase / semantic similarity well
  - BM25/FTS catches exact terms, proper nouns, OCR-garbled drug names, rare words
  - RRF is parameter-light and empirically outperforms linear interpolation

RRF formula:
  score(doc) = Σ_i  1 / (k + rank_i)
  where k=60 is the standard constant and rank_i is 1-indexed position in list i.
"""
import logging
from typing import List, Dict

import asyncpg
from core.config import settings

logger = logging.getLogger(__name__)

# RRF constant — standard value from the original Cormack & Clarke paper
_RRF_K = 60


async def vector_search(
    conn: asyncpg.Connection,
    query_embedding: List[float],
    limit: int = None,
    min_score: float = None,
) -> List[Dict]:
    """
    Pure cosine similarity search over chunks table.
    RLS is already active on `conn` — results are automatically user-scoped.
    Returns list of {chunk_id, document_id, chunk_index, text, similarity, document_name}.
    """
    limit = limit or settings.MAX_CHUNKS
    min_score = min_score if min_score is not None else settings.MIN_SIMILARITY_SCORE

    try:
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
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []


async def keyword_search(
    conn: asyncpg.Connection,
    query_text: str,
    limit: int = None,
) -> List[Dict]:
    """
    Postgres full-text search (BM25-approximation via ts_rank_cd) over chunk text.
    Uses plainto_tsquery for robustness with OCR-garbled / multi-word input.
    Returns list of {chunk_id, document_id, chunk_index, text, similarity, document_name}.
    """
    limit = limit or settings.MAX_CHUNKS * 2  # cast a wider net for keyword

    # plainto_tsquery is more tolerant than to_tsquery (no special syntax required)
    try:
        rows = await conn.fetch(
            """
            SELECT
                c.id::text        AS chunk_id,
                c.document_id::text,
                c.chunk_index,
                c.text,
                d.original_name   AS document_name,
                ts_rank_cd(
                    to_tsvector('english', c.text),
                    plainto_tsquery('english', $1)
                ) AS similarity
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE to_tsvector('english', c.text) @@ plainto_tsquery('english', $1)
            ORDER BY similarity DESC
            LIMIT $2
            """,
            query_text,
            limit,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        return []


def _reciprocal_rank_fusion(
    vector_results: List[Dict],
    keyword_results: List[Dict],
    k: int = _RRF_K,
    top_n: int = None,
) -> List[Dict]:
    """
    Merge two ranked lists via Reciprocal Rank Fusion.
    Each result's RRF score = 1/(k + rank_vector) + 1/(k + rank_keyword).
    Documents appearing in only one list get the other's contribution set to 0.
    """
    scores: Dict[str, float] = {}
    meta: Dict[str, Dict] = {}

    for rank, result in enumerate(vector_results, start=1):
        cid = result["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        meta[cid] = result

    for rank, result in enumerate(keyword_results, start=1):
        cid = result["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        if cid not in meta:
            meta[cid] = result

    sorted_ids = sorted(scores, key=lambda c: scores[c], reverse=True)
    if top_n:
        sorted_ids = sorted_ids[:top_n]

    merged = []
    for cid in sorted_ids:
        row = dict(meta[cid])
        row["similarity"] = scores[cid]   # overwrite with RRF score for consistency
        row["rrf_score"] = scores[cid]
        merged.append(row)

    return merged


async def hybrid_search(
    conn: asyncpg.Connection,
    query_text: str,
    query_embedding: List[float],
    limit: int = None,
    min_vector_score: float = None,
) -> List[Dict]:
    """
    Hybrid search: vector + keyword, merged via RRF.

    Falls back to vector-only if keyword search returns nothing (e.g. very short queries).
    Falls back to keyword-only if no embeddings exist yet.

    Args:
        conn: RLS-scoped asyncpg connection
        query_text: raw query string (for BM25)
        query_embedding: dense embedding vector (for cosine)
        limit: max chunks to return
        min_vector_score: minimum cosine similarity for vector leg
    Returns:
        Merged, deduplicated, RRF-ranked chunk list
    """
    limit = limit or settings.MAX_CHUNKS
    min_score = min_vector_score if min_vector_score is not None else settings.MIN_SIMILARITY_SCORE

    # Run both legs concurrently
    import asyncio
    vector_task = asyncio.create_task(
        vector_search(conn, query_embedding, limit=limit * 2, min_score=min_score)
    )
    keyword_task = asyncio.create_task(
        keyword_search(conn, query_text, limit=limit * 2)
    )
    vector_results, keyword_results = await asyncio.gather(vector_task, keyword_task)

    logger.debug(
        "[HYBRID] vector=%d keyword=%d query=%r",
        len(vector_results), len(keyword_results), query_text[:80],
    )

    if not vector_results and not keyword_results:
        return []

    if not vector_results:
        return keyword_results[:limit]

    if not keyword_results:
        return vector_results[:limit]

    merged = _reciprocal_rank_fusion(vector_results, keyword_results, top_n=limit)
    logger.debug("[HYBRID] merged=%d chunks after RRF", len(merged))
    return merged
