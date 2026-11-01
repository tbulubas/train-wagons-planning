# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Reference plan: load train by train, grouped by goods within each train.

Each train is loaded completely and leaves before the next one is started,
so the buffer only ever holds one train. Within a train the wagons are loaded
in blocks of one goods type each, in position order; the block of the goods
type loaded last for the previous train comes first. The plan gives an upper
bound for the model and a starting point for comparisons; it is not optimal.
"""

from __future__ import annotations

from train_wagons.instance import Wagon, YardInstance
from train_wagons.solution import TOLERANCE, Load, LoadingPlan, Status


def _choose_lane(wagon: Wagon, backs: list[tuple[int, int]], weight: list[float], capacity: float) -> int | None:
    """Lane whose last wagon is the latest one before `wagon` and that has room.

    Empty lanes have the back key (0, 0), so lanes in use are preferred and
    new lanes are opened in index order. Returns a 0-based index or None.
    """
    best = None
    for i, back in enumerate(backs):
        if back < wagon.key and weight[i] + wagon.weight <= capacity + TOLERANCE:
            if best is None or back > backs[best]:
                best = i
    return best


def baseline_plan(instance: YardInstance) -> LoadingPlan:
    loads: list[Load] = []
    last_goods: str | None = None
    by_train: dict[int, list[Wagon]] = {}
    for wagon in instance.wagons:
        by_train.setdefault(wagon.train, []).append(wagon)

    for train in by_train.values():
        types = sorted({w.goods for w in train}, key=lambda g: (g != last_goods, g))
        backs = [(0, 0)] * instance.lanes
        weight = [0.0] * instance.lanes
        for goods in types:
            for wagon in (w for w in train if w.goods == goods):
                lane = _choose_lane(wagon, backs, weight, instance.capacity)
                if lane is None:
                    return LoadingPlan(Status.INFEASIBLE, loads, "baseline")
                backs[lane] = wagon.key
                weight[lane] += wagon.weight
                loads.append((wagon.key, lane + 1))
        last_goods = types[-1]

    return LoadingPlan(Status.FEASIBLE, loads, "baseline")
