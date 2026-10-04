"""`jazz-arranger`: playable jazz guitar chord-melody from a chord progression.

This module is a **facade**. The engine is a package of eight modules with a
strict dependency order, and nothing above imports anything below it by accident:

    tuning -> chords -> grips -> cost
                 |         |        |
              textures   (grips)   bass
                 |                    |
              options ---------------> |
                 |                    |
              steps -> render -> (this module)

`import arranger` gives the same names it always did - `VoiceLeadingEngine`,
`Voicing`, `ArrangementStep`, `ChordParser`, the constants, and the renderers -
because everything public is re-exported here. The *code* moved; the spelling did
not, so the README, the tests, `wjazzd` and `headxml` are unaffected.

Two things are deliberately still lazy, and Phase 6 removes both:

- the three whole-progression staff renderers, resolved through a module-level
  `__getattr__` (PEP 562) because `tabstaff` imports *this* package;
- the `corpus` and `head` subcommand front ends, imported inside `main()`.

Adding a public name means adding it to `__all__` here, and
`tests/test_tab_rendering.py::TestTabstaffModuleBoundary` checks the list against
the module's real surface so the two cannot drift.

**Seven private names are re-exported too** - `_bass_harmony`, `_place_bass`,
`_walking_bass_line`, `_interval_offsets`, `_metric_weight`, `_roles_for_slot` and
`_step_annotation`. They are not API and are deliberately absent from `__all__`,
but the tests reach into them to state a rule directly rather than infer it from
the engine's output ("the walk's pitch-class set is exactly the chord's tones plus
its extensions", "a fill is chosen by the role rule"). Moving the code would
otherwise have forced those tests to reimplement the rule they are checking, which
is the copy-paste failure Phase 1 removed. They are listed here so the cost of
moving a function - "also re-export it" - is visible rather than discovered.
"""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING, Any, List

from musthe import Note  # re-exported: `from arranger import Note` is used by tests

