#!/usr/bin/env python3
"""Health, import, and writable-output checks. Fails with a nonzero exit code."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def get(url: str, timeout: float = 4.0) -> dict:
    with urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        if response.status >= 400:
            fail(f"{url} -> {response.status} {body}")
        return json.loads(body)


def post(url: str, payload: dict, timeout: float = 8.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_health(url: str, seconds: float = 12.0) -> dict:
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            return get(url)
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(0.2)
    fail(f"no health response from {url}: {last}")
    raise AssertionError


def main() -> None:
    os.environ["LLM_PROVIDER"] = "fake"
    os.environ.setdefault("LLM_API_KEY", "")
    os.environ.setdefault("LLM_MODEL", "")
    from agent.settings import load_settings

    settings = load_settings()
    settings.ensure_dirs()
    for path in (settings.workspace_path, settings.drafts_path, settings.reports_path, settings.logs_path):
        if not path.exists():
            fail(f"missing writable path {path}")
    marker = settings.logs_path / "smoke-write-check.txt"
    marker.write_text("ok", encoding="utf-8")
    marker.unlink()

    try:
        import fastapi  # noqa: F401
        import rank_bm25  # noqa: F401
        import sse_starlette  # noqa: F401
    except ImportError as exc:
        fail(f"dependency import failed: {exc}")

    mock = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mock_company.app:app", "--host", "127.0.0.1", "--port", "8001"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    operator = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.api:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        mock_health = wait_health("http://127.0.0.1:8001/health")
        op_health = wait_health("http://127.0.0.1:8000/health")
        tickets = get("http://127.0.0.1:8001/api/tickets?status=open&priority=high")
        if not tickets.get("tickets"):
            fail("seeded high-priority tickets missing")
        created = post(
            "http://127.0.0.1:8000/tasks",
            {
                "goal": "Review all unresolved high-priority support tickets, use our company policies to draft replies, and save a daily summary."
            },
        )
        task_id = created.get("task_id")
        if not task_id:
            fail(f"task submit failed: {created}")
        deadline = time.time() + 60
        status = None
        while time.time() < deadline:
            snap = get(f"http://127.0.0.1:8000/tasks/{task_id}")
            status = snap["task"]["status"]
            if status in {"waiting_approval", "complete", "partial", "blocked", "failed"}:
                break
            time.sleep(0.4)
        if status not in {"waiting_approval", "complete"}:
            fail(f"unexpected smoke task status {status}")
        print("PASS: imports, writable dirs, mock health, operator health, seeded tickets, task submit")
        print(json.dumps({"mock": mock_health, "operator": op_health, "task_id": task_id, "status": status}, indent=2))
    finally:
        for proc in (operator, mock):
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
