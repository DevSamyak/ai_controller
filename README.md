# AI Operator — Autonomous Company Operations Agent

A local, production-grade proof of concept demonstrating an **AI Employee / Autonomous Company Operator**. It resolves high-priority customer support tickets, grounds decisions against internal company policies, drafts replies, generates daily operational reports, safely escalates consequential actions for human approval, and deterministically verifies all output artifacts.

---

## Architecture & Autonomous Capabilities

The operator follows an explicit **Goal → Understand → Plan → Execute → Observe → Adapt → Verify → Complete** loop:

- **Dual-Provider Architecture:** Built for Google Gemini via `google-genai` with a deterministic offline `FakeLLM` provider that runs all tests and demo scenarios without an external API key or network access.
- **Resilient Tool Execution & Browser Fallback:** When ticket JSON API calls fail (e.g., HTTP 503), the agent retries boundedly and falls back to a Playwright Chromium headless browser against the simulated company portal.
- **Human Approval Boundary:** Consequential actions (such as refund authorizations $\ge$ ₹10,000) trigger human approval gates enforced in application code.
- **Prompt Injection Defense:** Customer tickets and untrusted inputs are isolated within strictly bounded data blocks. Code-level permission checks prevent unauthorized tool execution.
- **Idempotency & Re-entrancy:** Content hashes and ticket metadata prevent redundant drafts or duplicate actions across repeated runs.
- **Deterministic Verifier:** An independent verification module inspects actual files on disk, schema integrity, and ticket counts without invoking the LLM.

---

## System Requirements

- **Python:** 3.11+ (Python 3.12 recommended)
- **Node.js:** 20+ and `npm`
- **Operating System:** macOS, Linux, or Windows (WSL recommended)

---

## Setup & Installation

### 1. Python Environment

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 2. Frontend Dependencies

```bash
npm install --prefix ui
```

### 3. Environment Configuration

Copy the example environment configuration:

```bash
cp .env.example .env
```

By default, `.env` is configured with `LLM_PROVIDER=fake`, enabling offline execution.

To enable live Google Gemini execution:
1. Set `LLM_PROVIDER=google`
2. Provide your Gemini API key in `LLM_API_KEY` (or `GEMINI_API_KEY`)
3. Set `LLM_MODEL` to an available Gemini model (e.g., `gemini-2.0-flash` or `gemini-2.5-flash`)

---

## Running the Application

Start all three services across separate terminal tabs or background processes:

### Terminal 1: Mock Company Service (Port 8001)
```bash
source .venv/bin/activate
python -m uvicorn mock_company.app:app --host 127.0.0.1 --port 8001
```
*Health Check:* `http://127.0.0.1:8001/health`  
*HTML Portal:* `http://127.0.0.1:8001/ui/tickets`

### Terminal 2: AI Operator Server (Port 8000)
```bash
source .venv/bin/activate
python -m uvicorn server.api:app --host 127.0.0.1 --port 8000
```
*Health Check:* `http://127.0.0.1:8000/health`  
*API Docs:* `http://127.0.0.1:8000/docs`

### Terminal 3: React / Vite Dashboard (Port 5173)
```bash
npm run dev --prefix ui
```
Open `http://127.0.0.1:5173` in your browser.

---

## Verification & Automated Tests

All tests and verification scripts run deterministically without requiring a live Gemini API key:

### Run the Pytest Suite
```bash
pytest
```
Executes all 17 automated tests covering happy-path drafting, API recovery and browser fallback, human approval gates, prompt injection resistance, partial/blocked tasks, tool contracts, and independent artifact verification.

### Run Smoke Health Check
```bash
python scripts/smoke.py
```
Validates imports, writable workspace paths, mock company endpoints, operator health, seeded ticket availability, and task dispatch.

### Run End-to-End Demo Scenarios
```bash
python scripts/demo.py
```
Executes 5 complete scenarios:
1. `happy_path`: End-to-end ticket triage, policy retrieval, drafting, approval, and daily report generation.
2. `api_503_browser_fallback`: Injects API faults and verifies browser recovery via Playwright.
3. `both_paths_down`: Verifies honest `blocked` termination when both API and web UI are unreachable.
4. `injection_and_review_flags`: Verifies prompt injection quarantine and review flagging.
5. `idempotency`: Verifies re-run safety without generating redundant drafts.

### Build Frontend for Production
```bash
npm run build --prefix ui
```

### Package Clean Source Archive
```bash
python scripts/package.py
```
Generates `dist/ai-operator-source.zip` while strictly excluding caches, virtual environments, `node_modules`, SQLite databases, logs, and sensitive `.env` files.

---

## Project Structure

```text
ai-operator/
├── agent/                      # Core agent runtime & loop
│   ├── orchestrator.py         # Plan-execute-observe-adapt loop
│   ├── planner.py              # Goal analysis & step planning
│   ├── classifier.py           # Ticket categorization & policy matching
│   ├── permissions.py          # Risk policy & approval boundaries
│   ├── recovery.py             # Retry & browser fallback coordination
│   ├── verifier.py             # Deterministic disk & state verification
│   ├── state.py                # SQLite persistence for tasks, steps, events
│   ├── llm.py                  # LLM provider contract, Gemini & Fake providers
│   └── settings.py             # Central environment settings loader
├── mock_company/               # Local simulated company service
│   ├── app.py                  # FastAPI server with API & HTML endpoints
│   ├── db.py                   # Mock database connection & schema
│   ├── seed.py                 # Seeded support tickets & test scenarios
│   ├── faults.py               # Controllable failure injection (API/UI 503)
│   ├── policies/               # Markdown policy documents (SLA, refund, etc.)
│   └── templates/              # Jinja2 HTML templates for Playwright fallback
├── server/                     # Operator backend API
│   ├── api.py                  # FastAPI endpoints & SSE event stream
│   └── schemas.py              # Pydantic request/response schemas
├── tools/                      # Operator tool implementations
│   ├── tickets_api.py          # Ticket retrieval & refund API tools
│   ├── tickets_browser.py      # Playwright browser automation fallback
│   ├── policies.py             # BM25 lexical policy search & reading
│   ├── approvals.py            # Human approval request dispatch
│   ├── files.py                # Sandboxed workspace file operations
│   └── registry.py             # Tool registration & schemas
├── ui/                         # React + Vite live dashboard
│   ├── src/App.jsx             # Interactive operations control center
│   ├── src/styles.css          # Modern dashboard styles
│   ├── src/api.js              # Operator API client
│   └── src/main.jsx            # React root mount
├── scripts/                    # Utility & verification scripts
│   ├── smoke.py                # Quick system health & task submission check
│   ├── demo.py                 # Multi-scenario demonstration runner
│   └── package.py              # Clean source archive builder
├── tests/                      # Deterministic pytest suite (17 tests)
├── workspace/                  # Agent working directory (drafts, reports)
├── requirements.txt            # Python dependencies
├── .env.example                # Safe configuration template
└── README.md                   # Setup and execution guide
```

---

## Troubleshooting

- **Playwright missing browser:** Run `playwright install chromium` inside your active virtual environment.
- **Port already in use:** Ensure ports `8000`, `8001`, and `5173` are free (`lsof -i :8000`, etc.).
- **Missing Gemini key:** For offline operation, keep `LLM_PROVIDER=fake` in `.env`.
