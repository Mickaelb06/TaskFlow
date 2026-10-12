"""Moteur de planification — implémentation Python de RÉFÉRENCE.

Même contrat, mêmes résultats que le module Rust (`backend/planning_rs`) : l'application utilise Rust s'il
est compilé, et retombe sur ce fichier sinon. Les tests (`test_engine.py`) comparent les deux sur des milliers
de graphes aléatoires. Ne rien changer ici sans changer `planning_rs/src/engine.rs` (et inversement).

Un nœud est un tuple `(id, terminée, début, fin, ids_des_prérequis)` ; dates = ordinaux (`date.toordinal()`),
début et fin valent None si la tâche n'est pas planifiée.
"""
from collections import defaultdict, deque


def _topo(ids, preds):
    """Tri topologique (Kahn). Lève ValueError("cycle") en cas de boucle."""
    ids_set = set(ids)
    indegree, succs = {}, defaultdict(list)
    for n in ids:
        ps = {p for p in preds.get(n, ()) if p in ids_set}
        indegree[n] = len(ps)
        for p in ps:
            succs[p].append(n)
    queue = deque(sorted(n for n, d in indegree.items() if d == 0))
    order = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for s in succs[n]:
            indegree[s] -= 1
            if indegree[s] == 0:
                queue.append(s)
    if len(order) != len(ids):
        raise ValueError("cycle")
    return order


def _open_graph(nodes):
    """Tâches non terminées et planifiées, prérequis restreints à cet ensemble."""
    open_ = {n[0]: n for n in nodes if not n[1] and n[2] is not None and n[3] is not None}
    ids = sorted(open_)
    preds = {i: sorted({p for p in open_[i][4] if p in open_}) for i in ids}
    return ids, open_, preds


def _duration(node):
    return node[3] - node[2] + 1


def critical_path(nodes):
    """Chemin critique (CPM) : (ids triés par début au plus tôt puis id, durée totale en jours)."""
    ids, open_, preds = _open_graph(nodes)
    order = _topo(ids, preds)
    succs = defaultdict(list)
    for n, ps in preds.items():
        for p in ps:
            succs[p].append(n)
    es, ef = {}, {}
    for i in order:
        es[i] = max((ef[p] for p in preds[i]), default=0)
        ef[i] = es[i] + _duration(open_[i])
    total = max(ef.values(), default=0)
    ls = {}
    for i in reversed(order):
        lf = min((ls[s] for s in succs[i]), default=total)
        ls[i] = lf - _duration(open_[i])
    critical = [i for i in order if ls[i] == es[i]]
    return sorted(critical, key=lambda i: (es[i], i)), total


def forecast_end(nodes, today):
    """Fin prévue (ordinal) si rien ne change, ou None s'il ne reste rien à faire."""
    ids, open_, preds = _open_graph(nodes)
    if not ids:
        return None
    ends = {}
    for i in _topo(ids, preds):
        start, due = open_[i][2], open_[i][3]
        shift = max(0, today - due)
        for p in preds[i]:
            shift = max(shift, ends[p] + 1 - start)
        ends[i] = due + shift
    return max(ends.values())


def cascade_shifts(nodes, changed):
    """[(id, nouveau début, nouvelle fin)] triés par id : successeurs repoussés (jamais avancés), durée conservée,
    propagation transitive ; les tâches terminées ne bougent pas et arrêtent la propagation."""
    done = {n[0] for n in nodes if n[1]}
    spans = {n[0]: (n[2], n[3]) for n in nodes if n[2] is not None and n[3] is not None}
    original = dict(spans)
    dependents = defaultdict(list)
    for n in nodes:
        for p in n[4]:
            dependents[p].append(n[0])
    queue = deque([changed])
    budget = len(nodes) * len(nodes) + 16  # garde-fou : même valeur que côté Rust
    while queue:
        if budget == 0:
            break
        budget -= 1
        current = queue.popleft()
        if current not in spans:
            continue
        earliest = spans[current][1] + 1
        for dep in dependents.get(current, ()):
            if dep in done or dep not in spans:
                continue
            start, end = spans[dep]
            if start >= earliest:
                continue
            delta = earliest - start
            spans[dep] = (start + delta, end + delta)
            queue.append(dep)
    return sorted((i, s, e) for i, (s, e) in spans.items() if original.get(i) != (s, e))


