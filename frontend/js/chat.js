/* Messagerie interne : fonctions pures (mentions @, rendu HTML) — la navigation et les appels API sont dans app.js.
   Tout texte venant d'un utilisateur passe par esc() avant d'entrer dans le HTML. */
import * as TZ from "./tz.js";
import { icon } from "./icons.js";
import { hue } from "./palette.js";

const MENTION = /(?<![\w@])@(\w+(?:[.\-+]\w+)*)/g; // même règle que chat/services.py
const EVERYONE = ["tous", "all"];

/** @en cours de frappe juste avant le curseur : { start, query } ou null. « jean@ » (email) n'en est pas un. */
export function mentionAt(text, caret) {
  const m = /(?<![\w@])@(\w*)$/.exec(text.slice(0, caret));
  return m ? { start: m.index, query: m[1] } : null;
}

/** Propositions pour `query` : les autres participants, plus « tous » dans un fil d'équipe (3 personnes ou plus). */
export function suggestions(conv, query, meName) {
  const q = query.toLowerCase();
  const people = (conv.members || []).filter((m) => m.username !== meName).map((m) => ({ name: m.username, everyone: false }));
  if (conv.kind === "project" && (conv.members || []).length > 2) people.unshift({ name: "tous", everyone: true });
  return people.filter((p) => p.name.toLowerCase().startsWith(q)).slice(0, 6);
}

/** Remplace le @ en cours par « @nom » suivi d'une espace ; retourne le nouveau texte et la place du curseur. */
export function applyMention(text, caret, start, name) {
  const after = text.slice(caret);
  const insert = `@${name} `;
  return { text: text.slice(0, start) + insert + after.replace(/^ /, ""), caret: start + insert.length };
}

/** Texte → HTML sûr, avec les @mentions de vrais participants mises en valeur (celles qui vous visent en plus fort). */
export function renderContent(content, usernames, meName, esc) {
  const known = new Map(usernames.map((u) => [u.toLowerCase(), u]));
  return esc(content).replace(MENTION, (all, name) => {
    const key = name.toLowerCase();
    if (EVERYONE.includes(key)) return `<span class="mention all">@${name}</span>`;
    if (!known.has(key)) return all;
    return `<span class="mention ${known.get(key) === meName ? "me" : ""}">@${name}</span>`;
  });
}

/** « 14:05 » aujourd'hui, « Hier », sinon « 12 oct. ». */
export function whenLabel(iso, tz, now = new Date()) {
  const d = new Date(iso);
  const day = TZ.dayKey(d, tz);
  if (day === TZ.dayKey(now, tz)) return TZ.hhmm(d, tz);
  if (day === TZ.dayKey(new Date(now.getTime() - 86400000), tz)) return "Hier";
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", timeZone: tz }).format(d);
}

function dayLabel(iso, tz, now) {
  const day = TZ.dayKey(new Date(iso), tz);
  if (day === TZ.dayKey(now, tz)) return "Aujourd'hui";
  if (day === TZ.dayKey(new Date(now.getTime() - 86400000), tz)) return "Hier";
  return new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", timeZone: tz }).format(new Date(iso));
}

const avatar = (name, cls = "") => `<span class="avatar ${cls}" style="--h:${hue(name)}" title="${name.replace(/[<>&"]/g, "")}">${name.slice(0, 2).toUpperCase().replace(/[<>&"]/g, "")}</span>`;

/** Liste des messages : séparateurs de jour, messages du même auteur regroupés (moins de 5 min d'écart). */
export function messagesHtml({ messages, conv, meName, tz, now = new Date(), hasMore, esc }) {
  const names = (conv.members || []).map((m) => m.username);
  let prev = null;
  const rows = messages.map((m) => {
    const day = TZ.dayKey(new Date(m.created_at), tz);
    const author = m.author ? m.author.username : "Utilisateur supprimé";
    const sep = !prev || TZ.dayKey(new Date(prev.created_at), tz) !== day ? `<div class="chat-sep"><span>${esc(dayLabel(m.created_at, tz, now))}</span></div>` : "";
    const grouped = !sep && prev && (prev.author?.id ?? 0) === (m.author?.id ?? 0) && new Date(m.created_at) - new Date(prev.created_at) < 300000;
    prev = m;
    const mine = m.author && m.author.username === meName;
    const tagged = m.mentions.includes(meName) || (m.mentions_all && !mine);
    return `${sep}<div class="cmsg ${mine ? "own" : ""} ${grouped ? "grouped" : ""} ${tagged ? "tagged" : ""}" data-msg="${m.id}">
      ${grouped ? '<span class="cmsg-gap"></span>' : avatar(author, "sm")}
      <div class="cmsg-body">${grouped ? "" : `<div class="cmsg-head"><b>${esc(author)}</b><time>${TZ.hhmm(new Date(m.created_at), tz)}</time></div>`}
        <div class="cmsg-text">${renderContent(m.content, names, meName, esc)}</div></div>
      ${m.can_delete ? `<button class="icon-btn cmsg-del" data-action="delete-message" data-id="${m.id}" title="Supprimer ce message" aria-label="Supprimer ce message">${icon("trash", 15)}</button>` : ""}</div>`;
  });
  return `${hasMore ? '<button class="btn ghost chat-more" data-action="load-older">Messages plus anciens</button>' : ""}${rows.join("")}`;
}

