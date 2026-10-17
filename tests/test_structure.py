"""The structure this tree is built to, as budgets that may only shrink.

The gate already treats a moved count as the signal - ``make check`` reports the
test count, and a change that moves it has to say so. This module applies the
same idea to the shape of the code, because a restructuring that is not measured
is a preference: "smaller" and "simpler" are opinions until a number says which
function and by how much.

Three meters, because they catch different defects:

- **complexity**, counted as decision points, with a nested function body
  *excluded* - a closure is measured where it is defined rather than folded into
  its parent. A 228-line handler with thirteen top-level branches is still caught
  by the other two meters, which is the point of having them.
- **length**, which catches a function that is long without being branchy. A
  route handler that spells out four fallbacks in sequence reads badly at 228
  lines even when each fallback is one ``if``.
- **parameters**, which catches the shape that a parameter object should have
  folded: more than a dozen words in a signature is a missing value object.

Every entry is the worst value the tree had when the entry was written. **The
only edit this table should ever receive is a decrease.** If a number has to go
up, that is a decision to state in the commit - which is exactly what a budget
is for: it makes the decision visible instead of letting it pass quietly.

The second test here is the other half of encapsulation. A name another module
imports is public, whatever its spelling says. The allowlist that held the debt
from before that rule is empty now; it stays as the place a deliberate exception
has to be written down, and the test fails in both directions - a new private
import is caught, and an entry that is no longer used cannot rot there.
"""

from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple, Union

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "arranger"

# The five top-level modules are part of the library the gate measures, and they
# stay flat files: `tabgp`'s lazy `import guitarpro` is the licensing boundary and
# a package `__init__` would put a file in front of it. See
# `tests/test_optional_extras.py`, which is the other half of that argument.
TOP_LEVEL = ("tabstaff.py", "tabxml.py", "tabgp.py", "headxml.py", "grip_chart.py")


@dataclass(frozen=True)
class Budget:
    """The ceiling on one library module's worst function."""

    complexity: int
    lines: int
    parameters: int


# Keyed by path relative to the repository root, so the message names the file
# the way an editor sees it. Every library module needs an entry: a new module
# arriving without a budget is the one thing this table cannot express as a
# default, because a default is a ceiling nobody chose. A module that holds no
# function yet gets a small policy ceiling rather than a measurement, so the
# first method it grows is still a deliberate size.
BUDGETS: Dict[str, Budget] = {
    "arranger/__init__.py": Budget(14, 151, 1),
    "arranger/__main__.py": Budget(5, 10, 2),
    "arranger/bass.py": Budget(16, 82, 6),
    "arranger/bass_merge.py": Budget(6, 66, 3),
    "arranger/chords.py": Budget(17, 46, 5),
    "arranger/cli.py": Budget(13, 131, 11),
    "arranger/context.py": Budget(5, 30, 3),
    "arranger/cost.py": Budget(12, 140, 7),
    "arranger/decisions.py": Budget(11, 137, 9),
    "arranger/fingers.py": Budget(10, 41, 2),
    "arranger/grid.py": Budget(9, 25, 3),
    "arranger/grips.py": Budget(22, 128, 9),
    "arranger/harmony.py": Budget(4, 21, 2),
    "arranger/melody_alone.py": Budget(6, 74, 14),
    "arranger/movement.py": Budget(23, 360, 15),
    # `ArrangeOptions` is a flat dataclass of knobs with no methods today.
    "arranger/options.py": Budget(5, 30, 3),
    "arranger/parts.py": Budget(9, 45, 1),
    "arranger/render.py": Budget(18, 130, 2),
    "arranger/routes.py": Budget(13, 229, 12),
    "arranger/slots.py": Budget(9, 136, 12),
    "arranger/steps.py": Budget(1, 49, 15),
    "arranger/texture.py": Budget(11, 57, 6),
    "arranger/tuning.py": Budget(5, 28, 2),
    "headxml.py": Budget(29, 239, 12),
    "grip_chart.py": Budget(14, 84, 5),
    "tabgp.py": Budget(27, 223, 13),
    "tabstaff.py": Budget(27, 396, 13),
    "tabxml.py": Budget(24, 176, 12),
}

# Importing a `_`-prefixed name from a sibling is the coupling this test exists to
# retire, and the list is now empty: every name another module reads is public.
# The test still fails in both directions, so a new private import is caught and a
# deleted one cannot leave a stale entry behind.
ALLOWED_PRIVATE_IMPORTS: Set[str] = set()


FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _library_modules() -> List[Path]:
    """Every module the budgets cover: the engine package and the five front ends."""
    return sorted(ENGINE.glob("*.py")) + [ROOT / name for name in TOP_LEVEL]


def _complexity(node: FunctionNode) -> int:
    """Decision points in `node`, not counting the bodies of nested functions.

    A closure is a function in its own right and is measured as one; folding it
    into its parent would report a long list of small helpers as one branching
    monster, which is the opposite of what this number is for.
    """
    score = 1

    def walk(current: ast.AST) -> None:
        nonlocal score
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.IfExp,
                    ast.ExceptHandler,
                    ast.comprehension,
                ),
            ):
                score += 1
            elif isinstance(child, ast.BoolOp):
                # `a and b` is one branch; `a and b and c` is two.
                score += len(child.values) - 1
            elif isinstance(child, ast.Match):
                score += len(child.cases)
            walk(child)

    walk(node)
    return score


