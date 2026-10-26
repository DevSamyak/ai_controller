from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from tools.base import ToolResult, empty_to_none, normalize_ticket
from tools.tickets_api import GetTicketArgs, ListTicketsArgs


def _attrs(locator) -> dict[str, Any]:
    names = [
        "id",
        "title",
        "body",
        "customer",
        "status",
        "priority",
        "created-at",
        "due-at",
        "order-id",
        "refund-amount",
        "days-since-purchase",
        "refunded",
        "refunded-amount",
    ]
    raw: dict[str, Any] = {}
    for name in names:
        raw[name.replace("-", "_")] = locator.get_attribute(f"data-{name}")
    raw["order_id"] = empty_to_none(raw.get("order_id"))
    raw["due_at"] = empty_to_none(raw.get("due_at"))
    return raw


def _missing_browser_error(exc: Exception) -> ToolResult:
    message = str(exc)
    hint = ""
    lowered = message.lower()
    if "executable doesn't exist" in lowered or "playwright" in lowered and "chromium" in lowered:
        hint = " Run `playwright install chromium` from the project virtualenv."
    return ToolResult(
        ok=False,
        error=message + hint,
        retryable=False,
        evidence=[{"kind": "browser_error", "error": message}],
    )


def list_tickets_browser(settings, args: ListTicketsArgs) -> ToolResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return _missing_browser_error(exc)

    params = {k: v for k, v in args.model_dump().items() if v is not None and k != "limit"}
    url = settings.mock_company_url + "/ui/tickets"
    if params:
        url += "?" + urlencode(params)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            response = page.goto(url, wait_until="domcontentloaded")
            if response is not None and response.status >= 400:
                browser.close()
                return ToolResult(
                    ok=False,
                    error=f"browser list HTTP {response.status}",
                    retryable=response.status >= 500,
                    evidence=[{"kind": "browser_http", "status": response.status, "url": url}],
                )
            rows = page.locator("tr[id^='ticket-row-']")
            tickets = []
            for i in range(rows.count()):
                tickets.append(normalize_ticket(_attrs(rows.nth(i)), "browser"))
            if args.ticket_id:
                tickets = [t for t in tickets if t["id"] == args.ticket_id]
            if args.limit:
                tickets = tickets[: args.limit]
            browser.close()
            return ToolResult(
                ok=True,
                data={"tickets": tickets, "count": len(tickets), "source": "browser"},
                evidence=[
                    {
                        "kind": "ticket_list",
                        "source": "browser",
                        "count": len(tickets),
                        "ids": [t["id"] for t in tickets],
                        "url": url,
                    }
                ],
            )
    except Exception as exc:  # noqa: BLE001 - normalize Playwright failures
        return _missing_browser_error(exc)


def get_ticket_browser(settings, args: GetTicketArgs) -> ToolResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return _missing_browser_error(exc)

    url = f"{settings.mock_company_url}/ui/tickets/{args.ticket_id}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            response = page.goto(url, wait_until="domcontentloaded")
            if response is not None and response.status >= 400:
                status = response.status
                browser.close()
                return ToolResult(
                    ok=False,
                    error=f"browser detail HTTP {status}",
                    retryable=status >= 500,
                    evidence=[{"kind": "browser_http", "status": status, "url": url}],
                )
            detail = page.locator("#ticket-detail")
            if detail.count() == 0:
                browser.close()
                return ToolResult(ok=False, error="ticket detail selectors missing", retryable=False)
            ticket = normalize_ticket(_attrs(detail), "browser")
            browser.close()
            return ToolResult(
                ok=True,
                data={"ticket": ticket, "source": "browser"},
                evidence=[{"kind": "ticket_get", "source": "browser", "ticket_id": ticket["id"], "url": url}],
            )
    except Exception as exc:  # noqa: BLE001
        return _missing_browser_error(exc)
