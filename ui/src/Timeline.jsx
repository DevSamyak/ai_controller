export default function Timeline({ events, toolCalls }) {
  return (
    <section className="card">
      <h2>Tool activity</h2>
      <ul className="list">
        {(toolCalls || []).slice(-20).reverse().map((call) => (
          <li key={call.id}>
            <span className={`badge ${call.ok ? "ok" : ""}`}>{call.tool}</span>
            {call.ok ? "ok" : call.error || "failed"}
            {call.attempt > 1 ? ` · attempt ${call.attempt}` : ""}
          </li>
        ))}
      </ul>
      <h3>Events</h3>
      <ul className="list">
        {(events || []).slice(-30).reverse().map((event) => (
          <li key={event.id} className="mono">
            {event.type}
            {event.payload?.tool ? ` · ${event.payload.tool}` : ""}
            {event.payload?.error ? ` · ${event.payload.error}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
