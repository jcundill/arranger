"""The knobs an arrangement is made with, as one value.

The **request** is the public vocabulary: who plays the tune, when each
accompaniment layer attacks, what each states, and what the chord does in a melody
rest - six questions. `head`'s six flags and `Request(...)` are two spellings of
them, and `resolve_request` turns either into the engine's internal axes - `parts`,
`texture`, `bass` and the chord's rhythm - which is what the step loop
actually reads.

**This object is the only door to the four axes.** They are the engine's implementation
rather than a question a caller asks, so no entry point takes one as a keyword - a caller
who wants a texture or a bass policy names it here, and the axis tests hold each to its own
behaviour that way. `None` means "derive this from the request"; a value means "the
implementation axis, spelled out". The request and the metre are the exception the other
way: they are **input facts**, so `request=` and `time_signature=` sit beside `options=` on
the entry points and `resolution.settle_input_fact` reconciles the two spellings.

Frozen, because an options object that can be mutated halfway through arranging is
worse than the keyword list it replaces - the failure would depend on *when* it was
written. Build a second one instead.

Every field's default is the same value the entry point's keyword defaults to, so
`ArrangeOptions()` asks for exactly what `arrange_progression(progression)` builds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Container, Dict, Mapping, Optional, Sequence, Tuple

from .bass_rules import (
    BASS_RULE_5TH,
    BASS_RULE_ROOT,
    BASS_RULES,
    BASS_STYLE_NONE,
    parse_bass_style,
)
from .grid import (
    RHYTHM_MELODY,
    RHYTHM_NONE,
    Rhythm,
    parse_rhythm,
)
from .grip_tables import RIGHT_HAND_STRINGS
from .grouping import COMMON_TIME, TimeSignature
from .parts import PART_BASS, PART_CHORD, PART_MELODY, PART_NAMES
from .texture import texture_arity
from .tuning import MELODY_STRING_CHOICES_FULL, NECK_FRET_MAX, NECK_FRET_MIN

# `(bar, beat, duration)` for one slot. `bar` is signed - a pickup is negative -
# `beat` is within the bar, and both are Optional because a caller may simply not
# know where its notes fall. `None` throughout is "no rhythm supplied", which the
# texture rules read as "every slot is a principal note".
Timing = Tuple[Optional[int], Optional[float], Optional[float]]


# --- the request: two rhythm questions and two content questions -------------

CHORD_NOTES_FULL = "full"
CHORD_NOTES_TARGETS = "targets"

#: The chord part's arity, as the request names it, mapped to the texture that
#: states it. `full` is the **derivation** rather than a number: it means the most
#: the right hand can fit at that position - three notes under the melody, and two
#: when a bass note takes a string - which is why it is `uniform` and not `chord3`.
#:
#: `targets` is the one value whose answer **varies by position**: the same maximum
#: as `full` on a strong beat, and a thinner shape between them (`texture.TARGET_BEATS`).
#: It is a content answer rather than a rhythm one - where those strong beats *are* is
#: the metre's and the grouping's business, not the caller's - which is why it belongs
#: on this question rather than on `chord_on`.
CHORD_NOTES: Dict[str, str] = {
    CHORD_NOTES_FULL: "uniform",
    CHORD_NOTES_TARGETS: "targets",
    "3": "chord3",
    "2": "chord2",
    "1": "chord1",
}

BASS_NOTES_ROOT = "root"
BASS_NOTES_ROOT_FIFTH = "root-5th"
BASS_NOTES_WALK = "walk"

#: What a bass note states, mapped to the note rules the thumb line is written on.
#: The names say *which note*, not *which rhythm* - the rhythm is `bass_on`'s, and
#: that separation is the point of the redesign: `bass_on every-beat` with
#: `bass_notes root` is a pedal, not the old "root only where the harmony anchors".
BASS_NOTES: Dict[str, str] = {
    BASS_NOTES_ROOT: BASS_RULE_ROOT,
    BASS_NOTES_ROOT_FIFTH: f"{BASS_RULE_ROOT},{BASS_RULE_5TH}",
    BASS_NOTES_WALK: ",".join(BASS_RULES),
}

CHORD_FILLS_NONE = "none"
CHORD_FILLS_HOLD = "hold"
CHORD_FILLS_COMP = "comp"

#: What the chord states in a **notated melody rest**. Not a rhythm: a rest has no
#: melody note to attach to, and the flag is a policy for a different span.
CHORD_FILLS: Tuple[str, ...] = (
    CHORD_FILLS_NONE,
    CHORD_FILLS_HOLD,
    CHORD_FILLS_COMP,
)


@dataclass(frozen=True)
class Request:
    """The six questions a caller asks, before they become the engine's axes.

    The same six `head`'s flags ask, so a command line and a library name one
    request: passing this value to `arrange_progression` is the library spelling,
    and the axis keywords beside it are overrides rather than a second request.

    One value rather than six loose keywords, because the six are one request: a
    caller that names the chord's rhythm and the bass's content is describing one
    accompaniment, and a value is what keeps it from being threaded as six
    independent strings through three layers.

    Every default is the shipped arrangement: the guitar sings, the chord states
    the full harmonisation under each written melody note, and nothing else
    sounds. That is what makes `head FILE` the melody and no added rhythm.
    """

    melody: bool = True
    #: When the chord attacks: `melody` (the written onsets), `none`, or
    #: positions such as `1and`. See `grid.parse_rhythm`.
    chord_on: str = RHYTHM_MELODY
    #: How many chord notes to state, `full` being "the most that fits" and
    #: `targets` "the most that fits on a strong beat, thinner between".
    chord_notes: str = CHORD_NOTES_FULL
    #: When the bass attacks. `none` is no bass line.
    bass_on: str = RHYTHM_NONE
    #: What each bass note is: the root, root and fifth, or a walk.
    bass_notes: str = BASS_NOTES_ROOT
    #: What the chord states in a notated melody rest.
    chord_fills: str = CHORD_FILLS_NONE


#: The shipped request, as one value. A **module-level singleton** rather than a
#: call in each signature: `Request()` in a default is evaluated once at import,
#: but ruff's B008 is right that a call in a default is a trap - the next default
#: that is *not* frozen would be shared between calls.
DEFAULT_REQUEST = Request()


@dataclass(frozen=True)
class ResolvedRequest:
    """The request, and the internal axes it resolves to.

    `chord_on` and `bass_on` are the **canonical** spellings of the two rhythms,
    so the run header prints a request that parses back to this value rather than
    the caller's own spelling of it (`every-beat` prints as the positions it
    resolves to, which is the same request in that metre).
    """

    melody: bool
    chord_notes: str
    bass_notes: str
    chord_fills: str
    chord_rhythm: Rhythm
    bass_rhythm: Rhythm
    parts: Tuple[str, ...]
    texture: str
    bass: str

    @property
    def chord_on(self) -> str:
        """The chord rhythm's canonical spelling."""
        return str(self.chord_rhythm)

    @property
    def bass_on(self) -> str:
        """The bass rhythm's canonical spelling."""
        return str(self.bass_rhythm)


