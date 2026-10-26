from __future__ import annotations

GOAL = "Review all unresolved high-priority support tickets, use our company policies to draft replies, and save a daily summary."


def approve_first(orch, snapshot):
    pending = [a for a in snapshot["approvals"] if a["status"] == "pending"]
    assert pending, snapshot["task"]
    orch.store.decide_approval(pending[0]["id"], "approved")
    return orch.run(snapshot["task"]["id"])


def reject_first(orch, snapshot):
    pending = [a for a in snapshot["approvals"] if a["status"] == "pending"]
    assert pending
    orch.store.decide_approval(pending[0]["id"], "rejected")
    return orch.run(snapshot["task"]["id"])
