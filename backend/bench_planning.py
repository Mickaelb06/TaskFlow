"""Compare le moteur Rust et la version Python. Usage : python bench_planning.py [nb_tâches ...]"""
import random
import sys
import time

import taskflow_planning as rust

from tasks import planning_py as py


def graph(n, seed=1):
    rng = random.Random(seed)
    nodes = []
    for i in range(1, n + 1):
        s = rng.randint(0, 200)
        preds = [rng.randint(max(1, i - 40), i - 1) for _ in range(rng.randint(0, 3))] if i > 1 else []
        nodes.append((i, rng.random() < 0.2, s, s + rng.randint(0, 10), sorted(set(preds))))
    return nodes


def best(fn, repeat):
    out = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return min(out)


def main(sizes):
    print(f"{'tâches':>8} | {'fonction':<14} | {'Python':>10} | {'Rust':>10} | {'gain':>6}")
    print("-" * 60)
    for n in sizes:
        nodes = graph(n)
        repeat = 5 if n <= 5000 else 3
        for name, args in [("critical_path", (nodes,)), ("forecast_end", (nodes, 100)), ("cascade_shifts", (nodes, 1))]:
            tp = best(lambda: getattr(py, name)(*args), repeat)
            tr = best(lambda: getattr(rust, name)(*args), repeat)
            assert getattr(py, name)(*args) == getattr(rust, name)(*args), "résultats différents !"
            print(f"{n:>8} | {name:<14} | {tp * 1000:>8.2f}ms | {tr * 1000:>8.2f}ms | x{tp / tr:>4.0f}")


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [50, 1000, 20000])
