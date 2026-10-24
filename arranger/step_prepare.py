"""One step's voicing candidates: the octave-down rescue, the non-chord-tone
strategies, and the step's own preparation.

`prepare_step` builds the candidates for one melody note - every allowed soprano
string, every grip family, the octave-down rescue, and the non-chord-tone
strategies - and returns them as a `StepPreparation`. The harmonised route in
`harmonised_route` selects from those candidates.

Sits above `grips`, `cost`, `decisions` and `routes`; below `harmonised_route`
and `movement`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from . import cost as _cost
from . import grips as _grips
from .bass_merge import next_resolution_melody
from .chords import ChordParser, resolve_substitute_harmony
from .grip_tables import GRIP_PREFERENCE
from .grips import MELODY_STRING_CHOICES_FULL
from .step_types import Voicing
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    note_name,
)

__all__ = ["StepPreparation", "prepare_step"]


@dataclass
class StepPreparation:
    """One step's voicing candidates, plus the bookkeeping to report the step.

    Returned by `prepare_step` so a caller that needs extra per-step control can
    choose from these candidates using the engine's own rule rather than
    re-deriving the voicing itself.

    That distinction is load-bearing: a caller that builds its own candidates and
    calls `best_voicing` directly silently skips the non-chord-tone strategies,
    the selector's tone-purity criterion (because `allowed_tones` defaults None)
    and the octave-down rescue. `chord_name` stays the *written* chord even when
    `harmonized_as` names a substitute, and `chord_type` is the quality that name
    spells rather than a second input, because `allowed_tones` is built from the
    written chord and changing that would move the library's published output.
    """

    candidates: List[Voicing]
    written_melody: str
    melody: str
    original_melody: Optional[str]
    chord_type: str
    chord_name: str
    is_non_chord_tone: bool
    strategy: Optional[str]
    harmonized_as: Optional[str]


@dataclass(frozen=True)
class _SearchWindow:
    """Where the left hand may search: the strings, the grip families, the frets."""

    top_strings: Tuple[int, ...]
    grips: Tuple[str, ...]
    fret_min: int
    fret_max: int


@dataclass(frozen=True)
class _Voiced:
    """A prepared note's candidates, the pitch that actually sounds, and why.

    `melody` differs from the written note only when the octave-down rescue fired;
    `strategy` and `harmonized_as` say what the non-chord-tone rule did, if
    anything.
    """

    candidates: List[Voicing]
    melody: Note
    original_melody: Optional[str]
    strategy: Optional[str] = None
    harmonized_as: Optional[str] = None


def _voices_for(
    melody_note: Note,
    written: str,
    name: str,
    window: _SearchWindow,
) -> _Voiced:
    """The candidates for the note, after the octave-down rescue.

    Every allowed soprano string and every grip family, on the chord the name states.

    A melody whose best position sits outside the neck window is re-voiced an
    octave down on the B string. The written pitch is kept in `original_melody`.
    Decided before the non-chord-tone strategies run, so a substituted chord is
    voiced at the transposed pitch too rather than snapping back up.

    The guard requires candidates to exist: this repositions a voicing that is
    playable but sits too high. A melody unreachable at the written pitch (C6,
    fret 20 - past the end of the board) is left alone, because there is no shape
    to move down and respelling it would hide the real problem.
    """
    candidates = _grips.get_all_grip_voicings(
        melody_note, name,
        top_strings=window.top_strings, grips=window.grips,
    )
    voiced = _Voiced(candidates=candidates, melody=melody_note, original_melody=None)
    here = _cost.window_penalty(candidates, window.fret_min, window.fret_max)
    if not candidates or here <= 0:
        return voiced
    octave_down = _grips.get_octave_down_candidates(
        melody_note, name,
        top_strings=window.top_strings, grips=window.grips,
    )
    # Only take the lower octave when it genuinely improves the placement, or a
    # merely slightly out-of-window melody would be moved for nothing.
    there = _cost.window_penalty(octave_down, window.fret_min, window.fret_max)
    if not octave_down or there >= here:
        return voiced
    return _Voiced(
        candidates=octave_down,
        melody=Note(note_name(melody_note.midi_note() - 12)),
        original_melody=written,
    )


def _apply_non_chord_tone(
    voiced: _Voiced,
    *,
    name: str,
    strategy: str,
    previous: Optional[Voicing],
    previous_chord: Optional[str],
    window: _SearchWindow,
    progression: Sequence[Tuple[Optional[str], str]],
    index: int,
) -> _Voiced:
    """Re-voice a melody that is not a chord tone, and record what was done.

    Strategy 3 first: holding the shape moves less than any re-voicing.
    Strategies 1 and 2 then reharmonise the note as a genuine chord tone.

    When neither settles anything the strategy is still **recorded**, because the
    line has to name it: "non-chord tone" alone cannot tell a substitution that
    failed from one that was never attempted. What distinguishes the two is
    `harmonized_as`, which stays None here - not the strategy field.
    """
    if strategy == "sustain" and previous is not None:
        sustained = _grips.sustain_inner_voices(previous, voiced.melody)
        if sustained is not None:
            return replace(
                voiced,
                candidates=[sustained],
                strategy="sustain",
                harmonized_as=previous_chord,
            )
    substitute = resolve_substitute_harmony(
        voiced.melody,
        name,
        strategy,
        next_melody=next_resolution_melody(progression, index),
    )
    if substitute is not None:
        substitute_name = substitute[0]
        substituted = _grips.get_all_grip_voicings(
            voiced.melody,
            substitute_name,
            top_strings=window.top_strings, grips=window.grips,
        )
        if substituted:
            return replace(
                voiced,
                candidates=substituted,
                strategy=strategy,
                harmonized_as=substitute_name,
            )
    return replace(voiced, strategy=strategy)


def prepare_step(
    progression: Sequence[Tuple[Optional[str], str]],
    index: int,
    previous: Optional[Voicing] = None,
    previous_chord: Optional[str] = None,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    non_chord_tone: str = "extension",
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> Optional[StepPreparation]:
    """
    Builds one step's candidates, leaving the choice of shape to the caller.

    This is a whole step up to selection: the candidates across every allowed
    soprano string and grip family, the octave-down rescue, and the
    non-chord-tone strategies. `harmonised_route.harmonised_step` selects with
    `select_step_voicing` straight afterwards, and the facade's single-step
    method does the same, so the two cannot drift.

    Returns None when the step has no voicing at all. `previous` is only read
    by the `sustain` strategy, and `previous_chord` is what that strategy
    reports as `harmonized_as`.
    """
    note_str, name = progression[index]
    if note_str is None:
        # No melody to pin. `arrange_progression` skips such a slot before it can
        # reach here - every singing route needs a note, and the comping route
        # never calls this - so this is the widened pair type's honest answer
        # rather than a `Note(None)` waiting for a caller that lies.
        return None
    melody_note = Note(note_str)
    window = _SearchWindow(
        top_strings=top_strings, grips=grips,
        fret_min=fret_min, fret_max=fret_max,
    )
    voiced = _voices_for(melody_note, note_str, name, window)
    is_non_chord_tone = (
        _chords.quality_of(name) in ChordParser.CHORD_TONES_FROM_ROOT
        and not _chords.is_chord_tone(melody_note, name)
    )
    if is_non_chord_tone:
        voiced = _apply_non_chord_tone(
            voiced,
            name=name,
            strategy=non_chord_tone,
            previous=previous,
            previous_chord=previous_chord,
            window=window,
            progression=progression,
            index=index,
        )

    if not voiced.candidates:
        return None

    return StepPreparation(
        candidates=voiced.candidates,
        written_melody=note_str,
        # The transposed pitch when moved down an octave: the step reports
        # what actually sounds.
        melody=(
            note_str
            if voiced.original_melody is None
            else note_name(voiced.melody.midi_note())
        ),
        original_melody=voiced.original_melody,
        chord_type=_chords.quality_of(name),
        chord_name=name,
        is_non_chord_tone=is_non_chord_tone,
        strategy=voiced.strategy,
        harmonized_as=voiced.harmonized_as,
    )
