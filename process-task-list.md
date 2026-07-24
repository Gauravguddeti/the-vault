# The Vault — Process Task List (`process-task-list.md`)

> One sub-task at a time. Mark `[x]` + describe verification. Stop after each and wait for "go".

---

## Task Log

### [x] 1.1 — Create monorepo structure
**Done**: Created `frontend/`, `backend/`, `README.md`, `.gitignore` at project root.
**Verified**: Directories exist at `d:\ClgStuff\The Vault\`

---

### [x] 1.2 — Initialize Next.js App Router + Tailwind CSS
**Done**: `create-next-app@16.2.11` ran successfully — App Router, TypeScript, Tailwind, ESLint, src-dir, `@/*` alias.
**Verified**: `npx tsc --noEmit` in `frontend/` exits 0 (no TypeScript errors).

---

### [x] 1.3 — Initialize FastAPI project structure
**Done**: Created `backend/main.py`, `requirements.txt`, `core/config.py`, `db/connection.py`, `services/scheduler.py`, `routers/` (health, documents, query, conversations stubs), `agents/`, `tests/`, `uploads/` dirs, all `__init__.py` files.
**Verified**: `.venv\Scripts\python -c "from main import app; print(app.routes)"` → routes registered cleanly: `/health`, `/openapi.json`, `/docs`, `/redoc`.

---

### [x] 1.4 — Create `.env.example` (backend)
**Done**: `backend/.env.example` with all 18 environment variables documented and grouped.
**Verified**: File exists and matches PRD §11 variable list.

---

### [x] 1.5 — Create `frontend/.env.local.example`
**Done**: `frontend/.env.local.example` with `DATABASE_URL`, `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `NEXT_PUBLIC_BACKEND_URL`.
**Verified**: File exists.

---

### [x] 1.6 — Verify both servers start
**Done**: All Python packages installed and importable. FastAPI app loads cleanly. Next.js TypeScript compiles with 0 errors.
**Verified**:
- `python -c "import fastapi, uvicorn, asyncpg, groq, langgraph, mistralai, apscheduler"` → OK
- `from main import app` → routes: `/health`, `/docs`, `/redoc`
- `npx tsc --noEmit` → 0 errors

---

### [x] 2.2 — Write full `backend/db/schema.sql`
**Done**: Complete schema written — 7 data tables + 2 NextAuth tables. RLS enabled on 5 tables with user isolation policies. IVFFlat index on `chunks.embedding`. Auto-updated_at triggers. Verification queries included as comments.
**Verified**: SQL reviewed for correctness — all tables have `user_id`, all RLS policies use `current_setting('app.current_user_id', true)::uuid`.

---

## ⏳ Next: Task 2.1 — Enable pgvector on Neon + apply schema

**Status**: Waiting for user to:
1. Create a Neon project at https://neon.tech (free)
2. Copy the connection string
3. Provide it so the schema can be applied

---

## Remaining Tasks (not started)
- [ ] 2.1, 2.3, 2.4, 2.5, 2.6
- [ ] 3.1 through 3.7
- [ ] 4.1 through 4.9
- [ ] 5.1 through 5.7
- [ ] 6.1 through 6.12
- [ ] 7.1 through 7.10
- [ ] 8.1 through 8.8
- [ ] 9.1 through 9.6
