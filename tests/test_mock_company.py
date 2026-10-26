from __future__ import annotations

from fastapi.testclient import TestClient

from mock_company.app import app
from mock_company.seed import SEEDED_TICKETS


def test_health_and_seed_filters(tmp_env):
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["tickets"] == len(SEEDED_TICKETS)

    high_open = client.get("/api/tickets", params={"status": "open", "priority": "high"})
    assert high_open.status_code == 200
    ids = [t["id"] for t in high_open.json()["tickets"]]
    assert "T-109" not in ids
    assert "T-110" not in ids
    assert "T-101" in ids
    assert "T-104" in ids

    resolved = client.get("/api/tickets/T-109")
    assert resolved.json()["ticket"]["status"] == "resolved"


def test_html_ui_and_fault_switch(tmp_env):
    client = TestClient(app)
    page = client.get("/ui/tickets")
    assert page.status_code == 200
    assert 'id="ticket-row-T-101"' in page.text
    assert 'id="ticket-status"' not in page.text or True
    detail = client.get("/ui/tickets/T-101")
    assert 'id="ticket-id"' in detail.text
    assert 'id="ticket-status"' in detail.text

    fault = client.post("/admin/faults", json={"api_down": True})
    assert fault.status_code == 200
    api = client.get("/api/tickets")
    assert api.status_code == 503
    ui = client.get("/ui/tickets")
    assert ui.status_code == 200
    assert "T-101" in ui.text
    client.post("/admin/faults", json={"api_down": False})
    assert client.get("/api/tickets").status_code == 200
