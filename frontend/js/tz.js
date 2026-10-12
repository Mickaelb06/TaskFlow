/* Fuseaux horaires avec Intl uniquement (aucune bibliothèque). Un « instant » est un Date ; l'heure murale
   d'un fuseau IANA (« Europe/Paris ») s'obtient avec Intl.DateTimeFormat. */

const formatters = new Map();
function formatter(tz) {
  if (!formatters.has(tz)) {
    formatters.set(tz, new Intl.DateTimeFormat("en-CA", {
      timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }));
  }
  return formatters.get(tz);
}

export const pad = (n) => String(n).padStart(2, "0");

/** Heure murale de `instant` dans `tz` : { y, m, d, h, mi, s }. */
export function parts(instant, tz) {
  const o = {};
  for (const p of formatter(tz).formatToParts(instant)) if (p.type !== "literal") o[p.type] = Number(p.value);
  return { y: o.year, m: o.month, d: o.day, h: o.hour % 24, mi: o.minute, s: o.second };
}

/** Jour calendaire « AAAA-MM-JJ » de `instant` dans `tz`. */
export function dayKey(instant, tz) {
  const p = parts(instant, tz);
  return `${p.y}-${pad(p.m)}-${pad(p.d)}`;
}

/** Minutes écoulées depuis minuit (heure murale de `tz`). */
export function minutesOfDay(instant, tz) {
  const p = parts(instant, tz);
  return p.h * 60 + p.mi;
}

/** Décalage de `tz` par rapport à UTC à cet instant, en minutes (Paris l'été : 120). */
export function offsetMinutes(tz, instant) {
  const p = parts(instant, tz);
  const wall = Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi, p.s);
  return Math.round((wall - Math.floor(instant.getTime() / 1000) * 1000) / 60000);
}

/** « UTC+2 », « UTC+5:30 », « UTC−3 », « UTC ». */
export function offsetLabel(tz, instant = new Date()) {
  const off = offsetMinutes(tz, instant);
  if (off === 0) return "UTC";
  const a = Math.abs(off);
  const h = Math.floor(a / 60);
  const m = a % 60;
  return `UTC${off < 0 ? "−" : "+"}${h}${m ? ":" + pad(m) : ""}`;
}

/** « America/Argentina/Buenos_Aires » → « Buenos Aires ». */
const CITY_NAMES = { "Asia/Jerusalem": "Jerusalem", "Asia/Tel_Aviv": "Tel Aviv", "America/New_York": "New York City" };
export function city(tz) {
  return CITY_NAMES[tz] || tz.split("/").pop().replace(/_/g, " ");
}

/** Fuseaux ajoutés à la liste du navigateur (Tel Aviv est un alias IANA de Jérusalem : même heure, nom familier). */
const ADDED = ["Europe/Paris", "Asia/Jerusalem", "Asia/Tel_Aviv", "America/New_York"];
const HIDDEN = new Set(["Asia/Gaza"]);

const FALLBACK = ["Europe/Paris", "Asia/Jerusalem", "Asia/Tel_Aviv", "Europe/London", "Europe/Berlin", "Europe/Madrid", "Europe/Moscow", "Africa/Casablanca",
  "Africa/Johannesburg", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
  "America/Sao_Paulo", "America/Montreal", "Asia/Dubai", "Asia/Kolkata", "Asia/Bangkok", "Asia/Shanghai",
  "Asia/Tokyo", "Australia/Sydney", "Pacific/Auckland", "UTC"];

/** Tous les fuseaux IANA connus du navigateur (liste réduite si Intl.supportedValuesOf manque). */
export function allZones() {
  try {
    const z = Intl.supportedValuesOf("timeZone");
    return [...new Set([...z, "UTC", ...ADDED])].filter((x) => !HIDDEN.has(x)).sort();
  } catch { return FALLBACK.filter((x) => !HIDDEN.has(x)); }
}

export function isValid(tz) {
  try { formatter(tz); return true; } catch { return false; }
}

/** Fuseau du navigateur, utilisé tant que le profil n'en définit pas un. */
export const browserZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Paris";

/** Heure « HH:MM » de `instant` dans `tz` (24 h). */
export function hhmm(instant, tz) {
  const p = parts(instant, tz);
  return `${pad(p.h)}:${pad(p.mi)}`;
}

/** Libellé d'une minute du jour : 450 → « 7:30 », 480 → « 8 h » ; `compact` pour les gouttières d'heures. */
export function hourLabel(minutes) {
  const m = ((minutes % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h}:${pad(r)}` : `${h} h`;
}
