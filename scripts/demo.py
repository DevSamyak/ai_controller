#!/usr/bin/env python3
"""Run the documented demo scenarios against the local mock company."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["LLM_PROVIDER"] = "fake"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""

from agent.orchestrator import Orchestrator
from agent.settings import load_settings
from agent.state import TaskStore
from mock_company.app import app as mock_app
from mock_company.seed import seed
from tests.helpers import GOAL, approve_first

RESULTS: list[dict] = []


def _port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def start_mock() -> tuple[uvicorn.Server, threading.Thread, str]:
    port = _port()
    os.environ["MOCK_COMPANY_URL"] = f"http://127.0.0.1:{port}"
    config = uvicorn.Config(mock_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/health", timeout=0.5).status_code == 200:
                return server, thread, url
        except httpx.HTTPError:
            time.sleep(0.05)
    raise RuntimeError("mock company failed to start")


def orch() -> Orchestrator:
    settings = load_settings()
    seed(settings.mock_database_path, reset=True)
    return Orchestrator(settings=settings, store=TaskStore(settings.database_path))


def record(name: str, snap: dict, extra: dict | None = None) -> None:
    task = snap["task"]
    drafts = sorted((snap.get("memory") or {}).get("drafted") or {})
    report = ((snap.get("memory") or {}).get("report") or {}).get("path")
    row = {
        "scenario": name,
        "status": task["status"],
        "reason": task.get("reason"),
        "task_id": task["id"],
        "drafts": drafts,
        "report": report,
        "flags": [f.get("ticket_id") for f in snap.get("flags") or []],
    }
    if extra:
        row.update(extra)
    RESULTS.append(row)
    print(json.dumps(row, indent=2))


def main() -> None:
    server, thread, url = start_mock()
    try:
        operator = orch()
        snap = operator.run(operator.submit(GOAL)["id"])
        snap = approve_first(operator, snap)
        record("happy_path", snap)

        httpx.post(f"{url}/admin/faults", json={"api_down": True}, timeout=5)
        operator = orch()
        snap = operator.run(operator.submit(GOAL)["id"])
        extra = {
            "source": (snap.get("memory") or {}).get("list", {}).get("source"),
            "events": sorted({e["type"] for e in snap["events"]}),
        }
        snap = approve_first(operator, snap)
        extra["final_status"] = snap["task"]["status"]
        record("api_503_browser_fallback", snap, extra)
        httpx.post(f"{url}/admin/faults", json={"api_down": False}, timeout=5)

        httpx.post(f"{url}/admin/faults", json={"api_down": True, "ui_down": True}, timeout=5)
        operator = orch()
        snap = operator.run(operator.submit(GOAL)["id"])
        record("both_paths_down", snap)
        httpx.post(f"{url}/admin/faults", json={"api_down": False, "ui_down": False}, timeout=5)

        operator = orch()
        snap = operator.run(operator.submit(GOAL)["id"])
        flagged = {f["ticket_id"]: f["category"] for f in snap["flags"]}
        record("injection_and_review_flags", snap, {"categories": flagged})

        operator = orch()
        first = approve_first(operator, operator.run(operator.submit(GOAL)["id"]))
        second = approve_first(operator, operator.run(operator.submit(GOAL)["id"]))
        drafts_dir = operator.settings.drafts_path
        files = sorted(p.name for p in drafts_dir.glob("T-*.md"))
        record(
            "idempotency",
            second,
            {"draft_files": files, "first_status": first["task"]["status"], "reused": True},
        )
    finally:
        server.should_exit = True
        thread.join(timeout=2)

    print("\nScenario summary")
    for row in RESULTS:
        print(f"- {row['scenario']}: {row['status']}")
    bad = [r for r in RESULTS if r["scenario"] != "both_paths_down" and r["status"] not in {"complete", "waiting_approval"}]
    blocked_ok = any(r["scenario"] == "both_paths_down" and r["status"] == "blocked" for r in RESULTS)
    if bad or not blocked_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
