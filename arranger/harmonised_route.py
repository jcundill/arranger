"""The melody-bearing route: pin the tune, select a voicing, emit the step.

Reached when the guitar *sings* the slot - or when every other route declined
it. This is the route the whole library is built around: `prepare_step` supplies
the candidates, `voicing_cost` picks among them, and the last resort before
silence is the melody alone.

Sits above `step_prepare`, `routes`, `melody_alone`, `decisions`, `bass_merge`,
`chords`, `cost`, `grips`, `grip_tables`; below `movement`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Sequence, Tuple

from . import cost as _cost
from . import grips as _grips
from .bass import Slot
from .bass_merge import attach_bass
from .chords import ChordParser, normalised_harmony
from .context import SlotContext
from .decisions import (
    dropped_for_the_bass,
    hold_the_melody_string,
    holds_the_shape,
    is_bass_only,
    is_repeated_step,
    leaving_room_for_the_bass,
    melody_is_ringing,
    palette_facts,
    select_step_voicing,
    should_demote_to_melody_alone,
    should_promote_fill,
)
from .grip_tables import GRIP_MAX_SPAN
from .melody_alone import demoted_to_melody_alone, rescue_melody_alone
from .routes import rest_step
from .slot_plan import SlotPlan
from .step_history import last_sounding_step, previous_shape
from .step_prepare import StepPreparation, prepare_step
from .step_types import ArrangementStep, Palette, Voicing
from .tuning import (
    ROLE_TARGET,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    Note,
)


def _partial_attack(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
    prepared: StepPreparation,
    repeated: bool,
) -> Tuple[bool, bool]:
    """This step's two partial-attack flags: is nothing struck above the thumb, and does
    the melody repeat?

    `bass_only` is the hold `decisions.is_bass_only` decides - a slot the walk invented,
    which the chord's rhythm did not name, over a harmony and a melody that are already
    ringing - and `repeated` is the selector's answer **unless** nothing above the thumb
    is struck. The two flags name opposite halves of one column, and a step carrying both
    would strike the soprano the hold exists to leave alone.
    """
    harmony = normalised_harmony(prepared.chord_name, prepared.harmonized_as)
    bass_only = is_bass_only(
        slot.bass_only,
        chord_attack=context.state.chord_attack,
        holds=melody_is_ringing(
            arrangements, Note(prepared.melody).midi_note(), harmony
        ),
    )
    return bass_only, repeated and not bass_only


def _emit_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
    prepared: StepPreparation,
    chosen: Voicing,
    palette: Palette,
    *,
    role: str,
    repeated: bool,
) -> None:
    """Append the chosen shape as the step, then merge the thumb into it.

    Select first, merge after: the bass is written into the fret vector only once
    the shape has been chosen, so it cannot enter the cost tuple by construction
    rather than by discipline. The request *does* narrow the palette before the ranking -
    a shape whose player cannot reach the requested line's note is not offered - but that
    is a narrowing of what `harmonised_step` hands the tuple, never a candidate carrying a
    thumb and never a criterion reading one.

    The two partial-attack flags are settled by `_partial_attack`, from the step's own
    facts: `bass_only` asks whether anything above the thumb has to be struck at all
    (`decisions.is_bass_only`, which reads what the slot came from and what the last step
    is still sounding), and `repeated` is whatever the selector decided **unless** nothing
    is struck above the thumb - the two flags name opposite halves of one column, and a
    step carrying both would strike the soprano the hold exists to leave alone.
    """
    bass_only, repeated = _partial_attack(
        arrangements, slot, context, prepared, repeated)
    arrangements.append(ArrangementStep(
        chord=prepared.chord_name,
        melody=prepared.melody,
        voicing=chosen,
        palette=palette,
        non_chord_tone=prepared.is_non_chord_tone,
        strategy=prepared.strategy,
        harmonized_as=prepared.harmonized_as,
        original_melody=prepared.original_melody,
        repeated=repeated,
        partial=len(chosen.active_frets()) < 4,
        bar=context.timing.bar,
        beat=context.timing.beat,
        duration=context.timing.duration,
        role=role,
        metric_weight=context.state.weight,
        bass_only=bass_only,
        # A position the chord's rhythm **named** - the stab `--chord-on melody,1and` puts
        # under a held note - is struck even when the shape is unchanged. A slot the
        # skeleton invented, where the tune merely sustains, is not: that is a hold, and
        # `repeated` already covers the tune's own re-articulations.
        chord_attack=context.state.chord_attack,
    ))
    attach_bass(arrangements[-1], slot.bass, arrangements)


def _prepare_or_rescue(
    arrangements: List[ArrangementStep],
    slot: Slot,
    plan: SlotPlan,
    prev_sounding: Optional[ArrangementStep],
) -> Optional[Tuple[StepPreparation, str]]:
    """Prepare the slot's candidates, or answer why the tune cannot sound.

    Returns the preparation and the role the step will state. `None` means the
    step has already been emitted as a rest - by the rescue or by the rest step
    below - and the caller has nothing left to do.

    The order of the three attempts is the contract: play the tune alone, then
    promote the fill, and only then report the step missing.
    """

    context: SlotContext = plan.context
    prepared = prepare_step(
        context.identity.progression, context.identity.index,
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        previous_chord=prev_sounding.chord if prev_sounding is not None else None,
        top_strings=context.neck.top_strings,
        non_chord_tone=context.arrangement.non_chord_tone,
        fret_min=context.neck.fret_min,
        fret_max=context.neck.fret_max,
        grips=plan.slot_grips,
    )
    if prepared is not None:
        return prepared, context.state.role
    assert context.harmony.melody_note is not None
    if rescue_melody_alone(
        arrangements, slot, context,
        top_strings=context.neck.top_strings,
        previous=previous_shape(arrangements),
    ):
        return None
    prepared = _promoted_fill(plan, arrangements)
    if prepared is not None:
        return prepared, ROLE_TARGET
    rest_step(
        arrangements, slot, context,
        sings_here=False,
        silence=(
            SILENCE_OUT_OF_REACH
            if not _grips.get_melody_only_voicings(
                context.harmony.melody_note, prefer=context.neck.top_strings
            )
            else SILENCE_NO_SHAPE
        ),
    )
    return None


def _promoted_fill(
    plan: SlotPlan,
    arrangements: List[ArrangementStep],
) -> Optional[StepPreparation]:
    """Re-prepare a fill that produced nothing as a principal note."""

    context: SlotContext = plan.context
    if not should_promote_fill(
        context.arrangement.texture, context.state.role, True, plan.slot_grips,
        has_thumb=context.arrangement.has_thumb,
        melody_only=context.arrangement.melody_only,
    ):
        return None
    prev_sounding = last_sounding_step(arrangements)
    return prepare_step(
        context.identity.progression, context.identity.index,
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        previous_chord=prev_sounding.chord if prev_sounding is not None else None,
        top_strings=context.neck.top_strings,
        non_chord_tone=context.arrangement.non_chord_tone,
        fret_min=context.neck.fret_min,
        fret_max=context.neck.fret_max,
    )


def _bass_group(
    voicing: Voicing,
    bass_pc: Optional[int],
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]],
) -> Optional[int]:
    """How well `voicing` honours a written slash bass, or `None` without one."""
    if bass_pc is None or slash_bass_cost is None:
        return None
    return slash_bass_cost(voicing.midi_notes(), bass_pc)


@dataclass(frozen=True)
class _Selection:
    """Everything one slot's candidates are ranked against, as one value."""

    candidates: List[Voicing]
    criteria: _cost.SelectionCriteria

    def chosen(self) -> Optional[Voicing]:
        """The shape the engine's own rule prefers, honouring a slash bass first."""
        return select_step_voicing(self.candidates, self.criteria)

    def palette(self, chosen: Voicing, offered: Optional[List[Voicing]] = None) -> Palette:
        """What was on offer besides `chosen`, and why it was not played.

        `offered` is the palette **before** the requested bass note narrowed it. Passing it
        records the shape the ranking preferred there (`Palette.dropped_for_bass`), which
        is the only thing that tells a reader why a shape that is not the ranking's first
        choice is the one on the page. The default - no separate palette - is for the
        callers that never narrow.
        """
        facts = palette_facts(self.candidates, chosen, self.criteria)
        dropped = dropped_for_the_bass(
            offered if offered is not None else self.candidates,
            self.candidates, chosen, self.criteria,
        )
        return facts if dropped is None else replace(facts, dropped_for_bass=dropped)

    def narrower_than(self, demoted: Voicing) -> Optional[Voicing]:
        """A tighter shape inside the budget that the tuple ranks at least as high."""
        turned_away = self.criteria.cost(demoted)
        span = _cost.SPAN_CRITERION
        turned_away_bass = _bass_group(
            demoted, self.criteria.bass_pc, self.criteria.slash_bass_cost
        )

        def would_the_tuple_have_chosen_it(candidate: Voicing) -> bool:
            if _bass_group(
                candidate, self.criteria.bass_pc, self.criteria.slash_bass_cost
            ) != turned_away_bass:
                return False
            cost = self.criteria.cost(candidate)
            return cost[:span] + cost[span + 1:] <= turned_away[:span] + turned_away[span + 1:]

        inside_budget = [
            candidate for candidate in self.candidates
            if candidate.fret_span() < GRIP_MAX_SPAN[demoted.grip]
            and all(
                self.criteria.fret_min <= fret <= self.criteria.fret_max
                for fret in candidate.active_frets()
            )
            and would_the_tuple_have_chosen_it(candidate)
        ]
        if not inside_budget:
            return None
        return select_step_voicing(inside_budget, self.criteria)


