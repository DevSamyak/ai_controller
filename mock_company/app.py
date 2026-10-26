from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from agent.settings import load_settings
from mock_company.db import apply_refund, connect, get_faults, get_ticket, init_schema, list_tickets
from mock_company.faults import api_is_down, apply_fault_updates, slow_ms, ui_is_down
from mock_company.seed import seed

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
# Starlette 1.10 + Jinja2 3.1 can pass an unhashable dict cache key.
TEMPLATES.env.cache = None


class FaultRequest(BaseModel):
    api_down: bool | None = None
    ui_down: bool | None = None
    slow_ms: int | None = Field(default=None, ge=0, le=30000)


class RefundRequest(BaseModel):
    amount: int = Field(gt=0)


def get_conn():
    settings = load_settings()
    conn = connect(settings.mock_database_path)
    init_schema(conn)
    return conn


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed()
    yield


app = FastAPI(title="Mock Company", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def fault_middleware(request: Request, call_next):
    conn = get_conn()
    try:
        delay = slow_ms(conn)
        if delay:
            time.sleep(delay / 1000)
        path = request.url.path
        if path.startswith("/api/") and api_is_down(conn):
            return HTMLResponse(
                '{"detail":"mock company API fault injected"}',
                status_code=503,
                media_type="application/json",
            )
        if path.startswith("/ui/") and ui_is_down(conn):
            raise HTTPException(status_code=503, detail="mock company UI fault injected")
        return await call_next(request)
    finally:
        conn.close()


@app.get("/health")
def health():
    conn = get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]
        return {
            "status": "ok",
            "service": "mock-company",
            "tickets": int(count),
            "faults": get_faults(conn),
        }
    finally:
        conn.close()


@app.get("/api/tickets")
def api_list_tickets(
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    ticket_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
):
    conn = get_conn()
    try:
        tickets = list_tickets(conn, status=status, priority=priority, ticket_id=ticket_id, limit=limit)
        return {"ok": True, "tickets": tickets, "source": "api"}
    finally:
        conn.close()


@app.get("/api/tickets/{ticket_id}")
def api_get_ticket(ticket_id: str):
    conn = get_conn()
    try:
        ticket = get_ticket(conn, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"ticket {ticket_id} not found")
        return {"ok": True, "ticket": ticket, "source": "api"}
    finally:
        conn.close()


@app.post("/api/tickets/{ticket_id}/refund")
def api_refund(ticket_id: str, body: RefundRequest):
    conn = get_conn()
    try:
        ticket = apply_refund(conn, ticket_id, body.amount)
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"ticket {ticket_id} not found")
        return {"ok": True, "ticket": ticket, "source": "api"}
    finally:
        conn.close()


@app.get("/ui/tickets", response_class=HTMLResponse)
def ui_tickets(
    request: Request,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
):
    conn = get_conn()
    try:
        tickets = list_tickets(conn, status=status, priority=priority)
        return TEMPLATES.TemplateResponse(
            request,
            "tickets_list.html",
            {"tickets": tickets, "status": status, "priority": priority},
        )
    finally:
        conn.close()


@app.get("/ui/tickets/{ticket_id}", response_class=HTMLResponse)
def ui_ticket_detail(request: Request, ticket_id: str):
    conn = get_conn()
    try:
        ticket = get_ticket(conn, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"ticket {ticket_id} not found")
        return TEMPLATES.TemplateResponse(request, "ticket_detail.html", {"ticket": ticket})
    finally:
        conn.close()


@app.post("/admin/faults")
def admin_faults(body: FaultRequest):
    """Local demo only. Not production-safe. Controls mock API/UI failure modes."""
    conn = get_conn()
    try:
        faults = apply_fault_updates(conn, body.model_dump(exclude_none=True))
        return {"ok": True, "faults": faults, "warning": "local demo fault switch only"}
    finally:
        conn.close()


@app.get("/admin/faults")
def admin_get_faults():
    conn = get_conn()
    try:
        return {"ok": True, "faults": get_faults(conn), "warning": "local demo fault switch only"}
    finally:
        conn.close()
