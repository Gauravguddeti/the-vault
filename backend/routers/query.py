"""Query router — /api/query (JSON) + /api/query/stream (SSE streaming)."""
import asyncpg
import json
import logging
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from core.rate_limit import limiter

from core.auth import get_current_user, get_db_with_rls
from agents.vault_agent import get_agent, build_streaming_context

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
    SSE streaming endpoint. Runs retrieval/classification via LangGraph,
    then streams the final LLM answer token-by-token using Groq's streaming API.

    SSE format:
      data: {"token": "word", "done": false}
      data: {"token": "", "done": true, "sources": [...], "query_type": "...", "context_truncated": false}
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session = await conn.fetchrow(
        "SELECT id FROM conversation_sessions WHERE id=$1::uuid",
        body.session_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found")

    # Run retrieval / classification (everything except final LLM answer generation)
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

    async def event_generator():
        from groq import AsyncGroq
        from core.config import settings

        full_answer = []

        # ── Part 2: pre_answered path (confirmation prompt) ───────────────
        # The gate already produced a static message — stream it word-by-word
        # without an LLM call so the UI experience is identical to a normal reply.
        if context.get("pre_answered"):
            pre_answer = context.get("pre_answer", "")
            words = pre_answer.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                payload = json.dumps({"token": token, "done": False})
                yield f"data: {payload}\n\n"
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
                        payload = json.dumps({"token": delta, "done": False})
                        yield f"data: {payload}\n\n"

            except Exception as e:
                logger.error(f"Streaming LLM call failed: {e}", exc_info=True)
                err_payload = json.dumps({"token": "\n\n[Error generating response]", "done": False})
                yield f"data: {err_payload}\n\n"

        # Save the complete answer to the DB
        answer_text = "".join(full_answer)
        if context.get("context_truncated"):
            answer_text += "\n\n*Note: Some documents were excluded due to context limits.*"

        try:
            await conn.execute(
                """
                INSERT INTO conversation_messages (session_id, user_id, role, content)
                VALUES ($1::uuid, $2::uuid, 'user', $3)
                """,
                body.session_id, user["user_id"], body.question,
            )
            await conn.execute(
                """
                INSERT INTO conversation_messages
                    (session_id, user_id, role, content, sources, query_type)
                VALUES ($1::uuid, $2::uuid, 'assistant', $3, $4::jsonb, $5)
                """,
                body.session_id, user["user_id"],
                answer_text,
                json.dumps(context["sources"]),
                context["query_type"],
            )
            # Update session message count / title
            if not context.get("has_history"):
                short_title = body.question[:60]
                await conn.execute(
                    "UPDATE conversation_sessions SET title=$1, message_count=message_count+2, updated_at=NOW() WHERE id=$2::uuid",
                    short_title, body.session_id,
                )
            else:
                await conn.execute(
                    "UPDATE conversation_sessions SET message_count=message_count+2, updated_at=NOW() WHERE id=$1::uuid",
                    body.session_id,
                )
        except Exception as e:
            logger.error(f"Failed to save streamed memory: {e}")

        await conn.execute(
            """
            INSERT INTO audit_logs (user_id, action, resource_id, details)
            VALUES ($1::uuid, 'query_run', $2::uuid, $3)
            """,
            user["user_id"], body.session_id, f"Query Type (stream): {context['query_type']}"
        )

        # Final done event with metadata
        done_payload = json.dumps({
            "token": "",
            "done": True,
            "sources": context["sources"],
            "query_type": context["query_type"],
            "thinking": context.get("thinking", ""),
            "context_truncated": context.get("context_truncated", False),
            "is_general_knowledge": context.get("is_general_knowledge", False),
        })
        yield f"data: {done_payload}\n\n"


    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if behind proxy
        },
    )
