"""Where a **lone note** is fretted: the tune alone, with or without a chord under it.

Every route that sounds the melody by itself - a thinned fill, an `NC` bar, a rescue
when no shape can carry the chord, a demotion when the only shape that fitted needs a
stretch - picks its position here, through `_melody_alone_shape`. The position is a
choice among one-note shapes made by the same `cost.voicing_cost` tuple a chord goes
through, and `_sounding_melody` records the pitch that sounds when the generator had to
drop the written note an octave.

Sits above `bass_merge` and `decisions`; the route handlers that append the steps are in
`routes`.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from musthe import Note

from . import cost as _cost
from . import grips as _grips
from .bass import Slot
from .bass_merge import _attach_bass
from .decisions import is_bass_only
from .tuning import ArrangementStep, Palette, Voicing, _note_name


def _sounding_melody(voicing: Voicing, written: str) -> Tuple[str, Optional[str]]:
    """The pitch a melody-alone step *sounds*, and the written one when they differ.

    `get_melody_only_voicings` retries a note an octave down when no string reaches it
    inside `HIGH_FRET_LIMIT` (13 - G5 is fret 15 on the high E string), so a shape
    built for the tune can sound a whole octave away from the pitch the progression
    asked for. `melody` has to be what **sounds** - the tab is the contract - and
    `original_melody` is what the renderer shows beside it.

    One function, so a fourth route cannot spell it differently: three routes build a
    melody-alone step, and the *sounding* melody is what has to be recorded whichever of
    them built it.
    """
    sounding = max(voicing.midi_notes())
    if sounding == Note(written).midi_note():
        return written, None
    return _note_name(sounding), written


def _melody_alone_shape(
    melody_note: Note,
    *,
    previous: Optional[Voicing],
    top_strings: Tuple[int, ...],
    named_only: bool = False,
) -> Tuple[Optional[Voicing], bool]:
    """The lone-note shape for `melody_note`, with whether its palette was in the window.

    The tune on its own is a **palette like any other** - one position per eligible
    string - so the choice among its members is `cost.voicing_cost`'s: element 1 (frets
    outside the neck window) and element 4 (distance in neck position from the shape the
    hand is holding) place a lone note where a chord would be placed, instead of wherever
    the highest string happens to put it. That is what stops a single note jumping six
    frets away from the chord either side of it.

    `named_only` drops the candidates on strings the caller did not name, which is what
    `_rescue_melody_alone` promises: the generator rescues a note the named set cannot
    carry by searching below it, and that rescue does not widen the caller's soprano set
    - however much better the position on a string it did not ask for.

    Returns `(None, False)` when no candidate exists at all. The window fact is computed
    over the **palette** rather than the chosen shape, because that is what
    `Palette.inside_window` means: whether there was anything inside to play instead.
    """
    candidates = _grips.get_melody_only_voicings(melody_note, prefer=top_strings)
    if named_only:
        candidates = [
            candidate for candidate in candidates
            if candidate.soprano_string() in top_strings
        ]
    if not candidates:
        return None, False
    chosen = _cost.best_voicing(candidates, previous)
    assert chosen is not None
    # The same pair `render._window_clause` measures a step against, so the phrase a
    # reader sees and the fact recorded here cannot disagree.
    inside_window = any(
        all(_cost.NECK_FRET_MIN <= fret <= _cost.NECK_FRET_MAX
            for fret in candidate.active_frets())
        for candidate in candidates
    )
    return chosen, inside_window


def _rescue_melody_alone(
    arrangements: List[ArrangementStep],
    slot: Slot,
    *,
    name: str,
    note_str: str,
    melody_note: Note,
    top_strings: Tuple[int, ...],
    previous: Optional[Voicing],
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
) -> bool:
    """Play the tune alone when no shape in the palette can carry the chord.

    **The note of the tune is never dropped while it can be played at all.** The
    melody-alone route a fill takes is the last resort here too: the tune
    survives, the thumb still walks, and the harmony is stated at the next slot
    that can state it.

    This route is **not** gated on `has_thumb or melody_only`. A palette that cannot
    voice a chord has not thereby lost the melody, so any candidate able to carry the
    tune is taken - and the *claim* such a step makes, that the guitar is playing the
    tune and not the chord, is recorded on the step (`chord_unvoiced`, which the
    renderers report) rather than the step being deleted. Dropping it here would take
    the melody with it.

    Returns **True** when the step was appended. **False** means no string can
    reach the note at all - below the library's G3 floor, or past the end of the
    board - and the caller reports the step as skipped.
    """
    # **The string must be one the caller named.** `get_melody_only_voicings`
    # keeps searching *below* the set it is given, so a note the named set
    # cannot carry - D4 under `top_strings=(5,)`, below the high E string's
    # open pitch - comes back on the B string. That is the documented
    # behaviour of a restricted soprano set and not this rescue's to
    # override: the rescue answers a palette that cannot voice a chord, not
    # a caller asking for a string that cannot carry the tune. `named_only`
    # is where that promise is kept.
    solo_voicing, inside_window = _melody_alone_shape(
        melody_note, previous=previous, top_strings=top_strings, named_only=True
    )
    if solo_voicing is not None:
        # The note may have been dropped an octave to stay inside
        # HIGH_FRET_LIMIT, so the step reports what sounds and keeps the
        # written pitch - the same seam every melody-alone route uses.
        sounding, written_original = _sounding_melody(solo_voicing, note_str)
        step = ArrangementStep(
            chord=name,
            melody=sounding,
            voicing=solo_voicing,
            original_melody=written_original,
            partial=False,
            # The palette is the lone note's own - the positions the caller's strings
            # offer - so the line can say whether anything inside the window was on the
            # table. See `_melody_alone_shape`.
            palette=Palette(available=1, inside_window=inside_window),
            # The harmony is stated nowhere in this step. A fill reaches
            # the same shape deliberately and does not carry this; see
            # `ArrangementStep.chord_unvoiced`.
            chord_unvoiced=True,
            bar=bar,
            beat=beat,
            duration=duration,
            role=role,
            metric_weight=weight,
            bass_only=is_bass_only(slot.bass_only, role),
        )
        _attach_bass(step, slot.bass, arrangements)
        arrangements.append(step)
        return True
    return False


def _demoted_to_melody_alone(
    arrangements: List[ArrangementStep],
    slot: Slot,
    *,
    name: str,
    note_str: str,
    melody_note: Note,
    top_strings: Tuple[int, ...],
    previous: Optional[Voicing],
    best_voicing: Voicing,
    palette: Palette,
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
) -> bool:
    """Play the tune alone when the only shape that fitted needs a stretch.

    Reached only under `decisions.should_demote_to_melody_alone`, which is where
    the *why* of the fallback is documented: a complete chord at the very top of
    the span budget is a fallback, not a re-ranking.

    Returns **True** when the melody-alone step replaced the shape, so the caller
    stops. **False** when the melody alone would be the wider reach of the two,
    which leaves the chosen shape in place for the caller to play.
    """
    solo, inside_window = _melody_alone_shape(
        melody_note, previous=previous, top_strings=top_strings
    )
    if solo is not None and solo.fret_span() < best_voicing.fret_span():
        arrangements.append(ArrangementStep(
            chord=name,
            melody=note_str,
            voicing=solo,
            partial=False,
            # The shape the demotion turned away, and the criterion it did it for: the
            # span is the whole reason, which is what
            # `decisions.should_demote_to_melody_alone` asks about. `inside_window` is the
            # **lone** note's palette rather than the one the turned-away shape came from:
            # the window clause describes the shape that is actually sounding.
            palette=Palette(
                available=palette.available,
                alternative=best_voicing,
                decided_by=_cost.SPAN_CRITERION,
                inside_window=inside_window,
            ),
            bar=bar,
            beat=beat,
            duration=duration,
            role=role,
            metric_weight=weight,
            bass_only=is_bass_only(slot.bass_only, role),
        ))
        _attach_bass(arrangements[-1], slot.bass, arrangements)
        return True
    return False
