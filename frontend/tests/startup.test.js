// Démarrage : adresse /admin et affichage d'une erreur lisible quand le chargement échoue.
globalThis.__path = "/admin";
import "./stub.js";
import "../js/app.js";

let failed = 0;
const ok = (name, cond) => { if (!cond) failed++; print((cond ? "OK   " : "ECHEC") + " " + name); };
for (let i = 0; i < 150; i++) await Promise.resolve();
ok("l'adresse /admin ouvre l'administration", __els["#view"].innerHTML.includes("data-tab=\"users\"") && __els["#toolbar"].innerHTML.includes("Administration"));
if (failed) throw new Error("échec");
