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

from dataclasses import dataclass
from typing import Callable, Container, List, Mapping, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from . import cost as _cost
from . import grips as _grips
from .bass import (
    BASS_STYLE_AUTO,
    BASS_STYLE_NONE,
    BASS_STYLE_WALK,
    Slot,
    bass_allowed,
    parse_bass_style,
    walking_slots,
)
from .bass_merge import attach_bass, next_resolution_melody
from .chords import (
    NON_CHORD_TONE_STRATEGIES,
    ChordParser,
    normalised_harmony,
    resolve_substitute_harmony,
)
from .decisions import (
    MELODY_ALONE_NO_CHORD,
    MELODY_ALONE_REST,
    MELODY_ALONE_TEXTURE,
    SLASH_BASS_SATISFIED,
    hold_the_melody_string,
    holds_the_shape,
    is_bass_only,
    is_repeated_step,
    melody_alone_case,
    resolve_texture_grips,
    select_step_voicing,
    should_demote_to_melody_alone,
    should_promote_fill,
)
from .grid import GRID_DEFAULT, on_grid, parse_grid, resolve_grid
from .grips import (
    GRIP_MAX_SPAN,
    GRIP_PREFERENCE,
    MELODY_STRING_CHOICES_FULL,
)
from .harmony import (
    HARMONY_AUTO,
    parse_harmony,
    resolve_harmony,
)
from .melody_alone import demoted_to_melody_alone, rescue_melody_alone
from .options import ArrangeOptions
from .parts import (
    PART_BASS,
    PARTS_AUTO,
    parse_parts,
    parts_has_melody_only,
    parts_have_bass,
    parts_have_melody,
    resolve_parts,
)
from .routes import (
    comping_step,
    last_sounding_step,
    no_chord_step,
    rest_step,
    texture_fill_step,
)
from .texture import (
    TEXTURE_STYLES,
    _metric_weight,
    _roles_for_slot,
    derived_arity,
    texture_palette,
)
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    ROLE_TARGET,
    SILENCE_GRID,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    SILENCE_TUNE_SILENT,
    ArrangementStep,
    Palette,
    Voicing,
    _note_name,
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

    candidates: List["Voicing"]
    written_melody: str
    melody: str
    original_melody: Optional[str]
    chord_type: str
    chord_name: str
    is_non_chord_tone: bool
    strategy: Optional[str]
    harmonized_as: Optional[str]


def _resolve_bass(
    texture: str,
    bass: str,
    parts: Tuple[str, ...],
) -> str:
    """The style to actually run: `BASS_STYLE_AUTO` resolved or validated.

    Three outcomes, in the order they are decided:

    - `auto` resolves from the selection, and the shipped answer is **no line**: a
      caller who wants one names the note rules or a `bass:walk` grid row. The one
      case the sentinel writes one is a melody-only selection that also names the
      bass part - `parts="melody,bass"` is the tune with a thumb under it. A
      `parts="bass"` selection alone is **not** melody-only (it has no tune) and keeps
      no thumb: that part already is the bass line, and a thumb under it would double
      it.
    - an unknown rule raises. The same rule as everywhere else in the library: a
      spelling nobody recognises is a question, and answering it by defaulting to a
      walk would put a bass line under an arrangement that did not ask for one.
      `parse_bass_style` owns the vocabulary and the message.
    - a combination the left hand cannot accommodate **raises**. It used to fall back
      to `none` with a warning, and that was the wrong shape for the same reason
      `resolve_harmony` now raises: `none` is what a caller gets by asking for `none`,
      so handing it back for a walk the texture cannot carry is a silent
      substitution. A walking line with gaps in it is worse than no line, so the
      choice between them is the caller's, and the message names a texture that would
      work. Losing the *bass* still costs less than losing the tune - that trade is
      made per beat, by `attach_bass`, where the step survives and the tab says so.

    **The selection is passed rather than the flags derived from it** - the route
    (`voices_have_soprano`), the comping arity (`len(voices)`), the lone-bass case
    and the melody-only case are all decided here from the one fact, so the two
    spellings of one request cannot disagree. Which left-hand shapes an arrangement
    will generate is decided by the selection, and no texture can express it:
    `uniform` is a real grip palette on the melody-bearing route and a
    **meaningless name** on the comping one, where the shapes come from
    `get_comping_voicings`, and inert a third time over on a melody-only selection,
    whose shapes are single frets. So this function asks `bass_allowed` about the
    comping route's capacity when that is the route, the melody-only route's when
    that is, and the texture's otherwise.

    This is why the call site resolves the melody axis **first**. That ordering is
    deliberate rather than incidental - see `arrange_progression`, and note that the two
    resolutions are independent of each other, so swapping them back would only
    reintroduce the bug. What must not change is that both happen *before*
    `has_thumb` is read, because that flag gates whether the walked-beat union is built
    at all.
    """
    melody_voiced = parts_have_melody(parts)
    melody_only = parts_has_melody_only(parts)
    if bass == BASS_STYLE_AUTO:
        # A thumb line is a **combination**, not the default (docs/history/parts.md §9): the
        # shipped answer is no line, and a caller who wants one names a style or a
        # `bass:walk` grid row. The one sentinel case that still writes one is a
        # melody-only selection that names the bass part - the tune with a thumb under
        # it, which is what `parts=melody,bass` means.
        bass = (
            BASS_STYLE_WALK
            if melody_only and parts_have_bass(parts)
            else BASS_STYLE_NONE
        )
    if bass == BASS_STYLE_NONE:
        return bass
    parse_bass_style(bass)  # raises on an unknown rule; the style is validated here
    allowed, reason = bass_allowed(
        parts,
        texture,
        bass,
        # `None` for the melody-bearing route, so `bass_allowed` asks the route's
        # own capacity - the melody-only route's, or the texture's palette.
        # The chord part's arity on the comping one, which is the shape the comping
        # generator will actually build.
        None if melody_voiced else derived_arity(texture, parts),
        parts == (PART_BASS,),
        melody_only=melody_only,
    )
    if not allowed:
        raise ValueError(reason)
    return bass


def _resolve_parts(parts: str) -> Tuple[str, ...]:
    """The parts to actually take: `auto` resolved, parsed, validated.

    Two steps and they are not the same step. **Parsing** turns the caller's string into
    a canonical tuple of part names, so `bass,melody` and `melody,bass` are one request -
    `parts.parse_parts` owns the vocabulary and the canonical order. **Resolution** is
    what `parts.resolve_parts` owns: `auto` becomes every part.

    An unknown part name raises from `parse_parts`, before any voicing work, on the
    library's standing rule: a spelling nobody recognises is a question, and answering it
    by dropping the part would hand back an arrangement missing something nobody asked it
    to drop.
    """
    return resolve_parts(parse_parts(parts))


