# The Vault — Product Requirements Document (`create-prd.md`)

> **Status**: ✅ APPROVED — PROCEEDING TO generate-tasks.md  
> **Version**: 1.2 (OCR updated: Mistral OCR API as primary — Unlimited-OCR dropped, incompatible with cloud)  
> **Date**: 2026-07-23  
> **Author**: AI Coding Agent (per `sovereign-drive-agent-prompt.md`)

---

## 1. Overview

**The Vault** is a self-hostable, privacy-first personal document management system — a focused alternative to Google Drive for sensitive personal documents (receipts, medical records, warranties, tax documents, invoices). Every uploaded file is processed through an OCR pipeline, semantically chunked, embedded into a vector store, and made queryable in natural language. Users can ask questions like *"How much did I spend on laptop repairs last year?"* and receive grounded, cited, aggregated answers — never hallucinated numbers.

**Core Research Contribution (Thesis):**  
Privacy-preserving semantic search in a multi-tenant serverless architecture — guaranteeing User A's vector search can never retrieve User B's documents, and benchmarking the latency overhead of Postgres Row-Level Security (RLS) as the isolation mechanism.

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | Users can upload PDF/image documents and have them automatically OCR'd, parsed, and indexed |
| G2 | Users can query their documents in natural language and receive grounded, cited answers |
| G3 | Aggregation queries (sums, counts across documents) are answered using SQL math, not LLM guessing |
| G4 | Multi-tenant isolation is enforced at the database layer via Postgres RLS — provably tested |
| G5 | The system is self-hostable with a clear local-first development workflow |
| G6 | The UI is fully mobile-responsive (minimum 375px width) |
| G7 | The performance cost of RLS-enforced vector queries is benchmarked and documented for the thesis |

---

## 3. User Stories

| ID | As a... | I want to... | So that... |
|----|---------|--------------|------------|
| US-01 | User | Sign up with email and password | I can create a private account |
| US-02 | User | Log in and log out securely | My session is protected |
| US-03 | User | Upload a PDF, image (JPG/PNG), or scanned receipt | It gets indexed and searchable |
| US-04 | User | See the processing status of my uploaded document | I know when it's ready to query |
| US-05 | User | Ask a natural-language question about my documents | I get a specific, cited answer |
| US-06 | User | Get a "not enough information" response when no relevant docs exist | I'm never misled by hallucinated answers |
| US-07 | User | See which document(s) and which chunk(s) an answer came from | I can verify the source |
| US-08 | User | Ask aggregation questions ("total spend on X") | I get a correct SQL-computed number, not an LLM guess |
| US-09 | User | View, rename, and delete my documents | I can manage my vault |
| US-10 | User | Access all features on my phone | The UI works well at mobile widths |
| US-11 | User | Have the AI remember what I asked earlier in a chat session | I can ask follow-up questions naturally |
| US-12 | User | Have the AI recall past conversations I had weeks ago | I don't have to repeat context every session |

---

## 4. Functional Requirements

### 4.1 Authentication & Account Management

- **FR-AUTH-01**: Users can register with email + password (hashed with bcrypt).
- **FR-AUTH-02**: Users can log in and receive a JWT session (Auth.js / NextAuth Credentials provider).
- **FR-AUTH-03**: Neon Postgres is used as the NextAuth adapter database.
- **FR-AUTH-04**: Sessions are JWT-based; tokens are short-lived (24h access, 7d refresh).
- **FR-AUTH-05**: No Google OAuth in v1 (deferred per user decision).
- **FR-AUTH-06**: All API routes require a valid session; unauthenticated requests return 401.

### 4.2 Document Upload & Management

