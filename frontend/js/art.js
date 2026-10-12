/* Petites illustrations des écrans vides (SVG inline, couleurs de la palette via variables CSS). Rien d'utilisateur ici. */
const wrap = (body) => `<svg class="art" viewBox="0 0 160 110" width="160" height="110" role="img" aria-hidden="true">${body}</svg>`;

const ART = {
  messages: wrap(`<rect x="22" y="14" width="86" height="52" rx="14" class="a-main"/><path d="M44 66v18l20-18z" class="a-main"/>
    <rect x="42" y="30" width="46" height="6" rx="3" class="a-light"/><rect x="42" y="44" width="30" height="6" rx="3" class="a-light"/>
    <rect x="76" y="48" width="64" height="40" rx="12" class="a-accent"/><path d="M122 88v14l-16-14z" class="a-accent"/>
    <rect x="90" y="60" width="36" height="5" rx="2.5" class="a-light2"/><rect x="90" y="71" width="24" height="5" rx="2.5" class="a-light2"/>`),
  notifications: wrap(`<path d="M80 18c-17 0-28 12-28 30 0 21-10 27-10 27h76s-10-6-10-27c0-18-11-30-28-30z" class="a-main"/>
    <circle cx="80" cy="14" r="5" class="a-accent"/><path d="M70 82a10 10 0 0 0 20 0z" class="a-accent"/>
    <circle cx="116" cy="30" r="7" class="a-amber"/><circle cx="40" cy="92" r="4" class="a-light"/><circle cx="130" cy="86" r="3" class="a-light"/>`),
  tasks: wrap(`<rect x="34" y="12" width="92" height="86" rx="12" class="a-main"/>
    <circle cx="54" cy="36" r="8" class="a-accent"/><path d="M50 36l3 3 6-7" class="a-check"/><rect x="70" y="32" width="42" height="7" rx="3.5" class="a-light"/>
    <circle cx="54" cy="58" r="8" class="a-light2"/><rect x="70" y="54" width="34" height="7" rx="3.5" class="a-light"/>
    <circle cx="54" cy="80" r="8" class="a-light2"/><rect x="70" y="76" width="40" height="7" rx="3.5" class="a-light"/>`),
  projects: wrap(`<rect x="14" y="48" width="40" height="46" rx="8" class="a-main"/><rect x="60" y="26" width="40" height="68" rx="8" class="a-accent"/>
    <rect x="106" y="38" width="40" height="56" rx="8" class="a-amber"/><rect x="22" y="58" width="24" height="5" rx="2.5" class="a-light"/>
    <rect x="68" y="36" width="24" height="5" rx="2.5" class="a-light2"/><rect x="114" y="48" width="24" height="5" rx="2.5" class="a-light2"/>`),
  calendar: wrap(`<rect x="24" y="20" width="112" height="78" rx="12" class="a-main"/><rect x="24" y="20" width="112" height="22" rx="12" class="a-accent"/>
    <rect x="46" y="10" width="8" height="18" rx="4" class="a-amber"/><rect x="106" y="10" width="8" height="18" rx="4" class="a-amber"/>
    <rect x="40" y="54" width="20" height="14" rx="4" class="a-light"/><rect x="70" y="54" width="20" height="14" rx="4" class="a-light2"/><rect x="100" y="54" width="20" height="14" rx="4" class="a-light"/>
    <rect x="40" y="76" width="20" height="14" rx="4" class="a-light2"/><rect x="70" y="76" width="20" height="14" rx="4" class="a-amber"/>`),
};

/** Illustration `name` (messages, notifications, tasks, projects, calendar) ; chaîne vide si inconnue. */
export const art = (name) => ART[name] || "";
