"""
FastAPI JWT authentication middleware and dependency.

NextAuth signs JWTs with NEXTAUTH_SECRET.
This middleware decodes the token, extracts user_id,
and sets the Postgres RLS variable on every connection.
"""
import base64
import json
import hmac
import hashlib
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import asyncpg
from db.connection import get_pool, set_rls_user
from core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


from jose import jwt, JWTError

def _decode_nextauth_jwt(token: str) -> Optional[dict]:
    """
    Securely decode and verify the JWT signed by the frontend using NEXTAUTH_SECRET.
    """
    try:
        # NextAuth signs using HS256 and the secret
        secret = settings.NEXTAUTH_SECRET
        if not secret:
            return None
            
        payload = jwt.decode(
            token, 
            secret, 
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        return payload
    except JWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """
    FastAPI dependency that:
    1. Extracts the JWT from the Authorization header
    2. Decodes and validates it
    3. Returns the user payload

    Raises 401 if token is missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_nextauth_jwt(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("userId") or payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"user_id": user_id, "email": payload.get("email")}


async def get_db_with_rls(
    user: dict = Depends(get_current_user),
) -> asyncpg.Connection:
    """
    FastAPI dependency that:
    1. Gets an authenticated user (via get_current_user)
    2. Acquires a DB connection from the pool
    3. Sets the Postgres RLS variable so all queries are user-scoped
    4. Yields the connection
    5. Releases it after the request completes

    Usage in a router:
        @router.get("/documents")
        async def list_docs(conn=Depends(get_db_with_rls), user=Depends(get_current_user)):
            ...
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await set_rls_user(conn, user["user_id"])
        yield conn
