import { api, auth } from "./api.js";
import * as D from "./dates.js";
import { ganttHtml } from "./gantt.js";
import { teamHtml } from "./team.js";
import { homeHtml, projectDashHtml } from "./dashboard.js";
import { adminHtml, createAdmin } from "./admin.js";
import * as CAL from "./calendar.js";
import * as TZ from "./tz.js";
import * as CH from "./chat.js";
import { icon } from "./icons.js";
import { hue } from "./palette.js";

const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ROLE = { owner: "Propriétaire", member: "Membre", viewer: "Lecteur" };
const STATUS = { todo: "À faire", doing: "En cours", done: "Terminée" };
const PRIO = { 1: "Haute", 2: "Normale", 3: "Basse" };

const state = {
  user: null,
  projects: [],
  project: null,
  tasks: [],
  members: [],
  comments: [],
  selected: null,
  view: ["dashboard", "gantt", "team", "list", "board"].includes(auth.pref.get("view")) ? auth.pref.get("view") : "dashboard",
  page: "home", // "home" = tableau de bord personnel, "project" = un projet, "calendar", "messages", "notifications", "admin" = administration
  home: null,
  admin: { tab: "overview", q: "", filter: "", auditFilter: "", stats: null, users: [], projects: [], audit: [], settings: null },
  insights: null,
  zoom: auth.pref.get("zoom") === "month" ? "month" : "week",
  showCritical: auth.pref.get("critical") !== "0",
  filter: { group: "due", assignee: "", priority: "", showDone: false },
  summary: { unread_messages: 0, unread_notifications: 0 },
  chat: { convs: [], current: null, messages: [], hasMore: false, drafts: {}, pick: { items: [], active: 0, start: 0 }, editing: null, reactFor: null, replyTo: null, files: [], search: null, tasks: {} },
  notifs: [],
  mini: new Date(), // mois affiché dans le mini-calendrier de la barre latérale
  cal: { mode: ["day", "week", "month"].includes(auth.pref.get("calmode")) ? auth.pref.get("calmode") : "week", cursor: new Date(), data: null, project: "", mine: false },
};

const canWrite = () => !!state.project && state.project.role !== "viewer";
const isOwner = () => state.project?.role === "owner";
const avatar = (name, cls = "") =>
  `<span class="avatar ${cls}" style="--h:${hue(name)}" title="${esc(name)}">${esc(name.slice(0, 2).toUpperCase())}</span>`;

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 4000);
}
const guard = (fn) => async (...args) => {
  try { return await fn(...args); } catch (e) { toast(e.message); }
};