def _held_candidates(
    prepared: StepPreparation,
    prev_step: Optional[ArrangementStep],
    harmony: Tuple[Optional[str], Optional[str]],
) -> List[Voicing]:
    """The candidates a held melody may use: the string it is already on."""
    if prev_step is not None and holds_the_shape(
        prev_step, Note(prepared.melody).midi_note(), harmony
    ):
        return hold_the_melody_string(prepared.candidates, prev_step)
    return prepared.candidates


def _selection_for(
    context: SlotContext,
    prepared: StepPreparation,
    candidates: List[Voicing],
    previous: Optional[Voicing],
) -> _Selection:
    """One slot's ranking inputs, from the context and the preparation."""

    substitute = (
        prepared.harmonized_as
        if prepared.harmonized_as is not None
        else prepared.chord_name
    )
    _sub_root, sub_quality = ChordParser.parse_chord_name(substitute)
    if sub_quality is None:
        sub_quality = ChordParser.canonical_quality(prepared.chord_type)
        substitute = prepared.chord_name
    allowed_tones = ChordParser.get_chord_tones(sub_quality, substitute)
    root_pc = _grips.chord_context(prepared.chord_type, prepared.chord_name)[1]
    assert context.harmony.melody_note is not None
    return _Selection(
        candidates=candidates,
        criteria=_cost.SelectionCriteria(
            previous=previous,
            fret_min=context.neck.fret_min,
            fret_max=context.neck.fret_max,
            allowed_tones=allowed_tones,
            root_pc=root_pc,
            melody_pc=context.harmony.melody_note.midi_note() % 12,
            bass_pc=(
                None if context.bass.bass_pcs is None
                else context.bass.bass_pcs.get(context.identity.index)
            ),
            slash_bass_cost=context.bass.slash_bass_cost_for,
        ),
    )


