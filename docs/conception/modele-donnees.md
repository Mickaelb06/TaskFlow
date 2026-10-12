# Modèle de données et diagrammes UML

Les diagrammes sont en Mermaid (rendus automatiquement par GitHub).

## MCD / MLD
```mermaid
erDiagram
    USER ||--o{ PROJECT : "possède"
    USER ||--o{ MEMBERSHIP : "participe"
    TASK ||--o{ TIMEENTRY : "temps passé"
    USER |o--o{ TIMEENTRY : "saisit"
    USER ||--o{ PROJECTTEMPLATE : "enregistre"
    EVENT ||--o{ INVITATION : "invite"
    USER ||--o{ INVITATION : "reçoit"
    EVENT ||--o{ EVENTSKIP : "occurrences supprimées"
    MESSAGE ||--o{ REACTION : "reçoit"
    MESSAGE ||--o{ ATTACHMENT : "joint"
    MESSAGE |o--o{ MESSAGE : "répond à"
    TASK |o--o{ TASK : "récurrence (suivante)"
    PROJECT ||--o| CONVERSATION : "a un fil"
    CONVERSATION ||--o{ MESSAGE : "contient"
    MESSAGE }o--o{ USER : "mentionne"
    MESSAGE ||--o{ NOTIFICATION : "déclenche"
    USER ||--o{ NOTIFICATION : "reçoit"
    CONVERSATION ||--o{ READMARK : "suivi de lecture"
    PROJECT ||--o{ MEMBERSHIP : "a pour membres"
    PROJECT ||--o{ PROJECTINVITE : "a des liens d'invitation"
    PROJECT ||--o{ TASK : "contient"
    USER |o--o{ TASK : "est assigné à"
    TASK }o--o{ TASK : "dépend de"
    TASK ||--o{ COMMENT : "reçoit"
    USER |o--o{ COMMENT : "écrit (nul si compte supprimé)"
    USER |o--o{ AUDITLOG : "réalise"

    USER { int id PK
           string username UK
           string email UK
           string password_hash }
    PROJECT { int id PK
              string name
              text description
              date deadline "nullable"
              int owner_id FK
              datetime created_at }
    MEMBERSHIP { int project_id FK
                 int user_id FK
                 string role "owner | member | viewer" }
    TASK { int id PK
           int project_id FK
           string title
           text description
           string status "todo | doing | done"
           int priority "1 à 3"
           date start_date "nullable"
           date due_date "nullable"
           bool is_milestone
           datetime completed_at "nullable, posée au passage à terminée"
           int assignee_id FK "nullable"
           datetime created_at }
    AUDITLOG { int id PK
               int actor_id FK "nullable"
               string actor_name
               string action
               string target
               json details "sans secret"
               datetime created_at }
    SITESETTINGS { int id PK "singleton"
                   bool allow_registration }
    CONVERSATION { int id PK
                   string kind "project | direct"
                   int project_id FK "1-1, pour kind=project"
                   int user_a_id FK "direct : a < b"
                   int user_b_id FK }
    MESSAGE { int id PK
              int conversation_id FK
              int author_id FK "nullable"
              text content "2000 car. max"
              bool mentions_all
              int reply_to_id FK "nullable"
              datetime edited_at "nullable"
              datetime created_at }
    NOTIFICATION { int id PK
                   int user_id FK
                   int message_id FK
                   datetime read_at "nullable"
                   datetime created_at }
    READMARK { int id PK
               int conversation_id FK
               int user_id FK
               int last_read_id "dernier message lu" }
    TIMEENTRY { int id PK
                int task_id FK
                int user_id FK "nullable"
                date day
                int minutes "null = chrono en cours"
                datetime started_at "nullable"
                string note }
    PROJECTTEMPLATE { int id PK
                      int owner_id FK
                      string name
                      bool skip_weekends
                      json tasks "décalages relatifs, dépendances" }
    INVITATION { int id PK
                 int event_id FK
                 int user_id FK
                 string status "invited | accepted | declined"
                 datetime seen_at "nullable" }
    EVENTSKIP { int id PK
                int event_id FK
                date day "occurrence supprimée" }
    REACTION { int id PK
               int message_id FK
               int user_id FK
               string emoji }
    ATTACHMENT { int id PK
                 int message_id FK
                 string file "nom aléatoire"
                 string name "nom d'origine, affiché seulement"
                 string content_type "vérifié sur le contenu"
                 int size }
    PROFILE { int id PK
              int user_id FK "1-1"
              string timezone "IANA, défaut Europe/Paris"
              string secondary_timezone "optionnel : 2e colonne d'heures"
              bool notify_email
              bool digest_email }
    EVENT { int id PK
            int project_id FK "nullable : vide = personnel"
            int creator_id FK "nullable"
            string title
            text description
            datetime starts_at "UTC"
            datetime ends_at "UTC, > starts_at (CHECK)"
            string timezone "fuseau de saisie ; sert aussi à la récurrence"
            string recurrence "daily | weekdays | weekly | monthly"
            date recurrence_until "nullable"
            datetime created_at }
    COMMENT { int id PK
              int task_id FK
              int author_id FK
              text content
              datetime created_at }
```
Contraintes : `TIMEENTRY` : durée ≤ 24 h et soit `minutes` soit `started_at` renseigné (CHECK) ; `INVITATION (event_id, user_id)` unique ; `REACTION (message, user, emoji)` unique ; `MEMBERSHIP (project_id, user_id)` unique ; `TASK.start_date <= due_date` (CHECK) ; table de liaison `task_dependencies` (auto-association N:N, boucles interdites côté service) ; `TASK.priority` entre 1 et 3 (CHECK) ; suppression d'un projet → cascade sur membres, tâches, commentaires ; retrait d'un membre → ses tâches redeviennent non assignées.

