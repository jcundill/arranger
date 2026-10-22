"""The built-in demonstration, and the `head` hand-off: `main()`.

This is the package's **front end**, the one place allowed to print - the engine returns
values and every renderer returns a string. It sits above `steps` and `render` in the
dependency order, and its imports of the importer and the staff renderers are
deliberately function-local, for two different reasons: `import arranger` should not pay
for either, and `headxml` names the facade's public surface, so it cannot be imported
until the facade has finished - which is what this module is.

`arranger.main` re-exports it, so `python -m arranger`, the `jazz-arranger` console
script and `tests/test_cli.py` all reach one function rather than three copies.
"""

from __future__ import annotations

import sys

# `print_step` is the demo's one-line writer, imported under a private alias so this
# module does not publish it as API: `main()` is its only user.
from .render import format_progression
from .render import print_step as _print_step
from .steps import VoiceLeadingEngine


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

    The test is `argv[1]` being a bare word, so an option (`--chord-on 1and`) still
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
