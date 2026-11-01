# Planning Train Wagons — Problem Statement

*Draft, iteration 1. Points still to be confirmed are listed under
[Open questions](#open-questions).*

## Context

Goods arrive at a port by ship and leave by train. In the port, empty wagons
are loaded one by one by crane. Each loaded wagon is moved to a **buffer**
(sorting yard) of parallel lanes, and from there the trains are assembled and
dispatched, one after another, according to a given **dispatch plan**.

The goal is to find the **loading order** of the wagons in the port so that
every train of the dispatch plan can be assembled from the buffer without the
yard ever getting stuck, with as few changes of goods during loading as
possible.

## Layout

```
                                         buffer (N lanes, FIFO)
  ship ─► crane ─► loading track ─►  ┌─ lane 1  [in ► ■ ■ ■ ■ ► out] ─┐
                   (one wagon)       ├─ lane 2  [in ► ■ ■     ► out] ─┤
                                     ├─   ...                         ├─► departure track ─► trains
                                     └─ lane N  [in ► ■ ■ ■   ► out] ─┘
```

- **Loading track.** A single track in the port where one empty wagon at a
  time is loaded by crane from the ship that is alongside.
- **Track into the buffer.** A single track leads from the port to the
  entries of all lanes.
- **Buffer.** **N** parallel lanes (N = 26 in the reference case). Every lane
  is **FIFO**: wagons enter at one end and leave at the other, so the first
  wagon in is the first wagon out. The total load weight of the wagons
  standing in a lane must never exceed the lane's **load capacity M**.
  The lanes are numbered 1 … N by **priority**: lane 1 is closest to the exit
  of the buffer, and the higher the number, the more shunting it takes to
  bring a wagon from that lane to the departure track.
- **Track out of the buffer.** A single track leads from the exits of all
  lanes to the departure track, where the trains are assembled and dispatched.

## Dispatch plan (input)

The dispatch plan lists the trains in the order of their departure,
**T_1, T_2, …, T_K**. For each train it gives its wagons in order from the
locomotive, which is at the front: position 1 is the wagon right behind the
locomotive. For each wagon it gives

- the **goods type** (e.g. grain, diesel, sand, timber, …), and
- the **load weight** w in tonnes.

Every wagon is an individual: it is tied to exactly one position of one train
and cannot be swapped with another wagon, even one with the same goods type.
Wagon (k, p) denotes the wagon at position p of train T_k.

## Process

1. **Loading.** One wagon at a time is loaded on the loading track; each
   wagon of the plan is loaded exactly once.
2. **Into the buffer.** The loaded wagon is moved into the back of a lane
   that has enough capacity left for its weight.
3. **Assembly.** Trains are assembled in the order of the dispatch plan. A
   wagon can only be taken from the **front** of a lane. The wagons of a train
   are taken out in the order of their positions: first position 1 (right
   behind the locomotive), then 2, and so on.
4. **Departure.** A complete train leaves; the next train is assembled.

A train is one locomotive with its wagons. The departure track holds one
train at a time, so the trains are assembled and dispatched strictly one
after another: assembly of T_(k+1) starts only when T_k has left. If several
trains are already complete in the buffer, they leave one after another
before the next wagon is loaded.

Loading and assembly are **independent**: loading can go on at any time,
also while a train is being assembled. The buffer is **empty** at the start
and, once the last train has left, empty at the end.

## Rules

1. **(hard) Complete train before assembly.** Assembly of train T_k may start
   only when **all** wagons of T_k are in the buffer.
2. **(hard) Lane capacity.** At every moment the total load weight in a lane
   is at most M.
3. **(hard) No deadlock.** The process must never get stuck. Two situations
   are deadlocks:
   - *blocked lane* — the next wagon needed for the train under assembly is in
     the buffer but behind another wagon that is not needed yet;
   - *full buffer* — the next wagon to be loaded fits into no lane, and the
     next train is not yet complete in the buffer, so neither loading nor
     assembly can continue.
4. **(optional, hard) Spread of a train.** With a parameter S, the wagons of
   every train must be loaded within at most S + 1 consecutive runs — blocks
   of consecutively loaded wagons with the same goods type. S = 0 would load
   each train in one block; a train with g goods types needs at least g runs,
   so S ≥ g − 1. Without S the wagons of a train may be spread over the whole
   loading order.
5. **(soft) Few changes of goods.** Changing the goods type between two
   consecutively loaded wagons is expensive: another ship or another kind of
   crane must be brought in.

## Decisions

- The **loading order**: a sequence of all wagons of the plan.
- The **lane** each wagon goes to.
- How loading and assembly are interleaved.

## Objective

Lexicographic, among all plans that satisfy the hard rules. The criteria
and their priority are a **parameter**; the default is

1. **changes** — minimise the number of changes of goods type, i.e. the number
   of consecutively loaded wagon pairs with different goods types;
2. **lanes** — then minimise the number of lanes that receive at least one
   wagon;
3. **waiting** — then minimise the wagons held in the buffer over time;
4. **priority** — then minimise the shunting cost: every wagon taken out of
   lane ℓ costs c(ℓ), with c(1) ≤ c(2) ≤ … ≤ c(N); by default c(ℓ) = ℓ.
   Lanes with low numbers are preferred.

The occupancy after load step t is the number of wagons in the buffer right
after the t-th wagon has entered it. Two measures of "wagons held in the
buffer" are available:

- **waiting** — the sum of the occupancies over all load steps, i.e. for every
  wagon the number of load steps it spends in the buffer, summed up;
- **peak** — the largest occupancy.

Every ordered selection of the criteria changes, lanes, waiting, peak and
priority is a valid objective, e.g. *changes, peak* or *changes, waiting,
lanes*.

## Observations

- **Extraction order is fixed.** Wagons leave the buffer in the order
  (1, 1), (1, 2), …, (2, 1), (2, 2), …, i.e. by the key (train, position).
  Only the loading order and the lanes are decided.
- **FIFO condition.** A lane never blocks assembly if and only if the wagons
  in it were loaded in increasing key order. Which lane is taken from next is
  free, so lanes may be interleaved arbitrarily. Deadlocks of the first kind
  are therefore excluded by a static condition on each lane.
- **Departure as early as possible.** Taking wagons out only ever frees
  capacity, so train T_k can leave as soon as its last wagon is loaded and
  T_(k−1) has left. With this rule the whole process, including the moments
  of departure, follows from the loading order and the lanes, and the
  capacity rule can be checked step by step. Deadlocks of the second kind
  are then exactly the steps where the next wagon fits into no lane.
- **Phases.** Call phase p the stretch of loading after T_(p−1) has left and
  until T_p leaves. A wagon of train k is loaded in some phase p ≤ k. Inside
  a phase no wagon leaves, so the weight in every lane only grows, and it is
  largest at the end of the phase. The capacity rule therefore only has to be
  checked K times per lane: at the end of phase p, lane ℓ holds exactly the
  wagons of trains k ≥ p that were loaded in phases up to p, and their
  weight must be at most M. The same holds for the peak occupancy.
- **Where the difficulty is.** Without capacity limits, N lanes suffice for a
  loading order exactly when it has no decreasing subsequence of keys longer
  than N (Dilworth / patience sorting). Grouping goods across trains means
  loading wagons of later trains early, which fills lanes with weight that
  waits for its train; the capacity M is what makes the goods changes,
  the lanes and the buffer occupancy pull against each other.

## Inputs

| Symbol | Meaning                                         | Unit | Default |
|--------|-------------------------------------------------|------|---------|
| N      | number of lanes in the buffer                   | —    | 26      |
| M      | load capacity of a lane                         | t    | 30      |
| c(ℓ)   | shunting cost of taking a wagon out of lane ℓ   | —    | ℓ       |
| S      | spread: runs between the first and the last run of a train | — | none |
| K      | number of trains in the dispatch plan           | —    | 10–30   |
| G      | number of goods types                           | —    | about 4 |
| T_k    | wagons of train k from the locomotive: goods type and load weight | t | — |

All of them are parameters. Typical wagons: heavy ones carry 4–14 t, light
ones 1 t or less, so a lane holds about 7 heavy or 20 very light wagons.

## Modelling assumptions

1. **Order only, no time.** Iteration 1 plans the order of events (loading a
   wagon, taking a wagon out of the buffer), not their times; loading times
   and departure times come later.
2. **Lengths ignored.** Lengths of lanes and wagons are not considered.
3. **Only the load counts.** The weight of an empty wagon is neglected; the
   capacity M refers to the load weight only.
4. **Empty wagons and goods are always available** in the port, in any order.
5. **No shunting inside the buffer.** Wagons cannot move between lanes or
   leave a lane from the back.
6. All lanes have the same capacity M.

## Planned iterations

| Iteration | Change                                              |
|-----------|-----------------------------------------------------|
| 1         | Order of trains only; lane capacity by load weight (this spec) |
| later     | Time series: loading times per wagon, departure times of trains; lane and wagon lengths; tare weights |

## Open questions

1. How many **wagons per train** are typical, and how are the goods mixed
   within a train (one type per train, or several)?

---

© 2026 Taras Bulubas. All rights reserved. See [LICENSE](../LICENSE).