def resolve_request(
    request: Request,
    beats_per_bar: int,
    grouping: Optional[Sequence[int]] = None,
) -> ResolvedRequest:
    """The request resolved into the engine's axes, with every refusal up front.

    Resolution is a **derivation**, not a set of defaults: `chord_on` names the
    chord's rhythm and `bass_on` the bass's, so `parts` is decided from them rather
    than spelled separately. A question about a layer the request leaves silent is
    refused rather than ignored - the library's standing rule that a request it
    cannot honour is answered with a reason, never with an arrangement that quietly
    answers a different one.

    **`chord_on="melody"` reads the same whether or not this guitar sings the tune.**
    The written onsets are a fact about the *score* - which is how `bass_on="melody"`
    has always read them - so a comping selection states the chord on the tune's own
    rhythm rather than being handed the metre's reading in its place. A caller who
    wants every felt beat asks for it: `chord_on="every-beat"` is the same request
    whichever part is the guitar's.
    """
    chord_rhythm = parse_rhythm(request.chord_on, beats_per_bar, grouping)
    bass_rhythm = parse_rhythm(request.bass_on, beats_per_bar, grouping)
    return _resolved(request, chord_rhythm, bass_rhythm)


def _resolved(
    request: Request, chord_rhythm: Rhythm, bass_rhythm: Rhythm
) -> ResolvedRequest:
    """The value `resolve_request` returns, from the request and its parsed rhythms."""
    fills = _named(request.chord_fills, _identity(CHORD_FILLS), "chord-fills")
    bass_notes = _bass_notes_name(request.bass_notes)
    resolved = ResolvedRequest(
        melody=request.melody,
        chord_notes=request.chord_notes,
        bass_notes=bass_notes,
        chord_fills=fills,
        chord_rhythm=chord_rhythm,
        bass_rhythm=bass_rhythm,
        parts=_request_parts(
            request.melody,
            not chord_rhythm.is_none or fills != CHORD_FILLS_NONE,
            not bass_rhythm.is_none,
        ),
        texture=_named(request.chord_notes, CHORD_NOTES, "chord-notes"),
        bass=_bass_policy(bass_notes, bass_rhythm),
    )
    _refuse(resolved)
    return resolved


