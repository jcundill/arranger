"""The step loop: one progression in, one arrangement out.

`arrange_progression` is the entry point and `prepare_step` its one-step
counterpart. Between them they turn `(melody, quality, name)` triples into
`ArrangementStep`s, dispatching each slot to one of five routes - a rest, a
texture fill, a no-chord melody-alone step, a comping shape, or a harmonised
melody step - and merging the walking bass in afterwards.

Every step body lives here; `VoiceLeadingEngine` is a facade of one-line delegates
onto them. There is no state to move, so this module imports `grips`, `cost`,
`chords` and the rest directly and does not import `steps` at all.
`slots.arrange_slots` delegates through the class, so the imported-head path and the
hand-built one still run one loop rather than two.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Container, Dict, List, Mapping, Optional, Sequence, Tuple

from musthe import Note

from . import chords as _chords
from . import cost as _cost
from . import grips as _grips
from .bass import (
    BASS_AUTO,
    BASS_NONE,
    BASS_STYLES,
    BASS_WALK,
    BassNote,
    _held_shape,
    _place_bass,
    _previous_bass,
    _Slot,
    _walking_slots,
    bass_allowed,
)
from .chords import (
    NON_CHORD_TONE_STRATEGIES,
    ChordParser,
    normalised_harmony,
)
from .decisions import (
    MELODY_ALONE_NO_CHORD,
    MELODY_ALONE_REST,
    MELODY_ALONE_TEXTURE,
    is_bass_only,
    is_repeated_step,
    melody_alone_case,
    resolve_texture_grips,
    select_step_voicing,
    should_demote_to_melody_alone,
    should_promote_fill,
)
from .diagnostics import Diagnostics, default_diagnostics
from .grips import (
    GRIP_PREFERENCE,
    MELODY_STRING_CHOICES_FULL,
)
from .options import ArrangeOptions
from .textures import (
    GRID_EVERY_NOTE,
    HARMONY_AUTO,
    HARMONY_SHELL_ROOT,
    MELODY_AUTO,
    MELODY_BASS,
    MELODY_SOPRANO,
    TEXTURE_GRIPS,
    TEXTURE_STYLES,
    THUMB_TEXTURES,
    _metric_weight,
    _roles_for_slot,
    melody_only_selection,
    on_grid,
    parse_grid,
    parse_harmony,
    parse_voices,
    resolve_grid,
    resolve_harmony,
    resolve_voices,
    voices_have_soprano,
)
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    NO_CHORD,
    PITCH_CLASS_NAMES,
    ROLE_TARGET,
    STANDARD_TUNING,
    ArrangementStep,
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
    calls `_best_voicing` directly silently skips the non-chord-tone strategies,
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
    voices: Tuple[str, ...],
    diagnostics: Diagnostics,
) -> str:
    """The policy to actually run: `BASS_AUTO` resolved, validated, or refused.

    Three outcomes, in the order they are decided:

    - `auto` resolves from the texture and the selection. `texture="walking_bass"`
      walks; so does a melody-only selection that names the bass voice -
      `melody="soprano,bass"` is the tune with a thumb under it, the part the
      `melody_bass` texture spells. A lone `bass` selection is **not**
      melody-only (it has no soprano) and keeps no thumb: that part already is the
      bass line, and a thumb under it would double it.
    - an unknown spelling raises. The same rule as everywhere else in the library: a
      policy nobody recognises is a question, and answering it by defaulting to a walk
      would put a bass line under an arrangement that did not ask for one.
    - a combination the left hand cannot accommodate is **refused with a warning**, and
      the arrangement proceeds without a thumb line. Not dropped and not degraded: a
      walking line with gaps in it is worse than no line, and losing the bass costs less
      than losing the tune. The warning names a texture that would work.

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
    melody_voiced = voices_have_soprano(voices)
    melody_only = melody_only_selection(voices)
    if bass == BASS_AUTO:
        bass = (
            BASS_WALK
            if texture in THUMB_TEXTURES
            or (melody_only and MELODY_BASS in voices)
            else BASS_NONE
        )
    if bass not in BASS_STYLES:
        raise ValueError(
            f"Unknown bass policy {bass!r}; expected one of {BASS_STYLES}, "
            f"or 'auto'"
        )
    allowed, reason = bass_allowed(
        texture,
        bass,
        # `None` for the melody-bearing route, so `bass_allowed` asks the route's
        # own capacity - the melody-only route's, or the texture's palette.
        # `len(voices)` on the comping one, which is the arity the comping
        # generator will actually build.
        None if melody_voiced else len(voices),
        voices == (MELODY_BASS,),
        melody_only=melody_only,
    )
    if not allowed:
        diagnostics.warn(f"Warning: {reason}")
        return BASS_NONE
    return bass


def _resolve_melody(voices: str) -> Tuple[str, ...]:
    """The voices to actually play: `auto` resolved, parsed, validated.

    Two steps and they are not the same step. **Parsing** turns the caller's string into a
    canonical tuple of voice names, so `tenor,alto` and `alto,tenor` are one request -
    `textures.parse_voices` owns the vocabulary and the ordering. **Resolution** is what
    `textures.resolve_voices` owns: `auto` becomes every voice.

    An unknown voice name raises from `parse_voices`, before any voicing work, on the
    library's standing rule: a spelling nobody recognises is a question, and answering it
    by dropping the voice would hand back a part missing something nobody asked it to drop.
    """
    return resolve_voices(parse_voices(voices))


def _resolve_harmony(
    harmony: str, voices: Tuple[str, ...], diagnostics: Diagnostics
) -> str:
    """The degree family to actually voice: `auto` resolved, parsed, or refused.

    The same two-step shape as `_resolve_melody` above - parse, then resolve - because
    it is the same rule about the same thing: `textures` owns the vocabulary and the
    refusal, this function owns nothing but the wiring.

    Takes **no texture**, and that is deliberate rather than an oversight: whether a
    degree family can be voiced depends on how many notes were asked for, and on
    nothing about where the notes fall. `guide` under `walking_bass` and `guide` under
    `uniform` are the same two degrees.

    Resolved **once per arrangement**, next to `_resolve_melody` and for the reason
    stated there: the band does not change halfway through a tune.
    """
    return resolve_harmony(parse_harmony(harmony), voices, diagnostics)


def _resolve_grid(grid: str, beats_per_bar: int, diagnostics: Diagnostics) -> str:
    """The grid to place chords on: parsed, `auto` resolved, validated or refused.

    The same two-step shape as `_resolve_melody` and `_resolve_harmony` above,
    because it is the same rule about the same kind of thing: `textures` owns the
    vocabulary and the refusal, this function owns only the wiring.

    **Takes the metre rather than a texture**, and that is what distinguishes it from
    `harmony`. Whether a rhythm fits is a property of the metre - `final_and` is the
    upbeat of the last beat whatever the arrangement is doing - so it is resolved
    against `beats_per_bar` and nothing else.
    """
    return resolve_grid(parse_grid(grid), beats_per_bar, diagnostics)


