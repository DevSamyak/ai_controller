import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import ApprovalPanel from "./ApprovalPanel.jsx";
import EvidencePanel from "./EvidencePanel.jsx";
import PlanPanel from "./PlanPanel.jsx";
import Timeline from "./Timeline.jsx";

const DEFAULT_GOAL =
  "Review all unresolved high-priority support tickets, use our company policies to draft replies, and save a daily summary.";

export default function App() {
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [taskId, setTaskId] = useState("");
  const [snapshot, setSnapshot] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    api.health().then(setHealth).catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!taskId) return undefined;
    refresh(taskId);
    if (sourceRef.current) sourceRef.current.close();
    const source = new EventSource(api.eventsUrl(taskId));
    sourceRef.current = source;
    source.onmessage = () => refresh(taskId);
    source.addEventListener("ping", () => {});
    ["goal", "plan", "decision", "retry", "browser_fallback", "verification", "task_status", "approval_requested"].forEach((type) => {
      source.addEventListener(type, () => refresh(taskId));
    });
    source.onerror = () => refresh(taskId);
    const timer = setInterval(() => refresh(taskId), 1200);
    return () => {
      source.close();
      clearInterval(timer);
    };
  }, [taskId]);

  async function refresh(id) {
    try {
      const data = await api.getTask(id);
      setSnapshot(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setArtifact(null);
    try {
      const created = await api.createTask(goal);
      setTaskId(created.task_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(id, decision) {
    setBusy(true);
    try {
      await api.decide(id, decision);
      await refresh(taskId);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function openArtifact(path) {
    try {
      setArtifact(await api.artifact(path));
    } catch (err) {
      setError(err.message);
    }
  }

  const task = snapshot?.task;

  return (
    <div className="app">
      <header>
        <h1>AI Operator</h1>
        <p className="lede">
          Company operations agent for unresolved high-priority tickets. Mock company is simulated; drafts, approvals,
          retries, and verification are real.
        </p>
        {health ? (
          <p className="mono">
            operator {health.status} · LLM {health.llm_provider}
            {health.llm_configured ? " configured" : " (offline/fake ok)"}
          </p>
        ) : null}
      </header>
      <form className="goal-form" onSubmit={submit}>
        <textarea value={goal} onChange={(event) => setGoal(event.target.value)} />
        <button type="submit" disabled={busy}>
          Run task
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {task ? (
        <p>
          Task <span className="mono">{task.id}</span>{" "}
          <span className={`status ${task.status}`}>{task.status}</span>
          {task.reason ? ` — ${task.reason}` : ""}
        </p>
      ) : null}
      <div className="grid">
        <PlanPanel task={task} steps={snapshot?.steps} />
        <ApprovalPanel approvals={snapshot?.approvals} onDecide={decide} busy={busy} />
        <Timeline events={snapshot?.events} toolCalls={snapshot?.tool_calls} />
        <EvidencePanel snapshot={snapshot} artifact={artifact} onOpen={openArtifact} />
        {snapshot?.flags?.length ? (
          <section className="card wide">
            <h2>Human review flags</h2>
            <ul>
              {snapshot.flags.map((flag) => (
                <li key={flag.id}>
                  {flag.ticket_id}: {flag.category} — {flag.reason}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </div>
  );
}