- **FR-UPLOAD-01**: Users can upload files (PDF, JPG, PNG, TIFF) up to 25 MB per file.
- **FR-UPLOAD-02**: On upload, a record is inserted into the `documents` table with status `pending`.
- **FR-UPLOAD-03**: The file is stored in a configurable location (local disk for dev, Render persistent disk for prod).
- **FR-UPLOAD-04**: Users can view a list of all their documents with processing status.
- **FR-UPLOAD-05**: Users can delete a document (cascades to chunks, embeddings, extracted_fields).
- **FR-UPLOAD-06**: Users can rename a document.
- **FR-UPLOAD-07**: Processing status values: `pending`, `ocr_processing`, `embedding`, `ready`, `failed`.

### 4.3 OCR Pipeline

> **OCR Decision (v1.2):** Unlimited-OCR requires 16–24 GB GPU VRAM and cannot run on any cloud free tier (Render free = 512 MB RAM, 0 GPU). Dropped. **Mistral OCR API** is the primary — it is a cloud REST API specifically trained on documents/receipts, handles scanned PDFs natively (no image conversion needed), and has a free tier. pytesseract is the CPU fallback.

- **FR-OCR-01**: Primary OCR engine: **Mistral OCR API** (`mistral-ocr-latest`) — cloud REST API, handles PDFs and images natively, optimized for scanned receipts and invoices. Free experiment tier (~1 req/sec). Requires `MISTRAL_API_KEY`.
- **FR-OCR-02**: Fallback OCR: **pytesseract** (CPU-based, runs on any cloud instance, zero cost) — used when Mistral API fails or rate-limits. Requires PyMuPDF to convert PDFs to images first.
- **FR-OCR-03**: The OCR pipeline detects file type: PDFs sent directly to Mistral OCR API (it handles them natively); images (JPG/PNG) also sent directly. pytesseract fallback converts PDFs via PyMuPDF at 300 DPI.
- **FR-OCR-04**: Extracted raw text stored in `documents.raw_text`.
- **FR-OCR-05**: All OCR work runs asynchronously in a FastAPI `BackgroundTasks` task — upload returns immediately with `status: pending`.
- **FR-OCR-06**: If all OCR methods fail, `documents.status = 'failed'`, error logged to `processing_logs`.

### 4.4 Structured Field Extraction

- **FR-EXTRACT-01**: After OCR, a structured extraction pass identifies and stores: `amount`, `date`, `vendor`, `category`, `currency` where present.
- **FR-EXTRACT-02**: Extracted fields are stored in the `extracted_fields` table, linked by `document_id` and scoped by `user_id`.
- **FR-EXTRACT-03**: Extraction uses Groq (Llama) with a strict JSON-output prompt, with regex as a fallback for common patterns.
- **FR-EXTRACT-04**: The `amount` field is stored as `NUMERIC` to enable SQL aggregation.

### 4.5 Chunking & Embedding

- **FR-EMBED-01**: OCR'd text is split into overlapping chunks (~500 tokens, 50-token overlap) using a character/token splitter.
- **FR-EMBED-02**: Each chunk is embedded using `nomic-embed-text` (via Ollama locally) or `text-embedding-3-small` (OpenAI), selected via env var.
- **FR-EMBED-03**: Embeddings stored in the `chunks` table with a `pgvector` `embedding vector(1536)` column (dimension adjustable via `EMBEDDING_DIM`).
- **FR-EMBED-04**: Each chunk row includes: `id`, `document_id`, `user_id`, `chunk_index`, `text`, `token_count`, `embedding`.
- **FR-EMBED-05**: `user_id` is denormalized onto every chunk row — required for efficient RLS.

### 4.6 Retrieval & RAG Query

- **FR-QUERY-01**: User submits a natural-language question via the frontend chat UI.
- **FR-QUERY-02**: The question is embedded using the same model as the documents.
- **FR-QUERY-03**: Cosine similarity search via `pgvector` (`<=>`) on `chunks`, filtered automatically by RLS (`user_id`).
- **FR-QUERY-04**: **Similarity threshold**: Chunks with similarity score below `0.72` (env: `MIN_SIMILARITY_SCORE`) are excluded.
- **FR-QUERY-05**: Maximum `8` top chunks passed to the LLM (env: `MAX_CHUNKS`).
- **FR-QUERY-06**: **Token cap**: Total tokens to Groq capped at `6000` (env: `MAX_CONTEXT_TOKENS`). Truncation disclosed to user.
- **FR-QUERY-07**: Zero chunks above threshold → return "I don't have enough information" without calling LLM.
- **FR-QUERY-08**: Every answer includes `sources[]`: document name, chunk index, similarity score.

