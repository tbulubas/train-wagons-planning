# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""The MILP of docs/mip-model.md, solved lexicographically with SCIP or CP-SAT.

Numbers in comments refer to the constraints in docs/mip-model.md. Wagons are
indexed 0 … W−1 in extraction order, runs 0 … R−1 and lanes 0 … N−1; run r
has the number r + 1 in r(i), lane ℓ the number ℓ + 1 in the plan.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ortools.linear_solver import pywraplp

from train_wagons.baseline import baseline_plan
from train_wagons.heuristic import wave_plan
from train_wagons.instance import YardInstance
from train_wagons.solution import (
    DEFAULT_OBJECTIVE,
    Load,
    LoadingPlan,
    Stage,
    Status,
    goods_changes,
    parse_objective,
    simulate,
    train_spreads,
)

SOLVERS = {"scip": "SCIP", "cp-sat": "CP_SAT"}
SYMMETRY = ("size", "first", "none")
WEIGHT_SCALE = 1000
"""Weights enter the model in kilograms, so that all data are integers."""

_STATUS = {
    pywraplp.Solver.OPTIMAL: Status.OPTIMAL,
    pywraplp.Solver.FEASIBLE: Status.FEASIBLE,
    pywraplp.Solver.INFEASIBLE: Status.INFEASIBLE,
}


@dataclass(frozen=True)
class ModelOptions:
    """How the model is built and solved.

    Attributes:
        runs: R, the number of run slots; None takes the runs of the better
            of the wave plan and the reference plan, so that a plan exists.
        max_lanes: N̄ ≤ N lanes in the model; None uses all N.
        lookahead: H, how many trains ahead a wagon may be loaded; None is exact.
        spread: S, at most S runs between the first and the last run of the
            wagons of one train (16); None for no limit.
        symmetry: "size" orders the lanes by their number of wagons (14),
            "first" by their first wagon (14a)–(14b), "none" adds neither.
        aggregated_capacity: add the sum of the lane capacities (15).
        solver: "scip" or "cp-sat".
        time_limit: seconds per criterion, None for no limit.
        threads: number of solver threads, None for the solver's default.
        start: start the first criterion from the best heuristic plan.
    """

    runs: int | None = None
    max_lanes: int | None = None
    lookahead: int | None = None
    spread: int | None = None
    symmetry: str = "size"
    aggregated_capacity: bool = True
    solver: str = "cp-sat"
    time_limit: float | None = None
    threads: int | None = None
    start: bool = False


def _admitted(instance: YardInstance, plan: LoadingPlan, options: ModelOptions) -> bool:
    """Whether a valid plan also obeys the restrictions max_lanes, lookahead and spread."""
    if options.max_lanes is not None and max(lane for _, lane in plan.loads) > options.max_lanes:
        return False
    if options.spread is not None and max(train_spreads(instance, plan.loads)) > options.spread:
        return False
    if options.lookahead is not None:
        departures = simulate(instance, plan).departures
        for step, ((train, _), _) in enumerate(plan.loads, start=1):
            earlier = train - options.lookahead - 1
            if earlier >= 1 and (departures[earlier - 1] or 0) >= step:
                return False
    return True


def best_heuristic_plan(instance: YardInstance, options: ModelOptions = ModelOptions()) -> LoadingPlan | None:
    """The wave plan or the reference plan, whichever has fewer changes and fits the options."""
    plans = [plan for plan in (wave_plan(instance), baseline_plan(instance)) if plan.has_plan]
    plans = [plan for plan in plans if _admitted(instance, plan, options)]
    return min(plans, key=lambda plan: goods_changes(instance, plan.loads), default=None)


def default_runs(instance: YardInstance, options: ModelOptions = ModelOptions()) -> int:
    """Runs of the best heuristic plan; every number of runs ≥ this admits a plan."""
    plan = best_heuristic_plan(instance, options)
    return instance.wagon_count if plan is None else goods_changes(instance, plan.loads) + 1