def _resolve_harmony(
    harmony: str, parts: Tuple[str, ...]
) -> str:
    """The degree family to actually voice: `auto` resolved, parsed, validated.

    The same two-step shape as `_resolve_melody` above - parse, then resolve - because
    it is the same rule about the same thing: `parts` owns the vocabulary and the
    validation, this function owns nothing but the wiring.

    Takes **no texture**, and that is deliberate rather than an oversight: whether a
    degree family can be voiced depends on how many notes were asked for, and on
    nothing about where the notes fall. `guide` under `targets` and `guide` under
    `uniform` are the same two degrees.

    Resolved **once per arrangement**, next to `_resolve_melody` and for the reason
    stated there: the band does not change halfway through a tune.
    """
    return resolve_harmony(parse_harmony(harmony), parts)


def _resolve_grid(grid: str, beats_per_bar: int) -> str:
    """The grid to place chords on: parsed, `auto` resolved, validated.

    The same two-step shape as `_resolve_melody` and `_resolve_harmony` above,
    because it is the same rule about the same kind of thing: `harmony` owns the
    vocabulary and the validation, this function owns only the wiring.

    **Takes the metre rather than a texture**, and that is what distinguishes it from
    `harmony`. Whether a rhythm fits is a property of the metre - `final_and` is the
    upbeat of the last beat whatever the arrangement is doing - so it is resolved
    against `beats_per_bar` and nothing else.
    """
    return resolve_grid(parse_grid(grid), beats_per_bar)


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
    `best_voicing` straight afterwards, and the corpus loader selects the
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

    # Chord-tone match first, quality-only fallback second, across every
    # allowed soprano string and every grip family.
    candidates = _grips.get_all_grip_voicings(
        melody_note, chord_type, chord_name=name,
        top_strings=top_strings, grips=grips,
    )

    # A melody whose best position sits outside the neck window is re-voiced an
    # octave down on the B string. The written pitch is kept in original_melody.
    # Decided before the non-chord-tone strategies run, so a substituted chord
    # is voiced at the transposed pitch too rather than snapping back up.
    #
    # The guard requires candidates to exist: this repositions a voicing that
    # is playable but sits too high. A melody unreachable at the written pitch
    # (C6, fret 20 - past the end of the board) is left alone, because there is
    # no shape to move down and respelling it would hide the real problem.
    sounding_melody = melody_note
    original_melody: Optional[str] = None
    if candidates and _cost._window_penalty(candidates, fret_min, fret_max) > 0:
        octave_down = _grips.get_octave_down_candidates(
            melody_note, chord_type, chord_name=name,
            top_strings=top_strings, grips=grips,
        )
        # Only take the lower octave when it genuinely improves the placement,
        # or a merely slightly out-of-window melody would be moved for nothing.
        here = _cost._window_penalty(candidates, fret_min, fret_max)
        there = _cost._window_penalty(octave_down, fret_min, fret_max)
        if octave_down and there < here:
            candidates = octave_down
            sounding_melody = Note(_note_name(melody_note.midi_note() - 12))
            original_melody = note_str

    strategy_used: Optional[str] = None
    harmonized_as: Optional[str] = None
    is_non_chord_tone = (
        ChordParser.canonical_quality(chord_type) in ChordParser.CHORD_TONES_FROM_ROOT
        and not _chords.is_chord_tone(melody_note, chord_type, name)
    )

    if is_non_chord_tone:
        # Strategy 3 first: holding the shape moves less than any re-voicing.
        if non_chord_tone == "sustain" and previous is not None:
            sustained = _grips.sustain_inner_voices(previous, sounding_melody)
            if sustained is not None:
                candidates = [sustained]
                strategy_used = "sustain"
                harmonized_as = previous_chord

        # Strategies 1 and 2 reharmonise the note as a genuine chord tone.
        if strategy_used is None:
            substitute = resolve_substitute_harmony(
                sounding_melody,
                chord_type,
                name,
                non_chord_tone,
                next_melody=next_resolution_melody(progression, index),
            )
            if substitute is not None:
                substitute_quality, substitute_name = substitute[0], substitute[1]
                substituted = _grips.get_all_grip_voicings(
                    sounding_melody,
                    substitute_quality,
                    chord_name=substitute_name,
                    top_strings=top_strings, grips=grips,
                )
                if substituted:
                    candidates = substituted
                    strategy_used = non_chord_tone
                    harmonized_as = substitute_name

        if strategy_used is None:
            # The strategy is recorded even though it settled nothing, because the line has
            # to name it: "non-chord tone" alone cannot tell a substitution that failed from
            # one that was never attempted. What distinguishes the two is `harmonized_as`,
            # which stays None here - not this field.
            strategy_used = non_chord_tone

    if not candidates:
        return None

    return StepPreparation(
        candidates=candidates,
        written_melody=note_str,
        # The transposed pitch when moved down an octave: the step reports
        # what actually sounds.
        melody=(
            note_str
            if original_melody is None
            else _note_name(sounding_melody.midi_note())
        ),
        original_melody=original_melody,
        chord_type=chord_type,
        chord_name=name,
        is_non_chord_tone=is_non_chord_tone,
        strategy=strategy_used,
        harmonized_as=harmonized_as,
    )


@dataclass(frozen=True)
class _Knobs:
    """The call's knobs, after `options=` and the keywords are reconciled.

    `arrange_progression` takes thirteen knobs twice over - once as keywords and
    once as `ArrangeOptions` fields - and has to decide between them, validate
    them and validate them
    before the loop can start. That prologue is this function's job; the loop then
    unpacks the result straight back into the names it has always used, so the
    extraction changed nothing downstream of it.
    """

    top_strings: Tuple[int, ...]
    non_chord_tone: str
    fret_min: int
    fret_max: int
    texture: str
    bass: str
    parts: str
    harmony: str
    grid: str
    beats_per_bar: int
    beat_type: int
    melody_onsets: Optional[Container[int]]
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]]
    bass_pcs: Optional[Mapping[int, Optional[int]]]
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]]


