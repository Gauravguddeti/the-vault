# The Vault — Task List (`generate-tasks.md`)

> **PRD Version**: 1.2 (Approved)
> **Status**: Sub-tasks expanded — implementation in progress via `process-task-list.md`
> **Workflow**: One sub-task at a time; mark `[x]` + verify before next

---

## 1.0 — Project Scaffolding & Repository Setup

- [ ] **1.1** Create monorepo structure: `frontend/` and `backend/` dirs at project root; create `README.md` and root `.gitignore`
- [ ] **1.2** Initialize Next.js App Router + Tailwind CSS in `frontend/` via `create-next-app`
- [ ] **1.3** Initialize FastAPI project in `backend/` — `main.py`, `requirements.txt`, folder structure (`routers/`, `services/`, `db/`, `agents/`, `tests/`)
- [ ] **1.4** Create `.env.example` with all environment variables from PRD §11
- [ ] **1.5** Create `frontend/.env.local.example` for Next.js-specific vars
- [ ] **1.6** Verify: `npm run dev` starts Next.js on :3000; `uvicorn main:app --reload` starts FastAPI on :8000

## 2.0 — Neon Database Schema + Row-Level Security

- [ ] **2.1** Enable `pgvector` extension on Neon dev branch; confirm with `SELECT * FROM pg_extension`
- [ ] **2.2** Write full `backend/db/schema.sql` (all 7 tables: users, documents, chunks, extracted_fields, processing_logs, conversation_sessions, conversation_messages)
- [ ] **2.3** Apply schema to Neon dev branch via psql or Neon console
- [ ] **2.4** Enable RLS + write RLS policies for: `documents`, `chunks`, `extracted_fields`, `conversation_sessions`, `conversation_messages`
- [ ] **2.5** Create IVFFlat index on `chunks.embedding`; create standard indexes on all `user_id` + `document_id` FK columns
- [ ] **2.6** Verify RLS: manually run `SET app.current_user_id = '<uuid-A>'; SELECT * FROM documents;` — assert only User A rows returned; run with User B UUID — assert 0 rows

## 3.0 — Authentication (NextAuth + FastAPI JWT)

- [ ] **3.1** Install NextAuth v5 (Auth.js) + `@auth/pg-adapter` in `frontend/`; configure `auth.config.ts` with Credentials provider
- [ ] **3.2** Create `POST /api/auth/register` route in Next.js — accepts email+password, hashes with bcrypt, inserts into `users` table
- [ ] **3.3** Create NextAuth `[...nextauth]` route handler; configure JWT session strategy + Neon adapter
- [ ] **3.4** Create Login and Register pages in Next.js (functional, no final styling yet)
- [ ] **3.5** Implement FastAPI JWT verification middleware — reads `Authorization: Bearer <token>` header, decodes NextAuth JWT, extracts `user_id`
- [ ] **3.6** FastAPI middleware sets `SET LOCAL app.current_user_id = '<uuid>'` on every DB connection for RLS enforcement
- [ ] **3.7** Verify: register → login → get JWT → call protected FastAPI route → middleware decodes + RLS active

## 4.0 — Document Upload + OCR Pipeline

