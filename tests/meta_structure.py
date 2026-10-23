"""The structure this tree is built to, as budgets that may only shrink.

The gate already treats a moved count as the signal - ``make check`` reports the
test count, and a change that moves it has to say so. This module applies the
same idea to the shape of the code, because a restructuring that is not measured
is a preference: "smaller" and "simpler" are opinions until a number says which
function and by how much.

Four meters, because they catch different defects:

- **complexity**, counted as decision points, with a nested function body
  *excluded* - a closure is measured where it is defined rather than folded into
  its parent. A 228-line handler with thirteen top-level branches is still caught
  by the other two meters, which is the point of having them.
- **length**, which catches a function that is long without being branchy. A
  route handler that spells out four fallbacks in sequence reads badly at 228
  lines even when each fallback is one ``if``.
- **parameters**, which catches the shape that a parameter object should have
  folded: more than a dozen words in a signature is a missing value object.
- **single definition**, which catches a name bound twice in one module body. The
  second binding shadows the first, so an identical copy changes nothing and no
  test can see it - `grips` carried `_INTERVAL_CLASSES` and `INTERVAL_NAMES` twice
  for exactly that reason. It matters most during a module split, where a block
  that is *copied* rather than cut leaves the original behind and still imports.

Every entry is the worst value the tree had when the entry was written. **The
only edit this table should ever receive is a decrease.** If a number has to go
up, that is a decision to state in the commit - which is exactly what a budget
is for: it makes the decision visible instead of letting it pass quietly.

The other tests here are structural rather than numerical. A name another module
imports is public, whatever its spelling says - and the rule covers the two ways
to import it: the name itself, and a module alias followed by a private
attribute. Both allowlists fail in both directions, so a new reach is caught and
an entry that is no longer used cannot rot there.

The axis graph is the third kind. Each axis is answered by exactly one function,
in the module that owns its vocabulary, and this file reads those signatures to
hold them to the dependencies they declare - `parts` reads nothing, `bass` reads
`parts` and the texture, while the metre is read by
its own module rather than by an axis. A signature is the one place
an implicit dependency cannot hide, which is why the table below is asserted
against the AST rather than promised in a docstring.

The file also keeps the suite's own split honest: a test module is `test_*.py` (the
music, run by `make test-features`) or `meta_*.py` (the tree, run by
`make test-meta`), and `make test` is both. `TestTheSplit` fails on a file that is
neither, because a pattern-based gate would otherwise stop running it in silence.
"""

from __future__ import annotations

import ast
import fnmatch
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple, Union

from tests.support import FRONT_ENDS

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
ENGINE = ROOT / "arranger"

#: The two halves of the suite, by filename. `make test-features` discovers the
#: first pattern and `make test-meta` the second - so the half is the file's name,
#: not a list somewhere that has to be kept in step. A test about the music is
#: `test_*.py`; a test about the *tree* (the module graph, the budgets, the seams,
#: the generated chart, the fixture corpus, the extras' laziness, the explanation
#: contract) is `meta_*.py`. When in doubt it is `test_*.py`: that half runs first,
#: so a mis-filed test is seen early rather than never.
FEATURE_PATTERN = "test_*.py"
META_PATTERN = "meta_*.py"

#: The files in `tests/` that are not test modules: the package marker and the two
#: shared helpers. They match neither half and that is their whole job.
TEST_HELPERS: Set[str] = {"__init__.py", "support.py", "fixture_scores.py"}

