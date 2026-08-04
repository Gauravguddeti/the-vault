"""Query router — /api/query (JSON) + /api/query/stream (SSE streaming)."""
import asyncpg
import asyncio
import json
import logging
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from core.rate_limit import limiter

from core.auth import get_current_user, get_db_with_rls
from agents.vault_agent import get_agent, build_streaming_context
from db.connection import get_pool, set_rls_user

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    session_id: str


class QueryResponse(BaseModel):
    answer: str
    sources: list
    query_type: str
    context_truncated: bool = False


@router.post("", response_model=QueryResponse)
@limiter.limit("20/minute")
async def run_query(
    request: Request,
    body: QueryRequest,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session = await conn.fetchrow(
        "SELECT id FROM conversation_sessions WHERE id=$1::uuid",
        body.session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    agent = get_agent()
    result = await agent.ainvoke({
        "question": body.question,
        "session_id": body.session_id,
        "user_id": user["user_id"],
        "conn": conn,
        "history": [],
        "document_index": "",
        "query_type": "lookup",
        "chunks": [],
        "sql_result": None,
        "web_results": [],
        "answer": "",
        "sources": [],
        "thinking": "",
        "context_truncated": False,
        "user_memory": "",
        "is_general_knowledge": False,
        "web_category": None,
        "rxnorm_note": "",
        "confirmation_pending": None,
        "skip_confirmation_check": False,
    })

    await conn.execute(
        """
        INSERT INTO audit_logs (user_id, action, resource_id, details)
        VALUES ($1::uuid, 'query_run', $2::uuid, $3)
        """,
        user["user_id"], body.session_id, f"Query Type: {result['query_type']}"
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "query_type": result["query_type"],
        "context_truncated": result.get("context_truncated", False),
    }


@router.post("/stream")
@limiter.limit("20/minute")
async def run_query_stream(
    request: Request,
    body: QueryRequest,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    """
    SSE streaming endpoint — connection-resilient.

    The LLM generation and DB persistence run in a background asyncio.Task
    that uses its own dedicated DB connection from the pool. This means:
    - The answer is ALWAYS saved even if the user closes or leaves the page.
    - The user message is saved to the DB IMMEDIATELY (before any LLM call).
    - The SSE stream taps the background task via an asyncio.Queue.
    - If the browser disconnects, the background task continues uninterrupted.

    SSE format:
      data: {"token": "word", "done": false}
      data: {"token": "", "done": true, "sources": [...], "query_type": "...", ...}
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session = await conn.fetchrow(
        "SELECT id FROM conversation_sessions WHERE id=$1::uuid",
        body.session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    # ── Step 1: Build retrieval context (uses the request-scoped RLS connection) ──
    try:
        context = await build_streaming_context(
            question=body.question,
            session_id=body.session_id,
            user_id=user["user_id"],
            conn=conn,
        )
    except Exception as e:
        logger.error(f"Streaming context build failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build query context")

    # ── Step 2: Save user message to DB immediately (before LLM call) ──────────
    # This ensures the question persists even if the user disconnects mid-generation.
    has_history = bool(context.get("has_history"))
    question_text = body.question
    session_id = body.session_id
    user_id = user["user_id"]

    try:
        await conn.execute(
            """
            INSERT INTO conversation_messages (session_id, user_id, role, content)
            VALUES ($1::uuid, $2::uuid, 'user', $3)
            """,
            session_id, user_id, question_text,
        )
        # Update session title on first message
        if not has_history:
            short_title = question_text[:60]
            await conn.execute(
                "UPDATE conversation_sessions SET title=$1, message_count=message_count+1, updated_at=NOW() WHERE id=$2::uuid",
                short_title, session_id,
            )
        else:
            await conn.execute(
                "UPDATE conversation_sessions SET message_count=message_count+1, updated_at=NOW() WHERE id=$1::uuid",
                session_id,
            )
    except Exception as e:
        logger.error(f"Failed to save user message immediately: {e}")

    # ── Step 3: Fire background task to run LLM + save answer ───────────────────
    # The queue streams tokens to the SSE client. The task runs independently —
    # it will finish and persist the answer regardless of whether the client stays.
    token_queue: asyncio.Queue = asyncio.Queue()

    async def llm_background_task():
        """
        Runs in the background. Owns its own DB connection.
        Generates the full LLM answer and saves it to the DB.
        Puts tokens into the queue so the SSE stream can read them live.
        Puts None as a sentinel when done.
        """
        from groq import AsyncGroq
        from core.config import settings

        full_answer: list[str] = []

        try:
            # ── pre_answered path (confirmation gate) ────────────────────────
            if context.get("pre_answered"):
                pre_answer = context.get("pre_answer", "")
                words = pre_answer.split(" ")
                for i, word in enumerate(words):
                    token = word if i == 0 else " " + word
                    await token_queue.put({"token": token, "done": False})
                full_answer.append(pre_answer)

            else:
                # ── Normal LLM streaming path ─────────────────────────────────
                try:
                    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
                    stream = await client.chat.completions.create(
                        model=settings.GROQ_MODEL,
                        messages=context["messages"],
                        temperature=0.7 if context["query_type"] == "chat" else 0.1,
                        max_tokens=2048,
                        stream=True,
                    )

                    async for chunk in stream:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            full_answer.append(delta)
                            await token_queue.put({"token": delta, "done": False})

                except Exception as e:
                    logger.error(f"Background LLM streaming failed: {e}", exc_info=True)
                    err_token = "\n\n[Error generating response]"
                    full_answer.append(err_token)
                    await token_queue.put({"token": err_token, "done": False})

            # ── Save the completed answer with a fresh connection ─────────────
            answer_text = "".join(full_answer)
            if context.get("context_truncated"):
                answer_text += "\n\n*Note: Some documents were excluded due to context limits.*"

            try:
                pool = await get_pool()
                async with pool.acquire() as bg_conn:
                    async with bg_conn.transaction():
                        await set_rls_user(bg_conn, user_id)
                        await bg_conn.execute(
                            """
                            INSERT INTO conversation_messages
                                (session_id, user_id, role, content, sources, query_type)
                            VALUES ($1::uuid, $2::uuid, 'assistant', $3, $4::jsonb, $5)
                            """,
                            session_id, user_id,
                            answer_text,
                            json.dumps(context["sources"]),
                            context["query_type"],
                        )
                        # +1 for the assistant message (user message was +1 above)
                        await bg_conn.execute(
                            "UPDATE conversation_sessions SET message_count=message_count+1, updated_at=NOW() WHERE id=$1::uuid",
                            session_id,
                        )
                        await bg_conn.execute(
                            """
                            INSERT INTO audit_logs (user_id, action, resource_id, details)
                            VALUES ($1::uuid, 'query_run', $2::uuid, $3)
                            """,
                            user_id, session_id,
                            f"Query Type (stream): {context['query_type']}",
                        )
            except Exception as e:
                logger.error(f"Background task failed to save assistant message: {e}", exc_info=True)

        finally:
            # Always signal done, even on exception
            done_payload = {
                "token": "",
                "done": True,
                "sources": context["sources"],
                "query_type": context["query_type"],
                "thinking": context.get("thinking", ""),
                "context_truncated": context.get("context_truncated", False),
                "is_general_knowledge": context.get("is_general_knowledge", False),
            }
            await token_queue.put(done_payload)
            await token_queue.put(None)  # Sentinel: stream is finished

    # Launch background task — independent of the HTTP connection lifecycle
    asyncio.create_task(llm_background_task())

    # ── Step 4: SSE stream reads from queue ──────────────────────────────────────
    async def event_generator():
        try:
            while True:
                item = await token_queue.get()
                if item is None:
                    break  # sentinel: background task finished
                payload = json.dumps(item)
                yield f"data: {payload}\n\n"
        except asyncio.CancelledError:
            # Client disconnected — background task continues and saves the answer
            logger.info(
                f"SSE client disconnected for session {session_id}; "
                "background task continues to generate and save the answer."
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if behind proxy
        },
    )