### 4.7 LangGraph Aggregation Agent

- **FR-LANG-01**: Uses **LangGraph Python** to orchestrate multi-step retrieval and query routing.
- **FR-LANG-02**: Classifies queries as:
  - **Lookup**: answered by vector retrieval + LLM.
  - **Aggregation**: keywords "total", "sum", "how much", "all", "count" → SQL on `extracted_fields`.
- **FR-LANG-03**: For aggregation, agent generates SQL, executes against Neon (RLS-enforced), passes numeric result to LLM for phrasing only.
- **FR-LANG-04**: System prompt mandates grounded answers only.
- **FR-LANG-05**: Maximum `5` agent steps before termination with partial answer.

### 4.8 LLM (Groq)

- **FR-LLM-01**: Groq API, model configurable via `GROQ_MODEL` env var; default `llama-3.3-70b-versatile`.
- **FR-LLM-02**: Temperature `0.0` for all factual queries.
- **FR-LLM-03**: System prompt enforces grounded answering and required citation format.
- **FR-LLM-04**: `GROQ_API_KEY` stored as environment variable — never hardcoded.

### 4.9 Multi-Tenant Security (Thesis Core)

- **FR-SEC-01**: Every data table has a `user_id UUID NOT NULL` column.
- **FR-SEC-02**: Postgres RLS enabled on: `documents`, `chunks`, `extracted_fields`.
- **FR-SEC-03**: RLS policy: `USING (user_id = current_setting('app.current_user_id')::uuid)`.
- **FR-SEC-04**: FastAPI middleware sets `SET app.current_user_id = '<uuid>'` on every DB connection from the authenticated JWT.
- **FR-SEC-05**: `pgvector` `<=>` search inherits RLS — physically cannot return cross-user rows.
- **FR-SEC-06**: Security test suite (pytest): cross-user data leak tests → must return 0 rows in all cases.
- **FR-SEC-07**: Benchmark: 100× vector queries with/without RLS → p50/p95/p99 latency documented.

### 4.10 Cron Job

- **FR-CRON-01**: Runs on Render every 15 minutes via APScheduler (in-process) or Render Cron Job.
- **FR-CRON-02**: Picks up `status = 'failed'` or `status = 'pending'` documents older than 5 minutes and retries.
- **FR-CRON-03**: Max `retry_count = 3` per document to prevent infinite loops.
- **FR-CRON-04**: Cron events logged to `processing_logs` table.

### 4.11 Frontend (Next.js App Router + Tailwind CSS)

- **FR-UI-01**: Pages: Landing/Login, Register, Dashboard (doc list), Upload, Document Detail, Chat/Query.
- **FR-UI-02**: Mobile-responsive at ≥ 375px using Tailwind responsive utilities.
- **FR-UI-03**: Drag-and-drop upload zone with progress bar.
- **FR-UI-04**: Chat UI: question input, answer display, collapsible citations panel.
- **FR-UI-05**: Document list: filename, date, status badge (with spinner for in-progress).
- **FR-UI-06**: All interactive elements have unique `id` attributes.

### 4.12 Per-User AI Memory

