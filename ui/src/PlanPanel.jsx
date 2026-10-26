export default function PlanPanel({ task, steps }) {
  const plan = parsePlan(task?.plan_json);
  return (
    <section className="card">
      <h2>Plan</h2>
      <p>{plan?.summary || "No plan yet."}</p>
      <ol>
        {(plan?.steps || steps || []).map((step, idx) => (
          <li key={step.id || idx}>
            <span className="badge">{step.status || step.tool || "step"}</span>
            {step.purpose || step.expected_output}
          </li>
        ))}
      </ol>
      {plan?.success_conditions?.length ? (
        <>
          <h3>Success conditions</h3>
          <ul>
            {plan.success_conditions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function parsePlan(raw) {
  if (!raw) return null;
  if (typeof raw === "object") return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
