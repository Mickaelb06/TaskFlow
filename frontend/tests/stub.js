// Faux navigateur minimal (DOM + fetch + localStorage) pour exécuter le front hors navigateur.
// Utilisé par smoke.test.js avec JavaScriptCore (`jsc`, présent sur macOS). Ne remplace pas un vrai test E2E.
const els = {};
const mk = (sel) => (els[sel] ??= {
  sel, innerHTML: "", hidden: false, textContent: "", open: false, dataset: {},
  classList: { add() {}, remove() {}, toggle() {} }, addEventListener() {},
  querySelector: (q) => (q === "form" ? { addEventListener() {} } : null), querySelectorAll: () => [],
  showModal() { this.open = true; }, close() { this.open = false; }, focus() {}, setSelectionRange() {}, style: {}, scrollHeight: 30, scrollTop: 0, clientHeight: 100,
});
globalThis.__els = els;
globalThis.__calls = [];
globalThis.__handlers = {};
globalThis.window = globalThis;
globalThis.TASKFLOW_API = "http://x/api";
const mem = { access: "tok", refresh: "r" };
globalThis.localStorage = { getItem: (k) => mem[k] ?? null, setItem: (k, v) => (mem[k] = String(v)), removeItem: (k) => delete mem[k] };
globalThis.document = {
  documentElement: { dataset: {} }, querySelector: mk, querySelectorAll: () => [],
  addEventListener: (t, f) => (__handlers[t] ??= []).push(f),
};
globalThis.location = { get pathname() { return globalThis.__path || "/"; }, reload() {} };
globalThis.matchMedia = () => ({ matches: false });
globalThis.URLSearchParams = class {
  constructor(init = {}) { this.pairs = Array.isArray(init) ? init : Object.entries(init); }
  toString() { return this.pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&"); }
};
globalThis.setInterval = () => 0; // jsc n'a pas de minuteries
globalThis.setTimeout = globalThis.setTimeout || (() => 0);
globalThis.clearTimeout = globalThis.clearTimeout || (() => {});
globalThis.navigator = { clipboard: { writeText: async () => {} } };

const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const now = new Date();
const day = (n) => iso(new Date(now.getFullYear(), now.getMonth(), now.getDate() + n));
const dt = (n) => new Date(Date.now() + n * 86400000).toISOString();
globalThis.__day = day;

const task = (id, title, o = {}) => ({ recurrence: "", time_minutes: 0, id, title, status: "todo", priority: 2, start_date: null, due_date: null, dependencies: [], assignee: null,
  assignee_name: null, is_milestone: false, description: "", completed_at: null, ...o });
const brief = (id, title, o = {}) => ({ id, title, status: "todo", start: null, due: null, days_late: 0, ...o });

// 10 h (heure de Paris) le jour `n`, en instant ISO UTC : déterministe quelle que soit l'heure d'exécution
import * as TZ from "../js/tz.js";
const at = (n, h, mi = 0, tz = "Europe/Paris") => {
  const p = TZ.parts(new Date(now.getFullYear(), now.getMonth(), now.getDate() + n, 12), tz);
  const guess = Date.UTC(p.y, p.m - 1, p.d, h, mi);
  return new Date(guess - TZ.offsetMinutes(tz, new Date(guess)) * 60000).toISOString();
};
const ev = (id, title, a, b, o = {}) => ({ id, title, description: "", starts_at: a, ends_at: b, timezone: "Europe/Paris", project: 7,
  project_name: "Projet <b>A</b>", creator: 1, creator_name: "alice", can_edit: true, ...o });


const bob = { id: 2, username: "bob" };
const alice = { id: 1, username: "alice" };
const carol = { id: 3, username: "carol" };
const conv = (id, o) => ({ id, kind: "project", title: "x", project: null, other: null, solo: false, can_write: true, members: [alice, bob, carol], unread: 0, last: null, ...o });
const msg = (id, author, content, o = {}) => ({ id, author, content, created_at: dt(0), mentions: [], mentions_all: false, can_delete: false, ...o });
const RICH = msg(3, bob, "Voir #7 et le devis", { can_edit: false, edited: true,
  reply_to: { id: 2, author: "alice", excerpt: "Bien reçu merci" },
  reactions: [{ emoji: "👍", count: 2, mine: true, users: ["alice", "bob"] }, { emoji: "🎉", count: 1, mine: false, users: ["bob"] }],
  attachments: [{ id: 5, name: "maquette<1>.png", size: 20480, content_type: "image/png", image: true }, { id: 6, name: "devis.pdf", size: 3 * 1048576, content_type: "application/pdf", image: false }],
  tasks: [{ id: 7, title: "Maquettes <b>", status: "doing", project: 7 }] });
const THREAD = [
  msg(1, bob, "Salut @alice <script>boom()</script> @inconnu @tous", { mentions: ["alice"], mentions_all: true }),
  msg(2, alice, "Bien reçu\nmerci @bob", { can_delete: true, can_edit: true, mentions: ["bob"] }),
  RICH,
];

const routes = {
  "/me/": { id: 1, username: "alice", email: "a@x.fr", is_staff: true, is_superuser: false, timezone: "Europe/Paris", secondary_timezone: "" },
  "/chat/conversations/": [
    conv(10, { title: "Projet <b>A</b>", project: 7, unread: 2, last: { author: "bob", excerpt: "Salut @alice", created_at: dt(0) } }),
    conv(11, { title: "Perso", project: 8, solo: true, members: [alice] }),
    conv(13, { title: "Lecture seule", project: 9, can_write: false, members: [alice, bob] }),
    conv(12, { kind: "direct", title: "bob", other: bob, members: [alice, bob], last: { author: "alice", excerpt: "ok", created_at: dt(-1) } }),
  ],
  "/chat/conversations/10/messages/": { messages: THREAD, has_more: true },
  "/chat/conversations/11/messages/": { messages: [], has_more: false },
  "/chat/conversations/12/messages/": { messages: [msg(3, bob, "Hello")], has_more: false },
  "/chat/conversations/13/messages/": { messages: [], has_more: false },
  "/chat/search/": [{ message: 2, conversation: 10, conversation_title: "Projet <b>A</b>", author: "alice", excerpt: "Bien reçu merci @bob", created_at: dt(0) }],
  "/chat/summary/": { unread_messages: 2, unread_notifications: 1 },
  "/chat/contacts/": [bob, carol],
  "/timer/": { id: 9, task: 2, task_title: "Maquettes <b>", project: 7, project_name: "Projet <b>A</b>", running: true, minutes: null, started_at: new Date(Date.now() - 65000).toISOString(), day: day(0) },
  "/projects/7/time-report/": { total: 195, by_member: [{ user: "bob", minutes: 135 }, { user: "alice", minutes: 60 }], by_task: [{ task: 2, title: "Maquettes <i>x</i>", minutes: 150 }], by_day: [] },
  "/projects/7/tasks/2/time/": { total: 150, entries: [
    { id: 1, user: "alice", user_id: 1, day: day(-1), minutes: 90, running: false, started_at: null, note: "Maquette <b>x</b>" },
    { id: 2, user: "bob", user_id: 2, day: day(-2), minutes: 60, running: false, started_at: null, note: "" }] },
  "/projects/7/workload/": { weeks: [{ start: day(-3), end: day(3) }, { start: day(4), end: day(10) }], members: [
    { user_id: 1, username: "alice", role: "owner", cells: [{ days: 0, percent: 0, tasks: [] }, { days: 3, percent: 60, tasks: [3] }] },
    { user_id: 2, username: "bob <b>", role: "member", cells: [{ days: 10, percent: 200, tasks: [2, 3] }, { days: 5, percent: 100, tasks: [2] }] }],
    suggestions: [{ task: 3, title: "Livraison <i>", from: "bob <b>", from_id: 2, to: "alice", to_id: 1, week: day(-3), reason: "bob est à 200 % cette semaine, alice à 0 %." }] },
  "/projects/7/simulate/": { delay: 3, unit: "jours", forecast_end: day(10), safe: 1, tasks: [
    { id: 2, title: "Maquettes <script>", who: "bob", end_delay_days: 3, pushed: 1, critical: true },
    { id: 3, title: "Livraison", who: null, end_delay_days: 3, pushed: 0, critical: true },
    { id: 1, title: "Cadrage", who: "alice", end_delay_days: 0, pushed: 0, critical: false }] },
  "/templates/": [
    { key: "builtin:site-web", name: "Site web", description: "Du cadrage à la mise en ligne.", builtin: true, tasks: 8, skip_weekends: true },
    { key: "12", name: "Mon modèle <b>", description: "", builtin: false, tasks: 4, skip_weekends: false }],
  "/calendar/contacts/": [bob, carol],
  "/notifications/": [
    { type: "invite", id: 4, read: false, created_at: dt(0), event: 6, title: "Invitation <b>x</b>", starts_at: at(1, 10), author: "bob", project: "Projet <b>A</b>", status: "invited" },
    { type: "mention", id: 1, read: false, created_at: dt(0), conversation: 10, conversation_title: "Projet <b>A</b>", message: 1, author: "bob", excerpt: "Salut <b>@alice</b>", everyone: false },
    { id: 2, read: true, created_at: dt(-2), conversation: 10, conversation_title: "Projet <b>A</b>", message: 5, author: "carol", excerpt: "réunion", everyone: true },
  ],
  "/calendar/": {
    timezone: "Europe/Paris",
    events: [
      ev(1, "Point <b>équipe</b>", at(0, 10), at(0, 11)),
      ev(2, "Chevauchement", at(0, 10, 30), at(0, 12), { project: null, project_name: null }),
      ev(3, "Lecture seule", at(0, 15), at(0, 16), { can_edit: false, creator_name: "bob" }),
      ev(4, "Nuit", at(0, 22), at(1, 2)),
      ev(5, "Atelier <i>série</i>", at(0, 16), at(0, 17), { recurrence: "weekly", recurrence_until: null, occurrence_day: day(0), series_starts_at: at(-7, 16), series_ends_at: at(-7, 17),
        invitees: [{ id: 2, username: "bob", status: "invited" }, { id: 3, username: "carol", status: "accepted" }] }),
      ev(6, "Invitation", at(0, 18), at(0, 19), { my_status: "invited", can_edit: false, creator_name: "bob", invitees: [{ id: 1, username: "alice", status: "invited" }] }),
      ev(7, "Refusé", at(0, 20), at(0, 21), { my_status: "declined", can_edit: false }),
    ],
    tasks: [{ id: 2, project: 7, project_name: "Projet <b>A</b>", title: "Maquettes <script>alert(1)</script>", status: "doing", priority: 1,
      start_date: day(-3), due_date: day(0), is_milestone: false, assignee_name: "bob" }],
  },
  "/auth/config/": { registration_open: true },
  "/projects/": [{ id: 7, name: "Projet <b>A</b>", description: "", deadline: day(20), skip_weekends: true, owner: 1, role: "owner" }],
  "/projects/7/members/": [{ user_id: 1, username: "alice", role: "owner" }, { user_id: 2, username: "bob", role: "member" }],
  "/projects/7/tasks/": [
    task(1, "Cadrage", { status: "done", priority: 1, start_date: day(-8), due_date: day(-4), assignee: 1, assignee_name: "alice" }),
    task(2, "Maquettes <script>alert(1)</script>", { status: "doing", priority: 1, recurrence: "weekly", time_minutes: 150, start_date: day(-3), due_date: day(3), dependencies: [1], assignee: 2, assignee_name: "bob" }),
    task(3, "Livraison", { priority: 1, start_date: day(10), due_date: day(10), dependencies: [2], is_milestone: true }),
    task(4, "Sans date"),
  ],
  "/projects/7/tasks/2/comments/": [],
  "/projects/7/insights/": {
    total: 4, done: 1, progress: 35, planned_end: day(10), deadline: day(20), forecast_end: day(10), slip_days: -10, late_count: 0,
    critical_path: { task_ids: [2, 3], duration_days: 8 },
    risks: [{ type: "unassigned", severity: "low", task: 3, message: "« Livraison » n'a pas de responsable." }],
    workload: [{ user_id: 2, username: "bob", peak: 1, open: 1 }], unassigned: { open: 2, late: 1 },
    team: [
      { user_id: 2, username: "bob", role: "member", state: "late", total: 3, done: 1, open: 2, peak: 2, unscheduled: 0,
        late: [brief(2, "Retard <b>x</b>", { due: day(-3), days_late: 3 })], current: [brief(3, "En cours", { due: day(4) })], upcoming: [] },
      { user_id: 1, username: "alice", role: "owner", state: "free", total: 0, done: 0, open: 0, peak: 0, unscheduled: 0, late: [], current: [], upcoming: [] },
    ],
    stats: {
      status_counts: { todo: 2, doing: 1, done: 1 }, priority_counts: { "1": 2, "2": 1, "3": 0 },
      burnup: Array.from({ length: 30 }, (_, i) => ({ date: day(i - 29), created: Math.min(4, 1 + Math.floor(i / 8)), done: Math.floor(i / 12) })),
      velocity: { this_week: 3, last_week: 1 },
      recent_done: [{ id: 1, title: "Cadrage <b>", who: "alice", at: dt(0) }],
      due_soon: [{ ...brief(3, "Livraison", { due: day(10) }), who: null }],
    },
  },
  "/dashboard/": {
    kpis: { today: 2, late: 1, upcoming: 3, unscheduled: 1, done_this_week: 4, done_last_week: 2 },
    focus: [{ ...brief(2, "Retard <i>x</i>", { due: day(-2), days_late: 2 }), project_id: 7, project: "Projet <b>A</b>" },
            { ...brief(3, "Aujourd'hui", { due: day(0) }), project_id: 7, project: "Projet A" }],
    week: [0, 1, 2, 3, 4, 5, 6].map((i) => ({ date: day(i), tasks: i === 2 ? [{ ...brief(3, "Livraison"), project_id: 7, project: "Projet A" }] : [] })),
    projects: [{ id: 7, name: "Projet <b>A</b>", role: "owner", health: "risk", progress: 35, total: 4, done: 1, late_count: 1, forecast_end: day(10), deadline: day(20), slip_days: -10, members: 2, my_open: 2, team_late: 1 }],
    alerts: [{ project_id: 7, project: "Projet A", user: "bob", task: 2, title: "Retard", days_late: 3, count: 2 }],
    done_series: Array.from({ length: 14 }, (_, i) => ({ date: day(i - 13), count: i % 3 })),
  },
};

// --- administration
const U = (id, username, o = {}) => ({ id, username, email: username + "@x.fr", is_active: true, is_staff: false, is_superuser: false,
  date_joined: dt(-20), last_login: dt(-1), project_count: 2, owned_count: 1, open_tasks: 3, ...o });
const USERS = [U(1, "alice", { is_staff: true }), U(2, "bob"), U(3, "carol<img src=x onerror=alert(1)>", { is_active: false, last_login: null }),
  U(4, "root", { is_staff: true, is_superuser: true })];
Object.assign(routes, {
  "/admin/stats/": { users: { total: 4, active: 3, inactive: 1, admins: 2, new_30_days: 3, active_30_days: 2 }, projects: 5,
    tasks: { total: 20, done: 8, open: 12 }, comments: 6, registration_open: true,
    planning_engine: { name: "rust", version: "0.1.0", rust_available: true },
    signups_weekly: Array.from({ length: 8 }, (_, i) => ({ date: day(i * 7 - 49), count: i % 3 })),
    recent_users: [{ id: 9, username: "zoé<i>x</i>", email: "z@x.fr", date_joined: dt(-1) }] },
  "/admin/users/?": USERS,
  "/admin/users/?filter=active": USERS.filter((u) => u.is_active),
  "/admin/users/2/": { ...USERS[1], owned_projects: [{ id: 7, name: "Projet <b>A</b>", other_members: 1 }, { id: 8, name: "Solo", other_members: 0 }] },
  "/admin/projects/?": [{ id: 7, name: "Projet <b>A</b>", owner: "bob", owner_id: 2, members: 3, tasks: 10, done: 4, deadline: day(10), created_at: dt(-10) }],
  "/admin/audit/?limit=8": [{ id: 1, actor_name: "alice", action: "user.update", target: "bob (bob@x.fr)", details: { email: ["a@x.fr", "b@x.fr"] }, created_at: dt(0) }],
  "/admin/audit/?limit=200": [
    { id: 2, actor_name: "alice", action: "user.delete", target: "dan", details: { projects_transferred: 2, projects_deleted: 1, transferred_to: "bob" }, created_at: dt(0) },
    { id: 3, actor_name: "alice", action: "settings.update", target: "Réglages", details: { allow_registration: [true, false] }, created_at: dt(0) },
    { id: 4, actor_name: "al<b>ice", action: "user.password_reset", target: "bob", details: { password_generated: true }, created_at: dt(0) }],
  "/admin/settings/": { allow_registration: true },
});

globalThis.fetch = async (url, o = {}) => {
  if (globalThis.__failPath && url.endsWith(globalThis.__failPath)) throw new Error("Failed to fetch");
  if (globalThis.__realRoutes) { /* rejeu avec les vraies réponses de l'API (voir CLAUDE.md) */
    const rp = url.replace("http://x/api", "");
    if (!o.method || o.method === "GET") { const d = __realRoutes[rp]; return { ok: d !== undefined, status: d !== undefined ? 200 : 404, json: async () => d }; }
    return { ok: true, status: 200, json: async () => ({}) };
  }
  const path = url.replace("http://x/api", "");
  const method = o.method || "GET";
  __calls.push({ method, path, body: o.body ? JSON.parse(o.body) : null });
  if (method === "PATCH" && path.startsWith("/projects/7/tasks/")) {
    const id = Number(path.split("/")[4]);
    const t = routes["/projects/7/tasks/"].find((x) => x.id === id);
    return { ok: true, status: 200, json: async () => ({ ...t, ...JSON.parse(o.body) }) };
  }
  if (method === "PATCH" && path === "/me/") { Object.assign(routes["/me/"], JSON.parse(o.body)); return { ok: true, status: 200, json: async () => routes["/me/"] }; }
  if (method === "POST" && /^\/chat\/conversations\/\d+\/messages\/$/.test(path)) {
    const m = { id: 99, author: alice, content: JSON.parse(o.body).content, created_at: dt(0), mentions: [], mentions_all: false, can_delete: true };
    return { ok: true, status: 201, json: async () => m };
  }
  if (method === "PATCH" && /^\/chat\/messages\/\d+\/$/.test(path)) {
    const m = { ...THREAD.find((x) => x.id === Number(path.split("/")[3])), ...JSON.parse(o.body), edited: true };
    return { ok: true, status: 200, json: async () => m };
  }
  if (method === "POST" && /^\/chat\/messages\/\d+\/reactions\/$/.test(path)) {
    const m = { ...THREAD.find((x) => x.id === Number(path.split("/")[3])), reactions: [{ emoji: JSON.parse(o.body).emoji, count: 1, mine: true, users: ["alice"] }] };
    return { ok: true, status: 200, json: async () => m };
  }
  if (method !== "GET") return { ok: true, status: 200, json: async () => ({ moved: [], generated_password: "Zx9-secret-pw" }) };
  const data = routes[path] ?? routes[path.split("?")[0]];
  return { ok: !!data, status: data ? 200 : 404, json: async () => data };
};
