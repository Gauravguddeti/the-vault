"""
The Vault — LangGraph RAG Agent with per-user memory.

Graph flow:
  load_memory → classify_query → [chat | retrieve | sql_aggregate | out_of_scope] → generate_answer → save_memory

Query types:
  - "chat"         → casual conversation, greetings, small talk, follow-up chit-chat
  - "lookup"       → document-specific factual questions
  - "aggregation"  → totals, sums, counts over extracted document fields
  - "out_of_scope" → requests beyond The Vault's purpose (guardrail)

Classifier uses a fast LLM call (llama-3.1-8b-instant) for accurate intent detection,
including multi-turn context awareness. No keyword brittle matching.
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
    document_index: str              # lightweight metadata of uploaded docs
    query_type: str                  # "chat" | "lookup" | "aggregation" | "out_of_scope"
    chunks: List[Dict]               # retrieved chunks
    sql_result: Optional[Dict]       # aggregation SQL result
    answer: str
    sources: List[Dict]
    context_truncated: bool


# ── Prompts ────────────────────────────────────────────────────────────

CLASSIFIER_PROMPT = """You are an intent classifier for "The Vault" — a personal document management and expense tracking assistant.

Classify the user's latest message into EXACTLY ONE of these categories:

CHAT         — casual conversation, greetings (hi, hey, sup, how are you, thanks, bye), small talk, questions about the assistant itself, follow-up chit-chat, expressions of feeling, acknowledgements
DOCUMENT     — questions about specific documents, receipts, invoices, files, what's in a document, finding information from uploaded files (including meta-questions like "what did I upload today", "what is this document about")
AGGREGATE    — asking for totals, sums, averages, counts across documents (how much did I spend, total expenses, how many receipts)
OUT_OF_SCOPE — requests completely unrelated to documents/expenses (write me code, tell me a news story, solve this math problem, general trivia)

Rules:
- If ambiguous between CHAT and anything else, prefer CHAT for short casual messages
- Consider conversation history to determine if something is a follow-up (e.g. "what about that?" after a document question = DOCUMENT)
- Queries containing temporal language ("today", "this month") or vague references ("that document") should be DOCUMENT.
- Reply with ONLY the category word. Nothing else.

Recent conversation (for context):
{history}

Latest message: {question}

Category:"""

SYSTEM_PROMPT = """You are the assistant inside The Vault, a private, self-hosted personal document archive. You have access to: the user's uploaded documents, their extracted text and structured fields (dates, amounts, categories), and a live index of everything uploaded and when.

Personality: quietly sharp and permanently attentive — like an assistant who's already been paying attention and never needs re-briefing. Direct, warm, a little dry. Never robotic ("I do not have access to..."), never falsely humble. If you know it, say it plainly. If you don't, say that plainly too — no hedging filler.

Rules:
1. Always check the document index (filenames, dates, categories) before claiming you have no information — a document can be relevant even with a weak semantic match, especially for date-based questions like "what did I upload today".
2. Never state a number, date, or fact that isn't directly grounded in retrieved content or the document index. For totals/sums, use the structured extracted fields table via SQL — never estimate from raw text.
3. Cite the source document by name for every factual claim.
4. If a question is ambiguous and multiple recent documents could match, don't dead-end — name the top 1-2 candidates and ask which one, or answer with your best guess and flag your confidence.
5. If retrieval genuinely finds nothing, say so plainly and suggest a next step ("That doesn't look like it's in your Vault yet — want to check the Documents tab or re-upload it?") instead of a flat no.
6. Never fabricate document contents, dates, or amounts, under any circumstance, even to sound more helpful.

## LANGUAGE — STRICT RULE
- Mirror the user's language exactly. English in → English out. Hindi in → Hindi out. Hinglish in → Hinglish out.
- Never switch languages on your own.
- You understand Hindi, English, and Hinglish equally well.

## EMOJIS
- Do NOT use emojis by default.
- Only use an emoji when there is genuine humor, sarcasm, or a clear emotional moment.

Previous conversation is for context resolution — not a source of document facts."""

OUT_OF_SCOPE_SYSTEM = """You are The Vault — a personal document assistant.

The user has asked something outside your scope. Respond briefly and naturally, acknowledge their message, and redirect to what you can actually help with (document Q&A, expense tracking, finding receipts/invoices). 

Be friendly, not dismissive. Keep it short — 1-2 sentences max.

Mirror the user's language (English/Hindi/Hinglish)."""


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

    # Fetch lightweight document index
    docs = await conn.fetch(
        """
        SELECT d.original_name, d.created_at, e.category 
        FROM documents d
        LEFT JOIN extracted_fields e ON d.id = e.document_id
        WHERE d.status = 'ready'
        ORDER BY d.created_at DESC
        LIMIT 20
        """
    )
    doc_index_lines = []
    for d in docs:
        cat = d['category'] or 'Uncategorized'
        date_str = d['created_at'].strftime("%Y-%m-%d %H:%M") if d['created_at'] else 'Unknown date'
        doc_index_lines.append(f"- {d['original_name']} (Uploaded: {date_str}, Category: {cat})")
    
    document_index = "\n".join(doc_index_lines) if doc_index_lines else "No documents uploaded yet."

    return {**state, "history": history, "document_index": document_index}


