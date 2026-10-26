from __future__ import annotations

import hashlib
import re
from typing import Any

INJECTION_PATTERNS = [
    r"ignore all previous instructions",
    r"ignore previous instructions",
    r"do not follow company policy",
    r"you are now",
    r"system prompt",
    r"delete the audit logs",
]


def normalize_duplicate_key(ticket: dict[str, Any]) -> str:
    title = re.sub(r"\s+", " ", (ticket.get("title") or "").strip().lower())
    body = re.sub(r"\s+", " ", (ticket.get("body") or "").strip().lower())
    order_id = (ticket.get("order_id") or "").strip().lower()
    blob = f"{title}|{order_id}|{body}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def is_injection(text: str) -> bool:
    return any(re.search(pattern, text or "", re.I) for pattern in INJECTION_PATTERNS)


def classify_ticket(
    ticket: dict[str, Any],
    policy_payload: dict[str, Any] | None,
    seen_keys: dict[str, str],
    refund_threshold: int,
) -> dict[str, Any]:
    body = ticket.get("body") or ""
    if is_injection(body) or is_injection(ticket.get("title") or ""):
        return {
            "action": "flag",
            "category": "prompt_injection",
            "reason": "Ticket contains instruction-override language. Treated as untrusted data.",
        }
    if not ticket.get("order_id"):
        return {
            "action": "flag",
            "category": "missing_info",
            "reason": "Order ID is missing; do not invent facts.",
        }
    conflict = (policy_payload or {}).get("conflict")
    if conflict and _in_conflict_window(ticket):
        return {
            "action": "flag",
            "category": "policy_conflict",
            "reason": f"Policies conflict in group {conflict.get('group')}: {conflict.get('filenames')}",
        }
    key = normalize_duplicate_key(ticket)
    if key in seen_keys and seen_keys[key] != ticket["id"]:
        return {
            "action": "skip_duplicate",
            "category": "duplicate",
            "reason": f"Near-duplicate of {seen_keys[key]}",
            "duplicate_of": seen_keys[key],
        }
    amount = _as_int(ticket.get("refund_amount"))
    if amount is not None and amount >= refund_threshold:
        return {
            "action": "approve_then_draft",
            "category": "high_value_refund",
            "reason": f"Refund of ₹{amount} is at or above the ₹{refund_threshold} approval threshold.",
            "amount": amount,
        }
    return {"action": "draft", "category": "standard", "reason": "Clear policy match."}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _in_conflict_window(ticket: dict[str, Any]) -> bool:
    days = _as_int(ticket.get("days_since_purchase"))
    if days is not None and 31 <= days <= 90:
        return True
    blob = f"{ticket.get('title') or ''} {ticket.get('body') or ''}".lower()
    return "warranty" in blob and "refund" in blob


def preferred_policy(ticket: dict[str, Any], policy_payload: dict[str, Any] | None) -> str:
    results = (policy_payload or {}).get("results") or []
    if results:
        return results[0]["filename"]
    title = (ticket.get("title") or "").lower()
    body = (ticket.get("body") or "").lower()
    blob = title + " " + body
    if "sla" in blob or "premium" in blob:
        return "sla.md"
    if "password" in blob or "locked" in blob:
        return "reply_templates.md"
    if "refund" in blob:
        return "refund.md"
    if "ship" in blob or "charger" in blob:
        return "reply_templates.md"
    return "escalation.md"


def draft_text(ticket: dict[str, Any], policy_filename: str, extra: str = "") -> str:
    order = ticket.get("order_id") or "unknown"
    amount = ticket.get("refund_amount")
    lines = [
        f"# Draft reply for {ticket['id']}",
        "",
        f"- Ticket: {ticket['id']}",
        f"- Customer: {ticket.get('customer')}",
        f"- Order: {order}",
        f"- Policy: {policy_filename}",
        "",
        extra or (
            f"Hello {ticket.get('customer')}, we reviewed ticket {ticket['id']} for order {order} "
            f"against {policy_filename}. We will follow the documented procedure and will not invent details."
        ),
        "",
    ]
    if amount:
        lines.append(
            f"Noted refund amount ₹{amount}. No consequential refund is issued from this draft."
        )
    return "\n".join(lines)
