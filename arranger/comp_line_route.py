"""The comp line's route adapter: what the line is told about a slot.

Reads the arrangement's own history plus the progression, and produces the
request `comp_line` answers: the home band, the line's state, whether the chord
changed here, and the fill's target register.

Sits between `step_history` and `routes` in the dependency order: it reads the
arrangement and the progression, and `routes.comping_step` calls it. It holds no
selection logic - the ranking and the cost tuple stay where they are - only the
facts the comp line needs to narrow a palette.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from musthe import Note

from . import comp_line as _comp_line
from .bass import Slot
from .chords import ChordParser, normalised_harmony
from .context import SlotContext
from .step_history import last_sounding_step, sounding_tops
from .step_types import ArrangementStep, Voicing


def line_target(
    context: SlotContext, notes: int, bass_voice: bool
) -> Optional[Tuple[int, int]]:
    """The home band the comp line narrows the palette to, or None when it does not run.

    A one-voice comp has no top voice to walk, and a lone bass note belongs at the
    bottom of the neck rather than in the comp's band (`docs/history/comp-line.md`
    §"Bass interactions"). Both keep the unbanded palette, so their shapes are the ones
    the ranking always saw - the line is a narrowing of what the axis offered, never a
    new source of shapes.
    """
    if bass_voice or notes <= 1:
        return None
    return _comp_line.home_band(context.neck.fret_min, context.neck.fret_max)


def line_state(
    arrangements: List[ArrangementStep], context: SlotContext
) -> Tuple[_comp_line.LineState, Optional[float]]:
    """Where the comp line stands, and the register the hand is in.

    Read from the arrangement rather than carried in a field. **The window is the
    current chord's**: a harmony change is a new walk, so its first position is handed
    the incoming top alone - which is also what restarts the direction upward. Within
    one chord the last two tops are the no-retrace window, and the direction is
    `comp_line.read_state`'s derivative of them.

    The register is the previous shape's `avg_fret`, which is where a fill opens.
    """
    previous = last_sounding_step(arrangements)
    if previous is None:
        return (_comp_line.read_state([]), None)
    tops = (
        sounding_tops(arrangements)
        if same_chord(previous, context)
        else [max(previous.voicing.midi_notes())]
    )
    register = (
        previous.voicing.avg_fret if previous.voicing.active_frets() else None
    )
    return (_comp_line.read_state(tops), register)


def same_chord(previous: ArrangementStep, context: SlotContext) -> bool:
    """Whether the last sounding step stated this slot's chord.

    Compared through `normalised_harmony`, so a substituted chord reads as itself and
    two spellings of one chord are not a change.
    """
    return normalised_harmony(previous.chord) == normalised_harmony(
        context.harmony.name
    )


def next_chord_tones(
    context: SlotContext, slot: Slot, beats_per_bar: int
) -> Optional[Tuple[int, ...]]:
    """The next chord's tones, when this slot is the last position before the change.

    **The last position before a harmony change is an approach**, and both halves are
    needed: the written chord must actually change at the next position, and this slot's
    own duration must reach past the barline. A change *inside* a bar is not detected -
    the slot list is not readable forward from here - and the barline is where the
    chord's rhythm puts a change in every committed head.
    """
    index = context.identity.index
    progression = context.identity.progression
    if index + 1 >= len(progression):
        return None
    if normalised_harmony(progression[index + 1][1]) == normalised_harmony(
        context.harmony.name
    ):
        return None
    beat, duration = slot.beat, slot.duration
    if beat is None or duration is None or beat + duration <= beats_per_bar + 1e-9:
        return None
    return ChordParser.get_chord_tones(progression[index + 1][1])


def fill_target(
    context: SlotContext, band: Tuple[int, int], register: Optional[float]
) -> _comp_line.FillTarget:
    """A fill position: the hand's register, the tune's, and the path between them.

    The target is **the fret the returning tune sits at** (`comp_line.tune_register`),
    because the fill is joining the guitar's own line; when no soprano string can reach
    that note the fill holds the register it was handed rather than guessing one. The
    place on the path comes from `comp_line.fill_run`, which reads the run of
    melody-less positions out of the progression.
    """
    index = context.identity.index
    progression = context.identity.progression
    run_index, run_count = _comp_line.fill_run(progression, index)
    previous = register if register is not None else _comp_line.band_middle(band)
    target = previous
    note = _comp_line.next_melody(progression, index)
    if note is not None:
        reachable = _comp_line.tune_register(
            Note(note).midi_note(), context.neck.top_strings
        )
        if reachable is not None:
            target = reachable
    return _comp_line.FillTarget(
        previous=previous, target=target, index=run_index, count=run_count
    )


def line_inputs(
    context: SlotContext,
    slot: Slot,
    beats_per_bar: int,
    band: Tuple[int, int],
    register: Optional[float],
) -> Tuple[Optional[_comp_line.FillTarget], Optional[Tuple[int, ...]]]:
    """The fill target and the next-chord tones for a comping slot.

    A fill ignores the band and bridges toward the tune, so its target is the fret the
    returning melody sits at. Any other position is an approach: it reads the next
    chord's tones, but only when this slot's own duration reaches the barline - the last
    position before a harmony change.
    """
    is_fill = context.arrangement.melody_voiced and context.harmony.melody_note is None
    fill = fill_target(context, band, register) if is_fill else None
    next_tones = None if is_fill else next_chord_tones(context, slot, beats_per_bar)
    return fill, next_tones


def leaving_room_for_the_tune(
    candidates: List[Voicing],
    melody_note: Optional[Note],
    *,
    melody_voiced: bool,
) -> List[Voicing]:
    """The shapes whose top voice stays below the tune note in force.

    A stab must not restate the tune's own pitch. Where the tune is **held** across
    the attack, a shape whose top *is* that pitch takes the fingered string and cuts
    the tie; everywhere it reads as the tune struck on the chord's string rather than
    as an accompaniment under it. So the ceiling is **strict**, and it is a
    **narrowing**: the cost tuple ranks what comes back unchanged, and no criterion is
    added or re-weighted.

    The full palette comes back when nothing sits below the note, so a chord at the
    top of the neck is never lost to a tune above it. Returned unchanged when the
    guitar does not sing here (`melody_voiced` False - the tune is the horn's, and a
    comp behind it stays melody-blind) or when there is no note at all.
    """
    if not melody_voiced or melody_note is None:
        return candidates
    ceiling = melody_note.midi_note()
    below = [
        voicing for voicing in candidates
        if max(voicing.midi_notes()) < ceiling
    ]
    return below or candidates


def line_narrowed(
    arrangements: List[ArrangementStep],
    candidates: List[Voicing],
    context: SlotContext,
    slot: Slot,
    *,
    beats_per_bar: int,
    band: Optional[Tuple[int, int]],
) -> Tuple[List[Voicing], Optional[str]]:
    """The shapes whose top voice is the tone the line chose, and that tone's role.

    **A narrowing, never a widening** - the same form as the requested bass note's, and
    for the same reason: the ranking keeps its fields, and the line decides among shapes
    the ranking would otherwise be free to answer with a static repeat. The palette comes
    back **unchanged when the chosen tone states nothing**, so a chord is never lost to a
    line that could not be played.

    When `band` is None - a one-voice comp or a lone bass part - the line does not run
    and the palette comes back unchanged with no role, so the ranking's answer stands.

    A fill is the one reader that ignores the band: it is the bridge toward the tune, so
    its target is a register rather than a tone.
    """
    if band is None:
        return (candidates, None)
    state, register = line_state(arrangements, context)
    fill, next_tones = line_inputs(context, slot, beats_per_bar, band, register)
    shapes = [_comp_line.LineShape.of(voicing, band) for voicing in candidates]
    tone, role = _comp_line.chosen_top(
        state, shapes, band, next_tones=next_tones, fill=fill
    )
    narrowed = [voicing for voicing in candidates if max(voicing.midi_notes()) == tone]
    if not narrowed:
        return (list(candidates), None)
    return (narrowed, role)

