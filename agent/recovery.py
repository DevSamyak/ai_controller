from __future__ import annotations

from tools.base import ToolResult
from tools.registry import API_FALLBACKS, invoke_tool


def execute_with_recovery(
    *,
    registry,
    name: str,
    arguments: dict,
    settings,
    store,
    task_id: str,
    log,
) -> tuple[ToolResult, list[dict]]:
    trace: list[dict] = []
    result = invoke_tool(registry, name, arguments, settings, store, task_id)
    trace.append({"tool": name, "ok": result.ok, "error": result.error, "retryable": result.retryable, "attempt": 1})
    log(task_id, "tool_attempt", trace[-1])

    fallback = API_FALLBACKS.get(name)
    if result.ok or fallback is None:
        return result, trace

    attempts = 1
    while not result.ok and result.retryable and attempts <= settings.max_retries:
        attempts += 1
        result = invoke_tool(registry, name, arguments, settings, store, task_id)
        event = {
            "tool": name,
            "ok": result.ok,
            "error": result.error,
            "retryable": result.retryable,
            "attempt": attempts,
        }
        trace.append(event)
        log(task_id, "retry", event)

    if not result.ok and result.retryable:
        fb = invoke_tool(registry, fallback, arguments, settings, store, task_id)
        event = {
            "tool": fallback,
            "ok": fb.ok,
            "error": fb.error,
            "retryable": fb.retryable,
            "attempt": 1,
            "fallback_from": name,
        }
        trace.append(event)
        log(task_id, "browser_fallback", event)
        return fb, trace

    return result, trace
