# Plan de tests

## Stratégie
- **Tests d'API automatisés** (DRF `APITestCase`, base isolée) : 338 tests (+ 8 tests Rust), exécutés à chaque push par la CI.
- **Tests du front** sur un faux navigateur (204 vérifications) et **tests de bout en bout dans un vrai navigateur** (Firefox + Selenium, 33 scénarios, job CI dédié).
- **Tests manuels** du front selon les scénarios ci-dessous (ce que l'automatisation ne juge pas : la qualité visuelle).
- Priorité aux **règles métier et aux droits**, là où les régressions sont les plus graves.

## Exécution
```bash
cd backend && python manage.py test        # 338 tests (~15 s)
cd backend/planning_rs && cargo test --lib  # 8 tests Rust
./test-front.sh                              # 204 vérifications (faux navigateur, macOS)
./test-e2e.sh                                # 33 scénarios Firefox + Selenium (pip install selenium)
```

## Cas de test automatisés
| Domaine | Cas | Résultat attendu |
|---|---|---|
| Comptes | inscription → connexion → `/me/` | 201, 200, nom correct |
| Comptes | mot de passe faible / email en doublon (casse différente) | 400 |
| Projets | création | créateur = propriétaire |
| Invitations | lien créé par le propriétaire : jeton non stocké, absent de la liste ; réservé au propriétaire (403 membre, 404 étranger) | 201 ; seule l'empreinte en base |
| Invitations | accepter un lien : rôle du lien, compteur d'usages ; membre existant ni rétrogradé ni compté ; sans compte | 200 ; 401 sans compte |
| Membres | recherche par `@nom` : préfixe, casse, « @ » ignoré, 1 caractère = rien, comptes désactivés et membres exclus, propriétaire seulement, 8 résultats max., limite de débit | 200 ; 403/404 ; 429 |
| Invitations | lien épuisé, expiré, révoqué ou inconnu ; révocation du lien d'un autre projet ; plafond de liens actifs ; aperçu limité en débit | 404 identique ; 404 ; 400 ; 429 |
| Projets | liste d'un utilisateur sans projet | vide (isolation) |
| Projets | modification / suppression par un simple membre | 403 |
| Membres | ajout par nom, par email (casse ignorée), avec rôle lecteur | 201 |
| Membres | utilisateur inconnu, doublon, second propriétaire | 400 |
| Membres | gestion par un non-propriétaire | 403 |
| Membres | changement de rôle, retrait ; départ volontaire ; propriétaire qui part | 200/204 ; 400 |
| Tâches | priorité par défaut = 2 ; priorité 9 | 201 ; 400 |
| Tâches | non-membre | 404 |
| Tâches | non authentifié | 401 |
| Tâches | lecteur : lecture OK, écriture | 200 ; 403 |
| Tâches | assigné hors projet | 400 |
| Tâches | filtres calendrier (`due_after/before`) et statut | résultats filtrés |
| Tâches | retrait d'un membre | ses tâches deviennent non assignées |
| Commentaires | membre commente, lecteur lit ; lecteur commente | 201 ; 403 |
| Commentaires | tâche d'un autre projet | 404 |

| Planification | décalage en cascade ; jamais d'avance ; tâches terminées intactes | dates des successeurs |
| Planification | chemin critique sur un graphe connu | A→B→D, pas C |
| Planification | boucle de dépendances, auto-dépendance, dépendance inter-projets, début > fin | 400 |
| Planification | prévision de fin avec retard propagé ; écart à l'échéance | dates et jours exacts |
| Planification | risques (retard, bloquée, non assignée, échéance dépassée) ; avancement pondéré | indicateurs |
| Planification | replanification des retards (bug trouvé et corrigé par ce test) | redémarrage aujourd'hui + cascade |
| Historique | `completed_at` posée, conservée, effacée à la réouverture ; non falsifiable par le client | dates |
| Synthèse | répartition, courbe créées/terminées jour par jour, vélocité 2 semaines, récentes, échéances | chiffres exacts |
| Synthèse | santé d'un projet (done / empty / late / risk / ok) | état |
| Tableau de bord perso | buckets en retard / aujourd'hui / à venir / sans date ; tâches des autres exclues | KPI et listes |
| Tableau de bord perso | cartes projet, alertes sur collègues (pas sur soi), isolation entre utilisateurs, 401 sans connexion | données |
| Admin — accès | 401 sans connexion, 403 pour un utilisateur normal sur **chaque** route admin (lecture et écriture) ; admin désactivé refusé | codes HTTP, rien de modifié |
| Admin — utilisateurs | liste, recherche, filtres, compteurs ; création (mot de passe choisi / généré / validation / doublons casse ignorée / pas de superuser via l'API) | 201 ou 400 |
| Admin — utilisateurs | compte désactivé : connexion refusée **et jeton existant rejeté** ; réactivation | 401 puis 200 |
| Admin — utilisateurs | modifier email / promouvoir / rétrograder ; un champ absent ne modifie rien (régression trouvée par ce test) | valeurs |
| Admin — sécurité | pas d'action sur soi ; dernier admin protégé ; superutilisateur protégé (403) | 400 / 403 |
| Admin — mots de passe | réinitialisation générée ou choisie, ancien mot de passe invalidé, faible refusé, `last_login` mis à jour | connexions |
| Admin — suppression | sans projet : tâches non assignées, commentaires conservés « Utilisateur supprimé », adhésions retirées | état de la base |
| Admin — suppression | propriétaire : 409 sans repreneur (rien ne bouge), transfert, repreneur invalide, `delete_solo` + atomicité | 409 / 204 / 400 |
| Admin — projets | vue globale, recherche, suppression, transfert (un seul propriétaire, nouveau membre ajouté) | rôles |
| Admin — réglages | fermer les inscriptions (403 + config publique), l'admin peut quand même créer | codes |
| Admin — audit | une entrée par action, ordre, filtre, acteur conservé après suppression, **aucun mot de passe**, rien si l'action échoue | contenu du journal |
| Moteur Rust | 7 tests Rust (`cargo test`) : cascade, chemin critique, prévision, cycles | réussite |
| Moteur Rust ↔ Python | résultats identiques sur ~1 200 graphes aléatoires (DAG, cycles, tâches terminées/non planifiées, durées nulles) + graphe de 3 000 tâches | égalité stricte, erreurs comprises |
| Moteur — repli | toute la suite lancée avec `TASKFLOW_PLANNING_BACKEND=rust` puis `python` | 158/158 dans les deux cas |
| Équipe | statuts late / overloaded / ok / free ; jours de retard exacts | états et nombres |
| Équipe | en cours, à venir, avancement, tâches sans date ; une tâche terminée n'est jamais en retard | listes correctes |
| Équipe | tri par urgence ; tâches non assignées comptées ; visible par un lecteur | ordre, 200 |
| Messagerie | un fil par projet créé à la demande, sans doublon ; solo = bloc-notes, devient équipe quand quelqu'un rejoint | `solo` vrai / faux |
| Messagerie | lecteur : lit mais n'écrit pas (403) ; étranger : 404 partout (lecture, écriture, lu, suppression) ; non authentifié : 401 | codes |
| Messagerie | message vide, blanc, > 2000 caractères refusés (400) ; HTML stocké tel quel | 400 / 201 |
| Messagerie | pagination (`limit`, `before`, `after`) ; paramètre invalide | pages exactes / 400 |
| Messagerie | suppression : auteur oui, autre membre non (403), propriétaire du projet oui, en direct seul l'auteur | 204 / 403 |
| Mentions | motif : casse, ponctuation, email, inconnu, soi-même, doublons, `@@` | utilisateurs notifiés |
| Mentions | équipe : seul le mentionné est notifié ; `@tous` / `@all` : tous les autres ; hors projet : personne ; solo : personne | compteurs |
| Notifications | liste récentes d'abord, marquage unitaire / global, impossible de marquer celles d'autrui ; suppression du message → notification supprimée | compteurs |
| Non lus | ses propres messages ne comptent pas ; lecture remet à zéro ; répondre = avoir lu | compteurs |
| Messages directs | paire unique dans les deux sens (par id ou nom) ; projet commun obligatoire (404 identique à « inconnu ») ; ni soi-même (400) ni compte inactif ; invisible des tiers ; `@tous` ignoré | 200 / 404 / 400 |
| Messagerie — cycle de vie | suppression d'un projet → son fil ; suppression d'un utilisateur → messages de projet conservés (« Utilisateur supprimé »), conversations directes supprimées | cascade |
| Limites de débit | 11 connexions ratées → 429, y compris avec le bon mot de passe ensuite ; inscription limitée ; envoi de messages limité (61e → 429) mais lecture jamais ; changement de fuseau jamais limité | codes |
| Compte | export (mes données seulement, aucun mot de passe) ; suppression : mot de passe exigé, refus (dernier admin, projet partagé), projets solo supprimés, contenu conservé « Utilisateur supprimé », audit sans secret, limitée | 204 / 400 / 429 |
| Cession de projet | transfert à un membre ; refus pour un non-membre, soi-même, un non-propriétaire | 200 / 400 / 403 / 404 |
| Messagerie — enrichie | modification (auteur seul, mentions nouvelles seulement) ; réponse citée (même fil) et survie à la suppression du message cité | 200 / 400 / 403 |
| Messagerie — réactions | bascule, compteurs, 6 émojis autorisés, lecteur et étranger refusés | 200 / 400 / 403 / 404 |
| Messagerie — `#tâche` | tâche du projet liée ; autre projet jamais exposé ; rien en direct ; entités HTML ignorées | liste de tâches |
| Messagerie — recherche | seulement mes conversations, plus récent d'abord, requête courte refusée, `around` (résultat + contexte) | listes / 400 |
| Pièces jointes | envoi et téléchargement par les participants seulement (401/404), PDF en téléchargement, `nosniff` + CSP ; types dangereux refusés quel que soit le type annoncé ; contenu ≠ extension refusé ; limites 5 Mo / 3 fichiers ; nom d'origine jamais utilisé comme chemin ; fichier supprimé avec le message | 201 / 400 / 403 / 404 |
| Calendrier — récurrence | jour / jours ouvrés / semaine / mois ; 31 saute les mois courts ; fin, horizon 3 ans, plage lointaine ; heure murale conservée à travers le changement d'heure et dans un fuseau étranger ; déplacer la série ; supprimer une occurrence (idempotent) ; validations | dates exactes |
| Calendrier — invitations | invité voit sans modifier ; notification ; réponses ; règles d'invitation (membres / collègues, comptes inactifs) ; ajout et retrait ; suppression en cascade ; séries invitées | statuts, 400 / 403 / 404 |
| E-mails | un e-mail par mention (seulement le mentionné, jamais l'auteur) ; `@tous` ; préférence respectée ; 1 par fil et 10 min ; panne SMTP sans effet ; invitation avec l'heure dans le fuseau de l'invité | `outbox` |
| Résumé du matin | rien à dire → pas d'e-mail ; agenda, tâches du jour et en retard ; événements d'un autre jour et invitations refusées exclus ; série du jour ; commande (opt-in, `--dry-run`) | contenu du texte |
| Jours ouvrés | conversions sur dix ans, bords d'année et années bissextiles ; successeur le lundi ; durée conservée à travers un week-end ; chaîne de trois ; chemin critique et fin prévue en jours ouvrés ; « rattraper » un samedi ; projet calendaire inchangé | dates exactes |
| Tâches récurrentes | chaque règle ; pas de doublon à la réouverture ; durée, responsable, priorité copiés, pas les dépendances ; sans date ou une seule date ; jours ouvrés ; droits | tâche suivante |
| Simulation de retard | tâche critique vs isolée ; tâche à marge qui devient critique ; terminées ignorées ; retard existant ; jours ouvrés ; validation `delay` ; droits ; boucle → 400 | classement |
| Simulation — équivalence | Rust = Python sur 400 graphes aléatoires (dont des cycles) + graphe de 400 tâches | résultats identiques |
| Charge d'équipe | pourcentage par membre et semaine, week-ends exclus, terminées/non datées/non assignées ignorées ; propositions (moins prioritaire, `todo`, jamais à un lecteur, jamais au-delà de 100 %) ; bornes de l'API | `percent`, `suggestions` |
| Suivi du temps | chrono (minutes, plafond 12 h, minimum 1 min, un seul à la fois, jour local) ; saisie manuelle et validations ; suppression (propriétaire) ; total sans requête supplémentaire ; compte supprimé ; rapport | minutes exactes |
| Modèles de projet | les 4 modèles produisent un projet cohérent (aucune tâche avant ses prérequis, jours ouvrés respectés) ; enregistrer puis réutiliser ; privés ; limite 20 ; modèle corrompu | 201 / 400 / 404 |
| Fuseaux | profil créé à la première lecture (Europe/Paris) ; modification des deux fuseaux ; droits (`is_staff`) non modifiables | 200 |
| Fuseaux | nom inconnu, chemin (`../etc/passwd`), `UTC+2`, vide → refusés | 400 |
| Fuseaux | « 14 h » à Tokyo = 05 h UTC ; sans fuseau = celui du profil (New York, EDT) ; décalage explicite prioritaire | instants UTC exacts |
| Fuseaux | heure d'été : 9 h à Paris le 24 oct. = 07 h UTC, le 26 oct. = 08 h UTC ; heure inexistante (29 mars) et répétée (25 oct.) sans erreur | 201 |
| Fuseaux | la réponse relue dans Tokyo / New York donne 14 h / 1 h | heures locales |
| Événements | fin ≤ début, durée > 31 jours ; PATCH revalide avec les valeurs stockées ; le fuseau de saisie est conservé | 400 ; 200 |
| Événements | personnel invisible des autres (404) ; événement de projet visible des membres, pas d'un tiers | listes, 404 |
| Événements | lecteur : lecture seule (`can_edit` faux, 403 en écriture) ; projet étranger refusé ; pas de déplacement vers un projet où l'on est lecteur | 400 / 403 |
| Événements | suppression d'un projet → ses événements ; suppression d'un utilisateur → ses événements personnels | cascade |
| Calendrier | tâches qui chevauchent la période + événements de la période ; événement qui passe minuit visible les deux jours | contenus |
| Calendrier | les jours suivent le fuseau du profil (23 h 30 à Paris = lendemain à Tokyo) | événement présent / absent |
| Calendrier | filtres projet et « mes tâches » ; aucun contenu d'un tiers ; périodes invalides (absentes, inversées, > 62 jours) | 400 / 404 |
| API planification | lecteur : insights OK, replan 403 ; étranger : 404 | droits |


## Scénarios manuels (front)
1. Inscription, connexion, rechargement de la page (session conservée).
2. Vue Liste : ajout rapide (Entrée), cocher/décocher une tâche, filtres et regroupement ; création d'un projet.
3. Calendrier : clic dans la grille à 14 h 20 → l'événement démarre à 14:00 ; cliquer une tâche à la journée ouvre son projet.
4. Glisser une carte entre colonnes du tableau.
5. Inviter un second compte, vérifier ses droits selon le rôle (lecteur : aucun bouton d'écriture).
6. Saisir `<script>` dans un titre : affiché comme texte.
7. Thème sombre, raccourcis clavier, affichage à 800 px de large.
8. Gantt : déplacer une barre, la redimensionner par ses bords, vérifier que les successeurs suivent ; tenter de créer une boucle (refusée).
9. Gantt : bouton « Rattraper le retard », bascule du chemin critique, zoom jours/mois.
10. Fuseaux : choisir Tokyo comme fuseau principal → les heures se décalent de 7 h ; ajouter New York en second fuseau → deuxième colonne d'heures ; créer « 11 h Montréal » → s'affiche à 17 h en heure de Paris.
11. Vue Équipe : un membre avec une tâche dont la fin est passée apparaît « En retard » avec le bon nombre de jours ; terminer la tâche le repasse « Dans les temps » ou « Disponible ».
12. Accueil : cocher une tâche du focus la retire de la liste et met à jour les KPI ; cliquer une alerte ouvre le projet et la tâche concernée.
13. Synthèse : terminer une tâche fait monter la courbe « Terminées » et la vélocité ; les graphiques restent lisibles en thème sombre.
14. Administration : créer un utilisateur sans mot de passe → copier le mot de passe généré → se connecter avec ; le désactiver → connexion refusée ; supprimer un propriétaire de projets → l'interface impose un repreneur.
15. Administration : fermer les inscriptions → l'onglet « Inscription » disparaît de l'écran de connexion après rechargement ; ouvrir le journal et retrouver chaque action.
16. Calendrier : le dimanche 25 octobre 2026 (retour à l'heure d'hiver), créer un événement à 02:30 puis à 04:00 → aucune erreur, heures cohérentes ; ligne rouge « maintenant » à la bonne heure.
17. Messagerie : dans un projet d'équipe, taper `@` → la liste propose les collègues (flèches, Entrée) ; envoyer ; sur le compte du collègue, la pastille 🔔 apparaît en moins de 15 s et la notification ouvre le bon fil ; dans un projet solo, le fil est un bloc-notes sans proposition de mention ; Maj+Entrée = retour à la ligne.
18. Barre latérale : réduire/agrandir (« / »), pastilles sur Messages et sur les projets, administration et thème en pied ; `C` calendrier, `H` tableau de bord, `I` messages.

## Tests du front (`./test-front.sh`)
204 vérifications sur un faux navigateur (JavaScriptCore) : accueil, synthèse, Gantt, équipe, calendrier et fuseaux, administration. Elles contrôlent le HTML produit (structure, calculs de géométrie, échappement des contenus utilisateur, droits affichés). Elles **ne remplacent pas** un test dans un vrai navigateur.

## Tests de bout en bout (`./test-e2e.sh`)
33 scénarios dans un **vrai navigateur** (Firefox headless piloté par Selenium) contre une API et un front temporaires : barre latérale (repli), vues de projet, calendrier (grille, création par clic et par balayage, **déplacement et redimensionnement à la souris** avec contrôle de la base, simple clic sans déplacement, série et suppression d'une occurrence, réponse à une invitation, changement de fuseau, navigation), messagerie (autocomplétion `@`, envoi, **notification entre deux navigateurs connectés à deux comptes**, `#tâche`, réaction / réponse / modification / suppression, pièce jointe chargée avec le jeton, recherche, bloc-notes), charge et simulation, chrono (compteur qui avance, survie à un rechargement), création de projet depuis un modèle, tâche récurrente, jours ouvrés, **ajout d'un membre par `@nom`, **conversation qui reste en bas à droite sur les autres pages** (envoi, réduire, rechargement, retour dans Messages), lien d'invitation (un second navigateur s'inscrit via le lien et rejoint le projet avec le bon rôle)**, thème sombre, **création puis suppression d'un compte**, administration, erreur de connexion. Chaque test échoue si le bandeau d'erreur JavaScript apparaît. Ces tests ont déjà révélé de vrais défauts (onglet « Inscription » resté actif après déconnexion, Entrée qui choisissait la suggestion au lieu d'envoyer un nom déjà tapé en entier, plage créée par balayage trop courte).

## Journal des résultats
| Date | Version | Tests auto | Remarques |
|---|---|---|---|
| 2026-10-12 | 0.5.0 | 338/338 OK avec chaque moteur ; 8/8 tests Rust ; 204/204 front ; 33/33 E2E Firefox (Django 5.2, Python 3.12, SQLite) | à rejouer sur PostgreSQL ; Docker et CI non exécutés sur cette machine |

## À ajouter
Couverture de code (`coverage`), tests de charge, tests E2E sur Chrome et Safari (seul Firefox est piloté), tests d'accessibilité automatisés.
