"""The metre's third fact: which denominator units the player feels as one beat.

`beats_per_bar` says how many denominator units a bar has, `beat_type` says how long
one lasts, and `grouping` says how they are felt: 12/8 is four groups of three
eighths, while 5/4 named `3+2` is two groups. `auto` derives the compound reading -
threes for an eighth-or-finer denominator whose bar divides by three - and leaves a
simple metre one group per beat, so it is inert on the metres this library shipped
with.

No sibling imports: this module is metre arithmetic and pure predicates.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple, Union

GROUPING_AUTO = "auto"
GROUPING_SEPARATOR = "+"

#: A parsed grouping: the sentinel, or one group length per felt beat.
ParsedGrouping = Union[str, Tuple[int, ...]]


def format_grouping(grouping: Sequence[int]) -> str:
    """A grouping in its one written spelling, e.g. ``3+3+3+3``."""
    return GROUPING_SEPARATOR.join(str(length) for length in grouping)


def parse_grouping(argument: str) -> ParsedGrouping:
    """A `grouping` argument as the `auto` sentinel or a tuple of group lengths.

    The vocabulary is an **algebra rather than a list** - any positive integers that
    sum to the bar are a grouping - so no `GROUPING_STYLES` can enumerate it.
    Validation happens in `grouping_allowed`, where the bar length is known; this
    function answers only whether the spelling is well formed.

    Raises `ValueError` on an empty row, a non-integer row or a length below one,
    because a spelling nobody recognises is a question.
    """
    text = argument.strip().lower()
    if text == GROUPING_AUTO:
        return GROUPING_AUTO
    if not text:
        raise ValueError(
            f"grouping is empty; expected {GROUPING_AUTO!r} or a grouping such as "
            f"'3+3+3+3'"
        )
    lengths = []
    for row in text.split(GROUPING_SEPARATOR):
        row = row.strip()
        try:
            length = int(row)
        except ValueError:
            raise ValueError(
                f"Unknown grouping {argument!r}; expected {GROUPING_AUTO!r} or "
                f"positive lengths joined by {GROUPING_SEPARATOR!r}, such as '3+3+3+3'"
            ) from None
        if length < 1:
            raise ValueError(
                f"Unknown grouping {argument!r}; every group length must be at "
                f"least 1, got {length}"
            )
        lengths.append(length)
    return tuple(lengths)


def default_grouping(beats_per_bar: int, beat_type: int) -> Tuple[int, ...]:
    """The grouping `auto` derives from a metre.

    A compound metre is counted in **threes**: an eighth-or-finer denominator whose
    bar divides by three is felt as a group of three units per beat, which is 6/8,
    9/8 and 12/8 read as two, three and four beats. Every other metre is one group
    per denominator unit, which is what the engine did before this module existed.

    The rule is a convention, not a fact in the file: MusicXML states the count and
    the denominator and nothing about beaming, so 5/8 or 7/8 is **not guessed** - a
    caller states `3+2` or `2+2+3` when that is what the tune is.
    """
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if beat_type >= 8 and beats_per_bar % 3 == 0:
        return (3,) * (beats_per_bar // 3)
    return (1,) * beats_per_bar


def grouping_allowed(
    grouping: Sequence[int], beats_per_bar: int
) -> Tuple[bool, str]:
    """Whether these group lengths describe this bar, and why not.

    Derived from one fact - the groups are a partition of the bar - rather than
    listed. A grouping that spans fewer or more beats than the bar has is refused
    rather than padded, clamped or wrapped: every one of those would silently place
    the felt beats somewhere nobody asked for.
    """
    if not grouping:
        return False, "a grouping must name at least one group"
    if any(length < 1 for length in grouping):
        return False, (
            f"grouping={format_grouping(grouping)} has a group shorter than one beat"
        )
    total = sum(grouping)
    if total != beats_per_bar:
        return False, (
            f"grouping={format_grouping(grouping)} spans {total} beats, but the bar "
            f"has {beats_per_bar}"
        )
    return True, ""


def resolve_grouping(
    grouping: ParsedGrouping, beats_per_bar: int, beat_type: int
) -> Tuple[int, ...]:
    """The grouping to use: `auto` derived, then validated against the bar."""
    if grouping == GROUPING_AUTO:
        resolved = default_grouping(beats_per_bar, beat_type)
    else:
        if isinstance(grouping, str):
            raise ValueError(
                f"resolve_grouping takes a parsed grouping; use parse_grouping first "
                f"(got {grouping!r})"
            )
        resolved = tuple(grouping)
    allowed, reason = grouping_allowed(resolved, beats_per_bar)
    if not allowed:
        raise ValueError(reason)
    return resolved


def group_starts(
    beats_per_bar: int, grouping: Optional[Sequence[int]] = None
) -> Tuple[float, ...]:
    """The first beat of every group, in beat numbers starting at 1.

    `None` means "one group per denominator unit", which is the reading every caller
    had before `grouping` existed. A supplied grouping is validated against the bar,
    so a tuple that does not partition it is an error rather than a truncated list.
    """
    lengths = tuple(grouping) if grouping else (1,) * beats_per_bar
    allowed, reason = grouping_allowed(lengths, beats_per_bar)
    if not allowed:
        raise ValueError(reason)
    starts = []
    start = 1.0
    for length in lengths:
        starts.append(start)
        start += length
    return tuple(starts)


def group_offbeat(length: int) -> float:
    """How far into a group its offbeat falls, in beats.

    A one-beat group's offbeat is half a beat - the ``and`` this library has always
    placed. A longer group's offbeat is its **last** unit, so a group of three
    eighths answers on the third eighth rather than halfway between the second and
    the third. That is the pulse's subdivision in a compound metre, and it reduces
    to the simple rule at a group of one.
    """
    if length < 1:
        raise ValueError(f"a group length must be at least 1, got {length!r}")
    return 0.5 if length == 1 else float(length - 1)
