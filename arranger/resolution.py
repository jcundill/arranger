"""What the caller asked for, resolved once: parts, grid, harmony, bass and the knobs.

Every `*_AUTO` sentinel on the axes is answered here, against the selection and the
texture, so the step loop only ever reads a concrete value. Pure policy: no voicing is
built and no step is emitted. It sits above `movement`, which calls the two resolvers it
still needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Container, List, Mapping, Optional, Sequence, Tuple

from .bass import (
    Slot,
    walking_slots,
)
from .bass_rules import (
    BASS_STYLE_AUTO,
    BASS_STYLE_NONE,
    resolve_bass,
)
from .chords import (
    NON_CHORD_TONE_STRATEGIES,
)
from .grid import Rhythm, parse_grid, resolve_grid
from .grouping import COMMON_TIME, TimeSignature
from .harmony import (
    parse_harmony,
    resolve_harmony,
)
from .options import (
    DEFAULT_REQUEST,
    ArrangeOptions,
    Request,
    ResolvedRequest,
    resolve_request,
)
from .parts import (
    PART_BASS,
    parse_parts,
    parts_has_melody_only,
    parts_have_melody,
    resolve_parts,
)
from .texture import (
    parse_texture,
)


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


def _resolve_grid(
    grid: str,
    beats_per_bar: int,
    grouping: Tuple[int, ...],
) -> str:
    """The grid to place chords on: parsed, `auto` resolved, validated.

    The same two-step shape as `_resolve_melody` and `_resolve_harmony` above,
    because it is the same rule about the same kind of thing: `harmony` owns the
    vocabulary and the validation, this function owns only the wiring.

    **Takes the metre rather than a texture**, and that is what distinguishes it from
    `harmony`. Whether a rhythm fits is a property of the metre - `final_and` is the
    upbeat of the last felt beat whatever the arrangement is doing - so it is
    resolved against the count, the denominator and the grouping, and nothing else.
    """
    return resolve_grid(parse_grid(grid), beats_per_bar, grouping)


@dataclass(frozen=True)
class _Knobs:
    """The call's knobs, after `options=` and the keywords are reconciled.

    `arrange_progression` takes its knobs twice over - once as keywords and once as
    `ArrangeOptions` fields - and has to decide between them, validate them and
    validate them
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
    grid: Optional[str]
    request: ResolvedRequest
    beats_per_bar: int
    beat_type: int
    grouping: Tuple[int, ...]
    melody_onsets: Optional[Container[int]]
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]]
    bass_pcs: Optional[Mapping[int, Optional[int]]]
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]]


@dataclass(frozen=True)
class ResolvedAxes:
    """The request, and the four axes the step loop reads.

    `parts`, `texture`, `bass` and `harmony` are the engine's implementation; this
    value is what a caller gets when it asks for them without going through the
    step loop - `headxml` needs `parts` before the loop, to gate the comping union.
    """

    request: ResolvedRequest
    texture: str
    bass: str
    parts: str
    harmony: str


def resolve_axes(
    request: Request,
    texture: Optional[str],
    bass: Optional[str],
    parts: Optional[str],
    harmony: Optional[str],
    time_signature: TimeSignature = COMMON_TIME,
) -> ResolvedAxes:
    """The request's derivation, with a caller's axis override winning.

    `bass` and `parts` are **coupled**, and this is where the two spellings meet.
    The request derives both; a caller who spells `parts` is driving the
    selection, so the bass stays on its sentinel and follows it; a caller who
    spells only a bass policy is making a claim about the bass part, which takes
    that part with it. One spelling owns the pair rather than merging two answers.
    """
    resolved = resolve_request(
        request, time_signature.beats_per_bar, time_signature.resolved_grouping
    )
    texture = resolved.texture if texture is None else texture
    harmony = resolved.harmony if harmony is None else harmony
    if bass is None:
        bass = resolved.bass if parts is None else BASS_STYLE_AUTO
    elif parts is None and bass not in (BASS_STYLE_AUTO, BASS_STYLE_NONE):
        parts = ",".join(resolved.parts + (PART_BASS,))
    return ResolvedAxes(
        request=resolved,
        texture=texture,
        bass=bass,
        parts=",".join(resolved.parts) if parts is None else parts,
        harmony=harmony,
    )