async def classify_query_node(state: VaultState) -> VaultState:
    """
    Use a fast LLM call to classify query intent accurately,
    including multi-turn context awareness.
    """
    question = state["question"].strip()
    history = state.get("history", [])

    # Build a short history snippet for the classifier
    history_text = ""
    if history:
        recent = [m for m in history if m["role"] in ("user", "assistant")][-4:]
        history_text = "\n".join(
            f"{m['role'].capitalize()}: {m['content'][:120]}" for m in recent
        )

    if not history_text:
        history_text = "(none — this is the first message)"

    prompt = CLASSIFIER_PROMPT.format(
        history=history_text,
        question=question,
    )

    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",   # fast, cheap, good at classification
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        raw = response.choices[0].message.content.strip().upper()
    except Exception as e:
        logger.error(f"Classifier LLM call failed: {e}, defaulting to 'lookup'")
        raw = "DOCUMENT"

    if "AGGREGATE" in raw:
        query_type = "aggregation"
    elif "DOCUMENT" in raw:
        query_type = "lookup"
    elif "OUT" in raw or "SCOPE" in raw:
        query_type = "out_of_scope"
    else:
        query_type = "chat"

    logger.info(f"Query classified as: {query_type!r} (raw classifier output: {raw!r})")
    return {**state, "query_type": query_type, "chunks": [], "sql_result": None}


async def retrieve_node(state: VaultState) -> VaultState:
    """Embed the question and retrieve top-k similar chunks via pgvector."""
    conn = state["conn"]
    question = state["question"]

    # Augment with recent history for better recall
    context_question = question
    history = state.get("history", [])
    if history:
        last_user_msgs = [m for m in history if m["role"] == "user"][-2:]
        if last_user_msgs:
            last = last_user_msgs[-1].get("content", "")
            if last and len(last) < 200:
                context_question = f"{last} {question}"

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
    LLM only rephrases the result — no math by LLM.
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

        if row and row["total"] is not None:
            result = {
                "total": float(row["total"]),
                "count": row["count"],
                "currency": row["currency"] or "USD",
                "earliest": str(row["earliest"]) if row["earliest"] else None,
                "latest": str(row["latest"]) if row["latest"] else None,
                "category": category_filter,
            }
    except Exception as e:
        logger.error(f"SQL aggregation failed: {e}")

    # Also retrieve chunks for context
    try:
        query_vector = await embed_single(state["question"])
        chunks = await vector_search(conn, query_vector, limit=4)
    except Exception as e:
        logger.error(f"Vector search in aggregation failed: {e}")
        chunks = []

    return {**state, "sql_result": result, "chunks": chunks, "context_truncated": False}


async def generate_answer_node(state: VaultState) -> VaultState:
    """
    Generate an answer using Groq.
    Routes:
      - chat         → conversational reply, no doc context
      - out_of_scope → guardrail redirect
      - lookup       → grounded doc answer (zero-chunk guard)
      - aggregation  → SQL result + chunk context
    """
    chunks = state.get("chunks", [])
    query_type = state["query_type"]
    sql_result = state.get("sql_result")
    history = state.get("history", [])

    # ── Out-of-scope guardrail ─────────────────────────────────────────
    if query_type == "out_of_scope":
        messages = [
            {"role": "system", "content": OUT_OF_SCOPE_SYSTEM},
            *[{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ("user", "assistant")][-4:],
            {"role": "user", "content": state["question"]},
        ]
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=150,
        )
        return {**state, "answer": response.choices[0].message.content.strip(), "sources": []}

    # ── Zero-chunk guard for document lookup ──────────────────────────
    if query_type == "lookup" and not chunks:
        index_context = f"[Live Document Index (Recent Uploads)]\n{state.get('document_index', 'None')}\n"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ("user", "assistant")][-6:],
            {"role": "user", "content": f"{index_context}\nQuestion: {state['question']}\n\n[Note: No detailed document text chunks were retrieved. Answer using the Document Index above if possible. If the information isn't in the index, inform the user plainly and suggest uploading.]"},
        ]
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=200,
        )
        return {**state, "answer": response.choices[0].message.content.strip(), "sources": []}

    # ── Build document context ────────────────────────────────────────
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

    # ── Build full message list ───────────────────────────────────────
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in history:
        if msg["role"] in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    index_context = f"[Live Document Index (Recent Uploads)]\n{state.get('document_index', 'None')}\n"

    if context:
        user_content = f"{index_context}\nContext from documents:\n{context}\n\nQuestion: {state['question']}"
    else:
        user_content = f"{index_context}\nQuestion: {state['question']}"

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
        answer += "\n\n*Note: Some documents were excluded due to context limits.*"

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

        if not state.get("history"):
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
    """Route based on classified query type."""
    qt = state["query_type"]
    if qt in ("chat", "out_of_scope"):
        return "generate_answer"    # no retrieval needed
    if qt == "aggregation":
        return "sql_aggregate"
    return "retrieve"               # lookup


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
        "generate_answer": "generate_answer",
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