class YardModel:
    """The model of one instance; `solve` minimises the criteria in turn."""

    def __init__(self, instance: YardInstance, options: ModelOptions = ModelOptions()) -> None:
        if options.solver not in SOLVERS:
            raise ValueError(f"solver must be one of {', '.join(SOLVERS)}")
        if options.symmetry not in SYMMETRY:
            raise ValueError(f"symmetry must be one of {', '.join(SYMMETRY)}")
        if options.spread is not None:
            for k, wagons_k in enumerate(instance.trains, start=1):
                needed = len({goods for goods, _ in wagons_k}) - 1
                if options.spread < needed:
                    raise ValueError(f"spread {options.spread} is too small: T_{k} has {needed + 1} goods types")
        solver = pywraplp.Solver.CreateSolver(SOLVERS[options.solver])
        if solver is None:
            raise RuntimeError(f"OR-Tools offers no {options.solver} solver")
        self.instance = instance
        self.options = options
        self.solver = solver
        self.runs = R = options.runs or default_runs(instance, options)
        self.lanes = N = min(instance.lanes, options.max_lanes or instance.lanes)

        wagons = instance.wagons
        W, K = len(wagons), len(instance.trains)
        sizes = [len(train) for train in instance.trains]
        weight = [round(wagon.weight * WEIGHT_SCALE) for wagon in wagons]
        capacity = math.floor(instance.capacity * WEIGHT_SCALE + 1e-6)
        train = [wagon.train for wagon in wagons]
        H = options.lookahead
        # CP-SAT needs integer variables; for SCIP the auxiliary ones stay continuous.
        aux = solver.IntVar if options.solver == "cp-sat" else solver.NumVar
        self.wagons = wagons

        def lanes_of(i: int) -> range:
            return range(min(i + 1, N)) if options.symmetry == "first" else range(N)

        def first_preload(i: int) -> int:
            return 1 if H is None else max(1, train[i] - H)

        x = [[solver.BoolVar(f"x[{i},{r}]") for r in range(R)] for i in range(W)]
        y = {(r, g): solver.BoolVar(f"y[{r},{g}]") for r in range(R) for g in instance.goods_types}
        u = [solver.BoolVar(f"u[{r}]") for r in range(R)]
        z = {(i, l): solver.BoolVar(f"z[{i},{l}]") for i in range(W) for l in lanes_of(i)}
        v = [solver.BoolVar(f"v[{l}]") for l in range(N)]
        a = {
            (i, p): solver.BoolVar(f"a[{i},{p}]")
            for i in range(W)
            for p in range(first_preload(i), train[i])
        }
        h = {(i, p, l): aux(0, 1, f"h[{i},{p},{l}]") for (i, p) in a for l in lanes_of(i)}
        D = {p: aux(1, R, f"D[{p}]") for p in range(1, K + 1)}
        rho = [[aux(0, R, f"rho[{l},{i}]") for i in range(W)] for l in range(N)]
        run = [sum((r + 1) * x[i][r] for r in range(R)) for i in range(W)]
        count = [sum(z[i, l] for i in range(W) if (i, l) in z) for l in range(N)]
        self.x, self.y, self.u, self.z, self.v, self.a = x, y, u, z, v, a

        for i in range(W):  # (1)
            solver.Add(sum(x[i]) == 1)
            solver.Add(sum(z[i, l] for l in lanes_of(i)) == 1)
            for r in range(R):  # (2)
                solver.Add(x[i][r] <= y[r, wagons[i].goods])
        for r in range(R):  # (3), (4)
            solver.Add(sum(y[r, g] for g in instance.goods_types) == u[r])
            solver.Add(u[r] <= sum(x[i][r] for i in range(W)))
            if r + 1 < R:
                solver.Add(u[r + 1] <= u[r])
                for g in instance.goods_types:
                    solver.Add(y[r, g] + y[r + 1, g] <= 1)

        for l in range(N):  # (5)–(7): FIFO lanes
            for i in range(W):
                previous = rho[l][i - 1] if i > 0 else 0
                solver.Add(rho[l][i] >= previous)
                if (i, l) in z:
                    solver.Add(rho[l][i] >= run[i] - R * (1 - z[i, l]))
                    solver.Add(run[i] >= previous - R * (1 - z[i, l]))

        for i in range(W):  # (8)
            solver.Add(D[train[i]] >= run[i])
        for p in range(2, K + 1):  # (9)
            solver.Add(D[p] >= D[p - 1])
        for (i, p), pre in a.items():  # (10)
            solver.Add((R - 1) * pre >= D[p] - run[i])
        if H is not None:  # lookahead: no wagon is loaded before T_(k−H−1) has left
            for i in range(W):
                if train[i] - H - 1 >= 1:
                    solver.Add(D[train[i] - H - 1] <= run[i])
        if options.spread is not None:  # (16): F(k) is the first run of T_k
            first = {p: aux(1, R, f"F[{p}]") for p in range(1, K + 1)}
            for i in range(W):
                solver.Add(run[i] >= first[train[i]])
                solver.Add(run[i] <= first[train[i]] + options.spread)
        for (i, p), pre in a.items():  # (11)
            solver.Add(sum(h[i, p, l] for l in lanes_of(i)) == pre)
            for l in lanes_of(i):
                solver.Add(h[i, p, l] <= z[i, l])

        for p in range(1, K + 1):  # (12), (15)
            for l in range(N):
                own = sum(weight[i] * z[i, l] for i in range(W) if train[i] == p and (i, l) in z)
                waiting = sum(weight[i] * h[i, p, l] for i in range(W) if (i, p, l) in h)
                solver.Add(own + waiting <= capacity * v[l])
            if options.aggregated_capacity:
                own = sum(weight[i] for i in range(W) if train[i] == p)
                waiting = sum(weight[i] * a[i, p] for i in range(W) if (i, p) in a)
                solver.Add(own + waiting <= capacity * sum(v))

        for l in range(N):  # (13)
            solver.Add(v[l] <= count[l])
            for i in range(W):
                if (i, l) in z:
                    solver.Add(z[i, l] <= v[l])
        if options.symmetry == "size":  # (14)
            for l in range(N - 1):
                solver.Add(count[l + 1] <= count[l])
        elif options.symmetry == "first":  # (14a), (14b)
            q = [[aux(0, 1, f"q[{l},{i}]") for i in range(W)] for l in range(N)]
            for l in range(N):
                for i in range(W):
                    previous = q[l][i - 1] if i > 0 else 0
                    entering = z[i, l] if (i, l) in z else 0
                    solver.Add(q[l][i] >= previous)
                    solver.Add(q[l][i] >= entering)
                    solver.Add(q[l][i] <= previous + entering)
                    if l > 0 and (i, l) in z:
                        solver.Add(z[i, l] <= (q[l - 1][i - 1] if i > 0 else 0))

        preloaded = {p: sum(a[i, p] for i in range(W) if (i, p) in a) for p in range(1, K + 1)}
        before = [sum(sizes[:p]) for p in range(1, K + 1)]
        constant = sum(n * s for n, s in zip(sizes, before)) + W - W * (W + 1) // 2
        peak = aux(0, W, "peak")
        for p in range(1, K + 1):
            solver.Add(peak >= sizes[p - 1] + preloaded[p])
        zero = 0 * u[0]  # keeps a criterion an expression when it is constant, e.g. waiting for K = 1
        self.criteria = {
            "changes": sum(u) - 1,
            "lanes": sum(v),
            "waiting": zero + sum(n * preloaded[p] for p, n in enumerate(sizes, start=1)) + constant,
            "peak": zero + peak,
            "priority": sum(instance.lane_cost(l + 1) * var for (_, l), var in z.items()),
        }

    @property
    def size(self) -> dict[str, int]:
        return {"variables": self.solver.NumVariables(), "constraints": self.solver.NumConstraints()}

    def _plan(self) -> list[Load]:
        """Runs in order, each sorted by key (fact 1), with the lanes numbered from 1."""
        lane = {i: l for (i, l), var in self.z.items() if var.solution_value() > 0.5}
        loads = []
        for i, wagon in enumerate(self.wagons):
            run = next(r for r, var in enumerate(self.x[i]) if var.solution_value() > 0.5)
            loads.append((run, i, (wagon.key, lane[i] + 1)))
        return [load for _, _, load in sorted(loads)]

    def hint(self, plan: LoadingPlan) -> tuple[list[pywraplp.Variable], list[float]] | None:
        """Values of x, y, u, z and v that describe a valid plan, or None if it does not fit.

        The runs are the blocks of equal goods in the loading order; the lanes
        are renumbered as the symmetry breaking requires.
        """
        index = {wagon.key: i for i, wagon in enumerate(self.wagons)}
        run: dict[int, int] = {}
        goods: list[str] = []
        lane: dict[int, int] = {}
        for key, l in plan.loads:
            i = index[key]
            if not goods or goods[-1] != self.wagons[i].goods:
                goods.append(self.wagons[i].goods)
            run[i], lane[i] = len(goods) - 1, l
        used = sorted(set(lane.values()))
        if len(goods) > self.runs or len(used) > self.lanes:
            return None
        if self.options.symmetry == "size":
            used.sort(key=lambda l: -sum(1 for m in lane.values() if m == l))
        elif self.options.symmetry == "first":
            used.sort(key=lambda l: min(i for i, m in lane.items() if m == l))
        number = {l: n for n, l in enumerate(used)}

        values: dict[pywraplp.Variable, float] = {}
        for i, row in enumerate(self.x):
            for r, var in enumerate(row):
                values[var] = float(run[i] == r)
        for (r, g), var in self.y.items():
            values[var] = float(r < len(goods) and goods[r] == g)
        for r, var in enumerate(self.u):
            values[var] = float(r < len(goods))
        for (i, l), var in self.z.items():
            values[var] = float(number[lane[i]] == l)
        for l, var in enumerate(self.v):
            values[var] = float(l < len(used))
        return list(values), list(values.values())

    def solve(self, objective: str | tuple[str, ...] = DEFAULT_OBJECTIVE) -> LoadingPlan:
        """Minimise the criteria one after another, each kept at its best value."""
        criteria = parse_objective(objective)
        if self.options.symmetry == "first" and "priority" in criteria:
            raise ValueError("symmetry 'first' ignores lane priorities; use 'size' with the priority criterion")
        solver = self.solver
        if self.options.time_limit is not None:
            solver.SetTimeLimit(round(self.options.time_limit * 1000))
        if self.options.threads is not None:
            solver.SetNumThreads(self.options.threads)
        integral = self.instance.lane_costs is None or all(float(c).is_integer() for c in self.instance.lane_costs)

        method = f"MILP {self.options.solver}, R = {self.runs}"
        plan = LoadingPlan(Status.UNKNOWN, method=method)
        hint: tuple[list[pywraplp.Variable], list[float]] | None = None
        if self.options.start:
            start_plan = best_heuristic_plan(self.instance, self.options)
            if start_plan is not None:
                hint = self.hint(start_plan)
                method += f", start {start_plan.method}"
        for name in criteria:
            expr = self.criteria[name]
            solver.Minimize(expr)
            if hint is not None:
                solver.SetHint(*hint)
            start = time.perf_counter()
            status = _STATUS.get(solver.Solve(), Status.UNKNOWN)
            seconds = time.perf_counter() - start
            if status not in (Status.OPTIMAL, Status.FEASIBLE):
                plan.stages.append(Stage(name, status, None, None, seconds))
                if not plan.loads:
                    plan.status = status
                break
            value = solver.Objective().Value()
            bound = solver.Objective().BestBound()
            plan.stages.append(Stage(name, status, value, bound, seconds))
            plan.loads = self._plan()
            variables = solver.variables()
            hint = (variables, [var.solution_value() for var in variables])
            limit = round(value) if integral or name != "priority" else value + 1e-6
            solver.Add(expr <= limit)

        if plan.loads:
            done = len(plan.stages) == len(criteria) and all(s.status == Status.OPTIMAL for s in plan.stages)
            plan.status = Status.OPTIMAL if done else Status.FEASIBLE
        return plan


def solve(
    instance: YardInstance,
    objective: str | tuple[str, ...] = DEFAULT_OBJECTIVE,
    options: ModelOptions = ModelOptions(),
) -> LoadingPlan:
    return YardModel(instance, options).solve(objective)
