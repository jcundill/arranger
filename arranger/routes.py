"""The route handlers: one function per way a slot can become a step.

The rest, the thinned fill, the `NC` bar and the comping route each build their step
without re-entering the step loop; `harmonised_step` is in `harmonised_route` because it is
the orchestrating route, retrying through `prepare_step`. What the hand was holding
when a slot arrived is `step_history`'s question, and `resolve_substitute_harmony`
lives in `chords`, where the non-chord-tone routing it composes already is.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Container, List, Optional, Tuple

from musthe import Note

from . import comp_line as _comp_line
from . import grips as _grips
from .bass import Slot
from .bass_merge import attach_bass, next_resolution_melody
from .bass_place import is_shape_held
from .chords import ChordParser, normalised_harmony, resolve_substitute_harmony
from .context import SlotContext
from .cost import SelectionCriteria
from .decisions import (
    dropped_for_the_bass,
    is_bass_only,
    leaving_room_for_the_bass,
    melody_is_ringing,
    palette_facts,
    select_step_voicing,
)
from .melody_alone import melody_alone_shape, sounding_melody
from .parts import PART_BASS
from .step_history import last_sounding_step, sounding_tops
from .step_types import ArrangementStep, Palette, Voicing
from .texture import comping_arity
from .tuning import (
    NO_CHORD,
    SILENCE_NC_COMPING,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    STANDARD_TUNING,
)


def rest_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
    *,
    sings_here: bool,
    silence: str,
) -> None:
    """Append the silent step for a position the guitar does not play.

    The guitar is silent and the horn has the note - or the position is one the
    guitar *declined* for another reason (`silence` names which, one of the
    SILENCE_* constants). **The step is still emitted**, carrying the bar, the
    beat and the chord name: it is what keeps the melody's position in the tab
    staff, and a comping part whose bars collapsed to their stabs would not line
    up against the tune it is comping under.

    The slot's own facts come from `context`, so a route cannot read a bar the
    plan did not decide.
    """
    arrangements.append(ArrangementStep(
        chord=context.harmony.name,
        melody=context.harmony.note_str,
        voicing=Voicing(
            frets=[-1] * len(STANDARD_TUNING),
            top_fret=0,
            avg_fret=0.0,
            grip="rest",
        ),
        bar=context.timing.bar,
        beat=context.timing.beat,
        duration=context.timing.duration,
        role=context.state.role,
        metric_weight=context.state.weight,
        # A rest is a slot the guitar does **not** sing - which is `sings_here`,
        # False here by construction. The route-level `melody_voiced` would
        # claim the guitar sings a slot it just declined to play.
        melody_voiced=sings_here,
        # Why nothing sounds, so the renderer can say so rather than infer
        # silence from an all-muted fret vector, where the four reasons are
        # indistinguishable.
        silence=silence,
    ))
    # The thumb still walks on a rest. A comping grid thins the **chords**,
    # not the bass line - that is the whole difference between `grid` and
    # `bass_on="none"`, and dropping the attach here would silently delete the
    # walk from every bar the grid thinned.
    attach_bass(
        arrangements[-1], slot.bass, arrangements
    )


def texture_fill_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
    *,
    top_strings: Tuple[int, ...],
    previous: Optional[Voicing],
) -> bool:
    """Append the thin "fill" step for a slot the texture thins to a melody.

    Returns **True** when the slot is handled, **False** when the melody cannot
    be played alone at all and the caller should fall through to the harmonised
    route - an unreachable melody is genuinely unplayable, so inventing a shape
    for it would be worse than trying the full one.
    """
    # This kind is answered only when the guitar sings, and a singing slot
    # with no note was refused at the top of this loop - so a note is
    # pinned here, which is what lets the type say so below. The *name*
    # needs the same statement: `note_str` is only narrowed inside the
    # branch that built `melody_note`, and this route needs both.
    assert context.harmony.melody_note is not None and context.harmony.note_str is not None
    solo_voicing, inside_window = melody_alone_shape(
        context.harmony.melody_note, previous=previous, top_strings=top_strings
    )
    if solo_voicing is not None:
        sounding, written_original = sounding_melody(
            solo_voicing, context.harmony.note_str
        )
        fill = ArrangementStep(
            chord=context.harmony.name,
            melody=sounding,
            voicing=solo_voicing,
            # The tune alone *is* this slot's palette - the texture thinned the slot, or the
            # selection asked for the soprano on its own - so the count it states is the
            # palette's own limit rather than a choice between shapes. Recording it is what
            # lets the line answer "one note, why?" instead of leaving it open, and
            # `inside_window` says whether anything inside the preferred frets was on the
            # table at all.
            palette=Palette(available=1, inside_window=inside_window),
            original_melody=written_original,
            partial=False,
            bar=context.timing.bar,
            beat=context.timing.beat,
            duration=context.timing.duration,
            role=context.state.role,
            metric_weight=context.state.weight,
            # The tune alone under the thumb, on a beat the walk invented: the note is the
            # one already sounding, so nothing above the thumb is struck here either. A
            # position the chord's rhythm *named* is a fresh attack, and takes the answer
            # `_emit_step` gives it.
            bass_only=is_bass_only(
                slot.bass_only,
                chord_attack=context.state.chord_attack,
                holds=melody_is_ringing(
                    arrangements, Note(sounding).midi_note(),
                    normalised_harmony(context.harmony.name),
                ),
            ),
        )
        attach_bass(fill, slot.bass, arrangements)
        arrangements.append(fill)
        return True
    return False


def no_chord_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
    *,
    top_strings: Tuple[int, ...],
    previous: Optional[Voicing],
) -> None:
    """Append the melody-alone step for an `NC` bar: melody, but no harmony.

    This happens before any chord logic, so there is no non-chord-tone strategy and
    no substitute chord. The `melody_only` flag is
    set here and *only* here; the texture case above reaches the same shape
    deliberately without it.
    """
    # As the texture branch above: this kind means the guitar sings, and
    # that guard already refused a singing slot with no note.
    assert context.harmony.melody_note is not None and context.harmony.note_str is not None
    solo_voicing, inside_window = melody_alone_shape(
        context.harmony.melody_note, previous=previous, top_strings=top_strings
    )
    if solo_voicing is None:
        rest_step(
            arrangements, slot, context,
            sings_here=False, silence=SILENCE_OUT_OF_REACH,
        )
        return
    # get_melody_only_voicings may have dropped the note an octave to stay
    # below HIGH_FRET_LIMIT, so the step reports the pitch that sounds and
    # keeps the written one for the renderer. See `sounding_melody`.
    sounding, written_original = sounding_melody(
        solo_voicing, context.harmony.note_str
    )
    # The note already sounding, on a beat the walk invented: nothing above the thumb is
    # struck. Asked before the append so this step is not part of what it reads.
    bass_only = is_bass_only(
        slot.bass_only,
        chord_attack=context.state.chord_attack,
        holds=melody_is_ringing(
            arrangements, Note(sounding).midi_note(),
            normalised_harmony(context.harmony.name),
        ),
    )
    arrangements.append(ArrangementStep(
        chord=context.harmony.name,
        melody=sounding,
        voicing=solo_voicing,
        original_melody=written_original,
        melody_only=True,
        # A bar of melody with no harmony has a palette like any other lone note - the
        # positions the eligible strings offer - so it says what that palette held rather
        # than leaving the window clause to guess. See `melody_alone_shape`.
        palette=Palette(available=1, inside_window=inside_window),
        # `step.grip` is a derived view of `voicing.grip`, so nothing is
        # passed here: the voicing says "melody" and the step cannot
        # disagree with it. The property is what keeps the two spellings
        # one fact with one home - see `docs/history/one-fact.md`, commit 1.
        bar=context.timing.bar,
        beat=context.timing.beat,
        duration=context.timing.duration,
        role=context.state.role,
        metric_weight=context.state.weight,
        bass_only=bass_only,
    ))
    # An `NC` bar is still a place the thumb walks: the walk reads the last
    # known harmony (or skips), and the melody-alone shape leaves every bass
    # string free. Attaching it here rather than only on harmonised steps is
    # what keeps a bar of no-chord melody from being a hole in the walk.
    attach_bass(arrangements[-1], slot.bass, arrangements)


@dataclass(frozen=True)
class _CompingHarmony:
    """The chord a comping step states.

    The written chord, unless a non-chord-tone strategy substituted one. The
    substitution changes what the guitar **states**, not what it sings: the melody
    belongs to the horn here, so `melody_pc` stays None and the comping shape is still
    held to the substitute's full tone set.

    `name` is the whole harmony - the written chord, or the substitute's name - so the
    quality is read off it rather than carried beside it.
    """

    name: str
    strategy: Optional[str]
    harmonized_as: Optional[str]
    is_non_chord_tone: bool


def _comping_harmony(
    context: SlotContext,
    *,
    melody_onsets: Optional[Container[int]],
    non_chord_tone: str,
) -> _CompingHarmony:
    """Resolve a substitution **at an onset**, or state the written chord.

    A held position was decided where the note began, and a silent one has nothing to
    resolve, so only an onset is reharmonised. `melody_onsets` is the caller's onset
    set; None means every slot is an onset, which is what a hand-built progression gets
    when the caller never said which notes it begins.

    `D5` over `Cmaj7` therefore gives `Cmaj9` (extension) or `Bdim7` (diminished)
    under the guide-tone voices, exactly as the melody route re-voices it.
    """
    written = _CompingHarmony(
        name=context.harmony.name,
        strategy=None,
        harmonized_as=None,
        is_non_chord_tone=False,
    )
    if context.harmony.melody_note is None or (
        melody_onsets is not None and context.identity.index not in melody_onsets
    ):
        return written
    substitute = resolve_substitute_harmony(
        context.harmony.melody_note,
        context.harmony.name,
        non_chord_tone,
        next_melody=next_resolution_melody(
            context.identity.progression, context.identity.index, melody_onsets
        ),
    )
    if substitute is None:
        return written
    name, strategy = substitute
    # A guitarist handed `Cmaj7 -> Bdim7` with no melody on their own part cannot see
    # why the chord moved; the note that forced it is the horn's, so it has to be
    # named here or the part reads wrong.
    return _CompingHarmony(
        name=name,
        strategy=strategy,
        harmonized_as=name,
        is_non_chord_tone=True,
    )


def _line_target(
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


def _comping_candidates(
    context: SlotContext,
    harmony: _CompingHarmony,
    *,
    notes: int,
    bass_voice: bool,
    band: Optional[Tuple[int, int]],
) -> List[Voicing]:
    """The melody-free shapes a comping step may state, in a playable position.

    `notes` is how many chord voices the guitar states here - the chord part's arity,
    which `texture` owns. **A voice is a *role* in the stack, not a count of parts
    played twice**, so it is the arity rather than the number of parts named.

    **A grid position the tune is silent at is not the melody's voice** (§9.3 step D):
    the melody part has no note to sing there, and the arity already excludes it -
    `derived_arity` counts the melody only when the selection takes it. `comping_arity`,
    not `derived_arity`: this position has no note of the tune for the soprano string
    to carry - the tune belongs to the horn or is held across this beat - so the string
    is free for the chord part. Reserving it anyway costs the chord its 5th, which is
    what this arity avoids.

    **`bass_voice`** is whether this selection is the bass voice and nothing else,
    which arity cannot say: an inner voice and the bass both ask for one note, and only
    the bass voice has a register that is part of what it *is*. Derived from the
    resolved parts rather than an extra flag, so the two spellings of one request
    cannot disagree.

    `band` is the comp's register, decided once by `_line_target` and shared by the
    generator and the line so the palette and the narrowing can never disagree about
    whether the line runs at all.
    """
    return _grips.get_comping_voicings_for(_grips.CompingRequest(
        chord_name=harmony.name,
        fret_min=context.neck.fret_min,
        fret_max=context.neck.fret_max,
        notes=notes,
        bass_voice=bass_voice,
        band=band,
    ))


def _line_state(
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
        if _same_chord(previous, context)
        else [max(previous.voicing.midi_notes())]
    )
    register = (
        previous.voicing.avg_fret if previous.voicing.active_frets() else None
    )
    return (_comp_line.read_state(tops), register)


def _same_chord(previous: ArrangementStep, context: SlotContext) -> bool:
    """Whether the last sounding step stated this slot's chord.

    Compared through `normalised_harmony`, so a substituted chord reads as itself and
    two spellings of one chord are not a change.
    """
    return normalised_harmony(previous.chord) == normalised_harmony(
        context.harmony.name
    )


def _next_chord_tones(
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


def _fill_target(
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


def _line_inputs(
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
    fill = _fill_target(context, band, register) if is_fill else None
    next_tones = None if is_fill else _next_chord_tones(context, slot, beats_per_bar)
    return fill, next_tones


def _line_narrowed(
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
    state, register = _line_state(arrangements, context)
    fill, next_tones = _line_inputs(context, slot, beats_per_bar, band, register)
    shapes = [_comp_line.LineShape.of(voicing, band) for voicing in candidates]
    tone, role = _comp_line.chosen_top(
        state, shapes, band, next_tones=next_tones, fill=fill
    )
    narrowed = [voicing for voicing in candidates if max(voicing.midi_notes()) == tone]
    if not narrowed:
        return (list(candidates), None)
    return (narrowed, role)



def _comping_choice(
    arrangements: List[ArrangementStep],
    candidates: List[Voicing],
    context: SlotContext,
    harmony: _CompingHarmony,
    slot: Slot,
    *,
    beats_per_bar: int,
    band: Optional[Tuple[int, int]],
) -> Tuple[Voicing, Palette, Optional[str]]:
    """The comping shape the selector prefers, and the palette it chose from.

    The root is read once for the bass-function tie-break. `get_comping_voicings`
    refuses to generate anything without one, so by this point it is never
    None - the check is read from the same place the generator read it rather than
    re-derived, so the two cannot disagree.

    **Two narrowings, in this order: the bass, then the line.** The requested bass note
    runs first, exactly as on the melody-bearing route - a comping shape the thumb
    cannot reach that beat's note under is not offered, so the chord part moves instead
    of the line losing a note. The comp line then narrows what survives to the top tone
    it chose. Each records the shape it gave up against the palette it received
    (`Palette.dropped_for_bass`, `Palette.dropped_for_line`), because a comping step
    states its voices through `_comping_clause` while *why this shape* is a palette fact
    like any other.
    """
    _canonical, root_pc, _tones = _grips.chord_context(harmony.name)
    # The last *sounding* shape: a silent position between here and the previous chord
    # is a hole in the tab, not a shape the hand held - see `last_sounding_step`.
    prev_sounding = last_sounding_step(arrangements)
    criteria = SelectionCriteria(
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        fret_min=context.neck.fret_min,
        fret_max=context.neck.fret_max,
        # The tones the written chord allows. Passed even though the generator
        # already filters on them: `voicing_cost` counts wrong notes itself, and a
        # generator that could be wrong should not be the only thing standing
        # between a chord symbol and a note that is not in it.
        allowed_tones=ChordParser.get_chord_tones(harmony.name),
        # The root, which enables the bass-function tie-break. None for a chord
        # whose name will not parse, which leaves that criterion unasked rather
        # than guessing a bass - the same rule the ordinary route follows.
        root_pc=root_pc,
        # No `melody_pc`: there is no melody on the guitar for the wrong-note count
        # to excuse, which is what lets a comping shape be held to the chord's full
        # tone set.
        melody_pc=None,
        # The written slash bass, honoured before selection rather than after,
        # exactly as on the melody-bearing route.
        bass_pc=(
            context.bass.bass_pcs.get(context.identity.index)
            if context.bass.bass_pcs
            else None
        ),
    )
    offered = candidates
    candidates = leaving_room_for_the_bass(
        offered, slot.bass, arrangements,
        # Never a hold here - see `_emit_comping_step` for why - so the thumb is measured
        # against each candidate rather than against a shape already down.
        bass_only=is_bass_only(
            slot.bass_only, chord_attack=context.state.chord_attack, holds=False
        ),
    )
    ranked = select_step_voicing(candidates, criteria) or candidates[0]
    palette = palette_facts(candidates, ranked, criteria)
    dropped_bass = dropped_for_the_bass(offered, candidates, ranked, criteria)
    if dropped_bass is not None:
        palette = replace(palette, dropped_for_bass=dropped_bass)
    narrowed, top_role = _line_narrowed(
        arrangements, candidates, context, slot,
        beats_per_bar=beats_per_bar, band=band,
    )
    chosen = select_step_voicing(narrowed, criteria) or narrowed[0]
    palette = _apply_line_narrowing(palette, candidates, ranked, chosen, top_role)
    return chosen, palette, top_role


def _apply_line_narrowing(
    palette: Palette,
    candidates: List[Voicing],
    ranked: Voicing,
    chosen: Voicing,
    top_role: Optional[str],
) -> Palette:
    """Record the shape the comp line gave up, but only when it actually moved.

    When the line held the previous top there is no move - `top_role` is None - so
    `dropped_for_line` would have no honest sentence to back it: a hold is not
    re-explained, and claiming a walk or an approach over a static top would be false.
    """
    if chosen is not ranked and top_role is not None:
        return replace(palette, dropped_for_line=ranked)
    return palette


def _emit_comping_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
    harmony: _CompingHarmony,
    chosen: Voicing,
    palette: Palette,
    top_role: Optional[str] = None,
) -> None:
    """Append the comping shape, then merge the thumb into it.

    `chord` stays the **written** symbol; `harmonized_as` and `strategy` say what the
    substitution actually stated under the horn's line (§9.3 step C). The palette is what
    the shape was chosen from: a comping step's voice count is `_comping_clause`'s to name,
    and the palette is here for the choice the request's bass note forced.
    """
    arrangements.append(ArrangementStep(
        chord=context.harmony.name,
        # The written note, which is the horn's line. The guitar does not
        # sound it - `melody_voiced=False` is what says so.
        melody=context.harmony.note_str,
        voicing=chosen,
        palette=palette,
        # A comping shape is three voices by construction, so `partial`
        # is always true and is not worth re-deriving per step.
        partial=True,
        bar=context.timing.bar,
        beat=context.timing.beat,
        duration=context.timing.duration,
        role=context.state.role,
        metric_weight=context.state.weight,
        # **Nothing is ever held on this route**: a comping step exists to state its chord,
        # and a slot the walk invented with the chord part on is one of those - the chord
        # the tune is on has to be heard there. There is also no melody on the guitar for a
        # hold to leave ringing. So the second fact a hold needs cannot be had here.
        bass_only=is_bass_only(
            slot.bass_only, chord_attack=context.state.chord_attack, holds=False
        ),
        melody_voiced=False,
        # The rhythm asked for this chord, so it is struck even where the shape is the
        # one already ringing: a comp on `--chord-on every-beat` is four attacks a bar,
        # and the renderers would otherwise fold beats 2..n into one long chord.
        chord_attack=context.state.chord_attack,
        # What the substitution changed about the *harmony*, reported the
        # way the melody route reports it: `chord` stays the written
        # symbol, and these three say what was actually stated under the
        # horn's line (§9.3 step C).
        non_chord_tone=harmony.is_non_chord_tone,
        strategy=harmony.strategy,
        harmonized_as=harmony.harmonized_as,
        top_role=top_role,
    ))
    attach_bass(arrangements[-1], slot.bass, arrangements)


def bass_alone_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
) -> None:
    """The bass part alone: one thumb note where the guitar states no chord.

    A slot whose only job is the thumb - the chord's rhythm does not name it, and the
    guitar has no melody to sing there - is not a rest. The shape is **empty** rather
    than thin: no upper voice is meant to sound, and a one-note "chord" would be the
    chord part stealing the bass line's slot. `attach_bass` places the walked note
    against the shape the hand is still holding, which is why its fret vector comes
    back with exactly one string plucked and the rest muted.

    A thumb note that cannot be placed leaves the step silent with
    `bass_refused` set - the same contract every other route has, so a note the line
    asked for is named rather than dropped.
    """
    # **What the hand is still holding decides how the line reads.** A shape that is
    # ringing under this slot is held, exactly as it is for a `bass_only` union slot,
    # and `attach_bass` then places the thumb against it; with nothing ringing (the
    # head of a bass line, or a slot after a rest) the thumb is all there is, and the
    # line says so through `annotation._bass_alone_clause`.
    arrangements.append(ArrangementStep(
        chord=context.harmony.name,
        # The written note, which is the horn's line: the guitar does not sound it.
        melody=context.harmony.note_str,
        voicing=Voicing(
            frets=[-1] * len(STANDARD_TUNING),
            top_fret=0,
            avg_fret=0.0,
            grip="bass",
        ),
        bar=context.timing.bar,
        beat=context.timing.beat,
        duration=context.timing.duration,
        role=context.state.role,
        metric_weight=context.state.weight,
        partial=True,
        # Only a shape with something **above the thumb** still sounding can be held:
        # an all-muted previous step is a hole rather than a chord, and a run of lone
        # thumbs leaves the chord before them down rather than replacing it.
        bass_only=is_shape_held(arrangements),
        melody_voiced=False,
    ))
    attach_bass(arrangements[-1], slot.bass, arrangements)


def comping_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    context: SlotContext,
    *,
    chord_type: str,
    melody_onsets: Optional[Container[int]],
    parts: Tuple[str, ...],
    beats_per_bar: int,
) -> bool:
    """The comping route: the guitar harmonises, somebody else sings.

    Taken before `prepare_step`, because `prepare_step` is built around a melody
    to pin: it asks `get_all_grip_voicings` for shapes carrying this note on their
    topmost string, and every one of them would put the tune back on the guitar.
    There is nothing to subtract afterwards - the guitar's part was never
    generated - so the candidates have to come from the melody-free generator in
    the first place.

    Deliberately *after* the NC branch and the melody-alone branch, because both
    are cases where there is no harmony to state: an NC bar has no chord at all,
    and a melody-only selection's fill has already committed to playing one note.
    Under 9.3 step D the caller reaches this function whenever the guitar does not
    **sing** the slot - a selection without a soprano, or a position the tune is
    silent at - and never on a melody-only selection, whose note-less slots were
    skipped at the top.

    Returns **True** when the slot is handled. **False** means no guide-tone shape
    was found in a playable position while the slot still has a melody to voice,
    so the caller should fall through to the melody-bearing route: the chord of
    the tune is still owed to the band, and the guitar playing the tune is a worse
    answer than a thin shape and a better one than silence.

    **`beats_per_bar` is the metre's count**, and it is here because the comp line needs
    one thing the context cannot hold: whether this slot's own duration reaches the
    barline, which is what makes it the last position before a harmony change. The
    metre's other facts stay on the plan - this is a number rather than a `Rhythm`.
    """
    # An `NC` bar has no chord, so there is no guide tone to state and
    # nothing at all for the guitar to play under the horn's line. That is
    # a real hole in the part: the **silent step** records it, so the bar
    # keeps its place in the tab with the reason on it, rather than reaching
    # `get_comping_voicings` (which correctly refuses a chord with no root)
    # and then falling through to a melody-bearing route that would either
    # state it twice or hand the horn's line back to the guitarist. The guitar
    # is silent on this bar, and the horn is not - so the line says which.
    if chord_type == NO_CHORD or context.harmony.name == NO_CHORD:
        rest_step(arrangements, slot, context, sings_here=False, silence=SILENCE_NC_COMPING)
        return True
    # --- the non-chord-tone strategy, at harmony level (§9.3 step C) ---
    harmony = _comping_harmony(
        context,
        melody_onsets=melody_onsets,
        non_chord_tone=context.arrangement.non_chord_tone,
    )
    # **A lone bass part states one note**, whatever the arity says: the bass part is
    # the [part the thumb realises](../docs/history/parts.md), and a triad with the root
    # at the bottom is the chord part rather than a bass line. Before the parts axis
    # this fell out of the arity being the *number of voice names*; the arity is the
    # texture's now, so the rule has to be stated here - and it is the same fact
    # `bass_voice` carries, read once.
    standalone_bass = parts == (PART_BASS,)
    notes = 1 if standalone_bass else comping_arity(
        context.arrangement.texture, parts, context.arrangement.has_thumb
    )
    band = _line_target(context, notes, standalone_bass)
    candidates = _comping_candidates(
        context, harmony,
        notes=notes,
        bass_voice=standalone_bass,
        band=band,
    )
    if not candidates:
        if context.harmony.melody_note is None:
            # The ordinary fallback voices *the melody*, and this slot has none to
            # voice - there is no thin shape to fall back to either, so the chord of
            # the tune cannot be stated here at all. Reported as the hole it is, and
            # the position emitted silent; the next grid position still gets its
            # chance.
            rest_step(arrangements, slot, context, sings_here=False, silence=SILENCE_NO_SHAPE)
            return True
        # No guide-tone shape in a playable position. The chord of the tune is still
        # owed to the band, so fall through to the ordinary melody-bearing route
        # rather than dropping the bar - the same trade `prepare_step` makes when a
        # strategy finds nothing. The guitar plays the tune here, which is a worse
        # answer than a thin one and a better one than silence.
        return False
    # The requested bass note is part of the request here too: a comping shape the thumb
    # cannot reach that beat's note under is not offered, so the chord part moves instead
    # of the line losing a note. A narrowing of what the axis offered, never a widening -
    # see `decisions.leaving_room_for_the_bass`.
    chosen, palette, top_role = _comping_choice(
        arrangements, candidates, context, harmony, slot,
        beats_per_bar=beats_per_bar, band=band,
    )
    _emit_comping_step(arrangements, slot, context, harmony, chosen, palette, top_role=top_role)
    return True
