import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { api } from "./api.js";

const DEFAULT_GOAL =
  "Review all unresolved high-priority support tickets, use our company policies to draft replies, and save a daily summary.";

export default function App() {
  const [health, setHealth] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [taskData, setTaskData] = useState(null);
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [liveEvents, setLiveEvents] = useState([]);
  const [artifactModal, setArtifactModal] = useState(null);

  const eventSourceRef = useRef(null);
  const isFetchingRef = useRef(false);
  const debounceTimerRef = useRef(null);

  // Fetch task list and backend health (throttled)
  const refreshTasks = useCallback(async () => {
    try {
      const h = await api.health();
      setHealth((prev) => (prev?.status === h.status && prev?.llm_provider === h.llm_provider ? prev : h));

      const res = await api.listTasks();
      if (res.tasks) {
        setTasks((prev) => {
          if (prev.length === res.tasks.length && prev[0]?.id === res.tasks[0]?.id && prev[0]?.status === res.tasks[0]?.status) {
            return prev;
          }
          return res.tasks;
        });
        setCurrentTaskId((curr) => curr || (res.tasks.length > 0 ? res.tasks[0].id : null));
      }
    } catch (err) {
      setError(err.message || "Failed to connect to backend");
    }
  }, []);

  useEffect(() => {
    refreshTasks();
    const interval = setInterval(refreshTasks, 6000);
    return () => clearInterval(interval);
  }, [refreshTasks]);

  // Fetch full snapshot with in-flight lock to avoid concurrent thrashing
  const fetchTaskDetails = useCallback(async (id) => {
    if (!id || isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const snap = await api.getTask(id);
      setTaskData(snap);
    } catch (err) {
      console.error("Error fetching task details:", err);
    } finally {
      isFetchingRef.current = false;
    }
  }, []);

  // Debounced snapshot scheduler for bursts of SSE events
  const scheduleFetch = useCallback((id, delay = 400) => {
    if (!id) return;
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchTaskDetails(id);
    }, delay);
  }, [fetchTaskDetails]);

  // Set up SSE stream for currentTaskId
  useEffect(() => {
    if (!currentTaskId) return;

    fetchTaskDetails(currentTaskId);
    setLiveEvents([]);

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const url = api.eventsUrl(currentTaskId);
      const es = new EventSource(url);
      eventSourceRef.current = es;

      const handleEvent = (parsed, evType) => {
        setLiveEvents((prev) => [parsed, ...prev.slice(0, 49)]);

        // Important state transitions refresh immediately; tool steps are debounced
        if (evType === "task_status" || evType === "approval_requested" || evType === "verification") {
          fetchTaskDetails(currentTaskId);
        } else {
          scheduleFetch(currentTaskId, 450);
        }
      };

      es.onmessage = (e) => {
        try {
          const parsed = JSON.parse(e.data);
          handleEvent(parsed, "message");
        } catch (_) {}
      };

      // Heartbeat pings: do NOT fetch details, just keep connection alive
      es.addEventListener("ping", () => {});

      // Custom event listeners
      [
        "task_created",
        "task_status",
        "plan",
        "tool_call",
        "tool_attempt",
        "decision",
        "review_flag",
        "approval_requested",
        "browser_fallback",
        "retry",
        "verification",
      ].forEach((evType) => {
        es.addEventListener(evType, (e) => {
          try {
            const parsed = JSON.parse(e.data);
            handleEvent(parsed, evType);
          } catch (_) {}
        });
      });

      es.onerror = () => {
        // Fallback polling will handle updates
      };
    } catch (e) {
      console.error("SSE connection error:", e);
    }

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [currentTaskId, fetchTaskDetails, scheduleFetch]);

  // Light fallback polling only when the task is actively running or queued
  const taskStatus = taskData?.task?.status;
  useEffect(() => {
    if (!currentTaskId) return;
    if (taskStatus !== "running" && taskStatus !== "queued") return;

    const interval = setInterval(() => {
      fetchTaskDetails(currentTaskId);
    }, 3000);
    return () => clearInterval(interval);
  }, [currentTaskId, taskStatus, fetchTaskDetails]);

  const handleSubmitTask = async (e) => {
    e.preventDefault();
    if (!goal.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.createTask(goal);
      if (res.task_id) {
        setCurrentTaskId(res.task_id);
        refreshTasks();
        fetchTaskDetails(res.task_id);
      }
    } catch (err) {
      setError(err.message || "Failed to submit task");
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = async (approvalId, decision) => {
    setLoading(true);
    try {
      await api.decide(approvalId, decision);
      if (currentTaskId) {
        await fetchTaskDetails(currentTaskId);
      }
    } catch (err) {
      setError(`Approval decision failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const viewArtifact = async (path) => {
    try {
      const res = await api.artifact(path);
      setArtifactModal({ path, content: res.content });
    } catch (err) {
      setError(`Failed to read artifact ${path}: ${err.message}`);
    }
  };

  const task = taskData?.task;
  const approvals = taskData?.approvals || [];
  const flags = taskData?.flags || [];
  const evidence = taskData?.evidence || [];
  const toolCalls = taskData?.tool_calls || [];
  const memory = taskData?.memory || {};

  const verificationEvidence = useMemo(
    () => evidence.find((e) => e.kind === "verification"),
    [evidence]
  );

  const parsedPlan = useMemo(() => {
    if (!task?.plan_json) return null;
    try {
      return typeof task.plan_json === "string" ? JSON.parse(task.plan_json) : task.plan_json;
    } catch (_) {
      return null;
    }
  }, [task?.plan_json]);

  const pendingApprovals = useMemo(
    () => approvals.filter((a) => a.status === "pending"),
    [approvals]
  );

  const displayedToolCalls = useMemo(
    () => toolCalls.slice(-30).reverse(),
    [toolCalls]
  );

  return (
    <div className="container">
      {/* Header */}
      <header className="header">
        <div className="brand">
          <h1>🤖 Autonomous AI Operator</h1>
          <span className="subtitle">Company Operations Dashboard</span>
        </div>
        <div className="header-meta">
          <div className="health-badge">
            <span className={`status-dot ${health?.status === "ok" ? "green" : "red"}`}></span>
            Backend: {health?.status === "ok" ? "Connected" : "Disconnected"}
          </div>
          <div className="provider-tag">
            Provider: <strong>{health?.llm_provider || "unknown"}</strong>
          </div>
        </div>
      </header>

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
          <button className="btn-close" onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Main Grid */}
      <div className="layout-grid">
        {/* Left Column: Task Submission & Task List */}
        <section className="column">
          <div className="card">
            <h2>Submit Task</h2>
            <form onSubmit={handleSubmitTask}>
              <div className="form-group">
                <label htmlFor="goal-input">Goal</label>
                <textarea
                  id="goal-input"
                  rows={4}
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  placeholder="Enter task goal..."
                />
              </div>
              <div className="button-group">
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? "Submitting..." : "Execute Goal"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setGoal(DEFAULT_GOAL)}
                >
                  Reset Default
                </button>
              </div>
            </form>
          </div>

          <div className="card">
            <div className="card-header-flex">
              <h2>Recent Tasks</h2>
              <button className="btn-text" onClick={refreshTasks}>Refresh</button>
            </div>
            {tasks.length === 0 ? (
              <p className="empty-text">No tasks submitted yet.</p>
            ) : (
              <ul className="task-list">
                {tasks.map((t) => (
                  <li
                    key={t.id}
                    className={`task-item ${t.id === currentTaskId ? "active" : ""}`}
                    onClick={() => setCurrentTaskId(t.id)}
                  >
                    <div className="task-header-row">
                      <span className="task-id">{t.id}</span>
                      <span className={`status-pill status-${t.status}`}>{t.status}</span>
                    </div>
                    <div className="task-preview">{t.goal}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Middle & Right: Active Task Details */}
        <section className="column-wide">
          {!task ? (
            <div className="card empty-card">
              <p>Select a task or submit a new goal to view execution details.</p>
            </div>
          ) : (
            <>
              {/* Task Overview Card */}
              <div className="card">
                <div className="card-header-flex">
                  <div>
                    <span className="task-id-large">{task.id}</span>
                    <span className={`status-badge status-${task.status}`}>{task.status}</span>
                  </div>
                  {task.updated_at && <span className="timestamp">{task.updated_at}</span>}
                </div>
                <p className="task-goal-text"><strong>Goal:</strong> {task.goal}</p>
                {task.reason && (
                  <p className="task-reason"><strong>Reason:</strong> {task.reason}</p>
                )}
              </div>

              {/* Pending Approvals Card */}
              {pendingApprovals.length > 0 && (
                <div className="card approval-card">
                  <h2 className="alert-title">⚠️ Human Approval Required</h2>
                  {pendingApprovals.map((a) => (
                    <div key={a.id} className="approval-item">
                      <div className="approval-details">
                        <p><strong>Action:</strong> <code>{a.action}</code> ({a.risk || "high-risk"})</p>
                        <p><strong>Target:</strong> {a.target_record}</p>
                        <p><strong>Rationale:</strong> {a.rationale}</p>
                        {a.arguments && (
                          <pre className="code-block">{JSON.stringify(a.arguments, null, 2)}</pre>
                        )}
                      </div>
                      <div className="approval-actions">
                        <button
                          className="btn btn-success"
                          onClick={() => handleDecision(a.id, "approved")}
                          disabled={loading}
                        >
                          Approve
                        </button>
                        <button
                          className="btn btn-danger"
                          onClick={() => handleDecision(a.id, "rejected")}
                          disabled={loading}
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Plan Card */}
              {parsedPlan && (
                <div className="card">
                  <h2>Execution Plan</h2>
                  {parsedPlan.summary && <p className="plan-summary">{parsedPlan.summary}</p>}
                  {parsedPlan.steps && parsedPlan.steps.length > 0 && (
                    <ol className="plan-steps">
                      {parsedPlan.steps.map((step, idx) => (
                        <li key={idx}>
                          <strong>{step.title || step.description || `Step ${idx + 1}`}</strong>
                          {step.details && <p>{step.details}</p>}
                        </li>
                      ))}
                    </ol>
                  )}
                  {parsedPlan.success_conditions && (
                    <div className="success-conditions">
                      <strong>Success Conditions:</strong>
                      <ul>
                        {parsedPlan.success_conditions.map((sc, i) => (
                          <li key={i}>{sc}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Verification & Artifacts Card */}
              <div className="card">
                <h2>Verification & Output Artifacts</h2>
                {verificationEvidence ? (
                  <div className={`verification-box ${verificationEvidence.passed ? "passed" : "failed"}`}>
                    <div className="verification-header">
                      <strong>Status: {verificationEvidence.passed ? "PASSED ✅" : "FAILED ❌"}</strong>
                    </div>
                    {verificationEvidence.checks && (
                      <ul className="checks-list">
                        {verificationEvidence.checks.map((chk, i) => (
                          <li key={i} className={chk.ok ? "check-ok" : "check-fail"}>
                            {chk.ok ? "✓" : "✗"} <strong>{chk.name}:</strong> {chk.detail || (chk.ok ? "Passed" : "Failed")}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : (
                  <p className="subtle-text">Verification runs upon task completion.</p>
                )}

                {/* Artifact Links */}
                <div className="artifacts-section">
                  <h3>Generated Files</h3>
                  <div className="artifact-links">
                    {memory.report && (
                      <button
                        className="btn-link"
                        onClick={() => viewArtifact("reports/daily-summary.md")}
                      >
                        📄 Daily Summary (reports/daily-summary.md)
                      </button>
                    )}
                    {memory.drafted && Object.keys(memory.drafted).length > 0 && (
                      <div className="drafts-group">
                        <span className="drafts-title">Drafts:</span>
                        {Object.keys(memory.drafted).map((tid) => (
                          <button
                            key={tid}
                            className="btn-link"
                            onClick={() => viewArtifact(`drafts/${tid}.md`)}
                          >
                            📝 {tid}.md
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Flags Section */}
                {flags.length > 0 && (
                  <div className="flags-section">
                    <h3>Flagged for Review</h3>
                    <ul className="flag-list">
                      {flags.map((fl, i) => (
                        <li key={i} className="flag-item">
                          <span className="flag-pill">{fl.category}</span>
                          <strong>Ticket {fl.ticket_id}:</strong> {fl.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Tool Activity Logs */}
              <div className="card">
                <div className="card-header-flex">
                  <h2>Tool Activity & Observations</h2>
                  <span className="count-pill">{toolCalls.length} calls</span>
                </div>
                {toolCalls.length === 0 ? (
                  <p className="empty-text">No tool activity recorded yet.</p>
                ) : (
                  <div className="tool-calls-container">
                    {displayedToolCalls.map((tc, idx) => (
                      <div key={tc.id || idx} className={`tool-call-row ${tc.result?.ok ? "ok" : "fail"}`}>
                        <div className="tool-call-header">
                          <span className="tool-name">⚡ {tc.tool}</span>
                          <span className={`pill ${tc.result?.ok ? "pill-success" : "pill-fail"}`}>
                            {tc.result?.ok ? "SUCCESS" : "FAILED"}
                          </span>
                          <span className="call-time">{tc.created_at}</span>
                        </div>
                        {tc.arguments && Object.keys(tc.arguments).length > 0 && (
                          <div className="tool-args">
                            <strong>Args:</strong>
                            <code>{JSON.stringify(tc.arguments)}</code>
                          </div>
                        )}
                        {tc.result?.error && (
                          <div className="tool-error">
                            <strong>Error:</strong> {tc.result.error}
                          </div>
                        )}
                        {tc.result?.data && (
                          <details className="tool-details">
                            <summary>View Data</summary>
                            <pre>{JSON.stringify(tc.result.data, null, 2)}</pre>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Live Events Stream */}
              {liveEvents.length > 0 && (
                <div className="card">
                  <h2>Live Events Stream (SSE)</h2>
                  <div className="events-stream">
                    {liveEvents.slice(0, 20).map((ev, i) => (
                      <div key={ev.id || i} className="event-row">
                        <span className="event-type">{ev.type || "event"}</span>
                        <span className="event-time">{ev.created_at}</span>
                        <pre className="event-payload">
                          {JSON.stringify(ev.payload || ev, null, 1)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {/* Artifact Preview Modal */}
      {artifactModal && (
        <div className="modal-backdrop" onClick={() => setArtifactModal(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{artifactModal.path}</h3>
              <button className="btn-close" onClick={() => setArtifactModal(null)}>×</button>
            </div>
            <div className="modal-body">
              <pre className="artifact-body">{artifactModal.content}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
