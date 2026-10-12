"""Choix du moteur de calcul : Rust (module `taskflow_planning`) s'il est compilé, sinon Python.

Variable d'environnement `TASKFLOW_PLANNING_BACKEND` : `auto` (défaut : Rust si disponible), `rust` (erreur au
démarrage s'il manque) ou `python` (force la version de référence).
"""
import os
from contextlib import contextmanager

from django.core.exceptions import ImproperlyConfigured

from . import planning_py

try:
    import taskflow_planning as _rust
except ImportError:  # module non compilé : l'application fonctionne avec la version Python
    _rust = None

_choice = os.environ.get("TASKFLOW_PLANNING_BACKEND", "auto").strip().lower()
if _choice not in ("auto", "rust", "python"):
    raise ImproperlyConfigured("TASKFLOW_PLANNING_BACKEND doit valoir auto, rust ou python.")
if _choice == "rust" and _rust is None:
    raise ImproperlyConfigured(
        "TASKFLOW_PLANNING_BACKEND=rust mais le module Rust n'est pas installé "
        "(cd backend && maturin develop --release --uv -m planning_rs/Cargo.toml)."
    )

RUST_AVAILABLE = _rust is not None
_impl = _rust if (_rust is not None and _choice != "python") else planning_py
NAME = "rust" if _impl is _rust else "python"
VERSION = getattr(_rust, "__version__", None) if NAME == "rust" else None


@contextmanager
def use(name):
    """Bascule temporairement de moteur (tests, comparaisons)."""
    global _impl, NAME, VERSION
    previous = (_impl, NAME, VERSION)
    if name == "rust":
        if _rust is None:
            raise ImproperlyConfigured("Module Rust indisponible.")
        _impl, NAME, VERSION = _rust, "rust", _rust.__version__
    else:
        _impl, NAME, VERSION = planning_py, "python", None
    try:
        yield
    finally:
        _impl, NAME, VERSION = previous


def critical_path(nodes):
    return _impl.critical_path(nodes)


def forecast_end(nodes, today):
    return _impl.forecast_end(nodes, today)


def cascade_shifts(nodes, changed):
    return _impl.cascade_shifts(nodes, changed)


def delay_impacts(nodes, today, delay):
    return _impl.delay_impacts(nodes, today, delay)
