# Developer tasks for the jazz-arranger library.
# Prefers the repository's virtualenv interpreter; override with e.g.
#   make test PYTHON=python3
PYTHON ?= .venv/bin/python
PYRIGHT ?= .venv/bin/pyright
RUFF ?= .venv/bin/ruff

.PHONY: help install install-extra install-extra-gp install-dev test typecheck lint format check demo build clean chart chart-audit

help:
	@echo "Available targets:"
	@echo "  make help      Show this message"
	@echo "  make install   Install the package into the local virtualenv (editable)"
	@echo "  make test      Run the full unittest suite (verbose)"
	@echo "  make typecheck Run pyright over the modules and tests/ (dev-only tool)"
	@echo "  make lint      Run ruff over the modules and tests/ (dev-only tool)"
	@echo "  make format    Reformat the tree with ruff"
	@echo "  make check     lint + typecheck + test - what CI runs, what a change must pass"
	@echo "  make demo      Run the built-in demonstration arrangements"
	@echo "  make chart     Regenerate common_grips.md from the engine's tables"
	@echo "  make chart-audit  Check common_grips.md against those tables"
	@echo "  make build     Build a wheel into dist/ (no extra tooling required)"
	@echo "  make clean     Remove caches and build artefacts"
	@echo ""
	@echo "MusicXML export needs the optional extra: make install-extra"
	@echo "Guitar Pro export needs its own:     make install-extra-gp"
	@echo "Lint and type check need:            make install-dev"

install:
	$(PYTHON) -m pip install -e .

install-extra:
	$(PYTHON) -m pip install -e '.[xml]'

# A separate target rather than a flag: PyGuitarPro is LGPL-3.0, and a developer
# who only needs to work on the engine or the MusicXML renderer should not have it
# pulled in.
install-extra-gp:
	$(PYTHON) -m pip install -e '.[gp]'

# pyright and ruff are dev-only and reach no user, by design: a plain
# `pip install jazz-arranger` must not pull a type checker or a linter.
install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	$(PYTHON) -m unittest discover -s tests -v

typecheck:
	@command -v $(PYRIGHT) >/dev/null 2>&1 || { echo "make typecheck needs pyright: $(PYTHON) -m pip install pyright"; exit 1; }
	$(PYRIGHT) --pythonpath $(PYTHON) arranger.py tabstaff.py tabxml.py tabgp.py wjazzd.py headxml.py tests

# The rule set is configured in pyproject.toml ([tool.ruff]), and it is
# deliberately narrow - see the comment there for why UP*/E501/B905 are off.
lint:
	@command -v $(RUFF) >/dev/null 2>&1 || { echo "make lint needs ruff: $(PYTHON) -m pip install ruff"; exit 1; }
	$(RUFF) check arranger.py tabstaff.py tabxml.py tabgp.py wjazzd.py headxml.py grip_chart.py tests

format:
	@command -v $(RUFF) >/dev/null 2>&1 || { echo "make format needs ruff: $(PYTHON) -m pip install ruff"; exit 1; }
	$(RUFF) format arranger.py tabstaff.py tabxml.py tabgp.py wjazzd.py headxml.py grip_chart.py tests

# What a change has to pass, and what CI runs. Ordered cheapest-first so a lint
# failure is reported before the 80-second suite is spent.
check: lint typecheck test

demo:
	$(PYTHON) arranger.py

# The drop-2 shape chart is generated from the engine's own tables, never written
# by hand: a hand-written chart is what this replaced, and its fret numbers
# disagreed with its own labels. `chart-audit` is the check that would have caught
# it, and it is cheap enough to run after any change to the voicing tables.
chart:
	$(PYTHON) grip_chart.py --write common_grips.md

chart-audit:
	$(PYTHON) grip_chart.py --audit common_grips.md

build:
	$(PYTHON) -m pip wheel . -w dist --no-deps

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info
