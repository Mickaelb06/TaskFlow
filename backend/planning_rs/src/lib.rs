//! Liaison Python (PyO3) du moteur de planification. Aucune logique ici : conversion des types uniquement.

mod engine;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// (id, terminée, début, fin, ids des prérequis) — début et fin valent `None` pour une tâche non planifiée.
type PyNode = (i64, bool, Option<i64>, Option<i64>, Vec<i64>);

fn nodes(raw: Vec<PyNode>) -> Vec<engine::Node> {
    raw.into_iter()
        .map(|(id, done, start, end, preds)| engine::Node {
            id,
            done,
            span: match (start, end) {
                (Some(s), Some(e)) => Some((s, e)),
                _ => None,
            },
            preds,
        })
        .collect()
}

fn cycle(_: engine::EngineError) -> PyErr {
    PyValueError::new_err("cycle")
}

/// critical_path(nodes) -> (ids triés, durée totale en jours)
#[pyfunction]
fn critical_path(raw: Vec<PyNode>) -> PyResult<(Vec<i64>, i64)> {
    engine::critical_path(&nodes(raw)).map_err(cycle)
}

/// forecast_end(nodes, today) -> fin prévue (ordinal) ou None
#[pyfunction]
fn forecast_end(raw: Vec<PyNode>, today: i64) -> PyResult<Option<i64>> {
    engine::forecast_end(&nodes(raw), today).map_err(cycle)
}

/// cascade_shifts(nodes, changed_id) -> [(id, nouveau début, nouvelle fin)]
#[pyfunction]
fn cascade_shifts(raw: Vec<PyNode>, changed: i64) -> Vec<(i64, i64, i64)> {
    engine::cascade_shifts(&nodes(raw), changed)
}

#[pymodule]
fn taskflow_planning(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(critical_path, m)?)?;
    m.add_function(wrap_pyfunction!(forecast_end, m)?)?;
    m.add_function(wrap_pyfunction!(cascade_shifts, m)?)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
