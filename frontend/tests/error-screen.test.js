// Si l'API est injoignable, l'utilisateur doit voir un message et un bouton, jamais un écran vide.
globalThis.__failPath = "/projects/";
import "./stub.js";
import "../js/app.js";

let failed = 0;
const ok = (name, cond) => { if (!cond) failed++; print((cond ? "OK   " : "ECHEC") + " " + name); };
for (let i = 0; i < 150; i++) await Promise.resolve();
const v = __els["#view"].innerHTML;
ok("écran d'erreur lisible quand l'API ne répond pas", v.includes("Impossible de charger vos données") && v.includes("Failed to fetch") && v.includes("Réessayer"));
if (failed) throw new Error("échec");