def _candidates_for_the_slot(
    prepared: StepPreparation,
    prev_step: Optional[ArrangementStep],
    harmony: Tuple[Optional[str], Optional[str]],
    slot: Slot,
    arrangements: List[ArrangementStep],
    chord_attack: bool,
) -> Tuple[List[Voicing], List[Voicing]]:
    """The palette the axis offered, and what is left once the bass note has its room.

    Returned as a pair because both are needed: the second is what the ranking chooses
    from, and the first is what tells the reader which shape the request took away
    (`Palette.dropped_for_bass`). See `decisions.leaving_room_for_the_bass`.

    The `bass_only` answer is asked here **as it will be asked when the step is emitted**,
    because it decides what the thumb is measured against: a held step measures it against
    the shape already down, so the placement is one for the whole palette rather than one
    per candidate. Two spellings of the rule would let the narrow drop a shape for a reason
    the merge would not raise.
    """
    offered = _held_candidates(prepared, prev_step, harmony)
    held = melody_is_ringing(arrangements, Note(prepared.melody).midi_note(), harmony)
    return offered, leaving_room_for_the_bass(
        offered, slot.bass, arrangements,
        bass_only=is_bass_only(
            slot.bass_only, chord_attack=chord_attack, holds=held
        ),
    )


def harmonised_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    plan: SlotPlan,
) -> None:
    """The melody-bearing route: pin the tune, and voice the chord under it.

    Reached when the guitar *sings* the slot - or when every other route declined it - so a
    note is pinned by the `assert` below. `prepare_step` supplies the candidates,
    `voicing_cost` picks among them, and the last resort before silence is the melody alone.
    """

    context: SlotContext = plan.context
    assert context.harmony.note_str is not None and context.harmony.melody_note is not None
    prev_sounding = last_sounding_step(arrangements)
    prepared_and_role = _prepare_or_rescue(arrangements, slot, plan, prev_sounding)
    if prepared_and_role is None:
        return
    prepared, role = prepared_and_role

    harmony = normalised_harmony(prepared.chord_name, prepared.harmonized_as)
    prev_step = arrangements[-1] if arrangements else None
    # The palette is what is left once every shape the thumb cannot reach the requested
    # bass note under is taken out: a narrowing of what the axis offered, ranked by the
    # same tuple, so the harmony makes room for the line instead of dropping its note.
    offered, candidates = _candidates_for_the_slot(
        prepared, prev_step, harmony, slot, arrangements, context.state.chord_attack)

    selection = _selection_for(
        context, prepared, candidates,
        prev_sounding.voicing if prev_sounding is not None else None)
    best_voicing = selection.chosen()
    assert best_voicing is not None
    palette = selection.palette(best_voicing, offered)

    if should_demote_to_melody_alone(best_voicing, role):
        narrower = selection.narrower_than(best_voicing)
        if narrower is not None:
            best_voicing = narrower
            palette = selection.palette(best_voicing, offered)
        elif demoted_to_melody_alone(
            arrangements, slot, replace(context, state=replace(context.state, role=role)),
            top_strings=plan.context.neck.top_strings,
            previous=selection.criteria.previous,
            best_voicing=best_voicing,
            palette=palette,
        ):
            return
    repeated = is_repeated_step(prev_step, best_voicing, harmony)
    _emit_step(
        arrangements, slot, context, prepared, best_voicing, palette,
        role=role, repeated=repeated,
    )
