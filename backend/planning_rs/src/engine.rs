//! Moteur de planification — logique pure, sans dépendance à Python.
//!
//! Même contrat que `backend/tasks/planning_py.py` (implémentation de référence) : les deux sont comparés
//! sur des milliers de graphes aléatoires par les tests Python. Les dates sont des entiers (jours depuis
//! l'ère grégorienne, `date.toordinal()` côté Python), ce qui évite toute dépendance à une bibliothèque de dates.

use std::collections::{HashMap, VecDeque};
use std::hash::{BuildHasherDefault, Hasher};

pub type Id = i64;

/// Hachage rapide pour des clés entières (la table standard utilise SipHash, conçu contre les attaques, inutile ici).
#[derive(Default)]
struct Fx(u64);

impl Hasher for Fx {
    fn finish(&self) -> u64 {
        self.0
    }
    fn write(&mut self, bytes: &[u8]) {
        for &b in bytes {
            self.write_u64(b as u64);
        }
    }
    fn write_i64(&mut self, i: i64) {
        self.write_u64(i as u64);
    }
    fn write_u64(&mut self, i: u64) {
        self.0 = (self.0.rotate_left(5) ^ i).wrapping_mul(0x517c_c1b7_2722_0a95);
    }
}

type FxMap<K, V> = HashMap<K, V, BuildHasherDefault<Fx>>;

#[derive(Clone, Debug, PartialEq)]
pub struct Node {
    pub id: Id,
    pub done: bool,
    /// (début, fin) inclus ; `None` si la tâche n'est pas planifiée.
    pub span: Option<(i64, i64)>,
    /// Identifiants des prédécesseurs (« cette tâche dépend de… »).
    pub preds: Vec<Id>,
}

#[derive(Debug, PartialEq)]
pub enum EngineError {
    Cycle,
}

/// Tri topologique (Kahn) sur des indices 0..n. `preds[i]` = prérequis de i (doublons ignorés).
fn topo(preds: &[Vec<usize>]) -> Result<Vec<usize>, EngineError> {
    let n = preds.len();
    let mut indegree: Vec<usize> = vec![0; n];
    let mut succs: Vec<Vec<usize>> = vec![Vec::new(); n];
    for (i, ps) in preds.iter().enumerate() {
        let mut ps = ps.clone();
        ps.sort_unstable();
        ps.dedup();
        indegree[i] = ps.len();
        for p in ps {
            succs[p].push(i);
        }
    }
    let mut queue: VecDeque<usize> = (0..n).filter(|&i| indegree[i] == 0).collect();
    let mut order = Vec::with_capacity(n);
    while let Some(i) = queue.pop_front() {
        order.push(i);
        for &s in &succs[i] {
            indegree[s] -= 1;
            if indegree[s] == 0 {
                queue.push_back(s);
            }
        }
    }
    if order.len() == n { Ok(order) } else { Err(EngineError::Cycle) }
}

/// Tâches non terminées et planifiées, numérotées par id croissant ; prérequis restreints à cet ensemble.
struct OpenGraph {
    ids: Vec<Id>,
    start: Vec<i64>,
    end: Vec<i64>,
    preds: Vec<Vec<usize>>,
}

impl OpenGraph {
    fn new(nodes: &[Node]) -> Self {
        let mut open: Vec<&Node> = nodes.iter().filter(|n| !n.done && n.span.is_some()).collect();
        open.sort_unstable_by_key(|n| n.id);
        let index: FxMap<Id, usize> = open.iter().enumerate().map(|(i, n)| (n.id, i)).collect();
        let preds = open
            .iter()
            .map(|n| {
                let mut ps: Vec<usize> = n.preds.iter().filter_map(|p| index.get(p).copied()).collect();
                ps.sort_unstable();
                ps.dedup();
                ps
            })
            .collect();
        OpenGraph {
            ids: open.iter().map(|n| n.id).collect(),
            start: open.iter().map(|n| n.span.expect("planifiée").0).collect(),
            end: open.iter().map(|n| n.span.expect("planifiée").1).collect(),
            preds,
        }
    }

