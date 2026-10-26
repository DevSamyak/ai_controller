from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    goal: str = Field(min_length=3, max_length=4000)


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]


class Health(BaseModel):
    status: str
    service: str
    llm_provider: str
    llm_configured: bool
    workspace: str
    details: dict[str, Any] = Field(default_factory=dict)