# The top-level modules are part of the library the gate measures, and they stay
# flat files: `tabgp`'s lazy `import guitarpro` is the licensing boundary and a
# package `__init__` would put a file in front of it. See
# `tests/meta_optional_extras.py`, which is the other half of that argument. The
# tuple itself lives in `support`, because the front-end DAG test reads it too.


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
    "arranger/__init__.py": Budget(2, 5, 1),
    "arranger/__main__.py": Budget(5, 10, 2),
    # The printing front end, measured as it stood when it moved out of the facade:
    # the demonstration is one long function by design - a sequence of examples,
    # each with the comment that says what it demonstrates - so its ceiling is the
    # measurement, not a target. It imports `steps` and `render` and nothing else.
    "arranger/demo.py": Budget(14, 151, 0),
    "arranger/annotation.py": Budget(18, 130, 2),
    "arranger/bass_place.py": Budget(16, 79, 6),
    "arranger/bass_rules.py": Budget(10, 82, 6),
    # `walking_slots` takes a seventh parameter at Stage 3 of
    # `docs/history/rhythm-request.md`: `rhythm=` is the bass's **positions**, which
    # the metre's three facts cannot express (a sparse `1,3` is not a grouping).
    # Deliberate rather than an accident of growth - the metre's own three are one
    # grouping already, and the rhythm is a fourth fact rather than a second spelling
    # of one. The body did not grow past its length budget: the pitch emission moved
    # out to `_walk_notes`.
    "arranger/bass.py": Budget(10, 78, 7),
    "arranger/bass_merge.py": Budget(6, 66, 3),
    "arranger/chords.py": Budget(17, 46, 5),
    "arranger/cli.py": Budget(13, 131, 11),
    "arranger/context.py": Budget(5, 30, 3),
    "arranger/cost.py": Budget(12, 140, 7),
    "arranger/decisions.py": Budget(11, 137, 9),
    "arranger/fingers.py": Budget(10, 41, 2),
    # The named figures and their parser went, so what is left is the request's
    # `Rhythm` and the lattice under it: re-measured, not lowered by eye.
    "arranger/grid.py": Budget(8, 23, 3),
    "arranger/grip_tables.py": Budget(7, 39, 3),
    "arranger/grip_place.py": Budget(19, 66, 5),
    "arranger/grips.py": Budget(22, 128, 9),
    "arranger/grouping.py": Budget(6, 36, 3),
    "arranger/melody_alone.py": Budget(6, 74, 14),
    # The axis keywords left `resolve_knobs` (15 -> 9 parameters), so the module
    # ceiling is `resolve_policies`'s twelve rather than the reconciler's: the grid
    # parameter went with the axis. The axes are now one read of `options` and two
    # `settle_input_fact` calls where the defaults and the assignments used to be.
    "arranger/resolution.py": Budget(8, 114, 12),
    # `slot_state`'s grid branches left with the axis, so the ceiling is what it
    # measures rather than what it measured.
    "arranger/slot_plan.py": Budget(6, 78, 5),
    "arranger/step_prepare.py": Budget(6, 74, 9),
    # The value types and tab-cell primitives, split out of `tuning`: `Voicing`,
    # `ArrangementStep`, `Palette` and the six-line block renderer. Measured as it
    # stood when it moved, so the ceiling is the measurement.
    "arranger/step_types.py": Budget(5, 23, 1),
    "arranger/harmonised_route.py": Budget(8, 54, 8),
    # The dispatch table: eleven small functions, each an entry's claim or emit, so
    # the ceiling is `dispatch_step`'s four branches rather than any one route. The
    # longest entry is 19 lines because the two answers with nothing above the thumb
    # share one function and its reason.
    "arranger/route_dispatch.py": Budget(4, 19, 3),
    # The five axis keywords left `arrange_progression` (15 -> 10 parameters): they are
    # the engine's implementation, so `options=ArrangeOptions(...)` is the only door to
    # one. The body did not grow - it reads the resolved knobs and policies as values -
    # and the dispatch lives in `route_dispatch`, so this module is the loop, the knobs
    # and the merge.
    "arranger/movement.py": Budget(4, 89, 10),
    # `ArrangeOptions` is a flat dataclass of knobs with no methods today.
    "arranger/options.py": Budget(5, 30, 3),
    "arranger/parts.py": Budget(9, 45, 1),
    "arranger/render.py": Budget(11, 64, 2),
    "arranger/routes.py": Budget(6, 97, 12),
    "arranger/slots.py": Budget(9, 136, 12),
    # The facade's `arrange_progression` loses the same five (16 -> 10).
    "arranger/steps.py": Budget(1, 54, 10),
    "arranger/texture.py": Budget(11, 57, 6),
    # The instrument: tuning, the fretboard, the neck limits and the sentinels. The
    # value types (`Voicing`, `ArrangementStep`, `Palette`) and the tab-cell
    # primitives moved to `step_types`, so this ceiling is what is left after that
    # split rather than what the module measured before it.
    "arranger/tuning.py": Budget(4, 11, 2),
    # `arrange_xml_head` lost the five axis keywords and `grouping=` with them
    # (13 -> 8): the metre is one value, `time_signature=`, whose grouping is the one
    # fact of it a caller may set. `head_cli`'s branches live in `_print_metre_notes`,
    # and the merge block in `_head_slots`, so neither raises this budget.
    "headxml.py": Budget(17, 113, 8),
    "grip_chart.py": Budget(14, 84, 5),
    "tabgp.py": Budget(19, 151, 13),
    "tabscore.py": Budget(10, 98, 5),
    "tabstaff.py": Budget(17, 195, 13),
    "tabxml.py": Budget(12, 176, 12),
}

