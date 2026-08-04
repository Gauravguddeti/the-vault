"""
Documents router — upload, list, detail, rename, delete.
All endpoints require authentication and RLS-scoped DB access.
"""
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, BackgroundTasks, Request
from core.rate_limit import limiter
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


import filetype

# ── Upload ─────────────────────────────────────────────────────────────

@router.post("/upload", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    require_confirmation: bool = False,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    # Read contents first
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum is 25 MB.")
        
    # Strictly validate mime type using magic bytes
    kind = filetype.guess(contents)
    actual_mime = kind.mime if kind else None
    
    if actual_mime not in ALLOWED_MIME_TYPES:
        # Some plain text formats like simple CSVs might not be detected by filetype,
        # but our ALLOWED_MIME_TYPES are all binary (PDF, JPG, PNG, TIFF, WEBP).
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type detected. Allowed: PDF, JPG, PNG, TIFF, WEBP",
        )

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
        require_confirmation,
    )

    return {
        "id": doc_id,
        "original_name": file.filename,
        "status": "pending",
        "message": "Upload received. Processing started.",
    }


# ── Confirm ────────────────────────────────────────────────────────────

class ConfirmFields(BaseModel):
    category: Optional[str] = None
    vendor: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[float] = None
    title: Optional[str] = None

@router.post("/{doc_id}/confirm")
async def confirm_document(
    doc_id: str,
    fields: ConfirmFields,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    # Verify document exists and belongs to user
    doc = await conn.fetchrow("SELECT id FROM documents WHERE id = $1::uuid", doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # If title is provided, update original_name
    if fields.title:
        await conn.execute("UPDATE documents SET original_name = $1 WHERE id = $2::uuid", fields.title, doc_id)

    # Parse date
    txn_date = None
    if fields.date:
        from datetime import datetime
        try:
            txn_date = datetime.strptime(fields.date, "%Y-%m-%d").date()
        except ValueError:
            pass

    # ── Duplicate detection ─────────────────────────────────────────
    duplicate_warning = None
    if fields.vendor and txn_date and fields.amount:
        dup = await conn.fetchrow(
            """
            SELECT d.id::text, d.original_name
            FROM documents d
            JOIN extracted_fields ef ON ef.document_id = d.id
            WHERE d.status = 'ready'
              AND ef.vendor ILIKE $1
              AND ef.txn_date = $2
              AND ef.amount = $3
              AND d.id != $4::uuid
            LIMIT 1
            """,
            f"%{fields.vendor}%", txn_date, fields.amount, doc_id
        )
        if dup:
            duplicate_warning = f"Possible duplicate of '{dup['original_name']}' (same vendor, amount, and date)."

    # Update extracted_fields
    await conn.execute(
        """
        UPDATE extracted_fields 
        SET category = $1, vendor = $2, txn_date = $3, amount = $4
        WHERE document_id = $5::uuid
        """,
        fields.category, fields.vendor, txn_date, fields.amount, doc_id
    )

    # Set status to embedding and trigger the rest of the pipeline
    await conn.execute("UPDATE documents SET status = 'embedding' WHERE id = $1::uuid", doc_id)
    
    from services.pipeline import run_chunking_pipeline
    background_tasks.add_task(run_chunking_pipeline, doc_id, user["user_id"])

    return {"message": "Confirmed and processing resumed.", "duplicate_warning": duplicate_warning}


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


# ── Suggestions ────────────────────────────────────────────────────────

@router.get("/suggestions")
async def get_suggestions(
    conn: asyncpg.Connection = Depends(get_db_with_rls),
):
    """
    Returns 3 prompt chip suggestions tailored to the user's actual vault contents.
    Categories: resume → resume-flavored; receipt/invoice → spend-flavored;
    mixed → one of each; empty → upload-oriented.
    """
    rows = await conn.fetch(
        """
        SELECT d.original_name, ef.category, ef.vendor
        FROM documents d
        LEFT JOIN extracted_fields ef ON ef.document_id = d.id
        WHERE d.status = 'ready'
        ORDER BY d.created_at DESC
        LIMIT 20
        """
    )

    if not rows:
        return {
            "suggestions": [
                "Upload a receipt or bill to get started",
                "Drop a PDF and ask questions about it",
                "Add a document to your Vault",
            ]
        }

    # Tally categories
    category_counts: dict[str, int] = {}
    names = []
    for r in rows:
        cat = (r["category"] or "other").lower()
        category_counts[cat] = category_counts.get(cat, 0) + 1
        names.append(r["original_name"])

    total = len(rows)
    resume_cats = {"resume", "cv", "other"}
    spend_cats = {"receipt", "invoice", "bill", "medical", "food", "transport",
                  "utilities", "electronics", "clothing", "repairs", "insurance",
                  "taxes", "rent"}

    resume_count = sum(v for k, v in category_counts.items() if k in resume_cats)
    spend_count = sum(v for k, v in category_counts.items() if k in spend_cats)

    first_name = names[0] if names else "your document"
    second_name = names[1] if len(names) > 1 else None

    resume_suggestions = [
        "Summarize my work experience",
        "What's my most recent job or role?",
        "What skills are listed in my resume?",
        f"Give me an overview of {first_name}",
        "What's my educational background?",
    ]
    spend_suggestions = [
        "How much did I spend last month?",
        f"What's the total amount in {first_name}?",
        "Which category did I spend the most on?",
        "List my most recent receipts",
        "What was my biggest single expense?",
    ]
    mixed_suggestions = [
        f"Summarize {first_name}",
        "How much have I spent in total?",
        f"What's in {second_name}?" if second_name else "List all my documents",
    ]

    if resume_count / total >= 0.7:
        picks = resume_suggestions[:3]
    elif spend_count / total >= 0.7:
        picks = spend_suggestions[:3]
    else:
        picks = mixed_suggestions[:3]

    return {"suggestions": picks}


# ── Detail ─────────────────────────────────────────────────────────────

@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    user: dict = Depends(get_current_user),
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
        
    # Audit log
    await conn.execute(
        """
        INSERT INTO audit_logs (user_id, action, resource_id, details)
        VALUES ($1::uuid, 'document_viewed', $2::uuid, 'Viewed via detail route')
        """,
        user["user_id"], doc_id
    )
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
