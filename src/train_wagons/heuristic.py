# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Heuristic plan in waves: consecutive trains loaded together, goods type by goods type.

A wave is a group of consecutive trains. Its wagons are loaded in one run per
goods type, each run in key order (fact 1 of docs/mip-model.md); the goods
type loaded last in one wave comes first in the next, so the two runs merge.
Every wagon goes to the lane whose last wagon is the latest one before it
and that has room, and trains leave as soon as they are complete. A wave is
grown train by train as long as this greedy loading still succeeds.

The plan gives an upper bound on the changes, a value for the number of run
slots R of the model, and a starting point; it is not optimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from train_wagons.instance import Wagon, WagonKey, YardInstance
from train_wagons.solution import TOLERANCE, Load, LoadingPlan, Status


@dataclass
class _Yard:
    """Buffer state while loading greedily, with departures as early as possible."""

    instance: YardInstance
    lanes: list[list[Wagon]] = field(default_factory=list)
    weight: list[float] = field(default_factory=list)
    backs: list[WagonKey] = field(default_factory=list)
    in_buffer: list[int] = field(default_factory=list)
    next_train: int = 1
    loads: list[Load] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = self.instance.lanes
        self.lanes = [[] for _ in range(n)]
        self.weight = [0.0] * n
        self.backs = [(0, 0)] * n
        self.in_buffer = [0] * len(self.instance.trains)

    def copy(self) -> _Yard:
        yard = _Yard(self.instance)
        yard.lanes = [list(q) for q in self.lanes]
        yard.weight = list(self.weight)
        yard.backs = list(self.backs)
        yard.in_buffer = list(self.in_buffer)
        yard.next_train = self.next_train
        yard.loads = list(self.loads)
        return yard

    def load(self, wagon: Wagon) -> bool:
        best = None
        for i, back in enumerate(self.backs):
            if back < wagon.key and self.weight[i] + wagon.weight <= self.instance.capacity + TOLERANCE:
                if best is None or back > self.backs[best]:
                    best = i
        if best is None:
            return False
        self.lanes[best].append(wagon)
        self.weight[best] += wagon.weight
        self.backs[best] = wagon.key
        self.in_buffer[wagon.train - 1] += 1
        self.loads.append((wagon.key, best + 1))
        sizes = [len(train) for train in self.instance.trains]
        while self.next_train <= len(sizes) and self.in_buffer[self.next_train - 1] == sizes[self.next_train - 1]:
            for i, queue in enumerate(self.lanes):
                while queue and queue[0].train == self.next_train:
                    self.weight[i] -= queue.pop(0).weight
            self.next_train += 1
        return True


def _wave_orders(wagons: list[Wagon], first: str | None) -> list[list[Wagon]]:
    """Loading orders with one run per goods type, the most promising first.

    The goods type `first` (if present) opens the wave, so that it merges with
    the last run of the previous wave; the others follow, lighter types first,
    then in every other order.
    """
    totals: dict[str, float] = {}
    for w in wagons:
        totals[w.goods] = totals.get(w.goods, 0.0) + w.weight
    rest = sorted((g for g in totals if g != first), key=lambda g: (totals[g], g))
    head = [first] if first in totals else []
    orders = []
    for perm in permutations(rest):
        orders.append([w for g in head + list(perm) for w in sorted((w for w in wagons if w.goods == g), key=lambda w: w.key)])
    return orders


def wave_plan(instance: YardInstance) -> LoadingPlan:
    by_train: dict[int, list[Wagon]] = {}
    for wagon in instance.wagons:
        by_train.setdefault(wagon.train, []).append(wagon)
    K = len(instance.trains)

    yard = _Yard(instance)
    last: str | None = None
    start = 1
    while start <= K:
        accepted: tuple[int, _Yard, str] | None = None
        for end in range(start, K + 1):
            wagons = [w for k in range(start, end + 1) for w in by_train[k]]
            for order in _wave_orders(wagons, last):
                trial = yard.copy()
                if all(trial.load(w) for w in order):
                    accepted = (end, trial, order[-1].goods)
                    break
            else:
                break
        if accepted is None:
            return LoadingPlan(Status.INFEASIBLE, yard.loads, "waves")
        end, yard, last = accepted
        start = end + 1
    return LoadingPlan(Status.FEASIBLE, yard.loads, "waves")
