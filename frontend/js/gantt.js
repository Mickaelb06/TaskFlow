// Rendu du diagramme de Gantt : fonctions pures qui renvoient du HTML (la logique d'interaction est dans app.js).
import * as D from "./dates.js";

export const ROW_H = 36;
const DAY_MS = 86400000;
const daysBetween = (a, b) => Math.round((D.parse(b) - D.parse(a)) / DAY_MS);

/** [début, fin] ISO d'une tâche, ou null si elle n'est pas planifiée. */
export const spanOf = (t) => {
  const s = t.start_date || t.due_date;
  return s ? [s, t.due_date || s] : null;
};

export function layout(tasks, project, zoom) {
  const dayW = zoom === "month" ? 16 : 38;
  const today = D.iso(new Date());
  const dates = [today];
  tasks.forEach((t) => { const s = spanOf(t); if (s) dates.push(s[0], s[1]); });
  if (project?.deadline) dates.push(project.deadline);
  dates.sort();
  const start = D.startOfWeek(D.addDays(D.parse(dates[0]), -7));
  const end = D.addDays(D.parse(dates[dates.length - 1]), 28);
  const count = Math.max(daysBetween(D.iso(start), D.iso(end)) + 1, zoom === "month" ? 120 : 56);
  return { start: D.iso(start), count, dayW };
}

export const orderRows = (tasks) => {
  const planned = tasks.filter(spanOf).sort((a, b) => spanOf(a)[0].localeCompare(spanOf(b)[0]) || a.id - b.id);
  return [...planned, ...tasks.filter((t) => !spanOf(t)).sort((a, b) => a.id - b.id)];
};

function header(lay, esc) {
  const months = [];
  let cur = null;
  const cells = [];
  for (let i = 0; i < lay.count; i++) {
    const d = D.addDays(D.parse(lay.start), i);
    const key = d.getFullYear() * 12 + d.getMonth();
    if (!cur || cur.key !== key) { cur = { key, label: D.fmt(d, { month: "long", year: "numeric" }), n: 0 }; months.push(cur); }
    cur.n++;
    const wk = d.getDay() === 0 || d.getDay() === 6;
    const label = lay.dayW >= 30
      ? `<small>${esc(D.fmt(d, { weekday: "narrow" }))}</small>${d.getDate()}`
      : d.getDay() === 1 ? d.getDate() : "";
    cells.push(`<div class="g-day ${wk ? "wk" : ""} ${D.iso(d) === D.iso(new Date()) ? "today" : ""}" style="width:${lay.dayW}px">${label}</div>`);
  }
  const monthsHtml = months.map((m) =>
    `<div class="g-month" style="width:${m.n * lay.dayW}px">${m.n * lay.dayW > 90 ? esc(m.label) : ""}</div>`).join("");
  return `<div class="g-months">${monthsHtml}</div><div class="g-days">${cells.join("")}</div>`;
}

