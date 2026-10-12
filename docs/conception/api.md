# API REST

Base : `/api`. Authentification : `Authorization: Bearer <access token>`. Erreurs : 400 (validation), 401, 403 (rôle insuffisant), 404 (ressource inconnue **ou projet non accessible**).

| Méthode | Route | Rôle requis | Description |
|---|---|---|---|
| POST | `/auth/register/` | public | Créer un compte |
| POST | `/auth/token/` | public | Obtenir `access` + `refresh` |
| POST | `/auth/refresh/` | public | Renouveler l'`access` |
| GET | `/me/` | connecté | Utilisateur courant |
| GET, POST | `/projects/` | connecté | Mes projets / créer (le créateur devient propriétaire) |
| GET | `/projects/{id}/` | membre | Détail (inclut `role`) |
| PATCH, DELETE | `/projects/{id}/` | propriétaire | Modifier / supprimer |
| GET | `/projects/{id}/members/` | membre | Liste des membres |
| POST | `/projects/{id}/members/` | propriétaire | Ajouter `{identifier, role}` (nom ou email) |
| PATCH | `/projects/{id}/members/{user_id}/` | propriétaire | Changer le rôle |
| DELETE | `/projects/{id}/members/{user_id}/` | propriétaire, ou soi-même | Retirer / quitter |
| GET | `/projects/{id}/invites/` | propriétaire | Liens d'invitation actifs (`id, role, expires_at, max_uses, uses`) ; jamais le jeton |
| POST | `/projects/{id}/invites/` | propriétaire | Créer un lien `{role: member\|viewer, days: 1\|7\|30, max_uses: 1..100}` → renvoie **une seule fois** `token` (20 liens actifs au plus) |
| DELETE | `/projects/{id}/invites/{iid}/` | propriétaire | Révoquer un lien |
| GET | `/projects/{id}/member-candidates/?q=` | propriétaire | Comptes dont le nom **commence par** `q` (« @ » initial ignoré, 1 caractère min., 8 résultats, hors membres actuels) ; limité à 60/min |
| GET | `/invites/{jeton}/` | public (limité à 30/min) | Aperçu `{project_name, role, inviter}` ; **404 identique** si le jeton est inconnu, expiré, révoqué ou épuisé |
| POST | `/invites/{jeton}/accept/` | connecté | Rejoindre le projet → `{project_id, project_name, already_member}` ; un membre existant n'est ni rétrogradé ni compté |
| GET | `/projects/{id}/tasks/` | membre | Liste. Filtres : `status`, `assignee`, `due_after`, `due_before` |
| POST | `/projects/{id}/tasks/` | propriétaire, membre | Créer |
| GET, PATCH, DELETE | `/projects/{id}/tasks/{tid}/` | lecture : tous ; écriture : propriétaire, membre | Détail / modifier / supprimer |
| GET, POST | `/projects/{id}/tasks/{tid}/comments/` | lecture : tous ; écriture : propriétaire, membre | Commentaires |
| GET | `/projects/{id}/insights/` | membre | Avancement, fin prévue, retard, chemin critique, risques, charge par membre, **`team`** (par membre : `state`, `late[]`, `current[]`, `upcoming[]`, avancement) `unassigned` et **`stats`** (`status_counts`, `priority_counts`, `burnup` sur 30 jours, `velocity`, `recent_done`, `due_soon`) |
| GET | `/dashboard/` | connecté | **Tableau de bord personnel** : `kpis`, `focus[]` (mes tâches en retard/du jour), `week[]` (7 jours), `projects[]` (santé, avancement, fin prévue), `alerts[]` (collègues en retard), `done_series[]` (14 jours). Ne couvre que mes projets |
| POST | `/projects/{id}/replan/` | propriétaire, membre | Rattrape le retard (tâches en retard redémarrées aujourd'hui, successeurs décalés) |
| GET | `/health/` | public | Sonde de santé : `{status, planning_engine: "rust"\|"python"}` |

Champs de tâche ajoutés : `start_date`, `due_date`, `is_milestone`, `dependencies` (ids des prérequis). Une modification de date ou de dépendance repousse automatiquement les successeurs ; les boucles, les dépendances inter-projets et `start_date > due_date` sont refusées (400).

## Calendrier et fuseaux horaires (connecté)
| Méthode | Route | Description |
|---|---|---|
| GET | `/calendar/?from=AAAA-MM-JJ&to=AAAA-MM-JJ[&project=id][&mine=1]` | `{timezone, events[], tasks[]}` pour la période (62 jours max). Les **jours** sont ceux du fuseau du profil. `events` : mes événements personnels + ceux de mes projets ; `tasks` : tâches de mes projets dont les dates touchent la période (`mine=1` : seulement celles qui me sont assignées) |
| GET, POST | `/events/` | Lister (visibles) / créer `{title, starts_at, ends_at, timezone?, project?, description?}` |
| GET, PATCH, DELETE | `/events/{id}/` | Détail / modifier / supprimer. Personnel : son créateur seul. De projet : lecture pour tous les membres, écriture propriétaire et membre (403 pour un lecteur, 404 hors projet) |
| GET, PATCH | `/me/` | Le compte + `timezone` et `secondary_timezone` (noms IANA, validés : 400 si inconnus). Seuls les fuseaux sont modifiables |

**Règle des dates-heures** : une valeur *avec* décalage (`2026-10-07T11:00:00-04:00`) est prise telle quelle ; une valeur *sans* décalage (`2026-10-07T11:00`) est l'heure murale du fuseau `timezone` de la requête (à défaut, celui du profil). Tout est stocké et renvoyé comme instant ; l'affichage dans le fuseau voulu est fait par le client (`Intl`). Heure inexistante (saut de printemps) : décalée d'une heure ; heure répétée (retour d'automne) : première occurrence. Durée d'un événement : > 0 et ≤ 31 jours.