/* ---------- thème ---------- */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  auth.pref.set("theme", theme);
}
applyTheme(auth.pref.get("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

/* ---------- données ---------- */
async function loadProjects() {
  state.projects = await api.projects();
  const last = Number(auth.pref.get("project"));
  state.project = state.projects.find((p) => p.id === last) || state.projects[0] || null;
  state.tasks = [];
  state.members = [];
  await goHome();
}

async function goHome() {
  state.page = "home";
  state.selected = null;
  state.home = await api.dashboard();
  render();
}

async function selectProject(id) {
  state.page = "project";
  state.project = state.projects.find((p) => p.id === id);
  auth.pref.set("project", id);
  state.selected = null;
  state.members = await api.members(id);
  await reloadTasks();
  render();
}

/** Recharge les tâches ET les indicateurs : une modification de date peut en décaler d'autres (dépendances). */
async function reloadTasks() {
  const pid = state.project.id;
  [state.tasks, state.insights] = await Promise.all([api.tasks(pid), api.insights(pid).catch(() => null)]);
}

const isLate = (t) => t.due_date && t.status !== "done" && t.due_date < D.iso(new Date());

const PLANNING_FIELDS = ["start_date", "due_date", "dependencies", "status", "is_milestone"];

async function patchTask(id, patch, fromPanel = false) {
  const updated = await api.updateTask(state.project.id, id, patch);
  state.tasks = state.tasks.map((t) => (t.id === id ? updated : t));
  if (PLANNING_FIELDS.some((f) => f in patch)) {
    await reloadTasks();
    renderSidebar();
    renderView();
    renderPanel();
    return;
  }
  renderSidebar();
  renderView();
  if (!fromPanel) renderPanel();
}

/* ---------- rendu ---------- */
let lastPageKey = "";
function render() {
  // petite entrée animée à chaque changement de page (pas à chaque rafraîchissement de la même page)
  const key = `${state.page}:${state.page === "project" ? `${state.project?.id}:${state.view}` : ""}`;
  if (key !== lastPageKey) {
    lastPageKey = key;
    const v = $("#view");
    v.classList.remove("enter");
    void v.offsetWidth;
    v.classList.add("enter");
  }
  if (state.page === "admin") {
    renderSidebar();
    $("#toolbar").innerHTML = `<h1>Administration</h1><span class="tag">réservé aux administrateurs</span>`;
    $("#view").innerHTML = adminHtml({ admin: state.admin, user: state.user, esc, avatar });
    renderPanel();
    return;
  }
  if (state.page === "messages") {
    renderSidebar();
    $("#toolbar").innerHTML = `<h1>Messages</h1><div class="grow"></div><button class="btn primary" data-action="new-direct">Nouveau message direct</button>`;
    renderChat();
    renderPanel();
    return;
  }
  if (state.page === "notifications") {
    renderSidebar();
    $("#toolbar").innerHTML = `<h1>Notifications</h1><div class="grow"></div>
      <button class="btn" data-action="notifs-readall" ${state.summary.unread_notifications ? "" : "disabled"}>Tout marquer comme lu</button>`;
    $("#view").innerHTML = CH.notificationsHtml({ rows: state.notifs, tz: myTz(), esc });
    renderPanel();
    return;
  }
  if (state.page === "calendar") {
    renderSidebar();
    renderCalToolbar();
    renderCalView();
    renderPanel();
    return;
  }
  if (state.page === "home") {
    renderSidebar();
    $("#toolbar").innerHTML = `<h1>Tableau de bord</h1><div class="grow"></div>
      <button class="btn primary" data-action="new-project">Nouveau projet</button>`;
    $("#view").innerHTML = homeHtml({ data: state.home, user: state.user, esc, avatar });
    renderPanel();
    return;
  }
  renderSidebar();
  renderToolbar();
  renderView();
  renderPanel();
}

/** Jours (AAAA-MM-JJ) portant un événement ou une tâche dans la période chargée du calendrier. */
function calMarks() {
  const d = state.cal.data;
  if (state.page !== "calendar" || !d) return new Set();
  const tz = myTz();
  const marks = new Set(d.tasks.map((t) => t.due_date || t.start_date));
  d.events.forEach((e) => marks.add(TZ.dayKey(new Date(e.starts_at), tz)));
  return marks;
}

function miniCal() {
  const m = state.mini;
  const onCal = state.page === "calendar";
  const week = new Set(onCal && state.cal.mode === "week" ? D.weekDays(state.cal.cursor).map(D.iso) : []);
  const marks = calMarks();
  const todayKey = TZ.dayKey(new Date(), myTz());
  const days = D.monthGrid(m).map((d) => {
    const k = D.iso(d);
    const cls = [d.getMonth() !== m.getMonth() ? "out" : "", k === todayKey ? "today" : "", week.has(k) ? "inweek" : "",
      onCal && k === D.iso(state.cal.cursor) && state.cal.mode === "day" ? "inweek" : "", marks.has(k) ? "has" : ""].join(" ");
    return `<button class="mday ${cls}" data-action="mini-day" data-date="${k}">${d.getDate()}</button>`;
  });
  return `<div class="mini">
    <div class="mini-head"><b>${D.fmt(m, { month: "long", year: "numeric" })}</b>
      <span><button class="icon-btn" data-action="mini-prev" aria-label="Mois précédent">${icon("left", 15)}</button>
      <button class="icon-btn" data-action="mini-next" aria-label="Mois suivant">${icon("right", 15)}</button></span></div>
    <div class="mini-grid">${["L", "M", "M", "J", "V", "S", "D"].map((x) => `<i>${x}</i>`).join("")}${days.join("")}</div>
  </div>`;
}

const badge = (n) => (n ? `<span class="ncount">${n > 99 ? "99+" : n}</span>` : "");
const navItem = (page, action, icon, label, extra = "") =>
  `<button class="navitem ${state.page === page ? "active" : ""}" data-action="${action}" title="${label}"><span class="ico">${icon}</span><span class="lbl">${label}</span>${extra}</button>`;
const sideCollapsed = () => auth.pref.get("side") === "collapsed";
const projectUnread = (id) => state.chat.convs.find((c) => c.project === id)?.unread || 0;

function renderSidebar() {
  const u = state.user;
  const collapsed = sideCollapsed();
  $("#app").classList.toggle("side-collapsed", collapsed);
  const sm = state.summary;
  $("#sidebar").innerHTML = `
    <div class="brand"><span class="logo">✓</span><span class="lbl">TaskFlow</span><span class="grow"></span>
      <button class="icon-btn bell ${state.page === "notifications" ? "active" : ""}" data-action="go-notifications" title="Notifications" aria-label="Notifications">${icon("bell")}${badge(sm.unread_notifications)}</button>
      <button class="icon-btn collapse" data-action="toggle-side" title="${collapsed ? "Agrandir" : "Réduire"} la barre latérale" aria-label="Réduire la barre latérale">${icon(collapsed ? "rights" : "lefts", 17)}</button></div>
    <nav class="nav-main">
      ${navItem("home", "go-home", icon("home"), "Tableau de bord")}
      ${navItem("calendar", "go-calendar", icon("calendar"), "Calendrier", "<kbd>C</kbd>")}
      ${navItem("messages", "go-messages", icon("message"), "Messages", badge(sm.unread_messages))}
    </nav>
    ${state.page === "calendar" && !collapsed ? miniCal() : ""}
    <div class="side-section grow">
      <div class="side-title"><span class="lbl">Projets</span> <button class="icon-btn" data-action="new-project" title="Nouveau projet" aria-label="Nouveau projet">${icon("plus", 15)}</button></div>
      <div class="proj-list">${state.projects.map((p) => `<button class="proj ${state.page === "project" && p.id === state.project?.id ? "active" : ""}"
        data-action="select-project" data-id="${p.id}" title="${esc(p.name)}"><span class="dot" style="--h:${hue(p.name)}"></span><span class="lbl ellipsis">${esc(p.name)}</span>${badge(projectUnread(p.id))}</button>`).join("")
        || '<p class="muted small pad lbl">Aucun projet</p>'}</div>
    </div>
    <div class="side-foot"><button class="me-btn" data-action="account" title="Mon compte">${avatar(u.username)}<span class="lbl grow ellipsis">${esc(u.username)}</span></button>
      ${u.is_staff ? `<button class="icon-btn ${state.page === "admin" ? "active" : ""}" data-action="go-admin" title="Administration" aria-label="Administration">${icon("shield")}</button>` : ""}
      <button class="icon-btn" data-action="theme" title="Changer de thème" aria-label="Changer de thème">${icon(document.documentElement.dataset.theme === "dark" ? "sun" : "moon")}</button>
      <button class="icon-btn" data-action="logout" title="Se déconnecter" aria-label="Se déconnecter">${icon("logout")}</button></div>`;
}

function titleLabel() {
  return { dashboard: "Synthèse", gantt: "Planning", team: "Équipe", board: "Tableau" }[state.view] || "Tâches";
}

function renderToolbar() {
  if (!state.project) { $("#toolbar").innerHTML = ""; return; }
  const views = [["dashboard", "Synthèse"], ["gantt", "Gantt"], ["team", "Équipe"], ["list", "Liste"], ["board", "Tableau"]];
  $("#toolbar").innerHTML = `
    <h1>${esc(titleLabel())}</h1>
    <span class="tag" title="${esc(state.project.description)}">${esc(state.project.name)}</span>
    <div class="grow"></div>
    <div class="seg">${views.map(([v, l]) => `<button class="${state.view === v ? "on" : ""}" data-action="view" data-view="${v}">${l}</button>`).join("")}</div>
    <button class="avatars" data-action="members" title="Membres">${state.members.slice(0, 4).map((m) => avatar(m.username, "sm")).join("")}
      <span class="muted small">${state.members.length} ${state.members.length > 1 ? "membres" : "membre"}</span></button>
    <button class="icon-btn chat-btn" data-action="chat-project" title="Discussion du projet" aria-label="Discussion du projet">${icon("message")}${badge(projectUnread(state.project.id))}</button>
    <button class="icon-btn" data-action="edit-project" title="Paramètres du projet" aria-label="Paramètres du projet">${icon("sliders")}</button>
    ${canWrite() ? '<button class="btn primary" data-action="new-task">Nouvelle tâche <kbd>N</kbd></button>' : ""}`;
}

function renderView() {
  const v = $("#view");
  if (!state.project) {
    v.innerHTML = `<div class="empty"><h2>Bienvenue sur TaskFlow</h2>
      <p class="muted">Créez un projet pour commencer — seul ou en équipe.</p>
      <button class="btn primary" data-action="new-project">Créer un projet</button></div>`;
    return;
  }
  const old = $("#gantt-scroll");
  const keep = old ? { left: old.scrollLeft, top: old.scrollTop } : null;
  v.innerHTML = { dashboard: dashboardView, gantt: ganttView, team: teamView, list: listView, board: boardView }[state.view]();
  const g = $("#gantt-scroll");
  if (g) {
    if (keep) { g.scrollLeft = keep.left; g.scrollTop = keep.top; } else scrollGanttToToday(false);
  }
}

function dashboardView() {
  return projectDashHtml({ insights: state.insights, project: state.project, esc, avatar });
}

function teamView() {
  return teamHtml({ insights: state.insights, esc, avatar });
}

function ganttView() {
  return ganttHtml({ tasks: state.tasks, insights: state.insights, project: state.project, zoom: state.zoom,
    showCritical: state.showCritical, canWrite: canWrite(), esc, avatar });
}

function scrollGanttToToday(smooth = true) {
  const g = $("#gantt-scroll");
  if (!g) return;
  const left = D.parse(D.iso(new Date())) - D.parse(g.dataset.start);
  const x = Math.round(left / 86400000) * Number(g.dataset.daywidth);
  g.scrollTo({ left: Math.max(0, x - 120), behavior: smooth ? "smooth" : "auto" });
}

const BUCKETS = [["late", "En retard"], ["today", "Aujourd'hui"], ["week", "Cette semaine"], ["later", "Plus tard"], ["none", "Sans échéance"], ["done", "Terminées"]];

function bucketOf(t) {
  if (t.status === "done") return "done";
  if (!t.due_date) return "none";
  const now = D.iso(new Date());
  if (t.due_date < now) return "late";
  if (t.due_date === now) return "today";
  if (t.due_date <= D.iso(D.addDays(D.startOfWeek(new Date()), 6))) return "week";
  return "later";
}

function dateLabel(iso) {
  if (!iso) return "";
  const now = new Date();
  if (iso === D.iso(now)) return "Aujourd'hui";
  if (iso === D.iso(D.addDays(now, 1))) return "Demain";
  if (iso === D.iso(D.addDays(now, -1))) return "Hier";
  return D.fmt(D.parse(iso), { day: "numeric", month: "short" });
}

function visibleTasks() {
  const f = state.filter;
  return state.tasks.filter((t) =>
    (f.showDone || t.status !== "done") &&
    (!f.assignee || (f.assignee === "none" ? !t.assignee : String(t.assignee) === f.assignee)) &&
    (!f.priority || String(t.priority) === f.priority));
}

function taskRow(t) {
  const done = t.status === "done";
  const box = canWrite()
    ? `<button class="check ${done ? "on" : ""}" data-action="toggle-done" data-task="${t.id}" aria-label="${done ? "Rouvrir" : "Terminer"} la tâche">✓</button>`
    : `<span class="check ${done ? "on" : ""}">✓</span>`;
  return `<div class="task-row ${done ? "done" : ""}" data-task="${t.id}" data-action="open-task">
    ${box}<span class="pdot p${t.priority}" title="Priorité ${PRIO[t.priority].toLowerCase()}"></span>
    <span class="r-title">${esc(t.title)}</span>
    <span class="pill s-${t.status}">${STATUS[t.status]}</span>
    <span class="r-who">${t.assignee_name ? avatar(t.assignee_name, "sm") + `<span class="ellipsis">${esc(t.assignee_name)}</span>` : '<span class="muted">—</span>'}</span>
    <span class="r-date ${isLate(t) ? "late-text" : ""}">${dateLabel(t.due_date)}</span></div>`;
}

function listView() {
  const f = state.filter;
  const tasks = visibleTasks().sort((a, b) =>
    a.priority - b.priority || (a.due_date || "9").localeCompare(b.due_date || "9") || a.id - b.id);
  const groups = f.group === "status"
    ? Object.entries(STATUS).map(([k, l]) => [l, tasks.filter((t) => t.status === k)])
    : BUCKETS.map(([k, l]) => [l, tasks.filter((t) => bucketOf(t) === k), k]);
  const opts = (pairs, cur) => pairs.map(([v, l]) => `<option value="${v}" ${String(cur) === String(v) ? "selected" : ""}>${esc(l)}</option>`).join("");
  return `<div class="list">
    ${canWrite() ? `<form id="quick-add" class="quick-add" autocomplete="off"><span class="plus">+</span>
      <input name="newtitle" placeholder="Ajouter une tâche… puis Entrée" maxlength="200" aria-label="Nouvelle tâche"></form>` : ""}
    <div class="filters">
      <label class="inline">Grouper par <select data-filter="group">${opts([["due", "Échéance"], ["status", "Statut"]], f.group)}</select></label>
      <label class="inline">Assigné <select data-filter="assignee">${opts([["", "Tous"], ["none", "Personne"], ...state.members.map((m) => [m.user_id, m.username])], f.assignee)}</select></label>
      <label class="inline">Priorité <select data-filter="priority">${opts([["", "Toutes"], ...Object.entries(PRIO)], f.priority)}</select></label>
      <label class="inline check-label"><input type="checkbox" data-filter="showDone" ${f.showDone ? "checked" : ""}> Afficher les terminées</label>
      <span class="grow"></span><span class="muted small">${tasks.length} ${tasks.length > 1 ? "tâches" : "tâche"}</span>
    </div>
    ${groups.filter(([, ts]) => ts.length).map(([label, ts, key]) => `<section class="group">
      <div class="group-head ${key === "late" ? "late-text" : ""}"><b>${label}</b><span class="count">${ts.length}</span></div>
      ${ts.map(taskRow).join("")}</section>`).join("")
      || `<div class="empty small-empty"><p class="muted">${state.tasks.length ? "Aucune tâche ne correspond aux filtres." : "Aucune tâche pour l'instant."}</p></div>`}
  </div>`;
}

function boardView() {
  return `<div class="board">${Object.entries(STATUS).map(([s, label]) => {
    const ts = state.tasks.filter((t) => t.status === s);
    return `<div class="col" data-drop data-status="${s}">
      <div class="col-head"><b>${label}</b><span class="count">${ts.length}</span>
        ${canWrite() ? `<button class="icon-btn" data-action="new-task" data-status="${s}">+</button>` : ""}</div>
      <div class="stack-sm">${ts.map((t) => `<div class="card p${t.priority}" draggable="${canWrite()}" data-task="${t.id}" data-action="open-task">
        <div>${esc(t.title)}</div>
        <div class="meta">${t.due_date ? `<span class="${isLate(t) ? "late-text" : ""}">${D.fmt(D.parse(t.due_date), { day: "numeric", month: "short" })}</span>` : ""}
        <span>${PRIO[t.priority]}</span>${t.assignee_name ? avatar(t.assignee_name, "xs") : ""}</div></div>`).join("")}</div></div>`;
  }).join("")}</div>`;
}

/* ---------- panneau de détail ---------- */
function renderPanel() {
  const p = $("#panel");
  if (state.page !== "project") state.selected = null;
  const t = state.tasks.find((x) => x.id === state.selected);
  if (!t) { p.classList.remove("open"); p.innerHTML = ""; return; }
  const dis = canWrite() ? "" : "disabled";
  p.classList.add("open");
  p.innerHTML = `
    <div class="panel-head"><button class="icon-btn" data-action="close-panel" aria-label="Fermer">${icon("x", 16)}</button>
      ${canWrite() ? '<button class="btn ghost danger" data-action="delete-task">Supprimer</button>' : ""}</div>
    <input class="title-input" data-field="title" value="${esc(t.title)}" ${dis} aria-label="Titre">
    <div class="props">
      <label>Statut<select data-field="status" ${dis}>${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${t.status === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label>Priorité<select data-field="priority" ${dis}>${Object.entries(PRIO).map(([k, v]) => `<option value="${k}" ${t.priority == k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label>Début<input type="date" data-field="start_date" value="${t.start_date || ""}" ${dis}></label>
      <label>Fin / échéance<input type="date" data-field="due_date" value="${t.due_date || ""}" ${dis}></label>
      <label>Assigné à<select data-field="assignee" ${dis}><option value="">Personne</option>${state.members.map((m) => `<option value="${m.user_id}" ${t.assignee === m.user_id ? "selected" : ""}>${esc(m.username)}</option>`).join("")}</select></label>
    </div>
    <label class="inline check-label block"><input type="checkbox" data-field="is_milestone" ${t.is_milestone ? "checked" : ""} ${dis}> Jalon (étape clé, sans durée)</label>
    <div class="deps"><h3>Dépend de</h3>
      ${state.tasks.filter((o) => o.id !== t.id).map((o) => `<label class="inline dep"><input type="checkbox" data-dep="${o.id}" ${t.dependencies.includes(o.id) ? "checked" : ""} ${dis}> <span class="ellipsis">${esc(o.title)}</span></label>`).join("")
        || '<p class="muted small">Aucune autre tâche.</p>'}
      <p class="muted small">Cette tâche ne peut pas commencer avant la fin de ses prérequis ; si l'un d'eux est repoussé, elle suit.</p></div>
    <label class="block">Description<textarea data-field="description" rows="5" ${dis} placeholder="Ajouter une description…">${esc(t.description)}</textarea></label>
    <div class="comments"><h3>Commentaires</h3><div id="comment-list"></div>
      ${canWrite() ? `<form id="comment-form" class="row"><input name="content" placeholder="Écrire un commentaire…" required autocomplete="off"><button class="btn">Envoyer</button></form>` : ""}
    </div>`;
  loadComments(t.id);
}

const guardedComments = guard(async (id) => {
  state.comments = await api.comments(state.project.id, id);
  paintComments();
});
function loadComments(id) { guardedComments(id); }
function paintComments() {
  const el = $("#comment-list");
  if (!el) return;
  el.innerHTML = state.comments.map((c) => `<div class="comment">${avatar(c.author_name, "sm")}
    <div><b>${esc(c.author_name)}</b> <span class="muted small">${D.fmt(new Date(c.created_at), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
    <div>${esc(c.content)}</div></div></div>`).join("") || '<p class="muted small">Aucun commentaire.</p>';
}

/* ---------- modales ---------- */
function openModal(title, body, onSubmit) {
  const m = $("#modal");
  if (m.open) m.close();
  m.innerHTML = `<form class="modal-card" method="dialog"><h2>${title}</h2>${body}</form>`;
  const form = m.querySelector("form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (e.submitter?.value === "cancel") return m.close();
    try {
      if (onSubmit && (await onSubmit(Object.fromEntries(new FormData(form)))) !== false) m.close();
    } catch (err) { toast(err.message); }
  });
  m.showModal();
}
const actions = (ok = "Enregistrer") =>
  `<div class="row end"><button class="btn ghost" value="cancel" formnovalidate>Annuler</button><button class="btn primary" value="ok">${ok}</button></div>`;

function taskModal(date = "", status = "todo") {
  const members = state.members.map((m) => `<option value="${m.user_id}">${esc(m.username)}</option>`).join("");
  openModal("Nouvelle tâche", `
    <label class="block">Titre<input name="title" required maxlength="200" autofocus></label>
    <div class="props">
      <label>Début<input type="date" name="start_date" value="${date}"></label>
      <label>Fin / échéance<input type="date" name="due_date" value="${date}"></label>
      <label>Priorité<select name="priority">${Object.entries(PRIO).map(([k, v]) => `<option value="${k}" ${k == 2 ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label>Statut<select name="status">${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === status ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label>Assigné à<select name="assignee"><option value="">Personne</option>${members}</select></label>
    </div>${actions("Créer")}`, async (f) => {
    const t = await api.createTask(state.project.id, {
      title: f.title, status: f.status, priority: Number(f.priority),
      start_date: f.start_date || f.due_date || null, due_date: f.due_date || f.start_date || null,
      assignee: f.assignee ? Number(f.assignee) : null,
    });
    await reloadTasks();
    render();
  });
}

function projectModal(project) {
  openModal(project ? "Paramètres du projet" : "Nouveau projet", `
    <label class="block">Nom<input name="name" required maxlength="150" value="${esc(project?.name)}" ${project && !isOwner() ? "disabled" : ""}></label>
    <label class="block">Description<textarea name="description" rows="3" ${project && !isOwner() ? "disabled" : ""}>${esc(project?.description)}</textarea></label>
    <label class="block">Échéance du projet<input type="date" name="deadline" value="${project?.deadline || ""}" ${project && !isOwner() ? "disabled" : ""}></label>
    ${project ? `<div class="row">${isOwner() ? '<button class="btn ghost danger" value="delete" formnovalidate>Supprimer le projet</button>'
      : '<button class="btn ghost danger" value="leave" formnovalidate>Quitter le projet</button>'}</div>` : ""}
    ${actions(project ? "Enregistrer" : "Créer")}`, async (f) => {
    if (!project) {
      const p = await api.createProject({ name: f.name, description: f.description, deadline: f.deadline || null });
      state.projects.push(p);
      await selectProject(p.id);
    } else if (isOwner()) {
      Object.assign(project, await api.updateProject(project.id, { name: f.name, description: f.description, deadline: f.deadline || null }));
      await reloadTasks();
      render();
    }
  });
  // Les boutons « supprimer » / « quitter » sont gérés à part pour ne pas déclencher la validation du formulaire
  $("#modal").querySelectorAll('button[value="delete"], button[value="leave"]').forEach((b) =>
    b.addEventListener("click", guard(async (e) => {
      e.preventDefault();
      if (b.value === "delete") {
        if (!confirm(`Supprimer définitivement « ${project.name} » et toutes ses tâches ?`)) return;
        await api.deleteProject(project.id);
      } else {
        if (!confirm("Quitter ce projet ?")) return;
        await api.removeMember(project.id, state.user.id);
      }
      $("#modal").close();
      await loadProjects();
    })));
}

function membersModal() {
  const owner = isOwner();
  const rows = state.members.map((m) => `<div class="member">${avatar(m.username)}
    <span class="grow">${esc(m.username)}${m.user_id === state.user.id ? ' <span class="muted small">(vous)</span>' : ""}</span>
    ${owner && m.role !== "owner"
      ? `<select data-change="role" data-uid="${m.user_id}">${["member", "viewer"].map((r) => `<option value="${r}" ${m.role === r ? "selected" : ""}>${ROLE[r]}</option>`).join("")}</select>
         <button type="button" class="btn ghost sm" data-action="transfer-owner" data-uid="${m.user_id}" title="Céder la propriété du projet à ${esc(m.username)}">Céder</button>
         <button type="button" class="icon-btn" data-action="remove-member" data-uid="${m.user_id}" title="Retirer" aria-label="Retirer">${icon("x", 15)}</button>`
      : `<span class="muted small">${ROLE[m.role]}</span>`}</div>`).join("");
  const add = owner ? `<h3>Inviter</h3><div class="row">
      <input name="identifier" placeholder="Nom d'utilisateur ou email" required>
      <select name="role"><option value="member">Membre</option><option value="viewer">Lecteur</option></select>
      <button class="btn primary" value="ok">Ajouter</button></div>
      <p class="muted small">Un projet à un seul membre est un projet solo.</p>` : "";
  openModal("Membres", `<div class="stack-sm">${rows}</div>${add}
    <div class="row end"><button class="btn ghost" value="cancel" formnovalidate>Fermer</button></div>`, async (f) => {
    if (!f.identifier) return;
    await api.addMember(state.project.id, { identifier: f.identifier, role: f.role });
    state.members = await api.members(state.project.id);
    renderToolbar();
    membersModal();
    return false;
  });
}

/* ---------- messagerie ---------- */
const currentConv = () => state.chat.convs.find((c) => c.id === state.chat.current);
const nearBottom = (el) => !el || el.scrollHeight - el.scrollTop - el.clientHeight < 80;

function renderChat() {
  const c = state.chat;
  $("#view").innerHTML = CH.chatHtml({ convs: c.convs, current: c.current, messages: c.messages, hasMore: c.hasMore,
    draft: c.drafts[c.current], meName: state.user.username, tz: myTz(), esc, editing: c.editing, reactFor: c.reactFor, replyTo: c.replyTo, files: c.files, search: c.search });
  loadThumbs();
  const box = $("#chat-msgs");
  if (box) box.scrollTop = box.scrollHeight;
  const input = $("#chat-input");
  if (input) { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight || 0, 140)}px`; }
}

function paintChatList() {
  const el = $("#chat-convs");
  if (!el) return;
  const c = state.chat;
  el.innerHTML = c.search ? CH.searchHtml(c.search.rows, c.search.q, esc) : CH.convListHtml({ convs: c.convs, current: c.current, tz: myTz(), esc });
}

function paintMessages(stick) {
  const box = $("#chat-msgs");
  const conv = currentConv();
  if (!box || !conv) return;
  const keep = box.scrollHeight - box.scrollTop;
  const c = state.chat;
  box.innerHTML = CH.messagesHtml({ messages: c.messages, conv, meName: state.user.username, tz: myTz(), hasMore: c.hasMore, esc,
    editing: c.editing, reactFor: c.reactFor, canWrite: conv.can_write });
  box.scrollTop = stick ? box.scrollHeight : box.scrollHeight - keep;
  loadThumbs();
  if (c.editing) { const t = $("#edit-input"); t?.focus(); }
}

const unreadTotal = () => state.chat.convs.reduce((n, c) => n + c.unread, 0);

/** Recharge les fils et les compteurs ; retourne true si une nouvelle mention est arrivée. */
async function refreshChat() {
  const [convs, summary] = await Promise.all([api.chatConversations(), api.chatSummary()]);
  const grew = summary.unread_notifications > state.summary.unread_notifications;
  state.chat.convs = convs;
  state.summary = summary;
  return grew;
}

function saveDraft() {
  const input = $("#chat-input");
  if (input && state.chat.current) state.chat.drafts[state.chat.current] = input.value;
}

async function openMessages(convId = state.chat.current) {
  saveDraft();
  state.page = "messages";
  state.selected = null;
  render();
  await refreshChat();
  const id = state.chat.convs.some((c) => c.id === convId) ? convId : (state.chat.convs[0]?.id ?? null);
  await openConv(id);
}

async function openConv(id) {
  saveDraft();
  const c = state.chat;
  c.current = id;
  c.messages = [];
  c.hasMore = false;
  if (id) {
    const r = await api.chatMessages(id);
    c.messages = r.messages;
    c.hasMore = r.has_more;
    await api.chatRead(id);
    const conv = currentConv();
    if (conv) conv.unread = 0;
    state.summary = await api.chatSummary();
  }
  if (state.page !== "messages") return;
  render();
  $("#chat-input")?.focus();
}

async function sendChat() {
  const input = $("#chat-input");
  const conv = currentConv();
  if (!input || !conv) return;
  const c = state.chat;
  const text = input.value.trim();
  if (!text && !c.files.length) return;
  let msg;
  if (c.files.length) {
    const form = new FormData();
    form.append("content", text);
    if (c.replyTo) form.append("reply_to", c.replyTo.id);
    c.files.forEach((f) => form.append("files", f));
    msg = await api.chatSendForm(conv.id, form);
  } else {
    msg = await api.chatSend(conv.id, text, c.replyTo?.id);
  }
  input.value = "";
  input.style.height = "auto";
  delete c.drafts[conv.id];
  c.replyTo = null;
  c.files = [];
  paintComposerExtras();
  hidePick();
  c.messages.push(msg);
  conv.last = { author: state.user.username, excerpt: (text || "Pièce jointe").replace(/\s+/g, " ").slice(0, 90), created_at: msg.created_at };
  conv.unread = 0;
  c.convs.sort((a, b) => (b.last ? new Date(b.last.created_at) : 0) - (a.last ? new Date(a.last.created_at) : 0));
  paintMessages(true);
  paintChatList();
  input.focus();
}

/** Bandeau « réponse à… » et pastilles des fichiers en attente, sans toucher au champ de saisie. */
function paintComposerExtras() {
  const c = state.chat;
  const bar = $("#reply-bar");
  if (bar) { bar.hidden = !c.replyTo; bar.innerHTML = c.replyTo ? CH.replyBarHtml(c.replyTo, esc) : ""; }
  const chips = $("#file-chips");
  if (chips) { chips.hidden = !c.files.length; chips.innerHTML = CH.fileChipsHtml(c.files, esc); }
}

/** Miniatures des images jointes : chargées avec le jeton, une seule fois chacune. */
const thumbs = new Map();
function loadThumbs() {
  document.querySelectorAll("img[data-att]").forEach((img) => {
    const id = img.dataset.att;
    if (thumbs.has(id)) { if (thumbs.get(id)) img.src = thumbs.get(id); return; }
    thumbs.set(id, null);
    api.attachmentUrl(id).then((url) => { thumbs.set(id, url); document.querySelectorAll(`img[data-att="${id}"]`).forEach((n) => (n.src = url)); }).catch(() => thumbs.delete(id));
  });
}

const msgById = (id) => state.chat.messages.find((m) => m.id === Number(id));
function replaceMessage(updated) {
  state.chat.messages = state.chat.messages.map((m) => (m.id === updated.id ? updated : m));
}
function flash(id) {
  const el = document.querySelector(`[data-msg="${id}"]`);
  if (!el) return false;
  el.scrollIntoView?.({ block: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1600);
  return true;
}

/* --- @mentions et #tâches : liste de propositions sous le champ de saisie */
function hidePick() {
  state.chat.pick = { items: [], active: 0, start: 0 };
  const pop = $("#mention-pop");
  if (pop) { pop.hidden = true; pop.innerHTML = ""; }
}
async function projectTasks(conv) {
  if (conv.kind !== "project") return [];
  if (!state.chat.tasks[conv.project]) state.chat.tasks[conv.project] = await api.tasks(conv.project).catch(() => []);
  return state.chat.tasks[conv.project];
}
async function showPick() {
  const t = $("#chat-input");
  const conv = currentConv();
  const pop = $("#mention-pop");
  if (!t || !conv || !pop) return;
  const caret = t.selectionStart ?? t.value.length;
  const at = CH.mentionAt(t.value, caret);
  const hash = at ? null : CH.hashAt(t.value, caret);
  let items = [], start = 0, prefix = "@";
  if (at) { items = CH.suggestions(conv, at.query, state.user.username); start = at.start; }
  else if (hash) { items = CH.taskSuggestions(await projectTasks(conv), hash.query); start = hash.start; prefix = "#"; }
  if (!items.length) return hidePick();
  const active = Math.min(state.chat.pick.active, items.length - 1);
  state.chat.pick = { items, active, start, prefix };
  pop.innerHTML = CH.popupHtml(items, active, esc);
  pop.hidden = false;
}
function choosePick(name) {
  const t = $("#chat-input");
  if (!t) return;
  const r = CH.applyMention(t.value, t.selectionStart ?? t.value.length, state.chat.pick.start, name, state.chat.pick.prefix || "@");
  t.value = r.text;
  t.setSelectionRange?.(r.caret, r.caret);
  state.chat.drafts[state.chat.current] = r.text;
  hidePick();
  t.focus();
}

/* recherche dans les messages (attente de 300 ms après la dernière frappe) */
let searchTimer = 0;
function clearSearch() {
  clearTimeout(searchTimer);
  if (state.chat.search) { state.chat.search = null; paintChatList(); }
}
document.addEventListener("input", (e) => {
  if (e.target.id !== "chat-search") return;
  const q = e.target.value.trim();
  clearTimeout(searchTimer);
  if (q.length < 2) return clearSearch();
  searchTimer = setTimeout(guard(async () => {
    const rows = await api.chatSearch(q);
    if (e.target.value.trim() !== q) return; // la saisie a changé entre-temps
    state.chat.search = { q, rows };
    paintChatList();
  }), 300);
});

/* fichiers choisis avec le trombone */
document.addEventListener("change", (e) => {
  if (e.target.id !== "chat-file") return;
  const c = state.chat;
  for (const f of [...e.target.files]) {
    if (c.files.length >= 3) { toast("3 fichiers au plus par message."); break; }
    if (f.size > 5 * 1024 * 1024) { toast(`« ${f.name} » dépasse 5 Mo.`); continue; }
    c.files.push(f);
  }
  e.target.value = "";
  paintComposerExtras();
});

document.addEventListener("input", (e) => {
  if (e.target.id !== "chat-input") return;
  const t = e.target;
  t.style.height = "auto";
  t.style.height = `${Math.min(t.scrollHeight, 140)}px`;
  state.chat.drafts[state.chat.current] = t.value;
  state.chat.pick.active = 0;
  showPick();
});

/* Les touches du champ de saisie passent avant les raccourcis globaux */
document.addEventListener("keydown", guard(async (e) => {
  if (e.target.id === "edit-input") {
    if (e.key === "Escape") { e.preventDefault(); return handlers["cancel-edit"](); }
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); return handlers["save-edit"]({ dataset: { id: state.chat.editing } }); }
    return;
  }
  if (e.target.id === "chat-search" && e.key === "Escape") { e.target.value = ""; return clearSearch(); }
  if (e.target.id !== "chat-input") return;
  if (e.key === "Escape" && state.chat.replyTo && !state.chat.pick.items.length) { state.chat.replyTo = null; return paintComposerExtras(); }
  const pick = state.chat.pick;
  if (pick.items.length) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      pick.active = (pick.active + (e.key === "ArrowDown" ? 1 : pick.items.length - 1)) % pick.items.length;
      return showPick();
    }
    if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); return choosePick(pick.items[pick.active].name); }
    if (e.key === "Escape") { e.preventDefault(); return hidePick(); }
  }
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); await sendChat(); }
}));

/* --- relève toutes les 15 s : pastilles, nouveaux messages du fil ouvert, nouvelles notifications */
async function pollChat() {
  if (!state.user || document.hidden || $("#app")?.hidden) return;
  const grew = await refreshChat();
  if (grew) toast("Vous avez été mentionné — voir les notifications (🔔).");
  const c = state.chat;
  if (state.page === "messages" && c.current) {
    const last = c.messages.length ? c.messages[c.messages.length - 1].id : 0;
    const { messages } = await api.chatMessages(c.current, { after: last });
    if (messages.length) {
      const stick = nearBottom($("#chat-msgs"));
      c.messages.push(...messages);
      await api.chatRead(c.current);
      paintMessages(stick);
    }
    const conv = currentConv();
    if (conv) conv.unread = 0;
    state.summary = { ...state.summary, unread_messages: unreadTotal() };
    paintChatList();
  } else if (state.page === "notifications") {
    state.notifs = await api.notifications();
    render();
  }
  renderSidebar();
}
setInterval(() => pollChat().catch(() => {}), 15000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) pollChat().catch(() => {}); });

/* ---------- navigation ---------- */
/* ---------- calendrier (fuseaux horaires) ---------- */
const myTz = () => state.user.timezone || TZ.browserZone();
const myTz2 = () => state.user.secondary_timezone || "";
let calToken = 0;

/** L'événement (ou l'occurrence d'une série) représenté par un élément du calendrier. */
const findEvent = (el) => state.cal.data?.events.find((x) => x.id === Number(el.dataset.id) && (x.occurrence_day || "") === (el.dataset.occ || ""));

async function loadCalendar() {
  const token = ++calToken;
  const { first, last } = CAL.range(state.cal.mode, state.cal.cursor);
  const q = { from: D.iso(first), to: D.iso(last) };
  if (state.cal.project) q.project = state.cal.project;
  if (state.cal.mine) q.mine = "1";
  const data = await api.calendar(q);
  if (token === calToken) state.cal.data = data; // une réponse tardive ne remplace pas une plus récente
}

async function openCalendar(patch = {}) {
  Object.assign(state.cal, patch);
  state.page = "calendar";
  state.selected = null;
  state.mini = new Date(state.cal.cursor);
  render(); // tout de suite : la navigation reste fluide pendant le chargement
  await loadCalendar();
  render();
}

function calShift(dir) {
  const c = state.cal;
  const cursor = c.mode === "month" ? D.addMonths(c.cursor, dir) : D.addDays(c.cursor, (c.mode === "week" ? 7 : 1) * dir);
  return openCalendar({ cursor, data: null });
}

function renderCalToolbar() {
  const c = state.cal;
  const tz = myTz();
  const modes = [["day", "Jour"], ["week", "Semaine"], ["month", "Mois"]];
  const opts = ['<option value="">Tous les projets</option>', ...state.projects.map((p) =>
    `<option value="${p.id}" ${String(c.project) === String(p.id) ? "selected" : ""}>${esc(p.name)}</option>`)].join("");
  $("#toolbar").innerHTML = `
    <h1 class="cal-title">${esc(CAL.title(c.mode, c.cursor))}</h1>
    <div class="nav"><button class="btn ghost sq" data-action="cal-prev" aria-label="Précédent">${icon("left")}</button>
      <button class="btn ghost" data-action="cal-today">Aujourd'hui</button>
      <button class="btn ghost sq" data-action="cal-next" aria-label="Suivant">${icon("right")}</button></div>
    <select data-calfilter="project" aria-label="Projet">${opts}</select>
    <label class="inline check-label"><input type="checkbox" data-calfilter="mine" ${c.mine ? "checked" : ""}> Mes tâches</label>
    <div class="grow"></div>
    <button class="btn ghost tzbtn" data-action="tz-settings" title="Changer de fuseau horaire">${icon("globe", 15)} ${esc(TZ.city(tz))} · ${TZ.offsetLabel(tz)}${myTz2() ? ` <span class="muted">/ ${esc(TZ.city(myTz2()))}</span>` : ""}</button>
    <div class="seg">${modes.map(([v, l]) => `<button class="${c.mode === v ? "on" : ""}" data-action="cal-mode" data-mode="${v}">${l}</button>`).join("")}</div>
    <button class="btn primary" data-action="new-event">Nouvel événement <kbd>N</kbd></button>`;
}

function renderCalView() {
  const old = $("#cal-scroll");
  const keep = old ? old.scrollTop : null;
  const c = state.cal;
  const now = new Date();
  $("#view").innerHTML = CAL.calendarHtml({ mode: c.mode, cursor: c.cursor, data: c.data, tz: myTz(), tz2: myTz2(), now, esc });
  const sc = $("#cal-scroll");
  if (!sc) return;
  if (keep !== null) sc.scrollTop = keep;
  else {
    const todayShown = c.mode === "day" ? TZ.dayKey(now, myTz()) === D.iso(c.cursor) : D.weekDays(c.cursor).some((d) => D.iso(d) === TZ.dayKey(now, myTz()));
    sc.scrollTop = Math.max(0, ((todayShown ? TZ.minutesOfDay(now, myTz()) - 90 : 7 * 60) / 60) * CAL.HOUR_PX);
  }
}
setInterval(() => { if (state.page === "calendar" && state.cal.data && !$("#modal").open) renderCalView(); }, 60000); // ligne « maintenant »

const zoneOptions = (selected) => {
  const mine = [...new Set([myTz(), myTz2()].filter(Boolean))];
  const label = (z) => `${TZ.city(z)} (${TZ.offsetLabel(z)})${TZ.city(z) === z.split("/").pop().replace(/_/g, " ") ? ` — ${z.split("/")[0]}` : ""}`;
  const group = (name, zones) => zones.length ? `<optgroup label="${name}">${zones.map((z) =>
    `<option value="${esc(z)}" ${z === selected ? "selected" : ""}>${esc(label(z))}</option>`).join("")}</optgroup>` : "";
  const all = TZ.allZones().filter((z) => !mine.includes(z));
  const extra = selected && ![...mine, ...all].includes(selected) ? [selected] : [];
  return group("Vos fuseaux", mine) + group("Tous les fuseaux", [...extra, ...all]);
};

const RECURRENCES = [["", "Ne se répète pas"], ["daily", "Tous les jours"], ["weekdays", "Du lundi au vendredi"], ["weekly", "Toutes les semaines"], ["monthly", "Tous les mois"]];
const RSVP_LABEL = { organizer: "Organisateur", invited: "Invité", accepted: "Accepté", declined: "Refusé" };

function eventModal({ ev = null, date = D.iso(state.cal.cursor), startMin = 9 * 60, endMin = null } = {}) {
  const tz = myTz();
  const editable = !ev || ev.can_edit;
  const writable = state.projects.filter((p) => p.role !== "viewer" || (ev && ev.project === p.id));
  const hm = (min) => `${TZ.pad(Math.floor(min / 60) % 24)}:${TZ.pad(min % 60)}`;
  // Pour une occurrence d'une série, le formulaire montre les horaires de la SÉRIE : enregistrer ne la déplace pas
  const s = ev ? new Date(ev.series_starts_at || ev.starts_at) : null;
  const e = ev ? new Date(ev.series_ends_at || ev.ends_at) : null;
  const end = endMin ?? startMin + 60;
  const v = ev
    ? { sd: TZ.dayKey(s, tz), st: TZ.hhmm(s, tz), ed: TZ.dayKey(e, tz), et: TZ.hhmm(e, tz) }
    : { sd: date, st: hm(startMin), ed: end >= 1440 ? D.iso(D.addDays(D.parse(date), 1)) : date, et: hm(end) };
  const dis = editable ? "" : "disabled";
  const known = new Map((ev?.invitees || []).map((i) => [i.id, i]));
  const mine = ev?.my_status;
  openModal(ev ? "Événement" : "Nouvel événement", `
    <label class="block">Titre<input name="title" required maxlength="200" value="${esc(ev?.title)}" ${dis} autofocus></label>
    ${mine && mine !== "organizer" ? `<div class="rsvp"><span class="grow">${esc(ev.creator_name || "Quelqu'un")} vous a invité · vous : <b>${RSVP_LABEL[mine]}</b></span>
      <button type="button" class="btn sm ${mine === "accepted" ? "primary" : ""}" data-rsvp="accepted">Accepter</button>
      <button type="button" class="btn sm ${mine === "declined" ? "primary" : ""}" data-rsvp="declined">Refuser</button></div>` : ""}
    <div class="when">
      <label>Début<input type="date" name="sd" required value="${v.sd}" ${dis}></label>
      <label>&nbsp;<input type="time" name="st" required value="${v.st}" ${dis}></label>
      <label>Fin<input type="date" name="ed" required value="${v.ed}" ${dis}></label>
      <label>&nbsp;<input type="time" name="et" required value="${v.et}" ${dis}></label>
    </div>
    <div class="rec-row">
      <label>Répétition<select name="recurrence" ${dis}>${RECURRENCES.map(([k, l]) => `<option value="${k}" ${(ev?.recurrence || "") === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label>Jusqu'au (facultatif)<input type="date" name="until" value="${ev?.recurrence_until || ""}" ${dis}></label>
    </div>
    ${ev?.recurrence ? '<p class="muted small">Événement récurrent : les modifications s\'appliquent à toute la série.</p>' : ""}
    <label class="block">Fuseau de ces horaires<select name="tz" ${dis}>${zoneOptions(tz)}</select></label>
    <p class="muted small">Le calendrier affiche tout en heure de ${esc(TZ.city(tz))}. Saisissez ici l'heure locale du lieu de l'événement : elle sera convertie.</p>
    <label class="block">Calendrier<select name="project" ${dis}><option value="">Personnel (vous seul)</option>${writable.map((p) =>
      `<option value="${p.id}" ${(ev ? ev.project : state.cal.project) == p.id ? "selected" : ""}>${esc(p.name)} (partagé)</option>`).join("")}</select></label>
    <div class="block"><span class="label-text">Invités</span><div id="invitees" class="invitees">${editable ? '<p class="muted small">Chargement…</p>'
      : ((ev.invitees || []).length ? ev.invitees.map((i) => `<div>${avatar(i.username, "xs")} ${esc(i.username)} <span class="st">${RSVP_LABEL[i.status]}</span></div>`).join("") : '<p class="muted small">Aucun invité.</p>')}</div></div>
    <label class="block">Description<textarea name="description" rows="3" ${dis}>${esc(ev?.description)}</textarea></label>
    ${ev && editable ? `<div class="row">${ev.recurrence ? '<button class="btn ghost danger" value="delete-one" formnovalidate>Supprimer cette occurrence</button>' : ""}
      <button class="btn ghost danger" value="delete" formnovalidate>${ev.recurrence ? "Supprimer toute la série" : "Supprimer"}</button></div>` : ""}
    ${editable ? actions(ev ? "Enregistrer" : "Créer") : `<p class="muted small">Lecture seule${ev.creator_name ? ` · créé par ${esc(ev.creator_name)}` : ""}.</p>
      <div class="row end"><button class="btn ghost" value="cancel" formnovalidate>Fermer</button></div>`}`, async (f) => {
    if (!editable) return;
    const body = {
      title: f.title, description: f.description, project: f.project ? Number(f.project) : null,
      starts_at: `${f.sd}T${f.st}`, ends_at: `${f.ed}T${f.et}`, timezone: f.tz,
      recurrence: f.recurrence || "", recurrence_until: f.recurrence ? f.until || null : null,
      attendees: [...$("#modal").querySelectorAll('#invitees input[type="checkbox"]')].filter((c) => c.checked).map((c) => Number(c.value)),
    };
    if (ev) await api.updateEvent(ev.id, body); else await api.createEvent(body);
    await loadCalendar();
    render();
  });
  const box = $("#modal");
  /* liste des invités possibles : membres du projet choisi, ou collègues pour un événement personnel */
  const paintInvitees = guard(async () => {
    const holder = box.querySelector("#invitees");
    const sel = box.querySelector('select[name="project"]');
    if (!holder || !editable) return;
    const checked = new Set([...holder.querySelectorAll("input:checked")].map((c) => Number(c.value)));
    const first = !holder.dataset.ready;
    const pid = sel?.value;
    const people = (pid ? (await api.members(Number(pid))).map((m) => ({ id: m.user_id, username: m.username })) : await api.calendarContacts())
      .filter((p) => p.id !== state.user.id);
    holder.dataset.ready = "1";
    holder.innerHTML = people.length ? people.map((p) => `<label><input type="checkbox" value="${p.id}" ${(first ? known.has(p.id) : checked.has(p.id)) ? "checked" : ""}>
      ${avatar(p.username, "xs")} <span>${esc(p.username)}</span>${known.has(p.id) ? `<span class="st">${RSVP_LABEL[known.get(p.id).status]}</span>` : ""}</label>`).join("")
      : '<p class="muted small">Personne à inviter : ajoutez des membres à un projet.</p>';
  });
  paintInvitees();
  box.querySelector('select[name="project"]')?.addEventListener("change", paintInvitees);
  box.querySelectorAll("[data-rsvp]").forEach((b) => b.addEventListener("click", guard(async () => {
    await api.rsvp(ev.id, b.dataset.rsvp);
    box.close();
    await loadCalendar();
    state.summary = await api.chatSummary().catch(() => state.summary);
    render();
  })));
  box.querySelector('button[value="delete"]')?.addEventListener("click", guard(async (event) => {
    event.preventDefault();
    if (!confirm(ev.recurrence ? "Supprimer toute la série d'événements ?" : "Supprimer cet événement ?")) return;
    await api.deleteEvent(ev.id);
    box.close();
    await loadCalendar();
    render();
  }));
  box.querySelector('button[value="delete-one"]')?.addEventListener("click", guard(async (event) => {
    event.preventDefault();
    await api.skipOccurrence(ev.id, ev.occurrence_day);
    box.close();
    await loadCalendar();
    render();
  }));
}

function accountModal() {
  const u = state.user;
  openModal("Mon compte", `
    <div class="account-head">${avatar(u.username)}<div><b>${esc(u.username)}</b><div class="muted small">${esc(u.email)}${u.is_staff ? " · administrateur" : ""}</div></div></div>
    <h3>Mes données</h3>
    <p class="muted small">Téléchargez tout ce que TaskFlow conserve à votre sujet (compte, projets, tâches, commentaires, événements, messages) dans un fichier JSON.</p>
    <div class="row"><button type="button" class="btn" data-account="export">Exporter mes données</button>
      <button type="button" class="btn" data-account="timezone">Fuseaux horaires</button></div>
    <h3 class="danger-title">Supprimer mon compte</h3>
    <p class="muted small">Définitif. Les projets où vous êtes seul(e) sont supprimés ; vos messages et commentaires restent, signés « Utilisateur supprimé ». Pour un projet partagé, cédez d'abord la propriété (Membres → Céder).</p>
    <label class="block">Mot de passe<input type="password" name="password" autocomplete="current-password"></label>
    <div class="row"><button type="button" class="btn ghost danger" data-account="delete">Supprimer définitivement mon compte</button></div>
    <div class="row end"><button class="btn ghost" value="cancel" formnovalidate>Fermer</button></div>`);
  const box = $("#modal");
  box.querySelector('[data-account="export"]')?.addEventListener("click", guard(async () => { await api.downloadExport(); toast("Fichier téléchargé."); }));
  box.querySelector('[data-account="timezone"]')?.addEventListener("click", () => timezoneModal());
  box.querySelector('[data-account="delete"]')?.addEventListener("click", guard(async () => {
    const password = box.querySelector('input[name="password"]').value;
    if (!password) return void toast("Saisissez votre mot de passe pour confirmer.");
    if (!confirm("Supprimer définitivement votre compte ? Cette action est irréversible.")) return;
    await api.deleteAccount(password);
    box.close();
    auth.logout();
    showAuth();
    toast("Votre compte a été supprimé.");
  }));
}

function timezoneModal() {
  const tz = myTz();
  const here = TZ.browserZone();
  const now = new Date();
  openModal("Fuseaux horaires", `
    <p class="muted">Le calendrier affiche toutes les heures dans votre fuseau principal. Un second fuseau ajoute une colonne d'heures, pratique pour travailler avec quelqu'un à l'autre bout du monde.</p>
    <label class="block">Fuseau principal<select name="tz">${zoneOptions(tz)}</select></label>
    <label class="block">Second fuseau<select name="tz2"><option value="">Aucun</option>${zoneOptions(myTz2())}</select></label>
    <p class="muted small">Il est ${TZ.hhmm(now, tz)} à ${esc(TZ.city(tz))}${myTz2() ? `, ${TZ.hhmm(now, myTz2())} à ${esc(TZ.city(myTz2()))}` : ""}.
      ${here !== tz ? `<button type="button" class="link" data-use-device>Utiliser le fuseau de cet appareil (${esc(TZ.city(here))})</button>` : ""}</p>
    ${actions("Enregistrer")}`, async (f) => {
    const me = await api.updateMe({ timezone: f.tz, secondary_timezone: f.tz2 });
    state.user = { ...state.user, ...me };
    state.cal.data = null;
    await openCalendar();
  });
  $("#modal").querySelector("[data-use-device]")?.addEventListener("click", () => {
    const sel = $("#modal").querySelector('select[name="tz"]');
    sel.value = here;
    if (sel.value !== here) sel.insertAdjacentHTML("afterbegin", `<option value="${esc(here)}" selected>${esc(here)}</option>`);
  });
}

function setView(v) {
  state.view = v;
  auth.pref.set("view", v);
  render();
}

/* ---------- événements ---------- */
const handlers = {
  "select-project": (el) => selectProject(Number(el.dataset.id)),
  "new-project": () => projectModal(null),
  "edit-project": () => projectModal(state.project),
  "new-task": (el) => canWrite() && taskModal(el.dataset.date || "", el.dataset.status || "todo"),
  "open-task": (el) => { state.selected = Number(el.dataset.task); renderPanel(); },
  "close-panel": () => { state.selected = null; renderPanel(); },
  "delete-task": async () => {
    if (!confirm("Supprimer cette tâche ?")) return;
    await api.deleteTask(state.project.id, state.selected);
    state.selected = null;
    await reloadTasks();
    render();
  },
  "gantt-zoom": (el) => { state.zoom = el.dataset.zoom; auth.pref.set("zoom", state.zoom); renderView(); scrollGanttToToday(false); },
  "gantt-today": () => scrollGanttToToday(),
  "gantt-canvas": (_el, e) => ganttPlanHere(e),
  replan: async () => {
    const { moved } = await api.replan(state.project.id);
    await reloadTasks();
    render();
    toast(moved.length ? `${moved.length} tâche(s) replanifiée(s).` : "Rien à rattraper.");
  },
  "go-home": () => goHome(),
  "go-admin": async () => {
    state.page = "admin";
    state.selected = null;
    await admin.load();
    render();
  },
  "goto-task": async (el) => {
    await selectProject(Number(el.dataset.project));
    state.selected = Number(el.dataset.task);
    renderPanel();
  },
  "home-done": async (el) => {
    await api.updateTask(Number(el.dataset.project), Number(el.dataset.task), { status: "done" });
    state.home = await api.dashboard();
    render();
    toast("Bravo, une de moins ! ✓");
  },
  "toggle-done": (el) => {
    const t = state.tasks.find((x) => x.id === Number(el.dataset.task));
    return patchTask(t.id, { status: t.status === "done" ? "todo" : "done" });
  },
  view: (el) => setView(el.dataset.view),
  "go-calendar": () => openCalendar(),
  "go-messages": () => openMessages(),
  "open-conv": (el) => openConv(Number(el.dataset.id)),
  "chat-project": () => openMessages(state.chat.convs.find((c) => c.project === state.project.id)?.id),
  "pick-mention": (el) => choosePick(el.dataset.name),
  "delete-message": async (el) => {
    if (!confirm("Supprimer ce message ?")) return;
    const id = Number(el.dataset.id);
    await api.chatDelete(id);
    state.chat.messages = state.chat.messages.filter((m) => m.id !== id);
    paintMessages(false);
  },
  "load-older": async () => {
    const c = state.chat;
    const r = await api.chatMessages(c.current, { before: c.messages[0].id });
    c.messages = [...r.messages, ...c.messages];
    c.hasMore = r.has_more;
    paintMessages(false);
  },
  "new-direct": async () => {
    const people = await api.chatContacts();
    if (!people.length) return void toast("Personne avec qui discuter : invitez d'abord quelqu'un dans un projet.");
    openModal("Nouveau message direct", `<p class="muted small">Vous pouvez écrire aux personnes qui partagent un projet avec vous.</p>
      <label class="block">Destinataire<select name="user" required>${people.map((p) => `<option value="${p.id}">${esc(p.username)}</option>`).join("")}</select></label>
      ${actions("Ouvrir la conversation")}`, async (f) => {
      const conv = await api.chatDirect(Number(f.user));
      await openMessages(conv.id);
    });
  },
  attach: () => $("#chat-file")?.click(),
  "remove-file": (el) => { state.chat.files.splice(Number(el.dataset.i), 1); paintComposerExtras(); },
  reply: (el) => {
    state.chat.replyTo = msgById(el.dataset.id);
    paintComposerExtras();
    $("#chat-input")?.focus();
  },
  "cancel-reply": () => { state.chat.replyTo = null; paintComposerExtras(); },
  "edit-msg": (el) => { state.chat.editing = Number(el.dataset.id); state.chat.reactFor = null; paintMessages(false); },
  "cancel-edit": () => { state.chat.editing = null; paintMessages(false); },
  "save-edit": async (el) => {
    const text = $("#edit-input")?.value ?? "";
    const updated = await api.chatEdit(Number(el.dataset.id), text);
    state.chat.editing = null;
    replaceMessage(updated);
    paintMessages(false);
  },
  "react-pop": (el) => {
    const id = Number(el.dataset.id);
    state.chat.reactFor = state.chat.reactFor === id ? null : id;
    paintMessages(false);
  },
  react: async (el) => {
    const updated = await api.chatReact(Number(el.dataset.id), el.dataset.emoji);
    state.chat.reactFor = null;
    replaceMessage(updated);
    paintMessages(false);
  },
  "goto-msg": (el) => { if (!flash(el.dataset.id)) toast("Ce message est plus haut dans l'historique : chargez les messages plus anciens."); },
  "open-hit": async (el) => {
    const id = Number(el.dataset.msg);
    const conv = Number(el.dataset.conv);
    state.chat.search = null;
    state.chat.current = conv;
    const r = await api.chatMessages(conv, { around: id });
    state.chat.messages = r.messages;
    state.chat.hasMore = r.has_more;
    await api.chatRead(conv);
    const c = state.chat.convs.find((x) => x.id === conv);
    if (c) c.unread = 0;
    render();
    flash(id);
  },
  "open-att": async (el) => {
    const win = window.open("", "_blank");
    try { const url = await api.attachmentUrl(el.dataset.id); if (win) win.location.href = url; } catch (err) { win?.close(); throw err; }
  },
  "download-att": async (el) => {
    const url = await api.attachmentUrl(el.dataset.id);
    const a = Object.assign(document.createElement("a"), { href: url, download: el.dataset.name || "fichier" });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  },
  "go-notifications": async () => {
    saveDraft();
    state.page = "notifications";
    state.selected = null;
    state.notifs = await api.notifications();
    render();
  },
  "open-notif": async (el) => {
    await api.markNotifications({ ids: [Number(el.dataset.id)] });
    await openMessages(Number(el.dataset.conv));
  },
  rsvp: async (el) => {
    await api.rsvp(Number(el.dataset.event), el.dataset.status);
    state.notifs = await api.notifications();
    state.summary = await api.chatSummary();
    render();
    toast(el.dataset.status === "accepted" ? "Invitation acceptée." : "Invitation refusée.");
  },
  "open-invite": async (el) => {
    await api.markNotifications({ invitations: [Number(el.dataset.id)] });
    const day = TZ.dayKey(new Date(el.dataset.start), myTz());
    await openCalendar({ cursor: D.parse(day), data: null });
  },
  "notifs-readall": async () => {
    await api.markNotifications({ all: true });
    state.notifs = await api.notifications();
    state.summary = { ...state.summary, unread_notifications: 0 };
    render();
  },
  account: () => accountModal(),
  "transfer-owner": async (el) => {
    const m = state.members.find((x) => x.user_id === Number(el.dataset.uid));
    if (!confirm(`Céder la propriété de « ${state.project.name} » à ${m.username} ? Vous deviendrez simple membre.`)) return;
    Object.assign(state.project, await api.transferProject(state.project.id, m.user_id));
    state.members = await api.members(state.project.id);
    $("#modal").close();
    render();
    toast(`${m.username} est maintenant propriétaire.`);
  },
  "toggle-side": () => { auth.pref.set("side", sideCollapsed() ? "open" : "collapsed"); renderSidebar(); },
  "cal-prev": () => calShift(-1),
  "cal-next": () => calShift(1),
  "cal-today": () => openCalendar({ cursor: D.parse(TZ.dayKey(new Date(), myTz())), data: null }),
  "cal-mode": (el) => { auth.pref.set("calmode", el.dataset.mode); return openCalendar({ mode: el.dataset.mode, data: null }); },
  "cal-day": (el) => openCalendar({ mode: "day", cursor: D.parse(el.dataset.date), data: null }),
  "new-event": () => {
    const now = new Date();
    const today = TZ.dayKey(now, myTz());
    const { first, last } = CAL.range(state.cal.mode === "month" ? "day" : state.cal.mode, state.cal.cursor);
    const inView = state.cal.mode !== "month" && today >= D.iso(first) && today <= D.iso(last);
    const date = inView || state.cal.mode === "month" ? today : D.iso(state.cal.cursor);
    eventModal({ date, startMin: date === today ? Math.min(1380, Math.ceil((TZ.minutesOfDay(now, myTz()) + 1) / 30) * 30) : 9 * 60 });
  },
  "cal-slot": (el, e) => {
    const month = el.dataset.month === "1";
    const y = e.clientY - el.getBoundingClientRect().top;
    eventModal({ date: el.dataset.date, startMin: month ? 9 * 60 : CAL.minuteAt(y) });
  },
  "edit-event": (el) => {
    const ev = findEvent(el);
    if (ev) eventModal({ ev });
  },
  "tz-settings": () => timezoneModal(),
  "mini-prev": () => { state.mini = D.addMonths(state.mini, -1); renderSidebar(); },
  "mini-next": () => { state.mini = D.addMonths(state.mini, 1); renderSidebar(); },
  "mini-day": (el) => openCalendar({ mode: state.cal.mode === "month" ? "month" : state.page === "calendar" ? state.cal.mode : "week", cursor: D.parse(el.dataset.date), data: null }),
  members: () => membersModal(),
  "remove-member": async (el) => {
    await api.removeMember(state.project.id, Number(el.dataset.uid));
    state.members = await api.members(state.project.id);
    await reloadTasks();
    render();
    membersModal();
  },
  theme: () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"),
  logout: () => {
    auth.logout();
    state.chat = { convs: [], current: null, messages: [], hasMore: false, drafts: {}, pick: { items: [], active: 0, start: 0 }, editing: null, reactFor: null, replyTo: null, files: [], search: null, tasks: {} };
    state.summary = { unread_messages: 0, unread_notifications: 0 };
    showAuth();
  },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-action]");
  if (suppressClick) { suppressClick = false; return; }
  if (el && handlers[el.dataset.action]) guard(handlers[el.dataset.action])(el, e);
});

document.addEventListener("change", guard(async (e) => {
  const t = e.target;
  if (t.dataset.change === "role") {
    await api.setRole(state.project.id, Number(t.dataset.uid), t.value);
    state.members = await api.members(state.project.id);
    return;
  }
  if (t.dataset.admin || t.dataset.setting) {
    await admin.onChange(t);
    return;
  }
  if (t.dataset.calfilter) {
    state.cal[t.dataset.calfilter] = t.type === "checkbox" ? t.checked : t.value;
    state.cal.data = null;
    await openCalendar();
    return;
  }
  if (t.dataset.gantt === "critical") {
    state.showCritical = t.checked;
    auth.pref.set("critical", t.checked ? "1" : "0");
    renderView();
    return;
  }
  if (t.dataset.dep && state.selected) {
    const ids = [...document.querySelectorAll("[data-dep]")].filter((c) => c.checked).map((c) => Number(c.dataset.dep));
    await patchTask(state.selected, { dependencies: ids }, true);
    return;
  }
  if (t.dataset.filter) {
    state.filter[t.dataset.filter] = t.type === "checkbox" ? t.checked : t.value;
    renderView();
    return;
  }
  if (t.dataset.field && state.selected) {
    const f = t.dataset.field;
    let v = t.type === "checkbox" ? t.checked : t.value;
    if (f === "priority") v = Number(v);
    if (f === "due_date" || f === "start_date") v = v || null;
    if (f === "assignee") v = v ? Number(v) : null;
    if (f === "title" && !v.trim()) { renderPanel(); return; }
    await patchTask(state.selected, { [f]: v }, true);
  }
}));

document.addEventListener("submit", guard(async (e) => {
  if (e.target.id === "chat-form") {
    e.preventDefault();
    await sendChat();
    return;
  }
  if (e.target.id === "quick-add") {
    e.preventDefault();
    const title = e.target.elements.newtitle.value.trim();
    if (!title) return;
    await api.createTask(state.project.id, { title });
    await reloadTasks();
    render();
    $("#quick-add input")?.focus();
    return;
  }
  if (e.target.id === "comment-form") {
    e.preventDefault();
    const input = e.target.content;
    const c = await api.addComment(state.project.id, state.selected, input.value);
    state.comments.push(c);
    input.value = "";
    paintComments();
  }
}));

/* glisser-déposer : déplacer une tâche vers un jour (échéance) ou une colonne (statut) */
document.addEventListener("dragstart", (e) => {
  const c = e.target.closest?.("[data-task]");
  if (!c || !canWrite()) return;
  e.dataTransfer.setData("text/plain", c.dataset.task);
  e.dataTransfer.effectAllowed = "move";
  c.classList.add("dragging");
});
const clearDrag = () => document.querySelectorAll(".dragging,.drop-over").forEach((n) => n.classList.remove("dragging", "drop-over"));
document.addEventListener("dragend", clearDrag);
document.addEventListener("dragover", (e) => {
  const z = e.target.closest?.("[data-drop]");
  if (!z || !canWrite()) return;
  e.preventDefault();
  document.querySelectorAll(".drop-over").forEach((n) => n !== z && n.classList.remove("drop-over"));
  z.classList.add("drop-over");
});
document.addEventListener("drop", guard(async (e) => {
  const z = e.target.closest?.("[data-drop]");
  clearDrag();
  if (!z || !canWrite()) return;
  e.preventDefault();
  const id = Number(e.dataTransfer.getData("text/plain"));
  if (!id) return;
  await patchTask(id, { status: z.dataset.status });
}));

/* raccourcis clavier, façon Notion Calendar */
document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "Escape" && state.selected && !$("#modal").open) return handlers["close-panel"]();
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || $("#modal").open || !state.user) return;
  const k = e.key.toLowerCase();
  if (k === "h") return void goHome();
  if (k === "c") return void openCalendar();
  if (k === "i") return void openMessages();
  if (state.page === "calendar") {
    if (k === "t") handlers["cal-today"]();
    else if (k === "d" || k === "w" || k === "m") handlers["cal-mode"]({ dataset: { mode: { d: "day", w: "week", m: "month" }[k] } });
    else if (k === "n") { e.preventDefault(); handlers["new-event"](); }
    else if (k === "arrowleft") calShift(-1);
    else if (k === "arrowright") calShift(1);
    return;
  }
  if (state.page !== "project" || !state.project) return;
  if (k === "d") setView("dashboard");
  else if (k === "g") setView("gantt");
  else if (k === "e") setView("team");
  else if (k === "l") setView("list");
  else if (k === "b") setView("board");
  else if (k === "n" && canWrite()) { e.preventDefault(); taskModal(); }
});

