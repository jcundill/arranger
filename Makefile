# Developer tasks for the jazz-arranger library.
# Prefers the repository's virtualenv interpreter; override with e.g.
#   make test PYTHON=python3
PYTHON ?= .venv/bin/python
PYRIGHT ?= .venv/bin/pyright
RUFF ?= .venv/bin/ruff

# Every source file the gate runs over, spelled once. A new module that is not
# listed here is silently unlinted and untypechecked - which is how three early
# modules nearly shipped unchecked - so lint and format share the one list, and typecheck
# names its own (pyright is given the library, not the dev tools).
#
# `arranger` is a package, so the list names the *directory*: ruff and pyright both
# recurse into it. That is what makes this trap harmless for the eight engine
# modules - they cannot be added one at a time and forgotten, because there is
# nothing to add. Adding a *new top-level module* is still a two-line change here
# and in the typecheck target below.
MODULES = arranger tabscore.py tabstaff.py tabxml.py tabgp.py headxml.py grip_chart.py tests

# The suite is two halves and one command. A test about the **music** is
# `tests/test_*.py`; a test about the **tree** - the module graph, the budgets, the
# private seams, the generated chart, the fixture corpus, the extras' laziness, the
# explanation contract - is `tests/meta_*.py`. The half is the filename, so there is
# no list to keep in step, and `test` runs both so the split is a way in rather than
# a smaller gate. `tests/meta_structure.py::TestTheSplit` fails on a file that is
# neither, which is the one way a pattern-based gate could go quiet.
FEATURE_PATTERN = test_*.py
META_PATTERN = meta_*.py

.PHONY: help install install-extra install-extra-gp install-dev test test-features test-meta test-one typecheck lint format check demo build clean chart chart-audit

help:
	@echo "Available targets:"
	@echo "  make help      Show this message"
	@echo "  make install   Install the package into the local virtualenv (editable)"
	@echo "  make test      Run the whole unittest suite: both halves (verbose)"
	@echo "  make test-features  Run the music half only - the inner loop (verbose)"
	@echo "  make test-meta      Run the structural half only - before committing (verbose)"
	@echo "  make test-one M=tests.test_texture  Run named modules (the fastest loop)"
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

# The whole suite: both halves, in the order a reader wants them - the music first,
# because that is what a feature change moves.
#
# Two invocations rather than one `discover` because unittest filters by *one*
# basename pattern: `-p 'test_*.py'` cannot exclude `meta_*.py`, and a list of
# modules would be trap #1. The two patterns are therefore the split's only
# definition - `TestTheSplit` in tests/meta_structure.py fails if a file matches
# neither, so no module can fall between them and stop running.
test: test-features test-meta

test-features:
	$(PYTHON) -m unittest discover -s tests -t . -p '$(FEATURE_PATTERN)' -v

test-meta:
	$(PYTHON) -m unittest discover -s tests -t . -p '$(META_PATTERN)' -v

# The fastest loop there is, and the reason the split is not the whole answer:
# `make test-one M="tests.test_texture tests.test_grid"` costs one interpreter
# start (~0.6s) plus the modules named.
test-one:
	@test -n "$(M)" || { echo "name at least one module: make test-one M=tests.test_texture"; exit 1; }
	$(PYTHON) -m unittest -v $(M)

typecheck:
	@command -v $(PYRIGHT) >/dev/null 2>&1 || { echo "make typecheck needs pyright: $(PYTHON) -m pip install pyright"; exit 1; }
	$(PYRIGHT) --pythonpath $(PYTHON) arranger tabscore.py tabstaff.py tabxml.py tabgp.py headxml.py tests

# The rule set is configured in pyproject.toml ([tool.ruff]), and it is
# deliberately narrow - see the comment there for why UP*/E501/B905 are off.
lint:
	@command -v $(RUFF) >/dev/null 2>&1 || { echo "make lint needs ruff: $(PYTHON) -m pip install ruff"; exit 1; }
	$(RUFF) check $(MODULES)

format:
	@command -v $(RUFF) >/dev/null 2>&1 || { echo "make format needs ruff: $(PYTHON) -m pip install ruff"; exit 1; }
	$(RUFF) format $(MODULES)

# What a change has to pass, and what CI runs. Ordered cheapest-first so a lint
# failure is reported before the 80-second suite is spent.
check: lint typecheck test

demo:
	$(PYTHON) -m arranger

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