# Importing a `_`-prefixed name from a sibling is the coupling this test exists to
# retire, and the list is now empty: every name another module reads is public.
# The test still fails in both directions, so a new private import is caught and a
# deleted one cannot leave a stale entry behind.
ALLOWED_PRIVATE_IMPORTS: Set[str] = set()

# Reaching a sibling's `_`-prefixed name through a module alias is the same coupling
# as importing it by name, and it was invisible while only `ImportFrom` was read.
# The list is empty now: every name another module reaches is public, and the six
# dead delegates that used to spell the rest are gone. The test fails in both
# directions, so a new reach is caught and a deleted one cannot leave a stale entry.
ALLOWED_PRIVATE_ATTRIBUTES: Set[str] = set()

# Tests reach into arranger privates too, and that coupling is invisible unless it
# is named. TEST_SEAMS records every private name a test file imports from an
# arranger module, so a refactor that renames or removes one fails here rather
# than silently breaking a test. The test below fails in both directions: a new
# reach is caught, and a seam that no longer exists cannot rot.
#
# Each entry is `test_module -> arranger.module._private_name`, the same shape
# the encapsulation meter uses for library modules.
TEST_SEAMS: Set[str] = {
    # A test helper reads the phrase a cost criterion names.
    "test_palette -> arranger.annotation._criterion_phrase",
    # The explanation invariant reads the omission clause directly.
    "meta_explanations -> arranger.annotation._omission_clause",
    # Bass tests read the walking bass's private helpers.
    "test_bass -> arranger.bass._bass_harmony",
    "test_bass -> arranger.bass._walking_bass_line",
    # Walking bass tests read the melody-in-force helpers.
    "test_walking_bass -> arranger.bass._melody_in_force",
    "test_walking_bass -> arranger.bass._melody_timeline",
    # Bass rules tests read the no-room reason.
    "test_bass -> arranger.bass_rules._comping_no_room_reason",
    # Comping tests read the grip generators and palette directly.
    "test_comping -> arranger.grips._comping_palette",
    "test_comping -> arranger.grips._search_comping_voicings",
    # The generated-grips witness reads the drop-2 palette and guide tones.
    "test_generated_grips -> arranger.grips._drop2_palette",
    "test_generated_grips -> arranger.grips._guide_tones",
    # Exact fingerings read the grip tables and stack internals.
    "test_grips -> arranger.grips._guide_tones",
    "test_grips -> arranger.grips._close_stack_offsets",
    "test_grips -> arranger.grips._interval_set_for_grip",
    # Grip table tests read the layout/search partitions.
    "test_grip_tables -> arranger.grips._LAYOUT_GRIPS",
    "test_grip_tables -> arranger.grips._SEARCHED_GRIPS",
    # Placement tests read the searched shape and grip requests.
    "test_placement -> arranger.grip_place._searched_shape",
    "test_placement -> arranger.grips._drop2_6432_request",
    "test_placement -> arranger.grips._shell_request",
    # Texture tests read the interval offsets.
    "test_texture -> arranger.grips._interval_offsets",
    # Staff rendering reads the step's cells.
    "test_parts -> arranger.render._step_cells",
    "test_bass_hold -> arranger.render._step_cells",
    "test_bass_placement -> arranger.render._step_cells",
    # Tab rendering reads the step formatter directly.
    "test_tab_rendering -> arranger.render._format_step",
    # Repeat/volta rendering reads the as-written formatting.
    "test_headxml_repeats -> arranger.cli._as_written",
}


FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _library_modules() -> List[Path]:
    """Every module the budgets cover: the engine package and the top-level front ends."""
    return sorted(ENGINE.glob("*.py")) + [ROOT / name for name in FRONT_ENDS]


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


