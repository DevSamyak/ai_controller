export default function ApprovalPanel({ approvals, onDecide, busy }) {
  const pending = (approvals || []).filter((item) => item.status === "pending");
  return (
    <section className="card">
      <h2>Approvals</h2>
      {pending.length === 0 ? <p>No pending approvals.</p> : null}
      {pending.map((item) => (
        <div key={item.id}>
          <p>
            <strong>{item.action}</strong> on {item.target_record} ({item.risk})
          </p>
          <p>{item.rationale}</p>
          <p className="mono">{item.arguments_json || JSON.stringify(item.arguments || {})}</p>
          <button disabled={busy} onClick={() => onDecide(item.id, "approved")}>
            Approve
          </button>{" "}
          <button className="danger" disabled={busy} onClick={() => onDecide(item.id, "rejected")}>
            Reject
          </button>
        </div>
      ))}
      {(approvals || [])
        .filter((item) => item.status !== "pending")
        .map((item) => (
          <p key={item.id} className="mono">
            {item.id}: {item.status} · {item.action} · {item.target_record}
          </p>
        ))}
    </section>
  );
}