def _resolve_knobs(
    options: Optional[ArrangeOptions],
    *,
    top_strings: Tuple[int, ...],
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    texture: str,
    bass: str,
    parts: str,
    harmony: str,
    grid: str,
    beats_per_bar: int,
    beat_type: int,
    melody_onsets: Optional[Container[int]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
) -> _Knobs:
    """`options=` and the keywords reconciled into one `_Knobs`.

    `options` and the keywords are two spellings of the same knobs. An `options`
    wins outright rather than being merged field by field: a partial merge would
    make it impossible to tell which of two conflicting values won, and there is
    no use case for "the options, but with one keyword overridden". It raises
    instead of silently preferring one, because a caller who passes both has a
    bug and would otherwise spend an afternoon finding out why their keyword had
    no effect.

    Extracted from `arrange_progression` so the conflict rule and the up-front
    validation - the `non_chord_tone` and `texture` spellings - sit in one place
    rather than at the top of a thousand-line loop. A typo costs a message rather
    than a full arrangement followed by a surprise.
    """
    if options is not None:
        given = {
            name: value
            for name, value in (
                ("top_strings", top_strings),
                ("non_chord_tone", non_chord_tone),
                ("fret_min", fret_min),
                ("fret_max", fret_max),
                ("texture", texture),
                # `bass` is compared here like every other knob, and for the comparison
                # to mean anything the two spellings must be equal when a caller names
                # neither: `ArrangeOptions.bass` and the keyword both default to the
                # `BASS_STYLE_AUTO` sentinel. A field defaulting to the resolved "none"
                # would compare unequal to the sentinel on every call, and reading that
                # resolved field back out of `options` would make the keyword look like a
                # caller who had passed both.
                ("bass", bass),
                ("parts", parts),
                ("harmony", harmony),
                ("grid", grid),
                ("beats_per_bar", beats_per_bar),
                ("beat_type", beat_type),
                ("melody_onsets", melody_onsets),
            )
            if value != ArrangeOptions.__dataclass_fields__[name].default
        }
        if given:
            raise ValueError(
                f"arrange_progression got both options= and the keyword(s) "
                f"{sorted(given)}; pass one or the other, not both"
            )
        top_strings = options.top_strings
        non_chord_tone = options.non_chord_tone
        fret_min = options.fret_min
        fret_max = options.fret_max
        texture = options.texture
        bass = options.bass
        parts = options.parts
        harmony = options.harmony
        grid = options.grid
        beats_per_bar = options.beats_per_bar
        beat_type = options.beat_type
        melody_onsets = options.melody_onsets
        if options.timings is not None:
            timings = list(options.timings)
    bass_pcs = options.bass_pcs if options is not None else None
    slash_bass_cost = options.slash_bass_cost if options is not None else None

    if non_chord_tone not in NON_CHORD_TONE_STRATEGIES:
        raise ValueError(
            f"Unknown non_chord_tone strategy {non_chord_tone!r}; "
            f"expected one of {NON_CHORD_TONE_STRATEGIES}"
        )
    if texture not in TEXTURE_STYLES:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    # Resolved once, here, and passed down: an axis that cannot honour the request
    # raises rather than degrading to a value the caller did not ask for, so what a
    # caller sees is the refusal rather than an arrangement answering a different
    # question.

    return _Knobs(
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
        bass_pcs=bass_pcs,
        slash_bass_cost=slash_bass_cost,
    )


@dataclass(frozen=True)
class _Policies:
    """The axes and the walked-beat union, resolved once per arrangement.

    `parts`/`melody_voiced`/`melody_only` come off the parts axis, `bass` and
    `has_thumb` off the bass policy, `harmony_family` and `grid_pattern` off the
    two comping axes, and `slots` is the walked-beat union when a thumb line is
    running. Resolved up front because the band does not change halfway through a
    tune, and unpacked straight back into the names the loop has always used.
    """

    parts: Tuple[str, ...]
    melody_voiced: bool
    melody_only: bool
    bass: str
    has_thumb: bool
    harmony_family: str
    grid_pattern: str
    slots: Optional[List[Slot]]


def _resolve_policies(
    progression: Sequence[Tuple[Optional[str], str, str]],
    *,
    parts_arg: str,
    texture: str,
    bass: str,
    harmony: str,
    grid: str,
    beats_per_bar: int,
    beat_type: int,
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
) -> _Policies:
    """The axes resolved once per arrangement, plus the walked-beat union.

    Resolved up front rather than per step: the band does not change halfway
    through a tune, and a spelling nobody recognises has to be reported **once**
    rather than never at all on an arrangement where the guitar happens to be
    singing.

    **The melody axis comes before `_resolve_bass` because the bass policy needs
    to know which route the engine is on**, and only this function knows.
    `bass_allowed` measures thumb capacity against `texture.texture_palette`, which
    describes the shapes the melody-bearing route generates and is *inert* on the
    comping one - so asking it about a texture on that route refused a
    combination that is playable and, worse, told the player to change a setting
    that could not affect the result. See `comping_capacity`.

    The two resolutions are independent of each other, so the order between them
    carries no other meaning; what matters is that both finish before `has_thumb`
    is read, because that flag gates whether the walked-beat union is built.
    """
    parts = _resolve_parts(parts_arg)
    melody_voiced = parts_have_melody(parts)
    # The melody-only selection, decided once here and read by the bass policy,
    # the grip resolution and the promotion rule below: `(soprano,)` is the
    # tune alone and `(soprano, bass)` the tune with a thumb under it,
    # whatever `texture=` says - the texture is inert on that route, the same
    # way it is on the comping one.
    melody_only = parts_has_melody_only(parts)

    # The bass policy. `auto` means "whatever this selection means", and the shipped
    # answer is no line at all; a melody-only selection that also names the bass part
    # is the one case that walks. An explicit style overrides both, which is what lets
    # a texture that was never written for a thumb line carry one.
    #
    # The resolved parts are passed rather than the flags derived from them - the
    # route, the arity and the lone-bass case are decided inside, from the selection,
    # so the two spellings of one request cannot disagree.
    bass = _resolve_bass(
        texture,
        bass,
        parts,
    )
    has_thumb = bass != BASS_STYLE_NONE

    # The harmony axis, resolved here for the same reason and read only by the
    # comping route below. Resolving it unconditionally rather than inside
    # `if not melody_voiced` is deliberate: a spelling nobody recognises must be
    # reported **once, up front**, rather than never at all on an arrangement where
    # the guitar happens to be singing - the same argument as `_resolve_melody`'s.
    harmony_family = _resolve_harmony(harmony, parts)
    # The grid axis, resolved here for the same reason and read by **both** routes
    # below rather than only the comping one - unlike `harmony=`, which the guitar
    # singing makes unreachable. A grid says where a chord lands, and that is a
    # question about the part whether the guitar is singing it or comping under a
    # horn, so scoping it to one route would make `grid=` silently inert on a
    # melody-bearing arrangement rather than doing nothing there.
    grid_pattern = _resolve_grid(grid, beats_per_bar)

    slots: Optional[List[Slot]] = None
    if has_thumb:
        # Decision B: the union is built here, before the melody loop, so the
        # loop's index still indexes the skeleton it was given. `walking_slots`
        # is shared with `slots.arrange_slots`, so an imported head and a
        # hand-built progression cannot walk a different line from this one - see
        # its docstring for why that duplication has already cost this project one
        # bug.
        slots = walking_slots(
            progression, timings, beats_per_bar, beat_type, bass
        )

    return _Policies(
        parts=parts,
        melody_voiced=melody_voiced,
        melody_only=melody_only,
        bass=bass,
        has_thumb=has_thumb,
        harmony_family=harmony_family,
        grid_pattern=grid_pattern,
        slots=slots,
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
    *,
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
    arrangements: List[ArrangementStep],
    top_strings: Tuple[int, ...],
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    slot_grips: Tuple[str, ...],
    texture: str,
    role: str,
    has_thumb: bool,
    melody_only: bool,
) -> Optional[StepPreparation]:
    """Re-prepare a fill that produced nothing as a principal note.

    A fill slot with nothing thin to play must not lose the chord of the tune -
    the whole point of the texture is a lighter *texture*, never a missing
    harmony. Same argument as `NECK_FRET_MIN` being a penalty and not a filter.
    `decisions.should_promote_fill` decides whether this step gets the retry.

    The retry is prepared against the **whole** search space, not the

    Returns the promoted preparation, or **None** when the texture does not ask
    for the retry or the retry found nothing either - the two cases the caller
    answers the same way, by reporting the step as skipped.
    """
    if not should_promote_fill(
        texture, role, True, slot_grips,
        has_thumb=has_thumb,
        melody_only=melody_only,
    ):
        return None
    prev_sounding = last_sounding_step(arrangements)
    return prepare_step(
        progression, index,
        # The last *sounding* shape, not the step before this one: a silent
        # position is a hole in the tab rather than a shape the hand held.
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        previous_chord=prev_sounding.chord if prev_sounding is not None else None,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
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
    *,
    previous: Optional[Voicing],
    fret_min: int,
    fret_max: int,
    allowed_tones: Optional[Container[int]],
    root_pc: Optional[int],
    melody_pc: Optional[int],
    bass_pc: Optional[int] = None,
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]] = None,
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
        return _cost.voicing_cost(
            voicing,
            previous,
            fret_min,
            fret_max,
            allowed_tones=allowed_tones,
            root_pc=root_pc,
            melody_pc=melody_pc,
        )

    available = max(len(candidate.active_frets()) for candidate in candidates)
    inside_window = any(
        all(fret_min <= fret <= fret_max for fret in candidate.active_frets())
        for candidate in candidates
    )
    chosen_voices = len(chosen.active_frets())
    fuller = [c for c in candidates if len(c.active_frets()) > chosen_voices]
    if not fuller:
        return Palette(available=available, inside_window=inside_window)
    alternative = min(fuller, key=cost)
    decided_by = _cost.decisive_criterion(cost(chosen), cost(alternative))
    if _lost_to_the_bass_partition(chosen, alternative, bass_pc, slash_bass_cost):
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


