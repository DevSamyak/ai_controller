from __future__ import annotations

from tests.helpers import GOAL, approve_first


def test_happy_path_creates_real_files(operator):
    orch = operator
    task = orch.submit(GOAL)
    snap = orch.run(task["id"])
    assert snap["task"]["status"] == "waiting_approval"
    snap = approve_first(orch, snap)
    assert snap["task"]["status"] == "complete", snap["task"]
    drafted = sorted(snap["memory"]["drafted"])
    assert drafted == ["T-101", "T-102", "T-103", "T-104"]
    flagged = {f["ticket_id"]: f["category"] for f in snap["flags"]}
    assert flagged["T-105"] == "missing_info"
    assert flagged["T-106"] == "prompt_injection"
    assert flagged["T-108"] == "policy_conflict"
    assert "T-107" in snap["memory"]["skipped"]
    assert "T-109" not in snap["memory"]["tickets"]
    for ticket_id in drafted:
        path = orch.settings.drafts_path / f"{ticket_id}.md"
        text = path.read_text(encoding="utf-8")
        assert ticket_id in text
        assert ".md" in text
    report = (orch.settings.reports_path / "daily-summary.md").read_text(encoding="utf-8")
    assert "T-101" in report
    calls = [c["tool"] for c in snap["tool_calls"]]
    assert "list_tickets" in calls
    assert "search_policy" in calls