def format_request(request: ResolvedRequest) -> str:
    """The request as one line: `key=value` pairs a reader can copy back.

    Canonical, so it is the *arrangement* the engine is building rather than the
    caller's spelling of it, and space-separated rather than prose so the round
    trip is a test rather than a reading exercise.
    """
    return " ".join(
        (
            f"melody={'on' if request.melody else 'off'}",
            f"chord-on={request.chord_on}",
            f"chord-notes={request.chord_notes}",
            f"bass-on={request.bass_on}",
            f"bass-notes={request.bass_notes}",
            f"chord-fills={request.chord_fills}",
        )
    )


def _identity(names: Sequence[str]) -> Dict[str, str]:
    """A closed vocabulary as a lookup that names itself, for `_named`."""
    return {name: name for name in names}


def _named(value: str, vocabulary: Dict[str, str], label: str) -> str:
    """`value` mapped through `vocabulary`, or a refusal that lists the choices.

    One function for all three content questions, so a new one is a row in a table
    rather than a fourth copy of the same error message.
    """
    if value not in vocabulary:
        raise ValueError(
            f"Unknown {label} {value!r}; expected any of "
            f"{', '.join(vocabulary)}"
        )
    return vocabulary[value]


def _bass_notes_name(bass_notes: str) -> str:
    """The caller's answer to the content question, in one canonical spelling.

    A **name** is already canonical - it is the vocabulary's own word - and a rule
    list is written the way `parse_bass_style` reads it back: lowercase, no whitespace
    around the commas, in the order given. That is what `format_request` prints and
    what a reader pastes back, so the two are the same string, and the value is
    validated here rather than at the point of use.
    """
    if bass_notes in BASS_NOTES:
        return bass_notes
    return _bass_rules(bass_notes)


def _bass_policy(bass_notes: str, bass_rhythm: Rhythm) -> str:
    """The note rules to run, or no line when the bass never attacks.

    The rhythm decides *whether* there is a line at all, and the names decide what
    it states - so `bass_on none` is no line whatever it is asked to state, rather
    than a policy that silently exists with nothing to play it.

    A value is either one of the three **names** or the rules themselves as a
    comma-separated list, which is the axis's own spelling: `walk` is
    `root,5th,approach,nearest`, so a caller who wants a subset the names do not
    offer (`root,approach`) asks for it in the request rather than reaching for
    `options=`. The list is validated by `bass_rules.parse_bass_style`, which owns the
    vocabulary, its order and its message - the order **is** the resolution order, so
    it is kept as spelled rather than sorted.
    """
    if bass_rhythm.is_none:
        return BASS_STYLE_NONE
    if bass_notes in BASS_NOTES:
        return BASS_NOTES[bass_notes]
    return _bass_rules(bass_notes)


