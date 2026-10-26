const BASE = import.meta.env.VITE_OPERATOR_URL || "http://127.0.0.1:8000";

async function req(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || response.statusText);
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
  eventsUrl: (id) => `${BASE}/tasks/${id}/events`,
};