    fn duration(&self, i: usize) -> i64 {
        self.end[i] - self.start[i] + 1
    }
}

/// Chemin critique (CPM) : tâches sans marge, triées par (début au plus tôt, id), et durée totale.
pub fn critical_path(nodes: &[Node]) -> Result<(Vec<Id>, i64), EngineError> {
    let g = OpenGraph::new(nodes);
    let order = topo(&g.preds)?;
    let n = g.ids.len();
    let mut succs: Vec<Vec<usize>> = vec![Vec::new(); n];
    for (i, ps) in g.preds.iter().enumerate() {
        for &p in ps {
            succs[p].push(i);
        }
    }
    let mut earliest_start = vec![0i64; n];
    let mut earliest_finish = vec![0i64; n];
    for &i in &order {
        earliest_start[i] = g.preds[i].iter().map(|&p| earliest_finish[p]).max().unwrap_or(0);
        earliest_finish[i] = earliest_start[i] + g.duration(i);
    }
    let total = earliest_finish.iter().copied().max().unwrap_or(0);
    let mut latest_start = vec![0i64; n];
    for &i in order.iter().rev() {
        let latest_finish = succs[i].iter().map(|&s| latest_start[s]).min().unwrap_or(total);
        latest_start[i] = latest_finish - g.duration(i);
    }
    let mut critical: Vec<usize> = (0..n).filter(|&i| latest_start[i] == earliest_start[i]).collect();
    critical.sort_unstable_by_key(|&i| (earliest_start[i], g.ids[i]));
    Ok((critical.into_iter().map(|i| g.ids[i]).collect(), total))
}

/// Fin prévue si rien ne change : une tâche en retard finit au mieux aujourd'hui, et ce retard se propage.
pub fn forecast_end(nodes: &[Node], today: i64) -> Result<Option<i64>, EngineError> {
    let g = OpenGraph::new(nodes);
    if g.ids.is_empty() {
        return Ok(None);
    }
    let order = topo(&g.preds)?;
    let mut ends = vec![0i64; g.ids.len()];
    for &i in &order {
        let mut shift = (today - g.end[i]).max(0);
        for &p in &g.preds[i] {
            shift = shift.max(ends[p] + 1 - g.start[i]);
        }
        ends[i] = g.end[i] + shift;
    }
    Ok(ends.into_iter().max())
}

/// Décalages à appliquer quand `changed` a bougé : ses successeurs sont repoussés (jamais avancés), durée
/// conservée, et le décalage se propage. Les tâches terminées ne bougent pas et arrêtent la propagation.
/// Retourne (id, nouveau début, nouvelle fin) pour chaque tâche réellement déplacée, triées par id.
pub fn cascade_shifts(nodes: &[Node], changed: Id) -> Vec<(Id, i64, i64)> {
    let index: FxMap<Id, usize> = nodes.iter().enumerate().map(|(i, n)| (n.id, i)).collect();
    let Some(&first) = index.get(&changed) else { return Vec::new() };
    let mut spans: Vec<Option<(i64, i64)>> = nodes.iter().map(|n| n.span).collect();
    let original = spans.clone();
    let mut dependents: Vec<Vec<usize>> = vec![Vec::new(); nodes.len()];
    for (i, n) in nodes.iter().enumerate() {
        for p in &n.preds {
            if let Some(&pi) = index.get(p) {
                dependents[pi].push(i);
            }
        }
    }
    let mut queue: VecDeque<usize> = VecDeque::from([first]);
    // Garde-fou : sans boucle de dépendances, chaque tâche est repoussée un nombre fini de fois.
    let mut budget = nodes.len().saturating_mul(nodes.len()).saturating_add(16);
    while let Some(current) = queue.pop_front() {
        if budget == 0 {
            break;
        }
        budget -= 1;
        let Some((_, current_end)) = spans[current] else { continue };
        let earliest = current_end + 1;
        for &dep in &dependents[current] {
            if nodes[dep].done {
                continue;
            }
            let Some(sp) = spans[dep].as_mut() else { continue };
            if sp.0 >= earliest {
                continue;
            }
            let delta = earliest - sp.0;
            sp.0 += delta;
            sp.1 += delta;
            queue.push_back(dep);
        }
    }
    let mut moved: Vec<(Id, i64, i64)> = (0..nodes.len())
        .filter(|&i| spans[i] != original[i])
        .filter_map(|i| spans[i].map(|(s, e)| (nodes[i].id, s, e)))
        .collect();
    moved.sort_unstable();
    moved
}

