import { icon } from "./icons.js";
// Tableaux de bord : personnel (tous mes projets) et projet (équipe). Fonctions pures qui renvoient du HTML.
import * as D from "./dates.js";
import { barChart, donut, lineChart, ring } from "./charts.js";

const HEALTH = {
  ok: ["En bonne voie", "h-ok"], risk: ["À surveiller", "h-risk"], late: ["En retard", "h-late"],
  done: ["Terminé", "h-ok"], empty: ["Vide", "h-free"],
};
const ROLE = { owner: "Propriétaire", member: "Membre", viewer: "Lecteur" };
const day = (iso) => D.fmt(D.parse(iso), { day: "numeric", month: "short" });
const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;
const card = (title, body, cls = "", extra = "") =>
  `<section class="card ${cls}"><header><h3>${title}</h3>${extra}</header>${body}</section>`;
const kpi = (label, value, sub, valueCls = "") =>
  `<div class="kpi"><span class="k-label">${label}</span><b class="${valueCls}">${value}</b><small>${sub}</small></div>`;
const delta = (now, before) => {
  const d = now - before;
  return d === 0 ? "comme la semaine passée" : `${d > 0 ? "+" : "−"}${Math.abs(d)} vs semaine passée`;
};

/* ------------------------------------------------------------------ personnel */
export function homeHtml({ data, user, esc, avatar }) {
  const k = data.kpis;
  const now = new Date();
  const lead = k.late
    ? `Vous avez <b class="bad">${plural(k.late, "tâche en retard", "tâches en retard")}</b> et ${plural(k.today, "tâche", "tâches")} aujourd'hui.`
    : k.today ? `${plural(k.today, "tâche", "tâches")} aujourd'hui, rien en retard.` : "Rien d'urgent aujourd'hui.";

  const focus = data.focus.map((t) => {
    const label = t.days_late ? `<span class="late-text">${t.days_late} j de retard</span>`
      : `<span class="muted">${t.due ? (t.due === D.iso(now) ? "aujourd'hui" : `jusqu'au ${day(t.due)}`) : "en cours"}</span>`;
    return `<div class="frow ${t.days_late ? "is-late" : ""}">
      <button class="check" data-action="home-done" data-project="${t.project_id}" data-task="${t.id}" aria-label="Terminer « ${esc(t.title)} »">✓</button>
      <button class="frow-main" data-action="goto-task" data-project="${t.project_id}" data-task="${t.id}">
        <span class="ellipsis grow">${esc(t.title)}</span><span class="tag">${esc(t.project)}</span>${label}</button></div>`;
  }).join("") || '<p class="muted pad">Rien à faire pour le moment — profitez-en.</p>';

  const week = data.week.map((w, i) => `<div class="wday ${i === 0 ? "today" : ""}">
      <div class="wday-h"><span>${esc(D.fmt(D.parse(w.date), { weekday: "short" }))}</span><b>${D.parse(w.date).getDate()}</b></div>
      ${w.tasks.map((t) => `<button class="wchip p${t.status === "doing" ? 2 : 3}" data-action="goto-task" data-project="${t.project_id}" data-task="${t.id}" title="${esc(t.title)} — ${esc(t.project)}">${esc(t.title)}</button>`).join("")
        || '<span class="muted small">—</span>'}</div>`).join("");

  const alerts = data.alerts.map((a) => `<button class="alert" data-action="goto-task" data-project="${a.project_id}" data-task="${a.task}">
      <span class="sev sev-high"></span><span class="grow"><b>${esc(a.user)}</b> — ${esc(a.title)}${a.count > 1 ? ` <span class="muted">(+${a.count - 1})</span>` : ""}
      <span class="muted small block">${esc(a.project)}</span></span><span class="late-text nowrap">${a.days_late} j</span></button>`).join("")
    || '<p class="muted pad"><span class="sev sev-ok"></span> Aucun retard chez vos collègues.</p>';

  const projects = data.projects.map((p) => {
    const [label, cls] = HEALTH[p.health];
    const end = p.forecast_end ? `Fin prévue ${day(p.forecast_end)}` : "";
    const dl = p.deadline ? ` · échéance ${day(p.deadline)}` : "";
    return `<button class="proj-card ${cls}" data-action="select-project" data-id="${p.id}">
      ${ring(p.progress)}<div class="grow"><div class="pc-name">${esc(p.name)}</div>
        <div class="muted small">${ROLE[p.role] || ""} · ${plural(p.members, "membre", "membres")}</div>
        <div class="muted small">${end}${dl}</div>
        <div class="pc-line"><span class="badge ${cls}">${label}</span>
          ${p.my_open ? `<span class="muted small">${plural(p.my_open, "tâche pour moi", "tâches pour moi")}</span>` : ""}
          ${p.team_late ? `<span class="late-text small">${plural(p.team_late, "collègue en retard", "collègues en retard")}</span>` : ""}</div></div></button>`;
  }).join("") || '<div class="empty small-empty"><p class="muted">Aucun projet pour l\'instant.</p><button class="btn primary" data-action="new-project">Créer un projet</button></div>';

  return `<div class="dash">
    <div class="dash-hello"><div><h2>Bonjour ${esc(user.username)}</h2>
      <p class="muted">${esc(D.fmt(now, { weekday: "long", day: "numeric", month: "long" }))} — ${lead}</p></div>
      <div class="hero-actions"><button class="btn" data-action="go-calendar">${icon("calendar", 16)}Calendrier</button><button class="btn" data-action="go-messages">${icon("message", 16)}Messages</button></div></div>
    <div class="kpis dash-kpis">
      ${kpi("Aujourd'hui", k.today, "en cours ou prévues")}
      ${kpi("En retard", k.late, k.late ? "à rattraper en priorité" : "rien en retard", k.late ? "bad" : "")}
      ${kpi("À venir", k.upcoming, "dans les 7 prochains jours")}
      ${kpi("Terminées (7 j)", k.done_this_week, delta(k.done_this_week, k.done_last_week))}
    </div>
    <div class="dash-grid">
      ${card("Mon focus", `<div class="frows">${focus}</div>`, "span-7")}
      ${card("Productivité", barChart(data.done_series) + `<p class="muted small">Tâches terminées par jour sur 14 jours.</p>`, "span-5")}
      ${card("Mes 7 prochains jours", `<div class="wstrip">${week}</div>`, "span-7", k.unscheduled ? `<span class="muted small">${plural(k.unscheduled, "tâche sans date", "tâches sans date")}</span>` : "")}
      ${card("Alertes équipe", `<div class="alerts">${alerts}</div>`, "span-5")}
      ${card("Mes projets", `<div class="proj-cards">${projects}</div>`, "span-12", '<button class="btn ghost" data-action="new-project">+ Nouveau projet</button>')}
    </div></div>`;
}

