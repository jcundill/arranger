"""`jazz-arranger`: playable jazz guitar chord-melody from a chord progression.

This module is a **facade**. The engine is a package of modules with a strict
dependency order, and nothing above imports anything below it by accident:

    tuning -> fingers -> chords -> grips -> cost
                 |
              parts -> harmony/grid/texture
                              |
                             bass_place -> bass -> bass_merge -> options
                                         |
                            decisions -> melody_alone -> routes
                                                       |
                                              movement -> steps -> slots -> render -> cli

`fingers` is a second edge off `tuning`, and the diagram above omits it: it is the
left-hand fingering module of `docs/history/fingering.md`, and `bass_place` is the one engine
reader that reaches it - it calls `fingers.can_fret` for the four-fret budget of a merged
`bass_only` step, which is why the facade binds the module. `tests/test_fingers.py` holds
that caller set. It is in `test_package_dag.ORDER`, because a module missing from that
list is unconstrained by the layering.

`demo` holds `main()` - the built-in demonstration and the `head` hand-off - and sits
above `steps` and `render` rather than in the chain: it imports both, imports nothing
from `cli`, and is re-exported here as `arranger.main` so the console script and
`python -m arranger` name one function.

`import arranger` gives the same names it always did - `VoiceLeadingEngine`,
`Voicing`, `ArrangementStep`, `ChordParser`, the constants, and the renderers -
because everything public is re-exported here. The *code* moved; the spelling did
not, so the README, the tests and `headxml` are unaffected.

Two things are deliberately lazy, and both are load-bearing:

- the three whole-progression staff renderers, resolved through a module-level
  `__getattr__` (PEP 562) because `tabstaff` imports *this* package;
- the `head` front end, imported inside `demo.main()` so the demonstration costs
  nothing to a caller who only asked for it.

Adding a public name means adding it to `__all__` here, and
`tests/test_staff_rendering.py::TestTabstaffModuleBoundary` checks the list against
the module's real surface so the two cannot drift.

The facade re-exports the public surface only. Private helpers live in their
home modules and tests import them from there (`arranger.bass`, `arranger.grips`,
`arranger.render`, `arranger.texture`) rather than through `arranger`, so a
function that moves modules does not also have to move a re-export.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, List

from musthe import Note  # re-exported: `from arranger import Note` is used by tests

from . import (
    annotation,
    bass_merge,
    bass_place,
    bass_rules,
    cli,
    context,
    cost,
    decisions,
    fingers,
    grid,
    grip_place,
    harmonised_route,
    harmony,
    melody_alone,
    movement,
    options,
    parts,
    resolution,
    route_dispatch,
    routes,
    slot_plan,
    slots,
    step_prepare,
    texture,
)
from .bass import (
    bass_line_for,
)
from .bass_place import (
    BassNote,
    bass_cost,
)
from .bass_rules import (
    BASS_ROLE_ANCHOR,
    BASS_ROLE_APPROACH,
    BASS_ROLE_CONNECT,
    BASS_ROLE_ENCLOSURE,
    BASS_ROLE_FIFTH,
    BASS_ROLE_HOLD,
    BASS_ROLE_PEDAL,
    BASS_RULE_5TH,
    BASS_RULE_APPROACH,
    BASS_RULE_NEAREST,
    BASS_RULE_ROLES,
    BASS_RULE_ROOT,
    BASS_RULES,
    BASS_STRING_INDICES,
    BASS_STYLE_ANCHORS,
    BASS_STYLE_AUTO,
    BASS_STYLE_NONE,
    BASS_STYLE_WALK,
    bass_allowed,
    comping_capacity,
    parse_bass_style,
    thumb_capacity,
)
from .chords import (
    ChordParser,
    melody_degree_name,
    normalised_harmony,
    sounding_harmony,
)

# The selection rule's two value types: a caller ranking shapes itself needs the
# criteria object to hand `voicing_cost`, and the score it gets back.
from .cost import SelectionCriteria, VoicingScore

# The demonstration front end. Re-exported by name because `[project.scripts]` and
# `__main__.py` both point at `arranger:main`; binding it here also binds `arranger.demo`.
from .demo import main
from .grid import (
    ALL,
    GRID_ANCHORS,
    GRID_CHARLESTON,
    GRID_DEFAULT,
    GRID_EVERY_NOTE,
    GRID_FINAL_AND,
    GRID_FREDDIE,
    GRID_JOE_PASS,
    GRID_PART_PATTERNS,
    GRID_PATTERNS,
    GRID_STYLES,
    GRID_TIMELINE_PATTERNS,
    GRID_WALK,
    LAST,
    RHYTHM_EVERY_BEAT,
    RHYTHM_LAST,
    RHYTHM_MELODY,
    RHYTHM_NONE,
    SUB,
    TICKS_PER_BEAT,
    GridPattern,
    Rhythm,
    beat_offset,
    felt_beat,
    grid_allowed,
    grid_defers_to_melody,
    grid_positions,
    grid_resolutions,
    on_grid,
    parse_grid,
    parse_rhythm,
    resolve_grid,
    rhythm_beats,
)
from .grip_tables import (
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
    GRIP_STRING_SETS,
    SHELL_DEGREES,
    supported_string_sets,
)
from .grips import (
    BASS_DEGREES_6432,
    DUO_DEGREES,
    CompingRequest,
    get_comping_voicings,
    get_comping_voicings_for,
)
from .grouping import (
    COMMON_TIME,
    GROUPING_AUTO,
    GROUPING_SEPARATOR,
    ParsedGrouping,
    TimeSignature,
    default_grouping,
    format_grouping,
    group_offbeat,
    group_starts,
    grouping_allowed,
    parse_grouping,
    resolve_grouping,
)
from .harmony import (
    HARMONY_AUTO,
    HARMONY_AUTO_POLICIES,
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_LENGTH,
    HARMONY_SHELL_ROOT,
    HARMONY_STYLES,
    harmony_allowed,
    parse_harmony,
    resolve_harmony,
)
from .options import (
    BASS_NOTES,
    BASS_NOTES_ROOT,
    BASS_NOTES_ROOT_FIFTH,
    BASS_NOTES_WALK,
    CHORD_FILLS,
    CHORD_FILLS_COMP,
    CHORD_FILLS_HOLD,
    CHORD_FILLS_NONE,
    CHORD_NOTES,
    CHORD_NOTES_FULL,
    Request,
    ResolvedRequest,
    format_request,
    resolve_request,
)
from .parts import (
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    PART_NAMES,
    PARTS_AUTO,
    parse_parts,
    parts_has_melody_only,
    parts_have_bass,
    parts_have_chord,
    parts_have_melody,
    resolve_parts,
)
from .render import format_progression
from .slots import arrange_slots, parse_bar_range, unresolved_steps
from .steps import StepPreparation, VoiceLeadingEngine
from .texture import (
    TARGET_BEATS,
    TEXTURE_ARITY,
    TEXTURE_STYLES,
    comping_arity,
    derived_arity,
    families_for_arity,
    texture_arity,
    texture_palette,
)
from .tuning import (
    HIGH_FRET_LIMIT,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    NO_CHORD,
    PITCH_CLASS_NAMES,
    ROLE_FILL,
    ROLE_TARGET,
    SILENCE_GRID,
    SILENCE_NC_COMPING,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    SILENCE_TUNE_SILENT,
    STANDARD_TUNING,
    STRING_NAMES,
    ArrangementStep,
    GuitarFretboard,
    Voicing,
)

# Library version. The single source of truth: `pyproject.toml` reads it through
# [tool.setuptools.dynamic] rather than duplicating the number.
# 0.4.0 added the optional Weimar Jazz Database corpus integration (wjazzd.py).
# 0.5.0 added MusicXML export (tabxml.py), behind the optional `xml` extra.
# 0.7.0 gave the engine metric and textural awareness (TEXTURE_STYLES).
# 0.8.0 added 6-4-3-2 (grip `drop2_6432`) and a root-or-5th bass tie-break, so the
# lowest voice can be a root by decision rather than by string-set accident.
# 0.9.0 adds the walking-bass texture: a thumb line on the bass strings under a
# light left hand.
# 0.10.0 REMOVES the Weimar Jazz Database path: the `wjazzd` and `lead_sheet`
# modules, the `arranger corpus` subcommand, and the `--skeleton`/`--pick` flags.
# That is a breaking change to the public surface - hence the minor bump on a
# 0.x version, where the minor digit is the breaking one. `arrange_slots` moved
# into the package as `arranger.slots`, so the slot layer it always was is now
# importable from the engine. The MusicXML path is unchanged: byte-identical
# output on every committed fixture across sixteen flag combinations.
# 0.11.0 collapses one fact to one home: `ArrangementStep.grip` and
# `ArrangementStep.bass` become read-only derived views of the voicing's own
# fields, and the melody-only claim moves from the texture axis to the voices
# axis - `voices=soprano` is the melody and nothing else, and the `melody` and
# `melody_bass` textures are removed (a breaking change to the public surface,
# same rule as 0.10.0). Measured byte-identical against the old spellings on
# both committed heads and the engine's own fixture - see `docs/history/one-fact.md`.
__version__ = "0.12.0"


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
# finished. `tests/test_front_end_dag.py::TestTheRuntimeCycle` holds both halves.
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
    """Lists the lazily-exported renderers alongside the module's own names."""
    return sorted(__all__)


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
# adding a public name - test_dunder_all_matches_the_public_surface checks it.
#
# The engine submodules are listed too, and deliberately: `arranger.steps`,
# `arranger.grips` and `arranger.cost` are *public paths* - the places a change to the
# cost tuple or the grip tables belongs. Python binds a submodule as an attribute of its
# parent on import whether or not it is listed, so omitting them would not hide them; it
# would only make this list wrong, which is what
# `test_dunder_all_matches_the_public_surface` checks. The private names re-exported
# above are the deliberate exception: they are reachable and absent from this list on
# purpose.
__all__ = [
    "BASS_DEGREES_6432",
    "BASS_ROLE_ANCHOR",
    "BASS_ROLE_APPROACH",
    "BASS_RULE_5TH",
    "BASS_RULE_APPROACH",
    "BASS_RULE_NEAREST",
    "BASS_RULE_ROOT",
    "BASS_RULES",
    "BASS_RULE_ROLES",
    "BASS_STYLE_ANCHORS",
    "BASS_STYLE_AUTO",
    "BASS_STYLE_NONE",
    "BASS_STYLE_WALK",
    "BASS_ROLE_CONNECT",
    "BASS_ROLE_ENCLOSURE",
    "BASS_ROLE_FIFTH",
    "BASS_ROLE_HOLD",
    "BASS_ROLE_PEDAL",
    "BASS_STRING_INDICES",
    "BassNote",
    "DUO_DEGREES",
    "GRIP_MAX_SPAN",
    "COMMON_TIME",
    "ALL",
    "GRID_ANCHORS",
    "GRID_CHARLESTON",
    "GRID_DEFAULT",
    "GRID_EVERY_NOTE",
    "GRID_FINAL_AND",
    "GRID_FREDDIE",
    "GRID_JOE_PASS",
    "GRID_PATTERNS",
    "GRID_PART_PATTERNS",
    "GRID_STYLES",
    "GRID_TIMELINE_PATTERNS",
    "GRID_WALK",
    "BASS_NOTES",
    "BASS_NOTES_ROOT",
    "BASS_NOTES_ROOT_FIFTH",
    "BASS_NOTES_WALK",
    "CHORD_FILLS",
    "CHORD_FILLS_COMP",
    "CHORD_FILLS_HOLD",
    "CHORD_FILLS_NONE",
    "CHORD_NOTES",
    "CHORD_NOTES_FULL",
    "GridPattern",
    "LAST",
    "RHYTHM_EVERY_BEAT",
    "RHYTHM_LAST",
    "RHYTHM_MELODY",
    "RHYTHM_NONE",
    "Request",
    "ResolvedRequest",
    "Rhythm",
    "format_request",
    "resolve_request",
    "SUB",
    "TICKS_PER_BEAT",
    "beat_offset",
    "felt_beat",
    "grid_allowed",
    "grid_defers_to_melody",
    "grid_positions",
    "grid_resolutions",
    "on_grid",
    "parse_bar_range",
    "parse_grid",
    "parse_rhythm",
    "resolve_grid",
    "rhythm_beats",
    "HARMONY_AUTO",
    "HARMONY_AUTO_POLICIES",
    "HARMONY_LENGTH",
    "HARMONY_FULL",
    "HARMONY_GUIDE",
    "HARMONY_SHELL_ROOT",
    "HARMONY_STYLES",
    "harmony_allowed",
    "parse_harmony",
    "resolve_harmony",
    "GRIP_PREFERENCE",
    "GRIP_STRING_SETS",
    "GROUPING_AUTO",
    "GROUPING_SEPARATOR",
    "ParsedGrouping",
    "TimeSignature",
    "default_grouping",
    "format_grouping",
    "group_offbeat",
    "group_starts",
    "grouping_allowed",
    "parse_grouping",
    "resolve_grouping",
    "HIGH_FRET_LIMIT",
    "MELODY_STRING_CHOICES",
    "MELODY_STRING_CHOICES_FULL",
    "NECK_FRET_MAX",
    "NECK_FRET_MIN",
    "NO_CHORD",
    "PITCH_CLASS_NAMES",
    "ROLE_FILL",
    "ROLE_TARGET",
    "SHELL_DEGREES",
    "SILENCE_GRID",
    "SILENCE_NC_COMPING",
    "SILENCE_NO_SHAPE",
    "SILENCE_OUT_OF_REACH",
    "SILENCE_TUNE_SILENT",
    "STANDARD_TUNING",
    "STRING_NAMES",
    "TARGET_BEATS",
    "PART_BASS",
    "PART_CHORD",
    "PART_MELODY",
    "PART_NAMES",
    "PARTS_AUTO",
    "TEXTURE_ARITY",
    "TEXTURE_STYLES",
    "comping_arity",
    "derived_arity",
    "families_for_arity",
    "parse_parts",
    "parts_has_melody_only",
    "parts_have_bass",
    "parts_have_chord",
    "parts_have_melody",
    "resolve_parts",
    "texture_arity",
    "texture_palette",
    "ArrangementStep",
    "arrange_slots",
    "ChordParser",
    "melody_degree_name",
    "GuitarFretboard",
    "SelectionCriteria",
    "StepPreparation",
    "VoiceLeadingEngine",
    "Voicing",
    "VoicingScore",
    "annotation",
    "bass",
    "bass_rules",
    "bass_allowed",
    "bass_cost",
    "bass_line_for",
    "bass_merge",
    "bass_place",
    "parse_bass_style",
    "chords",
    "comping_capacity",
    "cli",
    "context",
    "cost",
    "decisions",
    "demo",
    "fingers",
    "format_progression",
    "format_gp5",
    "format_musicxml",
    "format_tab_html",
    "format_tab_staff",
    "CompingRequest",
    "get_comping_voicings",
    "get_comping_voicings_for",
    "grid",
    "grouping",
    "grip_place",
    "harmonised_route",
    "grip_tables",
    "grips",
    "harmony",
    "main",
    "melody_alone",
    "normalised_harmony",
    "movement",
    "options",
    "parts",
    "render",
    "resolution",
    "route_dispatch",
    "routes",
    "slot_plan",
    "step_prepare",
    "slots",
    "sounding_harmony",
    "steps",
    "supported_string_sets",
    "thumb_capacity",
    "texture",
    "tuning",
    "unresolved_steps",
    "write_musicxml",
    "write_tab_html",
    "write_gp5",
]
