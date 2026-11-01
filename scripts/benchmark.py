# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Benchmark the MILP on random instances: a grid of trains K × load factor λ.

Usage:
    python scripts/benchmark.py run [options]      solve the grid, append to docs/benchmark/<configs>.csv
    python scripts/benchmark.py report [options]   write docs/benchmark.md from docs/benchmark/*.csv

Two series of instances are generated with `random_instance` (5–15 wagons per
train, 4 goods types, half of the wagons heavy) and lanes of M = 30 t:

- "grid": the number of lanes N is chosen so that the load factor
  λ = total weight / (N · M) is close to the target;
- "N=26": the reference buffer with 26 lanes, λ follows from K.

Each instance is solved in the configurations cp-sat, scip (the pure model)
and cp-sat+start, scip+start (starting from the best heuristic plan); they
can be run in separate processes with --configs.

If no heuristic plan exists for the chosen N, N is increased until one does.
Rows already in the CSV are skipped, so an interrupted run can be resumed.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

import ortools

from train_wagons import random_instance, simulate
from train_wagons.baseline import baseline_plan
from train_wagons.heuristic import wave_plan
from train_wagons.instance import YardInstance
from train_wagons.model import ModelOptions, YardModel
from train_wagons.solution import goods_changes

CAPACITY = 30.0
CONFIGS = ("cp-sat", "scip", "cp-sat+start", "scip+start")
FIELDS = [
    "series", "K", "target", "seed", "W", "N", "load_factor", "goods", "heuristic", "R",
    "variables", "constraints", "build_s", "solver", "status", "value", "bound", "seconds", "valid",
]


def heuristic_changes(instance: YardInstance) -> int | None:
    plans = [plan for plan in (wave_plan(instance), baseline_plan(instance)) if plan.has_plan]
    return min((goods_changes(instance, plan.loads) for plan in plans), default=None)


def make_instance(series: str, trains: int, target: float, seed: int) -> YardInstance:
    base = random_instance(trains=trains, capacity=CAPACITY, seed=seed)
    if series == "N=26":
        lanes = 26
    else:
        total = base.load_factor * base.lanes * base.capacity
        lanes = max(1, round(total / (CAPACITY * target)))
    while True:
        instance = YardInstance(base.trains, lanes=lanes, capacity=CAPACITY)
        if heuristic_changes(instance) is not None:
            return instance
        lanes += 1


def cases(args: argparse.Namespace) -> list[tuple[str, int, float, int]]:
    grid = [("grid", k, lam, s) for lam in args.load for k in args.trains for s in args.seeds]
    reference = [("N=26", k, 0.0, s) for k in args.trains for s in args.seeds]
    return grid + reference


def run(args: argparse.Namespace) -> None:
    out = Path(args.csv or f"docs/benchmark/{'_'.join(args.configs)}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        with out.open(newline="", encoding="utf-8") as f:
            done = {(r["series"], r["K"], r["target"], r["seed"], r["solver"]) for r in csv.DictReader(f)}
    new_file = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for series, k, target, seed in cases(args):
            for config in args.configs:
                solver, _, start = config.partition("+")
                key = (series, str(k), f"{target:g}", str(seed), config)
                if key in done:
                    continue
                instance = make_instance(series, k, target, seed)
                options = ModelOptions(
                    solver=solver,
                    time_limit=args.time_limit,
                    threads=args.threads if solver == "cp-sat" else None,
                    start=start == "start",
                )
                start = time.perf_counter()
                model = YardModel(instance, options)
                build = time.perf_counter() - start
                plan = model.solve(args.objective)
                stage = plan.stages[0]
                valid = simulate(instance, plan).errors == [] if plan.has_plan else ""
                row = {
                    "series": series, "K": k, "target": f"{target:g}", "seed": seed,
                    "W": instance.wagon_count, "N": instance.lanes, "load_factor": f"{instance.load_factor:.2f}",
                    "goods": len(instance.goods_types), "heuristic": heuristic_changes(instance), "R": model.runs,
                    "variables": model.size["variables"], "constraints": model.size["constraints"],
                    "build_s": f"{build:.1f}", "solver": config, "status": stage.status.value,
                    "value": "" if stage.value is None else round(stage.value),
                    "bound": "" if stage.bound is None else math.ceil(stage.bound - 1e-6),
                    "seconds": f"{stage.seconds:.1f}", "valid": valid,
                }
                writer.writerow(row)
                f.flush()
                print(", ".join(f"{name}={row[name]}" for name in FIELDS), flush=True)


def _thousands(value: str) -> str:
    return f"{int(value):,}".replace(",", " ")


def _cell(row: dict[str, str]) -> str:
    if row["status"] == "optimal":
        return f"**{row['value']}** {float(row['seconds']):.0f}s" if float(row["seconds"]) >= 1 else f"**{row['value']}** <1s"
    if row["value"]:
        return f"{row['value']} [{row['bound']}]"
    return "—"


FINDINGS_START, FINDINGS_END = "<!-- findings -->", "<!-- /findings -->"


def _findings(path: Path) -> str:
    """The hand-written findings of an existing report, kept when it is regenerated."""
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if FINDINGS_START in text and FINDINGS_END in text:
            return text[text.index(FINDINGS_START) : text.index(FINDINGS_END) + len(FINDINGS_END)]
    return f"{FINDINGS_START}\n*To be written.*\n{FINDINGS_END}"


def _solved_up_to(by: dict, series: str, target: float, config: str) -> str:
    """Largest K such that every instance with K' ≤ K was solved to optimality."""
    largest = "—"
    for k in sorted({key[1] for key in by if key[0] == series and key[2] == target}):
        cells = [cell.get(config) for key, cell in by.items() if key[:3] == (series, k, target)]
        if not cells or any(c is None or c["status"] != "optimal" for c in cells):
            break
        largest = str(k)
    return largest


def report(args: argparse.Namespace) -> None:
    rows = []
    for path in sorted(Path().glob(args.results)):
        with path.open(newline="", encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    by: dict[tuple, dict[str, dict[str, str]]] = defaultdict(dict)
    for r in rows:
        by[(r["series"], int(r["K"]), float(r["target"]), int(r["seed"]))][r["solver"]] = r
    solvers = [s for s in CONFIGS if any(r["solver"] == s for r in rows)]
    output = Path(args.output)

    lines = [
        "# Benchmark",
        "",
        "How far the single MILP of [mip-model.md](mip-model.md) goes. The tables are generated",
        "by `python scripts/benchmark.py report` from the CSV files in [`benchmark/`](benchmark/);",
        "the findings are written by hand and kept when the tables are regenerated.",
        "",
        "## Setup",
        "",
        f"- Criterion: **{args.objective}** only (the first stage of the lexicographic solve),"
        f" time limit {args.time_limit:g} s per instance and configuration.",
        "- Configurations: *cp-sat*, *scip* — the pure model; *+start* — the first stage starts",
        "  from the best heuristic plan (a hint for x, y, u, z and v).",
        f"- Machine: {platform.processor() or platform.machine()}, {os.cpu_count()} logical CPUs;"
        f" OR-Tools {ortools.__version__}; CP-SAT with {args.threads} threads, SCIP single-threaded.",
        "  Several configurations ran at the same time, so the times are indicative only.",
        "- Instances: `random_instance` with 5–15 wagons per train, 4 goods types, half of the wagons",
        "  heavy (4–14 t) and half light (0.2–1 t), lanes of M = 30 t. In the series *grid* the number",
        "  of lanes N is chosen for a target load factor λ = total weight / (N · M); in the series",
        "  *N = 26* the buffer has 26 lanes and λ follows from K. N is raised if no heuristic plan exists,",
        "  so for small K the actual λ can stay below the target.",
        "- R (run slots) is taken from the better heuristic plan; *heur.* is its number of changes.",
        "- Every plan found was checked with `simulate`"
        + (" — **some plans failed the check**." if any(r["valid"] == "False" for r in rows) else "; all passed."),
        "",
        "## Findings",
        "",
        _findings(output),
        "",
        "## Summary",
        "",
        "Largest number of trains K up to which every instance was solved to optimality:",
        "",
        "| series | target λ | " + " | ".join(solvers) + " |",
        "|" + "---|" * (len(solvers) + 2),
    ]
    for series in ("grid", "N=26"):
        for target in sorted({key[2] for key in by if key[0] == series}):
            label = "—" if series == "N=26" else f"{target:g}"
            lines.append(
                f"| {series} | {label} | " + " | ".join(_solved_up_to(by, series, target, s) for s in solvers) + " |"
            )
    lines.append("")
    for solver in solvers:
        solved = [r for r in rows if r["solver"] == solver]
        optimal = sum(r["status"] == "optimal" for r in solved)
        found = sum(bool(r["value"]) for r in solved)
        lines.append(f"- **{solver}**: {optimal} of {len(solved)} instances optimal, a plan for {found}.")

    lines += [
        "",
        "Cells below: **v** t = optimal with v changes, proved in t seconds; v [b] = best plan v changes,",
        "best bound b at the time limit; — = no plan found. The trivial bound is |G| − 1 = 3.",
    ]
    for series in ("grid", "N=26"):
        keys = sorted(k for k in by if k[0] == series)
        if not keys:
            continue
        lines += ["", f"## Series {series}", ""]
        head = "| target λ | K | seed | W | N | λ | heur. | R | variables | " + " | ".join(solvers) + " |"
        lines += [head, "|" + "---|" * (head.count("|") - 1)]
        for key in sorted(keys, key=lambda k: (k[2], k[1], k[3])):
            cell = by[key]
            any_row = next(iter(cell.values()))
            target = "—" if series == "N=26" else f"{key[2]:g}"
            lines.append(
                f"| {target} | {key[1]} | {key[3]} | {any_row['W']} | {any_row['N']} | {any_row['load_factor']}"
                f" | {any_row['heuristic']} | {any_row['R']} | {_thousands(any_row['variables'])} | "
                + " | ".join(_cell(cell[s]) if s in cell else "" for s in solvers)
                + " |"
            )

    lines += ["", "---", "", "© 2026 Taras Bulubas. All rights reserved. See [LICENSE](../LICENSE).", ""]
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["run", "report"])
    parser.add_argument("--trains", type=lambda s: [int(x) for x in s.split(",")], default=[4, 6, 8, 12, 16, 24, 30])
    parser.add_argument("--load", type=lambda s: [float(x) for x in s.split(",")], default=[1.0, 2.0, 3.0, 4.0])
    parser.add_argument("--seeds", type=lambda s: [int(x) for x in s.split(",")], default=[1, 2])
    parser.add_argument("--configs", type=lambda s: s.split(","), default=list(CONFIGS), help=", ".join(CONFIGS))
    parser.add_argument("--objective", default="changes")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--threads", type=int, default=8, help="CP-SAT threads")
    parser.add_argument("--csv", help="results file of run (default: docs/benchmark/<configs>.csv)")
    parser.add_argument("--results", default="docs/benchmark/*.csv", help="results files read by report (glob)")
    parser.add_argument("--output", default="docs/benchmark.md")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.action == "run":
        run(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
