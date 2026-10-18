"""The top-level front ends form a DAG too, and this is what holds them to it.

`tests/test_package_dag.py` covers the engine package. The modules beside it are
not in that order, so their imports were unconstrained: a renderer could import
another renderer, or the facade could import one at module scope, and nothing
failed. This test closes that gap with the same shape as the package rule - the
deliberate edges are named, everything else is refused, and an allowance that
outlives its import fails.

`tabstaff` is the public rendering surface: it re-exports the MusicXML and GP5
renderers so `from arranger import format_musicxml` keeps one spelling, and its
two edges are that facade rather than accidental coupling. The writers' edge to
`tabscore` is different: both need the same score placement, and that shared core
is what keeps `tabgp` and `tabxml` from depending on one another.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Dict, Set

from tests.support import FRONT_ENDS

ROOT = Path(__file__).resolve().parent.parent
FRONT_ENDS_BY_STEM: Set[str] = {Path(name).stem for name in FRONT_ENDS}

# The edges that are deliberate, each with the reason it is sound. Anything added
# here has to justify itself in a comment; the stale check below is what forces an
# entry to leave when its import does.
ALLOWED_FRONT_EDGES: Dict[str, Set[str]] = {
    # The public facade: `arranger.__getattr__` resolves the whole rendering surface
    # through this module, so it must hold the names the other two define.
    "tabstaff": {"tabgp", "tabxml"},
    # The placement moved out of `tabxml`, so this is now the shared core rather
    # than a writer-to-writer edge. `tabxml` still re-exports the two names it uses.
    "tabxml": {"tabscore"},
    "tabgp": {"tabscore"},
}


def _module_imports(path: Path) -> Set[str]:
    """The front ends `path` imports at module scope, as module stems.

    Module scope is the boundary that matters: a function-local import is how the
    facade and the CLI stay lazy, and forbidding it would break the optional extras.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                stem = alias.name.rsplit(".", 1)[-1]
                if stem in FRONT_ENDS_BY_STEM:
                    found.add(stem)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            stem = node.module.rsplit(".", 1)[-1]
            if stem in FRONT_ENDS_BY_STEM:
                found.add(stem)
    return found


class TestTheFrontEndDag(unittest.TestCase):
    """No front end imports another outside the recorded facade and debt."""

    def test_no_front_end_imports_another_outside_the_recorded_edges(self):
        """A renderer importing a sibling is a coupling, not an implementation detail.

        The whole point of the top-level split is that a caller can use one writer
        without the other's dependencies. An import between them makes that false
        even when the imported module's optional extra is lazy.
        """
        offenders = []
        for name in FRONT_ENDS:
            module = Path(name).stem
            allowed = ALLOWED_FRONT_EDGES.get(module, set())
            for imported in sorted(_module_imports(ROOT / name)):
                if imported != module and imported not in allowed:
                    offenders.append(f"{module} imports {imported}")
        self.assertEqual(
            offenders,
            [],
            "a front end imports another - record the edge in "
            "ALLOWED_FRONT_EDGES with a reason, or remove the import",
        )

    def test_no_allowed_front_edge_is_stale(self):
        """An allowance must still permit an import that exists."""
        stale = []
        for module, allowed in ALLOWED_FRONT_EDGES.items():
            actual = _module_imports(ROOT / f"{module}.py")
            for edge in sorted(allowed - actual):
                stale.append(f"{module} -> {edge} is allowed but not imported")
        self.assertEqual(
            stale, [], "an allowed front-end edge no longer exists - delete the entry"
        )

    def test_the_facade_does_not_import_a_front_end_at_module_scope(self):
        """`arranger` re-exports the front ends lazily, not at import time.

        `tabstaff` imports `arranger`, so a module-level import in the other
        direction would be a cycle - and it would also make `import arranger`
        pull in the MusicXML and GP5 writers for a caller who only wants the
        engine. `arranger.__getattr__` and `main()` are the two lazy seams.
        """
        self.assertEqual(
            sorted(_module_imports(ROOT / "arranger" / "__init__.py")),
            [],
            "the facade imports a front end at module scope - keep it lazy",
        )


if __name__ == "__main__":
    unittest.main()
