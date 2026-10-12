// Vue « Équipe » : sur quoi chacun travaille et qui est en retard (données calculées par l'API : insights.team).
import * as D from "./dates.js";

const STATE = {
  late: ["En retard", "st-late"],
  overloaded: ["Surchargé", "st-over"],
  ok: ["Dans les temps", "st-ok"],
  free: ["Disponible", "st-free"],
};
const ROLE = { owner: "Propriétaire", member: "Membre", viewer: "Lecteur" };
const day = (iso) => D.fmt(D.parse(iso), { day: "numeric", month: "short" });

export function teamHtml({ insights, esc, avatar }) {
  if (!insights) return '<div class="empty"><p class="muted">Indicateurs indisponibles.</p></div>';
  const team = insights.team;
  const count = (s) => team.filter((m) => m.state === s).length;
  const btn = (t, meta, cls = "") => `<button class="tl ${cls}" data-action="open-task" data-task="${t.id}">
      <span class="ellipsis grow">${esc(t.title)}</span><span class="tl-meta">${meta}</span></button>`;
  const section = (title, items) => items ? `<div class="tm-sec"><h4>${title}</h4>${items}</div>` : "";

  const cards = team.map((m) => {
    const [label, cls] = STATE[m.state];
    const pct = m.total ? Math.round((100 * m.done) / m.total) : 0;
    const late = m.late.map((t) => btn(t, `${t.days_late} j de retard`, "late")).join("");
    const current = m.current.map((t) => btn(t, t.due ? `jusqu'au ${day(t.due)}` : "en cours")).join("");
    const next = m.upcoming.map((t) => btn(t, `dès le ${day(t.start)}`)).join("");
    const nothing = !late && !current && !next;
    return `<article class="member-card ${cls}">
      <header>${avatar(m.username)}
        <div class="grow"><b>${esc(m.username)}</b><div class="muted small">${ROLE[m.role]}</div></div>
        <span class="badge ${cls}">${label}</span></header>
      <div class="tm-progress"><div class="meter"><i style="width:${pct}%"></i></div>
        <small class="muted">${m.done}/${m.total} tâches terminées${m.peak >= 2 ? ` · jusqu'à ${m.peak} en parallèle` : ""}</small></div>
      ${section(`En retard (${m.late.length})`, late)}
      ${section("En ce moment", current)}
      ${section("À venir", next)}
      ${m.unscheduled ? `<p class="muted small">${m.unscheduled} tâche(s) sans date</p>` : ""}
      ${nothing && !m.unscheduled ? '<p class="muted small">Rien d\'assigné pour le moment.</p>' : ""}
    </article>`;
  }).join("");

  const un = insights.unassigned;
  const unassigned = un.open ? `<article class="member-card ${un.late ? "st-late" : "st-free"}">
      <header><span class="avatar" style="--h:0">?</span><div class="grow"><b>Non assignées</b><div class="muted small">Personne n'en est responsable</div></div>
        ${un.late ? `<span class="badge st-late">${un.late} en retard</span>` : ""}</header>
      <p class="muted small">${un.open} tâche(s) ouverte(s) sans responsable. Assignez-les depuis le panneau de détail.</p></article>` : "";

  const summary = [
    count("late") ? `<b class="bad">${count("late")} en retard</b>` : '<b class="ok">Personne en retard</b>',
    count("overloaded") ? `${count("overloaded")} surchargé(s)` : "",
    count("free") ? `${count("free")} disponible(s)` : "",
  ].filter(Boolean).join(" · ");

  return `<div class="team-view">
    <div class="team-head"><h2>Équipe</h2><span class="muted">${summary}</span></div>
    <div class="team-grid">${cards}${unassigned}</div>
  </div>`;
}