- [ ] **4.1** Create `POST /api/documents/upload` FastAPI endpoint — accepts multipart file, validates type/size, saves to `UPLOAD_DIR`, inserts `documents` row with `status=pending`, returns `document_id`
- [ ] **4.2** Implement Mistral OCR service (`backend/services/ocr_mistral.py`) — uses `mistralai` Python SDK, calls `mistral-ocr-latest`, returns extracted text
- [ ] **4.3** Implement pytesseract fallback service (`backend/services/ocr_tesseract.py`) — converts PDF pages to images via PyMuPDF at 300 DPI, runs pytesseract, returns concatenated text
- [ ] **4.4** Implement OCR orchestrator (`backend/services/ocr.py`) — tries Mistral first, falls back to tesseract on failure; updates `documents.status` through the pipeline
- [ ] **4.5** Implement Groq structured field extraction (`backend/services/field_extractor.py`) — sends OCR text to Groq with JSON-schema prompt, parses `amount`, `date`, `vendor`, `category`, `currency`; inserts into `extracted_fields`
- [ ] **4.6** Wire full OCR pipeline into FastAPI `BackgroundTasks` — upload returns immediately, background task runs: OCR → extract fields → update status
- [ ] **4.7** Implement APScheduler cron job (every 15 min) — picks up `status=failed` or `status=pending` docs older than 5 min with `retry_count < 3`, retries pipeline
- [ ] **4.8** Implement document management endpoints: `GET /api/documents` (list), `GET /api/documents/{id}` (detail), `PATCH /api/documents/{id}` (rename), `DELETE /api/documents/{id}` (cascade delete)
- [ ] **4.9** Verify: upload a real scanned PDF → wait for background task → check `documents.raw_text` populated + `extracted_fields` row inserted

## 5.0 — Embedding + Vector Retrieval Layer

- [ ] **5.1** Set up Ollama locally + pull `nomic-embed-text` model; verify `POST http://localhost:11434/api/embeddings` returns a 768-dim vector
- [ ] **5.2** Build text chunker (`backend/services/chunker.py`) — splits text into ~500-token chunks with 50-token overlap using `tiktoken`; returns list of `{chunk_index, text, token_count}`
- [ ] **5.3** Build embedding service (`backend/services/embedder.py`) — calls Ollama/OpenAI, returns vector; handles batching
- [ ] **5.4** Wire chunking + embedding into document pipeline (runs after OCR field extraction); inserts all chunks into `chunks` table with `user_id` denormalized
- [ ] **5.5** Build vector search function (`backend/db/vector_search.py`) — executes `SELECT ... ORDER BY embedding <=> $1 LIMIT $2` (RLS automatically filters by user); returns chunks with similarity scores
- [ ] **5.6** Build query endpoint (`POST /api/query/search`) — embeds question, runs vector search, applies similarity threshold, applies token cap, returns ranked chunks + metadata
- [ ] **5.7** Verify: upload doc → chunks in DB → POST `/api/query/search` with relevant question → returns matching chunks with scores above threshold

## 6.0 — LangGraph Agent + Per-User Memory

- [ ] **6.1** Install `langgraph`, `langchain-groq`, `langchain-core`; define `VaultState` TypedDict (query, session_id, history, chunks, sql_result, answer, sources, query_type)
- [ ] **6.2** Implement query classifier node — keyword + semantic rules to label query as `lookup` or `aggregation`
- [ ] **6.3** Implement retrieval node — calls vector search service, assembles context with token cap
- [ ] **6.4** Implement SQL aggregation node — generates + executes safe parameterized SQL against `extracted_fields` (RLS-enforced); returns structured result
- [ ] **6.5** Implement LLM answer node — calls Groq with grounded system prompt; zero-chunk guard (returns no-info message without LLM call if 0 chunks); formats citations
- [ ] **6.6** Wire agent graph: `load_memory → classify → [retrieval | sql_aggregation] → answer → save_memory`
- [ ] **6.7** Build memory loader node — fetches last `MEMORY_WINDOW` messages from `conversation_messages` for the session (RLS-enforced)
- [ ] **6.8** Build memory saver node — inserts user message + assistant answer into `conversation_messages`; updates `conversation_sessions.updated_at`
- [ ] **6.9** Build memory summary job — for sessions with `updated_at` > 7 days ago + message_count > 50, compress via Groq summary prompt, store in `conversation_sessions.summary`
- [ ] **6.10** Build conversation CRUD endpoints: `POST /api/conversations` (new session), `GET /api/conversations` (list), `GET /api/conversations/{id}/messages`, `DELETE /api/conversations/{id}`
- [ ] **6.11** Build main query endpoint `POST /api/query` — accepts `{question, session_id}`, runs LangGraph agent, returns `{answer, sources, query_type}`
- [ ] **6.12** Verify: ask lookup question → cited answer; ask aggregation question → SQL result phrased; ask follow-up → memory context used; zero-match → no-info message returned

