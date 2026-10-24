"""`jazz-arranger`: playable jazz guitar chord-melody from a chord progression.

This module is a **facade**, and it is deliberately narrow: it re-exports the API a
caller names *to arrange something and to read the result back* - the engine, the
options and request values, the metre, the chord and voicing types, the renderers, and
`main`.

**Everything else is reached through the module that owns it.** The engine's vocabulary
is spelled where it is implemented, so a caller writes
`arranger.options.CHORD_NOTES_FULL`, `arranger.grid.RHYTHM_NONE` or
`arranger.tuning.STANDARD_TUNING` rather than importing a constant from the package
root.

Every engine submodule is bound by the `from . import (...)` below, so `arranger.grips`
and `arranger.cost` resolve - the paths a change to the cost tuple or the grip tables
belongs - but a submodule is a *path* rather than a name this facade defines, which is
why none of them is in `__all__`. `fingers` is bound for the same reason although only
`bass_place` and `bass_merge` read it (`fingers.can_fret`, the four-fret budget and the
hand's reach), which `tests/test_fingers.py` holds. The layering that makes those paths
safe to depend on is
`ORDER` in `tests/meta_package_dag.py`, drawn in
[docs/dependency-dag.md](../docs/dependency-dag.md).

`ArrangeOptions` is re-exported because it carries the knobs that are not a question about
the music: `arrange_progression` and `arrange_xml_head` take `request=` and the input facts,
and the implementation axes are derived from the request rather than spelled. See
`options.py`.

`demo` holds `main()` - the built-in demonstration and the `head` hand-off - and is
re-exported as `arranger.main` so the console script and `python -m arranger` name one
function.

Two things are deliberately lazy, and both are load-bearing:

- the whole-progression staff renderers, resolved through a module-level `__getattr__`
  (PEP 562) because `tabstaff` imports *this* package;
- the `head` front end, imported inside `demo.main()` so the demonstration costs nothing
  to a caller who only asked for it.

Adding a public name means adding it to `__all__` here, and
`tests/test_staff_rendering.py::TestTabstaffModuleBoundary` checks the list against the
module's real surface so the two cannot drift: a public name this module binds that is
neither listed nor a submodule is a name it defines by accident.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import TYPE_CHECKING, Any, List

from musthe import Note  # re-exported: `from arranger import Note` is used by tests

# Every engine submodule, so `arranger.<module>` resolves without the caller importing it
# first. These are paths rather than public names, and `__all__` does not list them.
from . import (
    annotation,
    bass,
    bass_merge,
    bass_place,
    bass_rules,
    chords,
    cli,
    comp_line,
    context,
    cost,
    decisions,
    demo,
    fingers,
    grid,
    grip_place,
    grip_tables,
    grips,
    grouping,
    harmonised_route,
    melody_alone,
    movement,
    options,
    parts,
    render,
    resolution,
    route_dispatch,
    routes,
    slot_plan,
    slots,
    step_history,
    step_prepare,
    step_types,
    steps,
    text_layout,
    texture,
    tuning,
)

# The public surface: the types a caller builds a request with and reads a result back
# from, the functions that answer a question about one, and the renderers.
from .bass import bass_line_for
from .bass_place import BassNote, bass_cost
from .bass_rules import bass_allowed, comping_capacity, parse_bass_style, thumb_capacity
from .chords import (
    ChordParser,
    melody_degree_name,
    normalised_harmony,
    sounding_harmony,
)
from .cost import SelectionCriteria, VoicingScore
from .demo import main
from .grid import (
    Rhythm,
    beat_offset,
    felt_beat,
    grid_resolutions,
    parse_rhythm,
    rhythm_beats,
)
from .grip_tables import supported_string_sets
from .grips import CompingRequest, get_comping_voicings, get_comping_voicings_for
from .grouping import (
    ParsedGrouping,
    TimeSignature,
    default_grouping,
    format_grouping,
    group_starts,
    grouping_allowed,
    parse_grouping,
    resolve_grouping,
)
from .options import (
    ArrangeOptions,
    Request,
    ResolvedRequest,
    format_request,
    resolve_request,
)
from .parts import (
    parts_has_melody_only,
    parts_have_bass,
    parts_have_chord,
    parts_have_melody,
)
from .render import format_progression
from .slots import arrange_slots, parse_bar_range, unresolved_steps
from .step_types import ArrangementStep, Voicing
from .steps import StepPreparation, VoiceLeadingEngine
from .texture import (
    comping_arity,
    derived_arity,
    texture_arity,
    texture_palette,
)
from .tuning import GuitarFretboard

# Library version. The single source of truth: `pyproject.toml` reads it through
# [tool.setuptools.dynamic] rather than duplicating the number.
__version__ = "0.14.0"


# The whole-progression staff renderers live in `tabstaff`, which imports
# `arranger.tuning` - and importing a submodule runs this module first. They are
# exposed here through a module-level __getattr__ rather than a top-level
# `from tabstaff import ...`, so that `import arranger` does not load the four
# rendering modules (`tabstaff`, `tabxml`, `tabgp`, `tabscore`) for a caller who
# only wants the engine. PEP 562 resolves each name on first access instead, so
# `from arranger import format_tab_html` keeps working - the spelling the README
# and the tests use - without a lazy import at every call site. `demo.main()`'s
# `headxml` import is the same discipline and not the same reason: `headxml` names
# this module's public surface, so it *cannot* be imported until this module has
# finished. `tests/meta_front_end_dag.py::TestTheRuntimeCycle` holds both halves.
_TABSTAFF_EXPORTS = {
    # name -> the module it lives in. The MusicXML and Guitar Pro renderers live in
    # `tabxml` and `tabgp`, which `tabstaff` re-exports, so resolving them through
    # `tabstaff` as well keeps one spelling for the whole rendering surface.
    "format_tab_staff": "tabstaff",
    "format_tab_html": "tabstaff",
    "write_tab_html": "tabstaff",
    "format_musicxml": "tabstaff",
    "write_musicxml": "tabstaff",
    "format_gp5": "tabstaff",
    "write_gp5": "tabstaff",
}


def __getattr__(name: str) -> Any:
    """Resolves the renderer modules on first access. See _TABSTAFF_EXPORTS."""
    if name in _TABSTAFF_EXPORTS:
        return getattr(importlib.import_module(_TABSTAFF_EXPORTS[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    """Lists the module's own names beside the submodules it binds.

    A submodule is not a name this facade defines, so it is not in `__all__` - but it
    *is* bound, and `arranger.grips` works. Leaving it out of `dir()` would hide a
    path that resolves.
    """
    bound = {
        name for name, value in globals().items()
        if isinstance(value, ModuleType) and not name.startswith("_")
    }
    return sorted(set(__all__) | bound)


# The renderers are re-exported lazily (see `__getattr__`), which a static checker
# cannot follow. A TYPE_CHECKING import gives it the real declarations, so
# `from arranger import format_tab_html` type-checks and IDEs resolve it, while at
# runtime the names still come from `__getattr__` and never trigger an import cycle.
if TYPE_CHECKING:
    from tabstaff import (
        format_gp5,
        format_musicxml,
        format_tab_html,
        format_tab_staff,
        write_gp5,
        write_musicxml,
        write_tab_html,
    )


# Star-import support. The lazy `__getattr__` above hides the tabstaff renderers from
# `from arranger import *`, so they are listed here explicitly. Keep this in step when
# adding a public name - `test_dunder_all_matches_the_public_surface` checks it in both
# directions, and it treats a bound *submodule* as a path rather than as a name this
# facade defines.
__all__ = [
    "ArrangeOptions",
    "ArrangementStep",
    "BassNote",
    "ChordParser",
    "CompingRequest",
    "GuitarFretboard",
    "Note",
    "ParsedGrouping",
    "Request",
    "ResolvedRequest",
    "Rhythm",
    "SelectionCriteria",
    "StepPreparation",
    "TimeSignature",
    "VoiceLeadingEngine",
    "Voicing",
    "VoicingScore",
    "arrange_slots",
    "bass_allowed",
    "bass_cost",
    "bass_line_for",
    "beat_offset",
    "comping_arity",
    "comping_capacity",
    "default_grouping",
    "derived_arity",
    "felt_beat",
    "format_gp5",
    "format_grouping",
    "format_musicxml",
    "format_progression",
    "format_request",
    "format_tab_html",
    "format_tab_staff",
    "get_comping_voicings",
    "get_comping_voicings_for",
    "grid_resolutions",
    "group_starts",
    "grouping_allowed",
    "main",
    "melody_degree_name",
    "normalised_harmony",
    "parse_bass_style",
    "parse_bar_range",
    "parse_grouping",
    "parse_rhythm",
    "parts_has_melody_only",
    "parts_have_bass",
    "parts_have_chord",
    "parts_have_melody",
    "resolve_grouping",
    "resolve_request",
    "rhythm_beats",
    "sounding_harmony",
    "supported_string_sets",
    "texture_arity",
    "texture_palette",
    "thumb_capacity",
    "unresolved_steps",
    "write_gp5",
    "write_musicxml",
    "write_tab_html",
]