def _module_aliases(tree: ast.Module) -> Dict[str, str]:
    """The sibling modules `tree` binds to a local name, as alias -> module.

    Both spellings that bind a *module* are read: `from . import grips` (and its
    `as _grips` form) and `import arranger.grips as _grips`. `from .grips import x`
    binds `x`, not the module, so it is not an alias and is already covered by
    `_private_imports`.
    """
    siblings = {path.stem for path in ENGINE.glob("*.py")}
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name.rsplit(".", 1)[-1]
                if target in siblings:
                    aliases[alias.asname or alias.name] = target
        elif isinstance(node, ast.ImportFrom) and (
            (node.level == 1 and not node.module) or node.module == "arranger"
        ):
            for alias in node.names:
                if alias.name in siblings:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def _private_attributes(path: Path) -> Iterator[str]:
    """`importer -> home.private_name` for every private attribute reached by alias.

    A module alias is how the engine spelled the imports the import meter could not
    see: `alias._helper` is the same coupling as `from .module import _helper`, and
    only the second used to fail the gate.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases = _module_aliases(tree)
    importer = path.stem
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            continue
        target = aliases.get(node.value.id)
        if target and target != importer and node.attr.startswith("_"):
            yield f"{importer} -> {target}.{node.attr}"


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


#: The entry points a caller arranges through, and the seams the two of them share.
#: A retired axis keyword must not reappear on any of them.
ENTRY_POINTS: Tuple[Tuple[str, str], ...] = (
    ("arranger/movement.py", "arrange_progression"),
    ("arranger/steps.py", "arrange_progression"),
    ("arranger/resolution.py", "resolve_knobs"),
    ("headxml.py", "arrange_xml_head"),
    ("headxml.py", "_head_request"),
)

#: The axis names, live or retired, as the keyword each used to be spelled with, plus
#: `grouping` - the metre's third fact, which is a field of `TimeSignature` and so has
#: no keyword of its own either. `harmony` and `grid` are retired names kept here so a
#: future keyword cannot re-introduce one.
RETIRED_AXIS_KEYWORDS = frozenset({"texture", "bass", "parts", "harmony", "grid", "grouping"})



class TestTheAxesAreNotEntryPointKeywords(unittest.TestCase):
    """An axis is the implementation, so no entry point takes one as a keyword.

    The five axes answer *how* to play what the request asks for, so
    `options=ArrangeOptions(...)` is the one door to them; a keyword beside `options=`
    for the same thing is the second spelling this surface exists without. Nothing
    about a signature says so, so this is the standing check - it fails on the commit
    that adds one back, rather than on the first caller surprised by it.
    """

    def test_no_entry_point_takes_an_axis_keyword(self):
        found: List[str] = []
        for relative, function in ENTRY_POINTS:
            matches = [
                node
                for node, _length, _complexity, _count in _functions(ROOT / relative)
                if node.name == function
            ]
            self.assertTrue(matches, f"{relative} no longer defines {function}")
            for node in matches:
                # A catch-all would swallow the keyword rather than refuse it, which
                # is the one way this check could go quiet.
                self.assertIsNone(
                    node.args.kwarg,
                    f"{relative}: {function} takes **kwargs, so an axis keyword "
                    f"would be swallowed rather than refused",
                )
                found.extend(
                    f"{relative}: {function} takes {name}="
                    for name in sorted(
                        set(_parameter_names(node)) & RETIRED_AXIS_KEYWORDS
                    )
                )
        self.assertEqual(
            found,
            [],
            "an axis is the engine's implementation, so it has no keyword spelling: "
            "reach it through options=ArrangeOptions(...)",
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

    def test_no_module_reaches_into_a_sibling_by_attribute(self):
        """No private attribute crosses a module boundary through a module alias.

        This is the same rule as the import test above, and it was the blind spot:
        `alias._helper` names a private function exactly as plainly as
        `from .module import _helper` does, but only the second was read.
        The allowlist is the measured debt and fails in both directions, so a new
        reach is caught and a name that has been made public cannot linger here.
        """
        found: Set[str] = set()
        for path in _library_modules():
            found.update(_private_attributes(path))
        self.assertEqual(
            sorted(found - ALLOWED_PRIVATE_ATTRIBUTES),
            [],
            "a private attribute is reached through a module alias - make it "
            "public, or add it to ALLOWED_PRIVATE_ATTRIBUTES with a reason",
        )
        self.assertEqual(
            sorted(ALLOWED_PRIVATE_ATTRIBUTES - found),
            [],
            "the allowlist names an attribute that is no longer reached - delete "
            "the entry",
        )


def _test_files() -> List[Path]:
    """Every test module the seam rule covers - **both halves of the suite**.

    A meta test reaches into privates exactly as a feature test does, so scanning
    only `test_*.py` would have retired the seam list from the half that reads the
    engine's internals.
    """
    return sorted(TESTS.glob(FEATURE_PATTERN)) + sorted(TESTS.glob(META_PATTERN))


def _test_private_imports(path: Path) -> Iterator[str]:
    """`test -> home.private_name` for every private name a test imports.

    Mirrors `_private_imports` but scans the `tests/` tree instead of the
    library, and only reads `from arranger.<module> import <_name>` - the
    cross-module reach that makes a test coupled to implementation rather than
    contract.

    `_target_of` strips the `arranger.` prefix, so the full module name is
    rebuilt from `node.module` before the target is formed.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    importer = path.stem
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if not node.module or not node.module.startswith("arranger."):
            continue
        target = node.module.split(".", 1)[1]
        if not target or target == importer:
            continue
        for alias in node.names:
            if alias.name.startswith("_"):
                yield f"{importer} -> arranger.{target}.{alias.name}"


