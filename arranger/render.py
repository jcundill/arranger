"""Per-step rendering: one compact line per chord.

`format_progression` is the compact renderer, and it is **pure** - it returns a
string and prints nothing, so the caller stays in control of the output. The
whole-progression staff renderers are a different shape of output and live in
`tabstaff`.

It used to render a six-line vertical block per step too, behind a `vertical`
argument that the `--vertical` CLI flag existed only to reach. Both were removed:
the staff in `tabstaff` is what a player reads, and this is now the one-line
summary alone. The vertical form survives on a single voicing -
`Voicing.tab_block()` - which is not the same surface.

`_step_annotation` is shared by `format_progression` and the demonstration, so the
two renderings cannot drift apart. A step can be several things at once - a
non-chord tone, a repeated melody, a partial shell, a thumb note - and the
precedence between them is the whole content of that function.

The tab-cell primitives (`_MUTED_CELL`, `_cells_from_frets`) are **not** defined
here: `Voicing.tab_block` calls them and `Voicing` sits below this module, so they
live in `tuning` and are imported from there. `_STAFF_CELL_WIDTH` was the second of
two identical definitions of one constant - `tabstaff` had the other - and is
imported for the same reason. `_tab_block_from_cells` is still in `tuning` for
`Voicing.tab_block`, but this module no longer renders a block, so it no longer
imports it.
"""

from __future__ import annotations

from typing import Dict, List

from .grips import _INTERVAL_NAMES
from .tuning import (
    _BLANK_CELL,
    _MUTED_CELL,
    _STAFF_CELL_WIDTH,
    ArrangementStep,
    _cells_from_frets,
    _note_name,
)

__all__ = ["_MUTED_CELL", "_STAFF_CELL_WIDTH", "format_progression"]


# How a duo's **second voice** is named in a printed annotation, keyed by the interval it
# forms with the melody, modulo 12 - so a 9th or a 10th reads as the 3rd it is a compound
# form of, which is what a player calls it.
#
# These name the **interval**, not the chord function, and that is deliberate. A duo is
# built from the chord's guide tone, but the interval it makes with the melody is what the
# reader sees in the tab, and the two do not always agree: Cmaj7 with its root in the
# melody puts the 3rd (E) eight semitones below, which is a major 6th as an interval. So
# the label reads "melody + 6th" for a root-and-3rd pair. Naming it "3rd" there would
# describe the chord degree while contradicting the fretting, and a reader checking one
# against the other is exactly who this annotation is for.
#
# A suspended chord's guide tone is a 4th or a 9th, which is a 5th or a 6th as an interval
# below. A diminished chord's guide tone is a diminished 5th, a tritone below. Every
# semitone count from 2 upward is reachable and listed: a table with a hole in it would
# print "chord tone" for a real interval, which is the one thing worse than no label.
_DUO_SECOND_VOICE_NAMES: Dict[int, str] = {
    2: "2nd", 3: "b3", 4: "3rd", 5: "5th", 6: "b5", 7: "5th",
    8: "b6", 9: "6th", 10: "7th", 11: "7th",
}


