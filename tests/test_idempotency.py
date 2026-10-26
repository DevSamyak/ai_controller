from __future__ import annotations

from tests.helpers import GOAL, approve_first


def test_rerun_does_not_duplicate_drafts(operator):
    orch = operator
    first = approve_first(orch, orch.run(orch.submit(GOAL)["id"]))
    assert first["task"]["status"] == "complete"
    before = sorted(p.name for p in orch.settings.drafts_path.glob("*.md"))
    second = approve_first(orch, orch.run(orch.submit(GOAL)["id"]))
    after = sorted(p.name for p in orch.settings.drafts_path.glob("*.md"))
    assert before == after
    reused = [v.get("reused") for v in second["memory"]["drafted"].values()]
    assert any(reused)