class TestTheTestSeams(unittest.TestCase):
    """Tests that reach into arranger privates declare the seam.

    A private name another module imports is public whatever it is called - and
    a test file is another module. The seam list is the measured debt, and it
    fails in both directions so neither a new reach nor a stale entry can pass
    quietly.
    """

    def test_every_test_private_reach_is_recorded(self):
        """No private name crosses from a test into arranger undocumented."""
        found: Set[str] = set()
        for path in _test_files():
            found.update(_test_private_imports(path))
        self.assertEqual(
            sorted(found - TEST_SEAMS),
            [],
            "a test imports a private arranger name - make it public, or "
            "add it to TEST_SEAMS with a reason",
        )
        self.assertEqual(
            sorted(TEST_SEAMS - found),
            [],
            "TEST_SEAMS names a reach that no longer exists - delete the entry",
        )


class TestTheSplit(unittest.TestCase):
    """The suite is two halves, and every module is in exactly one of them.

    `make test-features` discovers `test_*.py`, `make test-meta` discovers
    `meta_*.py`, and `make test` runs both - so the split is a way *in*, never a
    smaller gate. What it could narrow by accident is the union: a module named
    neither way is matched by neither pattern, so `make test` would stop running
    it while every other check stayed green. That is the trap the halves are worth
    a test for - a gate that enumerates its inputs by hand silently skips whatever
    was added last, and a *pattern* is only better than a list if something fails
    when a file falls between the patterns.
    """

    def test_every_module_matches_one_half(self):
        """A test file is `test_*.py` or `meta_*.py` - never neither."""
        found = {path.name for path in TESTS.glob("*.py")} - TEST_HELPERS
        self.assertTrue(found, "the tests/ tree has no test modules at all")
        strays = sorted(
            name
            for name in found
            if not (
                fnmatch.fnmatch(name, FEATURE_PATTERN)
                or fnmatch.fnmatch(name, META_PATTERN)
            )
        )
        self.assertEqual(
            strays,
            [],
            "a test module matches neither `test_*.py` (the music, "
            "`make test-features`) nor `meta_*.py` (the tree, `make test-meta`), "
            "so `make test` does not run it - rename it into a half",
        )

    def test_both_halves_are_populated(self):
        """Neither pattern may match nothing, or the split is quietly one-sided.

        A rename that emptied a half would leave `make test` green over the other
        one, which is the same failure as a stray file seen from the other side.
        """
        self.assertTrue(sorted(TESTS.glob(FEATURE_PATTERN)))
        self.assertTrue(sorted(TESTS.glob(META_PATTERN)))


#: Where each axis is answered, and what its resolver is allowed to read.
#:
#: `module.function` is the one place the axis is resolved, and it lives beside
#: the vocabulary rather than beside the composition: `resolution` wires the
#: answers together, but it does not own the words. The parameter names **are**
#: the dependency graph, so a resolver that quietly grows a `parts` argument is a
#: change to this table rather than an extra keyword nobody reviewed.
AXIS_RESOLVERS: Dict[str, Tuple[str, str]] = {
    "parts": ("parts", "resolve_parts"),
    "texture": ("texture", "parse_texture"),
    "bass": ("bass_rules", "resolve_bass"),
}

AXIS_DEPENDENCIES: Dict[str, Tuple[str, ...]] = {
    "parts": ("parts",),
    "texture": ("argument",),
    "bass": ("bass", "parts", "texture"),
}

