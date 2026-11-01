# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

import pytest

from train_wagons import LoadingPlan, Metrics, Status, YardInstance, baseline_plan, random_instance, simulate, verify
from train_wagons.heuristic import wave_plan
from train_wagons.solution import parse_objective

# T_1 = grain 10 t, sand 10 t; T_2 = grain 10 t
TWO_TRAINS = ((("grain", 10.0), ("sand", 10.0)), (("grain", 10.0),))


def plan(*loads: tuple[tuple[int, int], int]) -> LoadingPlan:
    return LoadingPlan(Status.FEASIBLE, list(loads), "test")


def test_grouping_goods_across_trains() -> None:
    instance = YardInstance(TWO_TRAINS, lanes=2, capacity=20.0)
    sim = simulate(instance, plan(((1, 1), 1), ((2, 1), 1), ((1, 2), 2)))
    assert sim.errors == []
    assert sim.occupancy == [1, 2, 3]
    assert sim.departures == [3, 3]
    assert sim.metrics == Metrics(changes=1, lanes=2, waiting=6, peak=3, priority=4.0)


def test_train_leaves_as_soon_as_it_is_complete() -> None:
    instance = YardInstance(TWO_TRAINS, lanes=2, capacity=20.0)
    sim = simulate(instance, plan(((1, 1), 1), ((1, 2), 2), ((2, 1), 1)))
    assert sim.errors == []
    assert sim.occupancy == [1, 2, 1]
    assert sim.departures == [2, 3]
    assert sim.metrics == Metrics(changes=2, lanes=2, waiting=4, peak=2, priority=4.0)


def test_blocked_lane() -> None:
    instance = YardInstance(TWO_TRAINS, lanes=2, capacity=20.0)
    errors = verify(instance, plan(((2, 1), 1), ((1, 1), 1), ((1, 2), 2)))
    assert len(errors) == 1 and "blocked lane" in errors[0]


def test_lane_over_capacity() -> None:
    instance = YardInstance(TWO_TRAINS, lanes=2, capacity=15.0)
    errors = verify(instance, plan(((1, 1), 1), ((2, 1), 1), ((1, 2), 2)))
    assert len(errors) == 1 and "over capacity" in errors[0]


def test_capacity_is_freed_by_departure() -> None:
    instance = YardInstance(TWO_TRAINS, lanes=1, capacity=20.0)
    assert verify(instance, plan(((1, 1), 1), ((1, 2), 1), ((2, 1), 1))) == []


def test_missing_wagon_is_a_deadlock() -> None:
    instance = YardInstance(TWO_TRAINS, lanes=2, capacity=20.0)
    errors = verify(instance, plan(((1, 1), 1), ((2, 1), 2)))
    assert any("never loaded: 1.2" in e for e in errors)
    assert any("T_1 never leaves" in e for e in errors)


def test_invalid_steps() -> None:
    instance = YardInstance(TWO_TRAINS, lanes=2, capacity=20.0)
    errors = verify(instance, plan(((1, 1), 1), ((1, 1), 2), ((3, 1), 1), ((1, 2), 3), ((1, 2), 2), ((2, 1), 1)))
    assert len(errors) == 3
    assert "loaded twice" in errors[0]
    assert "not in the dispatch plan" in errors[1]
    assert "outside 1 … 2" in errors[2]


def test_instance_rejects_wagons_heavier_than_a_lane() -> None:
    with pytest.raises(ValueError):
        YardInstance(((("steel", 31.0),),), capacity=30.0)


@pytest.mark.parametrize("seed", range(20))
def test_baseline_is_valid(seed: int) -> None:
    instance = random_instance(trains=12, goods=4, seed=seed)
    result = baseline_plan(instance)
    assert result.status == Status.FEASIBLE
    sim = simulate(instance, result)
    assert sim.errors == []
    assert sim.metrics is not None and sim.metrics.changes >= instance.min_changes
    assert sim.metrics.peak <= max(len(train) for train in instance.trains)


def test_objective_order() -> None:
    metrics = Metrics(changes=3, lanes=5, waiting=40, peak=9, priority=12.0)
    assert metrics.objective() == (3, 5, 40, 12.0)
    assert metrics.objective(parse_objective("changes, peak")) == (3, 9)
    for bad in ("", "changes,changes", "speed"):
        with pytest.raises(ValueError):
            parse_objective(bad)


@pytest.mark.parametrize(("lanes", "seed"), [(lanes, seed) for lanes in (4, 8, 26) for seed in range(8)])
def test_wave_plan_is_valid(lanes: int, seed: int) -> None:
    instance = random_instance(trains=12, lanes=lanes, seed=seed)
    result = wave_plan(instance)
    if result.has_plan:
        sim = simulate(instance, result)
        assert sim.errors == []
        assert sim.metrics is not None and sim.metrics.changes >= instance.min_changes
