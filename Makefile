# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

# Development tasks for the train wagons planning project (GNU make).
#
# Works on Windows (recipes run in cmd.exe, also when make is started from
# PowerShell or Git Bash) and on Linux/macOS.
#
#   make venv      create .venv and install the project with the dev extra
#   make test      run the tests
#   make run       solve an example instance (override with ARGS="...")
#   make benchmark solve the benchmark grid and write docs/benchmark.md
#   make diagrams  export docs/diagrams/*.drawio to SVG with the draw.io desktop app
#   make view      solve an example and open the plan viewer (out/plan.html)
#   make image     render images/train-wagons-linkedin.png
#   make notebook  open notebooks/benchmark.ipynb in JupyterLab
#
# The project uses Python 3.12 (PYTHON_VERSION). The base interpreter is found
# with the py launcher on Windows and as python3.12 elsewhere, independently of
# which python comes first on the PATH.

PYTHON_VERSION := 3.12

ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
    .SHELLFLAGS := /c
    PYTHON := py -$(PYTHON_VERSION)
    VENV_PY := .venv\Scripts\python.exe
else
    PYTHON := python$(PYTHON_VERSION)
    VENV_PY := .venv/bin/python
endif

VENV_CFG := .venv/pyvenv.cfg

# draw.io desktop app for make diagrams; override with DRAWIO="path/to/draw.io".
ifeq ($(OS),Windows_NT)
    DRAWIO_USER := $(subst \,/,$(LOCALAPPDATA))/Programs/draw.io/draw.io.exe
    ifneq ($(wildcard $(DRAWIO_USER)),)
        DRAWIO ?= $(DRAWIO_USER)
    else
        DRAWIO ?= C:/Program Files/draw.io/draw.io.exe
    endif
else
    DRAWIO ?= drawio
endif
DIAGRAMS := $(wildcard docs/diagrams/*.drawio)
STAMP := .venv/.installed
ARGS ?= --trains 4 --seed 1

.DEFAULT_GOAL := help
.PHONY: help venv test run view image notebook notebook-check benchmark report diagrams clean distclean recreate

help:
	@echo Targets:
	@echo   make venv       create .venv and install the project with the dev extra
	@echo   make test       run the tests with pytest
	@echo   make run        solve an example; override the instance with ARGS="..."
	@echo   make view       solve the example and open the plan viewer out/plan.html
	@echo   make image      render images/train-wagons-linkedin.png
	@echo   make notebook   open notebooks/benchmark.ipynb in JupyterLab
	@echo   make notebook-check  run all notebook cells headless and store the outputs
	@echo   make benchmark  solve the benchmark grid (long) and write docs/benchmark.md
	@echo   make report     write docs/benchmark.md from docs/benchmark/*.csv
	@echo   make diagrams   export docs/diagrams/*.drawio to SVG (draw.io desktop, DRAWIO=...)
	@echo   make clean      remove caches and build metadata
	@echo   make distclean  clean and remove .venv
	@echo   make recreate   distclean, then venv
	@echo Python $(PYTHON_VERSION), base interpreter: $(PYTHON)

# .venv is created only once. Re-creating an existing one would overwrite its
# python.exe, which fails while an IDE or a Jupyter kernel is using it.
$(VENV_CFG):
	$(PYTHON) scripts/check_venv.py $(PYTHON_VERSION)
	$(PYTHON) -m venv .venv

# The stamp file is rewritten after every install, so the packages are
# refreshed whenever pyproject.toml or this Makefile changes. An existing
# .venv of another Python version is never upgraded in place: check_venv.py
# stops with a hint to run make recreate.
$(STAMP): pyproject.toml Makefile $(VENV_CFG)
	$(PYTHON) scripts/check_venv.py $(PYTHON_VERSION)
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -e ".[dev,plot,notebook]"
	$(VENV_PY) -c "open('$(STAMP)', 'w').close()"

venv: $(STAMP)

test: $(STAMP)
	$(VENV_PY) -m pytest

run: $(STAMP)
	$(VENV_PY) -m train_wagons $(ARGS)

notebook: $(STAMP)
	$(VENV_PY) -m jupyter lab notebooks/benchmark.ipynb

notebook-check: $(STAMP)
	$(VENV_PY) -m jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.record_timing=False notebooks/benchmark.ipynb

image: $(STAMP)
	$(VENV_PY) scripts/linkedin_image.py

view: $(STAMP)
	$(VENV_PY) -m train_wagons $(ARGS) --html out/plan.html
	$(VENV_PY) -m webbrowser -t out/plan.html

# Resumable: rows already in docs/benchmark/*.csv are skipped.
benchmark: $(STAMP)
	$(VENV_PY) scripts/benchmark.py run --configs cp-sat
	$(VENV_PY) scripts/benchmark.py run --configs scip
	$(VENV_PY) scripts/benchmark.py run --configs cp-sat+start
	$(VENV_PY) scripts/benchmark.py run --configs scip+start
	$(VENV_PY) scripts/benchmark.py report

report: $(STAMP)
	$(VENV_PY) scripts/benchmark.py report

# One SVG per diagram, rebuilt when its .drawio changes. Fonts are not
# embedded (60 kB instead of 1.4 MB); the white page background comes from the
# diagram, so the images read well in light and dark mode.
diagrams: $(DIAGRAMS:.drawio=.svg)

docs/diagrams/%.svg: docs/diagrams/%.drawio
	"$(DRAWIO)" --export --format svg --embed-svg-fonts false --theme light --border 10 --output $@ $<

clean:
	$(PYTHON) -c "import glob, shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', 'build', *glob.glob('src/*.egg-info'), *glob.glob('*/**/__pycache__', recursive=True)]]"

distclean: clean
	$(PYTHON) -c "import shutil; shutil.rmtree('.venv', ignore_errors=True)"

recreate: distclean
	$(MAKE) venv
