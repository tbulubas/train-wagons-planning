# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Render the LinkedIn image: one snapshot of an optimal plan while a train is assembled."""

from __future__ import annotations

import sys
from pathlib import Path

from train_wagons import Status, random_instance, simulate
from train_wagons.draw import draw_linkedin, yard_states
from train_wagons.model import ModelOptions, solve

OUTPUT = Path(__file__).resolve().parent.parent / "images" / "train-wagons-linkedin.png"


def main() -> None:
    instance = random_instance(trains=8, min_wagons=6, max_wagons=11, lanes=8, seed=5)
    # one thread: CP-SAT then finds the same optimal plan on every run, so the image does not change
    options = ModelOptions(solver="cp-sat", start=True, time_limit=120, threads=1)
    plan = solve(instance, "changes,lanes", options)
    sim = simulate(instance, plan)
    if sim.errors or sim.metrics is None:
        sys.exit("invalid plan: " + "; ".join(sim.errors))
    if plan.status != Status.OPTIMAL:
        sys.exit(f"the plan is not proved optimal ({plan.status.value}); the subline would be wrong")

    # a moment in the middle of assembling a train, with as many wagons in the buffer as possible
    states = yard_states(instance, plan)
    def fullness(state) -> tuple[int, int]:
        total = len(instance.trains[state.train - 1])
        return sum(map(len, state.lanes)), -abs(2 * len(state.track) - total)
    candidates = [s for s in states if s.event == "pull" and 2 <= len(s.track) < len(instance.trains[s.train - 1])]
    state = max(candidates, key=fullness)

    m = sim.metrics
    OUTPUT.parent.mkdir(exist_ok=True)
    draw_linkedin(
        instance,
        plan,
        state,
        str(OUTPUT),
        headline="In which order should the wagons be loaded?",
        subline=f"{len(instance.trains)} trains · {instance.wagon_count} wagons · {len(instance.goods_types)} goods types"
                f" · optimal plan: {m.changes} changes of goods, {m.lanes} lanes — one MILP, solved with CP-SAT",
        facts=[
            "One MILP: a run of equal goods\nand a FIFO lane for every wagon",
            "SCIP stalls at the trivial LP bound,\nCP-SAT proves optima up to ~80 wagons",
            "Next: loading times and a timetable.\nMIP or CP — how would you model it?",
        ],
        footer="github.com/tbulubas/train-wagons-planning",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
