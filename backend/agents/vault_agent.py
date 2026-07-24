"""
The Vault — LangGraph RAG Agent with per-user memory.

Graph flow:
  load_memory → classify_query → [retrieve | sql_aggregate] → answer → save_memory

Anti-hallucination:
  - Zero chunks → no LLM call → "I don't have enough information" response
  - System prompt forbids inference beyond retrieved context
  - Aggregation math done in SQL, LLM only rephrases result
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, TypedDict

import asyncpg

from langgraph.graph import END, StateGraph

from core.config import settings
from db.vector_search import vector_search
from services.embedder import embed_single

logger = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────

class VaultState(TypedDict):
    question: str
    session_id: str
    user_id: str
    conn: Any                        # asyncpg connection (RLS-scoped)
    history: List[Dict]              # previous messages from DB
    query_type: str                  # "lookup" | "aggregation"
    chunks: List[Dict]               # retrieved chunks
    sql_result: Optional[Dict]       # aggregation SQL result
    answer: str
    sources: List[Dict]
    context_truncated: bool

# ── Aggregation keywords ───────────────────────────────────────────────

AGGREGATION_KEYWORDS = [
    "total", "sum", "how much", "how many", "count", "all",
    "average", "avg", "spend", "spent", "cost", "costs",
    "add up", "tally", "aggregate",
]

# ── Grounded system prompt ─────────────────────────────────────────────

GROUNDED_SYSTEM_PROMPT = """You are The Vault assistant — a private document Q&A system.

CRITICAL RULES you must ALWAYS follow:
1. Answer ONLY from the provided context. Never infer, estimate, or guess beyond what is explicitly stated.
2. If the context does not contain enough information, respond EXACTLY with:
   "I don't have enough information in your documents to answer that question."
3. Always cite your sources using the format: [Source: <document_name>, chunk <chunk_index>]
4. For numbers and amounts, use ONLY values explicitly present in the context.
5. Do not fabricate document names, dates, amounts, or any other facts.

Previous conversation is provided for context resolution only — do not treat it as a source of facts about the user's documents."""

NO_INFO_RESPONSE = "I don't have enough information in your documents to answer that question."

# ── Nodes ──────────────────────────────────────────────────────────────

async def load_memory_node(state: VaultState) -> VaultState:
    """Load recent conversation history for this session."""
    conn = state["conn"]
    session_id = state["session_id"]

    # Fetch summary of old messages (if exists) + recent messages
    session = await conn.fetchrow(
        "SELECT summary FROM conversation_sessions WHERE id=$1::uuid",
        session_id,
    )

    messages = await conn.fetch(
        """
        SELECT role, content FROM conversation_messages
        WHERE session_id=$1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        session_id,
        settings.MEMORY_WINDOW,
    )

    history = [dict(m) for m in reversed(messages)]  # chronological order

    # Prepend summary if exists
    if session and session["summary"]:
        history.insert(0, {
            "role": "system",
            "content": f"[Earlier conversation summary]: {session['summary']}",
        })

    return {**state, "history": history}


async def classify_query_node(state: VaultState) -> VaultState:
    """Classify query as 'lookup' or 'aggregation' based on keywords."""
    question_lower = state["question"].lower()
    is_aggregation = any(kw in question_lower for kw in AGGREGATION_KEYWORDS)
    query_type = "aggregation" if is_aggregation else "lookup"
    logger.info(f"Query classified as: {query_type}")
    return {**state, "query_type": query_type}


async def retrieve_node(state: VaultState) -> VaultState:
    """Embed the question and retrieve top-k similar chunks via pgvector."""
    conn = state["conn"]
    question = state["question"]

    # Include recent history context in the query embedding for better recall
    context_question = question
    if state.get("history"):
        last_msg = state["history"][-1].get("content", "") if state["history"] else ""
        if last_msg and len(last_msg) < 200:
            context_question = f"{last_msg} {question}"

    query_vector = await embed_single(context_question)
    chunks = await vector_search(conn, query_vector)

    # Apply token cap
    total_tokens = 0
    filtered_chunks = []
    truncated = False

    for chunk in chunks:
        chunk_tokens = len(chunk["text"].split()) * 1.3  # rough estimate
        if total_tokens + chunk_tokens > settings.MAX_CONTEXT_TOKENS:
            truncated = True
            break
        filtered_chunks.append(chunk)
        total_tokens += chunk_tokens

    return {**state, "chunks": filtered_chunks, "context_truncated": truncated}


async def sql_aggregate_node(state: VaultState) -> VaultState:
    """
    For aggregation queries: run SQL on extracted_fields (RLS-enforced).
    The LLM will only rephrase the result — no math by LLM.
    """
    conn = state["conn"]
    question_lower = state["question"].lower()
    result = {}

    try:
        # Determine aggregation type and optional category filter
        category_filter = None
        for cat in ["medical", "dental", "food", "transport", "electronics",
                    "repairs", "insurance", "taxes", "rent", "utilities"]:
            if cat in question_lower or (cat == "dental" and "dentist" in question_lower):
                category_filter = cat if cat != "dental" else "medical"
                break

        if category_filter:
            row = await conn.fetchrow(
                """
                SELECT
                    SUM(amount) AS total,
                    COUNT(*) AS count,
                    MIN(txn_date) AS earliest,
                    MAX(txn_date) AS latest,
                    currency
                FROM extracted_fields
                WHERE category = $1
                GROUP BY currency
                ORDER BY total DESC NULLS LAST
                LIMIT 1
                """,
                category_filter,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT
                    SUM(amount) AS total,
                    COUNT(*) AS count,
                    MIN(txn_date) AS earliest,
                    MAX(txn_date) AS latest,
                    currency
                FROM extracted_fields
                GROUP BY currency
                ORDER BY total DESC NULLS LAST
                LIMIT 1
                """
            )

        if row:
            result = {
                "total": float(row["total"]) if row["total"] else 0,
                "count": row["count"],
                "currency": row["currency"] or "USD",
                "earliest": str(row["earliest"]) if row["earliest"] else None,
                "latest": str(row["latest"]) if row["latest"] else None,
                "category": category_filter,
            }
    except Exception as e:
        logger.error(f"SQL aggregation failed: {e}")

    # Also do vector retrieval for context
    query_vector = await embed_single(state["question"])
    chunks = await vector_search(conn, query_vector, limit=4)

    return {**state, "sql_result": result, "chunks": chunks, "context_truncated": False}


