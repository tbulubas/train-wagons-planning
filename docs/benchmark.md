# Benchmark

How far the single MILP of [mip-model.md](mip-model.md) goes. The tables are generated
by `python scripts/benchmark.py report` from the CSV files in [`benchmark/`](benchmark/);
the findings are written by hand and kept when the tables are regenerated.

## Setup

- Criterion: **changes** only (the first stage of the lexicographic solve), time limit 60 s per instance and configuration.
- Configurations: *cp-sat*, *scip* — the pure model; *+start* — the first stage starts
  from the best heuristic plan (a hint for x, y, u, z and v).
- Machine: Intel64 Family 6 Model 198 Stepping 2, GenuineIntel, 24 logical CPUs; OR-Tools 9.15.6755; CP-SAT with 8 threads, SCIP single-threaded.
  Several configurations ran at the same time, so the times are indicative only.
- Instances: `random_instance` with 5–15 wagons per train, 4 goods types, half of the wagons
  heavy (4–14 t) and half light (0.2–1 t), lanes of M = 30 t. In the series *grid* the number
  of lanes N is chosen for a target load factor λ = total weight / (N · M); in the series
  *N = 26* the buffer has 26 lanes and λ follows from K. N is raised if no heuristic plan exists,
  so for small K the actual λ can stay below the target.
- R (run slots) is taken from the better heuristic plan; *heur.* is its number of changes.
- Every plan found was checked with `simulate`; all passed.

## Findings

<!-- findings -->
First run, 70 instances, 60 s per instance and configuration.

1. **CP-SAT solves the pure MILP far better than SCIP.** CP-SAT proved the
   optimum on 39 instances (44 with a start), SCIP on 11 (15). Without a start
   SCIP found a plan for only 13 of 70 instances.
2. **The LP bound is the wall for SCIP, as expected.** Whenever the optimum is
   above the trivial bound |G| − 1 = 3, the best bound of SCIP stays at 3,
   except for one instance with 4 trains. SCIP proves optimality essentially
   only where the trivial bound is already tight (λ ≤ 1) or the instance is
   tiny. CP-SAT raises the bound well above 3 (to 5–10) through its own
   reasoning on the binaries.
3. **How far CP-SAT goes.** With a tight buffer (λ = 2–4) every instance up
   to **8 trains (about 70–80 wagons)** was solved to optimality, mostly in
   seconds, and some with 12 trains (up to 112 wagons). With a loose buffer
   (λ ≈ 1, the optimum is the trivial 3 changes) it reaches **16 trains (about
   150 wagons)**, 24 with a start. In the reference buffer with 26 lanes the
   optimum is proved up to 16 trains, i.e. as long as all wagons fit
   (λ < 1).
4. **Beyond that, plans but no proofs.** For 16–30 trains at λ ≥ 1.4 CP-SAT
   with a start returns plans with a gap of 1–2 changes in the reference
   buffer (6 [4]) and of 3–7 changes in the tight grid (9 [5], 12 [5]).
5. **A start is essential for large instances.** Without one CP-SAT found no
   plan at all from about 16–24 trains on; with one it returned a plan for 68
   of 70 instances. It barely changes the time to optimality on the instances
   solved anyway.
6. **The MILP improves on the heuristic where it can search.** On medium
   instances the optimum is much better than the plan in waves (8 instead of
   14, 6 instead of 11 changes). On the largest instances the plans of the
   MILP mostly stay at the heuristic value: within 60 s it neither improves
   them nor proves them optimal.
7. **Model size bites at λ ≈ 1.** With many lanes (N = 36–44 for 24–30
   trains) the model has 120 000–220 000 variables, mostly h = a · z. Even
   where the heuristic already reaches the trivial bound — so the plan is
   provably optimal without any solver — CP-SAT did not finish within 60 s.

