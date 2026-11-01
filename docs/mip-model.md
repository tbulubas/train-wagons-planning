# Planning Train Wagons — MIP Model (Iteration 1)

*Implemented in [`model.py`](../src/train_wagons/model.py). On about 100
tiny random instances the optimum of the model agrees, for both solvers and
several objectives, with an exhaustive search over all loading orders and
lanes ([`tests/exhaustive.py`](../tests/exhaustive.py)).*

Mixed-integer model for the loading problem described in
[`problem-statement.md`](problem-statement.md).
Diagrams of the model: [`model-overview.md`](model-overview.md).

The aim of the project is to find out whether the problem can be solved as a
**single, pure MILP** — no decomposition into subproblems — and how large the
instances can get before the solvers stop proving optimality. See
[Computational study](#computational-study).

## Idea

The loading order is a sequence of all wagons. Cut it into **runs**: maximal
stretches of consecutively loaded wagons with the same goods type. The number
of changes of goods is the number of runs minus one.

Three facts reduce the sequence to a much smaller decision (proofs below):

1. **Inside a run, the wagons are loaded in extraction order** — by the key
   (train, position). Sorting a run never makes a plan worse.
2. **A lane is FIFO-feasible exactly when its run numbers do not decrease
   along the keys** of its wagons. Wagons of one run in one lane are then
   automatically in key order.
3. **The capacity of a lane only has to be checked right before each
   departure.** Between two departures the weight in a lane only grows.

So the model only chooses, for every wagon, **its run and its lane**. The
order inside each run follows from the keys, the departures follow from the
runs, and the loading sequence is the concatenation of the runs.

## Indices and sets

| Symbol        | Meaning                                                           |
|---------------|-------------------------------------------------------------------|
| i, j ∈ I      | wagons, numbered 1 … W in **extraction order**, so i < j ⇔ key(i) < key(j) |
| p ∈ {1 … K}   | trains, in the order of departure                                 |
| k(i)          | train of wagon i                                                  |
| g ∈ G         | goods types; g(i) is the goods type of wagon i                    |
| r ∈ {1 … R}   | run slots, in loading order                                       |
| ℓ ∈ {1 … N}   | lanes of the buffer                                               |

## Parameters

| Symbol   | Meaning                                               | Unit |
|----------|-------------------------------------------------------|------|
| w(i)     | load weight of wagon i                                | t    |
| M        | load capacity of a lane                               | t    |
| n_p      | number of wagons of train T_p                         | —    |
| S_p      | n_1 + … + n_p, wagons of the first p trains           | —    |
| R        | number of run slots (see [Choosing R](#choosing-r))   | —    |

## Decision variables

| Variable                    | Domain   | Meaning                                                    |
|-----------------------------|----------|------------------------------------------------------------|
| x(i,r)                      | {0, 1}   | wagon i is loaded in run r                                 |
| y(r,g)                      | {0, 1}   | run r loads goods type g                                   |
| u(r)                        | {0, 1}   | run r is used                                              |
| z(i,ℓ)                      | {0, 1}   | wagon i goes to lane ℓ                                     |
| v(ℓ)                        | {0, 1}   | lane ℓ is used                                             |
| a(i,p), p < k(i)            | {0, 1}   | wagon i is loaded **before T_p leaves** (it is *pre-loaded* for T_p) |
| h(i,p,ℓ), p < k(i)          | [0, 1]   | a(i,p) · z(i,ℓ): i is pre-loaded for T_p and stands in lane ℓ |
| D(p)                        | [1, R]   | run during which T_p leaves                                |
| F(p)                        | [1, R]   | first run of T_p — only with the spread S (16)             |
| ρ(ℓ,i)                      | [0, R]   | highest run of the wagons 1 … i in lane ℓ                  |

Derived expressions — the run of wagon i, and the number of wagons in lane ℓ:

    r(i) = Σ_r r · x(i,r)
    n(ℓ) = Σ_i z(i,ℓ)

## Constraints

Every wagon is loaded in one run and goes to one lane:

    (1)  Σ_r x(i,r) = 1,   Σ_ℓ z(i,ℓ) = 1                         ∀ i

Runs: one goods type per used run, used runs first, no empty used run, and
consecutive runs with different goods (two consecutive runs of the same goods
are one run):

    (2)  x(i,r) ≤ y(r, g(i))                                       ∀ i, r
    (3)  Σ_g y(r,g) = u(r),   u(r+1) ≤ u(r),   u(r) ≤ Σ_i x(i,r)    ∀ r
    (4)  y(r,g) + y(r+1,g) ≤ 1                                     ∀ r < R, g

FIFO lanes — along the keys, the runs of the wagons in a lane do not
decrease (fact 2). ρ(ℓ,i) carries the highest run seen so far in lane ℓ,
with ρ(ℓ,0) = 0:

    (5)  ρ(ℓ,i) ≥ ρ(ℓ,i−1)                                         ∀ ℓ, i
    (6)  ρ(ℓ,i) ≥ r(i) − R · (1 − z(i,ℓ))                          ∀ ℓ, i
    (7)  r(i) ≥ ρ(ℓ,i−1) − R · (1 − z(i,ℓ))                        ∀ ℓ, i

Departures — T_p leaves in the run of its last wagon, and not before
T_(p−1):

    (8)  D(p) ≥ r(i)                                               ∀ i with k(i) = p
    (9)  D(p) ≥ D(p−1)                                             ∀ p > 1

Pre-loading — a wagon of a later train that is loaded in a run before D(p)
is in the buffer when T_p leaves. A wagon of a later train in the run D(p)
itself comes after the wagons of T_p (fact 1) and is not counted:

    (10) (R − 1) · a(i,p) ≥ D(p) − r(i)                            ∀ i, p < k(i)

Linearisation of h = a · z (exact, because every wagon is in exactly one lane):

    (11) Σ_ℓ h(i,p,ℓ) = a(i,p),   h(i,p,ℓ) ≤ z(i,ℓ)                ∀ i, p < k(i), ℓ

Lane capacity right before T_p leaves (fact 3): the lane holds the wagons
of T_p that stand in it and the wagons pre-loaded for T_p:

    (12) Σ_{i: k(i)=p} w(i) · z(i,ℓ) + Σ_{i: k(i)>p} w(i) · h(i,p,ℓ) ≤ M · v(ℓ)    ∀ p, ℓ

**Lane priority.** The lanes are numbered by priority (see the problem
statement): taking a wagon out of lane ℓ costs c(ℓ), with
c(1) ≤ c(2) ≤ … ≤ c(N). Apart from this cost the lanes are identical — the
same capacity and the same rules. So for a given split of the wagons into
groups, one group per lane, every numbering of the groups satisfies all
constraints, and the shunting cost is smallest when the largest group gets
lane 1, the second largest lane 2, and so on (rearrangement inequality).
Hence lanes may be required to be **ordered by the number of their wagons**
without losing an optimal plan, for every objective:

    (13) z(i,ℓ) ≤ v(ℓ),   v(ℓ) ≤ n(ℓ)                                ∀ i, ℓ
    (14) n(ℓ+1) ≤ n(ℓ)                                             ∀ ℓ < N

Consequences:

- The used lanes are always 1 … L, the busiest first.
- Most of the N!/(N − L)! numberings of a plan are removed; only lanes with
  the same number of wagons can still be swapped.

**Stronger symmetry breaking without priority.** When priority is not among
the criteria, or in the stages of the lexicographic solve before it, the
lanes are fully interchangeable, and (14) can be replaced by numbering the
lanes by their first wagon, which removes all symmetry. With q(ℓ,i) ∈ [0, 1]
meaning "lane ℓ holds one of the wagons 1 … i" and q(ℓ,0) = 0:

    (14a) q(ℓ,i) ≥ q(ℓ,i−1),   q(ℓ,i) ≥ z(i,ℓ),   q(ℓ,i) ≤ q(ℓ,i−1) + z(i,ℓ)   ∀ ℓ, i
    (14b) z(i,ℓ) ≤ q(ℓ−1,i−1)                                                   ∀ ℓ > 1, i

Wagon i can open lane ℓ only if lane ℓ − 1 already holds an earlier wagon,
so every split into lanes has exactly one numbering; wagon 1 is in lane 1 and
wagon i can only be in lanes 1 … i. Before the priority stage starts, the
solution of the previous stage is renumbered by group size so that it
satisfies (14) — a renumbering does not change any other criterion.

The sum of (12) over all lanes is implied, but much stronger in the LP
relaxation:

    (15) Σ_{i: k(i)=p} w(i) + Σ_{i: k(i)>p} w(i) · a(i,p) ≤ M · Σ_ℓ v(ℓ)          ∀ p

**Spread (optional).** With the parameter S (option `spread`, CLI `-S`) the
wagons of every train lie within S + 1 consecutive runs. F(p) is the first
run of T_p:

    (16) F(k(i)) ≤ r(i) ≤ F(k(i)) + S                              ∀ i

One run carries one goods type, so a train with g goods types needs at least
g runs; S below max_p (g_p − 1) admits no plan and is rejected before the model
is built. The reference plan loads every train in exactly g_p consecutive
runs, so it obeys every admissible S and R can always be taken from it.

The model may set a(i,p) = 1 or D(p) higher than necessary. That only counts
more weight in (12) than there really is, so every solution of the model is a
valid plan; the true values follow from the simulation.

## Criteria

    changes  C = Σ_r u(r) − 1
    lanes    L = Σ_ℓ v(ℓ)

Occupancy right before T_p leaves — its own wagons and the pre-loaded ones:

    O(p) = n_p + Σ_{i: k(i)>p} a(i,p)

The occupancy only grows between departures, so

    peak     P ≥ O(p)                                              ∀ p

T_p leaves after load step S_p + Σ_{i: k(i)>p} a(i,p), and a wagon spends
the load steps from its own to the departure of its train in the buffer.
Summing over all wagons, the load steps 1 + … + W cancel to a constant:

    waiting  = Σ_p n_p · Σ_{i: k(i)>p} a(i,p)  +  Σ_p n_p · S_p + W − W(W+1)/2

Both measures of the wagons held in the buffer are linear in a.

    priority Q = Σ_i Σ_ℓ c(ℓ) · z(i,ℓ)

## Objective

The criteria are minimised **lexicographically**, in the order given by the
parameter `objective` (default *changes, lanes, waiting, priority*). The model is solved
once per criterion: minimise the first, fix it at its optimum by a
constraint (≤ the optimal value), minimise the next, and so on. Each stage
starts from the solution of the previous one.

## Choosing R

R is the number of run slots; a plan with c changes needs c + 1 of them.

- When **changes** is the first criterion, any R for which the model is
  feasible gives the optimal number of changes: a plan with fewer runs would
  fit into the same R slots. If the model is infeasible, R is increased.
  The lower bound is R = |G| (every goods type needs a run).
- When changes is not the first criterion, R restricts the plans: a plan
  with fewer lanes might need more runs. R then has to be large enough, e.g.
  the number of runs of the reference plan.

By default R is the number of runs of the better of two heuristic plans —
the reference plan (train by train) and the plan in *waves*
([`heuristic.py`](../src/train_wagons/heuristic.py)): consecutive trains
loaded together, one run per goods type, the last goods of one wave first in
the next. Either plan also serves as a starting solution (option `start`).

## Proofs of the three facts

**Fact 1 — sorting a run.** Take a valid plan and sort the wagons of one run
by key, keeping their lanes. In every lane, the wagons of that run were
already in key order (FIFO), so the order of every lane is unchanged and no
lane is blocked. T_p leaves after the last wagon of trains ≤ p, in the same
run D_p as before; after sorting, the wagons of trains ≤ p come first in that
run, so at the departure the buffer holds a subset of what it held before.
The capacity holds, and no departure is later.

**Fact 2 — FIFO lanes.** The wagons leave in key order. If i < j are in the
same lane and j is loaded before i, then j stands in front of i but has to
leave after it — the lane is blocked. If all wagons of a lane are loaded in
key order, the lane always holds its wagons in the order in which they are
needed. With fact 1, "loaded in key order" means: the run of i is at most
the run of j for i < j in the same lane, which is what (5)–(7) express.

**Fact 3 — capacity.** Between two departures wagons are only added, so the
weight of a lane is largest right before a departure. Right before T_p
leaves, all trains before it have left, T_p is complete, and the only other
wagons are those of later trains loaded before this moment.

## Model size

For W = 300 wagons (K = 30 trains of 10), N = 26 lanes, R = 20 runs, |G| = 4:

| Item                         | Count                        |
|------------------------------|------------------------------|
| binaries x                   | W · R = 6 000                |
| binaries z                   | W · N = 7 800 (fewer after (14b)) |
| binaries a                   | Σ_i (k(i) − 1) ≈ 4 350       |
| binaries y, u, v             | 80 + 20 + 26                 |
| continuous h                 | ≈ 4 350 · 26 ≈ 113 000       |
| continuous ρ, D (q with (14a)) | N · W + K = 7 830 (+ N · W)  |
| constraints (5)–(7)          | 3 · N · W = 23 400           |
| constraints (13)–(14)        | W · N + 2N ≈ 7 850; with (14a)–(14b) ≈ 4 · N · W instead |
| constraints (11)             | ≈ 117 000                    |
| constraints (12)             | K · N = 780                  |

The h variables dominate. Optional reductions, each a restriction of the
plans unless noted:

- **Lookahead H**: a wagon of train k may only be loaded after T_(k−H−1)
  has left, i.e. a(i,p) = 0 and D(p) ≤ r(i) for p < k(i) − H. With H = 5,
  a and h shrink to about a third. H ≥ K − 1 is exact.
- **Fewer lanes**: N̄ < N lanes in the model (exact if a plan with N̄ lanes
  exists, which the lanes criterion favours anyway).
- **Lots not split**: all wagons of one train with the same goods type in
  the same run.

## Solvers

The model is linear with integer data once the weights are given in
kilograms. For CP-SAT all variables are declared integer (h, D, ρ, q take
integer values in every solution anyway); for SCIP they stay continuous. It can be solved by **SCIP**, like the sibling projects, and by
**CP-SAT** (both shipped with OR-Tools); CP-SAT is often stronger on large
pure-binary assignment models like this one. Both are planned behind one
option, so they can be compared on the same instances.

Both solvers detect symmetries on their own. With (14) or (14a)–(14b) in
the model the lanes are no longer interchangeable, so the solvers find no
lane symmetry to handle and the two mechanisms do not get in each other's
way.

## From the solution to the plan

1. Collect the wagons of every used run r = 1, 2, …, and sort each run by key.
2. Concatenate the runs: this is the loading order. The lane of every wagon
   is the ℓ with z(i,ℓ) = 1.
3. `simulate` carries the plan out step by step, independently of the model,
   checks every rule and computes the true criteria.

## Example: three trains

Three trains, five wagons of 10 t each, goods types A and B, N = 2 lanes of
M = 30 t. In extraction order the wagons are i = 1.1, 1.2, 2.1, 2.2, 3.1:

    T_1 = 1.1 A, 1.2 B        T_2 = 2.1 B, 2.2 A        T_3 = 3.1 A

The optimum for *changes, lanes, waiting, priority* (`tests/test_model.py`
checks it with both solvers):

    run 1 (B):  1.2 → lane 1,  2.1 → lane 1
    run 2 (A):  1.1 → lane 2   [T_1 leaves]   2.2 → lane 1   [T_2 leaves]   3.1 → lane 1   [T_3 leaves]

Values in the model:

- **Runs.** r(1.2) = r(2.1) = 1 and r(1.1) = r(2.2) = r(3.1) = 2; one change,
  which is the trivial bound |G| − 1, so the plan is optimal at once.
- **Departures.** Every train has its last wagon in run 2, so
  D(1) = D(2) = D(3) = 2 (8)–(9).
- **Pre-loading.** 2.1 is in run 1 < D(1): it waits in the buffer while T_1
  leaves, a(2.1, 1) = 1 (10). 2.2 and 3.1 are in run 2 = D(1) = D(2); inside
  the run they come after the wagons of T_1 and T_2 (fact 1), so
  a(2.2, 1) = a(3.1, 1) = a(3.1, 2) = 0.
- **Capacity right before T_1 leaves** (12). Lane 1 holds its own wagon 1.2
  and the pre-loaded 2.1, h(2.1, 1, 1) = 1: 20 t ≤ 30 t. Lane 2 holds 1.1:
  10 t ≤ 30 t.
- **FIFO** (5)–(7). Lane 1 receives 1.2, 2.1, 2.2, 3.1 with the runs 1, 1, 2, 2,
  which do not decrease, so ρ(1, ·) rises from 1 to 2. Wagon 1.1 cannot join
  lane 1: its key is smaller than that of 1.2 but its run is larger, so it
  would stand behind 1.2 and 2.1 and still have to leave first. It needs lane
  2.
- **Criteria.** changes 1; lanes 2; the occupancy after the five load steps
  is 1, 2, 3, 2, 1, so waiting = 9 — by the formula above
  Σ_p n_p S_p + W − W(W+1)/2 = 7 plus n_1 · a(2.1, 1) = 2 — and peak = 3;
  n(1) = 4 ≥ n(2) = 1 (14) and priority = 4 · c(1) + 1 · c(2) = 6.

## Expected difficulty

**The LP bound on the changes is weak.** For every goods type g, (1)–(2)
give Σ_r y(r,g) ≥ 1, so Σ_r u(r) ≥ |G| and the LP relaxation proves at least
|G| − 1 changes — the trivial bound. With fractional x, z and a, the FIFO
constraints (5)–(7) and the departure constraints (10) are hardly binding in
the LP. Every change above |G| − 1 therefore has to be proved by branching,
and this, more than the size of the model, is expected to limit how far the
MILP goes.

**What makes instances hard is the buffer, not the number of wagons.** If
all wagons fit into the buffer at once, every goods type can be loaded in a
single run, |G| − 1 changes are reached and the trivial bound proves them
optimal at once. The relevant measure is the **load factor**

    λ = (total load weight of all trains) / (N · M)

λ ≤ 1 tends to be easy; the larger λ, the more often the goods have to be
repeated and the harder the proof.

**Strengthening.** Valid inequalities that raise the bound on the changes —
from the capacity: a train cannot leave while too much weight of later trains
waits in the buffer — are the main lever and are still to be found.

## Computational study

1. *Done:* the model (`model.py`) with SCIP and CP-SAT, and the `priority`
   criterion in `simulate`.
2. *Done:* correctness — every solution goes through `simulate`, and on tiny
   instances (4–6 wagons) the optimum equals that of an exhaustive search
   over all loading orders and lanes.
3. *First run done:* benchmark on a grid of random instances — trains K ×
   load factor λ, the load factor set through the number of lanes N — and on
   the reference buffer of 26 lanes: [benchmark.md](benchmark.md). In short:
   CP-SAT proves the optimum up to about 8 trains (70–80 wagons) with a tight
   buffer and up to 16 trains when all wagons fit; SCIP is stuck at the
   trivial LP bound, as expected above. Record for SCIP and for CP-SAT: model size,
   LP bound, best plan, best bound, gap, time and nodes, with a fixed time
   limit per stage.
4. Measure what each part of the formulation is worth: symmetry breaking
   (14) vs (14a)–(14b) vs none, the aggregated capacity (15), the lookahead
   H, and a starting solution (a heuristic plan in *waves* — consecutive
   trains whose wagons fit into the buffer, each wave loaded goods type by
   goods type).
5. Add valid inequalities for the changes bound and measure again.

The result is a table: up to which size and load factor each solver proves
optimality, and how large the gap is beyond that.

---

© 2026 Taras Bulubas. All rights reserved. See [LICENSE](../LICENSE).
