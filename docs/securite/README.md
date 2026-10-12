# Sécurité

| Risque (OWASP) | Mesure dans TaskFlow | Où |
|---|---|---|
| Contrôle d'accès défaillant | Chaque requête vérifie l'appartenance au projet (404 sinon) puis le rôle (403) ; règles dupliquées dans la couche service | `projects/mixins.py`, `*/services.py` |
| Injection SQL | ORM Django (requêtes paramétrées), aucune SQL brute | `models.py` |
| XSS | Tout contenu utilisateur échappé avant affichage ; l'API ne renvoie que du JSON | `frontend/js/app.js` (`esc()`) |
| Authentification | JWT à durée limitée + refresh ; mots de passe hachés (PBKDF2) et validés (longueur, mots courants) | `settings.py`, `accounts/` |
| Exposition de données | Mot de passe jamais renvoyé ; liste des projets limitée à ceux de l'utilisateur | serializers, `get_queryset` |
| Mauvaise configuration | Secrets en variables d'environnement ; `.env` ignoré par Git ; CORS restreint hors mode debug | `settings.py`, `.gitignore` |
| Énumération d'utilisateurs | Ajout de membre réservé au propriétaire ; accès à un projet tiers = 404 | `services.add_member` |
| Fuseau horaire falsifié (chemin, texte libre) | Nom IANA validé par `zoneinfo` avant stockage (400 sinon) ; `zoneinfo` refuse les chemins (`../etc/passwd` testé) | `accounts/timezones.py`, `agenda/tests.py` |
| Injection HTML dans les messages (XSS) | Contenu stocké brut, **échappé à l'affichage** (`esc()` avant `innerHTML`) ; les mentions sont ajoutées après échappement, à partir d'un motif sans guillemet ni chevron | `frontend/js/chat.js`, `tests/chat.test.js` |
| Lecture des conversations d'autrui | Chaque accès est filtré par appartenance (projet ou paire) ; 404 sinon, pour ne pas révéler l'existence | `chat/services.py::conversation_for` |
| Sondage des comptes via les messages directs | Écrire exige un projet en commun ; réponse **identique** (404) pour « inconnu » et « sans projet en commun » | `services.direct_with`, `chat/tests.py` |
| Notifications détournées | Chacun ne lit et ne marque que les siennes ; on ne peut mentionner que les participants du fil | `NotificationsView`, `parse_mentions` |
| Fuite d'événements d'autrui | Requêtes filtrées par appartenance (`visible_events`) : 404 hors projet, événement personnel invisible aux autres | `agenda/services.py` |
| Élévation de privilèges / administration | Droits `is_staff` vérifiés **côté serveur** sur chaque route (le masquage des boutons n'est qu'ergonomique) ; un admin ne peut pas se verrouiller (auto-suppression, dernier admin) ni toucher un superutilisateur ; pas de création de superutilisateur via l'API | `accounts/permissions.py`, `admin_services.py` |
| Traçabilité | Journal d'audit de chaque action (qui, quoi, cible, détail), conservé même si l'acteur est supprimé ; jamais de mot de passe | `AuditLog` |
| Mots de passe générés | `secrets.token_urlsafe`, renvoyés une seule fois, jamais stockés ni journalisés ; mots de passe choisis validés (longueur, mots courants) | `generate_password` |
| Départ d'un utilisateur / RGPD | Désactivation (données conservées) ou suppression réelle ; les commentaires sont anonymisés plutôt que supprimés ; les projets ne sont jamais orphelins (repreneur obligatoire) | `delete_user` |
| Fermeture des inscriptions | Réglage global appliqué côté serveur (403) | `SiteSettings` |
| Module natif (Rust) | Aucun `unsafe` dans le code du projet ; entrées issues de la base uniquement ; boucle de dépendances = erreur (garde-fou d'itérations) ; `Cargo.lock` versionné ; une seule dépendance directe | `planning_rs/` |

## Limites connues / à faire
- Pas de limitation de débit (rate limiting) sur la connexion.
- Jetons JWT stockés en `localStorage` (exposés en cas de XSS) — alternative : cookies HttpOnly.
- `DJANGO_DEBUG=0`, `SECRET_KEY` forte et HTTPS obligatoires en production.
- Un utilisateur ne peut pas supprimer lui-même son compte (seul un admin le peut) ; pas d'export de ses données (RGPD : droit d'accès/portabilité).
- Les jetons JWT déjà émis restent valides jusqu'à expiration après un changement de mot de passe (ils sont en revanche rejetés immédiatement si le compte est désactivé).
- Pas d'audit automatique des dépendances Rust (`cargo audit`) ni Python (`pip-audit`) en CI.
- Pas d'authentification à deux facteurs pour les administrateurs.
- Aucune donnée n'est envoyée à un service tiers : l'application n'appelle aucune API externe (les polices du site viennent de Google Fonts, à héberger localement si la confidentialité l'exige).