def _conflicts(**values: object) -> List[str]:
    """The keyword names a caller spelled beside `options=`, sorted.

    A keyword is "given" when it differs from its declared default, which is why
    every sentinel default must equal the keyword's: a field defaulting to the
    *resolved* value would compare unequal on every call and make a bare
    `options=` look like a caller who had passed both spellings.

    The two **input facts** are not here: `timings` and `time_signature` say what is
    being arranged rather than how to play it, so they sit beside `options=` and are
    reconciled by `settle_input_fact` instead. `resolve_knobs` holds the rule.
    `request` is the third: it is *what to play*, so it rides beside `options=`, which
    carries the implementation axes that answer *how*.
    """
    return sorted(
        name
        for name, value in values.items()
        if value != ArrangeOptions.__dataclass_fields__[name].default
    )


def settle_input_fact(
    keyword: Any,
    stated: Any,
    default: Any,
    name: str,
    caller: str,
) -> Any:
    """One **input fact** that both the keyword and `options=` may state.

    The metre and the request say *what is being arranged* rather than *how to play
    it*, so they sit beside `options=` rather than inside it - unlike the axes, which
    are the implementation. The keyword wins; the object's own value is read only when
    the keyword was left at its default. Both stated is two claims about one thing,
    which raises rather than silently preferring one.

    A rule of its own rather than `_conflicts`, because these two have a default that
    is a real value (`COMMON_TIME`, the shipped request) rather than "no opinion", so
    the object being at its default is what says it has nothing to add.
    """
    if keyword != default and stated != default:
        raise ValueError(
            f"{caller} got both {name}= and an options= that states one; "
            f"pass one or the other, not both"
        )
    return stated if keyword == default else keyword


