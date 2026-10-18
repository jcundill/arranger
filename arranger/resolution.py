"""What the caller asked for, resolved once: parts, grid, harmony, bass and the knobs.

Every `*_AUTO` sentinel on the axes is answered here, against the selection and the
texture, so the step loop only ever reads a concrete value. Pure policy: no voicing is
built and no step is emitted. It sits above `movement`, which calls the two resolvers it
still needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Container, List, Mapping, Optional, Sequence, Tuple

from .bass import (
    Slot,
    walking_slots,
)
from .bass_rules import (
    BASS_STYLE_AUTO,
    BASS_STYLE_NONE,
    BASS_STYLE_WALK,
    bass_allowed,
    parse_bass_style,
)
from .chords import (
    NON_CHORD_TONE_STRATEGIES,
)
from .grid import parse_grid, resolve_grid
from .grouping import (
    GROUPING_AUTO,
    parse_grouping,
    resolve_grouping,
)
from .harmony import (
    parse_harmony,
    resolve_harmony,
)
from .options import ArrangeOptions
from .parts import (
    PART_BASS,
    parse_parts,
    parts_has_melody_only,
    parts_have_bass,
    parts_have_melody,
    resolve_parts,
)
from .texture import (
    TEXTURE_STYLES,
    derived_arity,
)


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


def _resolve_grouping(
    grouping: str, beats_per_bar: int, beat_type: int
) -> Tuple[int, ...]:
    """The grouping to feel the bar in: parsed, `auto` derived, validated.

    The same two-step shape again, and resolved here for the same reason: a spelling
    nobody recognises has to be reported once, before any voicing work, and the
    derived value is then a concrete tuple the metric layer can read without
    deciding anything.
    """
    return resolve_grouping(parse_grouping(grouping), beats_per_bar, beat_type)


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
    grouping: Tuple[int, ...]
    melody_onsets: Optional[Container[int]]
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]]
    bass_pcs: Optional[Mapping[int, Optional[int]]]
    slash_bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]]


def resolve_knobs(
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
    grouping: str = GROUPING_AUTO,
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
                ("grouping", grouping),
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
        grouping = options.grouping
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
    resolved_grouping = _resolve_grouping(grouping, beats_per_bar, beat_type)

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
    grid_pattern: str
    grouping: Tuple[int, ...]
    slots: Optional[List[Slot]]


def resolve_policies(
    progression: Sequence[Tuple[Optional[str], str, str]],
    *,
    parts_arg: str,
    texture: str,
    bass: str,
    harmony: str,
    grid: str,
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
    grid_pattern = _resolve_grid(grid, beats_per_bar, grouping)

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
        )

    return _Policies(
        parts=parts,
        melody_voiced=melody_voiced,
        melody_only=melody_only,
        bass=bass,
        has_thumb=has_thumb,
        harmony_family=harmony_family,
        grid_pattern=grid_pattern,
        grouping=grouping,
        slots=slots,
    )
