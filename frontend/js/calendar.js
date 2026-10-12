/* Calendrier façon Notion Calendar : grille horaire (jour / semaine) ou mois, événements à l'heure,
   tâches posées à la journée, une ou deux colonnes d'heures (deux fuseaux). Rendu en HTML pur ; la
   navigation et les modales sont dans app.js. */
import * as D from "./dates.js";
import * as TZ from "./tz.js";
import { hue } from "./palette.js";
import { icon } from "./icons.js";

export const HOUR_PX = 48;
const MIN_EVENT_PX = 18;

/** Place des intervalles qui se chevauchent côte à côte : retourne, pour chacun, `col` et `cols`
 *  (nombre de colonnes de son groupe de chevauchement). items = [{ start, end }] en minutes. */
export function layoutColumns(items) {
  const order = items.map((it, i) => ({ ...it, i })).sort((a, b) => a.start - b.start || b.end - a.end);
  const out = new Array(items.length);
  let group = [];
  let groupEnd = -1;
  const flush = () => {
    const cols = Math.max(0, ...group.map((g) => out[g.i].col + 1));
    group.forEach((g) => (out[g.i].cols = cols));
    group = [];
  };
  const colEnds = [];
  for (const it of order) {
    if (group.length && it.start >= groupEnd) { flush(); colEnds.length = 0; }
    let col = colEnds.findIndex((end) => end <= it.start);
    if (col < 0) col = colEnds.length;
    colEnds[col] = it.end;
    out[it.i] = { col, cols: 1 };
    group.push(it);
    groupEnd = Math.max(groupEnd, it.end);
  }
  if (group.length) flush();
  return out;
}

/** Portion d'un événement visible le jour `key` : { start, end } en minutes, ou null. */
export function segmentOn(ev, key, tz) {
  const s = new Date(ev.starts_at);
  const e = new Date(ev.ends_at);
  const sk = TZ.dayKey(s, tz);
  const ek = TZ.dayKey(e, tz);
  if (key < sk || key > ek) return null;
  const start = key === sk ? TZ.minutesOfDay(s, tz) : 0;
  const end = key === ek ? TZ.minutesOfDay(e, tz) : 1440;
  if (end <= start) return key === ek && key !== sk ? null : { start, end: Math.min(1440, start + 15), endsHere: key === ek };
  return { start, end, endsHere: key === ek };
}

const col = (name) => `--c: hsl(${hue(name)} 62% 44%)`;

function eventStyle(ev) {
  return ev.project_name ? col(ev.project_name) : "--c: var(--accent)";
}

function taskChip(t, esc) {
  return `<button class="ctask p${t.priority} ${t.status}" data-action="goto-task" data-project="${t.project}" data-task="${t.id}"
    title="${esc(t.project_name)} · ${esc(t.title)}">${t.is_milestone ? "◆ " : t.status === "done" ? "✓ " : ""}<span>${esc(t.title)}</span></button>`;
}

/** Tâches affichées le jour `key` : celles dont l'échéance tombe ce jour-là, plus (en mois/jour) celles
 *  qui le traversent. On ne répète pas une longue tâche sur chaque jour de la semaine. */
function tasksOn(tasks, key) {
  return tasks.filter((t) => (t.due_date || t.start_date) === key);
}

/** Classes d'état d'un événement : invitation en attente (bord pointillé), refusée (barrée), série, lecture seule. */
function stateClasses(ev) {
  return [ev.can_edit ? "" : "ro", ev.my_status === "invited" ? "pending" : "", ev.my_status === "declined" ? "declined" : "", ev.recurrence ? "series" : ""].join(" ");
}

function badges(ev) {
  return `${ev.recurrence ? icon("repeat", 11) : ""}${ev.invitees?.length ? icon("users", 11) : ""}`;
}

function eventBlock(ev, seg, lay, tz, esc) {
  const top = (seg.start / 60) * HOUR_PX;
  const height = Math.max(MIN_EVENT_PX, ((seg.end - seg.start) / 60) * HOUR_PX - 2);
  const w = 100 / lay.cols;
  const short = height < 34;
  const range = `${TZ.hhmm(new Date(ev.starts_at), tz)} – ${TZ.hhmm(new Date(ev.ends_at), tz)}`;
  return `<div class="cevent ${stateClasses(ev)}" role="button" tabindex="0" data-action="edit-event" data-id="${ev.id}" data-occ="${ev.occurrence_day || ""}"
    data-seg-start="${seg.start}" data-seg-end="${seg.end}"
    style="${eventStyle(ev)};top:${top}px;height:${height}px;left:calc(${lay.col * w}% + 1px);width:calc(${w}% - 3px)"
    title="${esc(ev.title)} — ${range}${ev.project_name ? " · " + esc(ev.project_name) : ""}">
    <b>${esc(ev.title)}<span class="ebadges">${badges(ev)}</span></b>${short ? "" : `<span>${range}</span>`}
    ${ev.can_edit && seg.endsHere ? '<i class="cevent-resize" data-resize aria-hidden="true"></i>' : ""}</div>`;
}

/** Gouttière d'heures : étiquettes de `tz` face aux lignes du fuseau principal (`shiftMin` = écart). */
function gutter(shiftMin, cls) {
  let html = "";
  for (let h = 1; h < 24; h++) {
    html += `<span style="top:${h * HOUR_PX}px">${TZ.hourLabel(h * 60 + shiftMin)}</span>`;
  }
  return `<div class="chours ${cls}" aria-hidden="true">${html}</div>`;
}