def _sounding_melody(voicing: Voicing, written: str) -> Tuple[str, Optional[str]]:
    """The pitch a melody-alone step *sounds*, and the written one when they differ.

    `get_melody_only_voicing` retries a note an octave down when no string reaches it
    inside `HIGH_FRET_LIMIT` (13 - G5 is fret 15 on the high E string), so a shape
    built for the tune can sound a whole octave away from the pitch the progression
    asked for. `melody` has to be what **sounds** - the tab is the contract - and
    `original_melody` is what the renderer shows beside it.

    Extracted because three routes build a melody-alone step and only one of them
    reported this. Measured on the committed heads, the texture fill printed the
    written pitch over a shape an octave lower on 4 steps of "The Jitterbug Waltz",
    and the palette rescue on 2 more. One function, so a fourth route cannot spell it
    differently.
    """
    sounding = max(voicing.midi_notes())
    if sounding == Note(written).midi_note():
        return written, None
    return _note_name(sounding), written


def _resolve_substitute_harmony(
    melody_note: Note,
    chord_type: str,
    name: str,
    strategy: str,
    next_melody: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    """The `(quality, name, strategy)` that makes a non-chord melody note a chord tone.

    **Extracted from `prepare_step` so the comping route reaches it too**
    (`docs/comping-styles.md` §9.3 step C). The melody route pins the note and
    re-voices a substituted chord around it; the comping route never sounds the note
    but must still *state* the chord the horn's line implies, so the two have to make
    the same decision the same way - otherwise `--non-chord-tone` means one thing on
    one route and another on the other, which is the split this codebase keeps having
    to close.

    Returns `None` when the note is already a chord tone, when the chord is outside
    `CHORD_TONES_FROM_ROOT` (nothing to substitute against), when `name` is empty, or
    when `resolve_non_chord_tone` finds no route for the strategy. `sustain` is
    deliberately excluded up front: it holds the *previous shape's* inner voices,
    which is a melody-route move with no meaning where the generator builds a fresh
    comping shape on every slot.
    """
    if strategy in ("legacy", "sustain") or not name:
        return None
    canonical = ChordParser.canonical_quality(chord_type)
    if canonical not in ChordParser.CHORD_TONES_FROM_ROOT:
        return None
    if _chords.is_chord_tone(melody_note, chord_type, name):
        return None
    resolved = _chords.resolve_non_chord_tone(
        melody_note, chord_type, name, strategy, next_melody=next_melody
    )
    if resolved is None:
        return None
    return resolved[0], resolved[1], strategy


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
    diagnostics: Optional[Diagnostics] = None,
) -> Optional[StepPreparation]:
    """
    Builds one step's candidates, leaving the choice of shape to the caller.

    This is a whole step up to selection: the candidates across every allowed
    soprano string and grip family, the octave-down rescue, and the
    non-chord-tone strategies. `arrange_progression` selects with
    `_best_voicing` straight afterwards, and the corpus loader selects the
    same way after honouring a slash bass, so the two cannot drift.

    Returns None when the step has no voicing at all. `previous` is only read
    by the `sustain` strategy, and `previous_chord` is what that strategy
    reports as `harmonized_as`.

    `diagnostics` receives the one warning this function can raise - a
    non-chord tone no strategy could resolve. It defaults to printing, which
    is what this function always did; see `diagnostics.Diagnostics`.
    """
    if diagnostics is None:
        diagnostics = default_diagnostics()
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

    if is_non_chord_tone and non_chord_tone != "legacy":
        # Strategy 3 first: holding the shape moves less than any re-voicing.
        if non_chord_tone == "sustain" and previous is not None:
            sustained = _grips.sustain_inner_voices(previous, sounding_melody)
            if sustained is not None:
                candidates = [sustained]
                strategy_used = "sustain"
                harmonized_as = previous_chord

        # Strategies 1 and 2 reharmonise the note as a genuine chord tone.
        if strategy_used is None:
            substitute = _resolve_substitute_harmony(
                sounding_melody,
                chord_type,
                name,
                non_chord_tone,
                next_melody=_next_resolution_melody(progression, index),
            )
            if substitute is not None:
                substitute_quality, substitute_name = substitute[0], substitute[1]
                substituted = _grips.get_all_grip_voicings(
                    sounding_melody,
                    substitute_quality,
                    chord_name=substitute_name,
                    top_strings=top_strings,
                    grips=grips,
                )
                if substituted:
                    candidates = substituted
                    strategy_used = non_chord_tone
                    harmonized_as = substitute_name

        if strategy_used is None:
            diagnostics.warn(
                f"Warning: melody {note_str} is not a chord tone of {name} and the "
                f"'{non_chord_tone}' strategy found no voicing; keeping the fallback"
            )

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
    them and derive two more (`texture_grips`, and the defaulted `diagnostics`)
    before the loop can start. That prologue is this function's job; the loop then
    unpacks the result straight back into the names it has always used, so the
    extraction changed nothing downstream of it.
    """

    top_strings: Tuple[int, ...]
    non_chord_tone: str
    fret_min: int
    fret_max: int
    grips: Tuple[str, ...]
    texture: str
    bass: str
    melody: str
    harmony: str
    grid: str
    beats_per_bar: int
    beat_type: int
    melody_onsets: Optional[Container[int]]
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]]
    bass_pcs: Optional[Mapping[int, Optional[int]]]
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]]
    texture_grips: Dict[str, Tuple[str, ...]]
    diagnostics: Diagnostics


def _resolve_knobs(
    options: Optional[ArrangeOptions],
    *,
    top_strings: Tuple[int, ...],
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    grips: Tuple[str, ...],
    texture: str,
    bass: str,
    melody: str,
    harmony: str,
    grid: str,
    beats_per_bar: int,
    beat_type: int,
    melody_onsets: Optional[Container[int]],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    diagnostics: Optional[Diagnostics],
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
                ("grips", grips),
                ("texture", texture),
                # `bass` is compared here like every other knob, which it was not
                # for its whole life: `ArrangeOptions.bass` defaulted to the
                # resolved "none" while the keyword defaults to the `BASS_AUTO`
                # sentinel, so the two could never be compared - and the field was
                # never read back out of `options` either, which is what made
                # `--bass` silently inert on every slot-path caller (`arranger
                # head` among them) while the walking-bass tests, which pass the
                # keyword directly, stayed green. The field default is the sentinel
                # now, so the comparison below holds, and the unpack below reads the
                # field back.
                ("bass", bass),
                ("melody", melody),
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
        grips = options.grips
        texture = options.texture
        bass = options.bass
        melody = options.melody
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
    texture_grips = TEXTURE_GRIPS.get(texture)
    if texture_grips is None:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    # Resolved once, here, and passed down: every warning this function reaches
    # goes to the one collector, so a caller that passed one sees all of them
    # rather than the first few. Defaults to printing, as this always did.
    if diagnostics is None:
        diagnostics = default_diagnostics()

    return _Knobs(
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        grips=grips,
        texture=texture,
        bass=bass,
        melody=melody,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        melody_onsets=melody_onsets,
        timings=timings,
        bass_pcs=bass_pcs,
        slash_bass_cost=slash_bass_cost,
        texture_grips=texture_grips,
        diagnostics=diagnostics,
    )


@dataclass(frozen=True)
class _Policies:
    """The axes and the walked-beat union, resolved once per arrangement.

    `voices`/`melody_voiced`/`melody_only` come off the melody axis, `bass` and
    `has_thumb` off the bass policy, `harmony_family` and `grid_pattern` off the
    two comping axes, and `slots` is the walked-beat union when a thumb line is
    running. Resolved up front because the band does not change halfway through a
    tune, and unpacked straight back into the names the loop has always used.
    """

    voices: Tuple[str, ...]
    melody_voiced: bool
    melody_only: bool
    bass: str
    has_thumb: bool
    harmony_family: str
    grid_pattern: str
    slots: Optional[List[_Slot]]


def _resolve_policies(
    progression: Sequence[Tuple[Optional[str], str, str]],
    *,
    melody: str,
    texture: str,
    bass: str,
    harmony: str,
    grid: str,
    beats_per_bar: int,
    beat_type: int,
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
    diagnostics: Diagnostics,
) -> _Policies:
    """The axes resolved once per arrangement, plus the walked-beat union.

    Resolved up front rather than per step: the band does not change halfway
    through a tune, and a spelling nobody recognises has to be reported **once**
    rather than never at all on an arrangement where the guitar happens to be
    singing.

    **The melody axis comes before `_resolve_bass` because the bass policy needs
    to know which route the engine is on**, and only this function knows.
    `bass_allowed` measures thumb capacity against `TEXTURE_GRIPS`, which
    describes the shapes the melody-bearing route generates and is *inert* on the
    comping one - so asking it about a texture on that route refused a
    combination that is playable and, worse, told the player to change a setting
    that could not affect the result. See `comping_capacity`, and
    `docs/open-issues.md` for the measurement.

    The two resolutions are independent of each other, so the order between them
    carries no other meaning; what matters is that both finish before `has_thumb`
    is read, because that flag gates whether the walked-beat union is built.
    """
    voices = _resolve_melody(melody)
    melody_voiced = voices_have_soprano(voices)
    # The melody-only selection, decided once here and read by the bass policy,
    # the grip resolution and the promotion rule below: `(soprano,)` is the
    # tune alone and `(soprano, bass)` the tune with a thumb under it,
    # whatever `texture=` says - the texture is inert on that route, the same
    # way it is on the comping one.
    melody_only = melody_only_selection(voices)

    # The bass policy. `auto` means "whatever this texture and this selection
    # mean", so `walking_bass` keeps walking and a melody-only selection that
    # names the bass voice walks too; an explicit policy overrides both, which
    # is what lets a texture that was never written for a thumb line carry one.
    #
    # The resolved `voices` are passed rather than the flags derived from them -
    # the route, the arity and the lone-bass case are decided inside, from the
    # selection, so the two spellings of one request cannot disagree.
    bass = _resolve_bass(
        texture,
        bass,
        voices,
        diagnostics,
    )
    has_thumb = bass != BASS_NONE

    # The harmony axis, resolved here for the same reason and read only by the
    # comping route below. Resolving it unconditionally rather than inside
    # `if not melody_voiced` is deliberate: a spelling nobody recognises must be
    # reported **once, up front**, rather than never at all on an arrangement where
    # the guitar happens to be singing - the same argument as `_resolve_melody`'s.
    harmony_family = _resolve_harmony(harmony, voices, diagnostics)
    # The grid axis, resolved here for the same reason and read by **both** routes
    # below rather than only the comping one - unlike `harmony=`, which the guitar
    # singing makes unreachable. A grid says where a chord lands, and that is a
    # question about the part whether the guitar is singing it or comping under a
    # horn, so scoping it to one route would make `grid=` silently inert on a
    # melody-bearing arrangement rather than doing nothing there.
    grid_pattern = _resolve_grid(grid, beats_per_bar, diagnostics)

    slots: Optional[List[_Slot]] = None
    if has_thumb:
        # Decision B: the union is built here, before the melody loop, so the
        # loop's index still indexes the skeleton it was given. `_walking_slots`
        # is shared with `slots.arrange_slots`, so an imported head and a
        # hand-built progression cannot walk a different line from this one - see
        # its docstring for why that duplication has already cost this project one
        # bug.
        slots = _walking_slots(
            progression, timings, beats_per_bar, beat_type, bass
        )

    return _Policies(
        voices=voices,
        melody_voiced=melody_voiced,
        melody_only=melody_only,
        bass=bass,
        has_thumb=has_thumb,
        harmony_family=harmony_family,
        grid_pattern=grid_pattern,
        slots=slots,
    )


def _rest_step(
    arrangements: List[ArrangementStep],
    slot: _Slot,
    *,
    name: str,
    note_str: Optional[str],
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
    sings_here: bool,
    diagnostics: Diagnostics,
) -> None:
    """Append the rest-or-hold step for a slot the guitar does not sing.

    The guitar is silent and the horn has the note. **The step is still
    emitted**, carrying the bar, the beat and the chord name: it is what keeps
    the melody's position in the tab staff, and a comping part whose bars
    collapsed to their stabs would not line up against the tune it is
    comping under.
    """
    arrangements.append(ArrangementStep(
        chord=name,
        melody=note_str,
        voicing=Voicing(
            frets=[-1] * len(STANDARD_TUNING),
            top_fret=0,
            avg_fret=0.0,
            grip="rest",
        ),
        bar=bar,
        beat=beat,
        duration=duration,
        role=role,
        metric_weight=weight,
        # A rest is a slot the guitar does **not** sing - which is `sings_here`,
        # False here by construction. The route-level `melody_voiced` would
        # claim the guitar sings a slot it just declined to play.
        melody_voiced=sings_here,
    ))
    # The thumb still walks on a rest. A comping grid thins the **chords**,
    # not the bass line - that is the whole difference between `grid=` and
    # `bass=none`, and dropping the attach here would silently delete the
    # walk from every bar the grid thinned.
    _attach_bass(
        arrangements[-1], slot.bass, arrangements, diagnostics
    )


def _texture_fill_step(
    arrangements: List[ArrangementStep],
    slot: _Slot,
    *,
    name: str,
    note_str: Optional[str],
    melody_note: Optional[Note],
    top_strings: Tuple[int, ...],
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
    diagnostics: Diagnostics,
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
    assert melody_note is not None and note_str is not None
    solo_voicing = _grips.get_melody_only_voicing(
        melody_note, prefer=top_strings
    )
    if solo_voicing is not None:
        sounding, written_original = _sounding_melody(solo_voicing, note_str)
        fill = ArrangementStep(
            chord=name,
            melody=sounding,
            voicing=solo_voicing,
            original_melody=written_original,
            partial=False,
            bar=bar,
            beat=beat,
            duration=duration,
            role=role,
            metric_weight=weight,
            bass_only=is_bass_only(slot.bass_only, role),
        )
        _attach_bass(fill, slot.bass, arrangements, diagnostics)
        arrangements.append(fill)
        return True
    return False


def _no_chord_step(
    arrangements: List[ArrangementStep],
    slot: _Slot,
    *,
    name: str,
    note_str: Optional[str],
    melody_note: Optional[Note],
    top_strings: Tuple[int, ...],
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
    diagnostics: Diagnostics,
) -> None:
    """Append the melody-alone step for an `NC` bar: melody, but no harmony.

    This happens before any chord logic, so there is no non-chord-tone strategy,
    no substitute chord and no warning about either. The `melody_only` flag is
    set here and *only* here; the texture case above reaches the same shape
    deliberately without it.
    """
    # As the texture branch above: this kind means the guitar sings, and
    # that guard already refused a singing slot with no note.
    assert melody_note is not None and note_str is not None
    solo_voicing = _grips.get_melody_only_voicing(melody_note, prefer=top_strings)
    if solo_voicing is None:
        diagnostics.warn(
            f"Warning: melody {note_str} is unreachable on any string; "
            f"skipping the no-chord step"
        )
        return
    # get_melody_only_voicing may have dropped the note an octave to stay
    # below HIGH_FRET_LIMIT, so the step reports the pitch that sounds and
    # keeps the written one for the renderer. See `_sounding_melody`.
    sounding, written_original = _sounding_melody(solo_voicing, note_str)
    arrangements.append(ArrangementStep(
        chord=name,
        melody=sounding,
        voicing=solo_voicing,
        original_melody=written_original,
        melody_only=True,
        # `step.grip` is a derived view of `voicing.grip`, so nothing is
        # passed here: the voicing says "melody" and the step cannot
        # disagree with it. The property is what keeps the two spellings
        # one fact with one home - see `docs/one-fact.md`, commit 1.
        bar=bar,
        beat=beat,
        duration=duration,
        role=role,
        metric_weight=weight,
    ))
    # An `NC` bar is still a place the thumb walks: the walk reads the last
    # known harmony (or skips), and the melody-alone shape leaves every bass
    # string free. Attaching it here rather than only on harmonised steps is
    # what keeps a bar of no-chord melody from being a hole in the walk.
    arrangements[-1].bass_only = is_bass_only(slot.bass_only, role)
    _attach_bass(arrangements[-1], slot.bass, arrangements, diagnostics)


def _comping_step(
    arrangements: List[ArrangementStep],
    slot: _Slot,
    *,
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
    chord_type: str,
    name: str,
    note_str: Optional[str],
    melody_note: Optional[Note],
    melody_onsets: Optional[Container[int]],
    voices: Tuple[str, ...],
    harmony_family: str,
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    bass_pcs: Optional[Mapping[int, Optional[int]]],
    slash_bass_cost_for: Optional[Callable[[Sequence[int], Optional[int]], int]],
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
    diagnostics: Diagnostics,
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
    """
    # An `NC` bar has no chord, so there is no guide tone to state and
    # nothing at all for the guitar to play under the horn's line. That is
    # a real hole in the part and it is reported as one, in one sentence -
    # rather than reaching `get_comping_voicings`, which correctly refuses a
    # chord with no root, and then falling through to a melody-bearing route
    # that would either warn twice or hand the horn's line back to the
    # guitarist. Skipping is the honest answer: the guitar is silent on this
    # bar, and the horn is not.
    if chord_type == NO_CHORD or name == NO_CHORD:
        diagnostics.warn(
            f"Warning: {name} has no chord and this voice selection "
            f"({', '.join(voices)}) leaves the guitar nothing to comp; "
            f"skipping the bar"
        )
        return True
    # --- the non-chord-tone strategy, at harmony level (§9.3 step C) ---
    #
    # The melody is *not* on the guitar here - the horn has it - so a
    # substitution changes what the guitar **states**, not what it sings.
    # `melody_pc` stays None below, so a comping shape is still held to the
    # substitute's full tone set; only the chord the shape is drawn from
    # moves. `D5` over `Cmaj7` therefore gives `Cmaj9` (extension) or
    # `Bdim7` (diminished) under the guide-tone voices, exactly as the
    # melody route re-voices it.
    comp_chord_type, comp_name = chord_type, name
    comp_strategy: Optional[str] = None
    comp_harmonized_as: Optional[str] = None
    comp_is_non_chord_tone = False
    # §9.2: reharmonise **at an onset**. A held position was decided where
    # the note began, and a silent one has nothing to resolve. `melody_onsets`
    # is the caller's onset set; None means every slot is an onset, the right
    # answer for a hand-built progression that carries no timeline.
    if (
        melody_note is not None
        and (melody_onsets is None or index in melody_onsets)
    ):
        substitute = _resolve_substitute_harmony(
            melody_note,
            chord_type,
            name,
            non_chord_tone,
            next_melody=_next_resolution_melody(
                progression, index, melody_onsets
            ),
        )
        if substitute is not None:
            comp_chord_type, comp_name, comp_strategy = substitute
            comp_harmonized_as = comp_name
            comp_is_non_chord_tone = True
            # A guitarist handed `Cmaj7 -> Bdim7` with no melody on their own
            # part cannot see why the chord moved; the note that forced it is
            # the horn's, so it has to be named here or the part reads wrong.
            diagnostics.warn(
                f"Warning: comping {name} as {comp_name} "
                f"({comp_strategy}) to accommodate the melody note "
                f"{note_str}"
            )
    # How many chord voices the guitar states here. **A voice is a *role*
    # in the stack, not a count of parts played twice** - `--voices
    # alto,tenor` is two notes, and padding it to three would put a voice
    # in the part that belongs to the bassist.
    #
    # **A named soprano that is not singing is not one of the sounding
    # voices** (§9.3 step D). On the comping route the selection has no
    # soprano and this is `len(voices)`, exactly as before. On a *singing*
    # selection reaching this branch - a grid position the tune is silent
    # at - the soprano has no note to sing, so the shape is built from the
    # voices that do sound: `soprano,alto,tenor,bass` states a three-voice
    # shell on the offbeats, not a four-voice shape with a redundant root.
    # (That four-note comping shape is `docs/comping-styles.md` §9.4, and it
    # needs new string sets - deliberately not this step.)
    comp_notes = len([voice for voice in voices if voice != MELODY_SOPRANO])
    candidates = _grips.get_comping_voicings(
        comp_chord_type,
        chord_name=comp_name,
        fret_min=fret_min,
        fret_max=fret_max,
        notes=comp_notes,
        # **Whether this selection is the bass voice and nothing else**,
        # which arity cannot say: `alto`, `tenor` and `bass` all ask for one
        # note, and only the bass voice has a register that is part of what it
        # *is*. Derived from the resolved voices rather than
        # an extra CLI flag, so the two spellings of one request cannot
        # disagree.
        bass_voice=voices == (MELODY_BASS,),
        # Whether this part states both guide tones **and** a root or 5th
        # under them. The one degree family neither `notes` nor
        # `bass_voice` can express, and derived from the resolved family
        # rather than passed as another flag, so the two spellings of one
        # request cannot disagree.
        shell_root=harmony_family == HARMONY_SHELL_ROOT,
    )
    if not candidates:
        if melody_note is None:
            # The ordinary fallback below voices *the melody*, and this
            # slot has none to voice - there is no thin shape to fall back
            # to either, so the chord of the tune cannot be stated here at
            # all. Reported as the hole it is and skipped; the next grid
            # position still gets its chance.
            diagnostics.warn(
                f"Warning: no guide-tone comping shape found for {name} "
                f"and no melody note at this position to fall back to; "
                f"skipping the slot"
            )
            return True
        # No guide-tone shape in a playable position. The chord of the tune
        # is still owed to the band, so fall through to the ordinary
        # melody-bearing route rather than dropping the bar - the same
        # trade `prepare_step` makes when a strategy finds nothing. The
        # guitar plays the tune here, which is a worse answer than a thin
        # one and a better one than silence.
        diagnostics.warn(
            f"Warning: no guide-tone comping shape found for {name}; "
            f"falling back to voicing the melody on the guitar"
        )
    else:
        # The root, read once for the selector's bass-function tie-break.
        # `get_comping_voicings` has already refused to generate anything
        # without a root, so by this point it is never None - the check is
        # read from the same place the generator read it rather than
        # re-derived, so the two cannot disagree.
        _canonical, root_pc, _tones = _grips._chord_context(comp_chord_type, comp_name)
        arrangements.append(ArrangementStep(
            chord=name,
            # The written note, which is the horn's line. The guitar does not
            # sound it - `melody_voiced=False` is what says so.
            melody=note_str,
            voicing=select_step_voicing(
                candidates,
                arrangements[-1].voicing if arrangements else None,
                fret_min,
                fret_max,
                # The tones the written chord allows. Passed even though the
                # generator already filters on them: `voicing_cost` counts
                # wrong notes itself, and a generator that could be wrong
                # should not be the only thing standing between a chord symbol
                # and a note that is not in it.
                ChordParser.get_chord_tones(comp_chord_type, comp_name),
                # The root, which enables the bass-function tie-break. None
                # for a chord whose name will not parse, which leaves that
                # criterion unasked rather than guessing a bass - the same
                # rule the ordinary route follows.
                root_pc,
                # No `melody_pc`: there is no melody on the guitar for the
                # wrong-note count to excuse, which is what lets a comping
                # shape be held to the chord's full tone set.
                None,
                # The corpus's slash bass, honoured before selection rather
                # than after, exactly as on the ordinary route.
                bass_pcs.get(index) if bass_pcs else None,
                slash_bass_cost_for,
            ) or candidates[0],
            # A comping shape is three voices by construction, so `partial`
            # is always true and is not worth re-deriving per step.
            partial=True,
            bar=bar,
            beat=beat,
            duration=duration,
            role=role,
            metric_weight=weight,
            bass_only=is_bass_only(slot.bass_only, role),
            melody_voiced=False,
            # What the substitution changed about the *harmony*, reported the
            # way the melody route reports it: `chord` stays the written
            # symbol, and these three say what was actually stated under the
            # horn's line (§9.3 step C).
            non_chord_tone=comp_is_non_chord_tone,
            strategy=comp_strategy,
            harmonized_as=comp_harmonized_as,
        ))
        _attach_bass(
            arrangements[-1], slot.bass, arrangements, diagnostics
        )
        return True
    return False


