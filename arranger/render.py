"""Per-step rendering: one line per chord, or a six-line vertical block.

`format_progression` is the compact renderer, and it is **pure** - it returns a
string and prints nothing, so the caller stays in control of the output. The
whole-progression staff renderers are a different shape of output and live in
`tabstaff`.

`_step_annotation` is shared by `format_progression` and the demonstration, so the
two renderings cannot drift apart. A step can be several things at once - a
non-chord tone, a repeated melody, a partial shell, a thumb note - and the
precedence between them is the whole content of that function.

The tab-cell primitives (`_MUTED_CELL`, `_cells_from_frets`,
`_tab_block_from_cells`) are **not** defined here: `Voicing.tab_block` calls them
and `Voicing` sits below this module, so they live in `tuning` and are imported
from there. `_STAFF_CELL_WIDTH` was the second of two identical definitions of one
constant - `tabstaff` had the other - and is imported for the same reason.
"""

from __future__ import annotations

from typing import List

from .grips import _INTERVAL_NAMES
from .tuning import (
    _BLANK_CELL,
    _MUTED_CELL,
    _STAFF_CELL_WIDTH,
    ArrangementStep,
    _cells_from_frets,
    _note_name,
    _tab_block_from_cells,
)

__all__ = ["_MUTED_CELL", "_STAFF_CELL_WIDTH", "format_progression"]


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
            return _bass_annotation(step, " (root & 5th duo - partial)")
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
    and every voice above it is held from the previous shape. A step that is *both*
    is a walking bass under a re-articulated melody, and it plays the soprano and
    the thumb - so the two rules compose rather than override one another, which is
    the case an `elif` chain would silently drop.

    The step still carries a full drop-2 `voicing`: the engine voice-leads from
    it and a caller wanting the literal shape still has `step.tab_line()`.
    """
    frets = step.voicing.frets
    partial = (step.repeated or step.bass_only) and not step.melody_only
    if not partial:
        return _cells_from_frets(frets)
    struck = set()
    if step.bass_only:
        struck.add(step.voicing.bass_string)
    if step.repeated:
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


def format_progression(steps: List[ArrangementStep], vertical: bool = False) -> str:
    """
    Renders an arranged progression as tab and returns it as a string.

    This is a pure renderer: it prints nothing and writes nothing to stdout, so
    the caller stays in control of the output.

    With vertical=False (the default) each step is one line, most compact first:

        Dm7      D5  x-x-10-10-10-10
        G7       B4  x-x-5-7-6-7
        Cmaj7    C5  x-x-9-9-8-8

    With vertical=True each step is rendered as a full six-line vertical tab
    block, preceded by its chord, melody and any non-chord-tone annotation.

    Args:
        steps: arrangement steps, typically from VoiceLeadingEngine.arrange_progression.
        vertical: render the six-line vertical tab instead of the one-line form.

    Returns:
        The rendered tab, with steps separated by newlines.
    """
    if not vertical:
        return "\n".join(
            f"{step.chord:<8} {step.melody:<3} "
            f"{_step_annotation(step)} {'-'.join(_step_cells(step))}".rstrip()
            for step in steps
        )

    blocks = []
    for step in steps:
        header = f"{step.chord} ({step.melody}){_step_annotation(step)}"
        blocks.append("\n".join([header, *_tab_block_from_cells(_step_cells(step))]))
    return "\n\n".join(blocks)


def _print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    print(
        f"Chord: {step.chord:<8} | Melody: {step.melody:<3}{_step_annotation(step)} | "
        f"Tab [E-A-D-G-B-E]: {'-'.join(_step_cells(step))} | Melody string: {melody_string}"
    )