Implémentation : `backend/projects/models.py`, `backend/tasks/models.py`, migrations associées.

## Cas d'utilisation
```mermaid
flowchart LR
    V([Visiteur]) --> S[S'inscrire] & L[Se connecter]
    M([Membre]) --> T[Gérer les tâches] & C[Commenter] & K[Consulter calendrier / tableau]
    LE([Lecteur]) --> K
    O([Propriétaire]) --> P[Gérer le projet] & G[Gérer les membres] & T
    O -. hérite de .-> M
```

## Diagramme de classes (couche métier)
```mermaid
classDiagram
    class Project { +name +description +owner }
    class Membership { +role }
    class Task { +title +status +priority +due_date }
    class Comment { +content }
    class ProjectService { +create_project() +add_member() +change_role() +remove_member() }
    class TaskService { +create_task() +update_task() +add_comment() }
    class Planning { +cascade() +critical_path() +forecast_end() +insights() +replan() }
    class EventService { +create_event() +update_event() +delete_event() +calendar() }
    class Event { +title +starts_at +ends_at +timezone }
    class Profile { +timezone +secondary_timezone }
    Project "1" --> "*" Membership
    Project "1" --> "*" Task
    Task "1" --> "*" Comment
    ProjectService ..> Project
    ProjectService ..> Membership
    TaskService ..> Task
    TaskService ..> Comment
    TaskService ..> Planning
    EventService ..> Event
    EventService ..> Profile : jours vus dans le fuseau de l'utilisateur
    Project "1" --> "*" Event
```

## Séquence : créer une tâche
```mermaid
sequenceDiagram
    actor U as Utilisateur
    participant F as Front (JS)
    participant V as TaskViewSet
    participant S as services.create_task
    participant DB as PostgreSQL
    U->>F: clic sur un jour / « Nouvelle tâche »
    F->>V: POST /api/projects/{id}/tasks/ (JWT)
    V->>V: authentification + rôle du projet (404 / 403)
    V->>V: TaskSerializer.validate (priorité, assigné membre)
    V->>S: create_task(user, project, données)
    S->>DB: INSERT task
    DB-->>S: ligne créée
    S-->>V: Task
    V-->>F: 201 + JSON
    F-->>U: la tâche apparaît dans le calendrier
```

