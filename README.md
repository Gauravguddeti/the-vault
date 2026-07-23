# The Vault

> Privacy-first personal document vault with semantic search, OCR, and AI-powered Q&A.

Research contribution: privacy-preserving semantic search in a multi-tenant serverless architecture using Postgres Row-Level Security.

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

---

## Local Development Setup

### Prerequisites
- Node.js 20+
- Python 3.11+
- [Ollama](https://ollama.ai) with `nomic-embed-text` pulled
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
# Copy and fill in the example files
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

### 3. Set up Neon database

1. Create a Neon project at [neon.tech](https://neon.tech)
2. Copy the connection string into `DATABASE_URL` in `.env`
3. Run the schema: `psql $DATABASE_URL -f backend/db/schema.sql`

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
│   ├── services/
│   │   ├── ocr.py
│   │   ├── embedder.py
│   │   ├── chunker.py
│   │   └── field_extractor.py
│   ├── agents/
│   │   └── vault_agent.py   # LangGraph
│   ├── db/
│   │   ├── schema.sql
│   │   └── connection.py
│   └── tests/
├── .env.example
├── .gitignore
└── README.md
```

---

## Security Model

Every data table has `user_id` + Postgres Row-Level Security:

```sql
CREATE POLICY isolation ON documents
  USING (user_id = current_setting('app.current_user_id')::uuid);
```

The FastAPI middleware sets this setting on every DB connection from the authenticated JWT — making cross-user data access physically impossible at the database layer.

---

## Documentation

- [`create-prd.md`](./create-prd.md) — Full Product Requirements Document
- [`generate-tasks.md`](./generate-tasks.md) — Task breakdown
- [`process-task-list.md`](./process-task-list.md) — Implementation progress log
- [`BENCHMARK.md`](./BENCHMARK.md) — RLS latency benchmark results (populated during testing)