def _bass_rules(bass_notes: str) -> str:
    """`bass_notes` read as the rule list itself, or a refusal naming both spellings.

    The names and the rules are one vocabulary written two ways, so the message lists
    both: a caller who wrote `swing` is told what `root`/`root-5th`/`walk` mean and
    what the rules are, rather than being handed the parser's list of the three.
    """
    try:
        return ",".join(parse_bass_style(bass_notes))
    except ValueError:
        raise ValueError(
            f"Unknown bass-notes {bass_notes!r}; expected any of "
            f"{', '.join(BASS_NOTES)}, or a comma-separated list of "
            f"{', '.join(BASS_RULES)}"
        ) from None


def _request_parts(melody: bool, has_chord: bool, has_bass: bool) -> Tuple[str, ...]:
    """The parts the request asks the guitar to take, in `PART_NAMES` order.

    Derived rather than spelled, which is the whole point: one fact decides each
    part, and the parts selection is a **set**, so its order is canonicalised here
    for the same reason `parse_parts` canonicalises a caller's.
    """
    chosen = {PART_MELODY if melody else "", PART_CHORD if has_chord else "",
              PART_BASS if has_bass else ""}
    return tuple(name for name in PART_NAMES if name in chosen)


def _refuse(resolved: ResolvedRequest) -> None:
    """Every request the engine cannot honour, refused before any voicing work."""
    _refuse_melody(resolved)
    _refuse_content(resolved)
    _refuse_capacity(resolved)


def _refuse_melody(resolved: ResolvedRequest) -> None:
    """The one remaining question that only makes sense when the guitar sings the tune.

    It is about a **span of the tune** - its notated rests - and the guitar has no
    tune on its part to attach it to, so it cannot be answered by guessing a different
    policy. `chord-on=melody` is not refused and needs no derivation: the written
    onsets are a fact about the score, so a comping selection reads them like any
    other request does.
    """
    if not resolved.melody and resolved.chord_fills != CHORD_FILLS_NONE:
        raise ValueError(
            f"chord-fills={resolved.chord_fills} is a policy for a notated melody "
            f"rest, and melody=off means there are no melody rests to fill - drop "
            f"the fills, or let the guitar play the tune"
        )


def _refuse_content(resolved: ResolvedRequest) -> None:
    """A content question for a part the request leaves silent, and the empty bar."""
    _refuse_chord_content(resolved)
    _refuse_bass_content(resolved)
    if not resolved.parts:
        raise ValueError(
            "the request leaves the guitar nothing to play: melody=off with no "
            "chord and no bass position"
        )


def _refuse_chord_content(resolved: ResolvedRequest) -> None:
    """How many chord notes, asked of a chord part that never attacks."""
    if PART_CHORD in resolved.parts or resolved.chord_notes == CHORD_NOTES_FULL:
        return
    raise ValueError(
        f"chord-notes={resolved.chord_notes} is a content choice for the chord "
        f"part, and chord-on=none leaves it silent - name a chord position, or "
        f"drop the choice"
    )


def _refuse_bass_content(resolved: ResolvedRequest) -> None:
    """What the bass states, asked of a bass part that never attacks."""
    if PART_BASS in resolved.parts or resolved.bass_notes == BASS_NOTES_ROOT:
        return
    raise ValueError(
        f"bass-notes={resolved.bass_notes} is a content choice for the bass "
        f"part, and bass-on=none leaves it silent - name a bass position, or "
        f"drop the choice"
    )


def _refuse_capacity(resolved: ResolvedRequest) -> None:
    """`melody + bass + chord <= RIGHT_HAND_STRINGS`, checked as arithmetic.

    **The arity is read from the texture table, not from the request's spelling.** A
    spelling that names a *number* is the only one that can over-ask - `full` and
    `targets` mean "the most that fits", so they cannot - and `texture.texture_arity`
    is what says which spellings those are. Parsing the request's own string would be
    the same fact written twice, and it would have to grow a branch per value: a
    four-note chord under a melody with a bass beneath it is five strings, a request
    no voicing can honour and no renderer could show.
    """
    arity = texture_arity(resolved.texture, resolved.parts)
    if arity is None:
        return
    strings = (
        arity
        + int(resolved.melody)
        + int(PART_BASS in resolved.parts)
    )
    if strings > RIGHT_HAND_STRINGS:
        raise ValueError(
            f"chord-notes={resolved.chord_notes} under a melody "
            f"{'and a bass ' if PART_BASS in resolved.parts else ''}is {strings} "
            f"right-hand strings, and the hand plucks {RIGHT_HAND_STRINGS}; ask "
            f"for full, which states the most that fits"
        )