## Séquence : déplacer une barre du Gantt (propagation des dépendances)
```mermaid
sequenceDiagram
    actor U as Utilisateur
    participant F as Gantt (JS)
    participant V as TaskViewSet
    participant S as services.update_task
    participant P as planning.cascade
    participant DB as PostgreSQL
    U->>F: glisse la barre de A de +3 jours
    F->>V: PATCH /tasks/A {start_date, due_date}
    V->>S: update_task(user, A, données)
    S->>DB: UPDATE A
    S->>P: cascade(A)
    loop pour chaque successeur trop tôt (non terminé)
        P->>DB: UPDATE dates décalées, durée conservée
    end
    V-->>F: 200 + A
    F->>V: GET /tasks/ et /insights/
    F-->>U: Gantt redessiné (successeurs décalés, KPI recalculés)
```

## Séquence : créer un événement saisi dans un autre fuseau
```mermaid
sequenceDiagram
    actor U as Utilisateur (calendrier en heure de Paris)
    participant F as Front
    participant V as EventViewSet
    participant S as EventSerializer
    participant E as agenda.services
    participant DB as Base (UTC)
    U->>F: « 11 h » le mercredi, fuseau Montréal
    F->>V: POST /events/ {starts_at: "2026-10-07T11:00", timezone: "America/Montreal"}
    V->>S: validation
    S->>S: heure sans décalage = heure murale de Montréal → 2026-10-07T15:00:00Z
    V->>E: create_event(user, …)
    E->>E: droits (propriétaire/membre du projet), fin > début, durée ≤ 31 j
    E->>DB: INSERT (starts_at en UTC)
    V-->>F: 201
    F->>V: GET /calendar/?from=…&to=…
    V-->>F: événements + tâches ; le front affiche 17:00 (heure de Paris)
```

## Séquence : mentionner un collègue
```mermaid
sequenceDiagram
    actor A as Alice
    participant F as Front (chat.js)
    participant V as MessagesView
    participant S as chat.services
    participant DB as Base
    actor B as Bob
    A->>F: tape « @b » → liste (bob), Entrée → « @bob »
    A->>F: Entrée (envoi)
    F->>V: POST /chat/conversations/10/messages/ {content}
    V->>S: post_message(alice, conv, content)
    S->>S: droits (écriture), 1..2000 caractères
    S->>S: parse_mentions : seuls les participants (bob), jamais l'auteur ; @tous = tous les autres
    S->>DB: INSERT message + mentions + notifications (bob)
    V-->>F: 201 message
    loop toutes les 15 s
        B->>F: (navigateur de Bob) GET /chat/summary/
        F-->>B: pastille 🔔 « 1 » + message « Vous avez été mentionné »
    end
    B->>F: clic sur la notification
    F->>V: POST /notifications/ {ids:[…]} puis GET messages
    V->>S: marquer lue ; ouvrir le fil (marque le fil comme lu)
```

## Séquence : simulation « et si cette tâche prenait du retard ? »
```mermaid
sequenceDiagram
    actor U as Utilisateur
    participant F as Front (onglet Charge)
    participant V as SimulateView
    participant P as planning.delay_simulation
    participant E as moteur (Rust)
    U->>F: choisit « retard de 5 jours »
    F->>V: GET /projects/7/simulate/?delay=5
    V->>P: delay_simulation(projet, 5)
    P->>P: tâches → nœuds (jours ouvrés si le projet les utilise)
    P->>E: delay_impacts(nœuds, aujourd'hui, 5)
    Note over E: une passe de prévision par tâche ouverte (O(n²)), sans retourner en Python entre deux
    E-->>P: [(id, recul de la fin, tâches repoussées)] trié
    P-->>V: titres, responsables, « absorbé » ou « +N j »
    V-->>F: JSON
    F-->>U: classement des tâches les plus risquées
```

## Liens d'invitation (`ProjectInvite`)
`project`, `token_hash` (SHA-256 du jeton, unique : **le jeton lui-même n'est jamais stocké**, comme un mot de passe), `role` (membre ou lecteur, jamais propriétaire), `created_by` (nullable), `created_at`, `expires_at`, `max_uses`, `uses`, `revoked`. Un lien est valable tant qu'il n'est ni révoqué, ni expiré, ni épuisé ; l'acceptation verrouille la ligne (`select_for_update`) pour que deux personnes simultanées ne dépassent pas `max_uses`.
