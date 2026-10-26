export default function EvidencePanel({ snapshot, artifact, onOpen }) {
  const evidence = snapshot?.evidence || [];
  const latest = evidence.filter((item) => item.kind === "verification" || item.payload?.kind === "verification").at(-1);
  const payload = latest?.payload || latest || {};
  const checks = payload.checks || [];
  const drafted = Object.keys(snapshot?.memory?.drafted || {});
  const report = snapshot?.memory?.report;
  return (
    <section className="card">
      <h2>Verification and outputs</h2>
      <p>
        Verifier:{" "}
        <span className={`status ${payload.passed ? "ok" : "partial"}`}>
          {payload.passed ? "passed" : checks.length ? "failed/pending" : "not run"}
        </span>
      </p>
      <ul>
        {checks.map((check) => (
          <li key={check.name}>
            {check.ok ? "✓" : "✗"} {check.name}
          </li>
        ))}
      </ul>
      <p>Drafts:</p>
      <ul>
        {drafted.map((id) => (
          <li key={id}>
            <button className="secondary" onClick={() => onOpen(`drafts/${id}.md`)}>
              drafts/{id}.md
            </button>
          </li>
        ))}
      </ul>
      {report ? (
        <p>
          <button className="secondary" onClick={() => onOpen(report.relative_path || "reports/daily-summary.md")}>
            {report.relative_path || "reports/daily-summary.md"}
          </button>
        </p>
      ) : null}
      {artifact ? <pre>{artifact.content}</pre> : null}
    </section>
  );
}
