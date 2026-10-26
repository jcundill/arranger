"""The score placement shared by the MusicXML and GP5 writers.

`score_events` turns an arrangement into absolute-onset events, folding a held step
into the event before it; `substitute_steps` names the harmony a step is actually
sounding. Both writers place a head through these, so the two agree on the beat of
every chord and on the symbol printed over it.

This module imports `arranger.tuning` and nothing else, so it is free of both
optional extras: each writer owns its format, and the placement belongs to neither.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from arranger.step_types import ArrangementStep

# The shortest event MusicXML can write, in quarter lengths: a sixteenth. See the
# duration floor in `score_events`.
_MIN_EVENT_LENGTH = 0.25


def score_events(
    steps: List[ArrangementStep],
    beats_per_bar: int,
    rhythm: bool,
    beat_type: int = 4,
    first_bar_implicit: Optional[bool] = None,
) -> Tuple[List[Tuple[Optional[ArrangementStep], bool, float]], float]:
    """
    The arrangement as (step, strikes, quarter_length) events, and the pickup.

    A **held** step is not emitted: its length is folded into the event before it,
    which is what a tie means. A step is a hold when it sounds the same pitches as
    the one before it and is not a re-articulated melody - the same rule, on the same
    comparison of sounding pitches, that `tabstaff._staff_columns` applies.

    The pickup is how many quarter lengths of the **first written bar** are not
    music: the bar line before the first note rather than the one after it. Two
    different things leave a first bar short, and both answer here.

    - A head that starts part-way into its bar has silence *before* the first note.
      One that starts on the third beat has a pickup of two beats, and the first bar
      is written short.
    - A head whose first bar simply **stops early** - the anacrusis a lead sheet
      writes and closes with a thin double bar line - has silence *after* its last
      note. Its first bar is short by exactly that much, and the notes it does carry
      are the whole of the measure that is written.

    Both are read from the events actually emitted, because the cap on the last
    group of a bar is what decides how much of that bar the music occupies. A first
    bar whose content fills it has a pickup of 0 and every bar is a full bar.

    The trailing rest that would fill an incomplete first bar is **dropped**, not
    shortened: the measure is written short instead. That is what lets `tabxml`
    mark it `implicit` and close it with a thin double bar line, and what lets
    `tabgp` - whose measures are fixed-length - write the same silence as a leading
    rest, padding before the pickup notes rather than after them.

    `first_bar_implicit` is what the **source** said about the first bar, and it is a
    tri-state rather than a flag. `None` is "nothing said", so the shortfall is the only
    evidence there is and is read as an anacrusis - every arrangement built without a
    score. `False` is a **whole** first bar: its silence is written instead (the lead-in
    becomes a leading rest, the trailing rest stays, the pickup is 0, so the measure adds
    up to its signature), which is the one answer onsets cannot give, because a complete
    first bar can still begin with three beats of rest. `True` is a stated anacrusis, and
    its amount is still measured here: a score states *that* the bar is short, not by how
    much, so `True` and `None` answer alike and only the writer's certainty differs. The
    test is `is False`, never falsiness: `None` means "no opinion", the opposite of
    "complete".

    It matters because the onsets are counted from zero at the first note, so the bar
    lines are not at multiples of the bar length - the first note of a Blue Train
    head sits at onset 4.0, which is bar 1's downbeat, and a grid anchored at zero
    would put a bar line in the middle of its first bar. The offset of the first note
    within its own bar is what recovers the real metre.

    Note that the steps are placed here rather than taken from
    `tabstaff._staff_columns`, although the two agree on everything a *staff* can
    show. The column grid is deliberately lossy: two steps sharing an onset collapse
    into one column, "the first step in a column owns that column", which is right
    for a fixed-width ASCII staff and wrong for a score, where the second chord is a
    note the reader must see. The eighth-note skeleton puts two steps on the last beat
    of most bars, so sharing the grid would drop a chord from every bar of a head.
    What is shared is the *semantics* - absolute onsets with signed bars, and
    collapse on unchanged sounding pitches - and both are implemented here.

    `beat_type` is what makes a **beat** a measurable length, and the expression
    is `4 / beat_type` quarters to the beat. That is a half note in 2/2 and a
    quarter in 4/4, so both metres give a four-quarter bar and only the counting
    differs. The tempting `beat_type / 4` is the same number inverted, and it is
    right in 4/4 and four times too small in 2/2 - which is why a bar written that
    way holds a quarter of the music its signature claims. `AGENTS.md` records
    this as the one error 4/4 cannot catch.

    An arrangement with **no steps** has no first onset to measure a pickup from,
    so it yields no events and a pickup of 0 rather than raising. The empty case
    is answered here, at the definition: `format_musicxml` and `format_gp5` both
    place through this seam, and each renderer's own `if not steps` guard is its
    documented empty-in/empty-out contract (an empty document for an empty
    arrangement), not what keeps this function safe to call.
    """
    if not steps:
        # No first onset, so no pickup to measure - and nothing to place. Answered
        # at the definition rather than guarded at each caller: `format_musicxml`
        # and `format_gp5` both place through this seam.
        return [], 0.0
    beat_in_quarters = 4.0 / float(beat_type)
    bar_length = float(beats_per_bar) * beat_in_quarters
    timed = bool(rhythm) and all(step.has_timing for step in steps)
    placed, lead_in = _placed_steps(steps, beats_per_bar, beat_type, rhythm)

    events, first_bar, first_bar_content, first_bar_end = _build_events(
        placed, beats_per_bar, beat_in_quarters, timed
    )
    # **A first bar the source states is complete stays complete.** Its silence is
    # written rather than turned into an anacrusis: the lead-in becomes a rest event at
    # the head of the bar, and the trailing rest stays where the cap put it, so the
    # measure adds up to its signature. See `first_bar_implicit` in the docstring.
    if first_bar_implicit is False:
        if lead_in > 1e-9:
            events.insert(0, (None, False, lead_in))
        return events, 0.0
    pickup = lead_in
    # **An incomplete first bar is an anacrusis.** Its music does not fill the bar,
    # so the first written measure is short by exactly the difference, and the
    # trailing rest that would have filled it is dropped: the bar is short by
    # design, and writing the rest would make it a full one again.
    if first_bar is not None and first_bar_end:
        shortfall = bar_length - first_bar_content
        if shortfall > 1e-9:
            pickup = shortfall
            if events[first_bar_end - 1][0] is None:
                events.pop(first_bar_end - 1)

    return events, pickup


def _build_events(
    placed: List[Tuple[float, ArrangementStep]],
    beats_per_bar: int,
    beat_in_quarters: float,
    timed: bool,
) -> Tuple[
    List[Tuple[Optional[ArrangementStep], bool, float]], Optional[int], float, int
]:
    """
    The events, and how much of the first bar they occupy.

    Returns `(events, first_bar, first_bar_content, first_bar_end)`. The last three
    are what `score_events` needs to decide whether the first bar is an anacrusis:
    its number (`None` for an untimed progression, which has no bars), the cumulative
    length of the events through its last **step** (internal rests count, a trailing
    rest does not), and the index in `events` just past its last event.

    The position is tracked as the events are placed rather than read back from their
    lengths afterwards, because a rest carries no step to say which bar it is in.
    """
    first_bar = placed[0][1].bar if timed else None
    first_bar_content = 0.0
    first_bar_end = 0
    position = 0.0

    events: List[Tuple[Optional[ArrangementStep], bool, float]] = []
    index = 0
    while index < len(placed):
        onset = placed[index][0]
        # Every step sharing this onset, kept: a score has to show them all.
        group: List[ArrangementStep] = []
        while _shares_onset(placed, index, onset):
            group.append(placed[index][1])
            index += 1
        # The group lasts until the next distinct onset; `_group_span` holds why that
        # is measured to the next *sound* and not from the transcribed `duration`.
        span = _group_span(placed, index, onset, beats_per_bar, beat_in_quarters)

        # Several steps can share one onset - the eighth-note skeleton puts two on the
        # last beat of most bars - and they divide up the time equally, capped and
        # floored by `_capped_span` and `_group_shares`, which hold the two rules:
        # a gap is a rest rather than a held note, and the sixteenth floor gives way
        # to the bar it would overrun.
        gap = span
        span = _capped_span(span, group, timed, index < len(placed))
        lengths, rest_length = _group_shares(span, gap, len(group))

        in_first_bar = _in_bar(group[0], first_bar)
        next_in_first_bar = _next_in_bar(placed, index, first_bar)

        for step, length in zip(group, lengths):
            if _is_hold(step, events):
                # Held, not struck: extend what is already ringing rather than
                # writing a second copy of the same shape.
                held_step, held_strikes, held_length = events[-1]
                events[-1] = (held_step, held_strikes, held_length + length)
            else:
                events.append((step, True, length))
            position += length
            if in_first_bar:
                # Through the last *step* only: a rest that follows it is the
                # bar's trailing silence, and `score_events` must not count it.
                first_bar_content = position

        if rest_length > 1e-9:
            # Silence between this note and the next sound, written as an explicit
            # rest. `None` is what the renderers already read as "nothing here":
            # `tabxml._build_part` writes a MusicXML `<rest>`, `tabstaff` leaves the
            # cell blank and clears the ring, and `tabgp` writes `BeatStatus.rest`.
            # Without it the bar opens with the previous shape held over the gap,
            # which is the tie this whole branch exists to prevent.
            events.append((None, False, rest_length))
            position += rest_length

        if in_first_bar and not next_in_first_bar:
            first_bar_end = len(events)
    return events, first_bar, first_bar_content, first_bar_end


def _shares_onset(
    placed: List[Tuple[float, ArrangementStep]], index: int, onset: float
) -> bool:
    """Whether the next step in `placed` starts at `onset`, if there is one."""
    return index < len(placed) and abs(placed[index][0] - onset) < 1e-9


def _in_bar(step: ArrangementStep, bar: Optional[int]) -> bool:
    """Whether `step` is in `bar` - false when there is no bar to ask about."""
    return bar is not None and step.bar == bar


def _next_in_bar(
    placed: List[Tuple[float, ArrangementStep]], index: int, bar: Optional[int]
) -> bool:
    """Whether the group at `index` is in `bar`, if there is a group there at all."""
    return index < len(placed) and _in_bar(placed[index][1], bar)


def _placed_steps(
    steps: List[ArrangementStep],
    beats_per_bar: int,
    beat_type: int,
    rhythm: bool,
) -> Tuple[List[Tuple[float, ArrangementStep]], float]:
    """Each step's absolute onset, sorted, and the first bar's lead-in.

    The onset is the bar's downbeat plus the beat within the bar, with signed bars so
    a pickup in a negative bar sorts before bar 0 with no special case - exactly what
    `NoteEvent.beat_position` computes. Without timing (or with `rhythm=False`) the
    steps fall back to the uniform one-chord-per-beat grid the other two renderers
    also use.

    The **lead-in** is how far the first note sits past the bar line before it, which
    is why it is a modulo of the bar length: the onsets are counted from zero at the
    first note, so the bar lines are not at multiples of the bar length, and this
    offset is what recovers the real metre.

    That answers only the silence *before* the first note. `score_events` extends it
    with a first bar that stops early - the silence *after* the last note - and decides
    from `first_bar_implicit` whether the lead-in is a pickup or a rest inside a whole
    bar, which is why it is returned rather than written straight into the events.
    """
    beat_in_quarters = 4.0 / float(beat_type)
    if rhythm and all(step.has_timing for step in steps):
        placed = [
            (step.bar * beats_per_bar + (step.beat - 1.0), step)  # type: ignore[operator]
            for step in steps
        ]
    else:
        placed = [(float(index), step) for index, step in enumerate(steps)]
    placed.sort(key=lambda item: item[0])
    lead_in = (placed[0][0] % beats_per_bar) * beat_in_quarters
    return placed, lead_in


def _group_span(
    placed: Sequence[Tuple[float, ArrangementStep]],
    next_index: int,
    onset: float,
    beats_per_bar: int,
    beat_in_quarters: float,
) -> float:
    """How long the group starting at `onset` lasts, up to the next distinct onset.

    Measuring to the next onset is what makes the written rhythm survive: a triplet
    transcription exports as triplets without this module ever knowing what a triplet
    is.

    The last group has no next onset, so it runs to the end of its own bar. The
    transcribed `duration` is **not** used for that span: it is the length of the last
    melody note, a fraction of a whole note MusicXML cannot always express, and music21
    refuses the whole export over one (`MusicXMLExportException`). Losing the tail of a
    head to that would be a poor trade; `_build_part` pads the closing bar instead.
    """
    if next_index < len(placed):
        return (placed[next_index][0] - onset) * beat_in_quarters
    bar_end = (int(onset // beats_per_bar) + 1) * beats_per_bar
    return max(bar_end - onset, 1.0) * beat_in_quarters


def _capped_span(
    span: float,
    group: Sequence[ArrangementStep],
    timed: bool,
    has_next: bool,
) -> float:
    """`span`, capped by the melody's own written length - and only ever a cap.

    **A gap is a rest, and a note is only as long as it is written.** The gap-to-next-
    onset rule says how long a group has until the next *sound*, which is not the same
    as how long it *sounds*: bar 4 of "But Not For Me" is one whole note and bar 5 opens
    with a quarter rest, so the gap is five quarters and the note is held over the rest
    into the next bar - a tie in GP5, where the score says silence. `duration` is the
    melody note's own length in whole notes, so it caps the span.

    Capped rather than used as the span, because it is not always expressible - which
    is why the gap rule exists at all. A `duration` longer than the gap is ignored, so
    nothing is stretched, and a note with no duration keeps the gap exactly.

    Not applied to the last group: it runs to the end of its bar by definition, so
    there is no gap to represent and a cap would only invent a rest at the end.
    """
    if not (timed and has_next and any(step.duration for step in group)):
        return span
    longest = max(step.duration or 0.0 for step in group) * 4.0
    return longest if longest + 1e-9 < span else span


def _group_shares(span: float, gap: float, count: int) -> Tuple[List[float], float]:
    """Divide `span` between `count` steps, and say how much silence is left over.

    Divided **after** the cap, so the group shares the time it actually occupies and
    the silence is left over rather than handed out with the notes.

    The sixteenth floor can push the shares past the gap they came from - three steps
    in a quarter of a bar is three sixteenths, not a quarter - and a group that
    overruns its own bar is the one thing a reader rejects outright ("voice 1 is too
    long"). So the floor is given up when it would do that: the gap is what the score
    says, and it wins.

    The rest is measured from what was *written* rather than from the cap, because the
    floor can make a group longer than the cap; taking it from the cap would add the
    two together and run the bar past its signature.
    """
    share = span / count
    lengths = [max(share, _MIN_EVENT_LENGTH) for _ in range(count)]
    if sum(lengths) > gap + 1e-9:
        lengths = [share] * count
    return lengths, max(gap - sum(lengths), 0.0)

def _is_hold(
    step: ArrangementStep,
    events: Sequence[Tuple[Optional[ArrangementStep], bool, float]],
) -> bool:
    """
    True when this step is the previous one still ringing rather than a new attack.

    The comparison is of sounding pitches, not of written note names, because either
    step may itself have been transposed down an octave by the `HIGH_FRET_LIMIT`
    rule. A repeated melody is excluded: its note is genuinely re-articulated, which
    is why `ArrangementStep.repeated` overrides the hold - see
    `tabstaff._staff_columns` for the same rule in the same words.
    """
    if not events or step.repeated:
        return False
    if step.chord_attack:
        # The chord's rhythm **named** this position, so it is a new attack even where
        # the shape is the one already ringing. The same exemption `bass_held` below
        # makes from the other end, and for the same reason: a struck voice is a strike
        # however the pitches compare. Without it a comp on `--chord-on every-beat` was
        # written as one long chord a bar instead of one attack per beat.
        return False
    if step.bass is not None and not step.bass_held:
        # The thumb is **struck** here, so this is an attack however the upper voices
        # compare: a bass line on one chord repeats its root beat after beat, and
        # folding those into one tied note deleted three of the four from the score
        # (`tests/test_lone_bass.py` counts them). A carried thumb is the opposite -
        # it is still ringing, and that *is* the tie.
        return False
    if sum(1 for fret in step.voicing.frets if fret >= 0) <= 1:
        # A single sounding note cannot hold: if it sounds again, the string is
        # re-articulated. Without this, sustain-mode short melody notes collapse
        # into one long note (`tests/test_holds.py` counts them).
        return False
    previous = events[-1][0]
    if previous is None:
        return False
    return sorted(previous.voicing.midi_notes()) == sorted(step.voicing.midi_notes())


def substitute_steps(steps: List[ArrangementStep]) -> List[ArrangementStep]:
    """
    The harmony a step is *sounding*, as a step carrying that chord name.

    The chord name to print for a step, which is the one actually sounding.

    A step harmonised under a substitution or a tension carries it in
    `harmonized_as`, and the written name is not what the notes are. Printing the
    written chord over such a step would put a symbol on the score for pitches that
    are not in it - the same thing `step_annotation` exists to prevent in the tab.
    A step with no substitution is returned untouched, so the two renderers spell
    an ordinary chord identically.
    """
    substituted: List[ArrangementStep] = []
    for step in steps:
        harmony_name = step.harmonized_as
        if harmony_name and harmony_name != step.chord:
            step = ArrangementStep(**{**step.__dict__, "chord": harmony_name})
        substituted.append(step)
    return substituted

