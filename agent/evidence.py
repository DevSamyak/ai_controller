from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.settings import Settings
from agent.state import TaskStore


class JsonlLogger:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.logs_path.mkdir(parents=True, exist_ok=True)

    def write(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        path = self.settings.logs_path / f"{task_id}.jsonl"
        record = {"type": event_type, **_redact(payload)}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = {"api_key", "llm_api_key", "token", "password", "authorization"}
    out = {}
    for key, value in payload.items():
        if key.lower() in blocked:
            out[key] = "[redacted]"
        else:
            out[key] = value
    return out


def build_report(store: TaskStore, task_id: str, memory: dict[str, Any], verification: dict[str, Any]) -> str:
    tickets = memory.get("tickets") or {}
    drafted = memory.get("drafted") or {}
    flags = memory.get("flags") or {}
    skipped = memory.get("skipped") or {}
    lines = [
        "# Daily support summary",
        "",
        f"Task: {task_id}",
        f"Source ticket count: {len(tickets)}",
        f"Drafts written: {len(drafted)}",
        f"Flagged for review: {len(flags)}",
        f"Duplicates skipped: {len(skipped)}",
        "",
        "## Tickets",
        "",
    ]
    for ticket_id, ticket in tickets.items():
        if not ticket:
            continue
        status = "drafted" if ticket_id in drafted else "flagged" if ticket_id in flags else "skipped" if ticket_id in skipped else "open"
        policy = (memory.get("policies") or {}).get(ticket_id, {})
        filenames = [item.get("filename") for item in (policy.get("results") or [])]
        draft_path = (drafted.get(ticket_id) or {}).get("path")
        lines.append(
            f"- {ticket_id} ({ticket.get('status')}/{ticket.get('priority')}): {status}. "
            f"policies={filenames}. draft={draft_path or 'n/a'}"
        )
    lines += ["", "## Verification", "", json.dumps(verification, indent=2, default=str), ""]
    evidence = store.list_evidence(task_id)
    lines += ["## Evidence references", ""]
    for item in evidence:
        payload = item["payload"]
        kind = payload.get("kind") or payload.get("tool")
        ticket = payload.get("ticket_id")
        path = payload.get("path") or payload.get("relative_path")
        lines.append(f"- {kind}: ticket={ticket} path={path}")
    return "\n".join(lines) + "\n"


def trace_path(settings: Settings, task_id: str) -> Path:
    return settings.logs_path / f"{task_id}.jsonl"
