"""One slot's plan: what the loop decided before any route is asked.

`slot_state` answers, once per slot, the note in force, whether the guitar sings here,
the metric weight, the role, the permitted grips and - when the plan is silent - why.
It builds a `SlotPlan` from the arrangement-level `SlotInputs`, so the five routes read
decisions rather than making them. It sits above `movement`, which calls it in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Container, Optional, Tuple

from musthe import Note

from .bass import Slot
from .chords import normalised_harmony
from .context import (
    SlotArrangementFacts,
    SlotBassFacts,
    SlotContext,
    SlotHarmony,
    SlotIdentity,
    SlotNeckFacts,
    SlotState,
    SlotTiming,
)
from .decisions import (
    MELODY_ALONE_BASS,
    MELODY_ALONE_REST,
    lone_bass_case,
    melody_alone_case,
    resolve_texture_grips,
)
from .grid import Rhythm
from .options import CHORD_FILLS_NONE
from .texture import (
    metric_weight,
    roles_for_slot,
    texture_palette,
)
from .tuning import (
    ROLE_TARGET,
    SILENCE_GRID,
    SILENCE_TUNE_SILENT,
)


@dataclass
class Carried:
    """What one iteration of the step loop leaves behind for the next.

    The only state the loop carries: the last harmony a *target* stated, and the
    last melody pitch that sounded. Both are read from what actually sounds, not
    from the written chord, so a substituted chord compares as itself (the same
    `normalised_harmony` the `repeated` hold uses).
    """

    last_target_harmony: Optional[Tuple[Optional[str], Optional[str]]] = None
    previous_melody_midi: Optional[int] = None


@dataclass(frozen=True)
class SlotPlan:
    """One slot's decisions, made before any route is chosen.

    Built by `slot_state`, which refuses a slot outright by returning None. The
    routes read this rather than recomputing anything, so the metric weight, the
    role, the texture grips and the melody-alone kind are each decided once.

    `context` is the slot's route-facing request and `rhythm` the one fact group it
    cannot hold (the context sits below `grid`); both are kept whole rather than
    unpacked, so a route cannot read a bar, a role or a search window the plan did
    not decide.
    """

    context: SlotContext
    rhythm: SlotRhythmFacts
    sings_here: bool
    slot_grips: Tuple[str, ...]
    melody_alone: str
    # Why a `MELODY_ALONE_REST` step sounds nothing, one of the SILENCE_* constants.
    # Defaults to the chord rhythm's answer, which is the only reason the loop's rest
    # route fired before the melody-only refusal learned to emit a step of its own.
    silence: str = SILENCE_GRID


@dataclass(frozen=True)
class SlotRhythmFacts:
    """The metre and the layers' rhythms: *when* each part sounds.

    The metre (`beats_per_bar`, `grouping`), the chord's own rhythm (`chord_rhythm`),
    where the chord fills a notated rest (`chord_fills`), and the tune's onsets
    (`melody_onsets`). Read by the plan's chord-attack decisions and the comping
    route's reharmonise guard.

    It lives here rather than in `context` because `chord_rhythm` is a `grid.Rhythm`
    and `context` sits below `grid` in the dependency order.
    """

    beats_per_bar: int
    grouping: Tuple[int, ...]
    #: The chord's rhythm, read by `_chord_here`.
    chord_rhythm: Optional[Rhythm]
    chord_fills: str
    melody_onsets: Optional[Container[int]]


@dataclass(frozen=True)
class SlotInputs:
    """The arrangement-level facts every slot's plan and context are built from.

    Bound once by `arrange_progression` and passed to `slot_state`, so a stage takes
    the *slot* rather than a dozen words about the arrangement. The four groups are
    focused rather than flat: `arrangement`, `neck` and `bass` pass straight through
    to the `SlotContext` the routes read, and `rhythm` stays on the plan.
    """

    arrangement: SlotArrangementFacts
    rhythm: SlotRhythmFacts
    neck: SlotNeckFacts
    bass: SlotBassFacts


def _slot_context(
    inputs: SlotInputs,
    slot: Slot,
    triple: Tuple[Optional[str], str, str],
    role: str,
) -> SlotContext:
    """The route-facing view of one slot, from the arrangement and the slot.

    `SlotContext` sits at the bottom of the dependency order and cannot import
    `SlotInputs`, so this is where the two are joined. The plan keeps both, which
    is what lets the routes read one object rather than the same fields twice.

    The weight is derived here from the slot and the metre, so the caller does not
    pass a value the context can compute from the same facts.
    """
    note_str, chord_type, name = triple
    melody_note = Note(note_str) if note_str is not None else None
    return SlotContext(
        timing=SlotTiming(
            bar=slot.bar,
            beat=slot.beat,
            duration=slot.duration,
        ),
        harmony=SlotHarmony(
            name=name,
            chord_type=chord_type,
            note_str=note_str,
            melody_note=melody_note,
        ),
        identity=SlotIdentity(
            progression=inputs.arrangement.progression,
            index=slot.index,
        ),
        state=SlotState(
            role=role,
            weight=metric_weight(
                slot.bar, slot.beat,
                inputs.rhythm.beats_per_bar, inputs.rhythm.grouping,
            ),
            chord_attack=_chord_attacks(
                inputs.arrangement, inputs.rhythm, slot, melody_note
            ),
        ),
        arrangement=inputs.arrangement,
        neck=inputs.neck,
        bass=inputs.bass,
    )


def _sings_here(
    arrangement: SlotArrangementFacts,
    rhythm: SlotRhythmFacts,
    index: int,
    melody_note: Optional[Note],
) -> bool:
    """**Does the guitar sing *this* slot?** (§9.3 step D: the soprano is per slot.)

    It sings a slot only where its voice selection has a soprano *and* the slot is a
    melody **onset** - a written note articulating here. Every other slot it comps,
    except on a melody-only selection, whose note-less slots were skipped above.

    §9.2's onset signal is reused rather than re-derived: `melody_onsets` is the same
    set the comping route's reharmonise guard reads, and a position the tune merely
    *sustains* through is not an onset, so the guitar states the chord there rather than
    re-articulating a note it did not begin - which is why a note-bearing merged
    position still comps. `None` means every slot is an onset - the honest answer for a
    caller who said nothing about onsets.
    """
    return (
        arrangement.melody_voiced
        and melody_note is not None
        and (rhythm.melody_onsets is None or index in rhythm.melody_onsets)
    )


def _tune_silent_plan(
    car: Carried,
    slot: Slot,
    chord_type: str,
    name: str,
    inputs: SlotInputs,
) -> SlotPlan:
    """The plan for a position a melody-only selection has nothing to play.

    A melody-only selection plays the tune and nothing else, so a position with no
    note has nothing for the guitar to play. The position is still **emitted**,
    silent: the tab keeps its bar count and its line-up against the band, and
    `tune_silent` is what the line says rather than the loop's own reason.

    It is kept as the only *early* answer because §9.3 step D made the other case a
    real one: a *singing* selection (soprano named) now receives note-less slots from
    the comping union - positions the tune is silent at - and the guitar **comps** them
    rather than being refused, which is why those fall through in `slot_state`.
    """
    bar, beat = slot.bar, slot.beat
    weight = metric_weight(
        bar, beat, inputs.rhythm.beats_per_bar, inputs.rhythm.grouping
    )
    # The role the slot would have had, read without committing to `car`: a refused
    # slot must not move the target or the tracked pitch that a later slot is judged
    # against, so the two `car` writes stay in `_carried_role`.
    role = roles_for_slot(
        weight,
        inputs.arrangement.texture,
        harmony_changed=(
            car.last_target_harmony is None
            or normalised_harmony(name) != car.last_target_harmony
        ),
        melody_moves=False,
        has_thumb=inputs.arrangement.has_thumb,
        melody_only=inputs.arrangement.melody_only,
    )[0]
    return SlotPlan(
        context=_slot_context(inputs, slot, (None, chord_type, name), role),
        rhythm=inputs.rhythm,
        sings_here=False,
        slot_grips=(),
        melody_alone=MELODY_ALONE_REST,
        silence=SILENCE_TUNE_SILENT,
    )


def _carried_role(
    car: Carried,
    weight: int,
    name: str,
    melody_note: Optional[Note],
    arrangement: SlotArrangementFacts,
) -> str:
    """This slot's metric role, updating the state the next slot is judged against.

    `roles_for_slot` re-validates the texture, which is harmless: the table was
    already checked before the loop, so this cannot raise here.

    Under `targets` a strong beat is only a target when something new happens on it:
    a different harmony from the last target's (the off-beat change rule), or the
    melody actually moving onto it (decision F, which is what lets the second bar of
    a two-bar chord restate its shell when the player re-articulates the line there
    and stay thin when they do not).

    A silent slot moves nothing onto the beat: `melody_moves` is False, and the
    tracked pitch clears to None so the next onset reads as the melody arriving
    there - a fresh attack after silence counts as movement, which is what the
    placeholder's C4 accidentally produced for the slot *after* a rest, minus its
    false claim about the silent slot itself.
    """
    harmony_key = normalised_harmony(name)
    melody_moves = (
        melody_note is not None
        and (car.previous_melody_midi is None
             or melody_note.midi_note() != car.previous_melody_midi)
    )
    role = roles_for_slot(
        weight,
        arrangement.texture,
        harmony_changed=(car.last_target_harmony is None
                         or harmony_key != car.last_target_harmony),
        melody_moves=melody_moves,
        has_thumb=arrangement.has_thumb,
        melody_only=arrangement.melody_only,
    )[0]
    if role == ROLE_TARGET:
        car.last_target_harmony = harmony_key
    car.previous_melody_midi = (
        melody_note.midi_note() if melody_note is not None else None
    )
    return role


def _texture_grips(
    role: str, slot: Slot, arrangement: SlotArrangementFacts
) -> Tuple[str, ...]:
    """Which grips the texture makes *available* on this step.

    It is not a term in the cost, so a fill cannot be outbid for being in position -
    the point is that fewer notes are played here, not that this shape is better.
    The narrowing rule itself, and why the default is not an intersection, are
    documented once in `decisions.resolve_texture_grips`.

    A melody-only selection never asks: the left hand plays nothing on every slot,
    whatever the texture's palettes say, so the loop hands an empty palette straight
    through. Skipping the resolution is what makes `texture` silently inert here
    rather than noisily so.
    """
    if arrangement.melody_only:
        return ()
    return resolve_texture_grips(
        role,
        texture_palette(
            role, arrangement.texture, arrangement.parts, arrangement.has_thumb
        ),
        # The right hand's budget, and a fact about *this slot* rather than about
        # the arrangement: a target may sound three strings only where a bass note
        # is actually being placed under it, which is what `slot.bass` says.
        # `has_thumb` alone would thin chords the thumb never plays under -
        # `bass-on 1` leaves most slots bare.
        has_thumb=arrangement.has_thumb and slot.bass is not None,
    )


def _chord_here(
    rhythm: SlotRhythmFacts, beat: Optional[float], melody_absent: bool
) -> bool:
    """Whether the chord part attacks at this position.

    The request's `chord_on` decides - `melody` at every written onset, or the
    positions it names - and `wants_melody` is true for every slot because the
    slots that exist are the melody's.

    A slot with **no melody** is one the chord layer asked for: either a
    `--chord-on` target or a rest `--chord-fills` fills, and a slot nothing asked
    for is not in the timeline at all. So the chord attacks at it by construction,
    which the rhythm test could not say - the position is precisely one the rhythm
    does *not* name.
    """
    if melody_absent and rhythm.chord_fills != CHORD_FILLS_NONE:
        return True
    if rhythm.chord_rhythm is None or rhythm.chord_rhythm.wants_melody:
        return True
    return rhythm.chord_rhythm.includes(
        beat, rhythm.beats_per_bar, rhythm.grouping
    )


def _tune_onset_attack(
    arrangement: SlotArrangementFacts,
    rhythm: SlotRhythmFacts,
    slot: Slot,
    melody_note: Note,
) -> bool:
    """Whether this slot is one the **tune's own rhythm** names and the guitar comps.

    `melody` is the written tune rather than a figure, so it has no position list to
    ask: the onsets `melody_onsets` carries are what answer for it. Only a slot the
    guitar is **not** singing needs the flag - a sung onset re-strikes through
    `ArrangementStep.repeated` or by carrying a different soprano, and setting it there
    would turn the collapse off for chord-melody.
    """
    if _sings_here(arrangement, rhythm, slot.index, melody_note):
        return False
    return rhythm.melody_onsets is None or slot.index in rhythm.melody_onsets


def _chord_attacks(
    arrangement: SlotArrangementFacts,
    rhythm: SlotRhythmFacts,
    slot: Slot,
    melody_note: Optional[Note],
) -> bool:
    """Whether this slot's chord is a **new attack** rather than a shape still ringing.

    `_chord_here` answers where the chord part states a harmony. This answers the
    narrower question the renderers ask when two consecutive steps sound the same
    pitches - is the later one struck again, or is the earlier one still ringing? - and
    only the arrangement can answer it, because the pitches are identical either way.

    Two ways to be an attack:

    - the slot carries **no melody**, so the chord layer asked for it: a position
      `--chord-on` named, or a silent bar `--chord-fills` placed a chord in. Nothing
      in the tune is being re-articulated, so there is no hold to preserve;
    - the chord's **own rhythm names this beat**. `--chord-on every-beat` on a comp is
      four stabs a bar, and `--chord-on melody,1and` adds one under a note the tune is
      holding - the named positions, and the tune's own onsets, which
      `_tune_onset_attack` answers.

    What the second clause keeps is the case the flag exists for: two identical comping
    shapes under a tune that moves are one attack and one hold by pitch alone, so
    without it a comp on the tune's rhythm was written as one chord per bar.

    A position the eighth-note skeleton invented, where the tune merely sustains, is
    neither - that is the hold `tabstaff._collapse_holds` and `tabscore._is_hold`
    exist for.

    """
    if melody_note is None:
        return True
    chord_rhythm = rhythm.chord_rhythm
    if chord_rhythm is None:
        return False
    if chord_rhythm.includes(slot.beat, rhythm.beats_per_bar, rhythm.grouping):
        return True
    if not chord_rhythm.wants_melody:
        return False
    return _tune_onset_attack(arrangement, rhythm, slot, melody_note)


def slot_state(
    car: Carried,
    slot: Slot,
    inputs: SlotInputs,
) -> Optional[SlotPlan]:
    """One slot's decisions, and the one refusal that ends a slot here.

    Returns a **silent plan** for a position a melody-only selection has nothing
    to play: the step is still emitted (`MELODY_ALONE_REST` with
    `silence=SILENCE_TUNE_SILENT`) so the tab keeps its line-up. Otherwise the
    plan carries everything the routes need, and the two values on `car` are
    updated in place.
    """
    index = slot.index
    note_str, chord_type, name = inputs.arrangement.progression[index]
    if note_str is None:
        # A melody-only selection's note-less slot is **tune silent** unless the thumb
        # has something there: `chord_on="none"` with a thumb plays the bass part, and a
        # position the walk invented is the one place it sounds anything at all.
        if inputs.arrangement.melody_only and slot.bass is None:
            return _tune_silent_plan(car, slot, chord_type, name, inputs)
        melody_note = None
    else:
        melody_note = Note(note_str)

    sings_here = _sings_here(inputs.arrangement, inputs.rhythm, index, melody_note)

    # Where this slot falls in the bar, and therefore what it is for. Read
    # defensively, exactly as slots.arrange_slots guards its own timings: a
    # short list leaves the trailing steps unlocated, and an unlocated step is
    # a principal note rather than a fill. The bar and beat are also stamped
    # onto the step, because a caller that supplied the rhythm wants to read it
    # back off the result rather than have to correlate two lists.
    bar, beat = slot.bar, slot.beat
    weight = metric_weight(
        bar, beat, inputs.rhythm.beats_per_bar, inputs.rhythm.grouping
    )
    role = _carried_role(car, weight, name, melody_note, inputs.arrangement)
    slot_grips = _texture_grips(role, slot, inputs.arrangement)

    # A slot that is played as a single note rather than looked up. Which
    # slots those are, and why each is a branch rather than a missing case,
    # is decisions.melody_alone_case. It returns a *kind*, because the three
    # non-default routes build different steps: an NC bar sets
    # `melody_only=True`, a texture case must not, and an off-grid slot on the
    # comping route is a rest with no notes in it at all.
    #
    # `melody_voiced` here is the **per-slot** `sings_here`, not the route: a
    # slot the guitar does not sing (no soprano, or no note at this position)
    # takes the comping-route branches inside `melody_alone_case`, so an
    # off-grid note-less slot rests rather than asserting a melody it has not
    # got. §9.3 step D.
    chord_here = _chord_here(inputs.rhythm, beat, melody_note is None)
    melody_alone = melody_alone_case(
        inputs.arrangement.texture, role, slot_grips, chord_type, name,
        inputs.arrangement.has_thumb, melody_voiced=sings_here, on_grid=chord_here,
    )
    # **The bass part's own claim on the slot**, and it is asked *after* the four
    # melody-alone answers rather than inside them: it is the one combination that
    # depends on the slot's thumb note, which `melody_alone_case` cannot see, and the
    # answers it replaces are the ones that would otherwise drop the note - a rest on
    # the comping route, and a melody-only selection's note-less position. A slot the
    # guitar **sings** is not one of these: the melody-alone route already carries the
    # thumb (`docs/engine.md`'s `--chord-on 1and` example).
    if lone_bass_case(
        has_bass=slot.bass is not None,
        sings_here=sings_here,
        chord_stated=chord_here and not inputs.arrangement.melody_only,
    ):
        melody_alone = MELODY_ALONE_BASS
    return SlotPlan(
        context=_slot_context(inputs, slot, (note_str, chord_type, name), role),
        rhythm=inputs.rhythm, sings_here=sings_here, slot_grips=slot_grips,
        melody_alone=melody_alone,
    )
