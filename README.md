# AI Operator

Proof of concept for an **AI Employee / Autonomous Company Operator**. It turns one company request into completed local work:

> Review all unresolved high-priority support tickets, use our company policies to draft replies, and save a daily summary.

The loop is **Goal → Understand → Plan → Execute → Observe → Adapt → Verify → Complete**. Python code owns tool allowlists, retries, approvals, permissions, and verification. The LLM cannot bypass those controls.

## What is real vs simulated

**Simulated:** the mock company ticketing system (local FastAPI + SQLite + HTML UI). No real refunds, no external email.

**Real:** HTTP tools, Playwright fallback against the mock HTML UI, SQLite task state, workspace draft/report files, human approval records, JSONL evidence logs, and a deterministic verifier that re-reads files and source records (no LLM).

Narrow on purpose: one support-ticket workflow, not a general multi-agent platform.

## Architecture

- `mock_company/` — tickets, policies, fault injection (`127.0.0.1:8001`)
- `tools/` — validated tools (`list_tickets`, browser fallback, policy search, files, approvals, mock refund)
- `agent/orchestrator.py` — plan/act/observe/adapt loop
- `agent/verifier.py` — independent checks; `complete` requires a pass
- `server/api.py` — operator API + SSE (`127.0.0.1:8000`)
- `ui/` — React/Vite dashboard (`127.0.0.1:5173`)
- Default tests use `LLM_PROVIDER=fake`. Live Gemini uses `google-genai` when `LLM_PROVIDER=google` and a key/model are set.

## Setup (macOS, Python 3.11+, Node 20+)

```bash
python3.12 --version
node --version
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
cd ui && npm install && cd ..
```

Put the Gemini key only in `.env` as `LLM_API_KEY` (alias `GEMINI_API_KEY`). Set `LLM_MODEL` to a model your key can use (for example `gemini-2.0-flash`). Never commit `.env`.

Offline / demo without Gemini:

```bash
# in .env
LLM_PROVIDER=fake
```

The operator also falls back to the fake provider if Google is selected but the key or model is missing. Live tasks then still run the deterministic workflow; they do not invent success without tools.

## Run (three terminals, project root, venv active)

```bash
# Terminal 1 — mock company (seeds on startup)
python -m mock_company.seed --reset
python -m uvicorn mock_company.app:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2 — operator API
python -m uvicorn server.api:app --host 127.0.0.1 --port 8000 --reload

# Terminal 3 — dashboard
cd ui
npm run dev -- --host 127.0.0.1 --port 5173
```

Health:

```bash
curl -s http://127.0.0.1:8001/health
curl -s 'http://127.0.0.1:8001/api/tickets?status=open&priority=high'
curl -s http://127.0.0.1:8000/health
```

Open `http://127.0.0.1:5173` to submit the default goal. High-value refunds pause for approve/reject. Ticket pages: `http://127.0.0.1:8001/ui/tickets`.

Local-only fault switch (demo, not production-safe):

```bash
curl -s -X POST http://127.0.0.1:8001/admin/faults -H 'Content-Type: application/json' -d '{"api_down": true}'
# /api/tickets -> 503, /ui/tickets still renders; agent retries then uses Playwright
curl -s -X POST http://127.0.0.1:8001/admin/faults -H 'Content-Type: application/json' -d '{"api_down": false}'
```

## Tests and demos

Default suite is offline and does not need a Gemini key:

```bash
python -m pytest -q
python scripts/smoke.py
python scripts/demo.py
cd ui && npm run build
python scripts/package.py
```

Optional live Gemini check (requires key + network):

```bash
python -m pytest -q -m live
```

`scripts/demo.py` prints scenario name, task status, draft paths, flags, and traces for happy path, API 503 → browser fallback, both-paths-down (`blocked`), injection/review flags, and idempotent drafts.

## Outputs

| What | Where |
| --- | --- |
| Draft replies | `workspace/drafts/T-*.md` |
| Daily summary | `workspace/reports/daily-summary.md` |
| JSONL traces | `logs/runs/<task_id>.jsonl` |
| Operator DB | `data/operator.sqlite3` |
| Mock tickets | `data/mock_company.sqlite3` |
| Policies | `mock_company/policies/*.md` |

Reset mock tickets: `python -m mock_company.seed --reset`. Delete `data/*.sqlite3` and workspace draft/report files for a clean run.

## Seeded tickets

| ID | Role |
| --- | --- |
| T-101–T-103 | Ordinary high-priority, policy-backed drafts |
| T-104 | ₹18,000 refund — human approval, then mock refund only |
| T-105 | Missing info — flag, do not invent |
| T-106 | Prompt injection — untrusted; cannot expand permissions |
| T-107 | Duplicate of another ticket — skip extra draft |
| T-108 | Conflicting policies — human review |
| T-109 | Already resolved — excluded from unresolved queries |

## Verification

`agent/verifier.py` reopens draft/report files and re-queries mock records. A task is `complete` only if those checks pass. If a required file is removed after generation, status becomes `partial`.

## Troubleshooting

- **Import errors (`rank_bm25`, `sse_starlette`):** activate `.venv` and `pip install -r requirements.txt`.
- **Playwright missing Chromium:** `python -m playwright install chromium`.
- **Gemini errors:** set `LLM_API_KEY` and `LLM_MODEL`, or `LLM_PROVIDER=fake`. Keys are never logged.
- **Ports in use:** stop other processes on 8000/8001/5173.
- **UI cannot reach API:** operator must be on `127.0.0.1:8000`; CORS allows `http://127.0.0.1:5173`.
- **Smoke fails because ports busy:** free 8000/8001 and rerun `python scripts/smoke.py`.

## Limitations / future work

No desktop computer-use, no multi-agent framework, no vector DB, no real payments or outbound mail. Browser fallback is Playwright against the mock HTML UI only.

## Package

```bash
python scripts/package.py
# dist/ai-operator-source.zip — excludes .venv, node_modules, .git, .env, caches, sqlite, runtime drafts/logs
unzip -t dist/ai-operator-source.zip
```
