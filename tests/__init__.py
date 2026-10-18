"""The test suite.

Present so `tests.support` is importable as a package module from every test
file. It changes how the suite is *discovered*: without it, `unittest discover
-s tests` puts `tests/` itself on `sys.path` and imports each file as a
top-level module; with it, `tests` is a package and discovery has to be run from
the repository root with the top-level directory set - which is what `make test`
does. Run it that way, not from inside `tests/`.
"""