#[cfg(test)]
mod tests {
    use super::*;

    fn n(id: Id, span: Option<(i64, i64)>, preds: &[Id]) -> Node {
        Node { id, done: false, span, preds: preds.to_vec() }
    }

    #[test]
    fn cascade_pushes_dependents_but_never_pulls_them_back() {
        // A 0-5 (rallongée), B 3-4 dépend de A, C 5-6 dépend de B
        let nodes = vec![n(1, Some((0, 5)), &[]), n(2, Some((3, 4)), &[1]), n(3, Some((5, 6)), &[2])];
        assert_eq!(cascade_shifts(&nodes, 1), vec![(2, 6, 7), (3, 8, 9)]);
        // A raccourcie : rien ne revient en arrière
        let nodes = vec![n(1, Some((0, 1)), &[]), n(2, Some((3, 4)), &[1])];
        assert!(cascade_shifts(&nodes, 1).is_empty());
    }

    #[test]
    fn cascade_leaves_finished_tasks_alone_and_stops_there() {
        let mut nodes = vec![n(1, Some((0, 5)), &[]), n(2, Some((1, 2)), &[1]), n(3, Some((3, 4)), &[2])];
        nodes[1].done = true;
        assert!(cascade_shifts(&nodes, 1).is_empty());
    }

    #[test]
    fn cascade_takes_the_latest_of_several_predecessors() {
        let nodes = vec![n(1, Some((0, 2)), &[]), n(2, Some((0, 9)), &[]), n(3, Some((3, 4)), &[1, 2])];
        assert_eq!(cascade_shifts(&nodes, 1), vec![]);
        assert_eq!(cascade_shifts(&nodes, 2), vec![(3, 10, 11)]);
    }

    #[test]
    fn critical_path_is_the_longest_chain() {
        // A(3j) -> B(2j) -> D(1j) ; C(1j) -> D
        let nodes = vec![n(1, Some((0, 2)), &[]), n(2, Some((3, 4)), &[1]), n(3, Some((0, 0)), &[]), n(4, Some((5, 5)), &[2, 3])];
        assert_eq!(critical_path(&nodes), Ok((vec![1, 2, 4], 6)));
    }

    #[test]
    fn critical_path_ignores_finished_and_unscheduled_tasks() {
        let mut nodes = vec![n(1, Some((0, 2)), &[]), n(2, Some((3, 4)), &[1]), n(3, None, &[2])];
        nodes[0].done = true;
        assert_eq!(critical_path(&nodes), Ok((vec![2], 2)));
        assert_eq!(critical_path(&[]), Ok((vec![], 0)));
    }

    #[test]
    fn forecast_propagates_lateness() {
        let nodes = vec![n(1, Some((0, 2)), &[]), n(2, Some((3, 5)), &[1])];
        assert_eq!(forecast_end(&nodes, 10), Ok(Some(13)));
        assert_eq!(forecast_end(&nodes, 0), Ok(Some(5)));
        assert_eq!(forecast_end(&[], 0), Ok(None));
    }

    #[test]
    fn cycles_are_reported_not_looped_on() {
        let nodes = vec![n(1, Some((0, 1)), &[2]), n(2, Some((2, 3)), &[1])];
        assert_eq!(critical_path(&nodes), Err(EngineError::Cycle));
        assert_eq!(forecast_end(&nodes, 0), Err(EngineError::Cycle));
        let _ = cascade_shifts(&nodes, 1); // doit se terminer
    }
}