## Messagerie et notifications (connecté)
| Méthode | Route | Description |
|---|---|---|
| GET | `/chat/conversations/` | Mes fils : un par projet (créé à la demande) + mes conversations directes. Chaque ligne : `title`, `kind`, `solo` (projet à un seul membre = bloc-notes), `can_write`, `members[]`, `unread`, `last`. Triés par activité |
| POST | `/chat/direct/` | `{user: id ou nom}` → conversation directe (créée si besoin). **404** (même message) si la personne est inconnue, sans projet en commun ou inactive — on ne peut pas deviner quels comptes existent ; 400 avec soi-même |
| GET | `/chat/contacts/` | Personnes avec qui je peux discuter (celles qui partagent un de mes projets) |
| GET | `/chat/conversations/{id}/messages/` | `{messages[], has_more}` — les 50 derniers par défaut ; `?before=id` (page précédente), `?after=id` (nouveautés), `?limit` (≤ 100). 404 si je n'y ai pas accès |
| POST | `/chat/conversations/{id}/messages/` | `{content}` (1 à 2000 caractères). Projet : propriétaire et membre (403 pour un lecteur). Direct : les deux personnes. Calcule les mentions |
| POST | `/chat/conversations/{id}/read/` | Marque le fil comme lu |
| DELETE | `/chat/messages/{id}/` | Auteur, ou propriétaire du projet (fil de projet). 403 sinon, 404 hors accès |
| GET | `/chat/summary/` | `{unread_messages, unread_notifications}` — interrogé toutes les 15 s par le front |
| GET, POST | `/notifications/` | Lister (50 dernières, `read`, `excerpt`, `everyone`) / marquer lues `{ids:[…]}` ou `{all:true}` — uniquement les miennes |

**Mentions** : `@nom` (sans casse) désigne un participant du fil ; `@tous` / `@all` prévient tous les autres dans un fil de projet de 3 personnes ou plus. Un `@` collé à un mot (`jean@x.fr`), un inconnu, un non-participant ou soi-même ne notifie personne. Le contenu est stocké brut : c'est le front qui l'échappe.

