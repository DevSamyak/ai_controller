from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from agent.settings import Settings
from tools import files as file_tools
from tools import policies as policy_tools
from tools import tickets_api
from tools import tickets_browser
from tools.approvals import FlagReviewArgs, RequestApprovalArgs, flag_for_review, request_approval
from tools.base import ToolResult, ToolSpec
from tools.files import ListFilesArgs, ReadFileArgs, SaveFileArgs
from tools.policies import ReadPolicyArgs, SearchPolicyArgs
from tools.tickets_api import GetTicketArgs, IssueRefundArgs, ListTicketsArgs

API_FALLBACKS = {
    "list_tickets": "list_tickets_browser",
    "get_ticket": "get_ticket_browser",
}


class Tool:
    def __init__(
        self,
        spec: ToolSpec,
        args_model: type[BaseModel],
        handler: Callable[..., ToolResult],
        needs_store: bool = False,
    ) -> None:
        self.spec = spec
        self.args_model = args_model
        self.handler = handler
        self.needs_store = needs_store

    def parse(self, arguments: dict[str, Any]) -> BaseModel:
        return self.args_model.model_validate(arguments)


def build_registry() -> dict[str, Tool]:
    return {
        "list_tickets": Tool(
            ToolSpec(
                name="list_tickets",
                description="List tickets from the mock company HTTP API.",
                risk="read",
                args_schema=ListTicketsArgs.model_json_schema(),
            ),
            ListTicketsArgs,
            tickets_api.list_tickets,
        ),
        "get_ticket": Tool(
            ToolSpec(
                name="get_ticket",
                description="Fetch one ticket from the mock company HTTP API.",
                risk="read",
                args_schema=GetTicketArgs.model_json_schema(),
            ),
            GetTicketArgs,
            tickets_api.get_ticket,
        ),
        "list_tickets_browser": Tool(
            ToolSpec(
                name="list_tickets_browser",
                description="List tickets by reading the mock HTML UI with Playwright.",
                risk="read",
                args_schema=ListTicketsArgs.model_json_schema(),
            ),
            ListTicketsArgs,
            tickets_browser.list_tickets_browser,
        ),
        "get_ticket_browser": Tool(
            ToolSpec(
                name="get_ticket_browser",
                description="Fetch one ticket from the mock HTML UI with Playwright.",
                risk="read",
                args_schema=GetTicketArgs.model_json_schema(),
            ),
            GetTicketArgs,
            tickets_browser.get_ticket_browser,
        ),
        "search_policy": Tool(
            ToolSpec(
                name="search_policy",
                description="Search company Markdown policies with BM25 lexical ranking.",
                risk="read",
                args_schema=SearchPolicyArgs.model_json_schema(),
            ),
            SearchPolicyArgs,
            policy_tools.search_policy,
        ),
        "read_policy": Tool(
            ToolSpec(
                name="read_policy",
                description="Read a policy Markdown file by filename.",
                risk="read",
                args_schema=ReadPolicyArgs.model_json_schema(),
            ),
            ReadPolicyArgs,
            policy_tools.read_policy,
        ),
        "save_file": Tool(
            ToolSpec(
                name="save_file",
                description="Write a draft or report under the local workspace.",
                risk="draft",
                args_schema=SaveFileArgs.model_json_schema(),
            ),
            SaveFileArgs,
            file_tools.save_file,
        ),
        "read_file": Tool(
            ToolSpec(
                name="read_file",
                description="Read a file from the local workspace.",
                risk="read",
                args_schema=ReadFileArgs.model_json_schema(),
            ),
            ReadFileArgs,
            file_tools.read_file,
        ),
        "list_files": Tool(
            ToolSpec(
                name="list_files",
                description="List files in a workspace subdirectory.",
                risk="read",
                args_schema=ListFilesArgs.model_json_schema(),
            ),
            ListFilesArgs,
            file_tools.list_files,
        ),
        "request_approval": Tool(
            ToolSpec(
                name="request_approval",
                description="Persist a human approval request and pause consequential work.",
                risk="read",
                args_schema=RequestApprovalArgs.model_json_schema(),
            ),
            RequestApprovalArgs,
            request_approval,
            needs_store=True,
        ),
        "flag_for_review": Tool(
            ToolSpec(
                name="flag_for_review",
                description="Flag a ticket for human review without inventing facts or taking action.",
                risk="read",
                args_schema=FlagReviewArgs.model_json_schema(),
            ),
            FlagReviewArgs,
            flag_for_review,
            needs_store=True,
        ),
        "issue_mock_refund": Tool(
            ToolSpec(
                name="issue_mock_refund",
                description="Simulated refund against local mock SQLite only. Requires matching approved approval.",
                risk="consequential",
                args_schema=IssueRefundArgs.model_json_schema(),
            ),
            IssueRefundArgs,
            tickets_api.issue_mock_refund,
        ),
    }


def invoke_tool(
    registry: dict[str, Tool],
    name: str,
    arguments: dict[str, Any],
    settings: Settings,
    store=None,
    task_id: str | None = None,
) -> ToolResult:
    tool = registry.get(name)
    if tool is None:
        return ToolResult(ok=False, error=f"unknown tool {name}")
    try:
        parsed = tool.parse(arguments)
    except ValidationError as exc:
        return ToolResult(ok=False, error=f"invalid arguments for {name}: {exc}")
    if tool.needs_store:
        if store is None or not task_id:
            return ToolResult(ok=False, error=f"{name} requires task state")
        return tool.handler(store, task_id, parsed)
    return tool.handler(settings, parsed)