async def answer_node(state: VaultState) -> VaultState:
    """
    Generate a grounded answer using Groq.
    Zero-chunk guard: if no chunks, return NO_INFO_RESPONSE without calling LLM.
    """
    chunks = state.get("chunks", [])
    query_type = state["query_type"]
    sql_result = state.get("sql_result")

    # ── Zero-chunk guard ──────────────────────────────────────────────
    if not chunks and not sql_result:
        return {
            **state,
            "answer": NO_INFO_RESPONSE,
            "sources": [],
        }

    # ── Build context ─────────────────────────────────────────────────
    context_parts = []

    if query_type == "aggregation" and sql_result:
        context_parts.append(
            f"[SQL Aggregation Result]: Total={sql_result.get('total')}, "
            f"Currency={sql_result.get('currency')}, Count={sql_result.get('count')}, "
            f"Category={sql_result.get('category')}, "
            f"Date range: {sql_result.get('earliest')} to {sql_result.get('latest')}"
        )

    for i, chunk in enumerate(chunks):
        context_parts.append(
            f"[Chunk {i+1} | {chunk['document_name']} | chunk #{chunk['chunk_index']} "
            f"| similarity: {chunk['similarity']:.2f}]\n{chunk['text']}"
        )

    context = "\n\n---\n\n".join(context_parts)

    # ── Build messages with history ───────────────────────────────────
    messages = [{"role": "system", "content": GROUNDED_SYSTEM_PROMPT}]

    for msg in state.get("history", []):
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"Context:\n{context}\n\nQuestion: {state['question']}",
    })

    # ── Call Mistral ─────────────────────────────────────────────────────
    from mistralai import Mistral
    client = Mistral(api_key=settings.MISTRAL_API_KEY)
    response = client.chat.complete(
        model=settings.MISTRAL_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=1024,
    )

    answer = response.choices[0].message.content.strip()

    if state.get("context_truncated"):
        answer += "\n\n*Note: Some relevant documents were excluded due to context limits.*"

    # ── Build sources ─────────────────────────────────────────────────
    sources = [
        {
            "document_name": c["document_name"],
            "document_id": c["document_id"],
            "chunk_index": c["chunk_index"],
            "similarity": round(c["similarity"], 3),
        }
        for c in chunks
    ]

    return {**state, "answer": answer, "sources": sources}


async def save_memory_node(state: VaultState) -> VaultState:
    """Save the Q&A pair to conversation_messages."""
    conn = state["conn"]
    session_id = state["session_id"]
    user_id = state["user_id"]

    try:
        # Insert user message
        await conn.execute(
            """
            INSERT INTO conversation_messages (session_id, user_id, role, content)
            VALUES ($1::uuid, $2::uuid, 'user', $3)
            """,
            session_id, user_id, state["question"],
        )

        # Insert assistant message with sources
        await conn.execute(
            """
            INSERT INTO conversation_messages
                (session_id, user_id, role, content, sources, query_type)
            VALUES ($1::uuid, $2::uuid, 'assistant', $3, $4::jsonb, $5)
            """,
            session_id, user_id,
            state["answer"],
            json.dumps(state["sources"]),
            state["query_type"],
        )

        # Update session metadata
        title_update = ""
        if not state.get("history"):
            # First message — set title from question
            short_title = state["question"][:60]
            await conn.execute(
                "UPDATE conversation_sessions SET title=$1, message_count=message_count+2, updated_at=NOW() WHERE id=$2::uuid",
                short_title, session_id,
            )
        else:
            await conn.execute(
                "UPDATE conversation_sessions SET message_count=message_count+2, updated_at=NOW() WHERE id=$1::uuid",
                session_id,
            )
    except Exception as e:
        logger.error(f"Failed to save memory: {e}")

    return state


# ── Route function ─────────────────────────────────────────────────────

def route_query(state: VaultState) -> str:
    """Route to retrieval or SQL aggregation based on query type."""
    if state["query_type"] == "aggregation":
        return "sql_aggregate"
    return "retrieve"


# ── Build graph ────────────────────────────────────────────────────────

def build_vault_agent():
    """Construct and compile the LangGraph agent."""
    graph = StateGraph(VaultState)

    graph.add_node("load_memory", load_memory_node)
    graph.add_node("classify_query", classify_query_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("sql_aggregate", sql_aggregate_node)
    graph.add_node("answer", answer_node)
    graph.add_node("save_memory", save_memory_node)

    graph.set_entry_point("load_memory")
    graph.add_edge("load_memory", "classify_query")
    graph.add_conditional_edges("classify_query", route_query, {
        "retrieve": "retrieve",
        "sql_aggregate": "sql_aggregate",
    })
    graph.add_edge("retrieve", "answer")
    graph.add_edge("sql_aggregate", "answer")
    graph.add_edge("answer", "save_memory")
    graph.add_edge("save_memory", END)

    return graph.compile()


# Singleton agent instance
_agent = None

def get_agent():
    global _agent
    if _agent is None:
        _agent = build_vault_agent()
    return _agent
