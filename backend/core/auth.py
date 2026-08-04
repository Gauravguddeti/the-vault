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
    3. Starts an explicit transaction (REQUIRED for SET LOCAL to work)
    4. Sets the Postgres RLS variable so all queries are user-scoped
    5. Yields the connection to the route handler
    6. Commits the transaction and releases the connection

    CRITICAL: SET LOCAL only works inside a transaction. Without BEGIN,
    the session variable is not set and RLS sees no user_id, which causes
    cross-account data leaks on pooled connections. This is the root cause
    of the documented cross-account document leak.
    """
    user_id = user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity",
        )

    pool = await get_pool()
    conn = await pool.acquire()
    try:
        # START TRANSACTION — SET LOCAL is scoped to this transaction.
        # When we COMMIT below, the variable is reset, preventing leakage
        # to the next request that reuses this pooled connection.
        async with conn.transaction():
            await set_rls_user(conn, user_id)
            yield conn
    finally:
        await pool.release(conn)