def _step_annotation(step: ArrangementStep) -> str:
    """
    Returns the non-chord-tone annotation for a step, e.g. '-> Cmaj9 via extension'.

    A melody-only (no chord) step is annotated instead with '(no chord - melody
    alone)'. A step that was transposed down an octave to stay below
    HIGH_FRET_LIMIT is annotated with the written pitch, since its `melody` is the
    transposed note. Empty string for an ordinary chord tone. Shared by
    format_progression and the demonstration so the two renderings cannot drift
    apart.
    The bass annotation is appended by `_bass_annotation` on **every** path out of
    this function, including the early returns: a walking step can equally be a
    melody-only fill, a repeated melody or a partial shell, and a bass note that is
    only annotated on some of those would be a worse defect than no annotation at
    all. Steps with no bass - every step of every other texture - come back
    unchanged.
    """
    if step.melody_only:
        return _bass_annotation(step, " (no chord - melody alone)")
    if step.chord_unvoiced:
        # The chord is in force and nothing here states it: the palette had no shape
        # under this melody note at all. Without this the step reads as a bare note
        # beneath a chord symbol, which is the other case `partial` exists to prevent
        # - and unlike a thin shell or duo there is not even a second voice to count.
        #
        # Composed with the transposition note rather than replacing it: the rescue
        # drops a high note an octave *and* leaves the chord unstated (measured: two
        # steps of "The Jitterbug Waltz"), and printing one of the two facts would hide
        # the other.
        if step.original_melody is not None:
            return _bass_annotation(
                step,
                " (melody alone, transposed down an octave from "
                f"{step.original_melody} - no voicing for this chord)",
            )
        return _bass_annotation(step, " (melody alone - no voicing for this chord)")
    if step.repeated:
        return _bass_annotation(step, " (melody repeated - single note)")
    if step.original_melody is not None:
        return _bass_annotation(
            step, f" (transposed down an octave from {step.original_melody})"
        )
    # A partial harmonisation is worth saying out loud: the chord name above the step
    # describes the harmony, not every note sounding under the melody, so a reader
    # counting strings would otherwise wonder where the rest of the chord went.
    if step.partial and not step.non_chord_tone:
        if step.grip == "interval":
            # A fill texture, so name the interval rather than the grip: the reader
            # needs to know it is a 6th under a passing note rather than that a chord
            # went missing, and the two notes are right there in the tab.
            #
            # The **upper** voices, because the thumb is not part of the interval - it
            # is a walking line underneath, and counting it would turn every
            # two-note fill under a bass into a seven-note "interval" that has no
            # name in the table and would silently render as "2 notes".
            upper = sorted(step.voicing.upper_midi_notes())
            size = (upper[-1] - upper[0]) % 12 if len(upper) == 2 else 0
            return _bass_annotation(
                step, f" (interval fill - {_INTERVAL_NAMES.get(size, '2 notes')}, partial)"
            )
        if step.grip == "duo":
            # Name the pair from the notes that actually sound, as the interval branch
            # above does. This used to be the fixed string "root & 5th duo", which
            # described **none** of the four pitch-class pairs a duo can produce:
            # `(3,7)`, `(4,7)`, `(0,4)` and `(0,3)` - a b3 with a 5th, a 3rd with a 5th, a
            # root with a 3rd, a root with a b3. It named the degrees the *melody* was
            # once allowed to take, which stopped being true when the melody gate was
            # lifted, and a reader checking the tab against the label found neither.
            #
            # The **upper** voices, for the reason given above: the thumb is a walking
            # line underneath and is not part of the pair.
            upper = sorted(step.voicing.upper_midi_notes())
            if len(upper) == 2:
                size = (upper[-1] - upper[0]) % 12
                return _bass_annotation(
                    step,
                    f" (duo - melody + {_DUO_SECOND_VOICE_NAMES.get(size, 'chord tone')}, partial)",
                )
            return _bass_annotation(step, " (duo - partial)")
        return _bass_annotation(step, f" ({step.grip} - 3rd & 7th, partial)")
    if not step.non_chord_tone:
        return _bass_annotation(step)
    if step.harmonized_as:
        return _bass_annotation(
            step, f" (non-chord tone -> {step.harmonized_as} via {step.strategy})"
        )
    return _bass_annotation(step, " (non-chord tone)")


def _bass_annotation(step: ArrangementStep, existing: str = "") -> str:
    """Appends the walking-bass role and motion to another step's annotation.

    The role is worth printing because the thumb line is no longer uniformly chord
    tones - two thirds of the notes in a textbook walk are extensions or chromatic
    approaches - so a reader counting strings would otherwise wonder why the bass is
    not playing the chord the name above it says.

    The motion needs the *previous* step, which `_step_annotation` is not given, so
    it is spelled from the step alone as `Ab (approach)`: enough to say what the note
    is for, which is the part that is not visible in the tab. `format_progression`
    prints one step per line and the chord name is already there, so a reader can
    see the descent by eye.

    Returns `existing` unchanged when the step carries no bass, which is every step
    of every other texture - so this cannot affect existing output.
    """
    if step.bass is None:
        return existing
    spelled = _note_name(step.bass)
    role = step.bass_role or "walk"
    return f"{existing} (bass: {spelled}, {role})"