/* ---------- calendrier : déplacer, redimensionner et créer à la souris ---------- */
let cdrag = null;
const SNAP = 15; // minutes
const snap = (px) => Math.round(((px / CAL.HOUR_PX) * 60) / SNAP) * SNAP;

document.addEventListener("pointerdown", (e) => {
  if (state.page !== "calendar" || state.cal.mode === "month" || e.button !== 0 || $("#modal").open) return;
  const block = e.target.closest?.(".cevent");
  const col = e.target.closest?.(".ccol");
  if (!block && !col) return;
  const cols = [...document.querySelectorAll(".ccol")];
  if (block) {
    const ev = findEvent(block);
    if (!ev || !ev.can_edit) return;
    cdrag = { kind: e.target.closest("[data-resize]") ? "resize" : "move", ev, el: block, cols, x0: e.clientX, y0: e.clientY,
      from: cols.indexOf(block.closest(".ccol")), h0: block.offsetHeight, moved: false, dmin: 0, dcol: 0 };
  } else {
    cdrag = { kind: "create", col, cols, y0: e.clientY, top: col.getBoundingClientRect().top, moved: false, a: 0, b: 0 };
    cdrag.a = Math.max(0, Math.floor((((e.clientY - cdrag.top) / CAL.HOUR_PX) * 60) / SNAP) * SNAP);
  }
  block?.setPointerCapture?.(e.pointerId);
});

