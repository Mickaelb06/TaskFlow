// Messagerie : détection et insertion des @mentions, rendu sûr des messages (fonctions pures).
import * as CH from "../js/chat.js";

let failed = 0;
const ok = (name, cond) => { if (!cond) failed++; print((cond ? "OK   " : "ECHEC") + " " + name); };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const team = { kind: "project", members: [{ username: "alice" }, { username: "bob" }, { username: "lea" }] };

print("# Détection du @ en cours de frappe");
ok("« @ » seul juste avant le curseur", same(CH.mentionAt("Salut @", 7), { start: 6, query: "" }));
ok("début de nom", same(CH.mentionAt("Salut @be", 9), { start: 6, query: "be" }));
ok("en début de message", same(CH.mentionAt("@al", 3), { start: 0, query: "al" }));
ok("le curseur au milieu du texte : seul ce qui précède compte", same(CH.mentionAt("a @bo et plus", 5), { start: 2, query: "bo" }));
ok("un email n'est pas une mention", CH.mentionAt("jean@", 5) === null && CH.mentionAt("jean@exa", 8) === null);
ok("après un espace ou un mot terminé : rien", CH.mentionAt("@bob ", 5) === null && CH.mentionAt("bonjour", 7) === null);
ok("« @@ » ignoré", CH.mentionAt("@@", 2) === null);

print("# Propositions");
const names = (c, q, me = "alice") => CH.suggestions(c, q, me).map((p) => p.name);
ok("équipe de 3 : les autres + « tous » en tête", same(names(team, ""), ["tous", "bob", "lea"]));
ok("filtre par début de nom, sans casse", same(names(team, "BO"), ["bob"]) && same(names(team, "l"), ["lea"]));
ok("on ne se propose pas soi-même", !names(team, "a").includes("alice"));
ok("« tous » apparaît en tapant « to »", same(names(team, "to"), ["tous"]));
ok("projet solo : personne à mentionner", same(names({ kind: "project", members: [{ username: "alice" }] }, ""), []));
ok("projet à deux : pas de « tous »", same(names({ kind: "project", members: [{ username: "alice" }, { username: "bob" }] }, ""), ["bob"]));
ok("conversation directe : pas de « tous »", same(names({ kind: "direct", members: [{ username: "alice" }, { username: "bob" }] }, ""), ["bob"]));

print("# Insertion");
let r = CH.applyMention("Salut @be et merci", 9, 6, "bob");
ok("remplace le @ en cours, ajoute une espace, curseur après", r.text === "Salut @bob  et merci" || r.text === "Salut @bob et merci");
ok("curseur juste après « @bob »+espace", r.caret === 11);
r = CH.applyMention("@", 1, 0, "tous");
ok("au début du message", r.text === "@tous " && r.caret === 6);

print("# Rendu sûr");
const html = (t, names = ["alice", "bob"], me = "alice") => CH.renderContent(t, names, me, esc);
ok("HTML échappé", !html("<img src=x onerror=alert(1)>").includes("<img") && html("<b>").includes("&lt;b&gt;"));
ok("mention d'un participant mise en valeur", html("salut @bob").includes('<span class="mention ">@bob</span>'));
ok("mention de moi : classe « me »", html("@alice regarde").includes('class="mention me"'));
ok("@tous et @all : classe « all »", html("@tous").includes("mention all") && html("@ALL").includes("mention all"));
ok("nom inconnu : texte brut", html("@inconnu") === "@inconnu");
ok("email laissé tel quel", html("jean@bob.fr") === "jean@bob.fr");
ok("ponctuation finale hors de la mention", html("@bob, merci. @alice!").includes("@bob</span>,") && html("@alice!").includes("@alice</span>!"));
ok("nom piégé ne casse pas l'attribut", !html('@bob"onmouseover="x').includes('onmouseover="x'));

print("# Messages et fils");
const author = { id: 1, username: "bob" };
const mk = (id, a, t, at, o = {}) => ({ id, author: a, content: t, created_at: at, mentions: [], mentions_all: false, can_delete: false, ...o });
const conv = { kind: "project", members: [{ username: "alice" }, { username: "bob" }] };
const out = CH.messagesHtml({ messages: [
  mk(1, author, "un", "2026-10-11T08:00:00Z"), mk(2, author, "deux", "2026-10-11T08:02:00Z"),
  mk(3, author, "trois", "2026-10-11T09:00:00Z"), mk(4, null, "fantôme", "2026-10-12T09:00:00Z"),
], conv, meName: "alice", tz: "Europe/Paris", now: new Date("2026-10-12T12:00:00Z"), hasMore: false, esc });
ok("2 messages rapprochés du même auteur : le second est groupé, sans nom", (out.match(/cmsg-head/g) || []).length === 3 && /class="cmsg[^"]*grouped[^"]*"[^>]*data-msg="2"/.test(out));
ok("séparateurs de jour : Hier et Aujourd'hui", out.includes("Hier") && out.includes("Aujourd&#39;hui"));
ok("heures dans le fuseau demandé (10:00 à Paris l'été)", out.includes("<time>10:00</time>") && !out.includes("<time>08:00</time>"));
ok("auteur supprimé affiché proprement", out.includes("Utilisateur supprimé") && !out.includes("undefined") && !out.includes("null"));
const now = new Date("2026-10-12T12:00:00Z");
ok("dates relatives : heure, Hier, jour", CH.whenLabel("2026-10-12T08:30:00Z", "Europe/Paris", now) === "10:30" && CH.whenLabel("2026-10-11T08:30:00Z", "Europe/Paris", now) === "Hier" && /5 oct/.test(CH.whenLabel("2026-10-05T08:30:00Z", "Europe/Paris", now)));
ok("changement de jour selon le fuseau : 23 h 30 UTC la veille = aujourd'hui à Tokyo", CH.whenLabel("2026-10-11T23:30:00Z", "Asia/Tokyo", now) === "08:30");

print(failed ? `\n${failed} vérification(s) en échec` : "\nToutes les vérifications passent");
if (failed) throw new Error("échec");
