# TaskFlow — gestion de projet et de tâches, solo ou en équipe

Projet support de la VAE **Concepteur Développeur d'Applications** (RNCP niveau 6).

Application web permettant de gérer des tâches seul ou en équipe : projets, membres et rôles, tâches (statut, priorité, échéance, assignation), commentaires.

## Fonctionnalités
**Administration** (comptes `is_staff`, entrée « Administration » du menu)
- **Utilisateurs** : recherche et filtres, création (mot de passe choisi ou généré, affiché une seule fois), modification, droits admin, réinitialisation du mot de passe, désactivation / réactivation, suppression
- **Suppression sûre** : un utilisateur qui possède des projets ne peut être supprimé qu'après désignation d'un repreneur (ou suppression de ses projets solo) ; confirmation par saisie du nom ; ses commentaires restent, signés « Utilisateur supprimé »
- **Projets** : liste de tous les projets (propriétaire, membres, avancement), transfert de propriété, suppression
- **Journal d'audit** : qui a fait quoi et quand — jamais de mot de passe
- **Réglages** : ouvrir/fermer les inscriptions publiques
- Garde-fous : impossible de se supprimer / se désactiver / se retirer ses droits, de supprimer le dernier admin actif, ou de toucher à un superutilisateur sans l'être soi-même

