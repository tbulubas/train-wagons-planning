# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

import math
import random

import pytest
from exhaustive import exhaustive

from train_wagons import Status, YardInstance, random_instance, simulate
from train_wagons.model import SYMMETRY, ModelOptions, YardModel, best_heuristic_plan, solve
from train_wagons.solution import train_spreads

SOLVERS = ["scip", "cp-sat"]

# T_1 = A, B and T_2 = B, A, 10 t each; a lane holds two wagons
CROSSED = ((("A", 10.0), ("B", 10.0)), (("B", 10.0), ("A", 10.0)))


def tiny_instance(seed: int) -> YardInstance:
    """2–3 trains, 4–6 wagons, 2–3 goods types, 1–3 lanes.

    The capacity lets the heaviest train fit into the buffer, but usually not
    all wagons at once (load factor 1–2), so that goods have to be repeated.
    """
    rng = random.Random(seed)
    goods = "ABC"[: rng.randint(2, 3)]
    trains: list[list[tuple[str, float]]] = [[] for _ in range(rng.randint(2, 3))]
    for t in range(rng.randint(4, 6)):
        train = trains[t] if t < len(trains) else rng.choice(trains)
        train.append((rng.choice(goods), float(rng.randint(1, 10))))
    lanes = rng.randint(1, 3)
    total = sum(w for train in trains for _, w in train)
    capacity = max(
        max(w for train in trains for _, w in train),
        math.ceil(max(sum(w for _, w in train) for train in trains) / lanes),
        math.ceil(total / lanes / rng.uniform(1.0, 2.0)),
    )
    return YardInstance(tuple(tuple(train) for train in trains), lanes=lanes, capacity=float(capacity))


def check(instance: YardInstance, objective: str, options: ModelOptions) -> None:
    """The model agrees with the exhaustive search, also when no plan exists."""
    plan = solve(instance, objective, options)
    try:
        expected, _ = exhaustive(instance, objective, options.spread)
    except ValueError:
        assert plan.status == Status.INFEASIBLE
        return
    assert plan.status == Status.OPTIMAL
    sim = simulate(instance, plan)
    assert sim.errors == []
    assert sim.metrics is not None
    assert sim.metrics.objective(objective) == pytest.approx(expected)
    # every stage reports the true value of its criterion
    for stage in plan.stages:
        assert stage.value == pytest.approx(getattr(sim.metrics, stage.criterion))


@pytest.mark.parametrize("solver", SOLVERS)
@pytest.mark.parametrize(("lanes", "changes"), [(1, 2), (2, 1)])
def test_crossed_trains(solver: str, lanes: int, changes: int) -> None:
    instance = YardInstance(CROSSED, lanes=lanes, capacity=20.0)
    plan = solve(instance, "changes,lanes", ModelOptions(solver=solver))
    sim = simulate(instance, plan)
    assert sim.errors == [] and sim.metrics is not None
    assert sim.metrics.changes == changes


@pytest.mark.parametrize("solver", SOLVERS)
@pytest.mark.parametrize("seed", range(40))
def test_default_objective_matches_exhaustive_search(solver: str, seed: int) -> None:
    instance = tiny_instance(seed)
    check(instance, "changes,lanes,waiting,priority", ModelOptions(solver=solver, runs=instance.wagon_count))


@pytest.mark.parametrize("objective", ["changes,peak", "waiting,changes", "lanes,changes", "priority,changes"])
@pytest.mark.parametrize("seed", range(10))
def test_other_objectives_match_exhaustive_search(objective: str, seed: int) -> None:
    instance = tiny_instance(100 + seed)
    check(instance, objective, ModelOptions(runs=instance.wagon_count))


@pytest.mark.parametrize("symmetry", ["first", "none"])
@pytest.mark.parametrize("seed", range(10))
def test_symmetry_variants(symmetry: str, seed: int) -> None:
    instance = tiny_instance(200 + seed)
    check(instance, "changes,lanes,waiting", ModelOptions(symmetry=symmetry, runs=instance.wagon_count))


def test_lane_costs_change_the_preferred_lanes() -> None:
    instance = YardInstance(CROSSED, lanes=3, capacity=20.0, lane_costs=(1.0, 1.0, 5.0))
    check(instance, "changes,priority", ModelOptions())


def test_without_aggregated_capacity() -> None:
    instance = tiny_instance(7)
    check(instance, "changes,lanes", ModelOptions(aggregated_capacity=False, runs=instance.wagon_count))


