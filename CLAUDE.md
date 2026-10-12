# TaskFlow — contexte pour Claude

Outil de **gestion de projet** (solo / équipe) : Gantt avec dépendances, chemin critique, indicateurs de risque, replanification, et un calendrier à fuseaux horaires. Page d'accueil = **tableau de bord personnel** (`planning.user_dashboard`, `GET /api/dashboard/`) ; vue par défaut d'un projet = **Synthèse** (`insights.stats`) ; **Gantt** ; **Équipe** montre qui travaille sur quoi et qui est en retard (`planning.team_status`, exposé dans `insights.team`) ; Liste et Tableau sont secondaires. Le **Calendrier** (page à part, façon Notion Calendar) montre événements à l'heure + tâches à la journée de tous les projets. Design inspiré de Notion Calendar. Ne pas dériver vers un simple agenda ni vers un clone de Todoist.
Projet support d'une VAE « Concepteur Développeur d'Applications » (RNCP niveau 6) : le code et la documentation doivent rester **défendables devant un jury** (architecture claire, tests, sécurité, docs). Projet autonome, sans lien avec d'autres projets de l'auteur.

## Stack
- `backend/` : Python 3.12, Django 5.2 LTS, Django REST Framework, JWT (simplejwt), PostgreSQL
- `frontend/` : HTML/CSS/JS pur (modules ES), **sans framework, sans build, sans TypeScript**. Pas d'appli mobile ni Flutter.
- Docker Compose (db, api, web/nginx), CI GitHub Actions

