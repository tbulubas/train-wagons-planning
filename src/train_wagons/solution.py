# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Loading plan, a step-by-step simulation of the yard and an independent check."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from train_wagons.instance import WagonKey, YardInstance

TOLERANCE = 1e-6

CRITERIA = ("changes", "lanes", "waiting", "peak", "priority")
DEFAULT_OBJECTIVE = ("changes", "lanes", "waiting", "priority")


class Status(enum.Enum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"


Load = tuple[WagonKey, int]
"""One load step: the wagon (train, position) and the lane it enters, 1 … N."""


@dataclass
class LoadingPlan:
    """Result of one planning run.

    Attributes:
        status: solver status.
        loads: the load steps in loading order.
        method: name of the method that produced the plan.
        stages: one entry per criterion of a lexicographic solve.
    """

    status: Status
    loads: list[Load] = field(default_factory=list)
    method: str = ""
    stages: list[Stage] = field(default_factory=list)

    @property
    def has_plan(self) -> bool:
        return self.status in (Status.OPTIMAL, Status.FEASIBLE)


@dataclass(frozen=True)
class Stage:
    """Result of minimising one criterion.

    Attributes:
        criterion: name of the criterion.
        status: solver status of this stage.
        value: best value found, or None.
        bound: best lower bound proved by the solver, or None.
        seconds: wall time of the stage.
    """

    criterion: str
    status: Status
    value: float | None
    bound: float | None
    seconds: float


@dataclass(frozen=True)
class Metrics:
    """Values of all criteria of the objective (see docs/problem-statement.md)."""

    changes: int
    lanes: int
    waiting: int
    peak: int
    priority: float

    def objective(self, criteria: tuple[str, ...] = DEFAULT_OBJECTIVE) -> tuple[float, ...]:
        """The criteria in priority order, to be compared lexicographically."""
        return tuple(getattr(self, name) for name in parse_objective(criteria))


@dataclass
class Simulation:
    """What happens in the yard when a plan is carried out.

    Attributes:
        errors: violated rules; empty for a valid plan.
        occupancy: wagons in the buffer right after each load step.
        departures: departures[k − 1] is the number of load steps after which
            T_k leaves, or None if it never leaves.
        metrics: the criteria, or None if the plan is invalid.
    """

    errors: list[str]
    occupancy: list[int]
    departures: list[int | None]
    metrics: Metrics | None


def parse_objective(criteria: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Criteria in priority order, from a tuple or a comma-separated string."""
    names = tuple(c.strip() for c in criteria.split(",")) if isinstance(criteria, str) else tuple(criteria)
    unknown = [c for c in names if c not in CRITERIA]
    if unknown or not names or len(set(names)) != len(names):
        raise ValueError(f"objective must be distinct criteria from {', '.join(CRITERIA)}")
    return names


def goods_changes(instance: YardInstance, loads: list[Load]) -> int:
    goods = {w.key: w.goods for w in instance.wagons}
    sequence = [goods[key] for key, _ in loads if key in goods]
    return sum(a != b for a, b in zip(sequence, sequence[1:]))


def train_spreads(instance: YardInstance, loads: list[Load]) -> list[int]:
    """For every train: runs between the first and the last run of its wagons.

    Runs are the maximal blocks of equal goods in the loading order, numbered
    from 1; a train loaded within one run has spread 0.
    """
    goods = {w.key: w.goods for w in instance.wagons}
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    run, previous = 0, None
    for key, _ in loads:
        if goods.get(key) != previous:
            run, previous = run + 1, goods.get(key)
        first.setdefault(key[0], run)
        last[key[0]] = run
    return [last.get(k, 0) - first.get(k, 0) for k in range(1, len(instance.trains) + 1)]


def simulate(instance: YardInstance, plan: LoadingPlan, tol: float = TOLERANCE) -> Simulation:
    """Carry out the loading order and let every train leave as early as possible.

    Train T_k leaves as soon as all its wagons are in the buffer and T_(k−1)
    has left. Works only with the rules of the problem statement,
    independently of any model.
    """
    wagons = {w.key: w for w in instance.wagons}
    sizes = [len(train) for train in instance.trains]
    lanes: list[list[WagonKey]] = [[] for _ in range(instance.lanes)]
    weight = [0.0] * instance.lanes
    loaded: set[WagonKey] = set()
    in_buffer = [0] * len(sizes)
    departures: list[int | None] = [None] * len(sizes)
    occupancy: list[int] = []
    errors: list[str] = []
    next_train = 1
    count = 0

    for step, (key, lane) in enumerate(plan.loads, start=1):
        wagon = wagons.get(key)
        if wagon is None:
            errors.append(f"step {step}: wagon {key} is not in the dispatch plan")
            continue
        if key in loaded:
            errors.append(f"step {step}: wagon {wagon.label} is loaded twice")
            continue
        if not 1 <= lane <= instance.lanes:
            errors.append(f"step {step}: wagon {wagon.label} goes to lane {lane}, outside 1 … {instance.lanes}")
            continue

        queue = lanes[lane - 1]
        if queue and key < queue[-1]:
            back = wagons[queue[-1]]
            errors.append(
                f"step {step}: blocked lane — wagon {wagon.label} enters lane {lane}"
                f" behind {back.label}, which leaves later"
            )
        if weight[lane - 1] + wagon.weight > instance.capacity + tol:
            errors.append(
                f"step {step}: lane {lane} over capacity — wagon {wagon.label} ({wagon.weight:g} t)"
                f" on top of {weight[lane - 1]:g} t, capacity {instance.capacity:g} t"
            )
        queue.append(key)
        weight[lane - 1] += wagon.weight
        loaded.add(key)
        in_buffer[wagon.train - 1] += 1
        count += 1
        occupancy.append(count)

        while next_train <= len(sizes) and in_buffer[next_train - 1] == sizes[next_train - 1]:
            for i, queue in enumerate(lanes):
                leaving = [k for k in queue if k[0] == next_train]
                weight[i] -= sum(wagons[k].weight for k in leaving)
                lanes[i] = [k for k in queue if k[0] != next_train]
            count -= sizes[next_train - 1]
            departures[next_train - 1] = step
            next_train += 1

    missing = [w.label for w in instance.wagons if w.key not in loaded]
    if missing:
        errors.append(f"{len(missing)} wagons are never loaded: {', '.join(missing[:10])}")
    if next_train <= len(sizes):
        errors.append(f"deadlock: train T_{next_train} never leaves")

    metrics = None
    if not errors:
        metrics = Metrics(
            changes=goods_changes(instance, plan.loads),
            lanes=len({lane for _, lane in plan.loads}),
            waiting=sum(occupancy),
            peak=max(occupancy, default=0),
            priority=sum(instance.lane_cost(lane) for _, lane in plan.loads),
        )
    return Simulation(errors, occupancy, departures, metrics)


def verify(instance: YardInstance, plan: LoadingPlan, tol: float = TOLERANCE) -> list[str]:
    """Check a plan against the rules of the problem statement.

    Returns a list of violated rules; an empty list means the plan is valid.
    """
    return simulate(instance, plan, tol).errors