document.addEventListener("pointermove", (e) => {
  const d = cdrag;
  if (!d) return;
  if (!d.moved && Math.abs(e.clientY - d.y0) < 5 && Math.abs(e.clientX - (d.x0 ?? e.clientX)) < 5) return;
  d.moved = true;
  if (d.kind === "create") {
    const m = Math.max(0, Math.min(1440, Math.round((((e.clientY - d.top) / CAL.HOUR_PX) * 60) / SNAP) * SNAP));
    d.b = m;
    let ghost = d.col.querySelector(".cghost");
    if (!ghost) { ghost = document.createElement("div"); ghost.className = "cghost"; d.col.appendChild(ghost); }
    const lo = Math.min(d.a, m);
    const hi = Math.max(d.a, m, lo + SNAP);
    ghost.style.top = `${(lo / 60) * CAL.HOUR_PX}px`;
    ghost.style.height = `${((hi - lo) / 60) * CAL.HOUR_PX}px`;
    ghost.textContent = `${TZ.hourLabel(lo)} – ${TZ.hourLabel(hi)}`;
    return;
  }
  d.el.classList.add("dragging");
  d.dmin = snap(e.clientY - d.y0);
  if (d.kind === "resize") {
    d.dmin = Math.max(d.dmin, -Math.round(((d.h0 - 18) / CAL.HOUR_PX) * 60 / SNAP) * SNAP);
    d.el.style.height = `${d.h0 + (d.dmin / 60) * CAL.HOUR_PX}px`;
    return;
  }
  const idx = d.cols.findIndex((c) => { const r = c.getBoundingClientRect(); return e.clientX >= r.left && e.clientX < r.right; });
  d.dcol = idx < 0 ? 0 : idx - d.from;
  const dx = d.cols[d.from + d.dcol].getBoundingClientRect().left - d.cols[d.from].getBoundingClientRect().left;
  d.el.style.transform = `translate(${dx}px, ${(d.dmin / 60) * CAL.HOUR_PX}px)`;
});