## Architecture backend (ne pas la contourner)
`urls → views (ViewSet) → services.py (règles métier + droits) → models (ORM)`. Serializers = validation.
- Apps : `accounts`, `projects` (Project, Membership), `tasks` (Task, Comment), `agenda` (Event), `chat` (Conversation, Message, Notification, ReadMark, Reaction, Attachment). Transverses : `accounts/emails.py` (e-mails), `accounts/account_services.py` (export/suppression de son compte), `taskflow/throttles.py` (limites de débit).
- **Moteur de calcul en deux implémentations** : `backend/planning_rs/` (Rust + PyO3, module `taskflow_planning`) et `tasks/planning_py.py` (Python de référence, aussi le repli). `tasks/planning_engine.py` choisit (`TASKFLOW_PLANNING_BACKEND` = auto/rust/python). **Tout changement d'algorithme se fait dans LES DEUX fichiers** (`engine.rs` et `planning_py.py`) + un cas dans `tasks/test_engine.py` (comparaison sur graphes aléatoires). Les nœuds sont des tuples `(id, terminée, début, fin, prérequis)`, dates en ordinaux ; le moteur ne touche jamais à la base.
- `tasks/planning.py` = moteur déterministe (cascade des dépendances, CPM, prévision de fin, risques, replan). **Aucune logique de date dans les vues** : tout passe par ce module.
- `agenda/` = calendrier : `Event` (UTC, `project` vide = personnel), `services.py` (droits, fuseaux, `calendar()`), `GET /api/calendar/` (événements + tâches d'une période). Fuseau de l'utilisateur = `accounts.Profile.timezone` (+ `secondary_timezone`), validé par `accounts/timezones.py::zone` (jamais de nom IANA non vérifié).
- Dépendances : `Task.dependencies` (M2M vers soi, « dépend de »). Jamais de boucle (`planning.would_cycle`). Déplacer une tâche repousse ses successeurs, ne les avance jamais, et ne touche pas aux tâches terminées.
- Les vues de projet héritent de `projects/mixins.py::ProjectScopedMixin` : 404 si non membre, 403 si écriture avec un rôle insuffisant.
- Les services lèvent des exceptions Django (`PermissionDenied`, `ValidationError`) ; `taskflow/exceptions.py` les convertit en 403/400.
- Rôles : `owner` (1 par projet), `member` (lit/écrit), `viewer` (lit). Un projet solo = un seul membre.
- Isolation : un utilisateur ne voit jamais un projet dont il n'est pas membre (réponse 404, pas 403).

## Commandes
```bash
cd backend
python manage.py test                      # tests (SQLite : USE_SQLITE=1, sinon PostgreSQL)
python manage.py makemigrations --check --dry-run
python manage.py runserver                 # API :8000
cd ../frontend && python3 serve.py 5173   # front :5173 (en-têtes no-store, repli sur index.html pour /admin)
docker compose up --build                  # tout, sur :8080
```

## Administration
- Un admin = `User.is_staff` (superutilisateur = `is_superuser`). Pas le site `/admin` de Django (non installé) : API `accounts/admin_views.py` sous `/api/admin/…`, permission `IsAppAdmin` (staff **actif**), interface `frontend/js/admin.js`.
- Toute règle de sécurité vit dans `accounts/admin_services.py` (jamais dans les vues ni le front) : pas d'action sur soi (désactiver/supprimer/retirer ses droits), toujours ≥ 1 admin actif, seul un superutilisateur touche un superutilisateur, suppression d'un propriétaire = `transfer_to` obligatoire (ou `delete_solo`), tout dans une transaction.
- **Chaque action d'admin écrit une ligne `AuditLog`** (`log()`), sans secret. Nouvelle action admin = nouvelle entrée dans `ACTION_LABEL` (`admin.js`) + test dans `accounts/test_admin.py` qui vérifie la trace d'audit.
- Les mots de passe générés (`secrets.token_urlsafe`) ne sont renvoyés qu'**une fois** dans la réponse, jamais stockés ni journalisés.
- `SiteSettings` (singleton pk=1) : `allow_registration` (ferme `/auth/register/`, exposé publiquement par `/auth/config/`).
- Les paramètres booléens d'un PATCH admin utilisent `partial=True` : un champ absent ne doit jamais valoir « faux ».
- `Comment.author` est nullable (`SET_NULL`) : un compte supprimé laisse ses commentaires, affichés « Utilisateur supprimé ».

## Tests
- Backend : `cd backend && python manage.py test` (338 tests, ~15 s : hachage MD5 en test seulement ; aucun appel réseau). Les limites de débit utilisent le cache : **`cache.clear()` dans `setUp`** des tests qui envoient beaucoup de requêtes. Les e-mails partent à `transaction.on_commit` : tests avec `self.captureOnCommitCallbacks(execute=True)` ; `django.core.mail.outbox`.
- E2E : `./test-e2e.sh` (Selenium + Firefox, vrai navigateur, 33 scénarios ; démarre sa propre API sur :8010 et son front sur :5180, base temporaire). Les tests réagissent à des repeints du DOM : utiliser les aides qui réessaient (`open_conv`, `has_text`) contre les `StaleElementReferenceException`.
- Front : `./test-front.sh` (204 vérifications) — `frontend/tests/stub.js` simule le DOM et l'API ; **ce n'est pas un test E2E** : le rendu visuel, les gestes à la souris et les modales ne sont vérifiés que par `./test-e2e.sh`. Ajouter une vérification à `smoke.test.js` pour chaque nouvelle vue **et** un scénario E2E pour chaque nouveau geste.
- Captures d'écran pour juger le rendu : Firefox headless sur une copie du front (`firefox --headless --no-remote --profile <dossier neuf> --screenshot …`) ; **profil neuf à chaque fois** sinon le cache sert d'anciens fichiers.

## Tableaux de bord
- Graphiques en SVG écrits à la main (`frontend/js/charts.js`), sans bibliothèque : donut, anneau, courbes, histogramme. Couleurs uniquement via les classes CSS de la palette.
- `Task.completed_at` est posée/effacée **uniquement** par `services.update_task`/`create_task` (jamais par le client, champ en lecture seule). Elle alimente la courbe d'avancement et la vélocité ; les tâches terminées avant son introduction ont `created_at` comme date de fin (migration 0003).
- `planning.health()` = santé d'un projet (done / empty / late / risk / ok). La page d'accueil ne montre que les projets dont l'utilisateur est membre.

## Design
Palette **crème et brun** (clair) / **espresso** (sombre), définie uniquement par les variables CSS de `:root` dans `frontend/css/style.css` (`--bg`, `--accent`, `--ok`, `--amber`, `--today`, `--p1..p3`, `--on-accent`). Ne jamais mettre de couleur en dur ailleurs : toujours une variable. Avatars et pastilles de projet utilisent des teintes chaudes (brun, ocre, olive).

## Messagerie — règles
- `chat/` : un fil `Conversation` par projet (créé à la demande, `solo` = un seul membre → bloc-notes) + conversations directes (`user_a.pk < user_b.pk`, unique). Droits dans `chat/services.py` (`can_read` / `can_write`), jamais dans les vues ; un non-participant reçoit **404**, un lecteur de projet **403** en écriture.
- Les mentions sont calculées **côté serveur** (`parse_mentions`) avec le même motif regex que `frontend/js/chat.js` (garder les deux identiques) ; seuls les participants sont notifiables, jamais l'auteur ; `@tous`/`@all` seulement dans un fil de projet de 3 personnes ou plus. Modifier un message ne renotifie que les **nouvelles** mentions.
- Le contenu est stocké **brut** ; le front l'échappe avec `esc()` puis ajoute les `<span class="mention">` (jamais l'inverse).
- `#12` cite une tâche **du projet du fil seulement** (jamais d'un autre projet : fuite de titres) ; pas dans les conversations directes.
- **Pièces jointes** : type imposé par l'extension **et** vérifié sur le contenu (octets magiques), jamais le type du navigateur ; pas de SVG/HTML/exécutables ; nom stocké = uuid ; servies par `/chat/attachments/<id>/` avec le jeton (`nosniff`, CSP `sandbox`) ; le fichier est supprimé avec le message (signal `post_delete`). Stockage `MEDIA_ROOT` (volume Docker `media`).
- Messages directs : exigent un projet en commun ; l'API répond **404 identique** pour « inconnu » et « sans projet en commun » (on ne devine pas quels comptes existent).
- Temps réel = **relève toutes les 15 s** (`pollChat` dans `app.js`), pas de WebSocket : volontaire (simple, défendable) ; ne pas descendre sous 10 s. Limite de débit `chat` (60/min) sur les écritures seulement (`WritesOnlyThrottle`), jamais sur la relève.
- Réponse (`reply_to`), réactions (6 émojis autorisés, `REACTIONS` dans `services.py` **et** `chat.js`), recherche (`/chat/search/`, `?around=` pour ouvrir un résultat).

## Calendrier et fuseaux horaires — règles
- **Stockage en UTC, affichage dans le fuseau de l'utilisateur.** Une date-heure *sans* décalage envoyée à l'API est l'heure murale du fuseau `timezone` de la requête (sinon celui du profil) ; avec décalage, elle est prise telle quelle (`agenda/serializers.py::to_internal_value`). Ne jamais convertir à la main dans une vue.
- `GET /api/calendar/?from&to` raisonne en **jours du fuseau du profil** (`services.day_bounds`) : un événement à 23 h 30 à Paris est le lendemain à Tokyo. Les tâches, elles, n'ont que des dates (sans heure ni fuseau).
- Front : `js/tz.js` (Intl uniquement, pas de bibliothèque) et `js/calendar.js` (rendu pur, testé dans `tests/calendar.test.js`). Le calendrier s'affiche toujours dans `state.user.timezone` ; le second fuseau n'ajoute qu'une colonne d'heures.
- Tout test de date-heure doit couvrir un changement d'heure (25 oct. 2026 à Paris) et un fuseau sans heure d'été (Tokyo).
- **Glisser-déposer / redimensionnement / création à la souris** : événements `pointer*` dans `app.js` (`cdrag`), pas de 15 min ; on envoie une heure *murale* (`tz.shiftLocal`) + `timezone`, jamais d'instant calculé côté navigateur. Un simple clic ne déplace rien (seuil de 5 px) et `suppressClick` évite d'ouvrir la fenêtre après un glissement.
- **Récurrence** (`agenda/services.occurrences`) : la même heure *murale* du fuseau de l'événement (donc suit l'heure d'été), horizon 3 ans, le 31 saute les mois courts. Modifier une occurrence modifie la **série** (les occurrences portent `series_starts_at`) ; « supprimer cette occurrence » = `EventSkip`.
- **Invitations** (`Invitation`) : un invité voit l'événement sans pouvoir le modifier ; compte comme notification (`summary`, `/notifications/` fusionne mentions et invitations, `type: mention|invite`).

## Gestion de projet — règles
- **Jours ouvrés** : `Project.skip_weekends` ; `tasks/workdays.py` convertit dates ↔ numéros de jour ouvré **autour** du moteur (`planning._nodes/_unit`). Ne jamais ajouter de logique « week-end » dans `engine.rs`/`planning_py.py`.
- **Tâches récurrentes** (`services._spawn_next`) : créées à la **première** fin de la tâche (garde `recurrence_of`), même durée, sans dépendances ; mensuel = même quantième ramené en fin de mois.
- **Simulation** `delay_impacts` (Rust **et** Python, comparés par `test_engine.py`) ; `planning.delay_simulation` / `planning.workload` = adaptateurs. Rééquilibrage : propose seulement des tâches `todo`, jamais à un lecteur, jamais au-delà de 100 %.
- **Temps** (`time_services.py`) : un seul chrono par utilisateur (en démarrer un arrête l'autre), plafonné à 12 h, minimum 1 min ; le total de la liste des tâches est annoté (une requête) ; compte supprimé → saisies conservées, signées « Utilisateur supprimé ».
- **Modèles** (`projects/templates.py`) : décalages en jours (ouvrés si le modèle l'est) ; chaque modèle fourni est vérifié par un test (aucune tâche ne commence avant la fin de ses prérequis) — en ajouter un = laisser ce test le valider.

## Compte et sécurité — règles
- **Mini-fenêtre de conversation** (`#dock`, `app.js` section « mini-fenêtre ») : `render()` est un enrobage de `renderPage()` ; quitter Messages avec un fil ouvert l'y place (`dockOpen`), revenir dans Messages la retire (le brouillon passe dans `state.chat.drafts`). Elle a **son propre état** (`state.dock`, ses messages) et n'utilise aucun id de la page Messages ; messages affichés sans outils (`canWrite:false`, `can_edit/can_delete:false`). Persistée dans `localStorage.dock`, relevée par `pollChat` (`pollDock`).
- **Ajout par `@nom`** : `GET /projects/{id}/member-candidates/?q=` (propriétaire seulement, préfixe de nom, jamais d'annuaire complet) ; `wireCandidates` dans `app.js`.
- **Liens d'invitation** (`ProjectInvite`, `projects/services.py`) : jeton jamais stocké (empreinte SHA-256), renvoyé une seule fois à la création ; rôle membre/lecteur seulement ; **404 identique** pour tout jeton non valable ; l'acceptation passe par `select_for_update`. Front : `?invite=jeton` → `localStorage.pending_invite`, adresse nettoyée, bandeau sur l'écran de connexion, acceptation après connexion/inscription (`acceptPendingInvite`, `startApp`).
- Limites de débit par `throttle_scope` (réglables par variables d'environnement) ; `login` limite par IP (et compte aussi les bons mots de passe une fois la limite atteinte). Derrière un proxy, régler `NUM_PROXIES`.
- Suppression de son compte : mot de passe exigé, refusée si dernier admin ou propriétaire d'un projet partagé (→ `POST /projects/{id}/transfer/`) ; projets solo supprimés ; messages/commentaires/temps conservés, signés « Utilisateur supprimé » ; ligne d'audit `user.self_delete`.
- E-mails : jamais bloquants (`fail_silently=False` mais exception journalisée), texte brut, 1 e-mail de mention par fil et par 10 min, préférence `Profile.notify_email` ; résumé : `send_digest`.
- PWA : `sw.js` « réseau d'abord », n'enregistre rien de `/api/`, **enregistré seulement hors localhost** (sinon risque de code périmé en développement).

## Page vitrine
`frontend/vitrine/` : `index.html` (page commerciale, ton orienté bénéfices), `vitrine.css`, `img/` (captures de l'application). Pas de page « jury ». Rien d'inventé : pas de témoignage, de prix ni de chiffre d'usage fictif. Captures : Firefox headless (profil neuf) sur le compte démo.

## Conventions
- Langue : **français** (UI, commentaires, docs, messages d'erreur). Code identifiants en anglais.
- Toute règle métier ou de droit nouvelle = un test dans le `tests.py` de l'app + une ligne dans `docs/tests/plan-de-tests.md`.
- Tout changement de modèle = migration commitée. Changement d'API = `docs/conception/api.md` à jour.
- Front : tout contenu venant de l'utilisateur passe par `esc()` avant d'aller dans `innerHTML`. Aucune dépendance npm.
- Pas de secret dans le dépôt : variables d'environnement (`.env.example`).
- Garder `docs/referentiel-cda.md` à jour (compétence ↔ preuve).

## Rust
- Compiler : `cd backend && export PYO3_PYTHON="$PWD/.venv/bin/python" VIRTUAL_ENV="$PWD/.venv" && maturin develop --release --uv -m planning_rs/Cargo.toml`. **Après toute modification de `engine.rs` il faut recompiler** sinon Django continue d'utiliser l'ancien binaire.
- `PYO3_PYTHON` est indispensable : sans lui `cargo` prend le Python système (3.9) et échoue (`abi3-py310`). `--uv` est indispensable avec un venv créé par `uv` (pas de pip dedans).
- Tests Rust : `cd backend/planning_rs && cargo test --lib`. La logique pure est dans `engine.rs`, `lib.rs` ne fait que convertir les types (aucune logique métier dedans).
- Ne pas affirmer que Rust « accélère » l'application : les mesures (`docs/conception/moteur-rust.md`) montrent ×2 à ×5 sur les calculs simples (dominés par la copie des données) et ×110 sur la simulation de retard (O(n²)) — imperceptible sur un projet réaliste de 50 tâches, utile au-delà de quelques centaines. Mettre à jour ces mesures si le moteur change.
- Docker : `backend/Dockerfile` compile le module en deux étapes (non testé ici : Docker n'est pas installé sur cette machine).

## Pièges connus
- **Cache navigateur** : avec `http.server` le navigateur gardait d'anciens `.js`/`.css` mélangés aux nouveaux (écran cassé après une mise à jour). Toujours servir le front avec `frontend/serve.py` (no-store). Un bandeau rouge (`#fatal`, dans `index.html`) s'affiche si une erreur JS survient, et `startApp` affiche « Impossible de charger vos données » si l'API échoue : ne jamais laisser un écran vide silencieux.
- `start.sh` : ne jamais lancer un serveur dans `( a && b & )` — la tâche de fond garde le terminal (et tout `| tail`) bloqué ; séparer les commandes avec `;` et rediriger sortie, erreur et entrée.
- Python 3.10+ requis (Django 5.2). Le Python macOS 3.9 ne suffit pas : `backend/.venv` (Python 3.12) est créé avec `uv`.
- `jsc` (tests front) n'a pas de minuteries : `stub.js` définit `setInterval`/`setTimeout`. `Intl` y fonctionne (fuseaux compris).
- `maturin develop --uv` : `uv` est dans `~/Library/Python/3.9/bin` (à mettre dans le `PATH`), `cargo` dans `~/.cargo/env` (`source ~/.cargo/env`).
- `CheckConstraint(condition=...)` est la syntaxe Django 5.1+ ; Django 4.2 attend `check=`.
- Le CORS est ouvert uniquement si `DJANGO_DEBUG=1`.

## À faire
jours fériés, invalidation des jetons JWT après changement de mot de passe, limitation de débit par compte (pas seulement par IP), WebSocket si la relève de 15 s ne suffit plus, vérification de Docker/CI/PostgreSQL (jamais exécutés sur cette machine), mise en production (HTTPS, sauvegardes).