function convRow(c, active, tz, now, esc) {
  const icon = c.kind === "direct" ? avatar(c.title, "sm") : `<span class="dot" style="--h:${hue(c.title)}"></span>`;
  const sub = c.last ? `${c.last.author ? esc(c.last.author) + " : " : ""}${esc(c.last.excerpt)}` : (c.solo ? "Bloc-notes personnel" : "Aucun message");
  return `<button class="crow ${active ? "active" : ""} ${c.unread ? "unread" : ""}" data-action="open-conv" data-id="${c.id}">
    <span class="crow-ico">${icon}</span>
    <span class="crow-main"><b>${esc(c.title)}</b><small>${sub}</small></span>
    <span class="crow-meta">${c.last ? `<time>${esc(whenLabel(c.last.created_at, tz, now))}</time>` : ""}${c.unread ? `<span class="ncount">${c.unread > 99 ? "99+" : c.unread}</span>` : ""}</span></button>`;
}

export function convListHtml({ convs, current, tz, now = new Date(), esc }) {
  const group = (title, rows) => rows.length ? `<div class="side-title">${title}</div>${rows.map((c) => convRow(c, c.id === current, tz, now, esc)).join("")}` : "";
  return group("Projets", convs.filter((c) => c.kind === "project")) + group("Messages directs", convs.filter((c) => c.kind === "direct"))
    || '<p class="muted small pad">Aucune conversation.</p>';
}

export function threadHeaderHtml(conv, esc) {
  const people = conv.members || [];
  const sub = conv.kind === "direct" ? "Conversation privée"
    : conv.solo ? "Bloc-notes personnel — vous êtes seul(e) dans ce projet. Invitez des membres pour échanger et vous mentionner avec @."
    : `${people.length} membres · tapez @ pour mentionner quelqu'un, @tous pour prévenir toute l'équipe`;
  return `<div class="thread-head"><div class="grow"><h2>${esc(conv.title)}</h2><p class="muted small">${esc(sub)}</p></div>
    <span class="avatars">${people.slice(0, 5).map((m) => avatar(m.username, "sm")).join("")}</span></div>`;
}

export function composerHtml(conv, draft, esc) {
  if (!conv.can_write) return '<p class="muted small chat-ro">Vous avez un accès en lecture seule à ce projet : vous ne pouvez pas écrire ici.</p>';
  const hint = conv.kind === "direct" ? `Écrire à ${conv.title}…` : conv.solo ? "Noter quelque chose…" : `Message à l'équipe — @ pour mentionner`;
  return `<form id="chat-form" class="composer" autocomplete="off"><div id="mention-pop" class="mention-pop" hidden></div>
    <textarea id="chat-input" rows="1" maxlength="2000" placeholder="${esc(hint)}" aria-label="Message">${esc(draft || "")}</textarea>
    <button class="btn primary send" aria-label="Envoyer">${icon("send", 16)}<span>Envoyer</span></button></form>`;
}

export function chatHtml({ convs, current, messages, hasMore, draft, meName, tz, now = new Date(), esc }) {
  const conv = convs.find((c) => c.id === current);
  const right = conv
    ? `${threadHeaderHtml(conv, esc)}<div id="chat-msgs" class="chat-msgs">${messagesHtml({ messages, conv, meName, tz, now, hasMore, esc })}</div>${composerHtml(conv, draft, esc)}`
    : '<div class="empty small-empty"><h2>Vos messages</h2><p class="muted">Choisissez une conversation, ou écrivez à un collègue.</p></div>';
  return `<div class="chat"><aside class="chat-list"><div id="chat-convs">${convListHtml({ convs, current, tz, now, esc })}</div></aside><section class="chat-thread">${right}</section></div>`;
}

export function popupHtml(items, active, esc) {
  return items.map((p, i) => `<button type="button" class="mention-item ${i === active ? "on" : ""}" data-action="pick-mention" data-name="${esc(p.name)}">
    ${p.everyone ? '<span class="avatar xs all">@</span>' : avatar(p.name, "xs")}<b>${esc(p.name)}</b>${p.everyone ? '<small class="muted">toute l\'équipe</small>' : ""}</button>`).join("");
}

export function notificationsHtml({ rows, tz, now = new Date(), esc }) {
  if (!rows.length) return '<div class="empty small-empty"><h2>Aucune notification</h2><p class="muted">Vous serez prévenu ici quand quelqu\'un vous mentionne avec @.</p></div>';
  return `<div class="notifs">${rows.map((n) => `<button class="notif ${n.read ? "" : "unread"}" data-action="open-notif" data-id="${n.id}" data-conv="${n.conversation}">
    ${avatar(n.author || "?", "sm")}<span class="notif-main"><span><b>${esc(n.author || "Utilisateur supprimé")}</b> ${n.everyone ? "a prévenu tout le monde" : "vous a mentionné"} dans <b>${esc(n.conversation_title)}</b></span>
    <small>${esc(n.excerpt)}</small></span><time>${esc(whenLabel(n.created_at, tz, now))}</time>${n.read ? "" : '<i class="udot" aria-label="Non lue"></i>'}</button>`).join("")}</div>`;
}
