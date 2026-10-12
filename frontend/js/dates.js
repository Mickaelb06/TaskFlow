export const pad = (n) => String(n).padStart(2, "0");
export const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const parse = (s) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
export const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
export const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1);
export const startOfWeek = (d) => addDays(d, -((d.getDay() + 6) % 7)); // lundi
export const today = () => new Date();
export const fmt = (d, opts) => new Intl.DateTimeFormat("fr-FR", opts).format(d);

export const weekDays = (cursor) => {
  const start = startOfWeek(cursor);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
};

export const monthGrid = (cursor) => {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const start = startOfWeek(first);
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
};

export function weekLabel(cursor) {
  const days = weekDays(cursor);
  const a = days[0];
  const b = days[6];
  if (a.getMonth() === b.getMonth()) {
    return `${a.getDate()} – ${b.getDate()} ${fmt(b, { month: "long", year: "numeric" })}`;
  }
  return `${fmt(a, { day: "numeric", month: "short" })} – ${fmt(b, { day: "numeric", month: "short", year: "numeric" })}`;
}