## 7.0 — Next.js Frontend (All Pages)

- [ ] **7.1** Set up global design system: Tailwind config, Google Fonts (Inter), CSS variables (colors, radii, shadows), dark mode base
- [ ] **7.2** Build shared components: `Navbar`, `Sidebar` (chat sessions list), `StatusBadge`, `Spinner`, `Button`, `Input`, `Modal`
- [ ] **7.3** Build **Landing / Login page** (`/`) — hero section, email+password form, link to register; connect to NextAuth `signIn`
- [ ] **7.4** Build **Register page** (`/register`) — form → `POST /api/auth/register` → auto-login → redirect to dashboard
- [ ] **7.5** Build **Dashboard page** (`/dashboard`) — document list with filename, date, status badge; real-time status polling (every 3s for pending/processing docs)
- [ ] **7.6** Build **Upload page** (`/upload`) — drag-and-drop zone + click-to-browse; progress bar; calls `POST /api/documents/upload`; redirects to dashboard on success
- [ ] **7.7** Build **Document Detail page** (`/documents/[id]`) — filename, metadata, extracted fields table, raw text preview, delete button
- [ ] **7.8** Build **Chat / Query page** (`/chat`) — left sidebar (session list + new chat button); main area: message history, input box; each answer has collapsible citations panel showing source doc + chunk + score
- [ ] **7.9** Wire all frontend API calls to FastAPI backend via a typed `apiClient` wrapper; handle auth headers, error states, loading states
- [ ] **7.10** Mobile responsiveness pass — test all 6 pages at 375px viewport; fix any layout breaks; verify upload + chat + document list all work on mobile

## 8.0 — Security Test Suite + RLS Benchmark

- [ ] **8.1** Set up pytest fixtures (`backend/tests/conftest.py`) — create two test users (A and B) with documents, chunks, extracted_fields, and conversation history each
- [ ] **8.2** Write + run test: User A JWT → query `documents` → assert 0 of User B's rows returned
- [ ] **8.3** Write + run test: User A JWT → vector search → assert 0 of User B's chunks returned
- [ ] **8.4** Write + run test: User A JWT → query `extracted_fields` → assert 0 of User B's rows returned
- [ ] **8.5** Write + run test: User A JWT → query `conversation_messages` → assert 0 of User B's messages returned
- [ ] **8.6** Write + run test: call query endpoint with User A's session_id but User B's token → assert 401 or 0 results
- [ ] **8.7** Write RLS benchmark script (`backend/tests/benchmark_rls.py`) — runs 100 identical vector queries with RLS on vs. off; records wall-clock time per query
- [ ] **8.8** Run benchmark, compute p50/p95/p99 latency for both conditions; write `BENCHMARK.md` with results table + interpretation

## 9.0 — Deployment

- [ ] **9.1** Push Neon schema + RLS policies to production Neon branch; verify pgvector + all tables present
- [ ] **9.2** Create Render Web Service — connect GitHub repo, set `backend/` as root, set all production env vars
- [ ] **9.3** Verify Render deployment: health check endpoint responds; cron job logs appear
- [ ] **9.4** Create Vercel project — connect GitHub repo, set `frontend/` as root, configure all production env vars
- [ ] **9.5** Smoke test production: signup → upload PDF → wait for OCR → ask question → receive cited answer
- [ ] **9.6** Mobile production pass: verify upload, chat, and document list at 375px

---

## Dependency Map

| Task | Depends On |
|------|------------|
| 1.0 | — |
| 2.0 | 1.0 |
| 3.0 | 1.0, 2.0 |
| 4.0 | 2.0, 3.0 |
| 5.0 | 2.0, 4.0 |
| 6.0 | 2.0, 5.0 |
| 7.0 | 3.0, 4.0, 5.0, 6.0 |
| 8.0 | 2.0, 5.0, 6.0 |
| 9.0 | 7.0, 8.0 |

---
*Implementation tracking in `process-task-list.md`*
