# Correspondance référentiel CDA ↔ preuves dans TaskFlow

Intitulés simplifiés : à vérifier mot pour mot avec le référentiel officiel du titre (fiche RNCP) et le livret fourni par ton certificateur.

| Bloc | Compétence | Preuve dans le projet |
|---|---|---|
| 1 | Installer et configurer son environnement de travail | README (démarrage), `docker-compose.yml`, `.env.example` |
| 1 | Développer des interfaces utilisateur | `frontend/` : calendrier, tableau, panneau, modales, thèmes |
| 1 | Développer des composants métier | `projects/services.py`, `tasks/services.py` |
| 1 | Contribuer à la gestion d'un projet informatique | `docs/conception/cahier-des-charges.md` (planning, priorités MoSCoW), historique Git |
| 2 | Analyser les besoins et maquetter une application | cahier des charges, cas d'utilisation, inspiration Notion Calendar |
| 2 | Définir l'architecture logicielle | architecture en couches (README), diagramme de déploiement |
| 2 | Concevoir et mettre en place une base de données | MCD/MLD (`modele-donnees.md`), `*/models.py`, migrations, contraintes |
| 2 | Développer des composants d'accès aux données | ORM Django, filtres de requête (`TaskViewSet.get_queryset`) |
| 3 | Préparer et exécuter les plans de tests | `*/tests.py`, `docs/tests/plan-de-tests.md` |
| 3 | Préparer et documenter le déploiement | `docs/deploiement`, Dockerfiles, compose |
| 3 | Contribuer à la mise en production (DevOps) | `.github/workflows/ci.yml` |
| 1 | Développer des composants métier complexes | `tasks/planning.py` : cascade, CPM, prévision, risques (algorithmique de graphes, tests dédiés) |
| 1 | Développer des interfaces riches | `frontend/js/gantt.js` + interactions (glisser-déposer, redimensionnement, SVG) |
| 2 | Gérer la complexité temporelle (fuseaux, heure d'été) | `agenda/services.py`, `frontend/js/tz.js` : stockage UTC, conversion d'heures murales, jours vus depuis le fuseau de l'utilisateur, tests des changements d'heure |
| 2 | Concevoir une messagerie temps quasi réel (sans WebSocket) | `chat/` : fils projet/direct, non-lus, relève toutes les 15 s, pagination par curseur |
| 2 | Gérer droits et notifications sur des données partagées | `chat/services.py` : mentions limitées aux participants, 404 plutôt que 403, tests `chat/tests.py` |
| 1 | Tests de bout en bout dans un navigateur réel | `e2e/test_e2e.py` (Selenium + Firefox) : glisser-déposer, messagerie à deux comptes, chrono, modèles ; job CI dédié |
| 2 | Calcul haute performance et validation d'équivalence | `delay_impacts` (Rust, ×110) comparé à la version Python sur ~1 600 graphes aléatoires |
| 2 | Sécuriser des téléversements | `chat/services._check_file` : liste blanche, vérification des octets, nom aléatoire, téléchargement authentifié |
| 2 | Conformité RGPD (accès, portabilité, effacement) | `accounts/account_services.py`, export JSON, suppression avec garde-fous, trace d'audit |
| 2 | Limitation de débit et protection contre la force brute | `taskflow/throttles.py`, tests de dépassement |
| 2 | Notifications multi-canaux | `accounts/emails.py` (e-mails, résumé planifié), notifications du navigateur, cloche in-app |
| 1 | Application installable (PWA) | `frontend/sw.js`, manifeste, icônes |
| 1 | Concevoir une interface de calendrier | `frontend/js/calendar.js` : grille horaire jour/semaine, mois, chevauchements, deux fuseaux côte à côte |
| 1 | Concevoir une interface orientée suivi d'équipe | vue Équipe (`frontend/js/team.js`), indicateurs de retard par membre |
| 1 | Concevoir des visualisations de données | `frontend/js/charts.js`, `dashboard.js` : graphiques SVG sans bibliothèque |
| 2 | Concevoir des requêtes d'agrégation | `planning.stats`, `planning.user_dashboard` (séries temporelles, isolation par membre) |
| 2 | Concevoir une application multi-rôles avec administration | `accounts/admin_*.py`, `frontend/js/admin.js` : permissions, garde-fous, audit |
| 3 | Garantir l'intégrité des données lors de suppressions | transactions, transfert de propriété, anonymisation (`delete_user`) |
| 2 | Choisir et intégrer une technologie adaptée (polyglotte) | module Rust via PyO3 (`planning_rs/`), frontière FFI, repli automatique, décision argumentée par des mesures (`moteur-rust.md`) |
| 3 | Garantir la non-régression entre deux implémentations | `tasks/test_engine.py` (tests différentiels sur graphes aléatoires), matrice CI |
| Transverse | Sécurité | `docs/securite/README.md` |
