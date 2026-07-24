"""Conversations router — CRUD for chat sessions and messages."""
import asyncpg
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status

from core.auth import get_current_user, get_db_with_rls

router = APIRouter()


class SessionOut(BaseModel):
    id: str
    title: Optional[str]
    message_count: int
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: Optional[list]
    query_type: Optional[str]
    created_at: str


# ── Create session ─────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    row = await conn.fetchrow(
        """
        INSERT INTO conversation_sessions (user_id, title)
        VALUES ($1::uuid, 'New conversation')
        RETURNING id::text, title, message_count,
                  created_at::text, updated_at::text
        """,
        user["user_id"],
    )
    return dict(row)


# ── List sessions ──────────────────────────────────────────────────────

@router.get("", response_model=List[SessionOut])
async def list_sessions(
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    rows = await conn.fetch(
        """
        SELECT id::text, title, message_count, created_at::text, updated_at::text
        FROM conversation_sessions
        ORDER BY updated_at DESC
        LIMIT 50
        """
    )
    return [dict(r) for r in rows]


# ── Get messages for a session ─────────────────────────────────────────

@router.get("/{session_id}/messages", response_model=List[MessageOut])
async def get_messages(
    session_id: str,
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    # RLS ensures only the owner can see these messages
    rows = await conn.fetch(
        """
        SELECT id::text, role, content, sources, query_type, created_at::text
        FROM conversation_messages
        WHERE session_id=$1::uuid
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]


# ── Delete session ─────────────────────────────────────────────────────

@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    result = await conn.execute(
        "DELETE FROM conversation_sessions WHERE id=$1::uuid",
        session_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Session not found")
