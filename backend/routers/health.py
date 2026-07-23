"""Health check router."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "the-vault-api"}
