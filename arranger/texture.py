"""The texture axis: how many notes the chord part states, by metric weight.

`texture=` owns **how many notes the chord part states**. It is not a grip list:
the grip families are an internal search space over the chord part's degrees
and the neck window, keyed by the number of notes they sound under the melody.
What remains a choice is the arity and the metric policy that varies it.

  uniform   the most notes the arithmetic allows at that position - the whole
            chord, and the shipped default
  targets   the same maximum on a strong beat and a thinner shape between them
  chord1    exactly one note under the melody
  chord2    exactly two
  chord3    exactly three

`chord4` is not built: four notes under a melody is five strings, which the
right hand's four digits cannot pluck.

`texture.py` imports `GRIP_PREFERENCE`, `GRIP_STRING_SETS`, `RIGHT_HAND_STRINGS`
from `grips`, `ROLE_FILL` and `ROLE_TARGET` from `tuning`, and `PART_MELODY`
and `parts_have_melody` from `parts`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .grip_tables import (
    GRIP_PREFERENCE,
    GRIP_STRING_SETS,
    RIGHT_HAND_STRINGS,
)
from .parts import PART_MELODY, parts_have_melody
from .tuning import ROLE_FILL, ROLE_TARGET

TEXTURE_STYLES: Tuple[str, ...] = (
    "uniform",
    "targets",
    "chord1",
    "chord2",
    "chord3",
)

TEXTURE_ARITY: Dict[str, Optional[int]] = {
    "uniform": None,
    "targets": None,
    "chord1": 1,
    "chord2": 2,
    "chord3": 3,
}

TARGET_BEATS: Tuple[int, ...] = (1, 3)

FILL_THINNING = 1

THIN_ENTRIES: Dict[str, int] = {
    "interval": 1,
    "melody": 0,
}

FILL_ONLY_EXCLUDED: Tuple[str, ...] = ("duo",)


def families_for_arity(arity: int) -> Tuple[str, ...]:
    """The grip families that state exactly `arity` notes under the melody.

    Derived from the string tables rather than listed, so a family added to the
    search space joins at its own size rather than needing a row here. `arity` below
    one is the empty palette - "the left hand plays nothing" - which is a real answer
    rather than an error, because that is what a one-note fill means.
    """
    if arity < 1:
        return ()
    families: List[str] = []
    for family in GRIP_PREFERENCE:
        sets = GRIP_STRING_SETS.get(family, ())
        if not sets:
            continue
        if min(len(strings) for strings, _soprano in sets) == arity + 1:
            families.append(family)
    return tuple(families)


def families_up_to_arity(arity: int) -> Tuple[str, ...]:
    """Every family that states **at most** `arity` notes under the melody.

    The arity a slot is offered is a **ceiling, not an exact count**: what the
    texture states is the most the arithmetic allows *here*, and the selector picks
    the fullest candidate that fits the position.
    """
    if arity < 1:
        return ()
    families: List[str] = []
    for family in GRIP_PREFERENCE:
        sets = GRIP_STRING_SETS.get(family, ())
        if not sets:
            continue
        if min(len(strings) for strings, _soprano in sets) <= arity + 1:
            families.append(family)
    return tuple(families)


def families_up_to_with_thin(arity: int) -> Tuple[str, ...]:
    """`families_up_to_arity`, plus the non-grip thinners this ceiling admits.

    A fill is heard between two chords rather than *as* one, and the two entries that
    say that most cheaply are an interval and the tune alone - neither is a grip,
    because neither states a chord part. They come **last**, which is where the
    voice-count criterion would put them anyway.

    `FILL_ONLY_EXCLUDED` is removed first, so the 3rd/7th reading is not offered where
    the loose one is - the two are the same thickness, and an exact tie between them
    would otherwise be decided by the order of this tuple rather than by the rule.
    """
    return tuple(
        family for family in families_up_to_arity(arity)
        if family not in FILL_ONLY_EXCLUDED
    ) + tuple(name for name, size in THIN_ENTRIES.items() if size <= arity)


def texture_arity(texture: str, parts: Tuple[str, ...]) -> Optional[int]:
    """The chord part's arity under this texture, or `None` for "derived".

    `TEXTURE_ARITY[texture]` when the texture names one; `None` for `uniform` and
    `targets`, which take **the most notes the arithmetic allows at that position**:
    four strings minus the melody and the bass a selection takes. With the tune on top
    and no thumb that is three - the four-note shape this library has always built -
    and with a thumb under it the budget gives two, which is the shell.

    Raises `ValueError` for a texture outside `TEXTURE_STYLES`, before any voicing
    work, so a typo cannot cost a caller a full arrangement before it is reported.
    """
    if texture not in TEXTURE_ARITY:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    return TEXTURE_ARITY[texture]


def derived_arity(
    texture: str, parts: Tuple[str, ...], has_thumb: bool = False
) -> int:
    """The number of notes the chord part states at one position.

    A fixed texture is its own number; `uniform` and `targets` are the arithmetic:
    `RIGHT_HAND_STRINGS` minus the melody part a selection takes and minus the bass
    part **when one is actually sounding** - naming the part is not the same as writing
    a line under it, and a named part with no line leaves the string free.

    Capped at `chord3`, because a four-note chord part under nothing is
    `docs/history/comping-styles.md` §9.4 - unbuilt - and floored at one, so a selection can
    always state something.
    """
    fixed = texture_arity(texture, parts)
    if fixed is not None:
        return fixed
    budget = RIGHT_HAND_STRINGS - int(parts_have_melody(parts)) - int(has_thumb)
    return max(1, min(3, budget))


def comping_arity(
    texture: str, parts: Tuple[str, ...], has_thumb: bool = False
) -> int:
    """The chord part's arity at a position the guitar does **not** sing.

    `derived_arity`, with the melody's string not reserved - because at this position
    there is no note of the tune for it to carry. On a walked beat the tune is held
    rather than re-struck and on a comping slot it belongs to the horn, so the string
    the soprano would use is free for the chord part to state.

    Two facts this is not. It is **not** "the guitar is comping", which is a property
    of the selection and not of one position (`parts_have_melody` answers that); and it
    is **not** a per-slot budget rule - the string is free because nothing is sounding
    on it, which is a fact about this position.
    """
    free = tuple(part for part in parts if part != PART_MELODY)
    return derived_arity(texture, free, has_thumb)


def texture_palette(
    role: str,
    texture: str,
    parts: Tuple[str, ...],
    has_thumb: bool = False,
) -> Tuple[str, ...]:
    """The palette a slot of this role may use, and nothing else.

    A **target** states the chord part's full arity; a **fill** states
    `FILL_THINNING` notes fewer, which is the thickness claim the role
    has always made. Both are **ceilings rather than exact counts** - see
    `families_up_to_arity` - so the fullest shape a position admits is the one
    generated first, and a position only a shell fits is a shell rather than silence.

    A fill may also reach the two entries that are not grips at all (`interval`,
    `melody`); a target may not, because neither of them states a chord part.

    The empty tuple is a real answer, not an omission: it means the left hand plays
    nothing here, which is how a one-note fill reaches `get_melody_only_voicing` and how
    a melody-only selection reaches the same route.
    """
    arity = derived_arity(texture, parts, has_thumb)
    if role == ROLE_TARGET:
        return families_up_to_arity(arity)
    return families_up_to_with_thin(arity - FILL_THINNING)


BEAT_EPSILON = 1e-6


def metric_weight(
    bar: Optional[int], beat: Optional[float], beats_per_bar: int = 4
) -> int:
    """How metrically strong a slot is: 2 on beat 1, 1 on beat 3, 0 on any other beat.

    Returns **-1 when there is no timing at all** (`bar` or `beat` is None), which is
    the load-bearing part. A caller that does not know where its notes fall has not
    told us the note is weak - it has told us nothing - and treating those two the
    same would thin out every hand-written progression and every existing test. The
    -1 is what keeps the default behaviour byte-identical.

    `beats_per_bar` is honoured rather than assumed, because a count without a
    denominator is not a metre. `TARGET_BEATS` names *beats*, so in 2/2 (two notated
    beats) beat 3 does not exist and only the downbeat is a target; in 3/4 beats 1
    and 3 are targets exactly as they are in 4/4. `headxml`'s onset conversion and
    `bass._melody_timeline` honour the same denominator.

    A beat is compared with `BEAT_EPSILON` because a notated beat is a float and a
    tune rarely lands only on the integers: the middle note of a triplet inside beat 1
    of a 3/4 bar is at 1.333..., and a note a third of a beat away from a target is not
    the target. An exact comparison would call almost no real note a downbeat.
    """
    if bar is None or beat is None:
        return -1
    for index, target in enumerate(TARGET_BEATS):
        if target > beats_per_bar:
            break
        if abs(float(beat) - target) <= BEAT_EPSILON:
            return 2 - index
    return 0


def roles_for_slot(
    weight: int,
    texture: str,
    harmony_changed: bool = True,
    melody_moves: bool = False,
    has_thumb: bool = False,
    melody_only: bool = False,
) -> List[str]:
    """
    The metric roles a slot of the given weight may take under `texture`.

    This is the whole texture policy in one function, so changing the target-note
    rule is a change here and not a change spread through the selector:

      - an unknown texture is a programming error and raises, rather than silently
        arranging as `uniform`;
      - `uniform` and the `chordN` rows make every slot a target, which is the
        default and the reason `arrange_progression` is unchanged unless a caller
        opts in;
      - a weight below zero means no timing was supplied, so the slot is a target;
      - a strong beat is a target and any other beat is a fill.

    Raises ValueError for an unknown texture, checked before any voicing work so a
    typo cannot cost a caller a full arrangement before it is reported.

    `harmony_changed` and `melody_moves` are the thumb line's extra condition and
    are defaulted to the values that leave every other texture untouched. Under a
    thumb line a slot is a target only when it is metrically strong **and**
    something new happens there: the harmony differs from the previous target's, or
    the melody moves onto it. The first half is the off-beat-change rule - a chord
    arriving on beat 4-and is voiced under the *new* chord by the harmony timeline,
    but is left as a fill, because a passing slot is exactly where the non-chord-tone
    strategies would rewrite the harmony. The second half is decision F: under
    `targets` the second bar of a two-bar chord is a fill, so a player who re-articulates
    the melody on that downbeat gets no chord under it. `TARGET_BEATS` alone cannot say
    either of those things, which is why the extra test lives here rather than in
    `metric_weight`.

    Both arguments are ignored by every other texture, so `uniform` and `targets`
    stay byte-identical.
    """
    if texture not in TEXTURE_ARITY:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    if (
        texture in ("uniform", "chord1", "chord2", "chord3")
        and not (has_thumb and melody_only)
    ) or weight < 0:
        return [ROLE_TARGET]
    if has_thumb:
        if weight > 0 and (harmony_changed or melody_moves):
            return [ROLE_TARGET]
        return [ROLE_FILL]
    if weight > 0:
        return [ROLE_TARGET]
    return [ROLE_FILL]
