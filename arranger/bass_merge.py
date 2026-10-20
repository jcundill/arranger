"""Merging the walking bass into a chosen step, holding it, and the next resolution
melody.

`attach_bass` runs **after** selection: the thumb is written into the fret vector
only once the upper shape has been chosen, so it cannot enter the cost tuple by
construction. Three independent failures are all handled the same way - the step
survives and the bass is named, which is why `bass_refused` carries the wanted pitch
class rather than a flag.

`carry_bass` is the other half of the same decision, and also after selection: a thumb
note is a **line**, so the note a step strikes keeps sounding under the steps that
follow it - until the next attack, the bar line, a rest, or a shape the hand cannot
hold it under.

`next_resolution_melody` answers a different question: the pitch the dim7 substitution
resolves into, read from the written onsets when the comping route has no melody of
its own.

This module sits above `bass` and below `movement`, and imports nothing from
`movement` - so the step loop can call it without a cycle.
"""

from __future__ import annotations

from typing import Container, List, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from .bass_place import BassNote, held_shape, place_bass, previous_bass
from .fingers import can_fret
from .tuning import PITCH_CLASS_NAMES, ArrangementStep


def attach_bass(
    step: ArrangementStep,
    note: Optional[BassNote],
    arrangements: List[ArrangementStep],
) -> None:
    """
    Merges one walked beat into a step: records it, then places it on a string.

    Deliberately after selection (see the caller). Three independent failures are
    all handled the same way - **the step survives and the bass is named**:

    - no candidate string survives `place_bass`'s filters, so there is nowhere to
      put the thumb. `step.bass_refused` records the wanted pitch class and
      `annotation._bass_refusal_clause` phrases it, because a reader cannot tell the
      three ways that happens apart from the outside and the common one is not the
      intuitive one: no free string below the melody, **no octave of the wanted
      pitch below the shape's own lowest note**, or a fifth fret for four fingers.
      The counts are in `docs/open-issues.md` item 2, and the field carries the
      wanted pitch rather than the cause, so a reader who needs the split has to
      re-measure it there. Same argument as the neck window being a penalty rather than
      a filter: losing a step is worse than losing its bass.
    - a candidate string exists, but every one of them would need a **fifth fret**
      from a hand already holding the shape - the `bass_only` case. A bass note a player cannot finger is not a
      bass note, so it is refused rather than written.
    - a step that already carries a bass, which cannot happen while the union is
      one walked note per slot, but is checked rather than assumed.

    The previous thumb note is the search's continuity term, so a line does not
    leap octaves between beats purely because a nearer-in-fret candidate happened
    to be two octaves away.
    """
    if note is None:
        return
    step.bass_role = note.role
    if step.bass is not None:
        return
    # A `bass_only` step re-states nothing above the thumb, so the shape the hand is
    # holding is the last **struck** one, not this step's own thinned vector.
    # Measured against the thinned vector the thumb is placed on a string the hand
    # is already fingering and ranked from a fret the hand is not at - the
    # unplayable bar. For any other step the current
    # voicing *is* the shape, so `held` must not narrow it.
    held = (
        held_shape(arrangements)
        if step.bass_only and not step.melody_only
        else None
    )
    placed = place_bass(
        step.voicing,
        note.pitch_class,
        previous_bass=previous_bass(arrangements),
        held=held,
    )
    if placed is None:
        # The pitch class rather than a flag: the tab shows no thumb, so a reader
        # has no way to derive which note of the walk went missing, and the
        # `bass_role` above has already been recorded for this beat.
        step.bass_refused = PITCH_CLASS_NAMES[note.pitch_class % 12]
        return
    midi, string_index, fret = placed
    step.voicing.bass_midi = midi
    step.voicing.bass_string = string_index
    step.voicing.frets[string_index] = fret
    # `bass_pc` is the lowest sounding voice, which the thumb now is by
    # construction: it sounds below every upper voice, or it was not placed.
    step.voicing.bass_pc = midi % 12