def resolve_knobs(
    options: Optional[ArrangeOptions],
    *,
    top_strings: Tuple[int, ...],
    non_chord_tone: str,
    fret_min: int,
    fret_max: int,
    request: Request = DEFAULT_REQUEST,
    time_signature: TimeSignature = COMMON_TIME,
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

    The five axes - `texture`, `bass`, `parts`, `harmony`, `grid` - are **not**
    among those keywords: they are the engine's implementation rather than a question
    a caller asks, so they are read off `options` or derived from the request.

    The request and the metre are **input facts** the other way - they say *what* is
    being arranged - so `settle_input_fact` lets them sit *beside* `options=`: the
    keyword wins, the object's own is read only when the keyword was left at its
    default, and both stated raises.

    Extracted from `arrange_progression` so the conflict rule and the up-front
    validation sit in one place rather than at the top of a thousand-line loop: a
    typo costs a message rather than a full arrangement followed by a surprise.
    """
    # `None` means "derive this from the request", which is what every axis means
    # unless `options` spells it out - the only door left to one.
    stated = options if options is not None else ArrangeOptions()
    texture, bass, parts, harmony, grid = (
        stated.texture, stated.bass, stated.parts, stated.harmony, stated.grid
    )
    if options is not None:
        given = _conflicts(
            top_strings=top_strings, non_chord_tone=non_chord_tone,
            fret_min=fret_min, fret_max=fret_max, melody_onsets=melody_onsets,
        )
        if given:
            raise ValueError(
                f"arrange_progression got both options= and the keyword(s) "
                f"{sorted(given)}; pass one or the other, not both"
            )
        request = settle_input_fact(
            request, options.request, DEFAULT_REQUEST, "request", "arrange_progression"
        )
        time_signature = settle_input_fact(
            time_signature, options.time_signature, COMMON_TIME,
            "time_signature", "arrange_progression",
        )
        top_strings = options.top_strings
        non_chord_tone = options.non_chord_tone
        fret_min = options.fret_min
        fret_max = options.fret_max
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
    # Resolved once, here, and passed down: an axis that cannot honour the request
    # raises rather than degrading to a value the caller did not ask for, so what a
    # caller sees is the refusal rather than an arrangement answering a different
    # question. The signature validated itself at construction; this reads the
    # concrete felt beats the metric layer consumes.
    beats_per_bar = time_signature.beats_per_bar
    beat_type = time_signature.beat_type
    resolved_grouping = time_signature.resolved_grouping

    # **The request is resolved before the axis overrides are read**, because it is
    # the derivation those overrides replace: `chord_notes` becomes the texture, the
    # two rhythms decide the parts, and `bass_notes` the note rules. An override is
    # the engine's own spelling of one axis and wins, which is how the axis tests
    # hold a texture or a bass policy to its behaviour without going through the
    # public questions.
    axes = resolve_axes(request, texture, bass, parts, harmony, time_signature)
    resolved, texture, bass = axes.request, axes.texture, axes.bass
    parts, harmony = axes.parts, axes.harmony
    # `texture` is the one axis with no sentinel to answer, so this is its whole
    # resolution: a membership check owned by `texture`, so the vocabulary is
    # spelled in one module rather than once per caller.
    texture = parse_texture(texture)

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
        request=resolved,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        grouping=resolved_grouping,
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
    #: The chord's rhythm. `None` when the caller spelled a `grid` preset instead,
    #: which is the internal axis; the preset then decides where a chord falls.
    chord_rhythm: Optional[Rhythm]
    grid_pattern: Optional[str]
    #: The bass's rhythm, and what the chord states in a notated melody rest.
    bass_rhythm: Rhythm
    chord_fills: str
    grouping: Tuple[int, ...]
    slots: Optional[List[Slot]]


def resolve_policies(
    progression: Sequence[Tuple[Optional[str], str, str]],
    *,
    parts_arg: str,
    texture: str,
    bass: str,
    harmony: str,
    grid: Optional[str],
    chord_rhythm: Optional[Rhythm],
    bass_rhythm: Rhythm,
    chord_fills: str,
    beats_per_bar: int,
    beat_type: int,
    grouping: Tuple[int, ...],
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]],
) -> _Policies:
    """The axes resolved once per arrangement, plus the walked-beat union.

    Resolved up front rather than per step: the band does not change halfway
    through a tune, and a spelling nobody recognises has to be reported **once**
    rather than never at all on an arrangement where the guitar happens to be
    singing.

    **The parts axis comes before the bass policy because the bass policy needs
    to know which route the engine is on**, and only this function knows.
    `resolve_bass` measures thumb capacity against `texture.texture_palette`, which
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
    # whatever `texture` says - the texture is inert on that route, the same
    # way it is on the comping one.
    melody_only = parts_has_melody_only(parts)

    # The bass policy. `auto` means "whatever this selection means", and the shipped
    # answer is no line at all; a melody-only selection that also names the bass part
    # is the one case that walks. An explicit style overrides both, which is what lets
    # a texture that was never written for a thumb line carry one.
    #
    # `resolve_bass` lives in `bass_rules` and takes the resolved `parts` rather than
    # the flags derived from them - the route, the arity and the lone-bass case are
    # decided inside from the selection, so the two spellings of one request cannot
    # disagree.
    bass = resolve_bass(bass, parts, texture)
    has_thumb = bass != BASS_STYLE_NONE

    # The harmony axis, resolved here for the same reason and read only by the
    # comping route below. Resolving it unconditionally rather than inside
    # `if not melody_voiced` is deliberate: a spelling nobody recognises must be
    # reported **once, up front**, rather than never at all on an arrangement where
    # the guitar happens to be singing - the same argument as `_resolve_melody`'s.
    harmony_family = _resolve_harmony(harmony, parts)
    # The grid axis, resolved here for the same reason and read by **both** routes
    # below rather than only the comping one - unlike `harmony`, which the guitar
    # singing makes unreachable. A grid says where a chord lands, and that is a
    # question about the part whether the guitar is singing it or comping under a
    # horn, so scoping it to one route would make `grid` silently inert on a
    # melody-bearing arrangement rather than doing nothing there.
    grid_pattern = (
        None if grid is None else _resolve_grid(grid, beats_per_bar, grouping)
    )

    slots: Optional[List[Slot]] = None
    if has_thumb:
        # Decision B: the union is built here, before the melody loop, so the
        # loop's index still indexes the skeleton it was given. `walking_slots`
        # is shared with `slots.arrange_slots`, so an imported head and a
        # hand-built progression cannot walk a different line from this one - see
        # its docstring for why that duplication has already cost this project one
        # bug.
        slots = walking_slots(
            progression,
            timings,
            beats_per_bar,
            beat_type,
            grouping=grouping,
            bass=bass,
            rhythm=bass_rhythm,
        )

    return _Policies(
        parts=parts,
        melody_voiced=melody_voiced,
        melody_only=melody_only,
        bass=bass,
        has_thumb=has_thumb,
        harmony_family=harmony_family,
        chord_rhythm=chord_rhythm,
        grid_pattern=grid_pattern,
        bass_rhythm=bass_rhythm,
        chord_fills=chord_fills,
        grouping=grouping,
        slots=slots,
    )
