from __future__ import annotations

from tests.helpers import GOAL, approve_first


def test_missing_and_conflict_are_flagged_not_invented(operator):
    orch = operator
    snap = approve_first(orch, orch.run(orch.submit(GOAL)["id"]))
    flags = {f["ticket_id"]: f for f in snap["flags"]}
    assert flags["T-105"]["category"] == "missing_info"
    assert flags["T-108"]["category"] == "policy_conflict"
    drafts = (orch.settings.drafts_path).glob("*.md")
    names = {p.stem for p in drafts}
    assert "T-105" not in names
    assert "T-108" not in names
    for path in orch.settings.drafts_path.glob("*.md"):
        assert "ORD-UNKNOWN" not in path.read_text()
