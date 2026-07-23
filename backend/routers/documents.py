"""
Documents router — upload, list, detail, rename, delete.
All endpoints require authentication and RLS-scoped DB access.
"""
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel

import asyncpg
from core.auth import get_current_user, get_db_with_rls
from core.config import settings
from services.pipeline import run_document_pipeline

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


class DocumentOut(BaseModel):
    id: str
    filename: str
    original_name: str
    status: str
    mime_type: Optional[str]
    file_size: Optional[int]
    created_at: str
    updated_at: str


class RenameRequest(BaseModel):
    original_name: str


# ── Upload ─────────────────────────────────────────────────────────────

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    # Validate mime type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, JPG, PNG, TIFF, WEBP",
        )

    # Read and validate size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum is 25 MB.")

    # Save to disk
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, stored_filename)
    with open(file_path, "wb") as f:
        f.write(contents)

    # Insert DB record
    doc = await conn.fetchrow(
        """
        INSERT INTO documents (user_id, filename, original_name, file_path, mime_type, file_size, status)
        VALUES ($1, $2, $3, $4, $5, $6, 'pending')
        RETURNING id, filename, original_name, status, mime_type, file_size,
                  created_at::text, updated_at::text
        """,
        user["user_id"],
        stored_filename,
        file.filename,
        file_path,
        file.content_type,
        len(contents),
    )

    doc_id = str(doc["id"])

    # Kick off OCR pipeline in the background
    background_tasks.add_task(
        run_document_pipeline,
        doc_id,
        file_path,
        file.content_type,
        user["user_id"],
    )

    return {
        "id": doc_id,
        "original_name": file.filename,
        "status": "pending",
        "message": "Upload received. Processing started.",
    }


# ── List ───────────────────────────────────────────────────────────────

@router.get("", response_model=List[DocumentOut])
async def list_documents(
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    rows = await conn.fetch(
        """
        SELECT id::text, filename, original_name, status, mime_type, file_size,
               created_at::text, updated_at::text
        FROM documents
        ORDER BY created_at DESC
        """
    )
    return [dict(r) for r in rows]


# ── Detail ─────────────────────────────────────────────────────────────

@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    row = await conn.fetchrow(
        """
        SELECT d.id::text, d.filename, d.original_name, d.status,
               d.mime_type, d.file_size, d.raw_text, d.error_message,
               d.created_at::text, d.updated_at::text,
               ef.amount, ef.currency, ef.txn_date::text,
               ef.vendor, ef.category
        FROM documents d
        LEFT JOIN extracted_fields ef ON ef.document_id = d.id
        WHERE d.id = $1::uuid
        """,
        doc_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


# ── Rename ─────────────────────────────────────────────────────────────

@router.patch("/{doc_id}")
async def rename_document(
    doc_id: str,
    body: RenameRequest,
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    result = await conn.execute(
        "UPDATE documents SET original_name = $1 WHERE id = $2::uuid",
        body.original_name,
        doc_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Renamed successfully"}


# ── Delete ─────────────────────────────────────────────────────────────

@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    # Fetch file path before deleting (for disk cleanup)
    row = await conn.fetchrow(
        "SELECT file_path FROM documents WHERE id = $1::uuid", doc_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    # Cascade deletes chunks + extracted_fields via FK ON DELETE CASCADE
    await conn.execute("DELETE FROM documents WHERE id = $1::uuid", doc_id)

    # Delete file from disk (best effort)
    try:
        if os.path.exists(row["file_path"]):
            os.remove(row["file_path"])
    except OSError:
        pass
