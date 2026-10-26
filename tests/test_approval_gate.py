from __future__ import annotations

import httpx

from agent.settings import load_settings
from mock_company.seed import seed
from tests.helpers import GOAL, approve_first, reject_first
from tools.registry import build_registry, invoke_tool


def test_refund_requires_matching_approval(operator, mock_server):
    settings = load_settings()
    registry = build_registry()
    direct = invoke_tool(
        registry,
        "issue_mock_refund",
        {"ticket_id": "T-104", "amount": 18000},
        settings,
        store=operator.store,
        task_id="none",
    )
    # registry itself does not check approvals; permissions layer does.
    assert direct.ok is True
    seed(settings.mock_database_path, reset=True)
    from agent.permissions import check_permission

    task = operator.store.create_task("permission check")
    blocked = check_permission(operator.store, task["id"], "issue_mock_refund", {"ticket_id": "T-104", "amount": 18000})
    assert blocked is not None
    assert blocked.ok is False

    orch = operator
    snap = orch.run(orch.submit(GOAL)["id"])
    ticket = httpx.get(f"{mock_server}/api/tickets/T-104", timeout=5).json()["ticket"]
    assert ticket["refunded"] is False
    snap = reject_first(orch, snap)
    ticket = httpx.get(f"{mock_server}/api/tickets/T-104", timeout=5).json()["ticket"]
    assert ticket["refunded"] is False
    refund_ok = [c for c in snap["tool_calls"] if c["tool"] == "issue_mock_refund" and c["ok"]]
    assert refund_ok == []


def test_approve_runs_only_matching_action(operator, mock_server):
    orch = operator
    snap = orch.run(orch.submit(GOAL)["id"])
    snap = approve_first(orch, snap)
    ticket = httpx.get(f"{mock_server}/api/tickets/T-104", timeout=5).json()["ticket"]
    assert ticket["refunded"] is True
    assert ticket["refunded_amount"] == 18000
    # wrong amount would not match approval
    blocked = invoke_tool(
        build_registry(),
        "issue_mock_refund",
        {"ticket_id": "T-104", "amount": 999999},
        load_settings(),
        store=orch.store,
        task_id=snap["task"]["id"],
    )
    from agent.permissions import check_permission

    denied = check_permission(orch.store, snap["task"]["id"], "issue_mock_refund", {"ticket_id": "T-104", "amount": 999999})
    assert denied is not None
    assert blocked.ok  # mock company may still accept if called directly
    assert denied.ok is False