def carry_bass(steps: List[ArrangementStep]) -> None:
    """Let a thumb note ring until the next attack or the bar line.

    A bass line is a line: `--bass-on 1` states one note per bar, and that note is
    meant to be *heard* under the melody notes that follow it. Merging each walked beat
    into the step it attacks on says what the thumb plays; this says for how long, by
    carrying the ringing note into the steps that follow, so the tab, the staff, the
    score and the GP5 file all know the string is sounding but not plucked.

    **After selection, like `attach_bass`**, and for the same reason: a voice a
    candidate did not choose cannot enter the cost tuple. It is also after the *routes*,
    because a note that is not struck is not a placement decision at all.

    Five things end the ring, and each is a fact rather than a policy:

    - **a new thumb attack**, which is what `bass_merge` recorded for that beat;
    - **the bar line** - a bass player releases on the bar and a line that re-attacks
      there would double the note otherwise;
    - **a rest** (a step that sounds nothing), because the guitar has stopped;
    - **a shape that uses the string**, which is a fret already written there; and
    - **a shape below the ringing note**, because the thumb is the lowest voice by
      construction (`place_bass`) and a note above the chord is not that note any
      more. A fret the hand cannot reach with the shape - `can_fret` - ends it too.

    An **unplaced** step (`bar` is None) carries nothing: a hand-built progression has
    no bar line to stop at, so carrying across it would ring a note through an
    arrangement that never asked for a rhythm.
    """
    ringing: Optional[Ring] = None
    for step in steps:
        if step.bass is not None and not step.bass_held:
            ringing = _struck(step)
            continue
        if ringing is None:
            continue
        if not _takes_the_ring(step, ringing):
            ringing = None
            continue
        _carry(step, ringing)


#: A thumb note as the ring carries it: (midi, string, fret, the bar it began in).
Ring = Tuple[int, int, int, int]


def _struck(step: ArrangementStep) -> Optional[Ring]:
    """The note this step plucks, as a ring, or None when it plucks none.

    `bass_pc` is the lowest sounding voice, so it is present exactly when the step
    carries a note of its own - a carried one is filtered by `bass_held` before this is
    asked.
    """
    string = step.voicing.bass_string
    if step.bass is None or string is None or step.bar is None:
        return None
    return (step.bass, string, step.voicing.frets[string], step.bar)


def _takes_the_ring(step: ArrangementStep, ringing: Ring) -> bool:
    """Whether `step` can sound `ringing` under what it plays. See `carry_bass`."""
    midi, string, fret, bar = ringing
    if step.bar != bar or not step.voicing.active_frets():
        return False
    if step.voicing.frets[string] >= 0:
        return False
    if min(step.voicing.midi_notes()) <= midi:
        return False
    merged = list(step.voicing.frets)
    merged[string] = fret
    return can_fret(merged)


def _carry(step: ArrangementStep, ringing: Ring) -> None:
    """Write the ringing note into `step`: sounding, and not plucked."""
    midi, string, fret, _bar = ringing
    step.voicing.frets[string] = fret
    step.voicing.bass_midi = midi
    step.voicing.bass_string = string
    step.voicing.bass_pc = midi % 12
    step.bass_held = True


def next_resolution_melody(
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
    onsets: Optional[Container[int]] = None,
) -> Optional[str]:
    """
    The pitch the melody line resolves into: the first following step whose
    melody is a chord tone of its own chord (None when the phrase never
    resolves). Spells the dim7 substitution's root.

    A slot with no melody note is stepped over: silence resolves into nothing.

    `onsets`, when given, restricts the scan to slots whose melody **articulates**.
    On the comping route a held position carries the note still sounding, not the
    horn's *next* note, so the resolution target must be read from the written
    onsets alone - otherwise a sustained note would name itself the thing the line
    resolves into (§9.3 step C). `None` scans every slot, the melody route's rule.
    """
    for offset in range(index + 1, len(progression)):
        if onsets is not None and offset not in onsets:
            continue
        note_str, chord_type, name = progression[offset]
        if note_str is None:
            continue
        if _chords.is_chord_tone(Note(note_str), chord_type, name):
            return note_str
    return None
