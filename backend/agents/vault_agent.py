"""
The Vault — LangGraph RAG Agent with per-user memory.

Graph flow:
  load_memory → classify_query → [chat | retrieve | sql_aggregate] → generate_answer → save_memory

Query types:
  - "chat"        → casual greetings, small talk, general questions (no doc search needed)
  - "lookup"      → document-specific factual questions
  - "aggregation" → totals, sums, counts over extracted fields

Features:
  - Hinglish-aware (Hindi + English mix)
  - Tone-adaptive (mirrors user's casual/formal style)
  - Anti-hallucination for document facts
  - Zero-chunk guard for lookup queries
"""
import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

import asyncpg
from groq import AsyncGroq
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
    query_type: str                  # "chat" | "lookup" | "aggregation"
    chunks: List[Dict]               # retrieved chunks
    sql_result: Optional[Dict]       # aggregation SQL result
    answer: str
    sources: List[Dict]
    context_truncated: bool


# ── Keyword lists ──────────────────────────────────────────────────────

AGGREGATION_KEYWORDS = [
    "total", "sum", "how much", "how many", "count", "all",
    "average", "avg", "spend", "spent", "cost", "costs",
    "add up", "tally", "aggregate", "kitna", "kitne", "total karo",
    "jod", "pura", "sab",
]

# Conversational triggers — greetings, small talk, general questions
CHAT_PATTERNS = [
    # Greetings
    "hi", "hello", "hey", "heyy", "heyyy", "heyyyy", "hiii", "hiiii",
    "hola", "yo", "sup", "what's up", "wassup", "whatsup",
    # Hindi/Hinglish greetings
    "namaste", "namaskar", "kem cho", "kaise ho", "kya haal", "kya chal raha",
    "kya scene", "bhai", "yaar", "dost",
    # Thanks / acknowledgement
    "thanks", "thank you", "shukriya", "dhanyawad", "thx", "ty",
    "ok", "okay", "cool", "got it", "nice", "great", "awesome",
    "accha", "theek hai", "sahi hai", "bilkul",
    # Farewells
    "bye", "goodbye", "see ya", "later", "alvida", "phir milenge",
    # Help / intro
    "help", "what can you do", "who are you", "kya kar sakte ho",
    "kya karta hai", "batao", "bata",
]


# ── System prompts ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are The Vault — a smart, friendly personal document assistant.

## YOUR PERSONALITY
- You are warm, helpful, and conversational. Not robotic.
- You adapt to how the user talks. If they're casual, you're casual. If formal, you're formal.
- You understand Hinglish (a natural mix of Hindi and English). Reply in the same language mix the user uses.
- If someone says "kya haal" reply naturally, "sab theek! Bata kya chahiye?" etc.
- Use emojis occasionally when the vibe is casual.

## YOUR TWO MODES

### Mode 1 — DOCUMENT Q&A (when context chunks are provided)
- Answer ONLY from the provided document chunks. Never infer or fabricate.
- If context doesn't have the answer, say so honestly: "Yaar, iske baare mein mujhe documents mein kuch nahi mila. Try uploading the relevant document!"
- Always cite sources: [Source: <document_name>, chunk <chunk_index>]
- For numbers/amounts: use ONLY values from the context.

### Mode 2 — GENERAL CHAT (when no context chunks)
- Answer general/conversational questions naturally.
- You can answer basic general knowledge, help questions, or just chat.
- If someone asks something that needs their documents but they haven't uploaded any, gently nudge them: "Upload karo apna document, phir main properly bata sakta hoon!"

## LANGUAGE RULES
- Understand Hindi, English, and Hinglish equally well.
- Reply in whatever language mix the user used.
- Common Hinglish words you should understand: kya, hai, nahi, haan, accha, sahi, bata, dekh, bol, kar, mera, tera, yaar, bhai, dost, theek, chal, aur, matlab, toh, phir, abhi, kab, kaise, kitna, kaun, kahan