function tzHead(tz, now, cls) {
  return `<div class="ctz ${cls}" title="${tz}"><b>${TZ.city(tz)}</b><span>${TZ.offsetLabel(tz, now)}</span></div>`;
}

function timeGrid({ days, data, tz, tz2, now, esc }) {
  const todayKey = TZ.dayKey(now, tz);
  const keys = days.map(D.iso);
  const shift2 = tz2 ? TZ.offsetMinutes(tz2, now) - TZ.offsetMinutes(tz, now) : 0;
  const gutters = tz2 ? 2 : 1;
  const head = days.map((d, i) => `<div class="cday ${keys[i] === todayKey ? "today" : ""}">
      <span>${D.fmt(d, { weekday: "short" })}</span><b>${d.getDate()}</b></div>`).join("");
  const allday = keys.map((k) => `<div class="call-cell">${tasksOn(data.tasks, k).map((t) => taskChip(t, esc)).join("")}</div>`).join("");
  const cols = keys.map((k) => {
    const segs = data.events.map((ev) => ({ ev, seg: segmentOn(ev, k, tz) })).filter((x) => x.seg);
    const lay = layoutColumns(segs.map((x) => x.seg));
    const nowLine = k === todayKey
      ? `<div class="cnow" style="top:${(TZ.minutesOfDay(now, tz) / 60) * HOUR_PX}px"><i></i></div>` : "";
    return `<div class="ccol ${k === todayKey ? "today" : ""}" data-action="cal-slot" data-date="${k}">
      ${segs.map((x, i) => eventBlock(x.ev, x.seg, lay[i], tz, esc)).join("")}${nowLine}</div>`;
  }).join("");
  return `<div class="cal" style="--days:${days.length};--gutters:${gutters};--hour:${HOUR_PX}px">
    <div class="chead"><div class="ctzs">${tz2 ? tzHead(tz2, now, "alt") : ""}${tzHead(tz, now, "main")}</div>${head}</div>
    <div class="callday"><div class="callday-label">journée</div>${allday}</div>
    <div class="cscroll" id="cal-scroll"><div class="cgrid">
      <div class="cgut">${tz2 ? gutter(shift2, "alt") : ""}${gutter(0, "main")}</div>
      <div class="ccols">${cols}</div></div></div></div>`;
}

function monthGrid({ cursor, data, tz, now, esc }) {
  const todayKey = TZ.dayKey(now, tz);
  const grid = D.monthGrid(cursor);
  const m = cursor.getMonth();
  const cells = grid.map((d) => {
    const k = D.iso(d);
    const evs = data.events.map((ev) => ({ ev, seg: segmentOn(ev, k, tz) })).filter((x) => x.seg);
    const tasks = tasksOn(data.tasks, k);
    const shownE = evs.slice(0, 3);
    const shownT = tasks.slice(0, Math.max(0, 3 - shownE.length));
    const more = evs.length + tasks.length - shownE.length - shownT.length;
    return `<div class="mcell ${d.getMonth() !== m ? "out" : ""}" data-action="cal-slot" data-date="${k}" data-month="1">
      <button class="mnum ${k === todayKey ? "today" : ""}" data-action="cal-day" data-date="${k}">${d.getDate() === 1 ? D.fmt(d, { day: "numeric", month: "short" }) : d.getDate()}</button>
      ${shownE.map(({ ev }) => `<button class="mevent ${stateClasses(ev)}" style="${eventStyle(ev)}" data-action="edit-event" data-id="${ev.id}" data-occ="${ev.occurrence_day || ""}">
        <i></i><em>${TZ.hhmm(new Date(ev.starts_at), tz)}</em><span>${esc(ev.title)}</span><span class="ebadges">${badges(ev)}</span></button>`).join("")}
      ${shownT.map((t) => taskChip(t, esc)).join("")}
      ${more > 0 ? `<button class="more" data-action="cal-day" data-date="${k}">+${more} autres</button>` : ""}</div>`;
  }).join("");
  return `<div class="cal month"><div class="mhead">${D.weekDays(new Date()).map((d) => `<div>${D.fmt(d, { weekday: "short" })}</div>`).join("")}</div>
    <div class="mbody">${cells}</div></div>`;
}

/** Période affichée : { first, last } (dates locales représentant des jours calendaires). */
export function range(mode, cursor) {
  if (mode === "day") return { first: cursor, last: cursor };
  if (mode === "week") { const d = D.weekDays(cursor); return { first: d[0], last: d[6] }; }
  const g = D.monthGrid(cursor);
  return { first: g[0], last: g[41] };
}

export function title(mode, cursor) {
  if (mode === "day") return D.fmt(cursor, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  if (mode === "week") return D.weekLabel(cursor);
  return D.fmt(cursor, { month: "long", year: "numeric" });
}

export function calendarHtml({ mode, cursor, data, tz, tz2, now = new Date(), esc }) {
  if (!data) return `<div class="empty small-empty"><p class="muted">Chargement du calendrier…</p></div>`;
  if (mode === "month") return monthGrid({ cursor, data, tz, now, esc });
  const days = mode === "day" ? [cursor] : D.weekDays(cursor);
  return timeGrid({ days, data, tz, tz2: tz2 && tz2 !== tz ? tz2 : "", now, esc });
}

/** Minute (arrondie à 30) correspondant à un clic à `y` pixels du haut d'une colonne. */
export const minuteAt = (y) => Math.max(0, Math.min(1410, Math.floor(((y / HOUR_PX) * 60) / 30) * 30));
