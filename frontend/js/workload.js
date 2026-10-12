/* Onglet « Charge » : qui est surchargé semaine par semaine, propositions de rééquilibrage, et simulation
   « et si une tâche prenait du retard ? » (calculée par le moteur Rust). Fonctions pures qui renvoient du HTML. */
import * as D from "./dates.js";
import { icon } from "./icons.js";

const WEEK_OPTIONS = [2, 4, 8, 12];
export const DELAY_OPTIONS = [1, 2, 3, 5, 10, 20];

/** Niveau de charge : free < 60 %, ok jusqu'à 100 %, high jusqu'à 150 %, over au-delà. */
export const level = (percent) => (percent === 0 ? "none" : percent < 60 ? "free" : percent <= 100 ? "ok" : percent <= 150 ? "high" : "over");

const weekLabel = (w) => {
  const a = D.parse(w.start);
  const b = D.parse(w.end);
  return `${a.getDate()}–${b.getDate()} ${D.fmt(b, { month: "short" })}`;
};

function cell(c, titles, esc) {
  const names = c.tasks.map((id) => titles.get(id)).filter(Boolean);
  return `<div class="wl-cell lv-${level(c.percent)}" title="${esc(names.join("\n") || "Rien de prévu")}"><b>${c.percent ? c.percent + " %" : "—"}</b>${c.days ? `<small>${c.days} j</small>` : ""}</div>`;
}

export function workloadHtml({ data, sim, weeks, delay, tasks, canWrite, esc, avatar }) {
  if (!data) return `<div class="empty small-empty"><p class="muted">Chargement…</p></div>`;
  const titles = new Map(tasks.map((t) => [t.id, t.title]));
  const opts = (list, cur, fmt) => list.map((v) => `<option value="${v}" ${v === cur ? "selected" : ""}>${fmt(v)}</option>`).join("");
  const grid = `<div class="wl-grid" style="--cols:${data.weeks.length}">
    <div class="wl-head"></div>${data.weeks.map((w) => `<div class="wl-head">${esc(weekLabel(w))}</div>`).join("")}
    ${data.members.map((m) => `<div class="wl-who">${avatar(m.username, "sm")}<span class="ellipsis">${esc(m.username)}</span></div>${m.cells.map((c) => cell(c, titles, esc)).join("")}`).join("")}</div>`;
  const sugg = data.suggestions.length
    ? data.suggestions.map((s) => `<div class="sugg"><span class="sugg-ico">${icon("users", 16)}</span>
        <div class="grow"><b>« ${esc(s.title)} »</b> : ${esc(s.from)} → ${esc(s.to)}<div class="muted small">${esc(s.reason)}</div></div>
        ${canWrite ? `<button class="btn sm" data-action="apply-suggestion" data-task="${s.task}" data-to="${s.to_id}">Appliquer</button>` : ""}</div>`).join("")
    : '<p class="muted small">Aucune surcharge à corriger : personne ne dépasse 100 % de sa semaine.</p>';
  const rows = sim
    ? sim.tasks.map((r) => `<div class="sim-row">
        <div class="grow"><b>${esc(r.title)}</b> <span class="muted small">${r.who ? esc(r.who) : "non assignée"}</span></div>
        <div class="sim-bar" title="${r.end_delay_days} ${esc(sim.unit)} de retard sur la fin"><i style="width:${Math.min(100, (r.end_delay_days / Math.max(1, sim.delay)) * 100)}%" class="${r.end_delay_days ? "hot" : ""}"></i></div>
        <div class="sim-val ${r.end_delay_days ? "bad" : "ok"}">${r.end_delay_days ? `+${r.end_delay_days} ${esc(sim.unit === "jours" ? "j" : "j ouvrés")}` : "absorbé"}</div>
        <div class="muted small sim-pushed">${r.pushed ? `${r.pushed} tâche${r.pushed > 1 ? "s" : ""} décalée${r.pushed > 1 ? "s" : ""}` : ""}</div></div>`).join("")
    : "";
  return `<div class="dash wl">
    <section class="card"><header><h3>Charge de l'équipe</h3>
      <label class="inline">Semaines <select data-wl="weeks">${opts(WEEK_OPTIONS, weeks, (v) => v)}</select></label></header>
      <p class="muted small">Un jour de charge = une tâche ouverte sur un jour de semaine. 100 % = une semaine pleine ; 200 % = deux tâches en parallèle.</p>
      ${grid}
      <div class="wl-legend"><span class="lv-free">&lt; 60 %</span><span class="lv-ok">≤ 100 %</span><span class="lv-high">≤ 150 %</span><span class="lv-over">&gt; 150 %</span></div>
      <h3 class="sub">Rééquilibrage proposé</h3>${sugg}</section>
    <section class="card"><header><h3>Et si une tâche prenait du retard ?</h3>
      <label class="inline">Retard de <select data-wl="delay">${opts(DELAY_OPTIONS, delay, (v) => `${v} jour${v > 1 ? "s" : ""}`)}</select></label></header>
      ${sim ? `<p class="muted small">Pour chaque tâche ouverte : de combien reculerait la fin du projet (aujourd'hui prévue ${sim.forecast_end ? esc(D.fmt(D.parse(sim.forecast_end), { day: "numeric", month: "long" })) : "—"}) ?
        Les plus risquées en premier ; <b>${sim.safe}</b> tâche${sim.safe > 1 ? "s absorbent" : " absorbe"} ce retard sans rien décaler.</p>
        <div class="sim">${rows || '<p class="muted small">Aucune tâche ouverte et planifiée.</p>'}</div>` : '<p class="muted small">Chargement…</p>'}</section></div>`;
}