def test_too_few_runs_is_infeasible() -> None:
    instance = YardInstance(CROSSED, lanes=1, capacity=20.0)
    assert solve(instance, "changes", ModelOptions(runs=2)).status == Status.INFEASIBLE


def test_lookahead_zero_loads_train_by_train() -> None:
    instance = YardInstance(CROSSED, lanes=2, capacity=20.0)
    plan = solve(instance, "changes", ModelOptions(lookahead=0))
    sim = simulate(instance, plan)
    assert sim.errors == [] and sim.metrics is not None
    assert sim.metrics.changes == 2  # 2.2 may not wait for T_1 any more
    assert sim.metrics.peak == 2


def test_first_symmetry_rejects_priority() -> None:
    instance = YardInstance(CROSSED, lanes=2, capacity=20.0)
    with pytest.raises(ValueError):
        YardModel(instance, ModelOptions(symmetry="first")).solve("changes,priority")


@pytest.mark.parametrize("solver", SOLVERS)
@pytest.mark.parametrize("seed", range(10))
def test_start_from_heuristic_plan(solver: str, seed: int) -> None:
    instance = tiny_instance(300 + seed)
    check(instance, "changes,lanes,waiting,priority", ModelOptions(solver=solver, start=True))


@pytest.mark.parametrize("symmetry", SYMMETRY)
def test_hint_is_a_valid_assignment(symmetry: str) -> None:
    instance = random_instance(trains=4, lanes=6, seed=3)
    model = YardModel(instance, ModelOptions(symmetry=symmetry))
    start = best_heuristic_plan(instance)
    assert start is not None
    variables, values = model.hint(start)
    for var, value in zip(variables, values):  # fix the hinted values: the model must stay feasible
        var.SetBounds(value, value)
    plan = model.solve("changes")
    assert plan.status == Status.OPTIMAL
    assert simulate(instance, plan).errors == []


THREE_TRAINS = ((("A", 10.0), ("B", 10.0)), (("B", 10.0), ("A", 10.0)), (("A", 10.0),))


@pytest.mark.parametrize("solver", SOLVERS)
def test_example_of_the_model_documentation(solver: str) -> None:
    """The three trains of docs/mip-model.md, "Example: three trains"."""
    instance = YardInstance(THREE_TRAINS, lanes=2, capacity=30.0)
    plan = solve(instance, "changes,lanes,waiting,priority", ModelOptions(solver=solver, runs=5))
    assert plan.status == Status.OPTIMAL
    assert plan.loads == [((1, 2), 1), ((2, 1), 1), ((1, 1), 2), ((2, 2), 1), ((3, 1), 1)]
    sim = simulate(instance, plan)
    assert sim.errors == []
    assert sim.occupancy == [1, 2, 3, 2, 1]
    assert sim.departures == [3, 4, 5]
    assert sim.metrics is not None
    assert (sim.metrics.changes, sim.metrics.lanes, sim.metrics.waiting, sim.metrics.peak) == (1, 2, 9, 3)
    assert sim.metrics.priority == 6



@pytest.mark.parametrize("solver", SOLVERS)
@pytest.mark.parametrize("seed", range(20))
def test_spread_matches_exhaustive_search(solver: str, seed: int) -> None:
    instance = tiny_instance(400 + seed)
    smallest = max(len({goods for goods, _ in train}) for train in instance.trains) - 1
    check(instance, "changes,lanes,waiting", ModelOptions(solver=solver, spread=smallest, runs=instance.wagon_count))


@pytest.mark.parametrize("solver", SOLVERS)
def test_spread_can_cost_changes(solver: str) -> None:
    instance = tiny_instance(643)  # found by the exhaustive search: spread 1 forces a third change
    free = solve(instance, "changes", ModelOptions(solver=solver, runs=instance.wagon_count))
    tight = solve(instance, "changes", ModelOptions(solver=solver, spread=1, runs=instance.wagon_count))
    assert free.stages[0].value == 2 and tight.stages[0].value == 3
    assert max(train_spreads(instance, tight.loads)) <= 1 < max(train_spreads(instance, free.loads))
    check(instance, "changes,lanes,waiting", ModelOptions(solver=solver, spread=1, runs=instance.wagon_count))


def test_too_small_spread_is_rejected() -> None:
    instance = YardInstance(CROSSED, lanes=2, capacity=20.0)
    with pytest.raises(ValueError, match="spread 0 is too small"):
        YardModel(instance, ModelOptions(spread=0))