from . import cli, cost, decisions, options
from .bass import (
    BASS_ANCHORS,
    BASS_AUTO,
    BASS_NONE,
    BASS_POLICY_ROLES,
    BASS_ROLE_ANCHOR,
    BASS_ROLE_APPROACH,
    BASS_ROLE_CONNECT,
    BASS_ROLE_ENCLOSURE,
    BASS_ROLE_HOLD,
    BASS_STRING_INDICES,
    BASS_STYLES,
    BASS_WALK,
    BassNote,
    _bass_harmony,
    _place_bass,
    _walking_bass_line,
    bass_allowed,
    bass_cost,
    bass_line_for,
    thumb_capacity,
)
from .chords import ChordParser, normalised_harmony, sounding_harmony
from .diagnostics import Diagnostics, default_diagnostics
from .grips import (
    BASS_DEGREES_6432,
    DUO_DEGREES,
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
    GRIP_STRING_SETS,
    SHELL_DEGREES,
    _interval_offsets,
    get_comping_voicings,
    supported_string_sets,
)
from .render import _print_step, _step_annotation, format_progression
from .steps import StepPreparation, VoiceLeadingEngine
from .textures import (
    HARMONY_AUTO,
    HARMONY_BUILT,
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_POLICIES,
    HARMONY_ROOT,
    HARMONY_SHELL_ROOT,
    HARMONY_STYLES,
    MELODY_ALTO,
    MELODY_AUTO,
    MELODY_BASS,
    MELODY_ONLY_TEXTURES,
    MELODY_POLICIES,
    MELODY_SOPRANO,
    MELODY_TENOR,
    ROLE_FILL,
    ROLE_TARGET,
    TARGET_BEATS,
    TEXTURE_GRIPS,
    TEXTURE_STYLES,
    THUMB_TEXTURES,
    VOICE_NAMES,
    VOICES_ALL,
    VOICES_NONE,
    _metric_weight,
    _roles_for_slot,
    harmony_allowed,
    melody_allowed,
    parse_harmony,
    parse_voices,
    resolve_harmony,
    resolve_voices,
    voices_have_soprano,
)
from .tuning import (
    _MUTED_CELL,  # re-exported: `tabstaff` imports it from here
    HIGH_FRET_LIMIT,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    NO_CHORD,
    PITCH_CLASS_NAMES,
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
__version__ = "0.9.0"


# The whole-progression staff renderers live in `tabstaff`, which imports this
# module. They are exposed here through a module-level __getattr__ rather than a
# top-level `from tabstaff import ...`, because that would be an import cycle:
# importing `tabstaff` first would re-enter this half-initialised module and fail to
# find the names. PEP 562 resolves each name on first access instead, so
# `from arranger import format_tab_html` keeps working - the spelling the README,
# the tests and wjazzd all use - without a lazy import at every call site. This is
# the same lazy-import discipline main() uses for wjazzd, for the same reason.
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
    Entry point: the built-in demonstration, or a subcommand.

    With no arguments this prints the built-in demonstration arrangements.

    With `corpus` as the first argument it hands over to `wjazzd.corpus_cli`, the
    Weimar Jazz Database front end, which is where the transcribed-head feature
    lives. The import is deliberately lazy and inside the branch: the database
    module is optional glue over a 42 MB file that most users do not have, and
    `import arranger` must never depend on it.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "corpus":
        from wjazzd import corpus_cli

        raise SystemExit(corpus_cli(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "head":
        # The MusicXML importer, imported here for the same reason as the corpus
        # front end above: both are optional entry points, and neither may be a
        # cost - or a dependency - to somebody who only wants the library.
        from headxml import head_cli

        raise SystemExit(head_cli(sys.argv[2:]))

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

    # Example 3: The same low melody arranged two ways. Pinning grips=("drop2",) with
    # the two traditional soprano strings reproduces the library's original
    # four-string-only output, which is what a caller wants when they need a known
    # arrangement rather than the best one.
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
    for label, kwargs in (
        ("every grip, frets 2-13", {}),
        ("drop-2 only, high E and B strings", {"top_strings": (5, 4), "grips": ("drop2",)}),
    ):
        print(f"\n--- LOW-REGISTER CADENCE, {label} (Dm7 -> G7 -> Cmaj7) ---")
        for step in engine.arrange_progression(low_progression, **kwargs):
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
    # (Bdim7), by holding the inner voices under the passing tone, or not at all
    # (the historical quality-only fallback).
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
    # compact form - one line per chord. (It also rendered a six-line block per
    # chord behind `vertical=True`, reachable from the CLI as --vertical; both
    # were removed, because the staff below is what a player actually reads.)
    print("\n--- TAB RENDERING: format_progression(), one line per chord ---")
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


# used to export every public name; the lazy __getattr__ above hides the tabstaff
# renderers from that, so they are listed here explicitly. Keep it in step when
# adding a public name - test_dunder_all_matches_the_public_surface checks that.
# Star-import support. This module never had an __all__, so `from arranger import *`
# used to export every public name; the lazy __getattr__ above hides the tabstaff
# renderers from that, so they are listed here explicitly.
#
# The engine submodules are listed too, and deliberately. Phase 5 made this a
# package, and `arranger.steps`, `arranger.grips` and `arranger.cost` are *public
# paths* - the places a change to the cost tuple or the grip tables belongs. Python
# binds a submodule as an attribute of its parent on import whether or not it is
# listed, so omitting them would not hide them; it would only make this list wrong,
# which is what `test_dunder_all_matches_the_public_surface` checks. The private
# names re-exported above are the deliberate exception: they are reachable and
# absent from this list on purpose.
__all__ = [
    "BASS_DEGREES_6432",
    "BASS_ROLE_ANCHOR",
    "BASS_ROLE_APPROACH",
    "BASS_ANCHORS",
    "BASS_AUTO",
    "BASS_NONE",
    "BASS_POLICY_ROLES",
    "BASS_ROLE_CONNECT",
    "BASS_ROLE_ENCLOSURE",
    "BASS_ROLE_HOLD",
    "BASS_STYLES",
    "BASS_STRING_INDICES",
    "BASS_WALK",
    "BassNote",
    "DUO_DEGREES",
    "GRIP_MAX_SPAN",
    "HARMONY_AUTO",
    "HARMONY_BUILT",
    "HARMONY_FULL",
    "HARMONY_GUIDE",
    "HARMONY_POLICIES",
    "HARMONY_ROOT",
    "HARMONY_SHELL_ROOT",
    "HARMONY_STYLES",
    "MELODY_ALTO",
    "MELODY_AUTO",
    "MELODY_BASS",
    "MELODY_ONLY_TEXTURES",
    "MELODY_POLICIES",
    "MELODY_SOPRANO",
    "MELODY_TENOR",
    "VOICES_ALL",
    "VOICES_NONE",
    "VOICE_NAMES",
    "parse_voices",
    "resolve_voices",
    "harmony_allowed",
    "parse_harmony",
    "resolve_harmony",
    "voices_have_soprano",
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
    "STANDARD_TUNING",
    "STRING_NAMES",
    "TARGET_BEATS",
    "TEXTURE_GRIPS",
    "TEXTURE_STYLES",
    "THUMB_TEXTURES",
    "ArrangementStep",
    "ChordParser",
    "Diagnostics",
    "GuitarFretboard",
    "StepPreparation",
    "VoiceLeadingEngine",
    "Voicing",
    "bass",
    "bass_allowed",
    "bass_cost",
    "bass_line_for",
    "chords",
    "cli",
    "cost",
    "decisions",
    "default_diagnostics",
    "diagnostics",
    "format_progression",
    "format_gp5",
    "format_musicxml",
    "format_tab_html",
    "format_tab_staff",
    "get_comping_voicings",
    "grips",
    "main",
    "normalised_harmony",
    "melody_allowed",
    "options",
    "render",
    "sounding_harmony",
    "steps",
    "supported_string_sets",
    "thumb_capacity",
    "textures",
    "tuning",
    "write_musicxml",
    "write_tab_html",
    "write_gp5",
]
