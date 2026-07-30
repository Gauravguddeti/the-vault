from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List

from core.auth import get_current_user
from db.connection import get_pool, set_rls_user

router = APIRouter(prefix="/memory", tags=["memory"])

class MemoryItem(BaseModel):
    id: str
    content: str
    category: str
    created_at: str

@router.get("", response_model=List[MemoryItem])
async def get_user_memory(user: dict = Depends(get_current_user)):
    """Fetch all durable memory facts learned about the current user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await set_rls_user(conn, user["user_id"])
        rows = await conn.fetch(
            """
            SELECT id::text, content, category, created_at::text
            FROM user_memory
            ORDER BY created_at DESC
            """
        )
        return [dict(r) for r in rows]

@router.delete("/{memory_id}")
async def delete_user_memory(memory_id: str, user: dict = Depends(get_current_user)):
    """Delete a specific memory item."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await set_rls_user(conn, user["user_id"])
        result = await conn.execute(
            "DELETE FROM user_memory WHERE id=$1::uuid",
            memory_id
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Memory item not found")
        return {"status": "success"}
