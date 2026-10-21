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
    hold_the_melody_string,
    holds_the_shape,
    is_bass_only,
    is_repeated_step,
    select_step_voicing,
    should_demote_to_melody_alone,
    should_promote_fill,
)
from .grip_tables import GRIP_MAX_SPAN
from .melody_alone import demoted_to_melody_alone, rescue_melody_alone
from .routes import last_sounding_step, previous_shape, rest_step
from .slot_plan import SlotPlan
from .step_prepare import StepPreparation, prepare_step
from .tuning import (
    ROLE_TARGET,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    ArrangementStep,
    Note,
    Palette,
    Voicing,
)


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
    rather than by discipline.
    """
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
        bass_only=is_bass_only(slot.bass_only, role),
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
    inputs = plan.inputs
    prepared = prepare_step(
        context.identity.progression, context.identity.index,
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        previous_chord=prev_sounding.chord if prev_sounding is not None else None,
        top_strings=inputs.top_strings,
        non_chord_tone=context.non_chord_tone,
        fret_min=context.fret_min,
        fret_max=context.fret_max,
        grips=plan.slot_grips,
    )
    if prepared is not None:
        return prepared, context.state.role
    assert context.harmony.melody_note is not None
    if rescue_melody_alone(
        arrangements, slot, context,
        top_strings=inputs.top_strings, previous=previous_shape(arrangements),
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
                context.harmony.melody_note, prefer=inputs.top_strings
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
    inputs = plan.inputs
    if not should_promote_fill(
        context.texture, context.state.role, True, plan.slot_grips,
        has_thumb=context.has_thumb,
        melody_only=inputs.melody_only,
    ):
        return None
    prev_sounding = last_sounding_step(arrangements)
    return prepare_step(
        context.identity.progression, context.identity.index,
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        previous_chord=prev_sounding.chord if prev_sounding is not None else None,
        top_strings=inputs.top_strings,
        non_chord_tone=context.non_chord_tone,
        fret_min=context.fret_min,
        fret_max=context.fret_max,
    )


def _lost_to_the_bass_partition(
    chosen: Voicing,
    alternative: Voicing,
    bass_pc: Optional[int],
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]],
) -> bool:
    """Whether the slash-bass partition would have dropped `alternative`."""
    if bass_pc is None or slash_bass_cost is None:
        return False
    here = slash_bass_cost(chosen.midi_notes(), bass_pc)
    there = slash_bass_cost(alternative.midi_notes(), bass_pc)
    return here != there


def _palette_facts(
    candidates: List[Voicing],
    chosen: Voicing,
    criteria: _cost.SelectionCriteria,
) -> Palette:
    """What was on offer besides `chosen`, and the criterion that ranked it lower."""
    def cost(voicing: Voicing) -> _cost.VoicingScore:
        return criteria.cost(voicing)

    available = max(len(candidate.active_frets()) for candidate in candidates)
    inside_window = any(
        all(
            criteria.fret_min <= fret <= criteria.fret_max
            for fret in candidate.active_frets()
        )
        for candidate in candidates
    )
    chosen_voices = len(chosen.active_frets())
    fuller = [c for c in candidates if len(c.active_frets()) > chosen_voices]
    if not fuller:
        return Palette(available=available, inside_window=inside_window)
    alternative = min(fuller, key=cost)
    decided_by = _cost.decisive_criterion(cost(chosen), cost(alternative))
    if _lost_to_the_bass_partition(
        chosen, alternative, criteria.bass_pc, criteria.slash_bass_cost
    ):
        decided_by = _cost.PARTITION_CRITERION
    return Palette(
        available=available,
        alternative=alternative,
        decided_by=decided_by,
        inside_window=inside_window,
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

    def palette(self, chosen: Voicing) -> Palette:
        """What was on offer besides `chosen`, and the criterion that ranked it lower."""
        return _palette_facts(self.candidates, chosen, self.criteria)

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
            fret_min=context.fret_min,
            fret_max=context.fret_max,
            allowed_tones=allowed_tones,
            root_pc=root_pc,
            melody_pc=context.harmony.melody_note.midi_note() % 12,
            bass_pc=(
                None if context.bass_pcs is None
                else context.bass_pcs.get(context.identity.index)
            ),
            slash_bass_cost=context.slash_bass_cost_for,
        ),
    )


def harmonised_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    plan: SlotPlan,
) -> None:
    """The melody-bearing route: pin the tune, and voice the chord under it.

    Reached when the guitar *sings* the slot - or when every other route declined
    it - so a note is pinned by the `assert` below. This is the route the whole
    library is built around: `prepare_step` supplies the candidates,
    `voicing_cost` picks among them, and the last resort before silence is the
    melody alone.
    """

    context: SlotContext = plan.context
    assert context.harmony.note_str is not None and context.harmony.melody_note is not None
    prev_sounding = last_sounding_step(arrangements)
    prepared_and_role = _prepare_or_rescue(
        arrangements, slot, plan, prev_sounding,
    )
    if prepared_and_role is None:
        return
    prepared, role = prepared_and_role

    harmony = normalised_harmony(prepared.chord_name, prepared.harmonized_as)
    prev_step = arrangements[-1] if arrangements else None
    candidates = _held_candidates(prepared, prev_step, harmony)

    selection = _selection_for(
        context, prepared, candidates,
        prev_sounding.voicing if prev_sounding is not None else None,
    )
    best_voicing = selection.chosen()
    assert best_voicing is not None
    palette = selection.palette(best_voicing)

    if should_demote_to_melody_alone(best_voicing, role):
        narrower = selection.narrower_than(best_voicing)
        if narrower is not None:
            best_voicing = narrower
            palette = selection.palette(best_voicing)
        elif demoted_to_melody_alone(
            arrangements, slot, replace(context, state=replace(context.state, role=role)),
            top_strings=plan.inputs.top_strings,
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
