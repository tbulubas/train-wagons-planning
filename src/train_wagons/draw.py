# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Snapshots of the yard while a plan is carried out, and their drawing with matplotlib."""

from __future__ import annotations

from dataclasses import dataclass

from train_wagons.instance import WagonKey, YardInstance
from train_wagons.solution import LoadingPlan

PALETTE = ("#8ecae6", "#ffb703", "#90be6d", "#f4978e", "#cdb4db", "#bde0fe", "#e9c46a", "#a8dadc")


@dataclass(frozen=True)
class YardState:
    """The yard right after one event of a plan.

    Attributes:
        event: "start", "load" (a wagon enters a lane), "pull" (a wagon goes
            from the front of its lane to the departure track) or "leave".
        wagon: the wagon of a load or pull event.
        lane: the lane of a load or pull event, numbered from 1.
        train: the train under assembly or leaving.
        lanes: the wagons in every lane, front (next to leave) first.
        track: the wagons on the departure track, position 1 first.
        departed: the trains that have left.
        loaded: number of wagons loaded so far.
        run: number of the current run of equal goods, 0 before the first load.
    """

    event: str
    wagon: WagonKey | None
    lane: int | None
    train: int | None
    lanes: tuple[tuple[WagonKey, ...], ...]
    track: tuple[WagonKey, ...]
    departed: tuple[int, ...]
    loaded: int
    run: int


def yard_states(instance: YardInstance, plan: LoadingPlan) -> list[YardState]:
    """Replay a plan event by event; every train leaves as soon as it can."""
    goods = {w.key: w.goods for w in instance.wagons}
    sizes = [len(train) for train in instance.trains]
    lanes: list[list[WagonKey]] = [[] for _ in range(instance.lanes)]
    lane_of: dict[WagonKey, int] = {}
    in_buffer = [0] * len(sizes)
    departed: list[int] = []
    states: list[YardState] = []
    run, last, next_train, track, loaded = 0, None, 1, [], 0

    def snap(event: str, wagon: WagonKey | None = None, lane: int | None = None, train: int | None = None) -> None:
        states.append(YardState(event, wagon, lane, train, tuple(map(tuple, lanes)), tuple(track), tuple(departed),
                                loaded, run))

    snap("start")
    for key, lane in plan.loads:
        if goods[key] != last:
            run, last = run + 1, goods[key]
        lanes[lane - 1].append(key)
        lane_of[key] = lane
        in_buffer[key[0] - 1] += 1
        loaded += 1
        snap("load", key, lane)
        while next_train <= len(sizes) and in_buffer[next_train - 1] == sizes[next_train - 1]:
            track = []
            for position in range(1, sizes[next_train - 1] + 1):
                wagon = (next_train, position)
                lanes[lane_of[wagon] - 1].remove(wagon)
                track.append(wagon)
                snap("pull", wagon, lane_of[wagon], next_train)
            departed.append(next_train)
            snap("leave", train=next_train)
            track = []
            next_train += 1
    return states


def goods_colors(instance: YardInstance) -> dict[str, str]:
    return {g: PALETTE[n % len(PALETTE)] for n, g in enumerate(instance.goods_types)}


