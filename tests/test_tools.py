from __future__ import annotations

from agent.settings import load_settings
from tools.files import SaveFileArgs, save_file
from tools.policies import SearchPolicyArgs, search_policy
from tools.registry import invoke_tool, build_registry
from tools.tickets_api import ListTicketsArgs, list_tickets


def test_policy_search_and_conflict(tmp_env):
    result = search_policy(load_settings(), SearchPolicyArgs(query="60 day defective speaker warranty refund"))
    assert result.ok
    names = [item["filename"] for item in result.data["results"]]
    assert "refund.md" in names
    assert "warranty.md" in names
    assert result.data["conflict"] is not None


def test_file_write_stays_in_workspace(tmp_env):
    settings = load_settings()
    saved = save_file(settings, SaveFileArgs(relative_path="drafts/T-TEST.md", content="# Draft reply for T-TEST\n\nPolicy: sla.md\n"))
    assert saved.ok
    path = settings.drafts_path / "T-TEST.md"
    assert path.exists()
    assert "T-TEST" in path.read_text()
    escaped = save_file(settings, SaveFileArgs(relative_path="../secret.txt", content="nope"))
    assert not escaped.ok


def test_api_ticket_schema(tmp_env, mock_server, monkeypatch):
    monkeypatch.setenv("MOCK_COMPANY_URL", mock_server)
    settings = load_settings()
    listed = list_tickets(settings, ListTicketsArgs(status="open", priority="high"))
    assert listed.ok
    ticket = listed.data["tickets"][0]
    for key in ("id", "title", "body", "status", "priority", "source"):
        assert key in ticket
    assert listed.data["source"] == "api"


def test_api_browser_shape_parity(tmp_env, mock_server, monkeypatch):
    monkeypatch.setenv("MOCK_COMPANY_URL", mock_server)
    settings = load_settings()
    registry = build_registry()
    api = invoke_tool(registry, "list_tickets", {"status": "open", "priority": "high"}, settings)
    browser = invoke_tool(registry, "list_tickets_browser", {"status": "open", "priority": "high"}, settings)
    assert api.ok, api.error
    assert browser.ok, browser.error
    api_ids = sorted(t["id"] for t in api.data["tickets"])
    browser_ids = sorted(t["id"] for t in browser.data["tickets"])
    assert api_ids == browser_ids
    api_one = invoke_tool(registry, "get_ticket", {"ticket_id": "T-101"}, settings)
    br_one = invoke_tool(registry, "get_ticket_browser", {"ticket_id": "T-101"}, settings)
    assert api_one.data["ticket"]["id"] == br_one.data["ticket"]["id"]
    assert api_one.data["ticket"]["status"] == br_one.data["ticket"]["status"]
    assert set(api_one.data["ticket"]) == set(br_one.data["ticket"])
