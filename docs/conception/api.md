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
