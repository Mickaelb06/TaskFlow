// Administration : utilisateurs, projets, journal d'audit, réglages.
// `adminHtml` produit le HTML ; `createAdmin` fournit les actions (modales, appels API).
import * as D from "./dates.js";
import { barChart } from "./charts.js";

const ACTION_LABEL = {
  "user.create": "Utilisateur créé", "user.update": "Utilisateur modifié", "user.activate": "Compte réactivé",
  "user.deactivate": "Compte désactivé", "user.promote": "Droits admin accordés", "user.demote": "Droits admin retirés",
  "user.password_reset": "Mot de passe réinitialisé", "user.delete": "Utilisateur supprimé", "user.self_delete": "Compte supprimé par son titulaire",
  "project.delete": "Projet supprimé", "project.transfer": "Projet transféré", "settings.update": "Réglages modifiés",
};
const SETTING_LABEL = { allow_registration: "Inscriptions ouvertes" };
const yn = (v) => (v ? "oui" : "non");
const when = (iso) => D.fmt(new Date(iso), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function ago(iso) {
  if (!iso) return "jamais";
  const days = Math.floor((Date.now() - new Date(iso)) / 86400000);
  return days <= 0 ? "aujourd'hui" : days === 1 ? "hier" : days < 30 ? `il y a ${days} j` : D.fmt(new Date(iso), { day: "numeric", month: "short", year: "numeric" });
}

function detailsText(action, d = {}) {
  switch (action) {
    case "user.create": return `${d.is_staff ? "administrateur" : "utilisateur"}${d.password_generated ? ", mot de passe généré" : ""}`;
    case "user.update": return d.email ? `email : ${d.email[0]} → ${d.email[1]}` : "";
    case "user.password_reset": return d.password_generated ? "mot de passe généré" : "mot de passe choisi";
    case "user.delete": return [d.projects_transferred ? `${d.projects_transferred} projet(s) transféré(s) à ${d.transferred_to}` : "",
      d.projects_deleted ? `${d.projects_deleted} projet(s) solo supprimé(s)` : ""].filter(Boolean).join(", ");
    case "project.delete": return `propriétaire ${d.owner}, ${d.tasks} tâche(s)`;
    case "project.transfer": return `${d.from} → ${d.to}`;
    case "settings.update": return Object.entries(d).map(([k, [a, b]]) => `${SETTING_LABEL[k] || k} : ${yn(a)} → ${yn(b)}`).join(", ");
    default: return "";
  }
}

const TABS = [["overview", "Vue d'ensemble"], ["users", "Utilisateurs"], ["projects", "Projets"], ["audit", "Journal"], ["settings", "Réglages"]];

export function adminHtml({ admin: ad, user, esc, avatar }) {
  const tabs = `<div class="seg admin-tabs">${TABS.map(([k, l]) => `<button class="${ad.tab === k ? "on" : ""}" data-action="admin-tab" data-tab="${k}">${l}</button>`).join("")}</div>`;
  const body = { overview, users, projects, audit, settings }[ad.tab]({ ad, user, esc, avatar });
  return `<div class="admin">${tabs}${body}</div>`;
}

const kpi = (label, value, sub, cls = "") => `<div class="kpi"><span class="k-label">${label}</span><b class="${cls}">${value}</b><small>${sub}</small></div>`;
const empty = (msg) => `<p class="muted pad">${msg}</p>`;

function overview({ ad, esc, avatar }) {
  const s = ad.stats;
  if (!s) return empty("Chargement…");
  const doneRate = s.tasks.total ? Math.round((100 * s.tasks.done) / s.tasks.total) : 0;
  const recent = s.recent_users.map((u) => `<div class="drow">${avatar(u.username, "sm")}<span class="grow"><b>${esc(u.username)}</b> <span class="muted small">${esc(u.email)}</span></span><span class="muted small">${ago(u.date_joined)}</span></div>`).join("");
  const last = (ad.audit || []).map((a) => `<div class="drow"><span class="muted small nowrap">${when(a.created_at)}</span><span class="grow"><b>${esc(a.actor_name)}</b> — ${esc(ACTION_LABEL[a.action] || a.action)} <span class="muted">${esc(a.target)}</span></span></div>`).join("")
    || empty("Aucune action enregistrée.");
  return `<div class="kpis admin-kpis">
      ${kpi("Utilisateurs", s.users.total, `${s.users.active} actifs · ${s.users.inactive} désactivés`)}
      ${kpi("Administrateurs", s.users.admins, "comptes actifs avec droits")}
      ${kpi("Projets", s.projects, `${s.comments} commentaires`)}
      ${kpi("Tâches", s.tasks.total, `${doneRate} % terminées`)}
      ${kpi("Nouveaux (30 j)", s.users.new_30_days, "inscriptions")}
      ${kpi("Connectés (30 j)", s.users.active_30_days, "comptes actifs récemment")}
    </div>
    <div class="dash-grid">
      <section class="card span-6"><header><h3>Inscriptions par semaine</h3></header>${barChart(s.signups_weekly.map((w) => ({ date: w.date, count: w.count })), { w: 460, h: 150 })}</section>
      <section class="card span-6"><header><h3>État du système</h3></header>
        <ul class="status-list">
          <li><span class="sev ${s.registration_open ? "sev-ok" : "sev-medium"}"></span>Inscriptions publiques : <b>${s.registration_open ? "ouvertes" : "fermées"}</b></li>
          <li><span class="sev ${s.planning_engine?.name === "rust" ? "sev-ok" : "sev-low"}"></span>Moteur de planification : <b>${s.planning_engine?.name === "rust" ? `Rust ${esc(s.planning_engine.version || "")}` : "Python (module Rust non compilé)"}</b></li>
          <li><span class="sev ${s.users.admins > 1 ? "sev-ok" : "sev-medium"}"></span>${s.users.admins > 1 ? "Plusieurs administrateurs actifs" : "Un seul administrateur actif : prévoyez un second compte"}</li>
        </ul></section>
      <section class="card span-6"><header><h3>Derniers inscrits</h3></header><div class="drows">${recent || empty("Aucun utilisateur.")}</div></section>
      <section class="card span-6"><header><h3>Dernières actions</h3><button class="btn ghost" data-action="admin-tab" data-tab="audit">Tout voir →</button></header><div class="drows">${last}</div></section>
    </div>`;
}

function users({ ad, user, esc, avatar }) {
  const rows = (ad.users || []).map((u) => {
    const self = u.id === user.id;
    const locked = u.is_superuser && !user.is_superuser;
    const role = u.is_superuser ? ["Superutilisateur", "st-over"] : u.is_staff ? ["Admin", "st-ok"] : ["Utilisateur", "st-free"];
    const acts = locked ? '<span class="muted small">protégé</span>' : `
      <button class="btn ghost sm" data-action="admin-edit-user" data-id="${u.id}">Modifier</button>
      <button class="btn ghost sm" data-action="admin-reset-pw" data-id="${u.id}">Mot de passe</button>
      ${self ? "" : `<button class="btn ghost sm" data-action="admin-toggle-active" data-id="${u.id}" data-active="${u.is_active ? 1 : 0}">${u.is_active ? "Désactiver" : "Réactiver"}</button>
      <button class="btn ghost sm danger" data-action="admin-delete-user" data-id="${u.id}">Supprimer</button>`}`;
    return `<tr class="${u.is_active ? "" : "off"}">
      <td><div class="ucell">${avatar(u.username)}<div><b>${esc(u.username)}</b>${self ? ' <span class="tag">vous</span>' : ""}<div class="muted small">${esc(u.email)}</div></div></div></td>
      <td><span class="badge ${role[1]}">${role[0]}</span></td>
      <td><span class="badge ${u.is_active ? "st-ok" : "st-late"}">${u.is_active ? "Actif" : "Désactivé"}</span></td>
      <td>${u.project_count}${u.owned_count ? ` <span class="muted small">(${u.owned_count} à lui)</span>` : ""}</td>
      <td>${u.open_tasks}</td><td class="muted">${ago(u.last_login)}</td><td class="acts">${acts}</td></tr>`;
  }).join("");
  const f = ad.filter || "";
  return `<div class="admin-bar">
      <input type="search" data-admin="q" value="${esc(ad.q)}" placeholder="Rechercher un nom ou un email…" aria-label="Rechercher">
      <select data-admin="filter" aria-label="Filtrer">${[["", "Tous"], ["active", "Actifs"], ["inactive", "Désactivés"], ["admin", "Administrateurs"]].map(([v, l]) => `<option value="${v}" ${f === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <span class="grow muted small">${(ad.users || []).length} compte(s)</span>
      <button class="btn primary" data-action="admin-new-user">+ Créer un utilisateur</button></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Utilisateur</th><th>Rôle</th><th>Statut</th><th>Projets</th><th>Tâches ouvertes</th><th>Connexion</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="7">${empty("Aucun utilisateur ne correspond.")}</td></tr>`}</tbody></table></div>
    <p class="muted small">Désactiver un compte bloque immédiatement sa connexion tout en conservant ses données. Supprimer est définitif.</p>`;
}

function projects({ ad, esc, avatar }) {
  const rows = (ad.projects || []).map((p) => `<tr>
      <td><b>${esc(p.name)}</b></td><td><div class="ucell">${avatar(p.owner, "sm")}${esc(p.owner)}</div></td>
      <td>${p.members}</td><td>${p.done}/${p.tasks}</td><td class="muted">${p.deadline ? D.fmt(D.parse(p.deadline), { day: "numeric", month: "short", year: "numeric" }) : "—"}</td>
      <td class="muted">${ago(p.created_at)}</td>
      <td class="acts"><button class="btn ghost sm" data-action="admin-transfer-project" data-id="${p.id}">Transférer</button>
        <button class="btn ghost sm danger" data-action="admin-delete-project" data-id="${p.id}">Supprimer</button></td></tr>`).join("");
  return `<div class="admin-bar"><input type="search" data-admin="q" value="${esc(ad.q)}" placeholder="Rechercher un projet ou un propriétaire…" aria-label="Rechercher">
      <span class="grow muted small">${(ad.projects || []).length} projet(s)</span></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Projet</th><th>Propriétaire</th><th>Membres</th><th>Tâches</th><th>Échéance</th><th>Créé</th><th></th></tr></thead>
    <tbody>${rows || `<tr><td colspan="7">${empty("Aucun projet.")}</td></tr>`}</tbody></table></div>`;
}

function audit({ ad, esc }) {
  const rows = (ad.audit || []).map((a) => `<tr><td class="nowrap muted">${when(a.created_at)}</td><td><b>${esc(a.actor_name)}</b></td>
      <td>${esc(ACTION_LABEL[a.action] || a.action)}</td><td>${esc(a.target)}</td><td class="muted">${esc(detailsText(a.action, a.details))}</td></tr>`).join("");
  const f = ad.auditFilter || "";
  return `<div class="admin-bar"><select data-admin="audit-filter" aria-label="Filtrer le journal">${[["", "Toutes les actions"], ["user", "Utilisateurs"], ["project", "Projets"], ["settings", "Réglages"]].map(([v, l]) => `<option value="${v}" ${f === v ? "selected" : ""}>${l}</option>`).join("")}</select>
      <span class="grow muted small">${(ad.audit || []).length} entrée(s) — les mots de passe n'y figurent jamais</span></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Date</th><th>Administrateur</th><th>Action</th><th>Cible</th><th>Détail</th></tr></thead>
    <tbody>${rows || `<tr><td colspan="5">${empty("Aucune action enregistrée.")}</td></tr>`}</tbody></table></div>`;
}

function settings({ ad }) {
  const s = ad.settings;
  if (!s) return empty("Chargement…");
  const row = (key, title, text, on, extra = "") => `<label class="setting"><div class="grow"><b>${title}</b><div class="muted small">${text}</div>${extra}</div>
      <input type="checkbox" class="switch" data-setting="${key}" ${on ? "checked" : ""} aria-label="${title}"></label>`;
  return `<div class="card settings">
      ${row("allow_registration", "Inscriptions publiques", "Si désactivé, seul un administrateur peut créer des comptes. Les comptes existants ne sont pas affectés.", s.allow_registration)}
    </div>
    <p class="muted small">Chaque modification est enregistrée dans le journal.</p>`;
}

/* ------------------------------------------------------------------ actions */
export function createAdmin({ api, state, render, openModal, actions, toast, esc }) {
  const ad = () => state.admin;

  async function load() {
    const a = ad();
    if (a.tab === "overview") [a.stats, a.audit] = await Promise.all([api.adminStats(), api.adminAudit({ limit: 8 })]);
    else if (a.tab === "users") a.users = await api.adminUsers({ q: a.q, filter: a.filter });
    else if (a.tab === "projects") a.projects = await api.adminProjects(a.q);
    else if (a.tab === "audit") a.audit = await api.adminAudit({ limit: 200, action: a.auditFilter });
    else if (a.tab === "settings") a.settings = await api.adminSettings();
  }
  const refresh = async () => { await load(); render(); };

  function secretModal(title, username, password) {
    openModal(title, `<p>Communiquez ce mot de passe à <b>${esc(username)}</b> par un canal sûr. <b>Il ne sera plus affiché.</b></p>
      <div class="secret-row"><code class="secret">${esc(password)}</code>
        <button type="button" class="btn" data-action="copy" data-text="${esc(password)}">Copier</button></div>
      <div class="row end"><button class="btn primary" value="cancel" formnovalidate>J'ai noté le mot de passe</button></div>`);
  }
  const findUser = (id) => ad().users.find((u) => u.id === Number(id));
  const activeUsers = async (except) => (await api.adminUsers({ filter: "active" })).filter((u) => u.id !== except);
  const options = (users) => users.map((u) => `<option value="${u.id}">${esc(u.username)} — ${esc(u.email)}</option>`).join("");

  const handlers = {
    "admin-tab": async (el) => { Object.assign(ad(), { tab: el.dataset.tab, q: "", filter: "", auditFilter: "" }); await refresh(); },

    "admin-new-user": () => openModal("Créer un utilisateur", `
      <label class="block">Nom d'utilisateur<input name="username" required maxlength="150" pattern="[\\w.@+\\-]+" autocomplete="off" autofocus></label>
      <label class="block">Email<input name="email" type="email" required autocomplete="off"></label>
      <label class="block">Mot de passe<input name="password" type="password" autocomplete="new-password" placeholder="Laisser vide pour en générer un"></label>
      <label class="inline check-label block"><input type="checkbox" name="is_staff"> Administrateur (accès à cette interface)</label>
      ${actions("Créer")}`, async (f) => {
      const u = await api.adminCreateUser({ username: f.username, email: f.email, password: f.password || undefined, is_staff: f.is_staff === "on" });
      await refresh();
      if (u.generated_password) secretModal("Compte créé", u.username, u.generated_password);
      else { toast(`Compte « ${u.username} » créé.`); return true; }
      return false;
    }),

    "admin-edit-user": (el) => {
      const u = findUser(el.dataset.id);
      const self = u.id === state.user.id;
      openModal(`Modifier « ${esc(u.username)} »`, `
        <label class="block">Email<input name="email" type="email" required value="${esc(u.email)}"></label>
        <label class="inline check-label block"><input type="checkbox" name="is_staff" ${u.is_staff ? "checked" : ""} ${self ? "disabled" : ""}> Administrateur</label>
        <label class="inline check-label block"><input type="checkbox" name="is_active" ${u.is_active ? "checked" : ""} ${self ? "disabled" : ""}> Compte actif</label>
        ${self ? '<p class="muted small">Vous ne pouvez pas modifier vos propres droits ni vous désactiver.</p>' : ""}${actions()}`, async (f) => {
        const body = { email: f.email };
        if (!self) { body.is_staff = f.is_staff === "on"; body.is_active = f.is_active === "on"; }
        await api.adminUpdateUser(u.id, body);
        await refresh();
        toast("Utilisateur mis à jour.");
      });
    },

    "admin-reset-pw": (el) => {
      const u = findUser(el.dataset.id);
      openModal(`Mot de passe de « ${esc(u.username)} »`, `
        <label class="block">Nouveau mot de passe<input name="password" type="password" autocomplete="new-password" placeholder="Laisser vide pour en générer un"></label>
        <p class="muted small">L'ancien mot de passe cesse de fonctionner immédiatement.</p>${actions("Réinitialiser")}`, async (f) => {
        const r = await api.adminResetPassword(u.id, { password: f.password || undefined });
        await refresh();
        if (r.generated_password) { secretModal("Mot de passe réinitialisé", u.username, r.generated_password); return false; }
        toast("Mot de passe modifié.");
      });
    },

    "admin-toggle-active": async (el) => {
      const u = findUser(el.dataset.id);
      const off = u.is_active;
      if (off && !confirm(`Désactiver « ${u.username} » ? Il ne pourra plus se connecter (ses données sont conservées).`)) return;
      await api.adminUpdateUser(u.id, { is_active: !off });
      await refresh();
      toast(off ? "Compte désactivé." : "Compte réactivé.");
    },

    "admin-delete-user": async (el) => {
      const u = findUser(el.dataset.id);
      const detail = await api.adminUser(u.id);
      const owned = detail.owned_projects;
      const heirs = owned.length ? await activeUsers(u.id) : [];
      const solo = owned.filter((p) => p.other_members === 0).length;
      openModal(`Supprimer « ${esc(u.username)} » ?`, `
        <p>Action <b>définitive</b>. Ses tâches deviennent non assignées, ses commentaires restent signés « Utilisateur supprimé », ses accès aux projets disparaissent.</p>
        <p class="muted small">Pour conserver ses données, préférez <b>Désactiver</b>.</p>
        ${owned.length ? `<div class="warn"><b>Il possède ${owned.length} projet(s) :</b> ${owned.map((p) => esc(p.name)).join(", ")}.
          <label class="block">Nouveau propriétaire<select name="transfer_to" required><option value="">Choisir…</option>${options(heirs)}</select></label>
          ${solo ? `<label class="inline check-label block"><input type="checkbox" name="delete_solo"> Supprimer plutôt les ${solo} projet(s) où il est seul</label>` : ""}</div>` : ""}
        <label class="block">Tapez <b>${esc(u.username)}</b> pour confirmer<input name="confirm" required autocomplete="off"></label>
        <div class="row end"><button class="btn ghost" value="cancel" formnovalidate>Annuler</button><button class="btn primary danger-fill" value="ok">Supprimer définitivement</button></div>`, async (f) => {
        if (f.confirm !== u.username) throw new Error("Le nom saisi ne correspond pas.");
        await api.adminDeleteUser(u.id, { transfer_to: f.transfer_to, delete_solo: f.delete_solo === "on" ? "1" : "" });
        await refresh();
        toast(`« ${u.username} » supprimé.`);
      });
    },

    "admin-delete-project": (el) => {
      const p = ad().projects.find((x) => x.id === Number(el.dataset.id));
      openModal(`Supprimer « ${esc(p.name)} » ?`, `
        <p>Le projet, ses <b>${p.tasks} tâche(s)</b> et leurs commentaires seront supprimés <b>définitivement</b> pour ses ${p.members} membre(s).</p>
        <label class="block">Tapez le nom du projet pour confirmer<input name="confirm" required autocomplete="off"></label>
        <div class="row end"><button class="btn ghost" value="cancel" formnovalidate>Annuler</button><button class="btn primary danger-fill" value="ok">Supprimer définitivement</button></div>`, async (f) => {
        if (f.confirm !== p.name) throw new Error("Le nom saisi ne correspond pas.");
        await api.adminDeleteProject(p.id);
        await refresh();
        toast("Projet supprimé.");
      });
    },

    "admin-transfer-project": async (el) => {
      const p = ad().projects.find((x) => x.id === Number(el.dataset.id));
      const users = await activeUsers(p.owner_id);
      openModal(`Transférer « ${esc(p.name)} »`, `
        <p>Propriétaire actuel : <b>${esc(p.owner)}</b>. Il restera membre du projet.</p>
        <label class="block">Nouveau propriétaire<select name="user_id" required><option value="">Choisir…</option>${options(users)}</select></label>${actions("Transférer")}`, async (f) => {
        await api.adminTransferProject(p.id, Number(f.user_id));
        await refresh();
        toast("Propriété transférée.");
      });
    },

    copy: async (el) => {
      try { await navigator.clipboard.writeText(el.dataset.text); toast("Copié."); } catch { toast("Copie impossible : sélectionnez le texte."); }
    },
  };

  async function onChange(t) {
    const a = ad();
    if (t.dataset.setting) {
      await api.adminSetSettings({ [t.dataset.setting]: t.checked });
      await refresh();
      toast("Réglage enregistré.");
      return;
    }
    const key = { q: "q", filter: "filter", "audit-filter": "auditFilter" }[t.dataset.admin];
    if (key) { a[key] = t.value; await refresh(); }
  }

  return { load, handlers, onChange };
}
