const BASE = window.TASKFLOW_API || "http://localhost:8000/api";

const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* stockage indisponible */ } },
  del: (k) => { try { localStorage.removeItem(k); } catch { /* stockage indisponible */ } },
};

let onLogout = () => {};

export const auth = {
  isLoggedIn: () => !!store.get("access"),
  onLogout: (fn) => { onLogout = fn; },
  logout() { store.del("access"); store.del("refresh"); },
  pref: store,
};

function errorMessage(data, status) {
  if (!data) return `Erreur ${status}`;
  if (typeof data === "string") return data;
  if (data.detail) return data.detail;
  return Object.entries(data)
    .map(([k, v]) => `${k === "non_field_errors" ? "" : k + " : "}${[].concat(v).join(" ")}`)
    .join("\n");
}

async function raw(path, { method = "GET", body, token } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  return { res, data };
}

async function refresh() {
  const refreshToken = store.get("refresh");
  if (!refreshToken) return false;
  const { res, data } = await raw("/auth/refresh/", { method: "POST", body: { refresh: refreshToken } });
  if (!res.ok) return false;
  store.set("access", data.access);
  if (data.refresh) store.set("refresh", data.refresh);
  return true;
}

async function request(path, opts = {}) {
  let { res, data } = await raw(path, { ...opts, token: opts.anon ? null : store.get("access") });
  if (res.status === 401 && !opts.anon && (await refresh())) {
    ({ res, data } = await raw(path, { ...opts, token: store.get("access") }));
  }
  if (res.status === 401 && !opts.anon) {
    auth.logout();
    onLogout();
  }
  if (!res.ok) throw new Error(errorMessage(data, res.status));
  return data;
}

export const api = {
  async login(username, password) {
    const t = await request("/auth/token/", { method: "POST", body: { username, password }, anon: true });
    store.set("access", t.access);
    store.set("refresh", t.refresh);
  },
  register: (body) => request("/auth/register/", { method: "POST", body, anon: true }),
  me: () => request("/me/"),
  deleteAccount: (password) => request("/me/", { method: "DELETE", body: { password } }),
  transferProject: (pid, user_id) => request(`/projects/${pid}/transfer/`, { method: "POST", body: { user_id } }),
  /** Télécharge un fichier JSON protégé : fetch avec le jeton, puis lien temporaire. */
  async downloadExport() {
    const res = await fetch(BASE + "/me/export/", { headers: { Authorization: `Bearer ${store.get("access")}` } });
    if (!res.ok) throw new Error(errorMessage(await res.json().catch(() => null), res.status));
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "taskflow-mes-donnees.json" });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  updateMe: (body) => request("/me/", { method: "PATCH", body }),
  calendar: (q) => request(`/calendar/?${new URLSearchParams(q)}`),
  createEvent: (body) => request("/events/", { method: "POST", body }),
  updateEvent: (id, body) => request(`/events/${id}/`, { method: "PATCH", body }),
  deleteEvent: (id) => request(`/events/${id}/`, { method: "DELETE" }),

  projects: () => request("/projects/"),
  createProject: (body) => request("/projects/", { method: "POST", body }),
  updateProject: (id, body) => request(`/projects/${id}/`, { method: "PATCH", body }),
  deleteProject: (id) => request(`/projects/${id}/`, { method: "DELETE" }),

  tasks: (pid) => request(`/projects/${pid}/tasks/`),
  createTask: (pid, body) => request(`/projects/${pid}/tasks/`, { method: "POST", body }),
  updateTask: (pid, id, body) => request(`/projects/${pid}/tasks/${id}/`, { method: "PATCH", body }),
  deleteTask: (pid, id) => request(`/projects/${pid}/tasks/${id}/`, { method: "DELETE" }),

  publicConfig: () => request("/auth/config/", { anon: true }),

  // --- administration
  adminStats: () => request("/admin/stats/"),
  adminUsers: (p = {}) => request(`/admin/users/?${new URLSearchParams(Object.entries(p).filter(([, v]) => v))}`),
  adminUser: (id) => request(`/admin/users/${id}/`),
  adminCreateUser: (body) => request("/admin/users/", { method: "POST", body }),
  adminUpdateUser: (id, body) => request(`/admin/users/${id}/`, { method: "PATCH", body }),
  adminResetPassword: (id, body) => request(`/admin/users/${id}/reset-password/`, { method: "POST", body: body || {} }),
  adminDeleteUser: (id, q = {}) => request(`/admin/users/${id}/?${new URLSearchParams(Object.entries(q).filter(([, v]) => v))}`, { method: "DELETE" }),
  adminProjects: (q = "") => request(`/admin/projects/?${new URLSearchParams(q ? { q } : {})}`),
  adminDeleteProject: (id) => request(`/admin/projects/${id}/`, { method: "DELETE" }),
  adminTransferProject: (id, user_id) => request(`/admin/projects/${id}/transfer/`, { method: "POST", body: { user_id } }),
  adminAudit: (p = {}) => request(`/admin/audit/?${new URLSearchParams(Object.entries(p).filter(([, v]) => v))}`),
  adminSettings: () => request("/admin/settings/"),
  adminSetSettings: (body) => request("/admin/settings/", { method: "PATCH", body }),

  chatConversations: () => request("/chat/conversations/"),
  chatMessages: (id, q = {}) => request(`/chat/conversations/${id}/messages/?${new URLSearchParams(q)}`),
  chatSend: (id, content) => request(`/chat/conversations/${id}/messages/`, { method: "POST", body: { content } }),
  chatRead: (id) => request(`/chat/conversations/${id}/read/`, { method: "POST" }),
  chatDelete: (msgId) => request(`/chat/messages/${msgId}/`, { method: "DELETE" }),
  chatDirect: (user) => request("/chat/direct/", { method: "POST", body: { user } }),
  chatContacts: () => request("/chat/contacts/"),
  chatSummary: () => request("/chat/summary/"),
  notifications: () => request("/notifications/"),
  markNotifications: (body) => request("/notifications/", { method: "POST", body }),

  dashboard: () => request("/dashboard/"),
  insights: (pid) => request(`/projects/${pid}/insights/`),
  replan: (pid) => request(`/projects/${pid}/replan/`, { method: "POST" }),

  members: (pid) => request(`/projects/${pid}/members/`),
  addMember: (pid, body) => request(`/projects/${pid}/members/`, { method: "POST", body }),
  setRole: (pid, uid, role) => request(`/projects/${pid}/members/${uid}/`, { method: "PATCH", body: { role } }),
  removeMember: (pid, uid) => request(`/projects/${pid}/members/${uid}/`, { method: "DELETE" }),

  comments: (pid, tid) => request(`/projects/${pid}/tasks/${tid}/comments/`),
  addComment: (pid, tid, content) =>
    request(`/projects/${pid}/tasks/${tid}/comments/`, { method: "POST", body: { content } }),
};
