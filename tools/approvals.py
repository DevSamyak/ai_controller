from __future__ import annotations

from pydantic import BaseModel, Field

from tools.base import ToolResult


class RequestApprovalArgs(BaseModel):
    action: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    arguments: dict = Field(default_factory=dict)
    rationale: str = Field(min_length=1)
    risk: str = "consequential"


class FlagReviewArgs(BaseModel):
    ticket_id: str
    reason: str
    category: str


def request_approval(store, task_id: str, args: RequestApprovalArgs) -> ToolResult:
    existing = store.find_approval(task_id, args.action, args.ticket_id)
    if existing and existing["status"] in {"pending", "approved", "rejected"}:
        return ToolResult(
            ok=True,
            data={"approval": existing, "reused": True},
            evidence=[{"kind": "approval_reuse", "approval_id": existing["id"], "status": existing["status"]}],
        )
    record = store.create_approval(
        task_id=task_id,
        action=args.action,
        arguments={"ticket_id": args.ticket_id, **args.arguments},
        target_record=args.ticket_id,
        rationale=args.rationale,
        risk=args.risk,
    )
    return ToolResult(
        ok=True,
        data={"approval": record, "reused": False},
        evidence=[{"kind": "approval_requested", "approval_id": record["id"], "ticket_id": args.ticket_id, "action": args.action}],
    )


def flag_for_review(store, task_id: str, args: FlagReviewArgs) -> ToolResult:
    record = store.add_review_flag(task_id, args.ticket_id, args.reason, args.category)
    return ToolResult(
        ok=True,
        data={"flag": record},
        evidence=[{"kind": "human_review", "ticket_id": args.ticket_id, "category": args.category}],
    )