## Calendrier — récurrence et invitations
`POST/PATCH /events/` acceptent en plus : `recurrence` (`""`, `daily`, `weekdays`, `weekly`, `monthly`), `recurrence_until` (date), `attendees` (liste d'identifiants, **remplace** la liste des invités ; absent = inchangée). Un événement récurrent dure moins d'un jour. Les réponses ajoutent `invitees[]` (`{id, username, status}`), `my_status` (`organizer | invited | accepted | declined | null`), `occurrence_day`, `series_starts_at`, `series_ends_at`.

| Méthode | Route | Description |
|---|---|---|
| GET | `/calendar/?from&to` | Renvoie les **occurrences** des séries comprises dans la période (une ligne par occurrence, avec `occurrence_day`) ; modifier une occurrence modifie la série (envoyer les horaires `series_*`) |
| POST | `/events/{id}/rsvp/` | `{status: accepted \| declined}` — réservé aux invités (403 sinon, 404 si invisible) |
| POST | `/events/{id}/skip/` | `{day}` — supprime UNE occurrence (204, idempotent ; 400 si ce n'est pas une occurrence) |
| GET | `/calendar/contacts/` | Personnes invitables à un événement personnel (partageant un projet) |

## Messagerie — compléments
| Méthode | Route | Description |
|---|---|---|
| PATCH | `/chat/messages/{id}/` | `{content}` — auteur seulement (403 pour les autres, y compris le propriétaire du projet) ; marque `edited` ; ne renotifie que les nouvelles mentions |
| POST | `/chat/messages/{id}/reactions/` | `{emoji}` parmi 👍 ❤️ 😂 🎉 👀 ✅ — bascule (ajoute / retire) ma réaction ; lecteur : 403 |
| POST | `/chat/conversations/{id}/messages/` | JSON `{content, reply_to?}` **ou** multipart `content`, `reply_to`, `files` (3 au plus, 5 Mo chacun ; images, PDF, TXT, CSV, DOCX, XLSX, PPTX, ODT ; refus si le contenu ne correspond pas à l'extension) |
| GET | `/chat/attachments/{id}/` | Télécharge un fichier (jeton requis, lecteurs du fil seulement) — images en ligne, le reste en téléchargement ; `nosniff`, CSP `sandbox` |
| GET | `/chat/search/?q=&conversation=` | Messages contenant `q` (≥ 2 caractères) dans mes conversations, 30 résultats, plus récents d'abord |
| GET | `/chat/conversations/{id}/messages/?around=id` | Le message visé avec ses 20 précédents et 30 suivants (ouverture d'un résultat de recherche) |

Les messages contiennent maintenant `edited`, `can_edit`, `reply_to {id, author, excerpt}`, `reactions[] {emoji, count, mine, users}`, `attachments[] {id, name, size, content_type, image}` et `tasks[] {id, title, status, project}` (tâches citées par `#id`, **du projet du fil uniquement**). `GET /notifications/` renvoie aussi les invitations (`type: invite`) ; `POST /notifications/` accepte `{ids, invitations}` ou `{all: true}`.

## Gestion de projet — compléments
| Méthode | Route | Description |
|---|---|---|
| PATCH | `/projects/{id}/` | accepte `skip_weekends` (propriétaire) : jours ouvrés |
| POST | `/projects/{id}/transfer/` | `{user_id}` — le propriétaire cède le projet à un membre |
| POST | `/projects/{id}/save-template/` | `{name, description?}` — enregistre la structure comme modèle (propriétaire ; 20 modèles au plus) |
| GET | `/templates/` | modèles fournis (`builtin:site-web`, `evenement`, `sprint`, `lancement`) + les miens |
| DELETE | `/templates/{id}/` | supprimer un de mes modèles (404 pour ceux d'autrui) |
| POST | `/projects/from-template/` | `{template, name?, start_date?}` → projet créé (201) avec tâches, dates et dépendances |
| GET | `/projects/{id}/workload/?weeks=4` | charge par membre et par semaine (`percent`, `days`, `tasks`) + `suggestions[]` de rééquilibrage (1 à 12 semaines) |
| GET | `/projects/{id}/simulate/?delay=3` | pour chaque tâche ouverte : recul de la fin du projet si elle prend `delay` jours de plus (1 à 60) — **calculé par le moteur Rust** |
| GET, POST | `/projects/{id}/tasks/{tid}/time/` | saisies de temps + total ; POST `{minutes, day?, note?}` (1 à 1 440 min) |
| POST | `/projects/{id}/tasks/{tid}/time/start/` | démarre le chrono (arrête celui qui tournait) |
| DELETE | `/projects/{id}/tasks/{tid}/time/{entry}/` | supprimer sa saisie (le propriétaire peut supprimer celles des autres) |
| GET, POST | `/timer/` | mon chrono en cours (ou `null`) ; POST l'arrête |
| GET | `/projects/{id}/time-report/?from&to` | temps passé : total, par membre, par tâche, par jour (30 jours par défaut) |

Les tâches ajoutent `recurrence` (`""`, `daily`, `weekdays`, `weekly`, `monthly`), `recurrence_of` (lecture seule) et `time_minutes` (lecture seule).

## Compte et limitation de débit
| Méthode | Route | Description |
|---|---|---|
| PATCH | `/me/` | `timezone`, `secondary_timezone`, `notify_email`, `digest_email` |
| GET | `/me/export/` | toutes mes données en JSON (téléchargement) |
| DELETE | `/me/` | `{password}` — supprime mon compte (400 si mot de passe faux, dernier administrateur, ou propriétaire d'un projet partagé) |

**429** quand une limite est dépassée : `login` 10/min par adresse IP, `register` 10/h, `chat` 60/min (écritures seulement), `account` 10/h (export, suppression). Réglables par variables d'environnement.

## Administration (`/api/admin/…` — comptes `is_staff` actifs uniquement : 401 sans connexion, 403 sinon)
| Méthode | Route | Description |
|---|---|---|
| GET | `/admin/stats/` | Comptes (actifs, désactivés, admins, nouveaux, connectés 30 j), projets, tâches, commentaires, inscriptions par semaine, derniers inscrits, état des réglages |
| GET | `/admin/users/?q=&filter=active\|inactive\|admin` | Liste (projets, tâches ouvertes, dernière connexion) |
| POST | `/admin/users/` | Créer `{username, email, password?, is_staff?}` → `generated_password` si aucun mot de passe fourni (**affiché une seule fois**) |
| GET | `/admin/users/{id}/` | Détail + `owned_projects[]` |
| PATCH | `/admin/users/{id}/` | `{email?, is_active?, is_staff?}` — seuls les champs envoyés changent |
| POST | `/admin/users/{id}/reset-password/` | `{password?}` → `generated_password` si omis |
| DELETE | `/admin/users/{id}/?transfer_to=ID&delete_solo=1` | Supprime. **409** + `owned_projects[]` s'il possède des projets sans repreneur. `delete_solo=1` supprime ses projets où il est seul |
| GET | `/admin/projects/?q=` | Tous les projets (propriétaire, membres, tâches, avancement) |
| DELETE | `/admin/projects/{id}/` | Supprime le projet et son contenu |
| POST | `/admin/projects/{id}/transfer/` | `{user_id}` — nouveau propriétaire (l'ancien reste membre) |
| GET | `/admin/audit/?limit=&action=user\|project\|settings` | Journal d'audit, du plus récent au plus ancien |
| GET, PATCH | `/admin/settings/` | `{allow_registration}` |
| GET | `/auth/config/` | **Public** : `{registration_open}` (masque l'inscription sur l'écran de connexion) |

Règles : impossible de se désactiver / supprimer / retirer ses droits (400) ; au moins un admin actif doit rester (400) ; seul un superutilisateur modifie un superutilisateur (403). Codes d'action du journal : `user.create|update|activate|deactivate|promote|demote|password_reset|delete`, `project.delete|transfer`, `settings.update`.