/* ------------------------------------------------------------------ projet */
export function projectDashHtml({ insights, project, esc, avatar }) {
  if (!insights) return '<div class="empty"><p class="muted">Indicateurs indisponibles.</p></div>';
  const i = insights;
  const s = i.stats;
  const slip = i.slip_days;
  const forecastSub = i.forecast_end == null ? "Tout est terminé"
    : slip == null ? "pas d'échéance définie"
    : slip > 0 ? `<span class="bad">+${slip} j sur ${i.deadline ? "l'échéance" : "le plan"}</span>`
    : `<span class="ok">${-slip === 0 ? "pile à l'échéance" : `${-slip} j de marge`}</span>`;
  const sc = s.status_counts;
  const totalTasks = sc.todo + sc.doing + sc.done;
  const legend = [["À faire", sc.todo, "seg-todo"], ["En cours", sc.doing, "seg-doing"], ["Terminées", sc.done, "seg-done"]]
    .map(([l, n, c]) => `<li><i class="sw ${c}"></i>${l}<b>${n}</b></li>`).join("");
  const pmax = Math.max(...Object.values(s.priority_counts), 1);
  const prio = [["1", "Haute"], ["2", "Normale"], ["3", "Basse"]].map(([k, l]) =>
    `<div class="pbar"><span>${l}</span><div><i class="p${k}" style="width:${(s.priority_counts[k] / pmax) * 100}%"></i></div><b>${s.priority_counts[k]}</b></div>`).join("");

  const team = i.team.map((m) => {
    const lateN = m.late.length;
    const openN = m.open - lateN;
    const tot = Math.max(m.total, 1);
    const [label, cls] = { late: ["En retard", "st-late"], overloaded: ["Surchargé", "st-over"], ok: ["OK", "st-ok"], free: ["Libre", "st-free"] }[m.state];
    return `<button class="trow" data-action="view" data-view="team">${avatar(m.username, "sm")}<span class="tname ellipsis">${esc(m.username)}</span>
      <div class="stack-bar" title="${m.done} terminées, ${openN} ouvertes, ${lateN} en retard">
        <i class="s-done" style="width:${(m.done / tot) * 100}%"></i><i class="s-open" style="width:${(openN / tot) * 100}%"></i><i class="s-late" style="width:${(lateN / tot) * 100}%"></i></div>
      <span class="badge ${cls}">${label}</span></button>`;
  }).join("") || '<p class="muted pad">Aucun membre.</p>';

  const due = s.due_soon.map((t) => `<button class="drow" data-action="open-task" data-task="${t.id}">
      <span class="dd">${day(t.due)}</span><span class="ellipsis grow">${esc(t.title)}</span><span class="muted small">${t.who ? esc(t.who) : "—"}</span></button>`).join("")
    || '<p class="muted pad">Aucune échéance dans les 7 prochains jours.</p>';
  const risks = i.risks.slice(0, 6).map((r) => {
    const inner = `<span class="sev sev-${r.severity}"></span><span class="grow">${esc(r.message)}</span>`;
    return r.task ? `<button class="risk" data-action="open-task" data-task="${r.task}">${inner}</button>` : `<div class="risk">${inner}</div>`;
  }).join("") || '<p class="muted pad"><span class="sev sev-ok"></span> Aucun risque détecté.</p>';
  const recent = s.recent_done.map((t) => `<div class="drow"><span class="dd ok">✓</span><span class="ellipsis grow">${esc(t.title)}</span>
      <span class="muted small">${t.who ? esc(t.who) + " · " : ""}${day(t.at.slice(0, 10))}</span></div>`).join("")
    || '<p class="muted pad">Aucune tâche terminée pour l\'instant.</p>';

  const v = s.velocity;
  return `<div class="dash">
    <div class="kpis dash-kpis five">
      ${kpi("Avancement", `${i.progress} %`, `${i.done}/${i.total} tâches terminées`)}
      ${kpi("Fin prévue", i.forecast_end ? day(i.forecast_end) : "—", forecastSub)}
      ${kpi("En retard", i.late_count, i.late_count ? "tâche(s) à rattraper" : "rien en retard", i.late_count ? "bad" : "")}
      ${kpi("Vélocité (7 j)", v.this_week, delta(v.this_week, v.last_week))}
      ${kpi("Chemin critique", plural(i.critical_path.task_ids.length, "tâche", "tâches"), `${i.critical_path.duration_days} jours incompressibles`)}
    </div>
    <div class="dash-grid">
      ${card("Avancement dans le temps", lineChart(s.burnup) + `<p class="legend"><i class="sw l-created"></i>Créées <i class="sw l-done"></i>Terminées</p>`, "span-8")}
      ${card("Répartition", `<div class="split">${donut([{ value: sc.todo, cls: "seg-todo" }, { value: sc.doing, cls: "seg-doing" }, { value: sc.done, cls: "seg-done" }], { top: totalTasks, bottom: "tâches" })}<ul class="legend-list">${legend}</ul></div><h4 class="sub">Ouvertes par priorité</h4>${prio}`, "span-4")}
      ${card("Équipe", `<div class="trows">${team}</div><p class="legend"><i class="sw s-done"></i>Terminées <i class="sw s-open"></i>Ouvertes <i class="sw s-late"></i>En retard</p>`, "span-6", '<button class="btn ghost" data-action="view" data-view="team">Détail →</button>')}
      ${card("Échéances de la semaine", `<div class="drows">${due}</div>`, "span-6")}
      ${card("Risques", `<div class="risks-list">${risks}</div>`, "span-6")}
      ${card("Terminées récemment", `<div class="drows">${recent}</div>`, "span-6")}
    </div></div>`;
}