- **FR-MEM-01**: Each user has isolated conversation memory — User A's history is physically inaccessible to User B (enforced by RLS on `conversation_sessions` and `conversation_messages` tables).
- **FR-MEM-02**: **In-session context**: LangGraph passes the last `N` messages (default `N=10`, env: `MEMORY_WINDOW`) from the current session as conversation history in the LLM prompt. This enables natural follow-up questions ("what was the total?" after asking about dentist receipts).
- **FR-MEM-03**: **Persistent memory**: Conversations are stored in Postgres (`conversation_sessions`, `conversation_messages` tables) and persist across browser sessions indefinitely. Users can start a new session or continue an existing one.
- **FR-MEM-04**: Each `conversation_messages` row stores: `role` (user/assistant), `content`, `sources` (JSONB citations), `query_type` (lookup/aggregation), `created_at`.
- **FR-MEM-05**: The frontend shows a sidebar list of past conversation sessions (title + date). Users can click to resume any past session.
- **FR-MEM-06**: LangGraph uses the conversation history to resolve **pronoun and context references** — e.g., "what about last month?" resolves relative to the prior question's time filter.
- **FR-MEM-07**: Memory tables have RLS policies identical to data tables: `USING (user_id = current_setting('app.current_user_id')::uuid)`.
- **FR-MEM-08**: Users can delete individual sessions or clear all memory. Deletion cascades to all messages in the session.
- **FR-MEM-09**: A **memory summary** is generated for sessions older than 7 days — the last 50 messages are compressed into a ~200-token summary stored in `conversation_sessions.summary`. This keeps the context window manageable for long-term users.

---

## 5. Non-Goals (v1)