@dataclass(frozen=True)
class ArrangeOptions:
    """Every knob `VoiceLeadingEngine.arrange_progression` reads."""

    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL
    non_chord_tone: str = "extension"
    fret_min: int = NECK_FRET_MIN
    fret_max: int = NECK_FRET_MAX
    # --- the request ---
    # The six questions as one value: who plays the tune, when each accompaniment
    # layer attacks, and what each states. Everything else in this dataclass is the
    # engine's **implementation axis**; `None` means "derive it from the request",
    # and a value is the axis spelled out - which is how the axis tests hold a
    # texture or a bass policy directly to its own behaviour.
    request: Request = Request()
    # --- implementation overrides ---
    # How many notes the chord part states (`TEXTURE_ARITY`). Derived from
    # `request.chord_notes`: `full` is `uniform`, which means the most the right
    # hand can fit at that position.
    texture: Optional[str] = None
    # The note rules the thumb line is written on (`BASS_RULES`). Derived from
    # `request.bass_notes`, or `none` when `request.bass_on` never attacks.
    bass: Optional[str] = None
    # Which of melody / bass / chord the guitar takes (`PART_NAMES`). Derived from
    # the request, because the three questions already decide it: the tune, a chord
    # position, a bass position.
    parts: Optional[str] = None
    # The metre as one value: the count, the denominator and the grouping. The
    # denominator is not decoration - a beat is `4 / beat_type` quarters, so the
    # count alone says which beats exist but not how long one lasts. The grouping is
    # validated against the count when the signature is built, because 12/8 and 12/4
    # share a count and are different bars. A hand-built progression that declares
    # none gets `COMMON_TIME`, which is the metre every bare call had.
    time_signature: TimeSignature = COMMON_TIME
    # `Sequence`, not `List`, and that is load-bearing rather than stylistic: the
    # library and the corpus hold *different* timing types - `Tuple[int, float, ...]`
    # against `Tuple[Optional[int], ...]` placeholders for slots it could not place.
    # `List` is invariant so neither is assignable to the other and the two paths
    # could not share one signature; `Sequence` is covariant so both are accepted.
    # This is the third time list invariance in a signature has cost this library
    # something, and the fourth would not have been a surprise.
    timings: Optional[Sequence[Timing]] = None
    # Per-progression-index bass pitch class: the note a written slash chord asks
    # for (`A-/G` wants G). It narrows *which candidates are considered*, and the
    # engine's own rule then decides within that narrowed set, so the two selection
    # rules stay combined rather than sequential. Absent or None for an index means
    # no restriction, which is exactly the library's own behaviour.
    #
    # The ranking that honours it is `chords.slash_bass_cost`, which `decisions`
    # calls directly - it is pure integer arithmetic over a voicing and a pitch
    # class, and `chords` sits below `decisions` in the order. There is nothing to
    # inject, so this field is the whole of the request.
    bass_pcs: Optional[Mapping[int, Optional[int]]] = None
    # The progression indexes whose melody note **articulates** (an onset), for the
    # §9.2 reharmonise rule on the comping route: a non-chord melody note is
    # substituted where it begins, not under a held note and not where the tune is
    # silent. `None` means *every* slot is an onset - the honest answer for a caller who
    # said nothing about onsets, so a bare `arrange_progression(..., parts=chord)` still
    # honours `--non-chord-tone`.
    # The head layer computes it from `headxml.melody_state`, which is the one place
    # that knows a note is sounding rather than merely in force.
    #
    # It sits beside `bass_pcs` rather than on the harmony axis because it is per-slot
    # *data* about the input, like the timings, not a policy a caller chooses.
    melody_onsets: Optional[Container[int]] = None
