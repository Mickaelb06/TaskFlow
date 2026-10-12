# Cahier des charges — TaskFlow

## 1. Contexte et besoin
Les outils de gestion de tâches sont soit trop simples (listes) pour un travail d'équipe, soit trop lourds pour un indépendant. TaskFlow propose un outil **unique, du projet solo à la petite équipe**, centré sur la **planification** : un diagramme de Gantt avec dépendances, des indicateurs de risque calculés, et une aide à la planification par IA. Les vues liste, tableau et calendrier complètent l'ensemble.

> À personnaliser : le besoin concret qui a motivé le projet.

## 2. Utilisateurs et rôles
| Rôle | Droits |
|---|---|
| Administrateur | gère tous les comptes, tous les projets, les réglages ; ne voit pas le contenu d'un projet dont il n'est pas membre (hors compteurs) |
| Propriétaire | tout : paramètres du projet, membres et rôles, tâches, suppression du projet |
| Membre | créer, modifier, assigner, supprimer des tâches ; commenter |
| Lecteur | consulter uniquement |

Un projet à un seul membre est un projet **solo**.

## 3. Besoins fonctionnels
| Réf | Besoin | Priorité |
|---|---|---|
| F1 | S'inscrire, se connecter, rester connecté (JWT + refresh) | Must |
| F2 | Créer / modifier / supprimer un projet | Must |
| F3 | Inviter, changer le rôle, retirer un membre ; quitter un projet | Must |
| F4 | Créer / modifier / supprimer une tâche (titre, description, statut, priorité, échéance, assigné) | Must |
| F5 | Vue liste : regroupement par échéance ou statut, terminer d'un clic, ajout rapide, filtres (assigné, priorité) | Must |
| F6 | Vue tableau par statut (kanban) | Must |
| F11 | Gantt : barres déplaçables/redimensionnables, jalons, ligne d'échéance, zoom | Must |
| F12 | Dépendances entre tâches avec propagation automatique des décalages et détection des boucles | Must |
| F13 | Indicateurs : avancement, fin prévue vs échéance, retards, charge par membre | Must |
| F14 | Chemin critique (CPM) mis en évidence | Should |
| F15 | « Rattraper le retard » : replanification des tâches en retard | Should |
| F19 | Tableau de bord personnel : tâches du jour et en retard (terminables d'un clic), 7 prochains jours, productivité, santé de mes projets, alertes sur les collègues en retard | Must |
| F20 | Synthèse de projet : avancement dans le temps, répartition, vélocité, charge par membre, échéances, risques, dernières tâches terminées | Must |
| F21 | Administration des utilisateurs : liste/recherche, création (mot de passe généré ou choisi), modification, rôle admin, réinitialisation du mot de passe, désactivation, suppression avec reprise des projets | Must |
| F22 | Administration des projets : vue globale, transfert de propriété, suppression | Must |
| F23 | Journal d'audit des actions d'administration | Must |
| F24 | Réglages globaux : inscriptions publiques | Should |
| F25 | Garde-fous : aucun verrouillage possible de l'administration (auto-suppression, dernier admin) | Must |
| F26 | Moteur de planification haute performance (Rust) avec repli automatique et vérification d'équivalence avec la version de référence | Could |
| F18 | Vue Équipe : tâches en cours, en retard (jours de retard), à venir et statut de chaque membre ; tâches sans responsable signalées | Must |
| F5b | Calendrier façon Notion Calendar (jour / semaine / mois) : événements à l'heure + tâches à la journée, création par clic, filtre par projet | Must |
| F28 | Messagerie interne : un fil par projet (équipe) ou bloc-notes personnel (projet solo), conversations directes entre collègues, messages datés dans le fuseau de l'utilisateur, suppression par l'auteur (ou le propriétaire du projet), historique paginé | Must |
| F29 | Mentions `@nom` et `@tous` → notifications (cloche + page dédiée), pastilles de messages non lus ; aucune mention possible hors des participants | Must |
| F30 | Barre latérale repensée : navigation principale (tableau de bord, calendrier, messages), projets avec pastilles, administration/thème/déconnexion en pied, repliable | Should |
| F31 | Calendrier interactif : déplacer, redimensionner et créer des événements à la souris ; événements récurrents (jour, jours ouvrés, semaine, mois) ; suppression d'une occurrence ou de la série | Must |
| F32 | Invitations à un événement avec réponse (accepter / refuser) et notification | Should |
| F33 | Messagerie enrichie : réponse citée, modification, réactions, pièces jointes (3 × 5 Mo, contenu vérifié), recherche, citation de tâche par `#` | Should |
| F34 | Jours ouvrés par projet (durées et décalages sans week-ends) | Should |
| F35 | Tâches récurrentes : la suivante est créée à la fin de la précédente | Should |
| F36 | Charge d'équipe par semaine avec propositions de rééquilibrage ; simulation de retard « et si ? » (module Rust) | Should |
| F37 | Suivi du temps : chrono unique, saisie manuelle, synthèse par membre | Should |
| F38 | Modèles de projet (fournis et personnels) | Could |
| F39 | Compte : export des données (RGPD), suppression par l'utilisateur, cession de propriété de projet | Must |
| F40 | Notifications : e-mails (mention, invitation), résumé du matin, notifications du navigateur, préférences | Should |
| F41 | Limitation de débit (connexion, inscription, messages, compte) | Must |
| F42 | Application installable (PWA), démarrage hors connexion | Could |
| F27 | Fuseaux horaires : fuseau principal par utilisateur, second fuseau en colonne d'heures, événement saisi dans n'importe quel fuseau, heure d'été gérée | Must |
| F7 | Glisser-déposer : changer l'échéance ou le statut | Should |
| F8 | Commentaires sur une tâche | Should |
| F9 | Thème clair / sombre, raccourcis clavier | Could |
| F10 | Notifications d'échéance par email | Won't (v1) |

## 4. Besoins non fonctionnels
- **Sécurité** : OWASP Top 10, isolation stricte des données entre projets (voir `docs/securite`).
- **Performance** : liste des tâches d'un projet < 300 ms pour 1 000 tâches.
- **Exactitude des dates** : les calculs de dates sont déterministes et testés ; les instants sont stockés en UTC et convertis à l'affichage (changement d'heure compris).
- **Maintenabilité** : architecture en couches, tests automatisés, CI.
- **Accessibilité** : navigation clavier, contrastes, libellés ARIA sur les boutons icônes.
- **RGPD** : données minimales (nom d'utilisateur, email) ; export et suppression de son compte par l'utilisateur (F39) ; messages et commentaires conservés sous « Utilisateur supprimé ».
- **Portabilité** : déploiement reproductible avec Docker Compose.

## 5. Contraintes techniques
Python / Django / PostgreSQL, front sans framework, API REST JSON.

## 6. Hors périmètre v1
Application mobile, notifications, pièces jointes, sous-tâches, récurrence, jours ouvrés et calendriers de congés (le moteur compte en jours calendaires), planification des ressources par capacité.

## 7. Planning
| Jalon | Contenu | État |
|---|---|---|
| J1 | Conception : CDC, UML, MCD | ✔ |
| J2 | API : comptes, projets, membres, tâches, commentaires | ✔ |
| J3 | Front : calendrier, tableau, panneau de détail | ✔ |
| J4 | Gestion de projet : Gantt, dépendances, indicateurs, calendrier | ✔ |
| J5 | Tests bout en bout du front, rate limiting de la connexion | à faire |
| J6 | Déploiement + documentation finale | à faire |
