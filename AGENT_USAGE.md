# Agent Usage

How AI assistance was used for this change (Streamlit -> React + cleanup).

## Tools used

- Codebase exploration (file reads, pattern search) to map the existing
  backend: `validator.py`, `llm/chat.py`, `store.py`, `pro/*`, `ingestion/*`
- File edits for comment cleanup (Hinglish -> minimal English)
- New code: `backend/app.py` (FastAPI), `app_logging.py` (JSON logs),
  `frontend/` (React + Vite), `tests/` (pytest)
- Shell: `npm install` / `npm run build` (frontend verified),
  `python -m pytest` (17 passed), Python `ast` syntax check

## Representative prompts

1. "Replace the Streamlit UI with a minimal React frontend, keep backend logic unchanged"
2. "Add structured application and AI-workflow logs plus focused tests"
3. "Write README (setup, architecture, scope, tests, limitations, deployment),
   AGENT_USAGE, and .env.example; never commit secrets"
4. "Document the chunking and retrieval strategy and every important decision in
   the README so the reasoning is clear"
5. "Compare tab does not show changes after approving; category dropdown empty"

## Delegated work

- Frontend scaffold + build: delegated to shell (`npm install`, `vite build`)
- Test execution: delegated to `pytest`; failures investigated and fixed
- No work was delegated to other agents; all changes were made directly

## Important mistakes / rejected suggestions

1. **Near-duplicate test used `title + "!"`** — punctuation is stripped by
   normalization, so the case collapsed to an exact duplicate and the
   near-duplicate check correctly skipped it. Fixed the test to change a word
   (`Black` -> `White`) instead of claiming the check was broken.
2. **`fastapi.testclient.TestClient(app)` in tests** — rejected; the installed
   httpx/starlette versions are incompatible (`unexpected keyword argument 'app'`).
   Replaced with direct guard-function assertions plus route-presence checks,
   keeping tests dependency-light.
3. **Kept `pandas` out of the backend** — batch CSV parsing moved to the
   frontend; backend accepts parsed JSON. Avoids a heavy server dependency.
4. **Compare tab did not show approved changes** — the AI's `revised_listing` was
   never persisted, so "approve as-is" fell back to the original text on any
   refetch. Fixed by adding `ai_revisions` to `store.py` (append-style
   `INSERT OR REPLACE` keyed by review) and rebuilding from it in
   `build_revised`; Compare now also refetches when the decision set changes, not
   only when the outcome changes. Covered by two new tests.
5. **Empty category dropdown when the backend was down** — added a bundled
   category fallback in `frontend/src/api.js` plus a clear
   "backend not reachable" banner.

## Verification

- `npm run build` — Vite production build succeeds (32 modules)
- `python -m pytest tests -q` — 19 passed, no API keys required
- `ast.parse` on `backend/app.py` — syntax OK
- Live server: `POST /api/init` OK; `POST /api/reviews` on a deliberately bad
  listing returned 6 deterministic findings with rule IDs
  (POL-3.3, POL-2.4/POL-4.1, POL-4.2, POL-3.6, POL-9.2, BRD-2.2/BRD-2.3)
- Grep for Hinglish leftovers in `*.py` — only `streamlit_app.py` still
  matched, and that file was deleted (replaced by React)
- Zip contents checked: no `.env`, no `__pycache__`, no `node_modules`,
  no `.streamlit/`; `.env.example` included with empty values
