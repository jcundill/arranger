"""The optional extras stay optional, and PyGuitarPro stays at arm's length.

The LGPL argument for this project is a structural one, and until now it was a
promise rather than a gate. Two facts keep the distribution clearly not a
combined work of PyGuitarPro:

1. it is a **runtime dependency of neither the package nor the test suite** -
   `pip install jazz-arranger` never pulls it, and the GP tests skip without it;
2. `tabgp` imports it **inside a function**, so importing the module costs
   nothing and the one place a file could couple the library to it is a single
   auditable line.

Fact 2 had no test. The MusicXML extra has had one since the optional extras were
introduced (`test_the_musicxml_renderers_are_lazy`), which makes the asymmetry
worse rather than harmless: the *licensed* dependency was the unguarded one.

The second half of that fact is why the five front ends stay **flat modules**.
A `tabgp/` package would put an `__init__.py` in front of the lazy import, and a
future author moving one line into it would silently turn `import arranger` into
a PyGuitarPro import. Keeping the names flat is not stylistic - it is what makes
the boundary a property of one file.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent

# The names the distribution ships (see `pyproject.toml`). `grip_chart` used to
# be a developer script here; it has been removed, so only the shipped names
# remain flat modules.
SHIPPED = (
    "tabscore",
    "tabstaff",
    "tabstaff_grid",
    "tabstaff_ascii",
    "tabstaff_html",
    "tabxml",
    "tabgp",
    "headxml",
    "headxml_cli",
    "headxml_model",
    "headxml_read",
    "headxml_repeats",
    "headxml_timeline",
    "tuning",
)
FLAT_MODULES = SHIPPED


def _guitarpro_imports(tree: ast.Module) -> List[Tuple[int, bool]]:
    """Every `guitarpro` import in `tree`, with whether it sits inside a function."""
    found: List[Tuple[int, bool]] = []

    def walk(node: ast.AST, inside_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            now_inside = inside_function or isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            )
            if isinstance(child, ast.Import):
                if any(
                    alias.name.split(".")[0] == "guitarpro" for alias in child.names
                ):
                    found.append((child.lineno, now_inside))
            elif isinstance(child, ast.ImportFrom):
                if (child.module or "").split(".")[0] == "guitarpro":
                    found.append((child.lineno, now_inside))
            walk(child, now_inside)

    walk(tree, False)
    return found


class TestTheGuitarProBoundary(unittest.TestCase):
    """PyGuitarPro is imported lazily, and one file is the whole boundary."""

    def test_importing_tabgp_does_not_import_guitarpro(self):
        """Blocking the module outright must not stop `arranger` or `tabgp` importing.

        `sys.modules['guitarpro'] = None` makes any import of it raise, so this is
        the same proof the MusicXML extra gets: the library is importable on a
        machine that has neither extra installed.
        """
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.modules['guitarpro'] = None;"
                " import arranger, tabstaff, tabgp;"
                " print(tabgp.format_gp5.__name__)",
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("format_gp5", result.stdout)

    def test_guitarpro_is_imported_inside_a_function(self):
        """The import must be function-local; module scope would make it a dependency.

        This is the line an editor is most likely to "tidy": moving `import
        guitarpro` to the top of `tabgp.py` reads like a cleanup and changes the
        distribution's licence analysis. The assertion is deliberately on the AST
        rather than on `sys.modules`, because it catches the move even on a
        machine where PyGuitarPro happens to be installed.
        """
        path = ROOT / "tabgp.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = _guitarpro_imports(tree)
        self.assertTrue(imports, "tabgp no longer imports PyGuitarPro at all")
        at_module_scope = [line for line, inside in imports if not inside]
        self.assertEqual(
            at_module_scope,
            [],
            "PyGuitarPro is imported at module scope in tabgp.py - it must stay "
            "inside the function that uses it, or `import arranger` pulls an "
            "LGPL dependency",
        )


class TestTheModuleSurface(unittest.TestCase):
    """The six front ends are flat modules, and the five shipped ones stay shipped."""

    def test_the_front_ends_are_flat_modules(self):
        """None of the six has an `__init__.py` in front of its contents."""
        for name in FLAT_MODULES:
            with self.subTest(module=name):
                module = importlib.import_module(name)
                self.assertFalse(
                    hasattr(module, "__path__"),
                    f"{name} is a package - the lazy-import boundary belongs to "
                    "one file, not a directory",
                )

    def test_the_distribution_ships_the_expected_names(self):
        """`py-modules` names exactly the shared core, the renderers and the importer."""
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        shipped = data["tool"]["setuptools"]["py-modules"]
        self.assertEqual(sorted(shipped), sorted(SHIPPED))


if __name__ == "__main__":
    unittest.main()