def _parameters(node: FunctionNode) -> int:
    """How many words the signature asks the caller for, `self`/`cls` excluded."""
    args = node.args
    count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    count += 1 if args.vararg else 0
    count += 1 if args.kwarg else 0
    positional = args.posonlyargs + args.args
    if positional and positional[0].arg in ("self", "cls"):
        count -= 1
    return count


def _functions(path: Path) -> Iterator[Tuple[FunctionNode, int, int, int]]:
    """Every function in `path` with its (length, complexity, parameters)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno or node.lineno
            yield node, end - node.lineno + 1, _complexity(node), _parameters(node)


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _target_of(node: ast.ImportFrom) -> str:
    """The module an `ImportFrom` reaches, as a bare module name.

    Relative imports are resolved against the package the file sits in, which is
    always `arranger/` for an engine module and the repository root for a front
    end. Only the module name matters here: the importer is known from the path.
    """
    if node.level:
        return node.module or ""
    module = node.module or ""
    if module == "arranger":
        return "__init__"
    if module.startswith("arranger."):
        return module.split(".", 1)[1]
    return module


def _private_imports(path: Path) -> Iterator[str]:
    """`importer -> home.private_name` for every private name `path` imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    importer = path.stem
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        target = _target_of(node)
        if not target or target == importer:
            continue
        for alias in node.names:
            if alias.name.startswith("_"):
                yield f"{importer} -> {target}.{alias.name}"


class TestTheMeter(unittest.TestCase):
    """The meters are tested, because a budget is only as good as its ruler."""

    def test_complexity_does_not_fold_a_nested_function_into_its_parent(self):
        """A closure's branches belong to the closure, not to the function holding it."""
        tree = ast.parse(
            "def outer(x):\n"
            "    def inner(y):\n"
            "        if y:\n"
            "            return 1\n"
            "        return 2\n"
            "    if x:\n"
            "        return inner(x)\n"
            "    return 0\n"
        )
        outer = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
        inner = next(n for n in outer.body if isinstance(n, ast.FunctionDef))
        self.assertEqual(_complexity(outer), 2)
        self.assertEqual(_complexity(inner), 2)

    def test_parameters_do_not_ask_for_self(self):
        """`self` is not a word the caller supplies, so it is not a parameter."""
        tree = ast.parse(
            "class A:\n"
            "    def method(self, a, b=1, *args, c, **kwargs):\n"
            "        return a\n"
        )
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        method = next(n for n in klass.body if isinstance(n, ast.FunctionDef))
        self.assertEqual(_parameters(method), 5)


class TestTheBudgets(unittest.TestCase):
    """No function grows past the ceiling its module was measured at."""

    def test_every_library_module_has_a_budget(self):
        """A new module must state its ceiling, because a default is nobody's decision."""
        measured = {_relative(path) for path in _library_modules()}
        self.assertEqual(
            sorted(measured ^ set(BUDGETS)),
            [],
            "the budget table and the library disagree - add an entry for a new "
            "module, or delete the entry for one that no longer exists",
        )

    def test_no_function_exceeds_its_module_budget(self):
        """Every function is inside its module's complexity, length and parameter ceiling."""
        offenders: List[str] = []
        for path in _library_modules():
            budget = BUDGETS[_relative(path)]
            for node, length, complexity, parameters in _functions(path):
                where = f"{_relative(path)}:{node.lineno} {node.name}"
                if complexity > budget.complexity:
                    offenders.append(
                        f"{where} has complexity {complexity}, over {budget.complexity}"
                    )
                if length > budget.lines:
                    offenders.append(f"{where} is {length} lines, over {budget.lines}")
                if parameters > budget.parameters:
                    offenders.append(
                        f"{where} takes {parameters} parameters, over {budget.parameters}"
                    )
        self.assertEqual(
            offenders,
            [],
            "a function over its budget is a function to split, not a budget to "
            "raise; if the increase is deliberate, edit BUDGETS in this file and "
            "say why in the commit",
        )


class TestTheEncapsulationRule(unittest.TestCase):
    """A name another module imports is public, whatever it is called."""

    def test_no_module_reaches_into_a_sibling(self):
        """No private name crosses a module boundary outside the recorded debt.

        The allowlist is the debt from before the rule, and it shrinks. An entry
        that is no longer needed fails here too, so the list cannot quietly keep
        a name that has since been made public.
        """
        found: Set[str] = set()
        for path in _library_modules():
            found.update(_private_imports(path))
        self.assertEqual(
            sorted(found - ALLOWED_PRIVATE_IMPORTS),
            [],
            "a private name is imported from another module - make it public, or "
            "add it to ALLOWED_PRIVATE_IMPORTS with a reason",
        )
        self.assertEqual(
            sorted(ALLOWED_PRIVATE_IMPORTS - found),
            [],
            "the allowlist names an import that no longer exists - delete the entry",
        )


if __name__ == "__main__":
    unittest.main()
