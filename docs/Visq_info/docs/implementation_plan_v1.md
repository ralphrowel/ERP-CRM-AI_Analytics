# End-to-End Upgrade Plan — AI Data Analyst Agent

Based on the System Change Proposal, Tokenization Notes, and the new IDE-style multi-chat workspace requirement. Every step is self-contained so the application remains functional end-to-end at every phase.

---

## Current Progress Overview

| Step   | Feature                         | Status       | Description                                                                                          |
|--------|---------------------------------|--------------|------------------------------------------------------------------------------------------------------|
| Step 1 | Token Display Persistence       | Completed    | localStorage persistence, daily midnight auto-reset, provider breakdown (Groq / Gemini) with dots.   |
| Step 2 | ToolRegistry Schemas            | Completed    | 7 structured tools registered in ToolRegistry with Gemini-compatible function schemas.               |
| Step 3 | Multi-Chat & Dataset Scoping    | Completed    | IDE-style isolated workspaces: SessionStore holds isolated df + history; + New Chat in sidebar.      |
| Step 4 | Wire Coordinator Execution      | Completed    | AgentCoordinator.process_query() executes tool loops against the session's isolated dataset.         |
| Step 5 | Router LLM Classification       | Completed    | Lightweight intent classification into Structured vs. RAG vs. Hybrid with heuristic fallback.        |
| Step 6 | RAG Layer (Unstructured Data)   | Completed    | Text chunking + vector embeddings + semantic retrieval for markdown/text knowledge docs.             |
| Step 7 | API Route Switchover            | Completed    | Connect /api/ask to AgentCoordinator behind a safety feature flag.                                   |
| Step 8 | File Upload UI & Polish         | Completed    | Drag-and-drop CSV and doc uploads, dataset management UI, and final hardening.                       |
| Step 9 | Supabase Auth & Client Quotas   | Completed    | Google 1-Click + Email login, per-user private sessions & datasets, and daily token budget metering.  |

---

## Detailed Step Specifications

### [Completed] Step 1 — Fix Token Display Persistence
- **Goal:** Token count persists across page refreshes and differentiates providers.
- **Implemented:**
  - `App.jsx`: `tokenUsage` initializes from and saves to `localStorage` (keyed by current date).
  - `TokenUsageDisplay.jsx`: Added per-provider breakdown (Gemini / Groq).
  - `Sidebar.jsx`: Threaded `activeModel` prop.
  - Verified: Refresh retains count; "Clear Chat" resets cleanly.

---

### [Completed] Step 2 — Register Structured Tools in ToolRegistry
- **Goal:** All structured tools discoverable via standard registry with function calling schemas.
- **Implemented:**
  - Created `registry_setup.py` with 7 tools registered: `get_dataset_schema`, `filter_rows`, `aggregate_data`, `group_data`, `sort_data`, `get_unique_values`, `generate_chart`.
  - Tools are completely data-agnostic; the `df` is injected at execution time rather than hardcoded.
  - Verified: `test_registry.py` confirms all 7 tools resolve and schemas validate.

---

### [Completed] Step 3 — Multi-Chat Sessions & Dataset Scoping
- **Goal:** Create isolated IDE-style chat workspaces ("voids"). Each chat session is permanently locked to its chosen dataset, with its own conversation history and token usage with zero cross-talk.
- **Implemented:**
  - `dataset_manager.py`: Discovers raw CSVs and caches DataFrames in memory.
  - `session_store.py`: Upgraded `SessionMemory` into `SessionStore` with isolated `ChatSession` workspaces.
  - `routes.py`: Added `/api/sessions`, `/api/datasets`, and `/api/upload` endpoints; `/api/ask` executes against session's private `df`.
  - `NewChatModal.jsx`: Modal triggered by `+ New Chat` allowing users to select either an existing dataset in storage or browse/open a `.csv` file directly from their computer explorer.
  - `Sidebar.jsx`: Added `+ New Chat` button, dynamic chat workspace list with dataset badges and delete buttons.
  - `Header.jsx`: Eliminated the upload button and dataset dropdown; replaced with a clean, read-only indicator badge showing the dataset currently locked to the active chat void.
  - `App.jsx`: Multi-session switching, history restoration, token isolation, and modal integration.
  - Verified: `test_sessions_backend.py` confirms Chat A (Netflix) and Chat B (Tech Salaries) run independently with zero cross-talk. All frontend builds pass cleanly.

---

