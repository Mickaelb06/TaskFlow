# Module Rust — moteur de planification

## Rôle
Les calculs de planification (chemin critique, décalage en cascade des dépendances, fin prévue, simulation de retard) sont des algorithmes de graphes purs. Ils sont implémentés **deux fois** avec le même contrat :

| | Fichier | Rôle |
|---|---|---|
| Rust | `backend/planning_rs/src/engine.rs` (+ `lib.rs` pour la liaison PyO3) | moteur utilisé quand il est compilé |
| Python | `backend/tasks/planning_py.py` | implémentation de **référence** et solution de repli |

Le choix est fait au démarrage par `tasks/planning_engine.py` :
`TASKFLOW_PLANNING_BACKEND=auto` (défaut : Rust s'il est installé), `rust` (erreur au démarrage s'il manque) ou `python`. Le moteur actif est visible dans `GET /health/` et dans l'administration (Vue d'ensemble → État du système).

```mermaid
flowchart LR
    V[Vues / services Django] --> P[tasks/planning.py<br>accès base de données, conversion]
    P --> E{planning_engine}
    E -->|compilé| R[taskflow_planning<br>Rust + PyO3]
    E -->|sinon| Y[planning_py.py<br>Python de référence]
    R & Y --> P
```

`planning.py` reste la seule couche qui connaît Django : elle convertit les tâches en nœuds `(id, terminée, début, fin, prérequis)` (dates en ordinaux), appelle le moteur, puis écrit le résultat. Le moteur ne touche jamais à la base.

## Contrat
| Fonction | Entrée | Sortie |
|---|---|---|
| `critical_path(nodes)` | nœuds | `(ids triés par début au plus tôt puis id, durée totale)` ; `ValueError("cycle")` |
| `forecast_end(nodes, today)` | nœuds, ordinal du jour | ordinal de la fin prévue ou `None` ; `ValueError("cycle")` |
| `cascade_shifts(nodes, changed_id)` | nœuds, tâche modifiée | `[(id, début, fin)]` des tâches repoussées, triées par id |
| `delay_impacts(nodes, today, delay)` | nœuds, ordinal du jour, retard en jours | `[(id, recul de la fin du projet, nb d'autres tâches repoussées)]`, par recul décroissant ; `ValueError("cycle")` |

Règles : on ne repousse jamais une tâche plus tôt ; les tâches terminées ne bougent pas et arrêtent la propagation ; une durée nulle vaut 1 jour ; un cycle est signalé, jamais bouclé (garde-fou sur le nombre d'itérations).

## Garantir que les deux versions restent identiques
- `cargo test --lib` : 8 tests Rust (cascade, chemin critique, prévision, simulation de retard, cycles).
- `tasks/test_engine.py` : compare Rust et Python sur environ **1 600 graphes aléatoires** (DAG, graphes avec cycles, tâches terminées ou non planifiées, graphe de 3 000 tâches). Une divergence fait échouer le test.
- Toute la suite Django (321 tests) est exécutée **avec chaque moteur** (matrice `engine: [rust, python]` en CI).

Règle d'or : modifier un algorithme = modifier **les deux** fichiers + ajouter le cas au test de comparaison.

## Mesures (`python bench_planning.py`, Mac Intel, Python 3.12, Rust 1.99 `--release`)
| Tâches | Fonction | Python | Rust | Gain |
|---|---|---|---|---|
| 50 | chemin critique | 0,15 ms | 0,03 ms | ×5 |
| 1 000 | chemin critique | 2,98 ms | 0,60 ms | ×5 |
| 20 000 | chemin critique | 70,7 ms | 12,9 ms | ×5 |
| 20 000 | fin prévue | 40,8 ms | 10,1 ms | ×4 |
| 20 000 | cascade | 13,1 ms | 8,3 ms | ×2 |
| 50 | **simulation de retard** | 1,39 ms | 0,04 ms | ×37 |
| 1 000 | **simulation de retard** | 469 ms | 4,2 ms | ×111 |
| 2 000 | **simulation de retard** | 1 897 ms | 17 ms | ×112 |

**Lecture honnête** : sur les calculs *simples* (une passe sur le graphe), le gain est réel mais modeste (×2 à ×5). Environ 8 à 10 ms sur 12 ms (20 000 tâches) sont consommées par la **copie des données de Python vers Rust**, pas par le calcul. Un projet réaliste (quelques dizaines de tâches) se calcule en moins d'une demi-milliseconde dans les deux cas : **l'utilisateur ne perçoit aucune différence**. Pour ces calculs, l'intérêt est surtout architectural (frontière FFI propre, contrat testé, repli automatique). 

**Là où Rust change vraiment les choses : la simulation « et si ? »** (`delay_impacts`, onglet Charge → « Et si une tâche prenait du retard ? »). Elle refait une passe complète du graphe *pour chaque tâche* (O(n²)) mais ne transmet qu'une seule fois les données : le coût de copie devient négligeable et le gain atteint **×110**. Pour un projet de 1 000 tâches, la réponse arrive en 4 ms au lieu d'une demi-seconde, ce qui rend la fonction utilisable en direct. Sur un projet réaliste de 50 tâches, 0,04 ms contre 1,4 ms : imperceptible dans les deux cas — là encore, l'honnêteté impose de dire que le bénéfice utilisateur n'apparaît qu'à grande échelle.

Une première version du moteur (tables de hachage) ne donnait que ×1 à ×3 : le passage à des tableaux indexés a été guidé par ces mesures.

## Compiler et installer
```bash
# 1. Rust (une fois) : https://rustup.rs  — installé dans ~/.cargo
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# 2. Dans le dépôt
cd backend
pip install maturin                       # (dans le venv)
export PYO3_PYTHON="$PWD/.venv/bin/python"   # cargo doit voir le Python du projet, pas celui du système
(cd planning_rs && cargo test --lib)      # tests Rust
maturin develop --release --uv -m planning_rs/Cargo.toml   # compile et installe dans le venv
python manage.py test tasks.test_engine   # comparaison Rust / Python
python bench_planning.py                  # mesures (nécessite DJANGO_SETTINGS_MODULE)
```
`--uv` est requis quand le venv est créé avec `uv` (pas de `pip` dedans). Le module est une roue **abi3** (Python ≥ 3.10) : une seule compilation suffit pour toutes les versions.

## Sécurité et robustesse
- Aucun `unsafe` dans le code du projet ; la mémoire est gérée par Rust, PyO3 contient la frontière avec Python.
- Entrées non fiables : les identifiants et dates viennent de la base, jamais directement de l'utilisateur. Un graphe incohérent (boucle) renvoie une erreur au lieu de boucler ou de planter.
- Chaîne d'approvisionnement : `Cargo.lock` est versionné (versions exactes des dépendances) ; une seule dépendance directe (`pyo3`). À ajouter en production : `cargo audit` en CI.

## Jours ouvrés : une conversion, pas un second moteur
Un projet peut compter en jours ouvrés (lundi → vendredi, `Project.skip_weekends`). Plutôt que de compliquer les deux implémentations, `tasks/workdays.py` convertit les dates en **numéros de jour ouvré** avant d'appeler le moteur (le vendredi est le n° 4, le lundi suivant le n° 5 ; un week-end prend le numéro du lundi suivant) et reconvertit les résultats. « Fin + 1 » devient naturellement le prochain jour ouvré, une durée de 3 jours est 3 jours ouvrés. Le moteur, lui, ne sait rien des week-ends : il reste simple, et la même suite de tests de comparaison continue de s'appliquer. Les conversions sont testées sur dix ans de dates (`tasks/test_workdays.py`).
