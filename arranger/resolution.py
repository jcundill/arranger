"""What the caller asked for, resolved once: parts, bass and the knobs.

The request is the one door. Every axis the step loop reads - which parts the guitar
takes, how many notes the chord part states, the note rules the thumb line is written
on - is derived from it here, so the loop only ever reads a concrete value. Pure
policy: no voicing is built and no step is emitted. It sits above `movement`, which
calls the two resolvers it still needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Container, List, Mapping, Optional, Sequence, Tuple

from .bass import (
    Slot,
    walking_slots,
)
from .bass_rules import (
    BASS_STYLE_NONE,
    resolve_bass,
)
from .chords import (
    NON_CHORD_TONE_STRATEGIES,
)
from .grid import Rhythm
from .grouping import COMMON_TIME, TimeSignature
from .options import (
    DEFAULT_REQUEST,
    ArrangeOptions,
    Request,
    ResolvedRequest,
    Timing,
    resolve_request,
)
from .parts import (
    parts_has_melody_only,
    parts_have_melody,
)


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
    parts: Tuple[str, ...]
    request: ResolvedRequest
    beats_per_bar: int
    beat_type: int
    grouping: Tuple[int, ...]
    melody_onsets: Optional[Container[int]]
    timings: Optional[Sequence[Tuple[Optional[int], Optional[float], Optional[float]]]]
    bass_pcs: Optional[Mapping[int, Optional[int]]]


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


def felt_beat_timings(count: int, beats_per_bar: int) -> List[Timing]:
    """The metre's own layout for a progression that supplied no timeline.

    Entry `i` lands on bar `i // beats_per_bar + 1`, beat `i % beats_per_bar + 1`, one
    entry per felt beat in the bar - so a hand-built progression is arranged as the bars
    it names rather than as a run of positions the metric layer knows nothing about. It
    is the same bar-and-beat numbering `headxml` writes, and it is what lets a requested
    chord rhythm have somewhere to land: before it, `chord_on` on a timing-less
    progression placed no chord at all.

    **The duration stays `None`.** A bar and a beat are positions the metre states; a
    duration is a *notated* length the caller never gave, and inventing one would also
    move the staff renderers, which space a column by it.

    **The bar is not completed.** Four entries make one bar in 4/4; three make three
    beats of it, because inventing the fourth would state a chord the caller did not
    write. A caller that wants whole bars - the MusicXML importer does - supplies its
    own timings, one per position.
    """
    return [
        (index // beats_per_bar + 1, float(index % beats_per_bar + 1), None)
        for index in range(count)
    ]


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

    The axes - the chord part's content, the bass policy and the parts selection -
    are **not** among those keywords: they are the engine's implementation rather than
    a question a caller asks, so they are derived from the request.

    The request and the metre are **input facts** the other way - they say *what* is
    being arranged - so `settle_input_fact` lets them sit *beside* `options=`: the
    keyword wins, the object's own is read only when the keyword was left at its
    default, and both stated raises.

    Extracted from `arrange_progression` so the conflict rule and the up-front
    validation sit in one place rather than at the top of a thousand-line loop: a
    typo costs a message rather than a full arrangement followed by a surprise.
    """
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

    # **The request is the one door to the axes.** `chord_notes` becomes the chord
    # part's content, the two rhythms decide the parts, and `bass_notes` the note
    # rules - so there is no second spelling of any axis for this function to
    # reconcile, and the loop reads the derivation directly.
    resolved = resolve_request(request, beats_per_bar, resolved_grouping)

    return _Knobs(
        top_strings=top_strings,
        non_chord_tone=non_chord_tone,
        fret_min=fret_min,
        fret_max=fret_max,
        texture=resolved.texture,
        bass=resolved.bass,
        parts=resolved.parts,
        request=resolved,
        beats_per_bar=beats_per_bar,
        beat_type=beat_type,
        grouping=resolved_grouping,
        melody_onsets=melody_onsets,
        timings=timings,
        bass_pcs=bass_pcs,
    )


@dataclass(frozen=True)
class _Policies:
    """The axes and the walked-beat union, resolved once per arrangement.

    `parts`/`melody_voiced`/`melody_only` come off the parts axis, `bass` and
    `has_thumb` off the bass policy, and `slots` is the walked-beat union when a thumb
    line is running. Resolved up front because the band does not change halfway through a
    tune, and unpacked straight back into the names the loop has always used.
    """

    parts: Tuple[str, ...]
    melody_voiced: bool
    melody_only: bool
    bass: str
    has_thumb: bool
    #: The chord's rhythm, from the request's `chord_on`.
    chord_rhythm: Optional[Rhythm]
    chord_fills: str
    grouping: Tuple[int, ...]
    slots: Optional[List[Slot]]


def resolve_policies(
    progression: Sequence[Tuple[Optional[str], str, str]],
    *,
    parts: Tuple[str, ...],
    texture: str,
    bass: str,
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

    **The selection comes before the bass policy because the bass policy needs to
    know which route the engine is on**, and only this function knows.
    `resolve_bass` measures thumb capacity against `texture.texture_palette`, which
    describes the shapes the melody-bearing route generates and is *inert* on the
    comping one - so asking it about a texture on that route refused a
    combination that is playable and, worse, told the player to change a setting
    that could not affect the result. See `comping_capacity`.

    The two resolutions are independent of each other, so the order between them
    carries no other meaning; what matters is that both finish before `has_thumb`
    is read, because that flag gates whether the walked-beat union is built.
    """
    melody_voiced = parts_have_melody(parts)
    # The melody-only selection, decided once here and read by the bass policy,
    # the grip resolution and the promotion rule below: the tune alone and the tune
    # with a thumb under it are one selection, and the chord content is inert on
    # that route, the same way it is on the comping one.
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
        chord_rhythm=chord_rhythm,
        chord_fills=chord_fills,
        grouping=grouping,
        slots=slots,
    )
