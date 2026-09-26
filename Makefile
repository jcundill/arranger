# Developer tasks for the jazz-arranger library.
# Prefers the repository's virtualenv interpreter; override with e.g.
#   make test PYTHON=python3
PYTHON ?= .venv/bin/python

.PHONY: help install test demo build clean

help:
	@echo "Available targets:"
	@echo "  make install   Install the package into the local virtualenv (editable)"
	@echo "  make test      Run the full unittest suite (verbose)"
	@echo "  make demo      Run the built-in demonstration arrangements"
	@echo "  make build     Build a wheel into dist/ (no extra tooling required)"
	@echo "  make clean     Remove caches and build artefacts"

install:
	$(PYTHON) -m pip install -e .

test:
	$(PYTHON) -m unittest discover -s tests -v

demo:
	$(PYTHON) arranger.py

build:
	$(PYTHON) -m pip wheel . -w dist --no-deps

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info