### [Completed] Step 4 — Wire Coordinator to Actually Execute Tools
- **Goal:** Transform `AgentCoordinator` from a skeleton into an active execution engine.
- **Implemented:**
  - `coordinator.py`: Full execution pipeline orchestrating Router classification, Session isolation, LLM tool selection via `build_tool_selection_prompt()`, deterministic function execution against `session.df`, plain-English summarization, automatic chart payload resolution (`generate_chart`), multi-turn memory recording, and cumulative token tracking.
  - `prompts.py`: Robust prompt builders for tool selection with strict JSON output rules, analytical summary generation, RAG document synthesis, and hybrid reasoning.
  - `structured_tools.py`: Added resilient case-insensitive column resolution (`_resolve_column`), multi-operator support (`eq`, `contains`, `gt`, `gte`, `lt`, `lte`), numeric aggregation safety, and NaN-safe JSON serialization.
  - `registry_setup.py`: Registered 8 tools (including `search_documents`) with full JSON schemas.
  - Verified: `test_coordinator_step4.py` confirmed 4 comprehensive tests passing:
    1. Netflix Session structured query ("Top 5 countries") computed exact figures (`US: 2818, India: 972...`), generated chart, and recorded 2073 tokens.
    2. Tech Salaries Session query ("Most common job titles") executed against `tech_salaries.csv` with zero cross-talk, isolated tokens (1650 tokens).
    3. Unsupported query correctly triggered `operation: unsupported` with clean explanatory reason.
    4. Schema inquiry executed `get_dataset_schema`, accurately detailing 8,807 rows and 14 columns.

---

### [Completed] Step 5 — Upgrade Router to LLM Classification
- **Goal:** Intelligent intent routing that decides whether a query needs structured calculations, document lookup, or both.
- **Implemented:**
  - `router.py`: `QueryRouter` upgraded with dual-mode classification (`llm` and `heuristic`):
    - `llm_route()`: Calls LLM with `build_router_prompt()` returning verified JSON `{ "route": "structured" | "rag" | "hybrid" }`.
    - `heuristic_route()`: Robust zero-cost keyword and pattern matching fallback.
  - `prompts.py`: Added `build_router_prompt()` with multi-turn conversation context threading and intent guidance.
  - `coordinator.py`: Passes active LLM `provider` down into `router.route()` for seamless provider consistency.
  - Verified: `test_router_step5.py` confirmed 100% accuracy across:
    - Structured queries ("Top 5 oldest movies", "Average duration of movies") -> `structured`
    - RAG queries ("What does TV-MA mean?", "Explain criteria for PG-13") -> `rag`
    - Hybrid queries ("List all TV-MA shows and explain why they received this rating") -> `hybrid`
    - Multi-turn context queries correctly inheriting intent.
    - Zero-cost heuristic fallback tested offline.

---

### [Completed] Step 6 — Build RAG Layer (Embeddings + Vector Search)
- **Goal:** Enable the agent to answer questions from unstructured knowledge documents (markdown/text/data dictionaries).
- **Implemented:**
  - `indexer.py`: Scans `data/knowledge/`, parses markdown & text documents, generates structured `DocumentChunk` passages with titles, and builds normalized TF-IDF vector representations with sublinear scaling.
  - `retriever.py`: `DocumentRetriever` computes in-memory cosine similarity over chunk vectors using numpy dot-product scoring, ranking passages with confidence scores.
  - `rag_tools.py`: `search_documents(query, top_k, user_id)` creates a user-scoped retriever and is registered in `default_registry`.
  - `tools/__init__.py`: Auto-initializes and registers all structured and RAG tools on module import.
  - Verified: `test_rag_step6.py` confirmed 4 comprehensive tests passing:
    1. Document indexer loaded 2 documents, chunked 5 passages, and built a vocabulary of 183 terms.
    2. Vector search matched relevant excerpts for "content rating criteria", "duration splitting", and "unique identifier".
    3. `search_documents` registered tool executed cleanly with similarity scores.
    4. End-to-end `AgentCoordinator.process_query()` on a RAG question routed to `rag`, executed `search_documents`, and synthesized an accurate factual answer.

---

### [Completed] Step 7 — Switch API Route from Legacy to Agent Coordinator
- **Goal:** `/api/ask` serves answers via the modern `AgentCoordinator` pipeline instead of the legacy `query_planner.py`.
- **Implemented:**
  - `config.py`: Added `USE_LEGACY_AGENT` feature flag (defaults to `False`) for immediate zero-downtime fallback capability.
  - `coordinator.py`: Added `unsupported_reason: None` and exported `default_coordinator` singleton.
  - `routes.py`: Refactored `POST /api/ask` to dispatch directly into `default_coordinator.process_query()`.
  - Verified: `test_api_step7.py` via FastAPI `TestClient` confirmed:
    1. Structured queries generate exact groupings, summary text, and base64 chart renderings.
    2. RAG queries retrieve data dictionary knowledge and return domain definitions.
    3. Unsupported queries cleanly return HTTP 200 with `operation: unsupported`.
    4. Frontend builds cleanly with zero errors.

