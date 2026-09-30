"""The package is a DAG, and this is what holds it to that.

`arranger.py` was one 4290-line module. It is now eleven modules, and the
*structure* carries an invariant the comments used to carry in prose: a module may
import only the ones below it. That is worth enforcing mechanically precisely
because the maintainers here are LLM agents, which edit what they can find and
cannot infer that a decision documented in one place is duplicated in another - so
the layering would otherwise erode one "temporary" import at a time.

Three things are asserted:

1. **No cycles.** Every module's imports are within the declared order, so the
   graph is acyclic by construction rather than by inspection.
2. **No reaching back up.** Nothing imports the facade, which is what would make a
   module's real dependency invisible to the first check.
3. **The facade is complete.** Each public name still resolves off `arranger`, and
   is the *same object* as its home - the assertion the deleted module-level
   `__getattr__` made untestable.

`ALLOWED_EDGES` is the honest escape hatch: a list of named edges rather than a
blanket exemption, because the split could not be done without them and naming
each one is what makes a seventh visible.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Dict, Set

import arranger

PACKAGE = Path(arranger.__file__).parent

# The declared dependency order. A module may import itself and anything above it
# in this list, and nothing else. This is the whole rule, in one place.
ORDER = [
    "tuning",       # the instrument, and the Voicing / ArrangementStep value types
    "diagnostics",  # where the warnings go - a value, and nothing depends on it
    "chords",       # chord symbols and the non-chord-tone routing
    "grips",        # the grip tables, builders and candidate generators
    "cost",         # voicing_cost: which candidate is played
    "textures",     # metric roles: what a slot is for
    "bass",         # the walking-bass thumb line
    "options",      # the knobs, as one value
    "decisions",    # the decisions both step loops share
    "steps",        # the engine and the one step loop
    "render",       # per-step rendering
]

# The edges the split could not avoid, each with the reason it is sound. Anything
# added here has to justify itself in a comment - that is the point of the list.
ALLOWED_EDGES: Dict[str, Set[str]] = {
    # `Voicing.role` and `ArrangementStep.role` both default to `ROLE_TARGET`,
    # which `textures` owns by policy, so `tuning` defines the two labels and
    # `textures` re-exports them. One definition, two spellings.
    "textures": {"tuning"},
    # The walking bass reads the metric grid, and reads chord tones and the
    # extension table: it is built on top of both, not beside them.
    "bass": {"tuning", "chords", "textures"},
    # `decisions.select_step_voicing` is the corpus's slash-bass rule and needs the
    # engine's own cost function. `steps` imports `decisions`, so this edge has to
    # point down - which is why it imports `cost` and never `steps`.
    "decisions": {"tuning", "chords", "cost", "grips", "diagnostics"},
}

def _is_below(module: str, other: str) -> bool:
    """True when `other` sits *later* in ORDER than `module` - i.e. beneath it."""
    return ORDER.index(other) > ORDER.index(module)


def _imports_of(module: str) -> Set[str]:
    """The sibling modules `module` imports at runtime, from its AST.

    Read from the source rather than from `sys.modules`: a function-local import
    shows up here, which is exactly what should be caught, and it does not depend
    on what some other test happened to import first.
    """
    tree = ast.parse((PACKAGE / f"{module}.py").read_text())
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module
    }



class TestPackageDag(unittest.TestCase):
    """The layering, asserted rather than described."""

    def test_every_module_is_in_the_declared_order(self):
        """A new module must be placed in the order, not merely added.

        A module missing from ORDER is unconstrained by the rule below, so it would
        be free to import anything - which is how a package stops being a DAG one
        file at a time. This is the Makefile's hand-enumerated-inputs trap, applied
        to the layering.

        `__init__` and `__main__` are exempt and the exemption is narrow: the
        facade sits above the whole graph by definition, and `__main__` is three
        lines that import it. They are named here rather than filtered by a
        leading underscore, because a filter would also swallow a module whose name
        merely *started* with one.
        """
        not_layers = {"__init__", "__main__"}
        on_disk = {path.stem for path in PACKAGE.glob("*.py")} - not_layers
        self.assertEqual(
            on_disk - set(ORDER),
            set(),
            "a module exists that the declared order does not mention",
        )

    def test_no_module_imports_below_itself_in_the_order(self):
        """The whole rule: imports point up the list, never down it.

        Reported as one sorted list of offenders rather than a failure per module,
        because a cycle usually shows up in several places at once and the useful
        thing to see is the whole set.
        """
        position = {name: index for index, name in enumerate(ORDER)}
        offenders = []
        for module in ORDER:
            # `self` is always allowed; the extra edges are the named exceptions.
            allowed = ALLOWED_EDGES.get(module, set()) | {module}
            for imported in sorted(_imports_of(module)):
                if imported not in position:
                    offenders.append(f"{module} imports unknown module {imported}")
                elif imported not in allowed and _is_below(module, imported):
                    offenders.append(
                        f"{module} imports {imported}, which is below it in the order"
                    )
        self.assertEqual(offenders, [], "the package is no longer a DAG")

    def test_no_module_imports_the_facade(self):
        """Nothing inside the package may import `arranger` itself.

        This is the cycle Phase 5 exists to open. A module reaching back up through
        the facade would get a half-initialised package, and would hide its real
        dependency from the check above.
        """
        offenders = []
        for module in ORDER:
            tree = ast.parse((PACKAGE / f"{module}.py").read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module == "arranger":
                        offenders.append(f"{module} imports the facade")
                    if node.level == 2:
                        offenders.append(f"{module} reaches two levels up")
        self.assertEqual(offenders, [])

    def test_every_module_is_imported_by_something(self):
        """No module is dead weight the DAG still permits.

        Without this, a module quietly falling out of use would still pass every
        structural check above - the DAG constrains what a module may import, not
        whether anything imports it. `__init__` counts as an importer, since that is
        the whole point of a facade; the other three in `ORDER` are reached only
        from there, and a future engine module that is *not* re-exported would be
        the thing this catches.
        """
        importers: Dict[str, Set[str]] = {name: set() for name in ORDER}
        for module in ["__init__"] + ORDER:
            for imported in _imports_of(module):
                if imported in importers:
                    importers[imported].add(module)
        unimported = sorted(name for name, users in importers.items() if not users)
        self.assertEqual(
            unimported, [], "a module nothing imports - dead weight the DAG permits"
        )

    def test_the_facade_reexports_the_public_surface(self):
        """Every public name resolves off `arranger`, and is the *same object*.

        The identity half is the assertion the old module-level `__getattr__` made
        untestable, and it is what a caller relying on `from arranger import X`
        actually depends on: not that the name resolves, but that it is the very
        object the home module defines rather than a copy of it.
        """
        for name in arranger.__all__:
            self.assertTrue(hasattr(arranger, name), f"{name} in __all__ but missing")

        for public_name, home, attribute in [
            ("VoiceLeadingEngine", "steps", "VoiceLeadingEngine"),
            ("StepPreparation", "steps", "StepPreparation"),
            ("ChordParser", "chords", "ChordParser"),
            ("Voicing", "tuning", "Voicing"),
            ("ArrangementStep", "tuning", "ArrangementStep"),
            ("GuitarFretboard", "tuning", "GuitarFretboard"),
            ("bass_cost", "bass", "bass_cost"),
            ("format_progression", "render", "format_progression"),
            ("supported_string_sets", "grips", "supported_string_sets"),
            ("Diagnostics", "diagnostics", "Diagnostics"),
        ]:
            module = __import__(f"arranger.{home}", fromlist=[attribute])
            self.assertIs(
                getattr(arranger, public_name),
                getattr(module, attribute),
                f"arranger.{public_name} is not arranger.{home}.{attribute}",
            )


if __name__ == "__main__":
    unittest.main()
