// Graphiques SVG sans dépendance. Les couleurs viennent des classes CSS (palette du thème).
import * as D from "./dates.js";

const shortDay = (iso) => D.fmt(D.parse(iso), { day: "numeric", month: "short" });

/** Anneau de répartition. segments = [{value, cls}] ; centre = deux lignes de texte. */
export function donut(segments, { size = 150, thickness = 20, top = "", bottom = "" } = {}) {
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const total = segments.reduce((a, s) => a + s.value, 0);
  let offset = 0;
  const arcs = total
    ? segments.filter((s) => s.value > 0).map((s) => {
        const len = (s.value / total) * c;
        const el = `<circle class="seg ${s.cls}" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${thickness}"
          stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${size / 2} ${size / 2})"/>`;
        offset += len;
        return el;
      }).join("")
    : "";
  return `<svg class="chart donut" viewBox="0 0 ${size} ${size}" role="img" aria-label="Répartition des tâches">
    <circle class="seg-bg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${thickness}"/>${arcs}
    <text x="50%" y="48%" text-anchor="middle" class="d-top">${top}</text>
    <text x="50%" y="62%" text-anchor="middle" class="ax">${bottom}</text></svg>`;
}

/** Petit anneau de progression (0-100). */
export function ring(pct, { size = 46, thickness = 5 } = {}) {
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const len = (Math.min(Math.max(pct, 0), 100) / 100) * c;
  return `<svg class="chart ring" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${pct} %">
    <circle class="seg-bg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${thickness}"/>
    <circle class="seg seg-ring" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${thickness}" stroke-linecap="round"
      stroke-dasharray="${len} ${c - len}" transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="55%" text-anchor="middle" class="r-txt">${pct}%</text></svg>`;
}

/** Courbes cumulées : points = [{date, created, done}] — « créées » en ligne, « terminées » en aire. */
export function lineChart(points, { w = 640, h = 210 } = {}) {
  const pad = { l: 30, r: 12, t: 12, b: 26 };
  const step = Math.ceil(Math.max(...points.map((p) => p.created), 1) / 4);
  const max = step * 4;
  const x = (i) => pad.l + (i * (w - pad.l - pad.r)) / Math.max(points.length - 1, 1);
  const y = (v) => h - pad.b - (v * (h - pad.t - pad.b)) / max;
  const line = (key) => points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const grid = [0, 1, 2, 3, 4].map((k) => `<line class="grid" x1="${pad.l}" x2="${w - pad.r}" y1="${y(k * step)}" y2="${y(k * step)}"/>
    <text class="ax" x="${pad.l - 6}" y="${y(k * step) + 3}" text-anchor="end">${k * step}</text>`).join("");
  const last = points.length - 1;
  const ticks = [0, Math.floor(last / 2), last].map((i) =>
    `<text class="ax" x="${x(i)}" y="${h - 8}" text-anchor="${i === 0 ? "start" : i === last ? "end" : "middle"}">${shortDay(points[i].date)}</text>`).join("");
  const area = `${line("done")} L${x(last)},${y(0)} L${x(0)},${y(0)} Z`;
  return `<svg class="chart line" viewBox="0 0 ${w} ${h}" role="img" aria-label="Tâches créées et terminées sur 30 jours">
    ${grid}<path class="a-done" d="${area}"/><path class="l-created" d="${line("created")}"/><path class="l-done" d="${line("done")}"/>
    <circle class="dot-created" cx="${x(last)}" cy="${y(points[last].created)}" r="3.5"/><circle class="dot-done" cx="${x(last)}" cy="${y(points[last].done)}" r="3.5"/>${ticks}</svg>`;
}

/** Histogramme : values = [{date, count}]. Le dernier jour (aujourd'hui) est mis en avant. */
export function barChart(values, { w = 420, h = 150 } = {}) {
  const pad = { l: 6, r: 6, t: 18, b: 22 };
  const max = Math.max(...values.map((v) => v.count), 1);
  const slot = (w - pad.l - pad.r) / values.length;
  const bars = values.map((v, i) => {
    const bh = (v.count / max) * (h - pad.t - pad.b);
    const bx = pad.l + i * slot + slot * 0.18;
    const label = i % 2 === (values.length - 1) % 2 ? D.parse(v.date).getDate() : "";
    return `<rect class="bar ${i === values.length - 1 ? "today" : ""}" x="${bx}" y="${h - pad.b - bh}" width="${slot * 0.64}" height="${Math.max(bh, v.count ? 2 : 0)}" rx="3"/>
      ${v.count ? `<text class="ax" x="${bx + slot * 0.32}" y="${h - pad.b - bh - 4}" text-anchor="middle">${v.count}</text>` : ""}
      <text class="ax" x="${bx + slot * 0.32}" y="${h - 6}" text-anchor="middle">${label}</text>`;
  }).join("");
  return `<svg class="chart bars" viewBox="0 0 ${w} ${h}" role="img" aria-label="Tâches terminées par jour">
    <line class="grid" x1="${pad.l}" x2="${w - pad.r}" y1="${h - pad.b}" y2="${h - pad.b}"/>${bars}</svg>`;
}
