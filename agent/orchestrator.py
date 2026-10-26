from __future__ import annotations

from typing import Any

from agent.evidence import JsonlLogger, build_report
from agent.llm import LLMProvider, make_llm
from agent.permissions import check_permission
from agent.recovery import execute_with_recovery
from agent.settings import Settings, load_settings
from agent.state import TaskStore, new_id
from agent.verifier import verify_task
from tools.base import ToolResult
from tools.registry import build_registry


class Orchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        store: TaskStore | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.settings.ensure_dirs()
        self.store = store or TaskStore(self.settings.database_path)
        self.llm = make_llm(self.settings, llm)
        self.registry = build_registry()
        self.logger = JsonlLogger(self.settings)
        self.memories: dict[str, dict[str, Any]] = {}

    def _memory(self, task_id: str) -> dict[str, Any]:
        return self.memories.setdefault(
            task_id,
            {
                "list": None,
                "tickets": {},
                "policies": {},
                "drafted": {},
                "flags": {},
                "skipped": {},
                "approvals": {},
                "refunded": {},
                "report": None,
                "policy_target": None,
            },
        )

    def _log(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.logger.write(task_id, event_type, payload)
        self.store.emit(task_id, event_type, payload)

    def submit(self, goal: str) -> dict[str, Any]:
        task = self.store.create_task(goal)
        self._log(task["id"], "goal", {"goal": goal})
        return task

    def run(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        if task["status"] in {"queued"}:
            self.store.set_status(task_id, "running")
        elif task["status"] == "waiting_approval":
            self.store.set_status(task_id, "running", "resumed after approval decision")
        elif task["status"] not in {"running"}:
            return self.snapshot(task_id)

        if not task.get("plan_json"):
            plan = self.llm.plan(task["goal"], {})
            self.store.save_plan(task_id, plan.model_dump())
            self._log(task_id, "plan", plan.model_dump())

        steps = 0
        last_observation: dict[str, Any] | None = None
        while steps < self.settings.max_steps:
            steps += 1
            snapshot = self._llm_snapshot(task_id, last_observation)
            action = self.llm.next_action(snapshot)
            self._log(task_id, "decision", {"type": action.type, "tool": action.tool, "reason": action.reason})

            if action.type == "wait_approval":
                self.store.set_status(task_id, "waiting_approval", action.reason)
                return self.snapshot(task_id)
            if action.type == "finish":
                return self._complete(task_id)
            if action.type != "tool" or not action.tool:
                self.store.set_status(task_id, "failed", "model returned an invalid action")
                return self.snapshot(task_id)

            denied = check_permission(self.store, task_id, action.tool, action.arguments or {})
            if denied is not None:
                result = denied
                recovery_trace: list[dict] = []
            else:
                result, recovery_trace = execute_with_recovery(
                    registry=self.registry,
                    name=action.tool,
                    arguments=action.arguments or {},
                    settings=self.settings,
                    store=self.store,
                    task_id=task_id,
                    log=self._log,
                )

            result_dict = result.model_dump()
            self.store.record_tool_call(task_id, action.tool, action.arguments or {}, result_dict, attempt=1)
            last_observation = {
                "tool": action.tool,
                "arguments": action.arguments,
                "result": result_dict,
                "recovery": recovery_trace,
            }
            self._ingest(task_id, action.tool, action.arguments or {}, result)

            if action.tool in {"list_tickets", "get_ticket"} and not result.ok:
                both_failed = any(item.get("tool", "").endswith("browser") and not item.get("ok") for item in recovery_trace)
                if both_failed or not result.retryable:
                    self.store.set_status(
                        task_id,
                        "blocked",
                        result.error or "ticket source unavailable; no records invented",
                    )
                    return self.snapshot(task_id)

            if action.tool == "request_approval" and result.ok:
                approval = (result.data or {}).get("approval") if isinstance(result.data, dict) else None
                if approval and approval.get("status") == "pending":
                    self.store.set_status(task_id, "waiting_approval", "high-value action requires human approval")
                    return self.snapshot(task_id)

        self.store.set_status(task_id, "blocked", f"exceeded MAX_STEPS={self.settings.max_steps}")
        return self.snapshot(task_id)

    def _ingest(self, task_id: str, tool: str, arguments: dict[str, Any], result: ToolResult) -> None:
        mem = self._memory(task_id)
        data = result.data if isinstance(result.data, dict) else {}
        if tool in {"list_tickets", "list_tickets_browser"} and result.ok:
            tickets = data.get("tickets") or []
            mem["list"] = data
            mem["tickets"] = {t["id"]: None for t in tickets}
        elif tool in {"get_ticket", "get_ticket_browser"} and result.ok:
            ticket = data.get("ticket") or {}
            mem["tickets"][ticket["id"]] = ticket
        elif tool == "search_policy" and result.ok:
            pending = [tid for tid, ticket in mem["tickets"].items() if tid not in mem["policies"]]
            if pending:
                mem["policies"][pending[0]] = data
        elif tool == "flag_for_review" and result.ok:
            flag = data.get("flag") or {}
            mem["flags"][flag.get("ticket_id")] = flag
        elif tool == "request_approval" and result.ok:
            approval = data.get("approval") or {}
            mem["approvals"][approval.get("target_record")] = approval
        elif tool == "issue_mock_refund" and result.ok:
            mem["refunded"][arguments.get("ticket_id")] = data
        elif tool == "save_file" and result.ok:
            rel = arguments.get("relative_path") or ""
            if rel.startswith("drafts/"):
                ticket_id = PathStem(rel)
                digest = (data or {}).get("sha256") or ""
                reused = self.store.remember_draft(task_id, ticket_id, digest, data.get("path", ""))
                mem["drafted"][ticket_id] = {**data, "reused": reused or data.get("reused")}
            elif rel.startswith("reports/"):
                mem["report"] = data

    def _complete(self, task_id: str) -> dict[str, Any]:
        mem = self._memory(task_id)
        verification = verify_task(self.settings, self.store, task_id, mem)
        report = build_report(self.store, task_id, mem, verification)
        report_path = self.settings.reports_path / "daily-summary.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        mem["report"] = {"path": str(report_path), "relative_path": "reports/daily-summary.md"}
        verification = verify_task(self.settings, self.store, task_id, mem)
        self.store.add_evidence(task_id, {"kind": "verification", **verification})
        self._log(task_id, "verification", verification)
        if verification["passed"]:
            self.store.set_status(task_id, "complete", "verifier passed")
        else:
            failed = [c["name"] for c in verification["checks"] if not c["ok"]]
            self.store.set_status(task_id, "partial", "verifier failed: " + ", ".join(failed))
        return self.snapshot(task_id)

    def reverify(self, task_id: str) -> dict[str, Any]:
        mem = self._memory(task_id)
        verification = verify_task(self.settings, self.store, task_id, mem)
        self.store.add_evidence(task_id, {"kind": "verification", **verification})
        self._log(task_id, "verification", verification)
        status = self.store.get_task(task_id)["status"]
        if verification["passed"] and status != "complete":
            if status == "running":
                self.store.set_status(task_id, "complete", "verifier passed")
        if not verification["passed"] and status == "complete":
            failed = [c["name"] for c in verification["checks"] if not c["ok"]]
            self.store.set_status(task_id, "partial", "verifier failed after artifact change: " + ", ".join(failed))
        return verification

    def snapshot(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        return {
            "task": task,
            "steps": self.store.list_steps(task_id),
            "approvals": self.store.list_approvals(task_id),
            "flags": self.store.list_flags(task_id),
            "evidence": self.store.list_evidence(task_id),
            "tool_calls": self.store.list_tool_calls(task_id),
            "events": self.store.list_events(task_id),
            "memory": self._memory(task_id),
        }

    def _llm_snapshot(self, task_id: str, last_observation: dict[str, Any] | None) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        mem = self._memory(task_id)
        for approval in self.store.list_approvals(task_id):
            mem["approvals"][approval["target_record"]] = approval
        for flag in self.store.list_flags(task_id):
            mem["flags"][flag["ticket_id"]] = flag
        specs = [{"name": t.spec.name, "description": t.spec.description, "risk": t.spec.risk} for t in self.registry.values()]
        return {
            "goal": task["goal"],
            "status": task["status"],
            "memory": mem,
            "last_observation": last_observation,
            "settings": {"refund_approval_threshold": self.settings.refund_approval_threshold},
            "tool_specs": specs,
        }


def PathStem(relative_path: str) -> str:
    name = relative_path.rsplit("/", 1)[-1]
    return name[:-3] if name.endswith(".md") else name


def run_goal(goal: str, settings: Settings | None = None, llm: LLMProvider | None = None) -> dict[str, Any]:
    orch = Orchestrator(settings=settings, llm=llm)
    task = orch.submit(goal)
    return orch.run(task["id"])
