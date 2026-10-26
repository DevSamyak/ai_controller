from __future__ import annotations

from typing import Any

from tools.base import ToolResult


CONSEQUENTIAL_TOOLS = {"issue_mock_refund"}


def check_permission(store, task_id: str, tool_name: str, arguments: dict[str, Any]) -> ToolResult | None:
    if tool_name not in CONSEQUENTIAL_TOOLS:
        return None
    approval = store.matching_approved(task_id, tool_name, arguments)
    if approval is None:
        return ToolResult(
            ok=False,
            error=(
                f"{tool_name} is a consequential action and requires a persisted approval "
                "matching the exact action and arguments. Absent approval is not approval."
            ),
            evidence=[{"kind": "permission_denied", "tool": tool_name, "arguments": arguments}],
        )
    return None