document.addEventListener("pointerup", guard(async () => {
  const d = cdrag;
  cdrag = null;
  if (!d) return;
  d.col?.querySelector(".cghost")?.remove();
  if (!d.moved) return; // simple clic : le gestionnaire de clic ouvre la fenêtre
  suppressClick = true;
  setTimeout(() => (suppressClick = false), 0);
  if (d.kind === "create") {
    const lo = Math.min(d.a, d.b);
    const hi = Math.max(d.a, d.b, lo + SNAP);
    return eventModal({ date: d.col.dataset.date, startMin: lo, endMin: hi });
  }
  d.el.classList.remove("dragging");
  if (d.dmin === 0 && d.dcol === 0) { d.el.style.transform = ""; d.el.style.height = ""; return; }
  const tz = myTz();
  const ev = d.ev;
  const start = new Date(ev.series_starts_at || ev.starts_at);
  const end = new Date(ev.series_ends_at || ev.ends_at);
  const body = d.kind === "resize"
    ? { ends_at: TZ.shiftLocal(end, tz, 0, d.dmin), starts_at: TZ.shiftLocal(start, tz), timezone: tz }
    : { starts_at: TZ.shiftLocal(start, tz, d.dcol, d.dmin), ends_at: TZ.shiftLocal(end, tz, d.dcol, d.dmin), timezone: tz };
  try {
    await api.updateEvent(ev.id, body);
    if (ev.recurrence) toast("Toute la série a été modifiée.");
  } catch (err) { toast(err.message); }
  await loadCalendar();
  renderCalView();
}));

