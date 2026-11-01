# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Command line interface: plan one random instance and print the loading order."""

from __future__ import annotations

import argparse
import sys
from itertools import groupby

from train_wagons.baseline import baseline_plan
from train_wagons.heuristic import wave_plan
from train_wagons.viewer import write_viewer
from train_wagons.instance import YardInstance, random_instance
from train_wagons.model import SOLVERS, SYMMETRY, ModelOptions, YardModel
from train_wagons.solution import CRITERIA, DEFAULT_OBJECTIVE, LoadingPlan, parse_objective, simulate, train_spreads


def format_instance(instance: YardInstance) -> str:
    return (
        f"instance: {len(instance.trains)} trains, {instance.wagon_count} wagons,"
        f" {len(instance.goods_types)} goods types ({', '.join(instance.goods_types)}),"
        f" {instance.lanes} lanes of {instance.capacity:g} t, load factor {instance.load_factor:.2f}"
    )


def format_plan(instance: YardInstance, plan: LoadingPlan, objective: tuple[str, ...] = DEFAULT_OBJECTIVE) -> str:
    lines = [f"plan: {plan.method}, status {plan.status.value}"]
    for stage in plan.stages:
        value = "—" if stage.value is None else f"{stage.value:g}"
        bound = "" if stage.bound is None else f", bound {stage.bound:g}"
        lines.append(f"  {stage.criterion:<8} {value}{bound}  ({stage.status.value}, {stage.seconds:.1f} s)")
    if not plan.has_plan:
        return "\n".join(lines)

    sim = simulate(instance, plan)
    if sim.metrics is not None:
        m = sim.metrics
        lines.append(
            f"changes {m.changes} (at least {instance.min_changes}), lanes {m.lanes},"
            f" waiting {m.waiting}, peak {m.peak}, priority {m.priority:g},"
            f" largest spread of a train {max(train_spreads(instance, plan.loads))} runs"
        )
        lines.append(f"objective ({', '.join(objective)}): {m.objective(objective)}")

    wagons = {w.key: w for w in instance.wagons}
    leaving = {step: k for k, step in enumerate(sim.departures, start=1) if step is not None}
    lines.append("loading order (train.position→lane), one line per block of goods:")
    step = 0
    for goods, block in groupby(plan.loads, key=lambda load: wagons[load[0]].goods):
        items = []
        for key, lane in block:
            step += 1
            items.append(f"{wagons[key].label}→{lane}")
            if step in leaving:
                items.append(f"[T_{leaving[step]} leaves]")
        lines.append(f"  {goods:<7} {' '.join(items)}")

    lines.append("check: OK" if not sim.errors else "check FAILED:\n  " + "\n  ".join(sim.errors))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Plan the loading order of train wagons.")
    parser.add_argument("--trains", "-K", type=int, default=4, help="number of trains K")
    parser.add_argument("--min-wagons", type=int, default=5, help="minimal wagons per train")
    parser.add_argument("--max-wagons", type=int, default=15, help="maximal wagons per train")
    parser.add_argument("--goods", "-G", type=int, default=4, help="number of goods types G")
    parser.add_argument("--heavy-share", type=float, default=0.5, help="share of heavy wagons (4–14 t)")
    parser.add_argument("--lanes", "-N", type=int, default=26, help="number of lanes N")
    parser.add_argument("--capacity", "-M", type=float, default=30.0, help="load capacity of a lane M [t]")
    parser.add_argument("--seed", type=int, default=1, help="seed of the random instance")
    parser.add_argument(
        "--objective",
        default=",".join(DEFAULT_OBJECTIVE),
        help=f"criteria in priority order, from {', '.join(CRITERIA)}",
    )
    parser.add_argument("--solver", choices=["baseline", "waves", *SOLVERS], default="cp-sat", help="heuristic plan or MILP solver")
    parser.add_argument("--time-limit", type=float, default=30.0, help="seconds per criterion")
    parser.add_argument("--runs", "-R", type=int, help="run slots R (default: runs of the best heuristic plan)")
    parser.add_argument("--lookahead", "-H", type=int, help="load wagons at most H trains ahead (default: no limit)")
    parser.add_argument("--spread", "-S", type=int, help="at most S runs between the first and last run of a train")
    parser.add_argument("--max-lanes", type=int, help="lanes in the model (default: N)")
    parser.add_argument("--symmetry", choices=SYMMETRY, default="size", help="symmetry breaking of the lanes")
    parser.add_argument("--start", action="store_true", help="start from the best heuristic plan")
    parser.add_argument("--html", metavar="FILE", help="write an interactive viewer of the plan to FILE")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page

    objective = parse_objective(args.objective)
    instance = random_instance(
        trains=args.trains,
        min_wagons=args.min_wagons,
        max_wagons=args.max_wagons,
        goods=args.goods,
        heavy_share=args.heavy_share,
        lanes=args.lanes,
        capacity=args.capacity,
        seed=args.seed,
    )
    print(format_instance(instance))
    if args.solver == "baseline":
        plan = baseline_plan(instance)
    elif args.solver == "waves":
        plan = wave_plan(instance)
    else:
        options = ModelOptions(
            runs=args.runs,
            max_lanes=args.max_lanes,
            lookahead=args.lookahead,
            spread=args.spread,
            symmetry=args.symmetry,
            solver=args.solver,
            time_limit=args.time_limit,
            start=args.start,
        )
        try:
            model = YardModel(instance, options)
        except ValueError as error:
            parser.error(str(error))
        size = model.size
        print(f"model: R = {model.runs}, {size['variables']} variables, {size['constraints']} constraints")
        plan = model.solve(objective)
    print(format_plan(instance, plan, objective))
    if args.html and plan.has_plan:
        print(f"viewer: {write_viewer(instance, plan, args.html)}")


if __name__ == "__main__":
    main()
