from __future__ import annotations

import httpx

from tests.helpers import GOAL, approve_first


def test_api_503_retries_then_browser(operator, mock_server):
    httpx.post(f"{mock_server}/admin/faults", json={"api_down": True}, timeout=5)
    orch = operator
    task = orch.submit(GOAL)
    snap = orch.run(task["id"])
    events = [e["type"] for e in snap["events"]]
    assert "retry" in events
    assert "browser_fallback" in events
    assert snap["memory"]["list"]["source"] == "browser"
    assert snap["task"]["status"] == "waiting_approval"
    snap = approve_first(orch, snap)
    assert snap["task"]["status"] == "complete", snap["task"]
    trace = (orch.settings.logs_path / f"{task['id']}.jsonl").read_text(encoding="utf-8")
    assert "503" in trace or "HTTP 503" in trace
    assert "browser_fallback" in trace
    httpx.post(f"{mock_server}/admin/faults", json={"api_down": False}, timeout=5)


def test_both_paths_down_is_blocked(operator, mock_server):
    httpx.post(f"{mock_server}/admin/faults", json={"api_down": True, "ui_down": True}, timeout=5)
    orch = operator
    task = orch.submit(GOAL)
    snap = orch.run(task["id"])
    assert snap["task"]["status"] == "blocked"
    assert not snap["memory"]["tickets"]
    assert snap["task"]["reason"]
    httpx.post(f"{mock_server}/admin/faults", json={"api_down": False, "ui_down": False}, timeout=5)
