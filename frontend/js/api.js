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
  calendarContacts: () => request("/calendar/contacts/"),
  rsvp: (id, status) => request(`/events/${id}/rsvp/`, { method: "POST", body: { status } }),
  skipOccurrence: (id, day) => request(`/events/${id}/skip/`, { method: "POST", body: { day } }),
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
  chatSend: (id, content, reply_to = null) => request(`/chat/conversations/${id}/messages/`, { method: "POST", body: reply_to ? { content, reply_to } : { content } }),
  chatEdit: (msgId, content) => request(`/chat/messages/${msgId}/`, { method: "PATCH", body: { content } }),
  chatReact: (msgId, emoji) => request(`/chat/messages/${msgId}/reactions/`, { method: "POST", body: { emoji } }),
  chatSearch: (q) => request(`/chat/search/?${new URLSearchParams({ q })}`),
  /** Envoi avec pièces jointes : multipart (le navigateur fixe lui-même le Content-Type et sa frontière). */
  async chatSendForm(id, form) {
    const call = (token) => fetch(`${BASE}/chat/conversations/${id}/messages/`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form });
    let res = await call(store.get("access"));
    if (res.status === 401 && (await refresh())) res = await call(store.get("access"));
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(errorMessage(data, res.status));
    return data;
  },
  /** Pièce jointe protégée : récupérée avec le jeton, exposée par une URL temporaire (blob). */
  async attachmentUrl(id) {
    const res = await fetch(`${BASE}/chat/attachments/${id}/`, { headers: { Authorization: `Bearer ${store.get("access")}` } });
    if (!res.ok) throw new Error("Fichier indisponible.");
    return URL.createObjectURL(await res.blob());
  },
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

  workload: (pid, weeks = 4) => request(`/projects/${pid}/workload/?weeks=${weeks}`),
  simulate: (pid, delay = 3) => request(`/projects/${pid}/simulate/?delay=${delay}`),
  timeList: (pid, tid) => request(`/projects/${pid}/tasks/${tid}/time/`),
  timeAdd: (pid, tid, body) => request(`/projects/${pid}/tasks/${tid}/time/`, { method: "POST", body }),
  timeStart: (pid, tid) => request(`/projects/${pid}/tasks/${tid}/time/start/`, { method: "POST" }),
  timeDelete: (pid, tid, id) => request(`/projects/${pid}/tasks/${tid}/time/${id}/`, { method: "DELETE" }),
  timer: () => request("/timer/"),
  timerStop: () => request("/timer/", { method: "POST" }),
  timeReport: (pid) => request(`/projects/${pid}/time-report/`),
  templates: () => request("/templates/"),
  fromTemplate: (body) => request("/projects/from-template/", { method: "POST", body }),
  saveTemplate: (pid, body) => request(`/projects/${pid}/save-template/`, { method: "POST", body }),
  deleteTemplate: (id) => request(`/templates/${id}/`, { method: "DELETE" }),
  members: (pid) => request(`/projects/${pid}/members/`),
  addMember: (pid, body) => request(`/projects/${pid}/members/`, { method: "POST", body }),
  setRole: (pid, uid, role) => request(`/projects/${pid}/members/${uid}/`, { method: "PATCH", body: { role } }),
  removeMember: (pid, uid) => request(`/projects/${pid}/members/${uid}/`, { method: "DELETE" }),
  memberCandidates: (pid, q) => request(`/projects/${pid}/member-candidates/?q=${encodeURIComponent(q)}`),
  invites: (pid) => request(`/projects/${pid}/invites/`),
  createInvite: (pid, body) => request(`/projects/${pid}/invites/`, { method: "POST", body }),
  revokeInvite: (pid, id) => request(`/projects/${pid}/invites/${id}/`, { method: "DELETE" }),
  invitePreview: (token) => request(`/invites/${encodeURIComponent(token)}/`, { anon: true }),
  acceptInvite: (token) => request(`/invites/${encodeURIComponent(token)}/accept/`, { method: "POST" }),

  comments: (pid, tid) => request(`/projects/${pid}/tasks/${tid}/comments/`),
  addComment: (pid, tid, content) =>
    request(`/projects/${pid}/tasks/${tid}/comments/`, { method: "POST", body: { content } }),
};
