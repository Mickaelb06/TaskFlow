/* Service worker de TaskFlow : rend l'application installable et la fait démarrer hors connexion.
   Stratégie « réseau d'abord » : on sert toujours la dernière version quand le réseau répond (jamais de code périmé),
   le cache ne sert qu'en secours hors connexion. L'API (/api/) n'est JAMAIS mise en cache : les données restent fraîches
   et privées. Enregistré seulement hors localhost (voir app.js) pour ne pas gêner le développement. */
const CACHE = "taskflow-shell-v1";
const SHELL = ["/", "/index.html", "/css/style.css", "/config.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return; // réseau direct
  e.respondWith(
    fetch(e.request).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
      return res;
    }).catch(() => caches.match(e.request).then((hit) => hit || caches.match("/index.html"))),
  );
});
