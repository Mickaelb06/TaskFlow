// Fuseaux horaires et mise en page du calendrier : fonctions pures, sans DOM.
import * as TZ from "../js/tz.js";
import * as CAL from "../js/calendar.js";

let failed = 0;
const ok = (name, cond) => { if (!cond) failed++; print((cond ? "OK   " : "ECHEC") + " " + name); };
const utc = (...a) => new Date(Date.UTC(...a));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

print("# Fuseaux horaires (tz.js)");
ok("décalage de Paris : +2 l'été, +1 l'hiver", TZ.offsetLabel("Europe/Paris", utc(2026, 6, 1)) === "UTC+2" && TZ.offsetLabel("Europe/Paris", utc(2026, 0, 15)) === "UTC+1");
ok("changement d'heure : 25 oct. 2026, Paris passe de +2 à +1", TZ.offsetLabel("Europe/Paris", utc(2026, 9, 25, 0, 30)) === "UTC+2" && TZ.offsetLabel("Europe/Paris", utc(2026, 9, 25, 1, 30)) === "UTC+1");
ok("décalages particuliers : Inde +5:30, New York −4, UTC", TZ.offsetLabel("Asia/Kolkata", utc(2026, 6, 1)) === "UTC+5:30" && TZ.offsetLabel("America/New_York", utc(2026, 6, 1)) === "UTC−4" && TZ.offsetLabel("UTC", utc(2026, 6, 1)) === "UTC");
const night = utc(2026, 9, 18, 22, 30); // dimanche 18 oct., 22 h 30 UTC
ok("le jour dépend du fuseau : 18 à New York, 19 à Paris et à Tokyo", TZ.dayKey(night, "America/New_York") === "2026-10-18" && TZ.dayKey(night, "Europe/Paris") === "2026-10-19" && TZ.dayKey(night, "Asia/Tokyo") === "2026-10-19");
ok("heure murale : 00:30 à Paris, 07:30 à Tokyo", TZ.hhmm(night, "Europe/Paris") === "00:30" && TZ.hhmm(night, "Asia/Tokyo") === "07:30" && TZ.minutesOfDay(night, "Asia/Tokyo") === 450);
ok("minuit s'écrit 00:00 (pas 24:00)", TZ.hhmm(utc(2026, 9, 18, 22, 0), "Europe/Paris") === "00:00");
ok("nom de ville lisible", TZ.city("America/Argentina/Buenos_Aires") === "Buenos Aires" && TZ.city("UTC") === "UTC");
ok("fuseau inconnu refusé, connu accepté", !TZ.isValid("Mars/Olympus") && TZ.isValid("Pacific/Auckland"));
ok("liste des fuseaux non vide, contient Paris", TZ.allZones().includes("Europe/Paris") && TZ.allZones().length > 15);
ok("étiquettes d'heures : 7:30, 8 h, minuit −1 h = 23 h, décalage Inde", TZ.hourLabel(450) === "7:30" && TZ.hourLabel(480) === "8 h" && TZ.hourLabel(-60) === "23 h" && TZ.hourLabel(60 + 270) === "5:30");

print("# Déplacement à la souris (shiftLocal)");
const mon = utc(2026, 9, 12, 7, 0); // lundi 12 oct. 9 h à Paris (UTC+2)
ok("décaler de 30 min", TZ.shiftLocal(mon, "Europe/Paris", 0, 30) === "2026-10-12T09:30");
ok("décaler d'un jour et d'une heure en arrière", TZ.shiftLocal(mon, "Europe/Paris", 1, -60) === "2026-10-13T08:00");
ok("passer minuit : 9 h − 10 h = 23 h la veille", TZ.shiftLocal(mon, "Europe/Paris", 0, -600) === "2026-10-11T23:00");
ok("l'heure murale est celle du fuseau demandé", TZ.shiftLocal(mon, "Asia/Tokyo", 0, 0) === "2026-10-12T16:00");
ok("changement d'heure : 9 h à Paris le 26 oct. (hiver) reste 9 h murales même si l'UTC change", TZ.shiftLocal(utc(2026, 9, 26, 8, 0), "Europe/Paris", 0, 0) === "2026-10-26T09:00");
ok("changement de mois et d'année", TZ.shiftLocal(utc(2026, 11, 31, 22, 0), "Europe/Paris", 0, 0) === "2026-12-31T23:00" && TZ.shiftLocal(utc(2026, 11, 31, 22, 0), "Europe/Paris", 1, 0) === "2027-01-01T23:00");

