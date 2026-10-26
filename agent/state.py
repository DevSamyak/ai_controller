from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"waiting_approval", "complete", "partial", "blocked", "failed", "cancelled"},
    "waiting_approval": {"running", "partial", "blocked", "failed", "cancelled"},
    "complete": {"partial", "failed"},
    "partial": set(),
    "blocked": set(),
    "failed": set(),
    "cancelled": set(),
}

STEP_TRANSITIONS = {
    "pending": {"running", "skipped"},
    "running": {"done", "retrying", "failed", "blocked", "waiting_approval"},
    "retrying": {"running", "failed", "blocked"},
    "done": set(),
    "failed": set(),
    "blocked": set(),
    "waiting_approval": {"running", "skipped", "failed"},
    "skipped": set(),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    plan_json TEXT,
    success_conditions_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    purpose TEXT NOT NULL,
    tool TEXT,
    status TEXT NOT NULL,
    expected_output TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT,
    tool TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    ok INTEGER,
    retryable INTEGER,
    attempt INTEGER NOT NULL,
    error TEXT,
    result_json TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    action TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    target_record TEXT,
    rationale TEXT,
    risk TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS review_flags (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(task_id, ticket_id),
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS draft_keys (
    task_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    UNIQUE(ticket_id, content_hash)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(id)
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TaskStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_task(self, goal: str) -> dict[str, Any]:
        task_id = new_id("task")
        now = utcnow()
        self.conn.execute(
            "INSERT INTO tasks(id, goal, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, goal, "queued", now, now),
        )
        self.conn.commit()
        self.emit(task_id, "task_created", {"goal": goal, "status": "queued"})
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def set_status(self, task_id: str, status: str, reason: str | None = None) -> None:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        current = task["status"]
        if status != current and status not in TASK_TRANSITIONS.get(current, set()):
            raise ValueError(f"illegal task transition {current} -> {status}")
        self.conn.execute(
            "UPDATE tasks SET status = ?, reason = ?, updated_at = ? WHERE id = ?",
            (status, reason, utcnow(), task_id),
        )
        self.conn.commit()
        self.emit(task_id, "task_status", {"status": status, "reason": reason})

    def save_plan(self, task_id: str, plan: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE tasks SET plan_json = ?, success_conditions_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(plan), json.dumps(plan.get("success_conditions", [])), utcnow(), task_id),
        )
        self.conn.execute("DELETE FROM steps WHERE task_id = ?", (task_id,))
        for index, step in enumerate(plan.get("steps", [])):
            self.conn.execute(
                "INSERT INTO steps(id, task_id, ordinal, purpose, tool, status, expected_output) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    step.get("id") or new_id("step"),
                    task_id,
                    index,
                    step["purpose"],
                    step.get("tool"),
                    "pending",
                    step.get("expected_output"),
                ),
            )
        self.conn.commit()
        self.emit(task_id, "plan", plan)

    def list_steps(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM steps WHERE task_id = ? ORDER BY ordinal", (task_id,)).fetchall()
        return [dict(r) for r in rows]

    def set_step_status(self, step_id: str, status: str) -> None:
        row = self.conn.execute("SELECT * FROM steps WHERE id = ?", (step_id,)).fetchone()
        if row is None:
            return
        current = row["status"]
        if status != current and status not in STEP_TRANSITIONS.get(current, set()):
            if current in {"done", "failed", "blocked", "skipped"}:
                return
            raise ValueError(f"illegal step transition {current} -> {status}")
        self.conn.execute("UPDATE steps SET status = ? WHERE id = ?", (status, step_id))
        self.conn.commit()

    def record_tool_call(
        self,
        task_id: str,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        attempt: int,
        step_id: str | None = None,
    ) -> str:
        call_id = new_id("call")
        now = utcnow()
        redacted = _redact(arguments)
        self.conn.execute(
            """INSERT INTO tool_calls(
                id, task_id, step_id, tool, arguments_json, ok, retryable, attempt, error, result_json, started_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                call_id,
                task_id,
                step_id,
                tool,
                json.dumps(redacted),
                1 if result.get("ok") else 0,
                1 if result.get("retryable") else 0,
                attempt,
                result.get("error"),
                json.dumps(_trim_result(result)),
                now,
                now,
            ),
        )
        for item in result.get("evidence") or []:
            self.add_evidence(task_id, {"tool": tool, **item})
        self.conn.commit()
        self.emit(
            task_id,
            "tool_call",
            {"id": call_id, "tool": tool, "ok": result.get("ok"), "attempt": attempt, "error": result.get("error")},
        )
        return call_id

    def add_evidence(self, task_id: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO evidence(id, task_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (new_id("ev"), task_id, json.dumps(payload), utcnow()),
        )
        self.conn.commit()

    def list_evidence(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM evidence WHERE task_id = ? ORDER BY created_at", (task_id,)).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload_json"])} for r in rows]

    def list_tool_calls(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tool_calls WHERE task_id = ? ORDER BY started_at",
            (task_id,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["arguments"] = json.loads(item["arguments_json"])
            item["result"] = json.loads(item["result_json"]) if item["result_json"] else None
            out.append(item)
        return out

    def create_approval(self, task_id: str, action: str, arguments: dict[str, Any], target_record: str, rationale: str, risk: str) -> dict[str, Any]:
        approval_id = new_id("appr")
        now = utcnow()
        self.conn.execute(
            """INSERT INTO approvals(id, task_id, action, arguments_json, target_record, rationale, risk, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (approval_id, task_id, action, json.dumps(arguments), target_record, rationale, risk, now),
        )
        self.conn.commit()
        record = self.get_approval(approval_id)
        self.emit(task_id, "approval_requested", record)
        return record

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["arguments"] = json.loads(data["arguments_json"])
        return data

    def find_approval(self, task_id: str, action: str, target_record: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM approvals WHERE task_id = ? AND action = ? AND target_record = ? ORDER BY created_at DESC LIMIT 1",
            (task_id, action, target_record),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["arguments"] = json.loads(data["arguments_json"])
        return data

    def matching_approved(self, task_id: str, action: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE task_id = ? AND action = ? AND status = 'approved'",
            (task_id, action),
        ).fetchall()
        for row in rows:
            stored = json.loads(row["arguments_json"])
            if _args_match(stored, arguments):
                data = dict(row)
                data["arguments"] = stored
                return data
        return None

    def decide_approval(self, approval_id: str, status: str) -> dict[str, Any]:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")
        record = self.get_approval(approval_id)
        if record is None:
            raise KeyError(approval_id)
        if record["status"] != "pending":
            raise ValueError("approval already decided")
        self.conn.execute(
            "UPDATE approvals SET status = ?, decided_at = ? WHERE id = ?",
            (status, utcnow(), approval_id),
        )
        self.conn.commit()
        updated = self.get_approval(approval_id)
        self.emit(record["task_id"], "approval_decided", updated)
        return updated

    def list_approvals(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM approvals WHERE task_id = ?", (task_id,)).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["arguments"] = json.loads(data["arguments_json"])
            out.append(data)
        return out

    def add_review_flag(self, task_id: str, ticket_id: str, reason: str, category: str) -> dict[str, Any]:
        existing = self.conn.execute(
            "SELECT * FROM review_flags WHERE task_id = ? AND ticket_id = ?",
            (task_id, ticket_id),
        ).fetchone()
        if existing:
            return dict(existing)
        flag_id = new_id("flag")
        now = utcnow()
        self.conn.execute(
            "INSERT INTO review_flags(id, task_id, ticket_id, reason, category, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (flag_id, task_id, ticket_id, reason, category, now),
        )
        self.conn.commit()
        record = dict(self.conn.execute("SELECT * FROM review_flags WHERE id = ?", (flag_id,)).fetchone())
        self.emit(task_id, "review_flag", record)
        return record

    def list_flags(self, task_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM review_flags WHERE task_id = ?", (task_id,)).fetchall()
        return [dict(r) for r in rows]

    def remember_draft(self, task_id: str, ticket_id: str, content_hash: str, path: str) -> bool:
        existing = self.conn.execute(
            "SELECT * FROM draft_keys WHERE ticket_id = ? AND content_hash = ?",
            (ticket_id, content_hash),
        ).fetchone()
        if existing:
            return True
        self.conn.execute(
            "INSERT INTO draft_keys(task_id, ticket_id, content_hash, path) VALUES (?, ?, ?, ?)",
            (task_id, ticket_id, content_hash, path),
        )
        self.conn.commit()
        return False

    def emit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO events(task_id, type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (task_id, event_type, json.dumps(payload, default=str), utcnow()),
        )
        self.conn.commit()

    def list_events(self, task_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE task_id = ? AND id > ? ORDER BY id",
            (task_id, after_id),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload_json"])
            out.append(item)
        return out


def _redact(arguments: dict[str, Any]) -> dict[str, Any]:
    blocked = {"api_key", "token", "password", "authorization"}
    out = {}
    for key, value in arguments.items():
        if key.lower() in blocked:
            out[key] = "[redacted]"
        elif key == "content" and isinstance(value, str) and len(value) > 400:
            out[key] = value[:400] + "…"
        else:
            out[key] = value
    return out


def _trim_result(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    if isinstance(data, dict) and "content" in data and isinstance(data["content"], str) and len(data["content"]) > 500:
        data = {**data, "content": data["content"][:500] + "…"}
    return {
        "ok": result.get("ok"),
        "error": result.get("error"),
        "retryable": result.get("retryable"),
        "data": data,
        "evidence": result.get("evidence"),
    }


def _args_match(stored: dict[str, Any], incoming: dict[str, Any]) -> bool:
    for key, value in incoming.items():
        if stored.get(key) != value:
            return False
    return True