/* Entrée sur un événement du calendrier = l'ouvrir (accessibilité clavier) */
document.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.classList?.contains?.("cevent")) { e.preventDefault(); handlers["edit-event"](e.target); }
});

/* ---------- Gantt : déplacer / redimensionner les barres ---------- */
let drag = null;
let suppressClick = false;
const DAY = 86400000;

document.addEventListener("pointerdown", (e) => {
  const bar = e.target.closest?.(".gbar, .gmile");
  const g = $("#gantt-scroll");
  if (!bar || !g || !canWrite() || e.button !== 0 || bar.classList.contains("ro")) return;
  const t = state.tasks.find((x) => x.id === Number(bar.dataset.task));
  const s = t.start_date || t.due_date;
  const handle = e.target.closest("[data-gdrag]");
  drag = {
    t, bar, mode: handle ? handle.dataset.gdrag : "move", x0: e.clientX, days: 0, moved: false,
    dayW: Number(g.dataset.daywidth), s0: s, d0: t.due_date || s,
    left0: parseFloat(bar.style.left), width0: parseFloat(bar.style.width),
  };
  bar.setPointerCapture?.(e.pointerId);
  e.preventDefault();
});

document.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.x0;
  if (Math.abs(dx) > 3) drag.moved = true;
  if (!drag.moved) return;
  const length = Math.round((D.parse(drag.d0) - D.parse(drag.s0)) / DAY); // durée − 1
  let days = Math.round(dx / drag.dayW);
  if (drag.mode === "start") days = Math.min(days, length);
  if (drag.mode === "end") days = Math.max(days, -length);
  drag.days = days;
  const px = days * drag.dayW;
  const b = drag.bar;
  if (drag.mode === "move") b.style.left = `${drag.left0 + px}px`;
  if (drag.mode === "start") { b.style.left = `${drag.left0 + px}px`; b.style.width = `${drag.width0 - px}px`; }
  if (drag.mode === "end") b.style.width = `${drag.width0 + px}px`;
  b.classList.add("dragging");
});

