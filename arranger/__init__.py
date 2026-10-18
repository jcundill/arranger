"""`jazz-arranger`: playable jazz guitar chord-melody from a chord progression.

This module is a **facade**. The engine is a package of modules with a strict
dependency order, and nothing above imports anything below it by accident:

    tuning -> fingers -> chords -> grips -> cost
                 |
              parts -> harmony/grid/texture
                              |
                             bass -> bass_merge -> options
                                         |
                            decisions -> melody_alone -> routes
                                                       |
                                              movement -> steps -> slots -> render -> cli

`fingers` is a second edge off `tuning`, and the diagram above omits it: it is the
left-hand fingering module of `docs/history/fingering.md`, and `bass` is the one engine reader
that reaches it - it calls `fingers.can_fret` for the four-fret budget of a merged
`bass_only` step, which is why the facade binds the module. `tests/test_fingers.py` holds
that caller set. It is in `test_package_dag.ORDER`, because a module missing from that
list is unconstrained by the layering.

`import arranger` gives the same names it always did - `VoiceLeadingEngine`,
`Voicing`, `ArrangementStep`, `ChordParser`, the constants, and the renderers -
because everything public is re-exported here. The *code* moved; the spelling did
not, so the README, the tests and `headxml` are unaffected.

Two things are deliberately lazy, and both are load-bearing:

- the three whole-progression staff renderers, resolved through a module-level
  `__getattr__` (PEP 562) because `tabstaff` imports *this* package;
- the `corpus` and `head` subcommand front ends, imported inside `main()`.

Adding a public name means adding it to `__all__` here, and
`tests/test_tab_rendering.py::TestTabstaffModuleBoundary` checks the list against
the module's real surface so the two cannot drift.

The facade re-exports the public surface only. Private helpers live in their
home modules and tests import them from there (`arranger.bass`, `arranger.grips`,
`arranger.render`, `arranger.texture`) rather than through `arranger`, so a
function that moves modules does not also have to move a re-export.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING, Any, List

from musthe import Note  # re-exported: `from arranger import Note` is used by tests

from . import (
    annotation,
    bass_merge,
    bass_rules,
    cli,
    context,
    cost,
    decisions,
    fingers,
    grid,
    grip_place,
    harmony,
    melody_alone,
    movement,
    options,
    parts,
    resolution,
    routes,
    slot_plan,
    slots,
    texture,
)
from .bass import (
    BassNote,
    bass_cost,
    bass_line_for,
)
from .bass_rules import (
    BASS_ROLE_ANCHOR,
    BASS_ROLE_APPROACH,
    BASS_ROLE_CONNECT,
    BASS_ROLE_ENCLOSURE,
    BASS_ROLE_HOLD,
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
    SUB,
    TICKS_PER_BEAT,
    GridPattern,
    beat_offset,
    grid_allowed,
    grid_defers_to_melody,
    grid_positions,
    grid_resolutions,
    on_grid,
    parse_grid,
    resolve_grid,
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

# `print_step` is the demo's one-line writer, imported under a private alias so
# the facade does not publish it as API: `main()` is its only user here.
from .render import format_progression
from .render import print_step as _print_step
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


# The whole-progression staff renderers live in `tabstaff`, which imports this
# module. They are exposed here through a module-level __getattr__ rather than a
# top-level `from tabstaff import ...`, because that would be an import cycle:
# importing `tabstaff` first would re-enter this half-initialised module and fail to
# find the names. PEP 562 resolves each name on first access instead, so
# `from arranger import format_tab_html` keeps working - the spelling the README
# and the tests use - without a lazy import at every call site. This is
# the same lazy-import discipline main() uses for the head importer, for the same reason.
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


def main() -> None:
    """
    Entry point: the built-in demonstration, or the `head` subcommand.

    With no arguments this prints the built-in demonstration arrangements.

    With `head` as the first argument it hands over to `headxml.head_cli`, the
    MusicXML front end. The import is deliberately lazy and inside the branch, so
    `import arranger` does not pull in the importer - nor, through it, the renderers
    it uses - for somebody who only wants the library.

    **Anything else that looks like a subcommand is a usage error, not the demo.**
    Falling through to the demo for an unrecognised command would answer a request for
    a head with three arrangements and exit 0 - the exit code would say it worked.

    The test is `argv[1]` being a bare word, so an option (`--texture targets`) still
    reaches the demo rather than being rejected, and `--help` is handled by the
    caller's own flag handling below.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "head":
        from headxml import head_cli

        raise SystemExit(head_cli(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1].isalpha() and not sys.argv[1].startswith("-"):
        # A bare leading word that is not `head` was a subcommand, or a typo for
        # one. Say so rather than arranging a demonstration nobody asked for.
        print(
            f"Unknown command {sys.argv[1]!r}. The only subcommand is "
            f"'head':\n"
            f"  python -m arranger head FILE.musicxml [options]\n"
            f"With no arguments, this prints the built-in demonstrations.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    engine = VoiceLeadingEngine()

    # Example 1: Minor ii - V - i cadence in C Minor (Dm7b5 -> G7b9 -> Cm7)
    # The staple progression for minor jazz standards (Autumn Leaves, Alone Together, Blue Bossa, etc.)
    minor_progression = [
        ("F5", "m7b5", "Dm7b5"),
        ("F5", "7b9", "G7b9"),
        ("Eb5", "m7", "Cm7")
    ]
    result_minor = engine.arrange_progression(minor_progression)

    print("\n--- MINOR ii - V - i ARRANGEMENT (Dm7b5 -> G7b9 -> Cm7) ---")
    for step in result_minor:
        _print_step(step)

    # Example 2: Major ii - V - I in C Major over a melody on the top string (D5 -> B4 -> C5)
    major_progression = [
        ("D5", "m7", "Dm7"),
        ("B4", "7", "G7"),
        ("C5", "maj7", "Cmaj7")
    ]
    result_major = engine.arrange_progression(major_progression)

    print("\n--- MAJOR ii - V - I ARRANGEMENT (Dm7 -> G7 -> Cmaj7) ---")
    for step in result_major:
        _print_step(step)

    # Example 3: The same low melody, played where the neck allows it. Every grip
    # family is offered, and the last chord drops to a three-note shell rather than
    # reaching back up for a four-string shape.
    #
    # The difference is the Cmaj7. D4 and C4 sit at the very bottom of the B string's
    # range, where the original engine put the whole phrase up at frets 2-3 on strings
    # A-D-G-B. With the G string available the last chord can drop to a three-note
    # shell on 5-4-3, an octave lower, and still sound its 3rd and 7th.
    low_progression = [
        ("D4", "m7", "Dm7"),
        ("D4", "7", "G7"),
        ("C4", "maj7", "Cmaj7")
    ]
    print("\n--- LOW-REGISTER CADENCE, frets 2-13 (Dm7 -> G7 -> Cmaj7) ---")
    for step in engine.arrange_progression(low_progression):
        _print_step(step)

    # Example 4: Texture. The same four melody notes under Fmaj7, arranged twice.
    # Without timings every slot is a principal note and all four are full chords.
    # Given the rhythm, the `targets` texture states the harmony on beats 1 and 3 and
    # fills the notes between with a shell or an interval - the arranging guide's
    # method, and the difference between an arrangement and a chord list.
    texture_progression = [
        ("C5", "maj7", "Fmaj7"),
        ("E5", "maj7", "Fmaj7"),
        ("A4", "maj7", "Fmaj7"),
        ("F4", "maj7", "Fmaj7"),
    ]
    texture_timings = [(0, 1.0, None), (0, 1.5, None), (0, 2.0, None), (0, 3.0, None)]

    for label, kwargs in (
        ("no timing - every note is a chord", {}),
        (
            "texture=targets - chords on beats 1 and 3, fills between",
            {"timings": texture_timings, "texture": "targets"},
        ),
    ):
        print(f"\n--- TEXTURE: one bar of Fmaj7, {label} ---")
        for step in engine.arrange_progression(texture_progression, **kwargs):
            _print_step(step)

    # Example 5: Non-chord melody tones. Bar 2 of "All of Me" moves C5 -> D5 -> C5
    # over Cmaj7; D5 is the 9th, not a chord tone, so each strategy harmonises it
    # differently: as an extension (Cmaj9), as a Barry Harris dim7 substitution
    # (Bdim7), or by holding the inner voices under the passing tone.
    all_of_me = [
        ("C5", "maj7", "Cmaj7"),
        ("D5", "maj7", "Cmaj7"),
        ("C5", "maj7", "Cmaj7"),
    ]

    print("\n--- NON-CHORD MELODY TONES: 'All of Me' bar 2 (C5 -> D5 -> C5 over Cmaj7) ---")
    for strategy in VoiceLeadingEngine.NON_CHORD_TONE_STRATEGIES:
        print(f"  strategy: {strategy}")
        for step in engine.arrange_progression(all_of_me, non_chord_tone=strategy):
            _print_step(step)

    # Example 8: Tab rendering. format_progression() returns the tab as a string
    # and prints nothing itself, so callers choose what to do with it. It is the
    # compact form - one block per chord, whose explanation wraps onto the lines
    # below when it is too long for one. (It also rendered a six-line block per
    # chord behind `vertical=True`, reachable from the CLI as --vertical; both
    # were removed, because the staff below is what a player actually reads.)
    print("\n--- TAB RENDERING: format_progression(), one block per chord ---")
    print(format_progression(result_major))

    # Example 8: The whole progression on one six-line staff. format_tab_staff()
    # is the standard reading order - high E on top, chord names above, barlines
    # between bars - so it is what a player would actually read off the page. With
    # `show_timing` (the default) it also states the metre and the note value of
    # every column; these steps carry no timing, so there is no rhythm to state and
    # only the metre is drawn. A transcribed head (see `arranger corpus --tab
    # staff`) has a written rhythm and gets the note values too.
    # The renderer is reached through the module's lazy export rather than imported
    # at the top, which is what keeps tabstaff importable on its own; see __getattr__.
    import tabstaff

    print("\n--- TAB RENDERING: format_tab_staff(), one progression on a six-line staff ---")
    print(tabstaff.format_tab_staff(result_major, show_melody=True))

    # Example 8: The same cadence with the timing the corpus loader supplies, so the
    # chords sit on their own beats, a barline falls between the two bars, and the
    # note-value row has something to say.
    timed_major = engine.arrange_progression(major_progression)
    for index, step in enumerate(timed_major):
        step.bar, step.beat, step.duration = index, 1.0, 1.0
    print("\n--- TAB RENDERING: format_tab_staff() on a timed progression, barline per bar ---")
    print(tabstaff.format_tab_staff(timed_major, show_melody=True, measures_per_line=1))


if __name__ == "__main__":
    main()



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
    "BASS_ROLE_HOLD",
    "BASS_STRING_INDICES",
    "BassNote",
    "DUO_DEGREES",
    "GRIP_MAX_SPAN",
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
    "GridPattern",
    "LAST",
    "SUB",
    "TICKS_PER_BEAT",
    "beat_offset",
    "grid_allowed",
    "grid_defers_to_melody",
    "grid_positions",
    "grid_resolutions",
    "on_grid",
    "parse_bar_range",
    "parse_grid",
    "resolve_grid",
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
    "StepPreparation",
    "VoiceLeadingEngine",
    "Voicing",
    "annotation",
    "bass",
    "bass_rules",
    "bass_allowed",
    "bass_cost",
    "bass_line_for",
    "bass_merge",
    "parse_bass_style",
    "chords",
    "comping_capacity",
    "cli",
    "context",
    "cost",
    "decisions",
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
    "grip_place",
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
    "routes",
    "slot_plan",
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
