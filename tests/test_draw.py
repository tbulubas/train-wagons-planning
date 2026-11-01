# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

from pathlib import Path

import pytest

from train_wagons import YardInstance, baseline_plan, random_instance, simulate
from train_wagons.draw import draw_linkedin, yard_states
from train_wagons.heuristic import wave_plan


@pytest.mark.parametrize("seed", range(5))
def test_yard_states_follow_the_simulation(seed: int) -> None:
    instance = random_instance(trains=6, lanes=6, seed=seed)
    plan = wave_plan(instance)
    sim = simulate(instance, plan)
    states = yard_states(instance, plan)
    loads = [s for s in states if s.event == "load"]
    assert [s.wagon for s in loads] == [key for key, _ in plan.loads]
    assert [sum(map(len, s.lanes)) for s in loads] == sim.occupancy
    # trains leave in order, each assembled position by position from the fronts of the lanes
    leaving = [s.train for s in states if s.event == "leave"]
    assert leaving == list(range(1, len(instance.trains) + 1))
    for before, after in zip(states, states[1:]):
        if after.event == "pull":
            assert before.lanes[after.lane - 1][0] == after.wagon
    assert states[-1].lanes == tuple(() for _ in range(instance.lanes))


def test_draw_linkedin_writes_an_image(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    instance = YardInstance(((("A", 10.0), ("B", 10.0)), (("B", 10.0), ("A", 10.0))), lanes=2, capacity=20.0)
    plan = baseline_plan(instance)
    state = next(s for s in yard_states(instance, plan) if s.event == "pull")
    path = tmp_path / "image.png"
    draw_linkedin(instance, plan, state, str(path), "headline", "subline", ["a", "b", "c"], "footer")
    assert path.stat().st_size > 10_000
