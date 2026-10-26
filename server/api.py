from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from agent.orchestrator import Orchestrator
from agent.settings import load_settings
from server.schemas import ApprovalDecision, TaskCreate

_orch: Orchestrator | None = None
_lock = asyncio.Lock()


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        settings = load_settings()
        try:
            _orch = Orchestrator(settings=settings)
        except RuntimeError as exc:
            # Live provider misconfigured: still serve health/mock; fail live tasks clearly.
            settings_fake = load_settings()
            object.__setattr__(settings_fake, "llm_provider", "fake") if False else None
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _orch


def _safe_orch() -> Orchestrator:
    global _orch
    if _orch is None:
        settings = load_settings()
        if settings.llm_provider in {"google", "gemini"} and (not settings.llm_api_key or not settings.llm_model):
            from dataclasses import replace

            settings = replace(settings, llm_provider="fake")
        _orch = Orchestrator(settings=settings)
    return _orch


app = FastAPI(title="AI Operator", version="0.1.0")
_settings = load_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_settings.frontend_origin, "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    settings = load_settings()
    live_ok = bool(settings.llm_api_key and settings.llm_model) if settings.llm_provider in {"google", "gemini"} else True
    return {
        "status": "ok",
        "service": "operator",
        "llm_provider": settings.llm_provider,
        "llm_configured": live_ok,
        "workspace": str(settings.workspace_path),
        "details": {
            "mock_company_url": settings.mock_company_url,
            "max_retries": settings.max_retries,
            "max_steps": settings.max_steps,
        },
    }


@app.post("/tasks")
async def create_task(body: TaskCreate):
    orch = _safe_orch()
    task = orch.submit(body.goal)
    asyncio.create_task(asyncio.to_thread(orch.run, task["id"]))
    return {"ok": True, "task_id": task["id"], "status": task["status"]}


@app.get("/tasks")
def list_tasks():
    orch = _safe_orch()
    return {"ok": True, "tasks": orch.store.list_tasks()}


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    orch = _safe_orch()
    task = orch.store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    snap = orch.snapshot(task_id)
    return {"ok": True, **snap}


@app.get("/tasks/{task_id}/events")
async def task_events(task_id: str):
    orch = _safe_orch()
    if orch.store.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def gen():
        last_id = 0
        idle = 0
        while idle < 300:
            events = orch.store.list_events(task_id, after_id=last_id)
            if events:
                idle = 0
                for event in events:
                    last_id = event["id"]
                    yield {"event": event["type"], "data": _json(event)}
            else:
                idle += 1
                yield {"event": "ping", "data": "{}"}
            status = (orch.store.get_task(task_id) or {}).get("status")
            if status in {"complete", "partial", "blocked", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.4)

    return EventSourceResponse(gen())


@app.post("/approvals/{approval_id}")
async def decide_approval(approval_id: str, body: ApprovalDecision):
    orch = _safe_orch()
    try:
        record = orch.store.decide_approval(approval_id, body.decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task = orch.store.get_task(record["task_id"])
    if task and task["status"] == "waiting_approval":
        asyncio.create_task(asyncio.to_thread(orch.run, record["task_id"]))
    return {"ok": True, "approval": record}


@app.get("/artifacts")
def read_artifact(path: str = Query(..., min_length=1)):
    orch = _safe_orch()
    workspace = orch.settings.workspace_path.resolve()
    candidate = (workspace / path).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes workspace") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return {"ok": True, "path": path, "content": candidate.read_text(encoding="utf-8")}


def _json(event: dict[str, Any]) -> str:
    import json

    return json.dumps({"id": event["id"], "type": event["type"], "payload": event["payload"], "created_at": event["created_at"]})
