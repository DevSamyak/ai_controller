from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    customer TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    created_at TEXT NOT NULL,
    due_at TEXT,
    order_id TEXT,
    refund_amount INTEGER,
    days_since_purchase INTEGER,
    refunded INTEGER NOT NULL DEFAULT 0,
    refunded_amount INTEGER
);

CREATE TABLE IF NOT EXISTS faults (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

TICKET_FIELDS = (
    "id",
    "title",
    "body",
    "customer",
    "status",
    "priority",
    "created_at",
    "due_at",
    "order_id",
    "refund_amount",
    "days_since_purchase",
    "refunded",
    "refunded_amount",
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def row_to_ticket(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["refunded"] = bool(data.get("refunded"))
    return data


def list_tickets(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    priority: str | None = None,
    ticket_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if ticket_id:
        clauses.append("id = ?")
        params.append(ticket_id)
    sql = "SELECT * FROM tickets"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    return [row_to_ticket(r) for r in rows]


def get_ticket(conn: sqlite3.Connection, ticket_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return row_to_ticket(row) if row else None


def upsert_tickets(conn: sqlite3.Connection, tickets: Iterable[dict[str, Any]]) -> None:
    sql = """
    INSERT INTO tickets (
        id, title, body, customer, status, priority, created_at, due_at,
        order_id, refund_amount, days_since_purchase, refunded, refunded_amount
    ) VALUES (
        :id, :title, :body, :customer, :status, :priority, :created_at, :due_at,
        :order_id, :refund_amount, :days_since_purchase, :refunded, :refunded_amount
    )
    ON CONFLICT(id) DO UPDATE SET
        title=excluded.title,
        body=excluded.body,
        customer=excluded.customer,
        status=excluded.status,
        priority=excluded.priority,
        created_at=excluded.created_at,
        due_at=excluded.due_at,
        order_id=excluded.order_id,
        refund_amount=excluded.refund_amount,
        days_since_purchase=excluded.days_since_purchase,
        refunded=excluded.refunded,
        refunded_amount=excluded.refunded_amount
    """
    for ticket in tickets:
        payload = {
            "refunded": 0,
            "refunded_amount": None,
            "due_at": None,
            "order_id": None,
            "refund_amount": None,
            "days_since_purchase": None,
            **ticket,
        }
        payload["refunded"] = 1 if payload.get("refunded") else 0
        conn.execute(sql, payload)
    conn.commit()


def apply_refund(conn: sqlite3.Connection, ticket_id: str, amount: int) -> dict[str, Any] | None:
    ticket = get_ticket(conn, ticket_id)
    if ticket is None:
        return None
    conn.execute(
        "UPDATE tickets SET refunded = 1, refunded_amount = ? WHERE id = ?",
        (amount, ticket_id),
    )
    conn.commit()
    return get_ticket(conn, ticket_id)


def get_faults(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM faults").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_faults(conn: sqlite3.Connection, updates: dict[str, Any]) -> dict[str, str]:
    for key, value in updates.items():
        if value is None or value is False or value == "":
            conn.execute("DELETE FROM faults WHERE key = ?", (key,))
        else:
            conn.execute(
                "INSERT INTO faults(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value).lower() if isinstance(value, bool) else str(value)),
            )
    conn.commit()
    return get_faults(conn)