print("# Mise en page (calendar.js)");
ok("deux événements qui se chevauchent : 2 colonnes", same(CAL.layoutColumns([{ start: 0, end: 60 }, { start: 30, end: 90 }]), [{ col: 0, cols: 2 }, { col: 1, cols: 2 }]));
ok("événements qui se suivent : pleine largeur chacun", same(CAL.layoutColumns([{ start: 0, end: 60 }, { start: 60, end: 120 }]), [{ col: 0, cols: 1 }, { col: 0, cols: 1 }]));
ok("trois en même temps : 3 colonnes", CAL.layoutColumns([{ start: 0, end: 60 }, { start: 10, end: 50 }, { start: 20, end: 40 }]).every((l) => l.cols === 3));
ok("la colonne se libère et se réutilise", same(CAL.layoutColumns([{ start: 0, end: 120 }, { start: 0, end: 30 }, { start: 30, end: 60 }]), [{ col: 0, cols: 2 }, { col: 1, cols: 2 }, { col: 1, cols: 2 }]));
ok("liste vide", same(CAL.layoutColumns([]), []));
const ev = (a, b) => ({ starts_at: a.toISOString(), ends_at: b.toISOString() });
const night2 = ev(utc(2026, 9, 14, 20, 0), utc(2026, 9, 15, 0, 0)); // 22 h → 02 h à Paris (UTC+2)
ok("événement de nuit : 22 h → minuit le premier jour, minuit → 2 h le suivant", same(CAL.segmentOn(night2, "2026-10-14", "Europe/Paris"), { start: 1320, end: 1440, endsHere: false }) && same(CAL.segmentOn(night2, "2026-10-15", "Europe/Paris"), { start: 0, end: 120, endsHere: true }) && CAL.segmentOn(night2, "2026-10-16", "Europe/Paris") === null && CAL.segmentOn(night2, "2026-10-13", "Europe/Paris") === null);
ok("fini pile à minuit : rien le lendemain", CAL.segmentOn(ev(utc(2026, 9, 14, 20, 0), utc(2026, 9, 14, 22, 0)), "2026-10-15", "Europe/Paris") === null);
ok("même événement, autre fuseau, autre jour : 20 h UTC = 05 h le lendemain à Tokyo", same(CAL.segmentOn(ev(utc(2026, 9, 14, 20, 0), utc(2026, 9, 14, 21, 0)), "2026-10-15", "Asia/Tokyo"), { start: 300, end: 360, endsHere: true }));
ok("clic : arrondi à la demi-heure et borné", CAL.minuteAt(0) === 0 && CAL.minuteAt(9 * 48 + 20) === 540 && CAL.minuteAt(9 * 48 + 30) === 540 + 30 && CAL.minuteAt(99999) === 1410 && CAL.minuteAt(-5) === 0);
const cursor = new Date(2026, 9, 14); // mercredi
const wk = CAL.range("week", cursor);
ok("semaine = lundi → dimanche", wk.first.getDate() === 12 && wk.last.getDate() === 18);
ok("jour = un seul jour, mois = 42 jours (6 semaines)", CAL.range("day", cursor).first === cursor && Math.round((CAL.range("month", cursor).last - CAL.range("month", cursor).first) / 86400000) === 41);
ok("titres : semaine et mois en français", CAL.title("week", cursor).includes("octobre") && CAL.title("month", cursor).includes("octobre 2026") && CAL.title("day", cursor).includes("mercredi"));
const esc = (s) => String(s).replace(/</g, "&lt;");
const html = CAL.calendarHtml({ mode: "week", cursor, data: { events: [{ ...ev(utc(2026, 9, 14, 8, 0), utc(2026, 9, 14, 9, 0)), id: 1, title: "<i>x</i>", project_name: null, can_edit: true }], tasks: [] },
  tz: "Europe/Paris", tz2: "Asia/Tokyo", now: utc(2026, 9, 14, 8, 30), esc });
ok("deux fuseaux : deux gouttières, décalage Tokyo (+7 h) sur les étiquettes", (html.match(/class="chours/g) || []).length === 2 && html.includes(">8 h<") && html.includes(">15 h<") && html.includes("Tokyo"));
ok("même fuseau deux fois : une seule gouttière", (CAL.calendarHtml({ mode: "week", cursor, data: { events: [], tasks: [] }, tz: "Europe/Paris", tz2: "Europe/Paris", now: utc(2026, 9, 14), esc }).match(/class="chours/g) || []).length === 1);
ok("ligne « maintenant » à 10 h 30 de Paris = 504 px, événement à 10 h = 480 px", html.includes("top:504px") && html.includes("top:480px") && !html.includes("<i>x"));
ok("avant chargement : message d'attente, pas d'erreur", CAL.calendarHtml({ mode: "week", cursor, data: null, tz: "Europe/Paris", esc }).includes("Chargement"));

print(failed ? `\n${failed} vérification(s) en échec` : "\nToutes les vérifications passent");
if (failed) throw new Error("échec");
