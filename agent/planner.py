from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PlanStep(BaseModel):
    id: str | None = None
    purpose: str
    tool: str | None = None
    expected_output: str
    depends_on: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    summary: str
    steps: list[PlanStep] = Field(min_length=1, max_length=20)
    success_conditions: list[str] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def unique_purposes(cls, steps: list[PlanStep]) -> list[PlanStep]:
        if not steps:
            raise ValueError("plan needs steps")
        return steps


DEFAULT_PLAN = Plan(
    summary="Review unresolved high-priority tickets, ground replies in policy, save drafts and a daily summary.",
    steps=[
        PlanStep(
            purpose="List unresolved high-priority tickets",
            tool="list_tickets",
            expected_output="Normalized ticket list from API or browser fallback",
        ),
        PlanStep(
            purpose="Load each listed ticket",
            tool="get_ticket",
            expected_output="Full ticket records",
        ),
        PlanStep(
            purpose="Retrieve applicable policies",
            tool="search_policy",
            expected_output="Ranked policy filenames and conflict flags",
        ),
        PlanStep(
            purpose="Draft, flag, or request approval per ticket",
            tool="save_file",
            expected_output="Workspace drafts and review flags",
        ),
        PlanStep(
            purpose="Write daily summary report",
            tool="save_file",
            expected_output="Report file whose counts match drafts and source tickets",
        ),
    ],
    success_conditions=[
        "Unresolved high-priority tickets are loaded from the live mock system",
        "Each drafted ticket has a non-empty file citing a policy filename",
        "Tickets needing review are flagged instead of guessed",
        "No consequential action runs without a matching approved approval",
        "Independent verifier confirms files and source counts",
    ],
)