def _harmonised_step(
    arrangements: List[ArrangementStep],
    slot: Slot,
    *,
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
    top_strings: Tuple[int, ...],
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    slot_grips: Tuple[str, ...],
    texture: str,
    has_thumb: bool,
    melody_only: bool,
    name: str,
    note_str: Optional[str],
    melody_note: Optional[Note],
    bass_pcs: Optional[Mapping[int, Optional[int]]],
    slash_bass_cost_for: Optional[Callable[[Sequence[int], Optional[int]], int]],
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
) -> None:
    """The melody-bearing route: pin the tune, and voice the chord under it.

    Reached when the guitar *sings* the slot - or when every other route declined
    it - so a note is pinned by the `assert` below. This is the route the whole
    library is built around: `prepare_step` supplies the candidates, `voicing_cost`
    picks among them, and the last resort before silence is the melody alone.
    """
    assert melody_note is not None and note_str is not None
    # Everything up to choosing a shape is shared with the corpus loader,
    # which needs the same candidates but honours a slash bass first. See
    # prepare_step.
    #
    # The previous shape is the last *sounding* one: a silent position between
    # here and the previous chord is a hole in the tab, not a shape the hand
    # held - see `last_sounding_step`.
    prev_sounding = last_sounding_step(arrangements)
    prepared = prepare_step(
        progression, index,
        previous=prev_sounding.voicing if prev_sounding is not None else None,
        previous_chord=prev_sounding.chord if prev_sounding is not None else None,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        grips=slot_grips,
    )
    if prepared is None:
        # The tune is never dropped while it can be played at all: play it
        # alone first, then promote the fill, and only then report the step
        # missing. See `rescue_melody_alone` and `_promoted_fill`.
        if rescue_melody_alone(
            arrangements, slot,
            name=name, note_str=note_str, melody_note=melody_note,
            top_strings=top_strings, previous=_previous_shape(arrangements),
            bar=bar, beat=beat, duration=duration,
            role=role, weight=weight,
        ):
            return
        prepared = _promoted_fill(
            progression=progression, index=index,
            arrangements=arrangements, top_strings=top_strings,
            non_chord_tone=non_chord_tone,
            fret_min=fret_min, fret_max=fret_max,
            slot_grips=slot_grips, texture=texture,
            role=role, has_thumb=has_thumb, melody_only=melody_only,
        )
        if prepared is None:
            # Reached only when the melody **cannot be played at all** - the
            # rescue above has already been tried, and answered None because no
            # string reaches the note (below the library's G3 floor, or past the
            # end of the board).
            #
            # The palette is named because it is the usual cause and the caller
            # is the only one who can change it, and the message says the step is
            # *skipped* because that is what happens to the note. Naming a family
            # the caller never asked for, or wording it like a fallback that had
            # happened, would both misdescribe the step.
            # The reason, told apart at the source: no string reaches the
            # written pitch at all (`out_of_reach`) versus a reachable melody
            # under a chord nothing could voice (`no_shape`). The rescue above
            # asked the same question, so the answer is read back rather than
            # re-derived from the clause's own words.
            rest_step(
                arrangements, slot,
                name=name, note_str=note_str,
                bar=bar, beat=beat, duration=duration,
                role=role, weight=weight,
                sings_here=False,
                silence=(
                    SILENCE_OUT_OF_REACH
                    if not _grips.get_melody_only_voicings(
                        melody_note, prefer=top_strings
                    )
                    else SILENCE_NO_SHAPE
                ),
            )
            return
        role = ROLE_TARGET
    candidates = prepared.candidates
    chord_type = prepared.chord_type
    name = prepared.chord_name
    original_melody = prepared.original_melody
    strategy_used = prepared.strategy
    harmonized_as = prepared.harmonized_as
    is_non_chord_tone = prepared.is_non_chord_tone

    # A melody that did not move is a **hold**: the previous shape is still ringing,
    # so only the harmony under it changes. The candidates are therefore narrowed to
    # the string the melody is already on *before* the selector sees them, which is a
    # filter over a list rather than a new cost criterion - ranking a hold above a
    # jump cannot stop the jump, because both are legal shapes, and `span` outranks
    # position in the tuple precisely so the hand stays put. The rule, and the reason
    # it comes back empty-handed rather than starving a thin palette, is
    # decisions.hold_the_melody_string.
    #
    # `harmony` is computed once here and used for the `repeated` flag below, so "the
    # note did not move" cannot mean two different things in one step.
    harmony = normalised_harmony(name, harmonized_as)
    prev_step = arrangements[-1] if arrangements else None
    if prev_step is not None and holds_the_shape(
        prev_step, Note(prepared.melody).midi_note(), harmony
    ):
        candidates = hold_the_melody_string(candidates, prev_step)

    # The whole selection rule lives in voicing_cost. The first chord has no
    # previous shape to lead from, so it falls back to "somewhere comfortable on
    # the neck"; every later chord is scored against the one before it, which is
    # what keeps the hand from jumping and lets a melody hold its place by
    # changing strings.
    # The shape the selector leads *from* is the last sounding one, not the step
    # before this one: a silent position is a hole in the tab rather than a shape
    # the hand held (`last_sounding_step`). `prev_step` above stays
    # `arrangements[-1]`, because a hold is about what is *ringing* - and a rest
    # stops the ringing, whether it is the grid's or a position the guitar
    # declined.
    prev_voicing = prev_sounding.voicing if prev_sounding is not None else None
    # The tones the *written* chord allows, so the selector can prefer a
    # shape that is merely out of position over one that sounds a wrong note.
    # The root enables the bass-function tie-break in voicing_cost; it is None
    # for a chord whose name cannot be parsed, which simply leaves that
    # criterion unasked rather than guessing a bass.
    #
    # The tones are those of the chord **actually sounding**, which is
    # `harmonized_as` where a non-chord-tone strategy substituted one. Scoring
    # the substitute against the written chord asked the wrong question: a
    # Bdim7 voicing under a written Cmaj7 is three foreign notes and every
    # candidate alike, so criterion 0 could not separate them and `missing` then
    # picked a three-note shell over the complete Bdim7 drop-2 that was
    # generated and correct. The step sounded D4-Ab4-D5 - two tones of Bdim7
    # rather than four - under a strategy whose whole purpose is to state the
    # substituted chord.
    #
    # `harmonized_as` is a chord *name* ("Bdim7"), not a quality, so it is
    # parsed rather than passed to `canonical_quality` directly: that returns
    # the whole name unchanged for an unrecognised spelling, and
    # `get_chord_tones` then yields an empty set, which silently switches the
    # criterion off rather than asking it the right question.
    substitute = harmonized_as if harmonized_as is not None else name
    _sub_root, sub_quality = ChordParser.parse_chord_name(substitute)
    if sub_quality is None:
        sub_quality = ChordParser.canonical_quality(chord_type)
        substitute = name
    allowed_tones = ChordParser.get_chord_tones(sub_quality, substitute)
    root_pc = _grips._chord_context(chord_type, name)[1]
    # The melody is the caller's note and is never rewritten, so when it
    # lies outside the chord every candidate is impure on it. Excluding it
    # lets a shape that adds no *other* wrong note reach zero - see
    # cost.voicing_cost, where counting rather than flagging makes the
    # difference between one wrong note and four.
    melody_pc = melody_note.midi_note() % 12
    bass_pc = None if bass_pcs is None else bass_pcs.get(index)
    best_voicing = select_step_voicing(
        candidates,
        prev_voicing,
        fret_min,
        fret_max,
        allowed_tones=allowed_tones,
        root_pc=root_pc,
        melody_pc=melody_pc,
        bass_pc=bass_pc,
        slash_bass_cost=slash_bass_cost_for,
    )
    # `candidates` is non-empty here (the step is skipped otherwise), so this
    # cannot fire. Written as an assertion rather than left to Optional
    # narrowing at every use below.
    assert best_voicing is not None
    def palette_facts_for(chosen: Voicing) -> Palette:
        """`_palette_facts` with this slot's context bound: what was on offer besides
        `chosen`, and the criterion that ranked it below the better one.

        A nested function because it is asked twice - once for the shape the selector
        picked, and again if a rule below replaces it - and the second answer has to be
        about the shape the step carries. A record about a shape the step does not
        carry is a second source for one fact, and the wrong one.
        """
        return _palette_facts(
            candidates,
            chosen,
            previous=prev_voicing,
            fret_min=fret_min,
            fret_max=fret_max,
            allowed_tones=allowed_tones,
            root_pc=root_pc,
            melody_pc=melody_pc,
            bass_pc=bass_pc,
            slash_bass_cost=slash_bass_cost_for,
        )

    palette = palette_facts_for(best_voicing)

    # A complete chord at the very top of the span budget is demoted to
    # the melody alone. Why that is a fallback rather than a re-ranking is
    # documented once in decisions.should_demote_to_melody_alone.
    #
    # **Only when nothing narrower was generated *that the demoted shape did not
    # outrank*.** The rule's premise is that the *palette* offered nothing inside the
    # budget - the shape it names spans the whole thing because no alternative was a
    # candidate to be ranked against. That premise is now checkable, because a palette
    # derived from the arity offers more families than the hand-written lists did:
    # where a four-note shape inside the budget was also generated, demoting threw the
    # whole chord away.
    #
    # **The narrower shape must tie with the demoted one on every criterion that
    # outranks span** - that is what makes this a fallback rather than a re-ranking,
    # and the comparison is the tuple's own prefix rather than a hand-written list.
    # Without it the filter silently *re-ranks*: on `Am7` under D5 the palette also
    # holds a span-0 shape sounding F4, which the tuple puts below the span-5 shape on
    # criterion 0 (a note outside the chord) - so re-selecting within the budget
    # would trade a pure five-fret reach for an impure chord, exactly the trade
    # `should_demote_to_melody_alone` says the tuple would never make. Measured on the
    # committed heads: without the span tie, 23 `uniform` steps move; with it,
    # `uniform` is byte-identical and only the textures whose palette grew move.
    #
    # **Inside the neck window as well**, and both halves are load-bearing. A candidate
    # that is merely tighter while sitting at fret 14 is not the alternative the rule
    # was written for: the demotion demotes a shape that is *unplayable*, and trading it
    # for one out of position is a different bad trade. Measured on the committed heads,
    # both halves earn their place: without the span test 30 `targets` steps lose three
    # notes each, and without the window test the A-7 of `MAJOR_CADENCE` trades its
    # pinned melody-alone step for a shape at fret 14 (`docs/history/fingering.md` §4.4's ban is
    # why nothing else fits there).
    if should_demote_to_melody_alone(best_voicing, role):
        turned_away = _cost.voicing_cost(
            best_voicing, prev_voicing, fret_min, fret_max,
            allowed_tones=allowed_tones, root_pc=root_pc, melody_pc=melody_pc,
        )
        # The comparison is the tuple **with the span element removed**, which is the
        # honest form of "the tuple would have chosen it anyway": everything the
        # ranking says except the one criterion the demotion exists for. Keeping the
        # element in would let the re-selection trade position, inner-voice movement
        # or the written bass for span - a re-ranking after all, and measured at two
        # `heres_that_rainy_day` steps whose `Bb7/F` slots would come back at a worse
        # fret for a tighter hand.
        span = _cost.SPAN_CRITERION
        # The **partition** is not part of the tuple and it outranks all of it: the
        # selector groups the candidates by how well they honour a written slash bass
        # and only then ranks within the best group. So a narrower shape may only
        # replace the demoted one from the **same group** - a shape that drops the
        # written bass for a tighter hand is the same bad trade as dropping it for
        # position, and this is the test that catches it.
        turned_away_bass = _bass_group(
            best_voicing, bass_pc, slash_bass_cost_for
        )

        def would_the_tuple_have_chosen_it(candidate: Voicing) -> bool:
            if _bass_group(candidate, bass_pc, slash_bass_cost_for) != turned_away_bass:
                return False
            cost = _cost.voicing_cost(
                candidate, prev_voicing, fret_min, fret_max,
                allowed_tones=allowed_tones, root_pc=root_pc, melody_pc=melody_pc,
            )
            return cost[:span] + cost[span + 1:] <= turned_away[:span] + turned_away[span + 1:]

        inside_budget = [
            candidate for candidate in candidates
            if candidate.fret_span() < GRIP_MAX_SPAN[best_voicing.grip]
            and all(fret_min <= fret <= fret_max
                    for fret in candidate.active_frets())
            and would_the_tuple_have_chosen_it(candidate)
        ]
        narrower = (
            select_step_voicing(
                inside_budget,
                prev_voicing,
                fret_min,
                fret_max,
                allowed_tones=allowed_tones,
                root_pc=root_pc,
                melody_pc=melody_pc,
                bass_pc=bass_pc,
                slash_bass_cost=slash_bass_cost_for,
            )
            if inside_budget else None
        )
        if narrower is not None:
            best_voicing = narrower
            palette = palette_facts_for(best_voicing)
        elif demoted_to_melody_alone(
            arrangements, slot,
            name=name, note_str=note_str, melody_note=melody_note,
            top_strings=top_strings, previous=prev_voicing,
            best_voicing=best_voicing,
            palette=palette,
            bar=bar, beat=beat, duration=duration,
            role=role, weight=weight,
        ):
            return
    # A repeated melody is a hold, so the renderers strike the soprano alone and
    # keep the inner voices ringing - and the shape was chosen on the string that
    # makes that true. The rule - the harmony-change case that is not a hold, and
    # the string clause - is decisions.is_repeated_step.
    repeated = is_repeated_step(prev_step, best_voicing, harmony)

    arrangements.append(ArrangementStep(
        chord=name,
        # The transposed pitch when the step was moved down an octave, so the
        # step reports what actually sounds; original_melody keeps the written one.
        melody=prepared.melody,
        voicing=best_voicing,
        palette=palette,
        non_chord_tone=is_non_chord_tone,
        strategy=strategy_used,
        harmonized_as=harmonized_as,
        original_melody=original_melody,
        repeated=repeated,
        # A shell or a duo leaves part of the chord unsounded, so the chord name
        # printed above the step describes the harmony rather than every note in
        # it. The renderers annotate this.
        #
        # Counted over the **upper voices**: the thumb is merged after this, so
        # a shell plus a bass note is still a shell and stays annotated
        # "(shell - 3rd & 7th, partial)". The merge happens below, which is what
        # makes that true by ordering rather than by a second count.
        partial=len(best_voicing.active_frets()) < 4,
        bar=bar,
        beat=beat,
        duration=duration,
        role=role,
        metric_weight=weight,
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
    # Select first, merge after: the bass is written into the fret vector only
    # once `best_voicing` has returned, so it cannot enter the cost tuple by
    # construction rather than by discipline.
    attach_bass(arrangements[-1], slot.bass, arrangements)


@dataclass
class _Carried:
    """What one iteration of the step loop leaves behind for the next.

    The only state the loop carries: the last harmony a *target* stated, and the
    last melody pitch that sounded. Both are read from what actually sounds, not
    from the written chord, so a substituted chord compares as itself (the same
    `normalised_harmony` the `repeated` hold uses).
    """

    last_target_harmony: Optional[Tuple[Optional[str], Optional[str]]] = None
    previous_melody_midi: Optional[int] = None


@dataclass(frozen=True)
class _SlotPlan:
    """One slot's decisions, made before any route is chosen.

    Built by `_slot_state`, which refuses a slot outright by returning None. The
    routes read this rather than recomputing anything, so the metric weight, the
    role, the texture grips and the melody-alone kind are each decided once.
    """

    index: int
    note_str: Optional[str]
    chord_type: str
    name: str
    melody_note: Optional[Note]
    sings_here: bool
    bar: Optional[int]
    beat: Optional[float]
    duration: Optional[float]
    weight: int
    role: str
    slot_grips: Tuple[str, ...]
    melody_alone: str
    # Why a `MELODY_ALONE_REST` step sounds nothing, one of the SILENCE_* constants.
    # Defaults to the grid's answer, which is the only reason the loop's rest route
    # fired before the melody-only refusal learned to emit a step of its own.
    silence: str = SILENCE_GRID


def _slot_state(
    car: _Carried,
    slot: Slot,
    *,
    progression: Sequence[Tuple[Optional[str], str, str]],
    texture: str,
    parts: Tuple[str, ...],
    has_thumb: bool,
    melody_only: bool,
    melody_voiced: bool,
    melody_onsets: Optional[Container[int]],
    grid_pattern: str,
    beats_per_bar: int,
) -> Optional[_SlotPlan]:
    """One slot's decisions, and the one refusal that ends a slot here.

    Returns a **silent plan** for a position a melody-only selection has nothing
    to play: the step is still emitted (`MELODY_ALONE_REST` with
    `silence=SILENCE_TUNE_SILENT`) so the tab keeps its line-up. Otherwise the
    plan carries everything the routes need, and the two values on `car` are
    updated in place.
    """
    index = slot.index
    note_str, chord_type, name = progression[index]
    if note_str is None:
        if melody_only:
            # A melody-only selection plays the tune and nothing else, so a
            # position with no note has nothing for the guitar to play. The
            # position is still **emitted**, silent: the tab keeps its bar
            # count and its line-up against the band, and `tune_silent` is
            # what the line says rather than the grid's own reason.
            #
            # It is kept as the only *early* answer here because §9.3 step D
            # made the other case a real one: a *singing* selection (soprano
            # named) now receives note-less slots from the grid union - positions
            # the tune is silent at - and the guitar **comps** them rather than
            # being refused, which is why they fall through to the comping
            # branch below.
            bar, beat, duration = slot.bar, slot.beat, slot.duration
            weight = _metric_weight(bar, beat, beats_per_bar)
            # The role the slot would have had, read without committing to
            # `car`: a refused slot must not move the target or the tracked
            # pitch that a later slot is judged against, so the two `car`
            # writes further down stay where they are.
            role = _roles_for_slot(
                weight,
                texture,
                harmony_changed=(
                    car.last_target_harmony is None
                    or normalised_harmony(name) != car.last_target_harmony
                ),
                melody_moves=False,
                has_thumb=has_thumb,
                melody_only=melody_only,
            )[0]
            return _SlotPlan(
                index=index,
                note_str=note_str,
                chord_type=chord_type,
                name=name,
                melody_note=None,
                sings_here=False,
                bar=bar,
                beat=beat,
                duration=duration,
                weight=weight,
                role=role,
                slot_grips=(),
                melody_alone=MELODY_ALONE_REST,
                silence=SILENCE_TUNE_SILENT,
            )
        melody_note = None
    else:
        melody_note = Note(note_str)

    # **Does the guitar sing *this* slot?** (§9.3 step D: the soprano is per
    # slot, not per route.) The guitar sings a slot only where its voice
    # selection has a soprano *and* the slot is a melody **onset** - a written
    # note articulating here. Every other slot it comps, except on a melody-only
    # selection, whose note-less slots were skipped above.
    #
    # §9.2's onset signal is reused rather than re-derived: `melody_onsets` is
    # the same set the comping route's reharmonise guard reads, and a grid
    # position the tune merely *sustains* through is not an onset, so the guitar
    # states the chord there rather than re-articulating a note it did not begin
    # - which is why a note-bearing merged position still comps. `None` means
    # every slot is an onset, the honest default for a hand-built progression
    # with no timeline, which keeps a bare `arrange_progression` unchanged.
    sings_here = (
        melody_voiced
        and melody_note is not None
        and (melody_onsets is None or index in melody_onsets)
    )

    # Where this slot falls in the bar, and therefore what it is for. Read
    # defensively, exactly as slots.arrange_slots guards its own timings: a
    # short list leaves the trailing steps unlocated, and an unlocated step is
    # a principal note rather than a fill. The bar and beat are also stamped
    # onto the step, because a caller that supplied the rhythm wants to read it
    # back off the result rather than have to correlate two lists.
    bar, beat, duration = slot.bar, slot.beat, slot.duration
    weight = _metric_weight(bar, beat, beats_per_bar)
    # _roles_for_slot re-validates the texture, which is harmless: the table was
    # already checked before the loop, so this cannot raise here.
    #
    # Under `targets` a strong beat is only a target when something new
    # happens on it: a different harmony from the last target's (the off-beat
    # change rule), or the melody actually moving onto it (decision F, which is
    # what lets the second bar of a two-bar chord restate its shell when the
    # player re-articulates the line there and stay thin when they do not).
    harmony_key = normalised_harmony(name)
    # A silent slot moves nothing onto the beat: `melody_moves` is False, and
    # the tracked pitch clears to None so the next onset reads as the melody
    # arriving there - a fresh attack after silence counts as movement, which
    # is what the placeholder's C4 accidentally produced for the slot *after*
    # a rest, minus its false claim about the silent slot itself.
    melody_moves = (
        melody_note is not None
        and (car.previous_melody_midi is None
             or melody_note.midi_note() != car.previous_melody_midi)
    )
    role = _roles_for_slot(
        weight,
        texture,
        harmony_changed=(car.last_target_harmony is None
                         or harmony_key != car.last_target_harmony),
        melody_moves=melody_moves,
        has_thumb=has_thumb,
        melody_only=melody_only,
    )[0]
    if role == ROLE_TARGET:
        car.last_target_harmony = harmony_key
    car.previous_melody_midi = (
        melody_note.midi_note() if melody_note is not None else None
    )
    # The texture decides which grips are *available* on this step. It is not a
    # term in the cost, so a fill cannot be outbid for being in position - the
    # point is that fewer notes are played here, not that this shape is better.
    # The narrowing rule itself, and why the default is not an intersection,
    # are documented once in decisions.resolve_texture_grips.
    #
    # A melody-only selection never asks: the left hand plays nothing on
    # every slot, whatever the texture's palettes say, so the loop hands an
    # empty palette straight through. Skipping the resolution is what
    # makes `texture=` silently inert here rather than noisily so.
    slot_grips = (
        ()
        if melody_only
        else resolve_texture_grips(
            role,
            texture_palette(role, texture, parts, has_thumb),
            # The right hand's budget, and a fact about *this slot* rather than
            # about the arrangement: a target may sound three strings only where
            # a bass note is actually being placed under it, which is what
            # `slot.bass` says. `has_thumb` alone would thin chords the thumb
            # never plays under - `--bass-style root` leaves most slots bare.
            has_thumb=has_thumb and slot.bass is not None,
        )
    )

    # A slot that is played as a single note rather than looked up. Which
    # slots those are, and why each is a branch rather than a missing case,
    # is decisions.melody_alone_case. It returns a *kind*, because the three
    # non-default routes build different steps: an NC bar sets
    # `melody_only=True`, a texture case must not, and an off-grid slot on the
    # comping route is a rest with no notes in it at all.
    #
    # `on_grid` is read from the **slot's own beat**, not from the bar it sits
    # in: the grid is bar-relative, so the same beat number means different
    # positions in different bars of different metres, and `grid.on_grid`
    # is the one place that knows the metre.
    #
    # `melody_voiced` here is the **per-slot** `sings_here`, not the route: a
    # slot the guitar does not sing (no soprano, or no note at this position)
    # takes the comping-route branches inside `melody_alone_case`, so an
    # off-grid note-less slot rests rather than asserting a melody it has not
    # got. §9.3 step D.
    melody_alone = melody_alone_case(
        texture, role, slot_grips, chord_type, name, has_thumb,
        melody_voiced=sings_here,
        on_grid=on_grid(beat, grid_pattern, beats_per_bar),
    )
    return _SlotPlan(
        index=index,
        note_str=note_str,
        chord_type=chord_type,
        name=name,
        melody_note=melody_note,
        sings_here=sings_here,
        bar=bar,
        beat=beat,
        duration=duration,
        weight=weight,
        role=role,
        slot_grips=slot_grips,
        melody_alone=melody_alone,
    )


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
    _k = _resolve_knobs(
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

    _p = _resolve_policies(
        progression,
        # `_k.parts` rather than the keyword `parts`, and that is not a style choice:
        # `_resolve_knobs` is what reads `options.parts`, so passing the raw keyword
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
    # What one step tells the next; see `_Carried`.
    carried = _Carried()

    # One slot per triple, carrying that triple's own `(bar, beat, duration)` or
    # None for a slot nobody located. Read defensively - a short `timings` leaves
    # the trailing steps unlocated - and, importantly, tolerating a *present but
    # empty* entry: the corpus normalises its unplaced slots to `(None, None, None)`,
    # so `float(beat)` here has to cope with None or the head path raises the
    # moment it is allowed to delegate. That is the fourth time the two paths'
    # differing timing types have cost something, and the first time it was a
    # crash rather than a signature that would not typecheck.
    def _timing(index: int) -> Tuple[Optional[int], Optional[float], Optional[float]]:
        if timings is None or index >= len(timings):
            return (None, None, None)
        bar, beat, duration = timings[index]
        return (
            bar,
            None if beat is None else float(beat),
            duration,
        )

    loop: List[Slot] = (
        slots if slots is not None
        else [
            Slot(index=index, bar=bar, beat=beat, duration=duration)
            for index, (bar, beat, duration) in enumerate(
                _timing(i) for i in range(len(progression))
            )
        ]
    )

    for slot in loop:
        plan = _slot_state(
            carried, slot,
            progression=progression,
            texture=texture,
            parts=chosen_parts,
            has_thumb=has_thumb,
            melody_only=melody_only,
            melody_voiced=melody_voiced,
            melody_onsets=melody_onsets,
            grid_pattern=grid_pattern,
            beats_per_bar=beats_per_bar,
        )
        if plan is None:
            continue

        if plan.melody_alone == MELODY_ALONE_REST:
            rest_step(
                arrangements, slot,
                name=plan.name, note_str=plan.note_str,
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight,
                sings_here=plan.sings_here, silence=plan.silence,
            )
            continue
        if plan.melody_alone == MELODY_ALONE_TEXTURE:
            if texture_fill_step(
                arrangements, slot,
                name=plan.name, note_str=plan.note_str,
                melody_note=plan.melody_note, top_strings=top_strings,
                previous=_previous_shape(arrangements),
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight,
            ):
                continue

        if plan.melody_alone == MELODY_ALONE_NO_CHORD:
            no_chord_step(
                arrangements, slot,
                name=plan.name, note_str=plan.note_str,
                melody_note=plan.melody_note, top_strings=top_strings,
                previous=_previous_shape(arrangements),
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight,
            )
            continue

        # --- The comping route: the guitar harmonises, somebody else sings ---
        # See `comping_step`: taken before `prepare_step` because there is no
        # melody for the guitar here, and only after the NC and melody-alone
        # branches, which are the cases with no harmony to state.
        if not plan.sings_here and not melody_only:
            if comping_step(
                arrangements, slot,
                progression=progression, index=plan.index,
                chord_type=plan.chord_type, name=plan.name,
                note_str=plan.note_str, melody_note=plan.melody_note,
                melody_onsets=melody_onsets,
                parts=chosen_parts, texture=texture, has_thumb=has_thumb,
                harmony_family=harmony_family,
                non_chord_tone=non_chord_tone,
                fret_min=fret_min, fret_max=fret_max,
                bass_pcs=bass_pcs, slash_bass_cost_for=slash_bass_cost_for,
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight,
            ):
                continue

        # Every melody-bearing route below pins a note, and a slot with none has
        # left the loop by now: the guard at the top refuses one the guitar is
        # asked to sing, and the comping block above always steps or continues.
        _harmonised_step(
            arrangements, slot,
            progression=progression, index=plan.index,
            top_strings=top_strings, non_chord_tone=non_chord_tone,
            fret_min=fret_min, fret_max=fret_max,
            slot_grips=plan.slot_grips, texture=texture,
            has_thumb=has_thumb, melody_only=melody_only,
            name=plan.name, note_str=plan.note_str,
            melody_note=plan.melody_note,
            bass_pcs=bass_pcs, slash_bass_cost_for=slash_bass_cost_for,
            bar=plan.bar, beat=plan.beat, duration=plan.duration,
            role=plan.role, weight=plan.weight,
        )

    return arrangements
