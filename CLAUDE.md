# PlanningTrainWagons — project guide for Claude

Optimisation model for planning the loading order of train wagons through a
FIFO buffer: `docs/problem-statement.md`, `docs/mip-model.md`.

## Layout

Follows the same standard as the user's `PlanningRopeBridge` and
`PlanningLinesSweeping` projects (use them as the reference):

- `src/train_wagons/` package, `pyproject.toml` (setuptools, no
  `requirements.txt`), `tests/` with pytest
- `Makefile` with `venv`, `test`, `run`, `clean`, `distclean`, `recreate`;
  Python 3.12 via the py launcher, `scripts/check_venv.py` guards the version
- `docs/` — `problem-statement.md`, later `mip-model.md`; `intellij.md`
- `.run/` — shared IntelliJ run configurations
- Copyright header in every source file:
  ```
  # Copyright (c) 2026 Taras Bulubas. All rights reserved.
  # Use requires prior written permission; see LICENSE.
  ```
- `LICENSE` — all rights reserved; README has the Author / Use of AI /
  License sections like the sibling projects

Modules: `instance.py` (dispatch plan, generator), `solution.py` (plan,
independent step-by-step `simulate()` / `verify()`), `baseline.py` (reference
plan), `heuristic.py` (wave plan), `model.py` (the MILP of
`docs/mip-model.md`, SCIP or CP-SAT, lexicographic), `viewer.py` (interactive
HTML replay of a plan, `--html`, `make view`), `draw.py` (yard snapshots and
the LinkedIn image, `make image`), `cli.py`. `tests/exhaustive.py` is the independent optimality
check on tiny instances. Later, like the siblings: `notebooks/` and its Makefile
targets.

Goal: find out how far a **single pure MILP** goes — no decomposition.

## Running and testing

```bash
make venv
make test
make run
```

The user is on Windows 11 and uses the local `.venv`; do not use or suggest
conda. After changing dependencies in `pyproject.toml`, run `make venv`.