#: The wiring `resolution.resolve_policies` calls, in the order the axes depend.
#: `_resolve_parts` first because `bass` reads its answer: it measures
#: the thumb against the route the selection names.
POLICY_WIRING: Tuple[str, ...] = (
    "_resolve_parts",
    "resolve_bass",
)


def _top_level_function(path: Path, name: str) -> FunctionNode:
    """The function `name` as `path` defines it in its module body."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{_relative(path)} does not define {name}")


def _parameter_names(node: FunctionNode) -> Tuple[str, ...]:
    """The words `node`'s signature asks its caller for, in order."""
    args = node.args
    positional = [argument.arg for argument in args.posonlyargs + args.args]
    if positional and positional[0] in ("self", "cls"):
        positional = positional[1:]
    return tuple(positional) + tuple(argument.arg for argument in args.kwonlyargs)


def _call_lines(node: FunctionNode) -> Dict[str, int]:
    """Where `node` first calls each bare function name, keyed by that name."""
    lines: Dict[str, int] = {}
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            lines.setdefault(child.func.id, child.lineno)
    return lines


class TestTheAxisResolvers(unittest.TestCase):
    """Each axis is answered where its vocabulary lives, from named dependencies.

    The axes were once resolved by one function, so `bass` could not be
    reasoned about - or tested - without `parts` and the texture in view,
    and the dependency between two of them was prose rather than a signature.
    These two tests are the shape of the repair, and they fail in both
    directions: a resolver that moves away from its module, and one that grows a
    dependency its table row does not name.
    """

    def test_each_axis_is_resolved_by_its_own_module(self):
        """The resolver's home is the axis's home, and its parameters are its deps."""
        for axis, (module, function) in AXIS_RESOLVERS.items():
            with self.subTest(axis=axis):
                node = _top_level_function(ENGINE / f"{module}.py", function)
                self.assertEqual(
                    _parameter_names(node),
                    AXIS_DEPENDENCIES[axis],
                    f"{module}.{function} reads more or less than the "
                    f"{axis} axis declares - update AXIS_DEPENDENCIES if the "
                    "dependency is real, or drop the parameter",
                )

    def test_the_composition_resolves_parts_before_the_axes_that_read_it(self):
        """`resolution` wires the axes in dependency order, not in call-site order.

        Read off the call sites rather than an arrangement's answer: a step whose
        parts happen to be right says nothing about which resolution ran first,
        while a call moved above `_resolve_parts` is visible here and silent in
        every tab.
        """
        lines = _call_lines(
            _top_level_function(ENGINE / "resolution.py", "resolve_policies")
        )
        missing = [name for name in POLICY_WIRING if name not in lines]
        self.assertEqual(
            missing,
            [],
            "resolve_policies no longer wires an axis - an axis resolved per slot "
            "is a band that changes halfway through a tune",
        )
        for axis in POLICY_WIRING[1:]:
            with self.subTest(axis=axis):
                self.assertLess(
                    lines["_resolve_parts"],
                    lines[axis],
                    f"{axis} is resolved before parts, which it reads",
                )


def _top_level_bindings(path: Path) -> Iterator[Tuple[str, int]]:
    """Every name the module binds at its top level, with the line that binds it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        names: List[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        for name in names:
            yield name, node.lineno


class TestTheSingleDefinition(unittest.TestCase):
    """No module binds one top-level name twice."""

    def test_no_module_binds_a_top_level_name_twice(self):
        """A duplicate binding is invisible: the later one wins and nothing fails.

        The duplicate this was written for was an *identical* copy of
        `_INTERVAL_CLASSES` and `INTERVAL_NAMES`, so even a diff of behaviour
        would have been empty. A split that copies a block instead of cutting it
        leaves the same trap in two modules at once, which is why this is checked
        over the whole tree rather than at the seam.
        """
        duplicates: List[str] = []
        for path in _library_modules():
            seen: Dict[str, int] = {}
            for name, lineno in _top_level_bindings(path):
                if name in seen:
                    duplicates.append(f"{_relative(path)}: {name} at {seen[name]} and {lineno}")
                else:
                    seen[name] = lineno
        self.assertEqual(
            duplicates,
            [],
            "a top-level name is bound twice - delete the binding that cannot win",
        )


if __name__ == "__main__":
    unittest.main()