document.addEventListener("pointerup", guard(async () => {
  if (!drag) return;
  const { t, mode, days, moved, s0, d0 } = drag;
  drag = null;
  if (!moved) return;
  suppressClick = true;
  setTimeout(() => (suppressClick = false), 0);
  if (days === 0) { renderView(); return; }
  const shift = (iso, n) => D.iso(D.addDays(D.parse(iso), n));
  const start = mode === "end" ? s0 : shift(s0, days);
  const due = mode === "start" ? d0 : shift(d0, days);
  try {
    await patchTask(t.id, { start_date: start, due_date: due });
  } catch (err) {
    toast(err.message);
    renderView();
  }
}));

async function ganttPlanHere(e) {
  if (!canWrite()) return;
  const canvas = $("#gantt-canvas");
  const g = $("#gantt-scroll");
  const rect = canvas.getBoundingClientRect();
  const rows = ganttRowsFor();
  const row = Math.floor((e.clientY - rect.top) / 36);
  const t = rows[row];
  if (!t || t.start_date || t.due_date) return;
  const day = Math.floor((e.clientX - rect.left) / Number(g.dataset.daywidth));
  const iso = D.iso(D.addDays(D.parse(g.dataset.start), day));
  await patchTask(t.id, { start_date: iso, due_date: iso });
}
function ganttRowsFor() {
  const planned = state.tasks.filter((t) => t.start_date || t.due_date)
    .sort((a, b) => (a.start_date || a.due_date).localeCompare(b.start_date || b.due_date) || a.id - b.id);
  return [...planned, ...state.tasks.filter((t) => !t.start_date && !t.due_date).sort((a, b) => a.id - b.id)];
}

