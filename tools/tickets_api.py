from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from agent.settings import Settings
from tools.base import ToolResult, normalize_ticket


class ListTicketsArgs(BaseModel):
    status: str | None = None
    priority: str | None = None
    ticket_id: str | None = None
    limit: int | None = Field(default=None, ge=1, le=500)


class GetTicketArgs(BaseModel):
    ticket_id: str


class IssueRefundArgs(BaseModel):
    ticket_id: str
    amount: int = Field(gt=0)


def _client(settings: Settings) -> httpx.Client:
    return httpx.Client(base_url=settings.mock_company_url, timeout=10.0)


def _http_error(exc: httpx.HTTPError) -> ToolResult:
    retryable = False
    message = str(exc)
    status = None
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        message = f"HTTP {status}: {exc.response.text[:300]}"
        retryable = status in {408, 429, 500, 502, 503, 504}
    elif isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)):
        retryable = True
    return ToolResult(
        ok=False,
        error=message,
        retryable=retryable,
        evidence=[{"kind": "http_error", "status": status, "retryable": retryable}],
    )


def list_tickets(settings: Settings, args: ListTicketsArgs) -> ToolResult:
    params = {k: v for k, v in args.model_dump().items() if v is not None}
    try:
        with _client(settings) as client:
            response = client.get("/api/tickets", params=params)
            response.raise_for_status()
            payload = response.json()
            tickets = [normalize_ticket(t, "api") for t in payload.get("tickets", [])]
            return ToolResult(
                ok=True,
                data={"tickets": tickets, "count": len(tickets), "source": "api"},
                evidence=[{"kind": "ticket_list", "source": "api", "count": len(tickets), "ids": [t["id"] for t in tickets]}],
            )
    except httpx.HTTPError as exc:
        return _http_error(exc)


def get_ticket(settings: Settings, args: GetTicketArgs) -> ToolResult:
    try:
        with _client(settings) as client:
            response = client.get(f"/api/tickets/{args.ticket_id}")
            response.raise_for_status()
            payload = response.json()
            ticket = normalize_ticket(payload["ticket"], "api")
            return ToolResult(
                ok=True,
                data={"ticket": ticket, "source": "api"},
                evidence=[{"kind": "ticket_get", "source": "api", "ticket_id": ticket["id"]}],
            )
    except httpx.HTTPError as exc:
        return _http_error(exc)


def issue_mock_refund(settings: Settings, args: IssueRefundArgs) -> ToolResult:
    try:
        with _client(settings) as client:
            response = client.post(
                f"/api/tickets/{args.ticket_id}/refund",
                json={"amount": args.amount},
            )
            response.raise_for_status()
            payload = response.json()
            ticket = normalize_ticket(payload["ticket"], "api")
            return ToolResult(
                ok=True,
                data={"ticket": ticket, "source": "api", "refunded": True, "amount": args.amount},
                evidence=[
                    {
                        "kind": "mock_refund",
                        "ticket_id": args.ticket_id,
                        "amount": args.amount,
                        "note": "simulated local SQLite mutation only",
                    }
                ],
            )
    except httpx.HTTPError as exc:
        return _http_error(exc)
