"""No engine name is defined and then referenced nowhere.

A name whose only occurrence in the tree is its own definition is dead code: nothing
imports it, nothing calls it and no test holds it. `texture.families_for_arity` was exactly
that for two phases - it answered for a grip-family axis that had been deleted - and no
other check can see it, because a dead function is still lint-clean and still type-checks.
This is the guard that fails on the commit that orphans a name.

**A deliberate test seam passes**, because a test is a referrer: the rule is "referenced
nowhere but its own definition", not "referenced by no engine module". What fails is a name
with no referrer at all.

A reference is a *load*, an attribute access, or an import - not a mention in prose, which
is why string literals are not counted. That is what makes the guard bite on the case it
exists for: a name kept alive only by its own `__all__` entry, with no import to match,
reads as a broken export rather than as a live name.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import List, Set

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "arranger"

# Everything that could refer to an engine name: the engine itself, the top-level front
# ends and helpers, and the tests. `SEARCHED` is derived rather than listed so a new module
# cannot be forgotten by the check - the same trap AGENTS.md records for the Makefile's
# `MODULES`.
SEARCHED = (
    sorted(ENGINE.glob("*.py"))
    + sorted(ROOT.glob("*.py"))
    + sorted((ROOT / "tests").glob("*.py"))
)


def _defined(path: Path) -> Set[str]:
    """The module-level names `path` defines: functions, classes and assignments."""
    names: Set[str] = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _referenced(path: Path) -> Set[str]:
    """Every name `path` refers to: loads, attribute accesses and imports."""
    found: Set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[-1] for alias in node.names)
    return found


class TestNoEngineNameIsOrphaned(unittest.TestCase):
    """Every module-level name has a referrer somewhere.

    Covers both the engine package (`arranger/`) and top-level modules
    (`headxml.py`, etc.), because a dead name at either level
    is still dead code.
    """

    def test_every_top_level_name_is_referenced(self) -> None:
        referenced: Set[str] = set()
        for path in SEARCHED:
            referenced |= _referenced(path)

        orphans: List[str] = []
        for path in sorted(ENGINE.glob("*.py")) + sorted(ROOT.glob("*.py")):
            for name in sorted(_defined(path)):
                # A dunder is the language's or the packaging's rather than the engine's:
                # `__all__` is read by `import *`, `__version__` by `pyproject.toml`.
                if name.startswith("__"):
                    continue
                if name not in referenced:
                    orphans.append(f"{path.name}: {name}")

        self.assertEqual(
            orphans,
            [],
            "these names are defined and referenced nowhere: delete them, or add "
            "the caller (or the test) that was supposed to hold them",
        )


if __name__ == "__main__":
    unittest.main()