/* ---------- administration ---------- */
const admin = createAdmin({ api, state, render, openModal, actions, toast, esc });
Object.assign(handlers, admin.handlers);

/* ---------- authentification ---------- */
function showAuth() {
  $("#app").hidden = true;
  $("#auth").hidden = false;
}
async function startApp() {
  $("#auth").hidden = true;
  $("#app").hidden = false;
  try {
    await refreshChat().catch(() => {}); // pastilles de la barre latérale ; la messagerie ne doit jamais bloquer le reste
    await loadProjects();
    if (location.pathname.replace(/\/$/, "") === "/admin" && state.user.is_staff) await handlers["go-admin"]();
  } catch (err) {
    $("#view").innerHTML = `<div class="empty"><h2>Impossible de charger vos données</h2><p class="muted">${esc(err.message)}</p>
      <button class="btn primary" onclick="location.reload()">Réessayer</button></div>`;
    toast(err.message);
  }
}

document.querySelectorAll("[data-auth-tab]").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll("[data-auth-tab]").forEach((x) => x.classList.toggle("on", x === b));
    $("#login-form").hidden = b.dataset.authTab !== "login";
    $("#register-form").hidden = b.dataset.authTab !== "register";
  }));

$("#login-form").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  await api.login(f.username, f.password);
  state.user = await api.me();
  await startApp();
}));
$("#register-form").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  await api.register(f);
  await api.login(f.username, f.password);
  state.user = await api.me();
  await startApp();
}));

api.publicConfig().then((cfg) => {
  if (cfg.registration_open) return;
  document.querySelector('[data-auth-tab="register"]')?.remove();
  $("#register-form")?.remove();
  $("#auth-tabs")?.insertAdjacentHTML("afterend", '<p class="muted small">Les inscriptions sont fermées. Contactez un administrateur pour obtenir un compte.</p>');
}).catch(() => {});

auth.onLogout(showAuth);
(async () => {
  if (!auth.isLoggedIn()) return showAuth();
  try {
    state.user = await api.me();
    await startApp();
  } catch { showAuth(); }
})();