export function ganttHtml({ tasks, insights, project, zoom, showCritical, canWrite, esc, avatar }) {
  const lay = layout(tasks, project, zoom);
  const rows = orderRows(tasks);
  const W = lay.count * lay.dayW;
  const H = rows.length * ROW_H;
  const crit = new Set(showCritical && insights ? insights.critical_path.task_ids : []);
  const x = (iso) => daysBetween(lay.start, iso) * lay.dayW;
  const todayIso = D.iso(new Date());
  const rowOf = new Map(rows.map((t, i) => [t.id, i]));

  const weekends = [];
  for (let i = 0; i < lay.count; i++) {
    const wd = D.addDays(D.parse(lay.start), i).getDay();
    if (wd === 0 || wd === 6) weekends.push(`<div class="g-wk" style="left:${i * lay.dayW}px;width:${lay.dayW}px"></div>`);
  }

  const bars = rows.map((t, i) => {
    const sp = spanOf(t);
    if (!sp) return "";
    const top = i * ROW_H;
    const cls = `p${t.priority} ${t.status} ${crit.has(t.id) ? "crit" : ""} ${t.status !== "done" && sp[1] < todayIso ? "late" : ""}`;
    const drag = canWrite ? "" : "ro";
    if (t.is_milestone) {
      const cx = x(sp[1]) + lay.dayW / 2;
      return `<div class="gmile ${cls} ${drag}" data-task="${t.id}" data-action="open-task" style="left:${cx - 9}px;top:${top + 9}px" title="${esc(t.title)}"></div>
        <span class="gb-out" style="left:${cx + 14}px;top:${top + 9}px">${esc(t.title)}</span>`;
    }
    const left = x(sp[0]) + 2;
    const width = Math.max((daysBetween(sp[0], sp[1]) + 1) * lay.dayW - 4, 10);
    const pct = t.status === "done" ? 100 : t.status === "doing" ? 50 : 0;
    const inside = width >= 110;
    return `<div class="gbar ${cls} ${drag}" data-task="${t.id}" data-action="open-task" style="left:${left}px;top:${top + 6}px;width:${width}px" title="${esc(t.title)}">
        <i class="fill" style="width:${pct}%"></i>
        ${canWrite ? '<b class="h l" data-gdrag="start"></b><b class="h r" data-gdrag="end"></b>' : ""}
        ${inside ? `<span class="gb-title">${esc(t.title)}</span>` : ""}</div>
      ${inside ? "" : `<span class="gb-out" style="left:${left + width + 6}px;top:${top + 9}px">${esc(t.title)}</span>`}`;
  }).join("");

  // flèches de dépendance : du bord droit du prédécesseur au bord gauche du successeur
  const geo = (t) => {
    const sp = spanOf(t);
    const i = rowOf.get(t.id);
    if (!sp) return null;
    const cy = i * ROW_H + ROW_H / 2;
    if (t.is_milestone) { const cx = x(sp[1]) + lay.dayW / 2; return { l: cx - 9, r: cx + 9, cy }; }
    return { l: x(sp[0]) + 2, r: x(sp[1]) + lay.dayW - 2, cy };
  };
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const arrows = rows.flatMap((t) => (t.dependencies || []).map((pid) => {
    const p = byId.get(pid);
    const a = p && geo(p);
    const b = geo(t);
    if (!a || !b) return "";
    const hot = crit.has(p.id) && crit.has(t.id);
    const path = b.l >= a.r + 14
      ? `M${a.r},${a.cy} H${a.r + Math.min(10, (b.l - a.r) / 2)} V${b.cy} H${b.l - 1}`
      : `M${a.r},${a.cy} H${a.r + 8} V${(a.cy + b.cy) / 2} H${b.l - 8} V${b.cy} H${b.l - 1}`;
    return `<path d="${path}" class="g-arrow ${hot ? "hot" : ""}" marker-end="url(#${hot ? "arr-hot" : "arr"})"/>`;
  })).join("");

  const todayLine = `<div class="g-today" style="left:${x(todayIso) + lay.dayW / 2}px"></div>`;
  const deadline = project?.deadline
    ? `<div class="g-deadline" style="left:${x(project.deadline) + lay.dayW}px"><span>Échéance</span></div>` : "";

  const names = rows.map((t) => {
    const unplanned = !spanOf(t);
    return `<div class="g-name ${unplanned ? "unplanned" : ""} ${t.status === "done" ? "done" : ""}" style="height:${ROW_H}px"
      data-task="${t.id}" data-action="open-task">
      ${crit.has(t.id) ? '<span class="crit-dot" title="Chemin critique"></span>' : '<span class="crit-dot off"></span>'}
      <span class="ellipsis grow">${t.status === "done" ? "✓ " : ""}${esc(t.title)}</span>
      ${t.assignee_name ? avatar(t.assignee_name, "xs") : ""}</div>`;
  }).join("");

  return `${insightsHtml({ insights, esc, canWrite, zoom, showCritical })}
    <div class="gantt" id="gantt-scroll" data-start="${lay.start}" data-daywidth="${lay.dayW}">
      <div class="g-head"><div class="g-corner">Tâche</div><div class="g-scale" style="width:${W}px">${header(lay, esc)}</div></div>
      <div class="g-body">
        <div class="g-names">${names || '<p class="muted pad">Aucune tâche. Créez-en une.</p>'}</div>
        <div class="g-canvas" id="gantt-canvas" data-action="gantt-canvas" style="width:${W}px;height:${Math.max(H, 120)}px;--row:${ROW_H}px">
          ${weekends.join("")}${todayLine}${deadline}
          <svg class="g-svg" width="${W}" height="${Math.max(H, 120)}" aria-hidden="true">
            <defs>
              <marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="arr-head"/></marker>
              <marker id="arr-hot" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="arr-head hot"/></marker>
            </defs>${arrows}
          </svg>
          ${bars}
        </div>
      </div>
    </div>`;
}

