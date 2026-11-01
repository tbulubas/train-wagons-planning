# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Exhaustive search over all loading orders and lanes, for tiny instances.

Independent of the model and of its three facts: every order of the wagons
and every lane for every wagon is tried, the yard is carried out step by step
and every train leaves as soon as it is complete and its predecessor has
left. The only reduction is that lanes never used so far are interchangeable,
so a wagon tries just one of them; the priority of a plan is then evaluated
with the best numbering of its lanes (busiest lane first).
"""

from __future__ import annotations

from train_wagons.instance import YardInstance
from train_wagons.solution import Load, parse_objective


def exhaustive(
    instance: YardInstance, objective: str | tuple[str, ...], spread: int | None = None
) -> tuple[tuple[float, ...], list[Load]]:
    """Lexicographically smallest criteria and one plan that attains them.

    With `spread`, only plans in which the wagons of every train lie within
    spread + 1 consecutive runs (blocks of equal goods) count.
    """
    criteria = parse_objective(objective)
    wagons = instance.wagons
    sizes = [len(train) for train in instance.trains]
    N, K, W = instance.lanes, len(sizes), len(wagons)
    costs = sorted(instance.lane_cost(l) for l in range(1, N + 1))
    best: list = [None, None]

    def spread_ok(loads: list[Load]) -> bool:
        runs: dict[int, list[int]] = {}
        run, previous = 0, None
        for key, _ in loads:
            goods = wagons[sum(sizes[: key[0] - 1]) + key[1] - 1].goods
            if goods != previous:
                run, previous = run + 1, goods
            runs.setdefault(key[0], []).append(run)
        return all(max(r) - min(r) <= spread for r in runs.values())

    def finish(changes: int, used: list[int], waiting: int, peak: int, loads: list[Load]) -> None:
        if spread is not None and not spread_ok(loads):
            return
        groups = sorted((n for n in used if n), reverse=True)
        values = {
            "changes": changes,
            "lanes": len(groups),
            "waiting": waiting,
            "peak": peak,
            "priority": sum(c * n for c, n in zip(costs, groups)),
        }
        key = tuple(values[c] for c in criteria)
        if best[0] is None or key < best[0]:
            best[0], best[1] = key, list(loads)

    def search(
        lanes: list[list[tuple[int, int]]],
        weight: list[float],
        used: list[int],
        left: frozenset[int],
        next_train: int,
        in_buffer: list[int],
        count: int,
        changes: int,
        waiting: int,
        peak: int,
        last: str | None,
        loads: list[Load],
    ) -> None:
        if not left:
            if next_train == K:
                finish(changes, used, waiting, peak, loads)
            return
        for index in sorted(left):
            wagon = wagons[index]
            new_changes = changes + (last is not None and last != wagon.goods)
            if criteria[0] == "changes" and best[0] is not None and new_changes > best[0][0]:
                continue
            opened = False
            for l in range(N):
                if lanes[l] and lanes[l][-1] > wagon.key:
                    continue  # it would stand in front of a wagon needed earlier
                if weight[l] + wagon.weight > instance.capacity + 1e-9:
                    continue
                if not used[l]:
                    if opened:
                        continue
                    opened = True
                lanes2 = [list(q) for q in lanes]
                weight2, used2, in_buffer2 = list(weight), list(used), list(in_buffer)
                lanes2[l].append(wagon.key)
                weight2[l] += wagon.weight
                used2[l] += 1
                in_buffer2[wagon.train - 1] += 1
                occupancy = count + 1
                train = next_train
                after = occupancy
                while train < K and in_buffer2[train] == sizes[train]:
                    for q, queue in enumerate(lanes2):
                        while queue and queue[0][0] == train + 1:
                            key = queue.pop(0)
                            weight2[q] -= wagons[sum(sizes[: key[0] - 1]) + key[1] - 1].weight
                    after -= sizes[train]
                    train += 1
                if any(k[0] == t + 1 for queue in lanes2 for k in queue for t in range(train)):
                    continue  # a train left a wagon behind: some lane was blocked
                search(
                    lanes2, weight2, used2, left - {index}, train, in_buffer2, after,
                    new_changes, waiting + occupancy, max(peak, occupancy), wagon.goods,
                    loads + [(wagon.key, l + 1)],
                )

    search([[] for _ in range(N)], [0.0] * N, [0] * N, frozenset(range(W)), 0, [0] * K, 0, 0, 0, 0, None, [])
    if best[0] is None:
        raise ValueError("instance has no valid plan")
    return best[0], best[1]