- ❌ Google OAuth
- ❌ Document sharing between users
- ❌ Full-text keyword search
- ❌ Document versioning
- ❌ In-browser PDF preview
- ❌ Email notifications
- ❌ Multi-file batch upload
- ❌ Fine-tuning any model
- ❌ Unlimited-OCR (requires 16–24 GB GPU VRAM — incompatible with cloud; Mistral OCR used instead)
- ❌ Cross-user memory sharing (each user's memory is strictly isolated by RLS)

---

## 6. Technical Decisions

### 6.1 Backend: FastAPI (Python)
Unlimited-OCR (transformers), LangGraph, and all ML libraries are Python-first. Keeping the entire backend in Python eliminates cross-language complexity.

### 6.2 LangGraph: Python
Same backend, more community examples, native LangGraph support. No JS translation layer.

### 6.3 OCR Provider Chain

**Final decision: Mistral OCR API (primary) + pytesseract (fallback)**

Unlimited-OCR was evaluated and rejected for cloud deployment: it requires 16–24 GB GPU VRAM. Render's free tier offers 512 MB RAM and zero GPU — the model would OOM-crash on startup.

| Priority | Engine | Mode | Cost | Cloud-ready? |
|----------|--------|------|------|-------------|
| 1 | Mistral OCR API (`mistral-ocr-latest`) | Cloud REST API | Free tier | ✅ Yes |
| 2 | pytesseract | In-process, CPU | Free | ✅ Yes |

**What the user needs to do:**
1. Get a free Mistral API key at [console.mistral.ai](https://console.mistral.ai)
2. Set `MISTRAL_API_KEY=<key>` in `.env`
3. Everything else is handled by the agent.

### 6.4 Groq Model
`llama-3.3-70b-versatile` as default. Configurable via `GROQ_MODEL`. Check GroqCloud console at deploy time.

### 6.5 Embedding
`nomic-embed-text` via Ollama (free, local) as default. OpenAI `text-embedding-3-small` as alternative. `EMBEDDING_DIM` env var must match model output dimension.

---

## 7. Database Schema (Conceptual)

```sql
-- RLS on ALL data tables
-- user_id on every row (denormalized for RLS efficiency)

-- Core Auth
TABLE users (
  id UUID PK,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT,
  created_at TIMESTAMPTZ
)

-- Documents
TABLE documents (
  id UUID PK,
  user_id UUID NOT NULL,  -- RLS
  filename TEXT,
  original_name TEXT,
  file_path TEXT,
  status TEXT,  -- pending | ocr_processing | embedding | ready | failed
  raw_text TEXT,
  retry_count INT DEFAULT 0,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)

-- Chunks + Vector Embeddings
TABLE chunks (
  id UUID PK,
  document_id UUID FK,
  user_id UUID NOT NULL,  -- RLS (denormalized)
  chunk_index INT,
  text TEXT,
  token_count INT,
  embedding vector(768),  -- dim matches EMBEDDING_MODEL
  created_at TIMESTAMPTZ
)
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops);

-- Structured Fields for SQL Aggregation
TABLE extracted_fields (
  id UUID PK,
  document_id UUID FK,
  user_id UUID NOT NULL,  -- RLS
  amount NUMERIC,
  currency TEXT,
  date DATE,
  vendor TEXT,
  category TEXT,
  raw_json JSONB,
  created_at TIMESTAMPTZ
)

-- OCR/Processing Logs (no RLS — admin/cron visibility)
TABLE processing_logs (
  id UUID PK,
  document_id UUID FK,
  event TEXT,
  detail TEXT,
  created_at TIMESTAMPTZ
)

-- ── Per-User AI Memory ──────────────────────────────────────

-- Conversation Sessions (one per chat thread)
TABLE conversation_sessions (
  id UUID PK,
  user_id UUID NOT NULL,  -- RLS
  title TEXT,             -- auto-generated from first question
  summary TEXT,           -- compressed summary of old messages (after 7 days)
  message_count INT DEFAULT 0,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)

-- Per-Message History
TABLE conversation_messages (
  id UUID PK,
  session_id UUID FK → conversation_sessions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,  -- RLS (denormalized for fast isolation)
  role TEXT NOT NULL,     -- 'user' | 'assistant'
  content TEXT NOT NULL,
  sources JSONB,          -- [{document_name, chunk_index, similarity_score}]
  query_type TEXT,        -- 'lookup' | 'aggregation' | 'chitchat'
  created_at TIMESTAMPTZ
)

-- RLS Policies (same pattern for all data tables):
-- ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY isolation ON <table>
--   USING (user_id = current_setting('app.current_user_id')::uuid);
-- Tables with RLS: documents, chunks, extracted_fields,
--                  conversation_sessions, conversation_messages
```

---

## 8. Success Metrics

| Metric | Target |
|--------|--------|
| OCR accuracy (printed) | ≥ 95% char accuracy |
| Query response time | < 5 seconds |
| Cross-tenant leak test | 0 rows returned |
| Aggregation correctness | 100% (SQL-computed) |
| Mobile usability | All flows at 375px |
| RLS latency overhead | Measured & documented |

---

## 9. Anti-Hallucination Contract

1. **Grounded only** — LLM system prompt forbids inference beyond context
2. **Citations mandatory** — every answer has `sources[]`; no sources = no LLM call
3. **SQL for math** — aggregations computed in SQL, LLM only rephrases
4. **Similarity cutoff** — `MIN_SIMILARITY_SCORE = 0.72`
5. **Context cap** — `MAX_CONTEXT_TOKENS = 6000` with disclosure on truncation

---

## 10. Open Questions (All Resolved)

| # | Question | Resolution |
|---|----------|------------|
| OQ-01 | OCR provider? | Unlimited-OCR → Mistral → Tesseract |
| OQ-02 | Google OAuth? | No (email/password only) |
| OQ-03 | Backend? | FastAPI (Python) |
| OQ-04 | LangGraph JS or Python? | Python |
| OQ-05 | Groq model? | `llama-3.3-70b-versatile` (configurable) |
| OQ-06 | Embedding model? | `nomic-embed-text` via Ollama (default) |
| OQ-07 | Unlimited-OCR on cloud? | ❌ Not viable — needs 16–24 GB GPU, Render has 0 GPU. **Replaced with Mistral OCR API** (free tier, cloud-native, excellent on receipts). |
| OQ-08 | AI memory scope? | Both: in-session context window (last 10 msgs) + persistent DB memory across sessions, RLS-isolated per user |

---

## 11. Full Environment Variables

```env
# Database
DATABASE_URL=postgresql://...neon.tech/vault?sslmode=require

# Auth (Next.js)
NEXTAUTH_SECRET=<generate with: openssl rand -base64 32>
NEXTAUTH_URL=http://localhost:3000

# Groq LLM
GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=llama-3.3-70b-versatile

# OCR (Mistral OCR API is primary; pytesseract is CPU fallback)
OCR_PROVIDER=mistral               # mistral | tesseract
MISTRAL_API_KEY=<your-mistral-api-key>

# Embedding
EMBEDDING_PROVIDER=ollama          # ollama | openai
OLLAMA_ENDPOINT=http://localhost:11434
OPENAI_API_KEY=<only-if-using-openai>
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768                  # 768 for nomic, 1536 for openai

# Query Tuning
MIN_SIMILARITY_SCORE=0.72
MAX_CHUNKS=8
MAX_CONTEXT_TOKENS=6000

# AI Memory
MEMORY_WINDOW=10               # number of past messages to include as context
MEMORY_SUMMARY_AFTER_DAYS=7   # compress sessions older than this into summary

# File Storage
UPLOAD_DIR=./uploads

# Backend URL (used by Next.js to call FastAPI)
BACKEND_URL=http://localhost:8000
```

---

## 12. Deployment Order

1. ✅ Fully working locally (end-to-end)
2. Push Neon schema (with RLS) to production branch
3. Deploy FastAPI backend + cron to Render
4. Deploy Next.js frontend to Vercel
5. Smoke test in production
6. Mobile verification pass

---

## 13. How Unlimited-OCR Works in This System

```
User uploads receipt.pdf
         ↓
FastAPI BackgroundTask starts
         ↓
PyMuPDF (fitz) converts each page → PNG at 300 DPI
         ↓
Unlimited-OCR model (already loaded in GPU memory) runs:
  - Single page  → model.infer(...)   [gundam config]
  - Multi-page   → model.infer_multi(...) [base config]
         ↓
Raw text returned per page, concatenated → documents.raw_text
         ↓
Groq (Llama) extracts: amount, date, vendor, category → extracted_fields
         ↓
Text chunked (500 tokens, 50 overlap) → embedded → chunks.embedding
         ↓
documents.status = 'ready'
```

**What you (the user) do:**
1. `pip install torch transformers pymupdf pillow einops addict easydict`
2. Set `.env`: `OCR_PROVIDER=unlimited_ocr`
3. First document upload triggers auto-download of `baidu/Unlimited-OCR` (~15–30 GB)
4. Subsequent uploads are fast (model stays loaded in GPU memory)

---

## 14. How Per-User AI Memory Works

```
User opens Chat → selects/creates a Session
         ↓
User types: "What did I spend on the dentist last year?"
         ↓
LangGraph:
  1. Loads last 10 messages from conversation_messages (RLS-filtered)
  2. Classifies query → aggregation (has "spend", "last year")
  3. Runs SQL on extracted_fields WHERE user_id=<me> AND category='dental'
  4. Passes SQL result + history to Groq → answer
  5. Saves question + answer to conversation_messages (user_id=<me>)

User types: "What about the month before?"
         ↓
LangGraph:
  1. Loads history — sees previous question was about dental spend last year
  2. Resolves "month before" relative to previous date filter
  3. Runs SQL with adjusted date range
  4. Saves new Q+A to conversation_messages

User B logs in → sees ZERO of User A's sessions or messages (RLS)
```

**Memory isolation guarantee:** Identical RLS policy to documents —
`USING (user_id = current_setting('app.current_user_id')::uuid)` —
making cross-user memory access as provably impossible as cross-user document access.
This becomes an additional thesis data point.

---

*This PRD (v1.1) is complete and awaiting user approval. Upon approval, `generate-tasks.md` will be produced.*
