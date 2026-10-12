"""Le module Rust et l'implémentation Python de référence doivent donner EXACTEMENT les mêmes résultats."""
import random
from datetime import date
from unittest import skipUnless

from django.test import SimpleTestCase

from . import planning_engine, planning_py

try:
    import taskflow_planning as rust
except ImportError:
    rust = None

needs_rust = skipUnless(rust is not None, "module Rust non compilé (voir README)")


def outcome(fn, *args):
    """('ok', valeur) ou ('cycle',) : permet de comparer aussi les erreurs."""
    try:
        return ("ok", fn(*args))
    except ValueError as e:
        return ("error", str(e))


def random_nodes(rng, n, cycles=False):
    nodes = []
    for i in range(1, n + 1):
        planned = rng.random() < 0.9
        start = rng.randint(0, 40)
        end = start + rng.randint(0, 12)
        pool = range(1, n + 1) if cycles else range(1, i)  # sans cycles : seulement des prérequis « plus anciens »
        preds = [j for j in pool if j != i and rng.random() < min(0.3, 3.0 / n)]
        nodes.append((i, rng.random() < 0.25, start if planned else None, end if planned else None, preds))
    return nodes


@needs_rust
class RustMatchesPythonTests(SimpleTestCase):
    CASES = 400

    def test_critical_path_forecast_and_cascade_on_random_dags(self):
        rng = random.Random(20261009)
        for case in range(self.CASES):
            nodes = random_nodes(rng, rng.randint(1, 45))
            today = rng.randint(-5, 60)
            changed = rng.choice(nodes)[0]
            self.assertEqual(outcome(rust.critical_path, nodes), outcome(planning_py.critical_path, nodes), f"cas {case}")
            self.assertEqual(outcome(rust.forecast_end, nodes, today), outcome(planning_py.forecast_end, nodes, today), f"cas {case}")
            self.assertEqual(rust.cascade_shifts(nodes, changed), planning_py.cascade_shifts(nodes, changed), f"cas {case}")

    def test_cascade_after_a_random_edit(self):
        """Scénario réel : on rallonge ou décale une tâche, puis on propage."""
        rng = random.Random(7)
        for case in range(self.CASES):
            nodes = random_nodes(rng, rng.randint(2, 40))
            k = rng.randrange(len(nodes))
            i, done, s, e, preds = nodes[k]
            if s is not None:
                shift = rng.randint(-3, 15)
                nodes[k] = (i, done, s + shift, e + shift + rng.randint(0, 4), preds)
            self.assertEqual(rust.cascade_shifts(nodes, i), planning_py.cascade_shifts(nodes, i), f"cas {case}")

    def test_graphs_with_cycles_fail_or_agree_identically(self):
        rng = random.Random(3)
        cyclic = 0
        for case in range(self.CASES):
            nodes = random_nodes(rng, rng.randint(2, 20), cycles=True)
            a, b = outcome(rust.critical_path, nodes), outcome(planning_py.critical_path, nodes)
            cyclic += a[0] == "error"
            self.assertEqual(a, b, f"cas {case}")
            self.assertEqual(outcome(rust.forecast_end, nodes, 10), outcome(planning_py.forecast_end, nodes, 10))
            self.assertEqual(rust.cascade_shifts(nodes, 1), planning_py.cascade_shifts(nodes, 1))  # doit se terminer
        self.assertGreater(cyclic, 20, "le test doit réellement exercer des cycles")

    def test_delay_simulation_agrees_including_cycles(self):
        rng = random.Random(31)
        errors = 0
        for case in range(self.CASES):
            nodes = random_nodes(rng, rng.randint(1, 35), cycles=rng.random() < 0.25)
            today, delay = rng.randint(-5, 50), rng.randint(0, 20)
            a, b = outcome(rust.delay_impacts, nodes, today, delay), outcome(planning_py.delay_impacts, nodes, today, delay)
            errors += a[0] == "error"
            self.assertEqual(a, b, f"cas {case}")
        self.assertGreater(errors, 3, "le test doit réellement exercer des cycles")

    def test_large_graph(self):
        rng = random.Random(1)
        nodes = random_nodes(rng, 3000)
        self.assertEqual(rust.critical_path(nodes), planning_py.critical_path(nodes))
        self.assertEqual(rust.forecast_end(nodes, 20), planning_py.forecast_end(nodes, 20))
        self.assertEqual(rust.cascade_shifts(nodes, nodes[0][0]), planning_py.cascade_shifts(nodes, nodes[0][0]))
        small = nodes[:400]
        small = [(i, d, s, e, [p for p in ps if p <= 400]) for i, d, s, e, ps in small]
        self.assertEqual(rust.delay_impacts(small, 20, 5), planning_py.delay_impacts(small, 20, 5))

    def test_empty_inputs(self):
        for mod in (rust, planning_py):
            self.assertEqual(mod.critical_path([]), ([], 0))
            self.assertIsNone(mod.forecast_end([], 5))
            self.assertEqual(mod.cascade_shifts([], 1), [])
            self.assertEqual(mod.delay_impacts([], 5, 3), [])

    def test_python_types_are_what_django_expects(self):
        ids, total = rust.critical_path([(1, False, 0, 2, [])])
        self.assertIsInstance(ids, list)
        self.assertIsInstance(total, int)
        self.assertEqual(rust.forecast_end([(1, False, 0, 2, [])], 0), 2)


class EngineSelectionTests(SimpleTestCase):
    def test_the_python_reference_always_works(self):
        with planning_engine.use("python"):
            self.assertEqual(planning_engine.NAME, "python")
            self.assertEqual(planning_engine.critical_path([(1, False, 0, 2, [])]), ([1], 3))

    @needs_rust
    def test_switching_to_rust_and_back(self):
        before = planning_engine.NAME
        with planning_engine.use("rust"):
            self.assertEqual(planning_engine.NAME, "rust")
            self.assertEqual(planning_engine.VERSION, rust.__version__)
        self.assertEqual(planning_engine.NAME, before)

    def test_engine_name_is_exposed(self):
        self.assertIn(planning_engine.NAME, ("rust", "python"))
        self.assertEqual(planning_engine.RUST_AVAILABLE, rust is not None)

    def test_dates_are_plain_ordinals(self):
        d = date(2026, 10, 9).toordinal()
        with planning_engine.use("python"):
            self.assertEqual(planning_engine.forecast_end([(1, False, d, d + 2, [])], d), d + 2)
