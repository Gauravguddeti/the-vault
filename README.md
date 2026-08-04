# The Vault

> Privacy-first personal document vault with semantic search, OCR, and AI-powered Q&A.

A privacy-preserving semantic search system in a multi-tenant serverless architecture using Postgres Row-Level Security.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (App Router) + Tailwind CSS → Vercel |
| Auth | NextAuth v5 (Credentials) + Neon Postgres adapter |
| Database | Neon (serverless Postgres) + pgvector |
| Backend | FastAPI (Python) → Render |
| OCR | Mistral OCR API (primary) + pytesseract (fallback) |
| LLM | Groq API (llama-3.3-70b-versatile) |
| Orchestration | LangGraph (Python) |
| Vector Store | pgvector inside Neon |
| Multi-tenancy | Postgres Row-Level Security (RLS) |
| Rate Limiting | slowapi (per-IP, 10 uploads/min · 20 queries/min) |

---

## Features

### Document Ingestion Pipeline
All uploads — whether via the upload page, in-chat attachment, mobile share-sheet, or camera scan — go through the same pipeline:

```
Upload → OCR (Mistral / tesseract fallback)
       → Structured Field Extraction (amount, date, vendor, category)
       → Chunking + Embedding → pgvector
       → Status: ready
```

- **Confirmation step**: files aren't committed until the user confirms (two-phase upload).
- **Duplicate detection**: server-side check (same vendor + amount + date) before finalising.
- **Offline queue**: files scanned while offline are queued in `localStorage` and auto-processed on reconnect.

### Ask Vault (AI Chat)
A LangGraph agent with four query modes, classified per-message by a fast LLM call:

| Mode | How it works |
|------|-------------|
| `chat` | Conversational reply, no retrieval |
| `lookup` | Semantic search (pgvector cosine similarity) → grounded answer with citations |
| `aggregation` | Intent parsed to JSON (category + date range) → **SQL math** → LLM describes result. No LLM arithmetic. |
| `out_of_scope` | Graceful redirect to what the Vault can help with |

- **Prompt injection defense**: all document content is wrapped in `<document_content>` XML tags with explicit system instructions to treat it as untrusted data.
- **Zero-chunk guard**: if no chunks are retrieved, the agent falls back to the document index (filenames, upload dates, categories) rather than hallucinating.
- **Conversation memory**: per-session history stored in Postgres; old sessions summarised.

### Upload Entry Points
- **Upload page** — standard file picker
- **Chat attach** — attach button / drag-and-drop / clipboard paste inside the chat
- **Share-sheet** (PWA) — share a PDF from any mobile app directly into the Vault
- **Mobile scanner FAB** — multi-page camera scan with offline queue

---

## Security Model

### Database-Level RLS

Every data table has `user_id` + Postgres Row-Level Security with `FORCE ROW LEVEL SECURITY`:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY docs_user_isolation ON documents
  USING (user_id = current_setting('app.current_user_id', true)::uuid);
```

The FastAPI auth middleware sets `app.current_user_id` on every DB connection from the decoded JWT, before any query executes. This makes cross-user data access impossible at the DB layer even if app-layer WHERE clauses were accidentally omitted.

> **Production hardening**: For full enforcement, the FastAPI app should connect with a **low-privilege role** (no `BYPASSRLS`). Run `backend/create_vault_app_role.py` to create the `vault_app` role, then update `DATABASE_URL` to use it.

### Audit Logging

Every document view and chat query is logged to the `audit_logs` table (user_id, action, resource_id, timestamp). Audit logs are RLS-scoped so users can only see their own activity.

### Upload Safety

File types are validated using **magic bytes** (via the `filetype` library) — not the client-supplied `Content-Type` header. An SVG with an embedded `<script>` or a disguised `.exe` renamed to `.pdf` will be rejected.

### Rate Limiting

`slowapi` enforces per-IP limits:
- Upload: **10 requests / minute**
- Query: **20 requests / minute**

### Prompt Injection Defense

All retrieved document chunks are wrapped in `<document_content>` XML tags. The system prompt explicitly instructs the model to treat anything inside those tags as untrusted data and never follow instructions contained within them.

---

## Local Development Setup

### Prerequisites
- Node.js 20+
- Python 3.11+
- Neon account (free tier)
- Groq API key (free tier)
- Mistral API key (free tier)

### 1. Clone and install

```bash
# Frontend
cd frontend
npm install

# Backend
cd ../backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

### 3. Set up Neon database

1. Create a Neon project at [neon.tech](https://neon.tech)
2. Copy the connection string into `DATABASE_URL` in `.env`
3. Run the schema: `psql $DATABASE_URL -f backend/db/schema.sql`
4. (Production) Create low-privilege app role: `python backend/create_vault_app_role.py`

### 4. Run locally

```bash
# Terminal 1 — FastAPI backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2 — Next.js frontend
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## Project Structure

```
the-vault/
├── frontend/           # Next.js App Router + Tailwind
│   ├── app/
│   ├── components/
│   └── lib/
├── backend/            # FastAPI Python
│   ├── main.py
│   ├── routers/
│   │   ├── documents.py       # Upload, confirm, CRUD
│   │   ├── query.py           # LangGraph agent endpoint
│   │   └── conversations.py   # Session CRUD
│   ├── services/
│   │   ├── ocr.py
│   │   ├── embedder.py
│   │   ├── chunker.py
│   │   ├── pipeline.py        # Async ingestion orchestration
│   │   └── field_extractor.py # LLM structured extraction
│   ├── agents/
│   │   └── vault_agent.py     # LangGraph: classify → retrieve/sql → generate
│   ├── core/
│   │   ├── auth.py            # JWT decode + RLS setter
│   │   ├── config.py
│   │   └── rate_limit.py      # slowapi limiter
│   ├── db/
│   │   ├── schema.sql         # Full schema with RLS policies
│   │   └── connection.py
│   └── tests/
│       ├── test_security_rls.py       # RLS policy existence + isolation
│       ├── test_prompt_injection.py   # Injection guard test
│       └── test_aggregation.py        # SQL math accuracy test
├── .env.example
├── .gitignore
└── README.md
```

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

| Test | What it verifies |
|------|-----------------|
| `test_rls_policy_exists` | RLS is enabled on all 6 sensitive tables |
| `test_rls_policies_created` | Named isolation policies exist and use `app.current_user_id` |
| `test_rls_isolation_with_set_role` | Policy WHERE clause correctly scopes by user_id |
| `test_prompt_injection_guard` | Document-embedded injection commands are not executed by the LLM |
| `test_aggregation_formatting` | LLM answer includes the exact SQL total and cites source documents |

---

## Documentation

- [`create-prd.md`](./create-prd.md) — Full Product Requirements Document
- [`generate-tasks.md`](./generate-tasks.md) — Task breakdown
- [`process-task-list.md`](./process-task-list.md) — Implementation progress log
