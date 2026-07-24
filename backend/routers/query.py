"""Query router — main /api/query endpoint using the LangGraph agent."""
import asyncpg
import uuid
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from core.rate_limit import limiter

from core.auth import get_current_user, get_db_with_rls
from agents.vault_agent import get_agent

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

    # Verify session belongs to user (RLS handles this, but explicit check is clearer)
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
        "query_type": "lookup",
        "chunks": [],
        "sql_result": None,
        "answer": "",
        "sources": [],
        "context_truncated": False,
    })

    # Audit log
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
