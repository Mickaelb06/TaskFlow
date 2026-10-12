/* Messagerie interne : fonctions pures (mentions @, rendu HTML) — la navigation et les appels API sont dans app.js.
   Tout texte venant d'un utilisateur passe par esc() avant d'entrer dans le HTML. */
import * as TZ from "./tz.js";
import { icon } from "./icons.js";
import { art } from "./art.js";
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
  const people = (conv.members || []).filter((m) => m.username !== meName).map((m) => ({ name: m.username, everyone: false, kind: "user" }));
  if (conv.kind === "project" && (conv.members || []).length > 2) people.unshift({ name: "tous", everyone: true, kind: "user" });
  return people.filter((p) => p.name.toLowerCase().startsWith(q)).slice(0, 6);
}

/** « #12 » en cours de frappe : numéro ou début de titre de tâche. */
export function hashAt(text, caret) {
  const m = /(?<![\w&#])#([^\s#]{0,30})$/.exec(text.slice(0, caret));
  return m ? { start: m.index, query: m[1] } : null;
}

/** Tâches proposées pour `#query` : par numéro ou par morceau de titre. */
export function taskSuggestions(tasks, query) {
  const q = query.toLowerCase();
  return (tasks || []).filter((t) => !q || String(t.id).startsWith(q) || t.title.toLowerCase().includes(q))
    .slice(0, 6).map((t) => ({ name: String(t.id), label: t.title, kind: "task" }));
}

/** Remplace le @ en cours par « @nom » suivi d'une espace ; retourne le nouveau texte et la place du curseur. */
export function applyMention(text, caret, start, name, prefix = "@") {
  const after = text.slice(caret);
  const insert = `${prefix}${name} `;
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

export const REACTIONS = ["👍", "❤️", "😂", "🎉", "👀", "✅"];

export function sizeLabel(n) {
  return n < 1024 ? `${n} o` : n < 1048576 ? `${Math.round(n / 1024)} Ko` : `${(n / 1048576).toFixed(1)} Mo`;
}

function attachmentsHtml(m, esc) {
  if (!m.attachments?.length) return "";
  return `<div class="atts">${m.attachments.map((a) => a.image
    ? `<button class="att img" data-action="open-att" data-id="${a.id}" data-name="${esc(a.name)}" title="${esc(a.name)}"><img data-att="${a.id}" alt="${esc(a.name)}"></button>`
    : `<button class="att file" data-action="download-att" data-id="${a.id}" data-name="${esc(a.name)}">${icon("file", 18)}<span class="att-name">${esc(a.name)}</span><small>${sizeLabel(a.size)}</small></button>`).join("")}</div>`;
}

function toolbarHtml(m) {
  return `<div class="cmsg-tools">
    <button class="icon-btn" data-action="react-pop" data-id="${m.id}" title="Réagir" aria-label="Réagir">${icon("smile", 15)}</button>
    <button class="icon-btn" data-action="reply" data-id="${m.id}" title="Répondre" aria-label="Répondre">${icon("reply", 15)}</button>
    ${m.can_edit ? `<button class="icon-btn" data-action="edit-msg" data-id="${m.id}" title="Modifier" aria-label="Modifier">${icon("edit", 15)}</button>` : ""}
    ${m.can_delete ? `<button class="icon-btn danger" data-action="delete-message" data-id="${m.id}" title="Supprimer" aria-label="Supprimer">${icon("trash", 15)}</button>` : ""}</div>`;
}

/** Liste des messages : séparateurs de jour, messages du même auteur regroupés (moins de 5 min d'écart), réponses citées,
 *  réactions, pièces jointes, tâches citées. `editing` = id du message en cours de modification, `reactFor` = id dont
 *  le sélecteur d'émojis est ouvert, `canWrite` = faux pour un lecteur (aucun outil d'écriture). */
export function messagesHtml({ messages, conv, meName, tz, now = new Date(), hasMore, esc, editing = null, reactFor = null, canWrite = true }) {
  const names = (conv.members || []).map((m) => m.username);
  let prev = null;
  const rows = messages.map((m) => {
    const day = TZ.dayKey(new Date(m.created_at), tz);
    const author = m.author ? m.author.username : "Utilisateur supprimé";
    const sep = !prev || TZ.dayKey(new Date(prev.created_at), tz) !== day ? `<div class="chat-sep"><span>${esc(dayLabel(m.created_at, tz, now))}</span></div>` : "";
    const grouped = !sep && !m.reply_to && prev && (prev.author?.id ?? 0) === (m.author?.id ?? 0) && new Date(m.created_at) - new Date(prev.created_at) < 300000;
    prev = m;
    const mine = m.author && m.author.username === meName;
    const tagged = m.mentions.includes(meName) || (m.mentions_all && !mine);
    const body = editing === m.id
      ? `<div class="cmsg-edit"><textarea id="edit-input" rows="2" maxlength="2000">${esc(m.content)}</textarea>
          <div class="row"><button class="btn primary sm" data-action="save-edit" data-id="${m.id}">Enregistrer</button><button class="btn ghost sm" data-action="cancel-edit">Annuler</button><span class="muted small">Entrée pour enregistrer, Échap pour annuler</span></div></div>`
      : (m.content ? `<div class="cmsg-text">${renderContent(m.content, names, meName, esc)}${m.edited ? ' <span class="edited">(modifié)</span>' : ""}</div>` : "");
    const quote = m.reply_to ? `<button class="cmsg-quote" data-action="goto-msg" data-id="${m.reply_to.id}"><b>${esc(m.reply_to.author || "Utilisateur supprimé")}</b><span>${esc(m.reply_to.excerpt)}</span></button>` : "";
    const chips = (m.tasks || []).map((t) => `<button class="tchip ${t.status}" data-action="goto-task" data-project="${t.project}" data-task="${t.id}" title="Ouvrir la tâche">#${t.id} ${esc(t.title)}</button>`).join("");
    const reactions = (m.reactions || []).map((r) => `<button class="react ${r.mine ? "mine" : ""}" ${canWrite ? `data-action="react" data-id="${m.id}" data-emoji="${r.emoji}"` : "disabled"} title="${esc(r.users.join(", "))}">${r.emoji}<span>${r.count}</span></button>`).join("");
    const picker = reactFor === m.id ? `<div class="react-picker">${REACTIONS.map((e) => `<button data-action="react" data-id="${m.id}" data-emoji="${e}">${e}</button>`).join("")}</div>` : "";
    return `${sep}<div class="cmsg ${mine ? "own" : ""} ${grouped ? "grouped" : ""} ${tagged ? "tagged" : ""}" data-msg="${m.id}">
      ${grouped ? '<span class="cmsg-gap"></span>' : avatar(author, "sm")}
      <div class="cmsg-body">${grouped ? "" : `<div class="cmsg-head"><b>${esc(author)}</b><time>${TZ.hhmm(new Date(m.created_at), tz)}</time></div>`}
        ${quote}${body}${attachmentsHtml(m, esc)}${chips ? `<div class="tchips">${chips}</div>` : ""}
        ${reactions || picker ? `<div class="reacts">${reactions}${picker}</div>` : ""}</div>
      ${canWrite && editing !== m.id ? toolbarHtml(m) : (m.can_delete && editing !== m.id ? `<div class="cmsg-tools"><button class="icon-btn danger" data-action="delete-message" data-id="${m.id}" title="Supprimer" aria-label="Supprimer">${icon("trash", 15)}</button></div>` : "")}</div>`;
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

export function composerHtml(conv, draft, esc, { replyTo = null, files = [] } = {}) {
  if (!conv.can_write) return '<p class="muted small chat-ro">Vous avez un accès en lecture seule à ce projet : vous ne pouvez pas écrire ici.</p>';
  const hint = conv.kind === "direct" ? `Écrire à ${conv.title}…` : conv.solo ? "Noter quelque chose…" : "Message à l'équipe — @ pour mentionner, # pour citer une tâche";
  return `<form id="chat-form" class="composer" autocomplete="off"><div id="mention-pop" class="mention-pop" hidden></div>
    <div id="reply-bar" class="reply-bar" ${replyTo ? "" : "hidden"}>${replyTo ? replyBarHtml(replyTo, esc) : ""}</div>
    <div id="file-chips" class="file-chips" ${files.length ? "" : "hidden"}>${fileChipsHtml(files, esc)}</div>
    <div class="composer-row">
      <button type="button" class="icon-btn attach" data-action="attach" title="Joindre un fichier (images, PDF, documents — 5 Mo, 3 fichiers)" aria-label="Joindre un fichier">${icon("paperclip", 18)}</button>
      <input type="file" id="chat-file" multiple hidden accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.csv,.docx,.xlsx,.pptx,.odt">
      <textarea id="chat-input" rows="1" maxlength="2000" placeholder="${esc(hint)}" aria-label="Message">${esc(draft || "")}</textarea>
      <button class="btn primary send" aria-label="Envoyer">${icon("send", 16)}<span>Envoyer</span></button></div></form>`;
}

export function replyBarHtml(m, esc) {
  return `<span>Réponse à <b>${esc(m.author ? m.author.username : "Utilisateur supprimé")}</b> : ${esc((m.content || "Pièce jointe").slice(0, 90))}</span>
    <button type="button" class="icon-btn" data-action="cancel-reply" title="Annuler" aria-label="Annuler la réponse">${icon("x", 14)}</button>`;
}

export function fileChipsHtml(files, esc) {
  return files.map((f, i) => `<span class="file-chip">${icon("file", 14)}<span>${esc(f.name)}</span><small>${sizeLabel(f.size)}</small>
    <button type="button" class="icon-btn" data-action="remove-file" data-i="${i}" aria-label="Retirer ${esc(f.name)}">${icon("x", 12)}</button></span>`).join("");
}

export function searchHtml(rows, query, esc) {
  if (!rows.length) return `<p class="muted small pad">Aucun message ne contient « ${esc(query)} ».</p>`;
  return `<div class="side-title">${rows.length} résultat${rows.length > 1 ? "s" : ""}</div>${rows.map((r) => `<button class="crow hit" data-action="open-hit" data-conv="${r.conversation}" data-msg="${r.message}">
    <span class="crow-main"><b>${esc(r.conversation_title)}</b><small>${esc(r.author || "Utilisateur supprimé")} : ${esc(r.excerpt)}</small></span></button>`).join("")}`;
}

export function chatHtml({ convs, current, messages, hasMore, draft, meName, tz, now = new Date(), esc, editing = null, reactFor = null, replyTo = null, files = [], search = null }) {
  const conv = convs.find((c) => c.id === current);
  const right = conv
    ? `${threadHeaderHtml(conv, esc)}<div id="chat-msgs" class="chat-msgs">${messagesHtml({ messages, conv, meName, tz, now, hasMore, esc, editing, reactFor, canWrite: conv.can_write })}</div>${composerHtml(conv, draft, esc, { replyTo, files })}`
    : '<div class="empty small-empty">${art("messages")}<h2>Vos messages</h2><p class="muted">Choisissez une conversation, ou écrivez à un collègue.</p></div>';
  const list = search ? searchHtml(search.rows, search.q, esc) : convListHtml({ convs, current, tz, now, esc });
  return `<div class="chat"><aside class="chat-list"><div class="chat-search">${icon("search", 15)}<input id="chat-search" type="search" placeholder="Rechercher dans les messages" value="${esc(search ? search.q : "")}" aria-label="Rechercher dans les messages"></div>
    <div id="chat-convs">${list}</div></aside><section class="chat-thread">${right}</section></div>`;
}

export function popupHtml(items, active, esc) {
  return items.map((p, i) => `<button type="button" class="mention-item ${i === active ? "on" : ""}" data-action="pick-mention" data-name="${esc(p.name)}" data-kind="${p.kind || "user"}">
    ${p.kind === "task" ? `<span class="tnum">#${esc(p.name)}</span><b class="ellipsis">${esc(p.label)}</b>`
      : `${p.everyone ? '<span class="avatar xs all">@</span>' : avatar(p.name, "xs")}<b>${esc(p.name)}</b>${p.everyone ? '<small class="muted">toute l\'équipe</small>' : ""}`}</button>`).join("");
}

function inviteRow(n, tz, now, esc) {
  const when = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(n.starts_at));
  const answered = n.status !== "invited";
  return `<div class="notif invite ${n.read ? "" : "unread"}">
    ${avatar(n.author || "?", "sm")}
    <span class="notif-main"><button class="notif-open" data-action="open-invite" data-id="${n.id}" data-event="${n.event}" data-start="${esc(n.starts_at)}">
      <span><b>${esc(n.author || "Utilisateur supprimé")}</b> vous invite à <b>${esc(n.title)}</b></span>
      <small>${esc(when)}${n.project ? ` · ${esc(n.project)}` : ""}</small></button>
      <span class="invite-actions">
        <button class="btn sm ${n.status === "accepted" ? "primary" : ""}" data-action="rsvp" data-event="${n.event}" data-status="accepted">${icon("check", 13)}Accepter</button>
        <button class="btn sm ${n.status === "declined" ? "primary" : ""}" data-action="rsvp" data-event="${n.event}" data-status="declined">Refuser</button>
        ${answered ? `<span class="badge-status">${n.status === "accepted" ? "Vous avez accepté" : "Vous avez refusé"}</span>` : ""}</span></span>
    <time>${esc(whenLabel(n.created_at, tz, now))}</time>${n.read ? "" : '<i class="udot" aria-label="Non lue"></i>'}</div>`;
}

export function notificationsHtml({ rows, tz, now = new Date(), esc }) {
  if (!rows.length) return '<div class="empty small-empty">${art("notifications")}<h2>Aucune notification</h2><p class="muted">Vous serez prévenu ici quand quelqu\'un vous mentionne avec @ ou vous invite à un événement.</p></div>';
  return `<div class="notifs">${rows.map((n) => n.type === "invite" ? inviteRow(n, tz, now, esc) : `<button class="notif ${n.read ? "" : "unread"}" data-action="open-notif" data-id="${n.id}" data-conv="${n.conversation}">
    ${avatar(n.author || "?", "sm")}<span class="notif-main"><span><b>${esc(n.author || "Utilisateur supprimé")}</b> ${n.everyone ? "a prévenu tout le monde" : "vous a mentionné"} dans <b>${esc(n.conversation_title)}</b></span>
    <small>${esc(n.excerpt)}</small></span><time>${esc(whenLabel(n.created_at, tz, now))}</time>${n.read ? "" : '<i class="udot" aria-label="Non lue"></i>'}</button>`).join("")}</div>`;
}