def _rescue_melody_alone(
    arrangements: List[ArrangementStep],
    slot: _Slot,
    *,
    name: str,
    note_str: str,
    melody_note: Note,
    top_strings: Tuple[int, ...],
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
    diagnostics: Diagnostics,
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
    the melody with it; for the measured cost of that, under `--grips shell` alone,
    see `docs/open-issues.md` item 14.

    Returns **True** when the step was appended. **False** means no string can
    reach the note at all - below the library's G3 floor, or past the end of the
    board - and the caller reports the step as skipped.
    """
    # **The string must be one the caller named.** `get_melody_only_voicing`
    # keeps searching *below* the set it is given, so a note the named set
    # cannot carry - D4 under `top_strings=(5,)`, below the high E string's
    # open pitch - comes back on the B string. That is the documented
    # behaviour of a restricted soprano set and not this rescue's to
    # override: the rescue answers a palette that cannot voice a chord, not
    # a caller asking for a string that cannot carry the tune.
    solo_voicing = _grips.get_melody_only_voicing(
        melody_note, prefer=top_strings
    )
    if solo_voicing is not None and solo_voicing.soprano_string() in top_strings:
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
        _attach_bass(step, slot.bass, arrangements, diagnostics)
        arrangements.append(step)
        return True
    return False


def _promoted_fill(
    *,
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
    arrangements: List[ArrangementStep],
    top_strings: Tuple[int, ...],
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    grips: Tuple[str, ...],
    slot_grips: Tuple[str, ...],
    texture: str,
    role: str,
    has_thumb: bool,
    melody_only: bool,
    diagnostics: Diagnostics,
) -> Optional[StepPreparation]:
    """Re-prepare a fill that produced nothing as a principal note.

    A fill slot with nothing thin to play must not lose the chord of the tune -
    the whole point of the texture is a lighter *texture*, never a missing
    harmony. Same argument as `NECK_FRET_MIN` being a penalty and not a filter.
    `decisions.should_promote_fill` decides whether this step gets the retry.

    The retry is prepared against `grips`, the **whole** palette, not the
    narrowed `slot_grips` the fill was given: the narrow palette is what failed.

    Returns the promoted preparation, or **None** when the texture does not ask
    for the retry or the retry found nothing either - the two cases the caller
    answers the same way, by reporting the step as skipped.
    """
    if not should_promote_fill(
        texture, role, True, slot_grips, grips,
        has_thumb=has_thumb,
        melody_only=melody_only,
    ):
        return None
    return prepare_step(
        progression, index,
        previous=arrangements[-1].voicing if arrangements else None,
        previous_chord=arrangements[-1].chord if arrangements else None,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        grips=grips,
        diagnostics=diagnostics,
    )

def _demoted_to_melody_alone(
    arrangements: List[ArrangementStep],
    slot: _Slot,
    *,
    name: str,
    note_str: str,
    melody_note: Note,
    top_strings: Tuple[int, ...],
    best_voicing: Voicing,
    bar: Optional[int],
    beat: Optional[float],
    duration: Optional[float],
    role: str,
    weight: int,
    diagnostics: Diagnostics,
) -> bool:
    """Play the tune alone when the only shape that fitted needs a stretch.

    Reached only under `decisions.should_demote_to_melody_alone`, which is where
    the *why* of the fallback is documented: a complete chord at the very top of
    the span budget is a fallback, not a re-ranking.

    Returns **True** when the melody-alone step replaced the shape, so the caller
    stops. **False** when the melody alone would be the wider reach of the two,
    which leaves the chosen shape in place for the caller to play.
    """
    solo = _grips.get_melody_only_voicing(
        melody_note, prefer=top_strings
    )
    if solo is not None and solo.fret_span() < best_voicing.fret_span():
        diagnostics.warn(
            f"Warning: {name} with melody {note_str} needs a "
            f"{best_voicing.fret_span()}-fret stretch "
            f"({best_voicing.tab_string()}); playing the melody alone"
        )
        arrangements.append(ArrangementStep(
            chord=name,
            melody=note_str,
            voicing=solo,
            partial=False,
            bar=bar,
            beat=beat,
            duration=duration,
            role=role,
            metric_weight=weight,
            bass_only=is_bass_only(slot.bass_only, role),
        ))
        _attach_bass(arrangements[-1], slot.bass, arrangements, diagnostics)
        return True
    return False


def _harmonised_step(
    arrangements: List[ArrangementStep],
    slot: _Slot,
    *,
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
    top_strings: Tuple[int, ...],
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    grips: Tuple[str, ...],
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
    diagnostics: Diagnostics,
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
    prepared = prepare_step(
        progression, index,
        previous=arrangements[-1].voicing if arrangements else None,
        previous_chord=arrangements[-1].chord if arrangements else None,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        grips=slot_grips,
        diagnostics=diagnostics,
    )
    if prepared is None:
        # The tune is never dropped while it can be played at all: play it
        # alone first, then promote the fill, and only then report the step
        # missing. See `_rescue_melody_alone` and `_promoted_fill`.
        if _rescue_melody_alone(
            arrangements, slot,
            name=name, note_str=note_str, melody_note=melody_note,
            top_strings=top_strings, bar=bar, beat=beat, duration=duration,
            role=role, weight=weight, diagnostics=diagnostics,
        ):
            return
        prepared = _promoted_fill(
            progression=progression, index=index,
            arrangements=arrangements, top_strings=top_strings,
            non_chord_tone=non_chord_tone,
            fret_min=fret_min, fret_max=fret_max,
            grips=grips, slot_grips=slot_grips, texture=texture,
            role=role, has_thumb=has_thumb, melody_only=melody_only,
            diagnostics=diagnostics,
        )
        if prepared is None:
            # Reached only when the melody **cannot be played at all** - the
            # rescue above has already been tried, and answered None because no
            # string reaches the note (below the library's G3 floor, or past the
            # end of the board).
            #
            # The palette is named because it is the usual cause and the caller
            # is the only one who can change it, and the message says the step is
            # *skipped* because that is what happens to the note. The old text
            # named "drop-2" whatever family had been asked for - a `--grips
            # shell` run was told about a grip it never requested - and read like
            # a fallback that had happened.
            diagnostics.warn(
                f"Warning: no voicing for {name} with melody {note_str} in the "
                f"palette ({', '.join(slot_grips) or 'none'}) and the melody "
                f"cannot be played alone either; skipping the step"
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

    # The whole selection rule lives in voicing_cost. The first chord has no
    # previous shape to lead from, so it falls back to "somewhere comfortable on
    # the neck"; every later chord is scored against the one before it, which is
    # what keeps the hand from jumping and lets a melody hold its place by
    # changing strings.
    prev_voicing = arrangements[-1].voicing if arrangements else None
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
    best_voicing = select_step_voicing(
        candidates,
        prev_voicing,
        fret_min,
        fret_max,
        allowed_tones=ChordParser.get_chord_tones(sub_quality, substitute),
        root_pc=_grips._chord_context(chord_type, name)[1],
        # The melody is the caller's note and is never rewritten, so when it
        # lies outside the chord every candidate is impure on it. Excluding it
        # lets a shape that adds no *other* wrong note reach zero - see
        # cost.voicing_cost, where counting rather than flagging makes the
        # difference between one wrong note and four.
        melody_pc=melody_note.midi_note() % 12,
        bass_pc=None if bass_pcs is None else bass_pcs.get(index),
        slash_bass_cost=slash_bass_cost_for,
    )
    # `candidates` is non-empty here (the step is skipped otherwise), so this
    # cannot fire. Written as an assertion rather than left to Optional
    # narrowing at every use below.
    assert best_voicing is not None

    # A complete chord at the very top of the span budget is demoted to
    # the melody alone. Why that is a fallback rather than a re-ranking is
    # documented once in decisions.should_demote_to_melody_alone.
    if should_demote_to_melody_alone(best_voicing, role):
        if _demoted_to_melody_alone(
            arrangements, slot,
            name=name, note_str=note_str, melody_note=melody_note,
            top_strings=top_strings, best_voicing=best_voicing,
            bar=bar, beat=beat, duration=duration,
            role=role, weight=weight, diagnostics=diagnostics,
        ):
            return
    # A repeated melody is a soprano-only re-strike, so the renderers hold
    # the inner voices. The rule - and the harmony-change case that is not
    # a hold - is decisions.is_repeated_step.
    repeated = is_repeated_step(
        arrangements[-1] if arrangements else None,
        best_voicing,
        normalised_harmony(name, harmonized_as),
    )

    arrangements.append(ArrangementStep(
        chord=name,
        # The transposed pitch when the step was moved down an octave, so the
        # step reports what actually sounds; original_melody keeps the written one.
        melody=prepared.melody,
        voicing=best_voicing,
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
        # target, which silenced the chord this line had just voiced - see
        # `docs/open-issues.md` item 4.
        bass_only=is_bass_only(slot.bass_only, role),
    ))
    # Select first, merge after: the bass is written into the fret vector only
    # once `_best_voicing` has returned, so it cannot enter the cost tuple by
    # construction rather than by discipline.
    _attach_bass(arrangements[-1], slot.bass, arrangements, diagnostics)


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


def _slot_state(
    car: _Carried,
    slot: _Slot,
    *,
    progression: Sequence[Tuple[Optional[str], str, str]],
    texture: str,
    texture_grips: Dict[str, Tuple[str, ...]],
    grips: Tuple[str, ...],
    has_thumb: bool,
    melody_only: bool,
    melody_voiced: bool,
    melody_onsets: Optional[Container[int]],
    grid_pattern: str,
    beats_per_bar: int,
    diagnostics: Diagnostics,
) -> Optional[_SlotPlan]:
    """One slot's decisions, and the one refusal that ends a slot here.

    Returns **None** for a position a melody-only selection has nothing to play,
    which is reported and skipped. Otherwise the plan carries everything the
    routes need, and the two values on `car` are updated in place.
    """
    index = slot.index
    note_str, chord_type, name = progression[index]
    if note_str is None:
        if melody_only:
            # A melody-only selection plays the tune and nothing else, so a
            # position with no note has nothing for the guitar to play. It is
            # kept as the *only* refusal here because §9.3 step D made the other
            # case a real one: a *singing* selection (soprano named) now receives
            # note-less slots from the grid union - positions the tune is silent
            # at - and the guitar **comps** them rather than being refused, which
            # is why they fall through to the comping branch below.
            diagnostics.warn(
                f"Warning: slot {index} has no melody note and this voice "
                f"selection plays the tune alone; skipping the slot"
            )
            return None
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
    # Under walking_bass a strong beat is only a target when something new
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
    # every slot, whatever the texture's palettes say, so the loop hands the
    # empty palette straight through - the same declaration `TEXTURE_GRIPS`
    # makes with an empty tuple, and the one channel `melody_alone_case`
    # reads. Skipping the resolution also skips its warnings, which is what
    # makes `texture=` and `grips=` silently inert here rather than noisily so.
    slot_grips = (
        ()
        if melody_only
        else resolve_texture_grips(
            role, texture, texture_grips, grips, diagnostics,
            # The right hand's budget, and a fact about *this slot* rather than
            # about the arrangement: a target may sound three strings only where
            # a bass note is actually being placed under it, which is what
            # `slot.bass` says. `has_thumb` alone would thin chords the thumb
            # never plays under - `--bass anchors` leaves most slots bare.
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
    # positions in different bars of different metres, and `textures.on_grid`
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
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
    # `Sequence` and Optional *bar* and *beat*, not `List[Tuple[int, float, ...]]`:
    # a slot a caller could not place is `(None, None, None)`, so an entry point may
    # hold either shape. `float(beat)` below must therefore not assume a non-None
    # beat.
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]] = None,
    texture: str = "uniform",
    bass: str = BASS_AUTO,
    melody: str = MELODY_AUTO,
    harmony: str = HARMONY_AUTO,
    grid: str = GRID_EVERY_NOTE,
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
    diagnostics: Optional[Diagnostics] = None,
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

    grips limits which grip families may be used, in the order they break a tie
    (see GRIP_PREFERENCE). The default offers all of them. `grips=("drop2",)` with
    `top_strings=MELODY_STRING_CHOICES` reproduces this library's original,
    four-string-drop-2-only output exactly, which is what a caller wants when they
    need a known arrangement rather than the best one.

    non_chord_tone selects what happens when a melody note is not a chord tone
    (one of NON_CHORD_TONE_STRATEGIES):
      'extension'  - reharmonise the note as a chord extension (D over Cmaj7
                     becomes Cmaj9), the default;
      'diminished' - Barry Harris 6/dim7 substitution (D over Cmaj7 -> Bdim7);
      'sustain'    - keep the previous chord's inner voices and move only the
                     melody, for brief passing tones;
      'legacy'     - keep the original quality-only fallback behaviour.
    Steps whose melody is already a chord tone are unaffected by this choice.

    A step whose chord_type or name is NO_CHORD ("NC") is voiced as the melody
    alone on a single fret (get_melody_only_voicing) and flagged
    melody_only=True. Such a step is short-circuited before any chord logic,
    so it is never reharmonised and never warns; it also does not take part in
    voice-leading minimisation, and being neither a drop-2 voicing nor a
    four-string shape it is exempt from that playability invariant.

    **Texture and rhythm.** `timings` is each slot's own `(bar, beat, duration)`
    in the caller's units - a signed bar, the beat within it, and a length in
    whole notes - the same triple `ArrangementStep` already carries. `None`, the
    default, means the caller has told us nothing about where its notes fall, and
    then every slot is a principal note and this function behaves exactly as it
    always has.

    `bass` selects the **policy** the thumb line is written on, from BASS_STYLES:
    `"none"` (the default, no thumb line), `"anchors"` (a note only where the
    harmony changes, carrying that chord's root), or `"walk"` (a note on every beat,
    which is what makes the line a walk). It is an argument of its own rather than a
    property of the texture, because the pattern is the composer's choice and the set
    of patterns is open - a new one is a row in `BASS_POLICY_ROLES`.

    `BASS_AUTO`, the default here, resolves from the texture and the selection, and a
    combination the left hand cannot accommodate is refused with a warning rather
    than degraded. **Both rules, and the measurement behind the second, are stated
    once** - in `_resolve_bass` and `bass.bass_allowed` - rather than repeated here.
    Two consequences a caller is most likely to meet: `texture="walking_bass"` and
    `texture="walking_bass", bass="walk"` are the same arrangement, and
    `bass="none"` on a walking bass gives the same strong-beat shells with the thumb
    dropped - a coherent texture in its own right.

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

    `texture="walking_bass"` adds a thumb line on the bass strings under a light
    left hand: a **shell** (3rd & 7th) on a target beat, the **melody alone**
    between, and a walk underneath, one thumb note per beat of the bar. Four
    consequences are part of its contract rather than details of it:

    - **It may return more steps than it was given.** The bass grid is finer than
      the melody grid, so a bar whose melody is a whole note still yields a step
      for each of its `beats_per_bar` beats - one carrying the melody and the rest
      marked `bass_only`, whose upper voices are held rather than re-struck. That
      is **four** steps in 4/4, **three** in 3/4 and **two** in 2/2, because the
      grid is `beats_per_bar` beats wide - and three of the committed scores are in
      cut time. Callers that zip their
      progression against the result, or derive a bar count from `len(steps)`, are
      wrong under this texture only; `uniform` and `targets` are untouched. A step
      the walk invented can be promoted to a **target** when the melody moves onto
      it, and then it states its harmony rather than holding - which is
      `decisions.is_bass_only`, and the reason a `bass_only` step is always a fill.
    - **A `bass_only` step carries the melody sounding at that instant**, not the
      melody the walk last passed. Those differ whenever the melody moves on a beat
      the walk does not visit - the beat 2.5 of a 2/2 bar, where the walk is on 1.0
      and 2.0 - and getting it wrong states a note the score has not reached yet.
      See `docs/open-issues.md` item 5.
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

    `diagnostics` collects this function's warnings - a melody that reaches no
    voicing, a step demoted to the melody alone, a fill promoted to a target, an
    unresolvable non-chord tone, a thumb with nowhere to go. It defaults to
    printing each one, which is what this function has always done, so a caller
    that passes nothing sees no change. Pass a `Diagnostics()` to collect them
    silently instead; see the `diagnostics` module for why that is a value
    rather than a logging call.
    """
    _k = _resolve_knobs(
        options,
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        grips=grips,
        texture=texture,
        bass=bass,
        melody=melody,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        melody_onsets=melody_onsets,
        timings=timings,
        diagnostics=diagnostics,
    )
    # Unpacked into the names the loop below has always used, so the extraction
    # above changes nothing downstream of it.
    top_strings = _k.top_strings
    non_chord_tone = _k.non_chord_tone
    fret_min = _k.fret_min
    fret_max = _k.fret_max
    grips = _k.grips
    texture = _k.texture
    bass = _k.bass
    melody = _k.melody
    harmony = _k.harmony
    grid = _k.grid
    beats_per_bar = _k.beats_per_bar
    beat_type = _k.beat_type
    melody_onsets = _k.melody_onsets
    timings = _k.timings
    bass_pcs = _k.bass_pcs
    slash_bass_cost_for = _k.slash_bass_cost
    texture_grips = _k.texture_grips
    diagnostics = _k.diagnostics

    arrangements: List[ArrangementStep] = []

    # The walking bass is computed here, over the **walked beats** rather than
    # over the slots, and it yields a pitch *class* rather than a pitch and a
    # string: neither the octave nor the string can be decided before an upper
    # voicing exists, and only this function is downstream of one. `_place_bass`
    # resolves both together, after selection.

    _p = _resolve_policies(
        progression,
        melody=melody,
        texture=texture,
        bass=bass,
        harmony=harmony,
        grid=grid,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        timings=timings,
        diagnostics=diagnostics,
    )
    # Unpacked into the names the loop below has always used, so the extraction
    # above changes nothing downstream of it.
    voices = _p.voices
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

    loop: List[_Slot] = (
        slots if slots is not None
        else [
            _Slot(index=index, bar=bar, beat=beat, duration=duration)
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
            texture_grips=texture_grips,
            grips=grips,
            has_thumb=has_thumb,
            melody_only=melody_only,
            melody_voiced=melody_voiced,
            melody_onsets=melody_onsets,
            grid_pattern=grid_pattern,
            beats_per_bar=beats_per_bar,
            diagnostics=diagnostics,
        )
        if plan is None:
            continue

        if plan.melody_alone == MELODY_ALONE_REST:
            _rest_step(
                arrangements, slot,
                name=plan.name, note_str=plan.note_str,
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight,
                sings_here=plan.sings_here, diagnostics=diagnostics,
            )
            continue
        if plan.melody_alone == MELODY_ALONE_TEXTURE:
            if _texture_fill_step(
                arrangements, slot,
                name=plan.name, note_str=plan.note_str,
                melody_note=plan.melody_note, top_strings=top_strings,
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight,
                diagnostics=diagnostics,
            ):
                continue

        if plan.melody_alone == MELODY_ALONE_NO_CHORD:
            _no_chord_step(
                arrangements, slot,
                name=plan.name, note_str=plan.note_str,
                melody_note=plan.melody_note, top_strings=top_strings,
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight,
                diagnostics=diagnostics,
            )
            continue

        # --- The comping route: the guitar harmonises, somebody else sings ---
        # See `_comping_step`: taken before `prepare_step` because there is no
        # melody for the guitar here, and only after the NC and melody-alone
        # branches, which are the cases with no harmony to state.
        if not plan.sings_here and not melody_only:
            if _comping_step(
                arrangements, slot,
                progression=progression, index=plan.index,
                chord_type=plan.chord_type, name=plan.name,
                note_str=plan.note_str, melody_note=plan.melody_note,
                melody_onsets=melody_onsets,
                voices=voices, harmony_family=harmony_family,
                non_chord_tone=non_chord_tone,
                fret_min=fret_min, fret_max=fret_max,
                bass_pcs=bass_pcs, slash_bass_cost_for=slash_bass_cost_for,
                bar=plan.bar, beat=plan.beat, duration=plan.duration,
                role=plan.role, weight=plan.weight, diagnostics=diagnostics,
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
            grips=grips, slot_grips=plan.slot_grips, texture=texture,
            has_thumb=has_thumb, melody_only=melody_only,
            name=plan.name, note_str=plan.note_str,
            melody_note=plan.melody_note,
            bass_pcs=bass_pcs, slash_bass_cost_for=slash_bass_cost_for,
            bar=plan.bar, beat=plan.beat, duration=plan.duration,
            role=plan.role, weight=plan.weight, diagnostics=diagnostics,
        )

    return arrangements


def _attach_bass(
    step: ArrangementStep,
    note: Optional[BassNote],
    arrangements: List[ArrangementStep],
    diagnostics: Optional[Diagnostics] = None,
) -> None:
    """
    Merges one walked beat into a step: records it, then places it on a string.

    Deliberately after selection (see the caller). Three independent failures are
    all handled the same way - **the step survives and the bass is reported**:

    - no candidate string survives `_place_bass`'s filters, so there is nowhere to
      put the thumb. The message names **all three** ways that happens, because a
      reader cannot tell them apart from the outside and the common one is not the
      intuitive one: no free string below the melody, **no octave of the wanted
      pitch below the shape's own lowest note**, or a fifth fret for four fingers.
      Measured over the committed heads the split is **0 / 38 / 1** of 39 refusals
      (`docs/open-issues.md` item 13), so the middle clause is the one that fires
      almost every time - and until it was named, the text offered a reader two
      causes that had not fired at all. Same argument as the neck window being a
      penalty rather than a filter: losing a step is worse than losing its bass.
    - a candidate string exists, but every one of them would need a **fifth fret**
      from a hand already holding the shape - the `bass_only` case of
      `docs/open-issues.md` item 12. A bass note a player cannot finger is not a
      bass note, so it is refused rather than written.
    - a step that already carries a bass, which cannot happen while the union is
      one walked note per slot, but is checked rather than assumed.

    The previous thumb note is the search's continuity term, so a line does not
    leap octaves between beats purely because a nearer-in-fret candidate happened
    to be two octaves away.
    """
    if note is None:
        return
    step.bass_role = note.role
    if step.bass is not None:
        return
    # A `bass_only` step re-states nothing above the thumb, so the shape the hand is
    # holding is the last **struck** one, not this step's own thinned vector.
    # Measured against the thinned vector the thumb is placed on a string the hand
    # is already fingering and ranked from a fret the hand is not at - the
    # unplayable bar in `docs/open-issues.md` item 1. For any other step the current
    # voicing *is* the shape, so `held` must not narrow it.
    held = (
        _held_shape(arrangements)
        if step.bass_only and not step.melody_only
        else None
    )
    placed = _place_bass(
        step.voicing,
        note.pitch_class,
        previous_bass=_previous_bass(arrangements),
        held=held,
    )
    if placed is None:
        # `if ... is None`, never `or`: `Diagnostics.__bool__` is False until it holds
        # something, so an empty collector handed in by a caller would be replaced by
        # the printing default and its first warnings lost - measured as three of
        # "But Not For Me"'s refusals under each of the four rows, and it is the same
        # `or`-on-a-falsy-collector trap the other three call sites avoid
        # (`docs/open-issues.md` item 16).
        if diagnostics is None:
            diagnostics = default_diagnostics()
        diagnostics.warn(
            f"Warning: no playable bass note for bass "
            f"{PITCH_CLASS_NAMES[note.pitch_class % 12]} - no free string "
            f"below the melody, no octave of that pitch below the shape, "
            f"or the hand would need a fifth fret; "
            f"the step keeps its upper voicing"
        )
        return
    midi, string_index, fret = placed
    step.voicing.bass_midi = midi
    step.voicing.bass_string = string_index
    step.voicing.frets[string_index] = fret
    # `bass_pc` is the lowest sounding voice, which the thumb now is by
    # construction: it sounds below every upper voice, or it was not placed.
    step.voicing.bass_pc = midi % 12


def _next_resolution_melody(
    progression: Sequence[Tuple[Optional[str], str, str]],
    index: int,
    onsets: Optional[Container[int]] = None,
) -> Optional[str]:
    """
    The pitch the melody line resolves into: the first following step whose
    melody is a chord tone of its own chord (None when the phrase never
    resolves). Spells the dim7 substitution's root.

    A slot with no melody note is stepped over: silence resolves into nothing.

    `onsets`, when given, restricts the scan to slots whose melody **articulates**.
    On the comping route a held position carries the note still sounding, not the
    horn's *next* note, so the resolution target must be read from the written
    onsets alone - otherwise a sustained note would name itself the thing the line
    resolves into (§9.3 step C). `None` scans every slot, the melody route's rule.
    """
    for offset in range(index + 1, len(progression)):
        if onsets is not None and offset not in onsets:
            continue
        note_str, chord_type, name = progression[offset]
        if note_str is None:
            continue
        if _chords.is_chord_tone(Note(note_str), chord_type, name):
            return note_str
    return None
