"""The top-level front ends form a DAG too, and this is what holds them to it.

`tests/meta_package_dag.py` covers the engine package. The modules beside it are
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

The package and the front ends no longer name each other: `tuning` moved to a
top-level module, so `tabstaff` imports `tuning` directly and no longer reaches
into `arranger` at module scope. The cycle that used to exist on paper
(`arranger.__getattr__` resolves `tabstaff`, `tabstaff` imported `arranger.tuning`,
importing a submodule ran `__init__` first) is gone. The last class here still
measures the two runtime facts rather than arguing about them.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Set

from tests.support import FRONT_ENDS

ROOT = Path(__file__).resolve().parent.parent
FRONT_ENDS_BY_STEM: Set[str] = {Path(name).stem for name in FRONT_ENDS}

# The edges that are deliberate, each with the reason it is sound. Anything added
# here has to justify itself in a comment; the stale check below is what forces an
# entry to leave when its import does.
ALLOWED_FRONT_EDGES: Dict[str, Set[str]] = {
    # The public facade: `arranger.__getattr__` resolves the whole rendering surface
    # through this module, so it must hold the names the other two define.
    "tabstaff": {"tabgp", "tabxml", "tabstaff_ascii", "tabstaff_html"},
    # The grid lives in `tabstaff_grid`, shared by `tabstaff_ascii` and
    # `tabstaff_html`. Both renderers import from it, which is the deliberate
    # coupling that keeps the two grids from drifting apart.
    "tabstaff_ascii": {"tabstaff_grid"},
    "tabstaff_html": {"tabstaff_grid"},
    # The placement moved out of `tabxml`, so this is now the shared core rather
    # than a writer-to-writer edge. `tabxml` still re-exports the two names it uses.
    "tabxml": {"tabscore"},
    "tabgp": {"tabscore"},
    # `headxml` names the facade's public surface directly (`from arranger import
    # CHORD_FILLS_COMP`), so it cannot import against a blank `arranger` package
    # and is excluded from `test_the_rendering_front_ends_import_with_the_facade_absent`.
    # It imports no sibling front end, so its edge set is empty.
    "headxml": set(),
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


def _arranger_imports(path: Path) -> List[str]:
    """The `arranger.*` submodules `path` imports at module scope, by name.

    The load-bearing rule is that a front end may reach into the engine package
    only through `arranger.step_types` (the value types) and top-level `tuning`.
    Anything deeper - `arranger.chords`, `arranger.grips`, `arranger.cost`, ... -
    is domain knowledge that belongs in the engine, not in a renderer, and a
    module-scope import of it couples the renderer to the engine's internal
    layering at import time.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.startswith("arranger."):
                found.append(node.module)
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

    def test_front_ends_only_reach_step_types_from_arranger(self):
        """A front end may import `arranger.step_types`, nothing deeper.

        `headxml` is exempt: it names the facade's public surface directly
        (`from arranger import CHORD_FILLS_COMP`), which is why `demo.main()`
        imports it only after the facade is complete.
        """
        offenders: List[str] = []
        for name in FRONT_ENDS:
            module = Path(name).stem
            # `headxml` names the facade's public surface directly; `grip_chart`
            # is a standalone chart-generator script (not imported as a library)
            # that legitimately reads the engine's grip tables to build the chart.
            if module in ("headxml", "grip_chart"):
                continue
            for imported in _arranger_imports(ROOT / name):
                sub = imported.split(".", 1)[1]
                if sub != "step_types":
                    offenders.append(f"{module} imports {imported}")
        self.assertEqual(
            offenders,
            [],
            "a front end imports an arranger submodule other than step_types at "
            "module scope - move the import inside a function, or reach step_types",
        )

    def test_no_package_module_imports_a_front_end_at_module_scope(self):
        """`arranger` reaches the front ends lazily, never during its own import.

        This is the load-bearing half of the cycle. `headxml` names the facade's
        own public surface at module scope (`from arranger import ...`), so a
        module-scope import of it from inside the package would run it against a
        *partially initialised* `arranger`; `tabstaff` imports the package too,
        which runs the facade before the renderer gets to its own first line.

        So every reach is function-local or a `__getattr__` resolution:
        `demo.main()` imports the importer and the staff renderers, `cli` imports
        `tabstaff`, and the facade's seven re-exports go through PEP 562. The scan
        is over the whole package rather than the facade, because the CLI was the
        second module that could have taken the edge at import time.
        """
        offenders: List[str] = []
        for path in sorted((ROOT / "arranger").glob("*.py")):
            for imported in sorted(_module_imports(path)):
                offenders.append(f"arranger/{path.name} imports {imported}")
        self.assertEqual(
            offenders,
            [],
            "a package module imports a front end at module scope - keep it lazy",
        )


class TestTheRuntimeCycle(unittest.TestCase):
    """The package and the front ends name each other, and neither needs the other.

    On paper the two edges make a cycle: `arranger.__getattr__` resolves the staff
    renderers, while `tabstaff` imports `arranger.tuning`. It is inert, and that is
    a measurement rather than an argument - the facade's edge is taken only *after*
    the facade is complete, and the four rendering front ends reach a leaf that
    needs nothing from it. Both halves are pinned here in a fresh interpreter,
    because this process imported all of them at collection time.
    """

    def test_the_facade_loads_no_front_end(self):
        """`import arranger` on its own leaves every front end unimported.

        The AST scan in the class above says no module-scope import exists. This is
        the same fact measured: a `__getattr__` is only lazy if nothing touches the
        attribute during the import, and a module-scope *read* of one of these names
        would import the front end just as surely as an import statement would.
        """
        expected = sorted(FRONT_ENDS_BY_STEM)
        code = (
            "import sys, arranger;"
            f" print(sorted(n for n in {expected!r} if n in sys.modules))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), "[]", "import arranger loaded a front end"
        )

    def test_the_rendering_front_ends_import_with_the_facade_absent(self):
        """The reverse direction is a leaf, so no cycle can fire.

        `sys.modules['arranger']` is replaced with a blank package before the
        imports, so the facade never runs and has no `__getattr__` at all. The four
        renderers still import, each reaching `tuning` directly (top-level module)
        and `arranger.step_types` through the blank package's `__path__`, and the
        blank module is still the one bound afterwards - which is the claim:
        nothing here needed a public name from the facade.

        `headxml` is deliberately absent. It names the facade's public surface
        (`from arranger import CHORD_FILLS_COMP`), so it fails against a blank
        package; that is why `demo.main()` imports it *after* the facade is
        complete, and why the module-scope rule above is not tidiness.
        """
        package_dir = str(ROOT / "arranger")
        code = (
            "import sys, types;"
            " blank = types.ModuleType('arranger');"
            f" blank.__path__ = [{package_dir!r}];"
            " sys.modules['arranger'] = blank;"
            " import tabscore, tabstaff, tabxml, tabgp;"
            " assert sys.modules['arranger'] is blank, 'a front end ran the facade';"
            " from arranger.step_types import ArrangementStep;"
            " assert tabscore.ArrangementStep is ArrangementStep;"
            " assert tabstaff.ArrangementStep is ArrangementStep;"
            " assert tabxml.ArrangementStep is ArrangementStep;"
            " assert tabgp.ArrangementStep is ArrangementStep;"
            " print('ok')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