def draw_linkedin(
    instance: YardInstance,
    plan: LoadingPlan,
    state: YardState,
    path: str,
    headline: str,
    subline: str,
    facts: list[str],
    footer: str,
) -> None:
    """A 2400 × 1350 px image: port, buffer lanes and departure track in one snapshot."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    colors = goods_colors(instance)
    weight = {w.key: w.weight for w in instance.wagons}
    goods = {w.key: w.goods for w in instance.wagons}
    fig = plt.figure(figsize=(12, 6.75), dpi=200)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 240)
    ax.set_ylim(0, 135)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    def box(x, y, w, h, face, edge="#555555", lw=1.0, radius=0.8, z=2):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
                                    facecolor=face, edgecolor=edge, linewidth=lw, zorder=z))

    def wagon(key, x, y, w, h, highlight=False, size=8.5):
        box(x, y, w, h, colors[goods[key]], "#c1121f" if highlight else "#444444", 2.4 if highlight else 0.8)
        ax.text(x + w / 2, y + h / 2, f"{key[0]}.{key[1]}", ha="center", va="center", fontsize=size, zorder=3)

    # headline
    ax.text(120, 127, headline, ha="center", va="center", fontsize=25, fontweight="bold", color="#1d3557")
    ax.text(120, 119, subline, ha="center", va="center", fontsize=12.5, color="#555555")

    # port: the wagon just loaded and the next ones
    ax.text(6, 109, "PORT · loading track", fontsize=11, fontweight="bold", color="#333333")
    if state.loaded:
        current = goods[plan.loads[state.loaded - 1][0]]
        ax.text(6, 104.5, f"run {state.run} · loading {current}", fontsize=9, color="#666666")
    y = 96
    upcoming = plan.loads[state.loaded:state.loaded + 9]
    for key, lane in upcoming:
        wagon(key, 6, y, 11, 5.6)
        ax.text(18.5, y + 2.8, f"→ lane {lane}", va="center", fontsize=8.5, color="#444444")
        y -= 7.4
    if len(plan.loads) > state.loaded + len(upcoming):
        ax.text(6, y + 3.5, f"… {len(plan.loads) - state.loaded - len(upcoming)} more", fontsize=8.5, color="#666666")

    # buffer: front of every lane on the right, next to the departure track
    n = instance.lanes
    top, bottom = 102.0, 26.0
    row = (top - bottom) / n
    lane_x, lane_w = 62.0, 120.0
    ax.text(lane_x, 109, f"BUFFER · {n} FIFO lanes of {instance.capacity:g} t — wagons enter left, leave right",
            fontsize=11, fontweight="bold", color="#333333")
    slot, gap = 9.2, 0.7
    for lane in range(1, n + 1):
        ly = top - lane * row
        queue = state.lanes[lane - 1]
        load = sum(weight[k] for k in queue)
        box(lane_x, ly + 0.4, lane_w, row - 0.8, "#f1f3f5" if lane % 2 else "#e9ecef", "none", 0, radius=0.6, z=1)
        ax.text(lane_x - 13.5, ly + row / 2, f"lane {lane}", ha="right", va="center", fontsize=9, color="#444444")
        share = min(load / instance.capacity, 1.0)
        box(lane_x - 12, ly + row * 0.25, 10, row * 0.5, "white", "#999999", 0.6, radius=0.3)
        full = round(load) >= instance.capacity  # red exactly when the label reads as full
        fill = "#d62828" if full else "#f4a261" if share > 0.85 else "#90be6d"
        if share > 0:
            box(lane_x - 12, ly + row * 0.25, 10 * share, row * 0.5, fill, "none", 0, radius=0.3)
        ax.text(lane_x - 7, ly + row / 2, f"{load:.0f} t", ha="center", va="center", fontsize=6.5, zorder=4)
        for j, key in enumerate(queue[: int(lane_w // (slot + gap))]):
            x = lane_x + lane_w - (j + 1) * (slot + gap)
            wagon(key, x, ly + row * 0.14, slot, row * 0.72, highlight=key == state.wagon, size=7.5)
    ax.add_patch(FancyArrowPatch((lane_x + lane_w + 1.5, (top + bottom) / 2), (190, (top + bottom) / 2),
                                 arrowstyle="-|>", mutation_scale=18, color="#888888", lw=1.5))

    # departure track: the train under assembly, position 1 right behind the locomotive
    k = state.train
    ax.text(192, 109, "DEPARTURE TRACK", fontsize=11, fontweight="bold", color="#333333")
    if k is not None:
        total = len(instance.trains[k - 1])
        h = min(6.0, 70 / (total + 1))
        box(192, 100 - h, 32, h - 0.8, "#343a40", "#343a40")
        ax.text(208, 100 - h / 2 - 0.4, f"T_{k}  locomotive", ha="center", va="center", fontsize=8.5, color="white")
        for q, key in enumerate(state.track, start=1):
            wagon(key, 192, 100 - (q + 1) * h, 32, h - 0.8, highlight=key == state.wagon)
        ax.text(192, 100 - (len(state.track) + 1) * h - 3.5, f"{len(state.track)} of {total} wagons, taken from"
                "\nthe fronts of the lanes", fontsize=8.5, color="#555555", va="top")
    ax.text(192, 26, "left: " + (" ".join(f"T_{t}" for t in state.departed) or "—"), fontsize=9, color="#555555")

    # legend of the goods types
    x = 62.0
    for g, c in colors.items():
        box(x, 20.2, 3.2, 2.6, c, "#555555", 0.6, radius=0.3)
        ax.text(x + 4.2, 21.5, g, va="center", fontsize=9)
        x += 6 + 1.6 * len(g)

    # facts and footer
    fx, fw = 6.0, 74.0
    for fact in facts:
        box(fx, 4.5, fw - 2, 11.5, "#f8f9fa", "#adb5bd", 0.8, radius=1.0)
        ax.text(fx + (fw - 2) / 2, 10.25, fact, ha="center", va="center", fontsize=10, color="#222222", wrap=True)
        fx += fw + 3
    ax.text(234, 0.8, footer, ha="right", va="bottom", fontsize=9, color="#888888")
    fig.savefig(path, dpi=200, facecolor="white")
    plt.close(fig)
