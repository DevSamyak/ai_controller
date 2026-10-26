from __future__ import annotations

from tests.helpers import GOAL, approve_first


def test_corrupt_draft_fails_verification(operator):
    orch = operator
    snap = approve_first(orch, orch.run(orch.submit(GOAL)["id"]))
    assert snap["task"]["status"] == "complete"
    target = orch.settings.drafts_path / "T-101.md"
    assert target.exists()
    target.write_text("", encoding="utf-8")
    verification = orch.reverify(snap["task"]["id"])
    assert verification["passed"] is False
    assert orch.store.get_task(snap["task"]["id"])["status"] == "partial"


def test_sse_and_task_schema(tmp_env, mock_server, monkeypatch):
    monkeypatch.setenv("MOCK_COMPANY_URL", mock_server)
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    from fastapi.testclient import TestClient
    import server.api as api_mod

    api_mod._orch = None
    client = TestClient(api_mod.app)
    health = client.get("/health")
    assert health.status_code == 200
    created = client.post("/tasks", json={"goal": "ping"})
    assert created.status_code == 200
    task_id = created.json()["task_id"]
    listed = client.get(f"/tasks/{task_id}")
    assert listed.status_code == 200
    assert "task" in listed.json()
    events = client.get(f"/tasks/{task_id}/events")
    assert events.status_code == 200