Previous conversation is for context only — not a source of document facts."""


# ── Nodes ──────────────────────────────────────────────────────────────

async def load_memory_node(state: VaultState) -> VaultState:
    """Load recent conversation history for this session."""
    conn = state["conn"]
    session_id = state["session_id"]

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

    history = [dict(m) for m in reversed(messages)]

    if session and session["summary"]:
        history.insert(0, {
            "role": "system",
            "content": f"[Earlier conversation summary]: {session['summary']}",
        })

    return {**state, "history": history}


async def classify_query_node(state: VaultState) -> VaultState:
    """
    Classify query into 3 types:
    - 'chat'        → casual / conversational (no doc search needed)
    - 'aggregation' → totals, sums, counts
    - 'lookup'      → document Q&A
    """
    question = state["question"].strip()
    question_lower = question.lower()

    # 1. Check for pure conversational queries (short + matches chat pattern)
    # Strip punctuation for matching
    clean = question_lower.strip("!?.,;: ")
    words = clean.split()

    is_chat = False
    if len(words) <= 4:
        # Short messages — check if any word or phrase matches chat patterns
        for pattern in CHAT_PATTERNS:
            if pattern in clean:
                is_chat = True
                break

    # Also catch very short messages with no document intent
    if not is_chat and len(clean) <= 12:
        # Check if message contains any document-search intent
        doc_intent_words = [
            "document", "file", "receipt", "invoice", "pdf", "amount",
            "paid", "payment", "date", "vendor", "total", "expense",
            "doc", "dekh", "find", "search", "show",
        ]
        has_doc_intent = any(w in question_lower for w in doc_intent_words)
        has_agg_intent = any(kw in question_lower for kw in AGGREGATION_KEYWORDS)
        if not has_doc_intent and not has_agg_intent:
            is_chat = True

    if is_chat:
        logger.info("Query classified as: chat")
        return {**state, "query_type": "chat", "chunks": [], "sql_result": None}

    # 2. Check for aggregation
    is_aggregation = any(kw in question_lower for kw in AGGREGATION_KEYWORDS)
    if is_aggregation:
        logger.info("Query classified as: aggregation")
        return {**state, "query_type": "aggregation"}

    # 3. Default: document lookup
    logger.info("Query classified as: lookup")
    return {**state, "query_type": "lookup"}


async def retrieve_node(state: VaultState) -> VaultState:
    """Embed the question and retrieve top-k similar chunks via pgvector."""
    conn = state["conn"]
    question = state["question"]

    # Augment with recent history for better recall
    context_question = question
    if state.get("history"):
        last_msg = state["history"][-1].get("content", "") if state["history"] else ""
        if last_msg and len(last_msg) < 200:
            context_question = f"{last_msg} {question}"

    query_vector = await embed_single(context_question)
    chunks = await vector_search(conn, query_vector)

    # Token cap
    total_tokens = 0
    filtered_chunks = []
    truncated = False

    for chunk in chunks:
        chunk_tokens = len(chunk["text"].split()) * 1.3
        if total_tokens + chunk_tokens > settings.MAX_CONTEXT_TOKENS:
            truncated = True
            break
        filtered_chunks.append(chunk)
        total_tokens += chunk_tokens

    return {**state, "chunks": filtered_chunks, "context_truncated": truncated}


async def sql_aggregate_node(state: VaultState) -> VaultState:
    """
    For aggregation queries: run SQL on extracted_fields (RLS-enforced).
    The LLM only rephrases the result — no math by LLM.
    """
    conn = state["conn"]
    question_lower = state["question"].lower()
    result = {}

    try:
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


async def generate_answer_node(state: VaultState) -> VaultState:
    """
    Generate an answer using Groq.
    - For 'chat': answer conversationally without document context.
    - For 'lookup': use retrieved chunks (zero-chunk guard applies).
    - For 'aggregation': use SQL result + chunks.
    """
    chunks = state.get("chunks", [])
    query_type = state["query_type"]
    sql_result = state.get("sql_result")

    # ── Zero-chunk guard for lookup queries ───────────────────────────
    if query_type == "lookup" and not chunks:
        return {
            **state,
            "answer": "Yaar, iske baare mein mujhe tumhare documents mein kuch nahi mila 🤔 Try uploading the relevant document, phir properly bata sakta hoon!",
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

    context = "\n\n---\n\n".join(context_parts) if context_parts else ""

    # ── Build messages with history ───────────────────────────────────
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in state.get("history", []):
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Build user message depending on mode
    if context:
        user_content = f"Context from documents:\n{context}\n\nQuestion: {state['question']}"
    else:
        # Pure chat mode — no document context
        user_content = state["question"]

    messages.append({"role": "user", "content": user_content})

    # ── Call Groq ─────────────────────────────────────────────────────
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    response = await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=messages,
        temperature=0.7 if query_type == "chat" else 0.1,
        max_tokens=1024,
    )

    answer = response.choices[0].message.content.strip()

    if state.get("context_truncated"):
        answer += "\n\n*Note: Kuch relevant documents context limit ki wajah se exclude ho gaye.*"

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
        await conn.execute(
            """
            INSERT INTO conversation_messages (session_id, user_id, role, content)
            VALUES ($1::uuid, $2::uuid, 'user', $3)
            """,
            session_id, user_id, state["question"],
        )

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

        short_title = state["question"][:60]
        if not state.get("history"):
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
    """Route to: chat handler, retrieval, or SQL aggregation."""
    qt = state["query_type"]
    if qt == "chat":
        return "generate_answer"   # skip retrieval entirely for chat
    if qt == "aggregation":
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
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("save_memory", save_memory_node)

    graph.set_entry_point("load_memory")
    graph.add_edge("load_memory", "classify_query")
    graph.add_conditional_edges("classify_query", route_query, {
        "generate_answer": "generate_answer",   # chat shortcut
        "retrieve": "retrieve",
        "sql_aggregate": "sql_aggregate",
    })
    graph.add_edge("retrieve", "generate_answer")
    graph.add_edge("sql_aggregate", "generate_answer")
    graph.add_edge("generate_answer", "save_memory")
    graph.add_edge("save_memory", END)

    return graph.compile()


# Singleton agent instance
_agent = None

def get_agent():
    global _agent
    if _agent is None:
        _agent = build_vault_agent()
    return _agent