def _step_cells(step: ArrangementStep) -> List[str]:
    """The tab cells for one step, honouring step.repeated and step.bass_only.

    A repeated melody is played as a **single note**: only the soprano string is
    struck. Every other string is left blank rather than marked 'x', because the
    player is not being asked to mute anything - the other strings are simply not
    part of this step, and 'x' on five strings says more than the gesture does.

    `bass_only` is the mirror image and the same reasoning: the thumb alone strikes
    and every voice above it is held from the previous shape. It only ever describes
    a **fill**, because a target states its harmony instead (`decisions.is_bass_only`)
    - a step marked both rendered here as a blank column, which is how a chord the
    engine had already voiced went missing; see `docs/open-issues.md` item 4. A step
    that is *both* `repeated` and `bass_only` is a walking bass under a
    re-articulated melody, and it plays the soprano and the thumb - so the two rules
    compose rather than override one another, which is the case an `elif` chain would
    silently drop.

    The step still carries a full drop-2 `voicing`: the engine voice-leads from
    it and a caller wanting the literal shape still has `step.tab_line()`.

    **`melody_voiced=False` removes the soprano from the `repeated` rule.** A repeat is
    a soprano-only re-strike, which presumes there *is* a soprano carrying the tune; under
    `melody="none"` the guitar has none, so striking "the soprano" would strike a
    guide tone and the shape would change on a beat where nothing has. The rule becomes
    **hold the whole shape**, which is what a guitarist comping behind a horn actually
    does while the horn repeats the note.

    This is not a corner case: measured over 2,243 corpus steps, 152 carry `repeated`,
    and a filter that kept the old rule rendered every one of them as a single moving
    note - the part would have played a melody line the arrangement had explicitly given
    away. `tabstaff._strikes_here` reads the same predicate, so the ASCII staff, the HTML
    and this one cannot disagree about what attacks.
    """
    frets = step.voicing.frets
    partial = (step.repeated or step.bass_only) and not step.melody_only
    if not partial:
        return _cells_from_frets(frets)
    struck = set()
    if step.bass_only:
        struck.add(step.voicing.bass_string)
    if step.repeated:
        if not step.melody_voiced:
            # Hold the whole shape: the soprano is not ours to re-strike, and the
            # inner voices are still ringing from the step before. `bass_only` is a
            # separate case above and composes with this one, exactly as it does when
            # the guitar does sing.
            return _cells_from_frets(frets)
        struck.add(step.voicing.soprano_string())
        # A repeated melody still moves the thumb: the bass is a moving voice, not a
        # held one, so blanking it here would silently delete the walking line.
        if step.voicing.bass_midi is not None:
            struck.add(step.voicing.bass_string)
    cells = [_BLANK_CELL] * len(frets)
    for string_index in struck:
        if string_index is not None and 0 <= string_index < len(frets):
            cells[string_index] = str(frets[string_index])
    return cells


def format_progression(steps: List[ArrangementStep]) -> str:
    """
    Renders an arranged progression as tab and returns it as a string.

    This is a pure renderer: it prints nothing and writes nothing to stdout, so
    the caller stays in control of the output. Each step is one line, most compact
    first:

        Dm7      D5  x-x-10-10-10-10
        G7       B4  x-x-5-7-6-7
        Cmaj7    C5  x-x-9-9-8-8

    This used to take `vertical=True` to render each step as a six-line vertical
    block, and the `--vertical` CLI flag existed only to reach it. Both are gone:
    a whole-progression staff is what a player reads, and `format_tab_staff` in
    `tabstaff` renders one, with the chords on their real beats. **This renderer is
    now the compact one-line summary and nothing else**, which is the shape the
    demo and `make demo` print.

    The six-line form is not gone from the library, only from here: a single
    voicing still renders vertically through `Voicing.tab_block()` / `.tab()` and
    `ArrangementStep.tab_block()`, which is where `_tab_block_from_cells` lives.

    Args:
        steps: arrangement steps, typically from VoiceLeadingEngine.arrange_progression.

    Returns:
        The rendered tab, with steps separated by newlines.
    """
    return "\n".join(
        f"{step.chord:<8} {(step.melody or ''):<3} "
        f"{_step_annotation(step)} {'-'.join(_step_cells(step))}".rstrip()
        for step in steps
    )


def _print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    print(
        f"Chord: {step.chord:<8} | Melody: {(step.melody or ''):<3}{_step_annotation(step)} | "
        f"Tab [E-A-D-G-B-E]: {'-'.join(_step_cells(step))} | Melody string: {melody_string}"
    )