**Calendrier** (entrée « Calendrier » du menu, façon Notion Calendar)
- Vues **jour / semaine / mois** : grille horaire avec ligne « maintenant », événements à l'heure (blocs côte à côte quand ils se chevauchent), tâches de tous vos projets posées à la journée
- **Fuseaux horaires** : un fuseau principal par utilisateur, un **second fuseau en colonne d'heures**, et chaque événement peut être saisi dans n'importe quel fuseau (« 11 h à Montréal » s'affiche à 17 h à Paris) ; stockage en UTC, heure d'été gérée
- Événements **personnels** (vous seul) ou **de projet** (partagés avec les membres, lecture seule pour les lecteurs) ; filtre par projet et « mes tâches » ; clic dans la grille pour créer

**Messagerie** (entrée « Messages » du menu, touche `I`)
- Un **fil par projet** : en équipe, la discussion du projet ; si vous êtes seul(e) dans le projet, c'est votre **bloc-notes** personnel
- **Messages directs** entre collègues (personnes qui partagent un projet)
- **Mentions** : `@` ouvre la liste des participants (flèches + Entrée), `@tous` prévient toute l'équipe ; la personne reçoit une **notification** (cloche 🔔) et une pastille sur le fil et sur le projet
- Pastilles de non-lus, historique paginé, heures dans votre fuseau, suppression de ses messages (le propriétaire du projet peut modérer) ; lecteurs en lecture seule ; mise à jour automatique toutes les 15 s

**Tableaux de bord**
- **Tableau de bord personnel** (page d'accueil) : mon focus du jour (je coche une tâche directement), mes 7 prochains jours, ma productivité sur 14 jours, la santé de chacun de mes projets, et des alertes sur les collègues en retard — tous projets confondus
- **Synthèse de projet** (onglet par défaut d'un projet) : avancement dans le temps (tâches créées / terminées sur 30 jours), répartition par statut et priorité, vélocité hebdomadaire, charge et retard de chaque membre, échéances de la semaine, risques, dernières tâches terminées

**Gestion de projet**
- **Diagramme de Gantt** interactif : barres déplaçables et redimensionnables, jalons, flèches de dépendance, ligne d'échéance
- **Dépendances** entre tâches : si une tâche est repoussée, celles qui en dépendent suivent automatiquement (jamais l'inverse)
- **Chemin critique** (méthode CPM) : les tâches dont le retard décale la fin du projet
- **Indicateurs calculés** : avancement pondéré par la durée, fin prévue vs échéance, retards, charge par membre, risques détectés
- **Vue Équipe** : pour chaque membre, ce sur quoi il travaille en ce moment, ce qui est en retard (et de combien de jours), ce qui arrive, sa charge, et un statut (en retard / surchargé / dans les temps / disponible) ; les tâches sans responsable sont signalées
- **« Rattraper le retard »** : replanifie en un clic les tâches en retard et leurs successeurs

**Tâches et équipe**
- Comptes (JWT), projets **solo** ou **en équipe** (propriétaire / membre / lecteur), invitations par nom ou email
- Vues Synthèse, Gantt, Équipe, Liste et Tableau (kanban) ; glisser-déposer ; commentaires ; thème clair/sombre
- Barre latérale repliable : navigation principale, projets avec pastilles, administration / thème / déconnexion en pied
- Raccourcis : `H` tableau de bord, `C` calendrier, `I` messages ; dans un projet `D` `G` `E` `L` `B` (Synthèse, Gantt, Équipe, Liste, Tableau), `N` nouvelle tâche ; dans le calendrier `D` `W` `M` (jour, semaine, mois), `T` aujourd'hui, `N` nouvel événement, `←` `→`

## Stack
| Couche | Technologie |
|---|---|
| Front | HTML / CSS / JavaScript (modules ES, sans framework ni build) |
| API | Python 3.12 + Django 5.2 + Django REST Framework |
| Base de données | PostgreSQL + migrations Django |
| Authentification | JWT (djangorestframework-simplejwt) |
| Tests | Django TestCase / DRF APITestCase |
| Moteur de calcul | **Rust** (PyO3, module `taskflow_planning`) avec repli automatique sur Python — voir [docs/conception/moteur-rust.md](docs/conception/moteur-rust.md) |
| Déploiement | Docker Compose (db, api, web/nginx) + GitHub Actions |

## Architecture
`navigateur (SPA) → API REST → views (ViewSet) → services (règles métier) → planning.py (moteur) / models (ORM) → PostgreSQL`
`tasks/planning.py` : moteur de planification déterministe (cascade, CPM, prévision, risques).
`chat/` : messagerie, mentions, notifications ; `frontend/js/chat.js` : mentions et rendu des messages.
`agenda/` : calendrier (événements, fuseaux horaires) ; `frontend/js/tz.js` et `calendar.js` : conversion d'heures et grille horaire.
Les serializers valident les entrées/sorties ; les permissions par rôle sont vérifiées côté serveur.

## Démarrage rapide (Docker)
```bash
cp .env.example .env
docker compose up --build
# application : http://localhost:8080
```

## Démarrage en développement
```bash
cp .env.example .env
docker compose up -d db
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Python 3.10+ requis
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver                 # API : http://localhost:8000
# dans un autre terminal :
cd frontend && python3 serve.py 5173 # front : http://localhost:5173 (sans cache ; /admin ouvre l'administration)
```
Module Rust (optionnel, recommandé) : `cd backend && pip install maturin && export PYO3_PYTHON="$PWD/.venv/bin/python" && maturin develop --release --uv -m planning_rs/Cargo.toml` (nécessite [Rust](https://rustup.rs)). Sans lui l'application fonctionne avec la version Python.
Tests : `cd backend && python manage.py test` (158 tests, aucun appel réseau ; `TASKFLOW_PLANNING_BACKEND=python` pour tester le repli) ; `cd backend/planning_rs && cargo test --lib` (7 tests Rust) ; `python bench_planning.py` (mesures Rust/Python)
Données de démo : `python manage.py seed_demo` (comptes `demo` (propriétaire des projets **et** administrateur : voit toutes les vues), `lea`, `sam` — mot de passe `demo-taskflow-2026` ; compte `admin` / `admin-taskflow-2026` = administrateur seul, sans projet : n'affiche que l'administration — **à changer en production**)
Front : `./test-front.sh` (145 vérifications sur un faux navigateur, macOS). Premier administrateur en production : `python manage.py createsuperuser`.
Lancement local : `./start.sh` (démarre API + front, ouvre le navigateur) ; `./start.sh stop`.

## Documentation
- [Cahier des charges](docs/conception/cahier-des-charges.md)
- [Modèle de données et UML](docs/conception/modele-donnees.md)
- [API REST](docs/conception/api.md)
- [Module Rust](docs/conception/moteur-rust.md)
- [Plan de tests](docs/tests/plan-de-tests.md)
- [Sécurité](docs/securite/README.md)
- [Déploiement](docs/deploiement/README.md)
- [Correspondance référentiel CDA](docs/referentiel-cda.md)
