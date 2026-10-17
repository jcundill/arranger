"""The step loop: one progression in, one arrangement out.

`arrange_progression` is the entry point and `prepare_step` its one-step
counterpart. Between them they turn `(melody, quality, name)` triples into
`ArrangementStep`s, dispatching each slot to one of five routes - a rest, a
texture fill, a no-chord melody-alone step, a comping shape, or a harmonised
melody step - and merging the walking bass in afterwards. The first four routes
are in `routes`; the lone-note positions they choose are in `melody_alone`; this
module owns the loop, the knobs and the harmonised route.

`VoiceLeadingEngine` is a facade of one-line delegates onto the step loop. There
is no state to move, so this module imports `grips`, `cost`, `chords` and the
rest directly and does not import `steps` at all.
`slots.arrange_slots` delegates through the class, so the imported-head path and the
hand-built one still run one loop rather than two.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Container, List, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from . import cost as _cost
from . import grips as _grips
from .bass import (
    Slot,
)
from .bass_merge import attach_bass, next_resolution_melody
from .bass_rules import (
    BASS_STYLE_AUTO,
)
from .chords import (
    ChordParser,
    normalised_harmony,
    resolve_substitute_harmony,
)
from .context import SlotContext
from .decisions import (
    MELODY_ALONE_NO_CHORD,
    MELODY_ALONE_REST,
    MELODY_ALONE_TEXTURE,
    SLASH_BASS_SATISFIED,
    hold_the_melody_string,
    holds_the_shape,
    is_bass_only,
    is_repeated_step,
    select_step_voicing,
    should_demote_to_melody_alone,
    should_promote_fill,
)
from .grid import GRID_DEFAULT
from .grip_tables import (
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
)
from .grips import (
    MELODY_STRING_CHOICES_FULL,
)
from .harmony import (
    HARMONY_AUTO,
)
from .melody_alone import demoted_to_melody_alone, rescue_melody_alone
from .options import ArrangeOptions
from .parts import (
    PARTS_AUTO,
)
from .resolution import resolve_knobs, resolve_policies
from .routes import (
    comping_step,
    last_sounding_step,
    no_chord_step,
    rest_step,
    texture_fill_step,
)
from .slot_plan import Carried, SlotInputs, SlotPlan, slot_state
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    ROLE_TARGET,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    ArrangementStep,
    Palette,
    Voicing,
    note_name,
)

__all__ = [
    "StepPreparation",
    "arrange_progression",
    "prepare_step",
]


@dataclass
class StepPreparation:
    """One step's voicing candidates, plus the bookkeeping to report the step.

    Returned by `VoiceLeadingEngine.prepare_step` so a caller that needs extra
    per-step control - the corpus loader honours a slash bass and attaches the
    slot's timing - can choose from these candidates using the engine's own rule
    rather than re-deriving the voicing itself.

    That distinction is load-bearing: a caller that builds its own candidates and
    calls `best_voicing` directly silently skips the non-chord-tone strategies,
    the selector's tone-purity criterion (because `allowed_tones` defaults to None)
    and the octave-down rescue. `chord_type`
    and `chord_name` stay the *written* chord even when `harmonized_as` names a
    substitute, because `allowed_tones` is built from the written
    chord and changing that would move the library's published output.
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
    `strategy` and `harmonized_as` say what the non-chord-tone rule did, if anything.
    """

    candidates: List[Voicing]
    melody: Note
    original_melody: Optional[str]
    strategy: Optional[str] = None
    harmonized_as: Optional[str] = None


def _voices_for(
    melody_note: Note,
    written: str,
    chord_type: str,
    name: str,
    window: _SearchWindow,
) -> _Voiced:
    """The candidates for the note, after the octave-down rescue.

    Chord-tone match first, quality-only fallback second, across every allowed
    soprano string and every grip family.

    A melody whose best position sits outside the neck window is re-voiced an octave
    down on the B string. The written pitch is kept in `original_melody`. Decided
    before the non-chord-tone strategies run, so a substituted chord is voiced at the
    transposed pitch too rather than snapping back up.

    The guard requires candidates to exist: this repositions a voicing that is
    playable but sits too high. A melody unreachable at the written pitch (C6, fret
    20 - past the end of the board) is left alone, because there is no shape to move
    down and respelling it would hide the real problem.
    """
    candidates = _grips.get_all_grip_voicings(
        melody_note, chord_type, chord_name=name,
        top_strings=window.top_strings, grips=window.grips,
    )
    voiced = _Voiced(candidates=candidates, melody=melody_note, original_melody=None)
    here = _cost.window_penalty(candidates, window.fret_min, window.fret_max)
    if not candidates or here <= 0:
        return voiced
    octave_down = _grips.get_octave_down_candidates(
        melody_note, chord_type, chord_name=name,
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
    chord_type: str,
    name: str,
    strategy: str,
    previous: Optional[Voicing],
    previous_chord: Optional[str],
    window: _SearchWindow,
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
) -> _Voiced:
    """Re-voice a melody that is not a chord tone, and record what was done.

    Strategy 3 first: holding the shape moves less than any re-voicing. Strategies 1
    and 2 then reharmonise the note as a genuine chord tone.

    When neither settles anything the strategy is still **recorded**, because the line
    has to name it: "non-chord tone" alone cannot tell a substitution that failed from
    one that was never attempted. What distinguishes the two is `harmonized_as`, which
    stays None here - not the strategy field.
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
        chord_type,
        name,
        strategy,
        next_melody=next_resolution_melody(progression, index),
    )
    if substitute is not None:
        substitute_quality, substitute_name = substitute[0], substitute[1]
        substituted = _grips.get_all_grip_voicings(
            voiced.melody,
            substitute_quality,
            chord_name=substitute_name,
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
    progression: Sequence[Tuple[Optional[str], str, str]],
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
    non-chord-tone strategies. `arrange_progression` selects with
    `select_step_voicing` straight afterwards, and the corpus loader selects the
    same way after honouring a slash bass, so the two cannot drift.

    Returns None when the step has no voicing at all. `previous` is only read
    by the `sustain` strategy, and `previous_chord` is what that strategy
    reports as `harmonized_as`.

    """
    note_str, chord_type, name = progression[index]
    if note_str is None:
        # No melody to pin. `arrange_progression` skips such a slot before it can
        # reach here - every singing route needs a note, and the comping route
        # never calls this - so this is the widened triple type's honest answer
        # rather than a `Note(None)` waiting for a caller that lies.
        return None
    melody_note = Note(note_str)
    window = _SearchWindow(
        top_strings=top_strings, grips=grips,
        fret_min=fret_min, fret_max=fret_max,
    )
    voiced = _voices_for(melody_note, note_str, chord_type, name, window)
    is_non_chord_tone = (
        ChordParser.canonical_quality(chord_type) in ChordParser.CHORD_TONES_FROM_ROOT
        and not _chords.is_chord_tone(melody_note, chord_type, name)
    )
    if is_non_chord_tone:
        voiced = _apply_non_chord_tone(
            voiced,
            chord_type=chord_type,
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
        chord_type=chord_type,
        chord_name=name,
        is_non_chord_tone=is_non_chord_tone,
        strategy=voiced.strategy,
        harmonized_as=voiced.harmonized_as,
    )


def _previous_shape(arrangements: List[ArrangementStep]) -> Optional[Voicing]:
    """The voicing of the last sounding step, or None - what a shape is scored against.

    The same answer `last_sounding_step` gives, in the form the selector wants, so a
    lone note and a chord lead from one shape rather than two lookbacks that could
    disagree about which step the hand was holding.
    """
    previous = last_sounding_step(arrangements)
    return previous.voicing if previous is not None else None


def _promoted_fill(
    plan: SlotPlan,
    arrangements: List[ArrangementStep],
) -> Optional[StepPreparation]:
    """Re-prepare a fill that produced nothing as a principal note.

    A fill slot with nothing thin to play must not lose the chord of the tune -
    the whole point of the texture is a lighter *texture*, never a missing
    harmony. Same argument as `NECK_FRET_MIN` being a penalty and not a filter.
    `decisions.should_promote_fill` decides whether this step gets the retry.

    The retry is prepared against the **whole** search space, not the narrower
    palette the fill's role was given: that palette is exactly what produced
    nothing, so asking it again would repeat the failure.

    Returns the promoted preparation, or **None** when the texture does not ask
    for the retry or the retry found nothing either - the two cases the caller
    answers the same way, by reporting the step as skipped.
    """
    context = plan.context
    inputs = plan.inputs
    if not should_promote_fill(
        context.texture, context.role, True, plan.slot_grips,
        has_thumb=context.has_thumb,
        melody_only=inputs.melody_only,
    ):
        return None
    prev_sounding = last_sounding_step(arrangements)
    return prepare_step(
        context.progression, context.index,
        # The last *sounding* shape, not the step before this one: a silent
        # position is a hole in the tab rather than a shape the hand held.
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
    """Whether the slash-bass partition would have dropped `alternative` before the tuple.

    The partition is `decisions.select_step_voicing`'s, applied only when some candidate
    can honour the written bass at all (`SLASH_BASS_SATISFIED`) - so this is False for a
    chord whose bass is unachievable, where the tuple decides alone and the criterion it
    reports is the whole story.
    """
    if bass_pc is None or slash_bass_cost is None:
        return False
    here = slash_bass_cost(chosen.midi_notes(), bass_pc)
    there = slash_bass_cost(alternative.midi_notes(), bass_pc)
    return here <= SLASH_BASS_SATISFIED and there > here


def _palette_facts(
    candidates: Sequence[Voicing],
    chosen: Voicing,
    criteria: _cost.SelectionCriteria,
) -> Palette:
    """What the palette offered besides the shape it chose, recorded for the renderer.

    `available` is the most voices any candidate in the palette states, which is the
    number that separates a palette's limit from a decision. The alternative is the best
    candidate stating **more** voices than the chosen shape - the chord that is not being
    played, which is the question a reader actually asks - and `decided_by` is the element
    of `cost.voicing_cost` that separated the two.

    That element is never the voice-count one: a fuller shape cannot lose on how many
    voices it has. So the answer is always a wrong note, the neck window or the hand's
    travel, which is exactly what a reader counting strings cannot see for themselves -
    unless the shape never reached the tuple at all, which is the slash-bass partition.

    The costs are the ones the selection used, from the same arguments, so the criterion
    reported here is the criterion that decided there rather than a second opinion.
    """

    def cost(voicing: Voicing) -> Tuple[float, ...]:
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
        # The partition runs *before* the tuple, so the two cost tuples need not differ at
        # all: what removed this shape is the bass note it does not sound.
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
    """How well `voicing` honours a written slash bass, or `None` without one.

    `decisions.select_step_voicing` partitions its candidates on exactly this number
    before it consults `voicing_cost` at all, so a caller comparing two shapes "on the
    tuple" has to compare them in the same group first - otherwise it can prefer a
    shape that drops the written bass for one that sounds it, which is a re-ranking
    across the rule that outranks the whole tuple.
    """
    if bass_pc is None or slash_bass_cost is None:
        return None
    return slash_bass_cost(voicing.midi_notes(), bass_pc)


def _prepare_or_rescue(
    arrangements: List[ArrangementStep],
    slot: Slot,
    plan: SlotPlan,
    prev_sounding: Optional[ArrangementStep],
) -> Optional[Tuple[StepPreparation, str]]:
    """Prepare the slot's candidates, or answer why the tune cannot sound.

    Returns the preparation **and the role the step will state**, because a fill that
    is promoted to a principal note is a target: the retry exists to keep the chord,
    so the step must not carry on describing itself as a fill. `None` means the step
    has already been emitted as a rest - by the rescue or by the rest step below - and
    the caller has nothing left to do.

    The order of the three attempts is the contract: play the tune alone, then promote
    the fill, and only then report the step missing. See `rescue_melody_alone` and
    `_promoted_fill`.
    """
    context = plan.context
    inputs = plan.inputs
    prepared = prepare_step(
        context.progression, context.index,
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        previous_chord=prev_sounding.chord if prev_sounding is not None else None,
        top_strings=inputs.top_strings,
        non_chord_tone=context.non_chord_tone,
        fret_min=context.fret_min,
        fret_max=context.fret_max,
        grips=plan.slot_grips,
    )
    if prepared is not None:
        return prepared, context.role
    assert context.melody_note is not None
    if rescue_melody_alone(
        arrangements, slot, context,
        top_strings=inputs.top_strings, previous=_previous_shape(arrangements),
    ):
        return None
    prepared = _promoted_fill(plan, arrangements)
    if prepared is not None:
        return prepared, ROLE_TARGET
    # Reached only when the melody **cannot be played at all** - the rescue above has
    # already been tried, and answered None because no string reaches the note (below
    # the library's G3 floor, or past the end of the board).
    #
    # The palette is named because it is the usual cause and the caller is the only
    # one who can change it, and the message says the step is *skipped* because that
    # is what happens to the note. Naming a family the caller never asked for, or
    # wording it like a fallback that had happened, would both misdescribe the step.
    # The reason is told apart at the source: no string reaches the written pitch at
    # all (`out_of_reach`) versus a reachable melody under a chord nothing could
    # voice (`no_shape`). The rescue above asked the same question, so the answer is
    # read back rather than re-derived from the clause's own words.
    rest_step(
        arrangements, slot, context,
        sings_here=False,
        silence=(
            SILENCE_OUT_OF_REACH
            if not _grips.get_melody_only_voicings(
                context.melody_note, prefer=inputs.top_strings
            )
            else SILENCE_NO_SHAPE
        ),
    )
    return None


@dataclass(frozen=True)
class _Selection:
    """Everything one slot's candidates are ranked against, as one value.

    `select_step_voicing`, the palette record and the demotion's own filter all ask
    these same questions of the same slot, and their answers have to agree: a palette
    computed from different arguments than the selection would be a second opinion
    rather than the criterion that decided. Grouping them makes that agreement
    structural instead of a convention every call site has to repeat.
    """

    candidates: List[Voicing]
    criteria: _cost.SelectionCriteria

    def chosen(self) -> Optional[Voicing]:
        """The shape the engine's own rule prefers, honouring a slash bass first."""
        return select_step_voicing(self.candidates, self.criteria)

    def palette(self, chosen: Voicing) -> Palette:
        """What was on offer besides `chosen`, and the criterion that ranked it lower.

        Asked again whenever a rule replaces the chosen shape, so the record is always
        about the shape the step carries - a record about any other shape is a second
        source for one fact, and the wrong one.
        """
        return _palette_facts(self.candidates, chosen, self.criteria)

    def narrower_than(self, demoted: Voicing) -> Optional[Voicing]:
        """A tighter shape inside the budget that the tuple ranks at least as high.

        The demotion documented in `decisions.should_demote_to_melody_alone` exists
        because the *palette* offered nothing inside the span budget. That premise is
        checkable here, and checking it is what stops the demotion from throwing away
        a chord that a narrower candidate could have kept.

        Two tests make this a fallback rather than a re-ranking, and both are
        load-bearing:

        - **The narrower shape must tie with the demoted one on every criterion that
          outranks span.** The comparison is the tuple's own prefix rather than a
          hand-written list. Without it the filter silently *re-ranks*: on `Am7`
          under D5 the palette also holds a span-0 shape sounding F4, which the tuple
          puts below the span-5 shape on criterion 0 (a note outside the chord) - so
          re-selecting within the budget would trade a pure five-fret reach for an
          impure chord, exactly the trade the demotion says the tuple would never
          make. Measured on the committed heads: without the span tie, 23 `uniform`
          steps move; with it, `uniform` is byte-identical and only the textures
          whose palette grew move.
        - **Inside the neck window as well.** A candidate that is merely tighter
          while sitting at fret 14 is not the alternative the rule was written for:
          the demotion demotes a shape that is *unplayable*, and trading it for one
          out of position is a different bad trade. Measured on the committed heads,
          both halves earn their place: without the span test 30 `targets` steps lose
          three notes each, and without the window test the A-7 of `MAJOR_CADENCE`
          trades its pinned melody-alone step for a shape at fret 14
          (`docs/history/fingering.md` §4.4's ban is why nothing else fits there).

        The comparison drops the span element from the tuple: everything the ranking
        says *except* the one criterion the demotion exists for. Keeping it would let
        the re-selection trade position, inner-voice movement or the written bass for
        span - a re-ranking after all, measured at two `heres_that_rainy_day` steps
        whose `Bb7/F` slots would come back at a worse fret for a tighter hand.

        The **partition** is not part of the tuple and it outranks all of it, so a
        narrower shape may only replace the demoted one from the same group: a shape
        that drops the written bass for a tighter hand is the same bad trade.
        """
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
    """The candidates a held melody may use: the string it is already on.

    `harmony` is the normalised `(root, quality)` pair the caller also gives
    `is_repeated_step`, so "the note did not move" cannot mean two things.

    A melody that did not move is a **hold**: the previous shape is still ringing, so
    only the harmony under it changes. The candidates are narrowed before the selector
    sees them, which is a filter over a list rather than a new cost criterion -
    ranking a hold above a jump cannot stop the jump, because both are legal shapes,
    and `span` outranks position in the tuple precisely so the hand stays put. The
    rule, and the reason it comes back empty-handed rather than starving a thin
    palette, is `decisions.hold_the_melody_string`.
    """
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
    """One slot's ranking inputs, from the context and the preparation.

    The tones are those of the chord **actually sounding**, which is `harmonized_as`
    where a non-chord-tone strategy substituted one. Scoring the substitute against
    the written chord asked the wrong question: a Bdim7 voicing under a written Cmaj7
    is three foreign notes and every candidate alike, so criterion 0 could not
    separate them and `missing` then picked a three-note shell over the complete
    Bdim7 drop-2 that was generated and correct. The step sounded D4-Ab4-D5 - two
    tones of Bdim7 rather than four - under a strategy whose whole purpose is to
    state the substituted chord.

    `harmonized_as` is a chord *name* ("Bdim7"), not a quality, so it is parsed
    rather than passed to `canonical_quality` directly: that returns the whole name
    unchanged for an unrecognised spelling, and `get_chord_tones` then yields an
    empty set, which silently switches the criterion off rather than asking it the
    right question.

    The root enables the bass-function tie-break in `voicing_cost`; it is None for a
    chord whose name cannot be parsed, which leaves that criterion unasked rather
    than guessing a bass.
    """
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
    assert context.melody_note is not None
    # The melody is the caller's note and is never rewritten, so when it lies outside
    # the chord every candidate is impure on it. Scoring it separately lets a shape
    # that adds no *other* wrong note reach zero - see `cost.voicing_cost`, where
    # counting rather than flagging makes the difference between one wrong note and
    # four.
    return _Selection(
        candidates=candidates,
        criteria=_cost.SelectionCriteria(
            previous=previous,
            fret_min=context.fret_min,
            fret_max=context.fret_max,
            allowed_tones=allowed_tones,
            root_pc=root_pc,
            melody_pc=context.melody_note.midi_note() % 12,
            bass_pc=(
                None if context.bass_pcs is None
                else context.bass_pcs.get(context.index)
            ),
            slash_bass_cost=context.slash_bass_cost_for,
        ),
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

    Select first, merge after: the bass is written into the fret vector only once the
    shape has been chosen, so it cannot enter the cost tuple by construction rather
    than by discipline.
    """
    arrangements.append(ArrangementStep(
        chord=prepared.chord_name,
        # The transposed pitch when the step was moved down an octave, so the
        # step reports what actually sounds; original_melody keeps the written one.
        melody=prepared.melody,
        voicing=chosen,
        palette=palette,
        non_chord_tone=prepared.is_non_chord_tone,
        strategy=prepared.strategy,
        harmonized_as=prepared.harmonized_as,
        original_melody=prepared.original_melody,
        repeated=repeated,
        # A shell or a duo leaves part of the chord unsounded, so the chord name
        # printed above the step describes the harmony rather than every note in
        # it. The renderers annotate this.
        #
        # Counted over the **upper voices**: the thumb is merged after this, so
        # a shell plus a bass note is still a shell and stays annotated
        # "(shell - 3rd & 7th, partial)". The merge happens below, which is what
        # makes that true by ordering rather than by a second count.
        partial=len(chosen.active_frets()) < 4,
        bar=context.bar,
        beat=context.beat,
        duration=context.duration,
        role=role,
        metric_weight=context.weight,
        # Decision B: this slot exists for the thumb. The upper voices are held
        # across it by the renderers rather than re-struck, and the melody is
        # not re-attacked - the opposite of `repeated`, and never set together.
        #
        # `is_bass_only` and not the slot's own flag: the bass grid invented
        # this beat, but a strong beat the melody moves onto is a **target**,
        # and a target states the harmony rather than holding it. Passing the
        # slot's flag straight through marked such a step both bass-only and a
        # target, which silenced the chord this line had just voiced.
        bass_only=is_bass_only(slot.bass_only, role),
    ))
    attach_bass(arrangements[-1], slot.bass, arrangements)


def _harmonised_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    plan: SlotPlan,
) -> None:
    """The melody-bearing route: pin the tune, and voice the chord under it.

    Reached when the guitar *sings* the slot - or when every other route declined
    it - so a note is pinned by the `assert` below. This is the route the whole
    library is built around: `prepare_step` supplies the candidates, `voicing_cost`
    picks among them, and the last resort before silence is the melody alone.
    """
    context = plan.context
    assert context.note_str is not None and context.melody_note is not None
    # The previous shape is the last *sounding* one: a silent position between here
    # and the previous chord is a hole in the tab, not a shape the hand held - see
    # `last_sounding_step`.
    prev_sounding = last_sounding_step(arrangements)
    # Everything up to choosing a shape is shared with the corpus loader, which needs
    # the same candidates but honours a slash bass first. See `prepare_step`.
    prepared_and_role = _prepare_or_rescue(
        arrangements, slot, plan, prev_sounding,
    )
    if prepared_and_role is None:
        return
    prepared, role = prepared_and_role

    # `harmony` is computed once here and used for the `repeated` flag below, so "the
    # note did not move" cannot mean two different things in one step.
    harmony = normalised_harmony(prepared.chord_name, prepared.harmonized_as)
    # The step a hold is about: `arrangements[-1]`, because what matters is what is
    # *ringing*, and a rest stops the ringing, whether it is the grid's or a position
    # the guitar declined.
    prev_step = arrangements[-1] if arrangements else None
    candidates = _held_candidates(prepared, prev_step, harmony)

    # The whole selection rule lives in voicing_cost. The first chord has no previous
    # shape to lead from, so it falls back to "somewhere comfortable on the neck";
    # every later chord is scored against the one before it, which is what keeps the
    # hand from jumping and lets a melody hold its place by changing strings.
    #
    # The shape the selector leads *from* is the last sounding one, not the step
    # before this one: a silent position is a hole in the tab rather than a shape the
    # hand held (`last_sounding_step`). `prev_step` above stays `arrangements[-1]`,
    # because a hold is about what is *ringing* - and a rest stops the ringing,
    # whether it is the grid's or a position the guitar declined.
    selection = _selection_for(
        context,
        prepared,
        candidates,
        prev_sounding.voicing if prev_sounding is not None else None,
    )
    best_voicing = selection.chosen()
    # `candidates` is non-empty here (the step is skipped otherwise), so this cannot
    # fire. Written as an assertion rather than left to Optional narrowing at every
    # use below.
    assert best_voicing is not None
    palette = selection.palette(best_voicing)

    # A complete chord at the very top of the span budget is demoted to the melody
    # alone. Why that is a fallback rather than a re-ranking, and why a narrower shape
    # may replace it only when it ties on every criterion that outranks span, is
    # documented in `decisions.should_demote_to_melody_alone` and in
    # `_Selection.narrower_than`.
    if should_demote_to_melody_alone(best_voicing, role):
        narrower = selection.narrower_than(best_voicing)
        if narrower is not None:
            best_voicing = narrower
            palette = selection.palette(best_voicing)
        elif demoted_to_melody_alone(
            arrangements, slot, replace(context, role=role),
            top_strings=plan.inputs.top_strings,
            previous=selection.criteria.previous,
            best_voicing=best_voicing,
            palette=palette,
        ):
            return
    # A repeated melody is a hold, so the renderers strike the soprano alone and
    # keep the inner voices ringing - and the shape was chosen on the string that
    # makes that true. The rule - the harmony-change case that is not a hold, and
    # the string clause - is decisions.is_repeated_step.
    repeated = is_repeated_step(prev_step, best_voicing, harmony)
    _emit_step(
        arrangements, slot, context, prepared, best_voicing, palette,
        role=role, repeated=repeated,
    )


def _loop_slots(
    progression: Sequence[Tuple[Optional[str], str, str]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    slots: Optional[List[Slot]],
) -> List[Slot]:
    """One slot per triple, carrying that triple's own timing or None for an unplaced one.

    The walk's union wins when it exists, because its extra beats are the steps the
    thumb needs. Otherwise the list is read defensively - a short `timings` leaves
    the trailing steps unlocated - and, importantly, tolerating a *present but empty*
    entry: the corpus normalises its unplaced slots to `(None, None, None)`, so
    `float(beat)` here has to cope with None or the head path raises the moment it is
    allowed to delegate. That is the fourth time the two paths' differing timing
    types have cost something, and the first time it was a crash rather than a
    signature that would not typecheck.
    """
    if slots is not None:
        return slots

    def timing(index: int) -> Tuple[Optional[int], Optional[float], Optional[float]]:
        if timings is None or index >= len(timings):
            return (None, None, None)
        bar, beat, duration = timings[index]
        return (bar, None if beat is None else float(beat), duration)

    return [
        Slot(index=index, bar=bar, beat=beat, duration=duration)
        for index, (bar, beat, duration) in enumerate(
            timing(i) for i in range(len(progression))
        )
    ]


def _route_slot(
    arrangements: List[ArrangementStep],
    slot: Slot,
    plan: SlotPlan,
) -> None:
    """Send one planned slot to exactly one route, which appends its step.

    The order is the contract: rest, fill, `NC`, comping, melody-bearing. A fill that
    cannot be filled falls through rather than returning, because the chord of the
    tune must not be lost to a texture - `texture_fill_step`'s own answer.

    The route reads the plan's `context` and `inputs`, so the slot facts and the
    arrangement facts keep the values the plan decided.
    """
    context = plan.context
    inputs = plan.inputs
    if plan.melody_alone == MELODY_ALONE_REST:
        rest_step(
            arrangements, slot, context,
            sings_here=plan.sings_here, silence=plan.silence,
        )
        return
    if plan.melody_alone == MELODY_ALONE_TEXTURE:
        if texture_fill_step(
            arrangements, slot, context,
            top_strings=inputs.top_strings,
            previous=_previous_shape(arrangements),
        ):
            return
    if plan.melody_alone == MELODY_ALONE_NO_CHORD:
        no_chord_step(
            arrangements, slot, context,
            top_strings=inputs.top_strings,
            previous=_previous_shape(arrangements),
        )
        return
    # --- The comping route: the guitar harmonises, somebody else sings ---
    # See `comping_step`: taken before `prepare_step` because there is no melody for
    # the guitar here, and only after the NC and melody-alone branches, which are the
    # cases with no harmony to state.
    if not plan.sings_here and not inputs.melody_only:
        if comping_step(
            arrangements, slot, context,
            chord_type=context.chord_type,
            melody_onsets=inputs.melody_onsets,
            parts=inputs.parts,
            harmony_family=inputs.harmony_family,
        ):
            return

    # Every melody-bearing route below pins a note, and a slot with none has left the
    # loop by now: the guard at the top refuses one the guitar is asked to sing, and
    # the comping block above always steps or returns.
    _harmonised_step(arrangements, slot, plan)


def arrange_progression(
    progression: Sequence[Tuple[Optional[str], str, str]],
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    non_chord_tone: str = "extension",
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    # `Sequence` and Optional *bar* and *beat*, not `List[Tuple[int, float, ...]]`:
    # a slot a caller could not place is `(None, None, None)`, so an entry point may
    # hold either shape. `float(beat)` below must therefore not assume a non-None
    # beat.
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None,
    texture: str = "uniform",
    bass: str = BASS_STYLE_AUTO,
    parts: str = PARTS_AUTO,
    harmony: str = HARMONY_AUTO,
    grid: str = GRID_DEFAULT,
    beats_per_bar: int = 4,
    # The metre's denominator, read by the walking bass's melody timeline alone: a
    # slot's `duration` is in whole notes and one whole note is `beat_type` beats
    # (`4 / beat_type` quarters to the beat). Defaulted rather than required, so a
    # hand-built progression - which has no notated metre to state - keeps the
    # arithmetic it had.
    beat_type: int = 4,
    # The progression indexes whose melody note articulates, for the §9.2
    # reharmonise rule on the comping route (§9.3 step C). `None` means every slot
    # is an onset - the correct answer for a hand-built progression with no
    # timeline, and what keeps a bare `arrange_progression(..., melody="alto,tenor")`
    # honouring `--non-chord-tone`. See `ArrangeOptions.melody_onsets`.
    melody_onsets: Optional[Container[int]] = None,
    options: Optional[ArrangeOptions] = None,
) -> List[ArrangementStep]:
    """
    Takes a progression of (Melody Note, Chord Quality, Name) tuples
    and computes the optimal voice-led arrangement.

    top_strings selects which strings may carry the melody (see
    MELODY_STRING_CHOICES_FULL). The default allows the high E, the B *and* the G
    string, so a melody can hold its place on the neck by changing strings rather
    than by moving the hand, and a melody below the high E string's open pitch is
    still arranged rather than skipped.

    fret_min and fret_max bound the comfortable neck window the selector aims for
    (frets 2-13 by default). They are a strong preference, not a constraint: a step
    with no voicing inside the window is still played, just outside it, because
    losing a chord of the tune is worse than being a fret out of position.

    `top_strings=MELODY_STRING_CHOICES` reproduces this library's original,
    four-string-drop-2-only output exactly, which is what a caller wants when they
    need a known arrangement rather than the best one.

    non_chord_tone selects what happens when a melody note is not a chord tone
    (one of NON_CHORD_TONE_STRATEGIES):
      'extension'  - reharmonise the note as a chord extension (D over Cmaj7
                     becomes Cmaj9), the default;
      'diminished' - Barry Harris 6/dim7 substitution (D over Cmaj7 -> Bdim7);
      'sustain'    - keep the previous chord's inner voices and move only the
                     melody, for brief passing tones.
    Steps whose melody is already a chord tone are unaffected by this choice.

    A step whose chord_type or name is NO_CHORD ("NC") is voiced as the melody
    alone on a single fret (get_melody_only_voicing) and flagged
    melody_only=True. Such a step is short-circuited before any chord logic,
    so it is never reharmonised and never carries a clause; it also does not take part in
    voice-leading minimisation, and being neither a drop-2 voicing nor a
    four-string shape it is exempt from that playability invariant.

    **Texture and rhythm.** `timings` is each slot's own `(bar, beat, duration)`
    in the caller's units - a signed bar, the beat within it, and a length in
    whole notes - the same triple `ArrangementStep` already carries. `None`, the
    default, means the caller has told us nothing about where its notes fall, and
    then every slot is a principal note and this function behaves exactly as it
    always has.

    `bass` selects the **style** the thumb line is written on, as a comma-separated list
    of note rules from `BASS_RULES`: `"none"` (the default, no thumb line),
    `"root"` (a note only where the harmony anchors, carrying that chord's root), or the
    full `"root,5th,approach,nearest"` (a note on every beat, which is what makes the
    line a walk). It is an argument of its own rather than a property of the texture,
    because the note rules are the composer's choice and the set is open - a new one is a
    row in `BASS_RULE_ROLES`.

    `BASS_STYLE_AUTO`, the default here, resolves from the texture and the selection, and
    a combination the left hand cannot accommodate is refused rather
    than degraded. **Both rules, and the measurement behind the second, are stated
    once** - in `_resolve_bass` and `bass.bass_allowed` - rather than repeated here.
    Two consequences a caller is most likely to meet: a melody-only selection that also
    names the bass part walks without any style being named (`parts="melody,bass"`), and
    `bass="none"` on that selection is the same arrangement with the thumb dropped - a
    coherent part in its own right.

    `texture="targets"` uses the timing to arrange the way the guide describes:
    a full four-note chord on beats 1 and 3 of the bar, and a shell, a 3rd/6th
    interval or the melody alone in between. `beats_per_bar` is what the rule
    reads to decide which beats exist, so a 3/4 or 2/2 head is not treated as
    4/4 (see TARGET_BEATS). The rule changes *which grips are offered*, never
    the cost tuple, so the selection order and the engine's determinism are
    untouched.

    `beat_type` is the metre's other half: `beats_per_bar` says which beats exist,
    `beat_type` how long one lasts. The walking bass is the one rule that reads it -
    a slot's `duration` is in whole notes, and a whole note is `beat_type` beats -
    so a head passes both. Every other caller may leave it at 4.

    A `timings` list shorter than `progression` is not an error: the unlocated
    trailing steps are simply treated as principal notes, which is the same
    "we know nothing" rule that governs `timings=None`. The guard is the one
    `slots.arrange_slots` already applies to its own timings, for the same
    reason - a hand-built list must not silently shift the rhythm.

    `texture="targets"` with a walking thumb (`bass="root,5th,approach,nearest"`, or a
    `bass:walk` grid row) adds a thumb line on the bass strings under a light left hand:
    a **shell** (3rd & 7th) on a target beat, the **melody alone** between, and a walk
    underneath, one thumb note per beat of the bar. Four consequences are part of the
    contract rather than details of it:

    - **It may return more steps than it was given.** The bass grid is finer than
      the melody grid, so a bar whose melody is a whole note still yields a step
      for each of its `beats_per_bar` beats - one carrying the melody and the rest
      marked `bass_only`, whose upper voices are held rather than re-struck. That
      is **four** steps in 4/4, **three** in 3/4 and **two** in 2/2, because the
      grid is `beats_per_bar` beats wide - and three of the committed scores are in
      cut time. Callers that zip their
      progression against the result, or derive a bar count from `len(steps)`, are
      wrong under a walked route only; `uniform` and the default `targets` are untouched. A step
      the walk invented can be promoted to a **target** when the melody moves onto
      it, and then it states its harmony rather than holding - which is
      `decisions.is_bass_only`, and the reason a `bass_only` step is always a fill.
    - **A `bass_only` step carries the melody sounding at that instant**, not the
      melody the walk last passed. Those differ whenever the melody moves on a beat
      the walk does not visit - the beat 2.5 of a 2/2 bar, where the walk is on 1.0
      and 2.0 - and getting it wrong states a note the score has not reached yet.
    - **A fill is the melody alone**, and so is a target no shell can sound. The
      chord name above such a step describes the harmony rather than everything
      sounding, which is the texture rather than a defect - the harmony is stated
      in full at the next target.
    - **With `timings=None` the walk degrades to one note per slot.** There is no
      beat grid to place the walk on, and that is the path every existing
      hand-written caller takes, so it is documented rather than silent.

    The bass is merged into `Voicing.frets` *after* `select_step_voicing` has chosen the
    upper shape, so it cannot enter `voicing_cost`'s tuple by construction. That
    also means the combined string set is deliberately **not** a member of
    `supported_string_sets()`: the playability invariant applies to the upper
    voices, with exactly one `BASS_STRING_INDICES` string outside that set carrying
    the thumb below it.
    """
    _k = resolve_knobs(
        options,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        texture=texture,
        bass=bass,
        parts=parts,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        melody_onsets=melody_onsets,
        timings=timings,
    )
    # Unpacked into the names the loop below has always used, so the extraction
    # above changes nothing downstream of it.
    top_strings = _k.top_strings
    non_chord_tone = _k.non_chord_tone
    fret_min = _k.fret_min
    fret_max = _k.fret_max
    texture = _k.texture
    bass = _k.bass
    harmony = _k.harmony
    grid = _k.grid
    beats_per_bar = _k.beats_per_bar
    beat_type = _k.beat_type
    melody_onsets = _k.melody_onsets
    timings = _k.timings
    bass_pcs = _k.bass_pcs
    slash_bass_cost_for = _k.slash_bass_cost

    arrangements: List[ArrangementStep] = []

    # The walking bass is computed here, over the **walked beats** rather than
    # over the slots, and it yields a pitch *class* rather than a pitch and a
    # string: neither the octave nor the string can be decided before an upper
    # voicing exists, and only this function is downstream of one. `place_bass`
    # resolves both together, after selection.

    _p = resolve_policies(
        progression,
        # `_k.parts` rather than the keyword `parts`, and that is not a style choice:
        # `resolve_knobs` is what reads `options.parts`, so passing the raw keyword
        # here handed the engine the *default* whenever a caller used
        # `options=ArrangeOptions(parts=...)` - a silent drop of the whole selection,
        # the same defect `options.bass` had. The two spellings are compared by
        # `test_comping.TestTheCompingArrangement`, which is where it was caught.
        parts_arg=_k.parts,
        texture=texture,
        bass=bass,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        timings=timings,
    )
    # Unpacked into the names the loop below has always used, so the extraction
    # above changes nothing downstream of it.
    chosen_parts = _p.parts
    melody_voiced = _p.melody_voiced
    melody_only = _p.melody_only
    bass = _p.bass
    has_thumb = _p.has_thumb
    harmony_family = _p.harmony_family
    grid_pattern = _p.grid_pattern
    slots = _p.slots

    # Harmony and melody state for the walking-bass role rule. Both are read from
    # what actually sounds, not from the written chord, so a substituted chord
    # What one step tells the next; see `Carried`.
    carried = Carried()

    loop = _loop_slots(progression, timings, slots)
    slot_inputs = SlotInputs(
        progression=progression,
        top_strings=top_strings,
        texture=texture,
        parts=chosen_parts,
        has_thumb=has_thumb,
        melody_only=melody_only,
        melody_voiced=melody_voiced,
        melody_onsets=melody_onsets,
        harmony_family=harmony_family,
        grid_pattern=grid_pattern,
        beats_per_bar=beats_per_bar,
        fret_min=fret_min,
        fret_max=fret_max,
        non_chord_tone=non_chord_tone,
        bass_pcs=bass_pcs,
        slash_bass_cost_for=slash_bass_cost_for,
    )
    for slot in loop:
        plan = slot_state(carried, slot, slot_inputs)
        if plan is None:
            continue
        _route_slot(arrangements, slot, plan)

    return arrangements