---

### [Completed] Step 8 — File Upload UI, Hardening & Polish
- **Goal:** Allow users to upload new CSV datasets and unstructured documents directly from the UI.
- **Implemented:**
  - `routes.py`: Upgraded `POST /api/upload` to support:
    - `.csv` datasets: stored in `data/uploads/{user_id}/`, validated before atomic replacement, with metadata persisted in PostgreSQL.
    - `.md` / `.txt` knowledge documents: stored in `data/knowledge/{user_id}/`, with an isolated index rebuilt for retrieval.
  - `UploadModal.jsx`: Modern drag-and-drop modal with file detection, format validation, progress state, and instant "Start Chat with this Dataset" transition.
  - `Header.jsx`: Added accessible "Upload" button with icon next to the active dataset badge.
  - `App.jsx`: Fully wired upload modal, state lifecycle, and dataset reloading.
  - Verified: `test_step8_hardening.py` confirmed:
    1. CSV upload saves, discovers rows/columns, and enables new chat workspace creation.
    2. Markdown knowledge upload saves, auto-triggers vector indexing, and is immediately retrievable via vector similarity search.
    3. Frontend builds with 0 errors.

---

### [Completed] Step 9 — Supabase Auth & Per-Client Token Quotas (Option 1)
- **Goal:** Authenticate users with Google 1-Click / Email OTP via Supabase, scope chat workspaces & datasets privately per user, and enforce a daily per-client token allowance (50,000 tokens/day) to prevent server quota exhaustion.
- **Implemented:**
  - **Backend Auth & Quota Layer:**
    - `backend/app/auth/supabase_auth.py`: Mandatory authentication validates signatures, issuer, audience, expiry, issued-at and authenticated role. Demo accounts require an explicit development-only flag.
    - `backend/app/auth/quota_manager.py`: Daily UTC-resetting token quota manager backed by PostgreSQL, with transactional increments across workers.
    - `backend/app/memory/session_store.py`: `ChatSession` and `SessionStore` scoped strictly by `user_id`.
    - `backend/app/data_engine/dataset_manager.py`: Multi-tenant dataset isolation separating global public datasets from private user uploads under `data/uploads/{user_id}/`.
    - `backend/app/api/routes.py`: Secured `/api/sessions`, `/api/upload`, `/api/datasets`, `/api/auth/me`, `/api/user/quota`, and `/api/ask` (HTTP 429 quota guard triggered before LLM execution, atomic quota increment upon completion).
  - **Frontend Integration:**
    - Installed `@supabase/supabase-js`.
    - `frontend/src/supabase.js`: Configured client with live Supabase credentials and built-in demo profiles (Alice & Bob).
    - `frontend/src/components/AuthModal.jsx`: Google and email login; profile switching is available only with the explicit development demo flag.
    - `frontend/src/components/Header.jsx`: Added user identity badge and live token quota allowance progress bar.
    - `frontend/src/components/HomePage.jsx`: Added user identity pill and daily token quota indicator in top navigation.
    - `frontend/src/api.js`: Automatic `Authorization: Bearer <token>` injection across all endpoints and friendly 429 error handling.
    - `frontend/src/components/App.jsx`: Full auth lifecycle, reactive quota reloading, and multi-tenant workspace isolation.
  - **Verified:**
    - `scratch/test_step9_auth_quota.py`:
      1. User A and User B profile resolution tested and verified.
      2. Workspace isolation verified: User A cannot see User B's sessions in lists or via direct ID lookup.
      3. Private dataset storage verified: User A's private CSV upload is isolated and completely invisible to User B.
      4. Quota guard verified: Exhausting User A's 50,000 token limit returns HTTP 429 before LLM call; User B's quota remains untouched and unblocked.
    - `scratch/test_step8_hardening.py`: Zero regression verified across all file upload and RAG auto-indexing capabilities.
    - Frontend bundle: `npm run build` compiled with 0 errors.

---



### Security and persistence follow-up (2026-09-10)

Step 9 implementation now requires authenticated private routes and verified Supabase tokens. Demo identities are explicitly development-only. PostgreSQL backs users, sessions, quota records, activity, and dataset metadata; private RAG and safe bounded uploads replace shared uploads. Automated pytest regression and PostgreSQL CI replace the scratch verification scripts. See README setup and rollout notes; live OAuth/provider smoke checks depend on deployment credentials.
