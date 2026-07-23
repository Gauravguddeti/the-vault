# The Vault — Full Build Prompt for AI Coding Agent

---

## 1. Project Overview

Build **"The Vault"** — a self-hostable, privacy-first alternative to Google Drive for personal documents (receipts, medical records, warranties, tax documents). Every uploaded file is OCR'd, chunked, embedded, and made queryable in natural language. A user can ask "How much did I spend on laptop repairs last year?" and the system aggregates the answer across multiple invoices, with citations back to source documents — never a hallucinated number.

This is a final-year project. The core research contribution is: **privacy-preserving semantic search in a multi-tenant serverless architecture** — guaranteeing User A's vector search can never retrieve User B's documents, and measuring the performance cost of the isolation mechanism chosen.

---

## 2. Tech Stack (finalized — do not substitute without asking)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js (App Router) + Tailwind CSS | Deployed on **Vercel** |
| Auth | Auth.js (NextAuth) with Credentials + Google OAuth, Neon as the adapter DB | Session-based, JWT |
| Database | **Neon** (serverless Postgres) with `pgvector` extension | Single DB for relational + vector data |
| Backend / workers | **Render** (Node/Express or FastAPI — agent should pick one and justify it) | Handles OCR, embedding generation, and a scheduled **cron job** for reprocessing failed uploads / re-indexing |
| LLM | **Groq API** (Llama 3.3 70B or similar — confirm current best Groq-hosted model) | Used for the RAG answer-generation layer |
| OCR | Advanced OCR parser — evaluate and pick one: Groq/Llama vision model, Mistral OCR API (has a free tier), or Tesseract.js as a free fallback | Must handle scanned receipts/invoices reliably, not just clean text |
| Vector store | `pgvector` inside Neon | No separate vector DB — keeps it one system to secure |
| Multi-tenancy security | Postgres **Row-Level Security (RLS)** scoped by `user_id` on every table including the vectors table | This is the thesis's core mechanism — must be testable/provable |
| Orchestration | LangGraph agent layer on top of retrieval, for multi-step/aggregation queries | Handles queries that need math across multiple retrieved chunks, not just single-hit lookup |

Non-negotiables from the user:
- Mobile-responsive UI (test at 375px width minimum)
- Local testing must pass fully before any deployment step
- No hallucinated answers: if the retrieved context doesn't support an answer, the system must say so explicitly rather than guess

---

## 3. Anti-Hallucination / Context Requirements

The agent must implement these specifically, not just "use RAG":

1. **Grounded answering only** — the LLM prompt must instruct the model to answer *only* from retrieved chunks, and to explicitly respond "I don't have enough information in your documents to answer that" when retrieval confidence is low or chunks are irrelevant.
2. **Citations** — every generated answer must reference which document(s) and chunk(s) it drew from, shown to the user (e.g. "Source: invoice_march2025.pdf").
3. **Aggregation correctness** — for questions requiring sums/counts across documents (e.g. total spend), the agent must extract structured values (amount, date, category) at OCR/parse time into a proper Postgres table — **not** rely on the LLM to "do math" over unstructured chunks. The LLM's job is query understanding and final phrasing; math happens in SQL.
4. **Confidence threshold** — define and document a similarity-score cutoff below which chunks are excluded from context.
5. **Context window management** — cap total tokens sent to Groq per query; if too many chunks match, rank and truncate, and say so if the answer might be incomplete.

---

## 4. Multi-Tenant Security (thesis core)

- Every table (`documents`, `chunks`, `embeddings`, `extracted_fields`) must have a `user_id` column and RLS policies enforcing `user_id = current_setting('app.current_user_id')` or equivalent.
- The agent must write a test suite that specifically tries to leak User B's data into User A's query results, and document the result.
- Benchmark and document the **latency overhead** of RLS-enforced vector queries vs. an unsecured baseline — this becomes a chapter in the thesis, so numbers must be real, not estimated.

---

## 5. Required Development Workflow — 3-File System

To avoid hallucinated scope, unnecessary rewrites, and context drift, the agent must **strictly follow this three-file workflow** and not skip ahead:

### File 1: `create-prd.md`
- Before writing any code, the agent generates a full Product Requirements Document based on everything in this prompt.
- The agent must ask clarifying questions before finalizing it if anything above is ambiguous (e.g. exact OCR provider choice, exact Groq model name/availability).
- Sections required: Overview, Goals, User Stories, Functional Requirements (numbered), Non-Goals, Technical Considerations, Success Metrics, Open Questions.
- The agent stops after producing this file and waits for user approval before proceeding.

### File 2: `generate-tasks.md`
- Only after `create-prd.md` is approved, the agent breaks it into a task list:
  - High-level parent tasks first (e.g. "1.0 Set up Neon schema + RLS", "2.0 Build upload + OCR pipeline", "3.0 Build embedding + retrieval layer", "4.0 Build LangGraph aggregation agent", "5.0 Build auth", "6.0 Build UI", "7.0 Deploy").
  - The agent pauses after listing parent tasks and asks: "Ready to generate sub-tasks?" before expanding each into detailed sub-tasks.
  - Each sub-task must be small enough to implement and verify in one sitting.

### File 3: `process-task-list.md`
- The agent works through **one sub-task at a time only.**
- After completing a sub-task: mark it `[x]` in the file, briefly state what was done and how it was verified (tests run, manual check, etc.), and **stop and wait for user confirmation** ("yes"/"continue"/"go") before starting the next sub-task.
- If a sub-task reveals the plan was wrong, the agent updates `generate-tasks.md` and flags the change explicitly rather than silently deviating.
- No task is marked complete without an actual passing test or explicit manual verification step described.

This file-based checkpointing is mandatory — it is the mechanism for preventing hallucinated "done" claims and unreviewed scope creep.

---

## 6. Deployment Order (only after local testing passes)

1. Fully working locally: Next.js dev server + local/dev Neon branch + Render backend running locally + Groq API calls working end-to-end.
2. Push Neon schema (with RLS policies) to production branch.
3. Deploy backend to Render, including the cron job for reprocessing/re-indexing.
4. Deploy frontend to Vercel, pointed at production Neon + Render backend.
5. Smoke test full flow in production: signup → upload → OCR → query → cited answer.
6. Mobile pass: verify upload flow, chat/query UI, and document list all work at mobile widths.

---

## 7. First Action

Start by producing **`create-prd.md`** only. Ask any clarifying questions you need first (e.g. confirm current best available Groq model, confirm OCR provider choice given free-tier constraints, confirm whether Google OAuth is wanted alongside email/password). Do not write implementation code yet.