**Next levers**, in the order of [mip-model.md](mip-model.md#computational-study):
valid inequalities that raise the bound on the changes; a smaller model (the
lookahead H, fewer lanes N̄, fewer h variables); stopping at once when a
heuristic plan meets a lower bound; and longer time limits for the largest
instances.
<!-- /findings -->

## Summary

Largest number of trains K up to which every instance was solved to optimality:

| series | target λ | cp-sat | scip | cp-sat+start | scip+start |
|---|---|---|---|---|---|
| grid | 1 | 16 | 4 | 24 | 8 |
| grid | 2 | 8 | — | 8 | — |
| grid | 3 | 8 | — | 12 | — |
| grid | 4 | 8 | — | 8 | — |
| N=26 | — | 16 | 4 | 16 | 8 |

- **cp-sat**: 39 of 70 instances optimal, a plan for 46.
- **scip**: 11 of 70 instances optimal, a plan for 13.
- **cp-sat+start**: 44 of 70 instances optimal, a plan for 68.
- **scip+start**: 15 of 70 instances optimal, a plan for 40.

Cells below: **v** t = optimal with v changes, proved in t seconds; v [b] = best plan v changes,
best bound b at the time limit; — = no plan found. The trivial bound is |G| − 1 = 3.

## Series grid

| target λ | K | seed | W | N | λ | heur. | R | variables | cp-sat | scip | cp-sat+start | scip+start |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | 1 | 30 | 4 | 1.00 | 3 | 4 | 659 | **3** <1s | **3** 1s | **3** <1s | **3** <1s |
| 1 | 4 | 2 | 36 | 7 | 0.95 | 3 | 4 | 1 136 | **3** <1s | **3** 2s | **3** <1s | **3** <1s |
| 1 | 6 | 1 | 51 | 9 | 0.95 | 3 | 4 | 2 628 | **3** <1s | **3** 40s | **3** <1s | **3** <1s |
| 1 | 6 | 2 | 58 | 10 | 0.99 | 3 | 4 | 3 123 | **3** <1s | — | **3** <1s | **3** <1s |
| 1 | 8 | 1 | 76 | 12 | 1.00 | 3 | 4 | 6 225 | **3** 1s | — | **3** <1s | **3** <1s |
| 1 | 8 | 2 | 68 | 11 | 1.00 | 3 | 4 | 4 436 | **3** <1s | **3** 43s | **3** <1s | **3** <1s |
| 1 | 12 | 1 | 109 | 18 | 0.97 | 3 | 4 | 16 324 | **3** 15s | — | **3** 7s | — |
| 1 | 12 | 2 | 112 | 18 | 0.98 | 3 | 4 | 16 786 | **3** 12s | — | **3** 8s | — |
| 1 | 16 | 1 | 148 | 23 | 1.01 | 3 | 4 | 35 228 | **3** 39s | — | **3** 22s | — |
| 1 | 16 | 2 | 152 | 25 | 0.98 | 3 | 4 | 39 002 | **3** 31s | — | **3** 23s | — |
| 1 | 24 | 1 | 232 | 36 | 1.00 | 3 | 4 | 121 202 | — | — | **3** 47s | — |
| 1 | 24 | 2 | 240 | 37 | 1.00 | 3 | 4 | 128 356 | — | — | **3** 39s | — |
| 1 | 30 | 1 | 287 | 44 | 1.00 | 3 | 4 | 218 739 | — | — | — | — |
| 1 | 30 | 2 | 293 | 44 | 0.99 | 3 | 4 | 220 056 | — | — | — | — |
| 2 | 4 | 1 | 30 | 3 | 1.33 | 9 | 10 | 754 | **5** <1s | — | **5** <1s | 7 [3] |
| 2 | 4 | 2 | 36 | 4 | 1.67 | 5 | 6 | 828 | **4** <1s | **4** 57s | **4** <1s | **4** 16s |
| 2 | 6 | 1 | 51 | 4 | 2.14 | 8 | 9 | 1 658 | **6** 4s | — | **6** 5s | 8 [3] |
| 2 | 6 | 2 | 58 | 5 | 1.98 | 6 | 7 | 1 957 | **4** 4s | — | **4** <1s | 6 [3] |
| 2 | 8 | 1 | 76 | 6 | 2.00 | 6 | 7 | 3 678 | **5** 11s | — | **5** 2s | 6 [3] |
| 2 | 8 | 2 | 68 | 6 | 1.84 | 6 | 7 | 2 875 | **4** 3s | — | **4** 1s | 6 [3] |
| 2 | 12 | 1 | 109 | 9 | 1.95 | 6 | 7 | 9 052 | **5** 17s | — | **5** 36s | 6 [3] |
| 2 | 12 | 2 | 112 | 9 | 1.96 | 6 | 7 | 9 307 | 5 [4] | — | 5 [4] | 6 [3] |
| 2 | 16 | 1 | 148 | 12 | 1.93 | 6 | 7 | 19 693 | — | — | 6 [5] | — |
| 2 | 16 | 2 | 152 | 12 | 2.05 | 6 | 7 | 20 142 | 6 [5] | — | 6 [5] | — |
| 2 | 24 | 1 | 232 | 18 | 2.01 | 6 | 7 | 63 197 | — | — | 6 [5] | — |
| 2 | 24 | 2 | 240 | 19 | 1.95 | 6 | 7 | 68 539 | — | — | 6 [5] | — |
| 2 | 30 | 1 | 287 | 22 | 1.99 | 6 | 7 | 112 981 | — | — | 6 [5] | — |
| 2 | 30 | 2 | 293 | 22 | 1.98 | 6 | 7 | 113 678 | — | — | 6 [5] | — |
| 3 | 4 | 1 | 30 | 3 | 1.33 | 9 | 10 | 754 | **5** <1s | 6 [3] | **5** <1s | 6 [3] |
| 3 | 4 | 2 | 36 | 4 | 1.67 | 5 | 6 | 828 | **4** <1s | **4** 34s | **4** <1s | **4** 10s |
| 3 | 6 | 1 | 51 | 3 | 2.85 | 14 | 15 | 1 744 | **8** 6s | — | **8** 5s | 14 [3] |
| 3 | 6 | 2 | 58 | 4 | 2.48 | 11 | 12 | 2 001 | **6** 9s | — | **6** 7s | 11 [3] |
| 3 | 8 | 1 | 76 | 4 | 3.00 | 11 | 12 | 3 153 | **7** 7s | — | **7** 3s | 11 [3] |
| 3 | 8 | 2 | 68 | 4 | 2.76 | 14 | 15 | 2 747 | **6** 11s | — | **6** 13s | 14 [3] |
| 3 | 12 | 1 | 109 | 6 | 2.92 | 9 | 10 | 6 856 | 9 [6] | — | **7** 34s | 9 [3] |
| 3 | 12 | 2 | 112 | 6 | 2.94 | 12 | 13 | 7 399 | 7 [6] | — | **6** 20s | 12 [3] |
| 3 | 16 | 1 | 148 | 8 | 2.90 | 9 | 10 | 14 336 | 8 [6] | — | 8 [6] | 9 [3] |
| 3 | 16 | 2 | 152 | 8 | 3.07 | 9 | 10 | 14 665 | — | — | 8 [6] | 9 [3] |
| 3 | 24 | 1 | 232 | 12 | 3.01 | 9 | 10 | 44 336 | — | — | 9 [5] | — |
| 3 | 24 | 2 | 240 | 12 | 3.09 | 9 | 10 | 45 726 | — | — | 9 [5] | — |
| 3 | 30 | 1 | 287 | 15 | 2.93 | 9 | 10 | 79 928 | — | — | 9 [5] | — |
| 3 | 30 | 2 | 293 | 15 | 2.90 | 9 | 10 | 80 440 | — | — | 9 [6] | — |
| 4 | 4 | 1 | 30 | 3 | 1.33 | 9 | 10 | 754 | **5** <1s | 6 [3] | **5** <1s | 6 [3] |
| 4 | 4 | 2 | 36 | 4 | 1.67 | 5 | 6 | 828 | **4** <1s | **4** 17s | **4** <1s | **4** 7s |
| 4 | 6 | 1 | 51 | 3 | 2.85 | 14 | 15 | 1 744 | **8** 3s | — | **8** 2s | 14 [3] |
| 4 | 6 | 2 | 58 | 4 | 2.48 | 11 | 12 | 2 001 | **6** 4s | — | **6** 4s | 11 [3] |
| 4 | 8 | 1 | 76 | 4 | 3.00 | 11 | 12 | 3 153 | **7** 2s | — | **7** 2s | 11 [3] |
| 4 | 8 | 2 | 68 | 4 | 2.76 | 14 | 15 | 2 747 | **6** 5s | — | **6** 12s | 14 [3] |
| 4 | 12 | 1 | 109 | 4 | 4.38 | 14 | 15 | 5 734 | 11 [10] | — | **10** 20s | 14 [3] |
| 4 | 12 | 2 | 112 | 4 | 4.41 | 17 | 18 | 6 244 | 10 [9] | — | 10 [9] | 17 [3] |
| 4 | 16 | 1 | 148 | 6 | 3.86 | 12 | 13 | 11 887 | — | — | 9 [8] | 12 [3] |
| 4 | 16 | 2 | 152 | 6 | 4.09 | 15 | 16 | 12 633 | — | — | 10 [8] | 15 [3] |
| 4 | 24 | 1 | 232 | 9 | 4.02 | 12 | 13 | 35 261 | — | — | 12 [6] | — |
| 4 | 24 | 2 | 240 | 9 | 4.12 | 12 | 13 | 36 369 | — | — | 10 [8] | — |
| 4 | 30 | 1 | 287 | 11 | 3.99 | 12 | 13 | 61 416 | — | — | 12 [5] | — |
| 4 | 30 | 2 | 293 | 11 | 3.96 | 12 | 13 | 61 830 | — | — | 10 [6] | — |

## Series N=26

| target λ | K | seed | W | N | λ | heur. | R | variables | cp-sat | scip | cp-sat+start | scip+start |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| — | 4 | 1 | 30 | 26 | 0.15 | 3 | 4 | 3 189 | **3** <1s | **3** <1s | **3** <1s | **3** <1s |
| — | 4 | 2 | 36 | 26 | 0.26 | 3 | 4 | 3 606 | **3** <1s | **3** 14s | **3** <1s | **3** <1s |
| — | 6 | 1 | 51 | 26 | 0.33 | 3 | 4 | 6 878 | **3** 1s | **3** 10s | **3** <1s | **3** <1s |
| — | 6 | 2 | 58 | 26 | 0.38 | 3 | 4 | 7 459 | **3** 1s | — | **3** 1s | **3** <1s |
| — | 8 | 1 | 76 | 26 | 0.46 | 3 | 4 | 12 735 | **3** 2s | — | **3** 3s | **3** <1s |
| — | 8 | 2 | 68 | 26 | 0.42 | 3 | 4 | 9 776 | **3** 1s | **3** 25s | **3** 2s | **3** <1s |
| — | 12 | 1 | 109 | 26 | 0.67 | 3 | 4 | 23 092 | **3** 9s | — | **3** 6s | — |
| — | 12 | 2 | 112 | 26 | 0.68 | 3 | 4 | 23 746 | **3** 8s | — | **3** 7s | — |
| — | 16 | 1 | 148 | 26 | 0.89 | 3 | 4 | 39 590 | **3** 36s | — | **3** 11s | — |
| — | 16 | 2 | 152 | 26 | 0.95 | 3 | 4 | 40 489 | **3** 41s | — | **3** 11s | — |
| — | 24 | 1 | 232 | 26 | 1.39 | 6 | 7 | 89 293 | — | — | 6 [4] | — |
| — | 24 | 2 | 240 | 26 | 1.42 | 6 | 7 | 92 087 | — | — | 6 [4] | — |
| — | 30 | 1 | 287 | 26 | 1.69 | 6 | 7 | 132 369 | — | — | 6 [4] | — |
| — | 30 | 2 | 293 | 26 | 1.67 | 6 | 7 | 133 182 | — | — | 6 [4] | — |

---

© 2026 Taras Bulubas. All rights reserved. See [LICENSE](../LICENSE).
