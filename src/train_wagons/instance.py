# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Input data: the dispatch plan and the buffer (weights in tonnes)."""

from __future__ import annotations

import random
from dataclasses import dataclass

GOODS = ("grain", "diesel", "sand", "timber", "coal", "steel", "salt", "ore")

WagonKey = tuple[int, int]
"""(train, position), both counted from 1; also the order of extraction."""


@dataclass(frozen=True)
class Wagon:
    """One wagon of the dispatch plan.

    Attributes:
        train: index k of its train, 1 = first train to leave.
        position: position in the train, 1 = right behind the locomotive.
        goods: goods type of its load.
        weight: load weight in tonnes (the empty wagon is neglected).
    """

    train: int
    position: int
    goods: str
    weight: float

    @property
    def key(self) -> WagonKey:
        return (self.train, self.position)

    @property
    def label(self) -> str:
        return f"{self.train}.{self.position}"


@dataclass(frozen=True)
class YardInstance:
    """Dispatch plan and buffer of the problem statement.

    Attributes:
        trains: T_1 … T_K; each train as the tuple of (goods, weight) of its
            wagons from the locomotive.
        lanes: N, number of FIFO lanes of the buffer, numbered by priority.
        capacity: M, load capacity of one lane in tonnes.
        lane_costs: c(1) … c(N), shunting cost of taking a wagon out of each
            lane, non-decreasing; None means c(ℓ) = ℓ.
    """

    trains: tuple[tuple[tuple[str, float], ...], ...]
    lanes: int = 26
    capacity: float = 30.0
    lane_costs: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if self.lanes <= 0:
            raise ValueError("lanes must be positive")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if self.lane_costs is not None:
            costs = self.lane_costs
            if len(costs) != self.lanes or costs[0] < 0 or any(a > b for a, b in zip(costs, costs[1:])):
                raise ValueError("lane_costs must be N non-negative, non-decreasing values")
        if not self.trains or any(not train for train in self.trains):
            raise ValueError("every train needs at least one wagon")
        for wagon in self.wagons:
            if not 0 < wagon.weight <= self.capacity:
                raise ValueError(f"wagon {wagon.label} must weigh more than 0 and at most the capacity")

    @property
    def wagons(self) -> list[Wagon]:
        """All wagons in the order in which they leave the buffer."""
        return [
            Wagon(k, p, goods, weight)
            for k, train in enumerate(self.trains, start=1)
            for p, (goods, weight) in enumerate(train, start=1)
        ]

    @property
    def wagon_count(self) -> int:
        return sum(len(train) for train in self.trains)

    @property
    def goods_types(self) -> list[str]:
        return sorted({goods for train in self.trains for goods, _ in train})

    def train_weight(self, k: int) -> float:
        return sum(weight for _, weight in self.trains[k - 1])

    def lane_cost(self, lane: int) -> float:
        """c(ℓ) for a lane numbered from 1."""
        return float(lane) if self.lane_costs is None else self.lane_costs[lane - 1]

    @property
    def load_factor(self) -> float:
        """λ = total load weight / (N · M); above 1 not all wagons fit at once."""
        return sum(map(self.train_weight, range(1, len(self.trains) + 1))) / (self.lanes * self.capacity)

    @property
    def min_changes(self) -> int:
        """Lower bound G − 1 on the number of changes of goods type."""
        return len(self.goods_types) - 1


def random_instance(
    trains: int = 10,
    min_wagons: int = 5,
    max_wagons: int = 15,
    goods: int = 4,
    heavy_share: float = 0.5,
    lanes: int = 26,
    capacity: float = 30.0,
    seed: int | None = None,
) -> YardInstance:
    """Random dispatch plan with typical wagons.

    Heavy wagons carry 4–14 t, light ones 0.2–1 t (rounded to 0.1 t); the
    goods type and the weight class of every wagon are drawn independently.
    """
    if not 1 <= goods <= len(GOODS):
        raise ValueError(f"goods must be between 1 and {len(GOODS)}")
    if not 1 <= min_wagons <= max_wagons:
        raise ValueError("wagon counts must satisfy 1 <= min_wagons <= max_wagons")
    rng = random.Random(seed)
    types = GOODS[:goods]

    def wagon() -> tuple[str, float]:
        low, high = (4.0, 14.0) if rng.random() < heavy_share else (0.2, 1.0)
        return rng.choice(types), round(rng.uniform(low, min(high, capacity)), 1)

    plan = tuple(
        tuple(wagon() for _ in range(rng.randint(min_wagons, max_wagons))) for _ in range(trains)
    )
    return YardInstance(plan, lanes, capacity)
