const BASE = import.meta.env.VITE_OPERATOR_URL || "http://127.0.0.1:8000";

async function req(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch (err) {
    throw new Error(`Unable to connect to operator API: ${err.message}`);
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    let msg = response.statusText;
    if (data.detail) {
      if (Array.isArray(data.detail)) {
        msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      } else if (typeof data.detail === "object") {
        msg = JSON.stringify(data.detail);
      } else {
        msg = String(data.detail);
      }
    }
    throw new Error(msg || `Request failed with HTTP ${response.status}`);
  }
  return data;
}

export const api = {
  health: () => req("/health"),
  createTask: (goal) => req("/tasks", { method: "POST", body: JSON.stringify({ goal }) }),
  getTask: (id) => req(`/tasks/${id}`),
  listTasks: () => req("/tasks"),
  decide: (id, decision) => req(`/approvals/${id}`, { method: "POST", body: JSON.stringify({ decision }) }),
  artifact: (path) => req(`/artifacts?path=${encodeURIComponent(path)}`),
  eventsUrl: (id, afterId = 0) => `${BASE}/tasks/${id}/events${afterId ? `?after_id=${afterId}` : ""}`,
};