const fmtDay = (iso) => D.fmt(D.parse(iso), { day: "numeric", month: "short" });

export function insightsHtml({ insights, esc, canWrite, zoom, showCritical }) {
  if (!insights) return "";
  const i = insights;
  const slip = i.slip_days;
  const forecastSub = i.forecast_end == null ? "Tout est terminé"
    : slip == null ? "pas d'échéance définie"
    : slip > 0 ? `<span class="bad">+${slip} j de retard sur ${i.deadline ? "l'échéance" : "le plan"}</span>`
    : `<span class="ok">${-slip === 0 ? "pile à l'échéance" : `${-slip} j de marge`}</span>`;
  const risks = i.risks.slice(0, 6).map((r) => {
    const inner = `<span class="sev sev-${r.severity}"></span><span>${esc(r.message)}</span>`;
    return r.task ? `<button class="risk" data-action="open-task" data-task="${r.task}">${inner}</button>` : `<div class="risk">${inner}</div>`;
  }).join("");
  const work = i.workload.filter((w) => w.open || w.peak).map((w) =>
    `<span class="wl ${w.peak >= 4 ? "over" : ""}" title="${w.open} tâche(s) ouverte(s), jusqu'à ${w.peak} en parallèle">${esc(w.username)} <b>${w.open}</b></span>`).join("");
  return `<div class="kpis">
      <div class="kpi"><span class="k-label">Avancement</span><b>${i.progress} %</b>
        <div class="meter"><i style="width:${i.progress}%"></i></div><small>${i.done}/${i.total} tâches terminées</small></div>
      <div class="kpi"><span class="k-label">Fin prévue</span><b>${i.forecast_end ? fmtDay(i.forecast_end) : "—"}</b><small>${forecastSub}</small></div>
      <div class="kpi"><span class="k-label">En retard</span><b class="${i.late_count ? "bad" : ""}">${i.late_count}</b><small>${i.late_count ? "tâche(s) à rattraper" : "rien en retard"}</small></div>
      <div class="kpi"><span class="k-label">Chemin critique</span><b>${i.critical_path.task_ids.length} tâche${i.critical_path.task_ids.length > 1 ? "s" : ""}</b><small>${i.critical_path.duration_days} jours incompressibles</small></div>
    </div>
    <div class="g-tools">
      <div class="risks">${risks || '<span class="risk"><span class="sev sev-ok"></span><span>Aucun risque détecté.</span></span>'}</div>
      <div class="g-actions">
        ${work ? `<div class="workload" title="Tâches ouvertes par membre">${work}</div>` : ""}
        <label class="inline check-label"><input type="checkbox" data-gantt="critical" ${showCritical ? "checked" : ""}> Chemin critique</label>
        <div class="seg"><button class="${zoom === "week" ? "on" : ""}" data-action="gantt-zoom" data-zoom="week">Jours</button><button class="${zoom === "month" ? "on" : ""}" data-action="gantt-zoom" data-zoom="month">Mois</button></div>
        <button class="btn" data-action="gantt-today">Aujourd'hui</button>
        ${canWrite ? `<button class="btn" data-action="replan" ${i.late_count ? "" : "disabled"} title="Redémarre les tâches en retard aujourd'hui et décale celles qui en dépendent">Rattraper le retard</button>` : ""}
      </div>
    </div>`;
}
