"""The comp line: top-voice movement for the comping route.

Owns the home band and the rules that move the comp's top voice between slots:
the opening, the walk (direction + no-retrace), the approach (a pivot on a tone
both chords share) and the fill's interpolation. It reads pitch lists and chord
tones only - the route that gathers them is `routes.comping_step` - and it holds
no vocabulary a caller chooses from, because there is nothing to choose: the line
is *how* the chord part plays the notes it already states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .grip_place import frets_in_band
from .step_types import (
    TOP_APPROACH_FROM_ABOVE,
    TOP_APPROACH_FROM_BELOW,
    TOP_FILL_DOWN,
    TOP_FILL_UP,
    TOP_OPENING,
    TOP_WALK_DOWN,
    TOP_WALK_UP,
    Voicing,
)
from .tuning import GuitarFretboard


@dataclass(frozen=True)
class LineState:
    """Where the line is when a slot arrives.

    `previous_top` is the top voice of the last sounding step - `None` at the head of
    an arrangement, which is what makes a slot an *opening*. `history` is the last two
    of those tops, the window `walk_step` reads for no-retrace, and `direction` is the
    walk's carried direction. Derived from the arrangement by `read_state` rather than
    stored beside it, so there is one source for where the line stands.
    """

    previous_top: Optional[int] = None
    history: Tuple[int, ...] = ()
    direction: int = 1


@dataclass(frozen=True)
class LineShape:
    """One shape, as the line reads it: its top voice, its register, and its band.

    **`in_band` is tested on every fret**, not on the average, and
    `grip_place.frets_in_band` is that one test - the banded palette's collapse reads
    the same predicate, so the shape it keeps per top tone is one the line can walk.
    """

    tone: int
    register: float
    in_band: bool

    @classmethod
    def of(cls, voicing: Voicing, band: Tuple[int, int]) -> "LineShape":
        return cls(
            tone=max(voicing.midi_notes()),
            register=voicing.avg_fret,
            in_band=frets_in_band(voicing.active_frets(), band),
        )


@dataclass(frozen=True)
class FillTarget:
    """One fill position's place between two registers.

    `previous` is the register of the last sounding step - the hand position the fill
    opens at - and `target` the register it resolves into. `index` and `count` put this
    position on the path `interpolate` draws, so a two-position fill moves at its last
    position only and a four-position one moves in thirds.
    """

    previous: float
    target: float
    index: int
    count: int


def home_band(fret_min: int, fret_max: int) -> Tuple[int, int]:
    """The register the comp lives in: ``fret_min + 1``, eight frets, clamped
    to the window.

    Eight is a **value rather than a hand-span**, and the measurement is the reason:
    inside five frets a seventh chord reaches only two or three tones and the line
    bounces between them (`docs/history/comp-line.md` §"The band width is the one value worth
    re-tuning").
    """
    lo = fret_min + 1
    hi = min(fret_min + 8, fret_max)
    if hi < lo:
        hi = lo
    return (lo, hi)


def band_middle(band: Tuple[int, int]) -> float:
    """The register the comp opens in: the band's midpoint."""
    lo, hi = band
    return (lo + hi) / 2.0


def nearest_tone(target: int, candidates: Sequence[int]) -> Optional[int]:
    """The candidate nearest `target`, the lower one on a tie."""
    if not candidates:
        return None
    return min(candidates, key=lambda tone: (abs(tone - target), tone))


def _nearest_in_direction(
    pool: Sequence[int], current: int, direction: int
) -> Optional[int]:
    """The nearest pool tone strictly in `direction` from `current`."""
    if direction > 0:
        above = [tone for tone in pool if tone > current]
        if above:
            return min(above, key=lambda tone: (tone - current, tone))
        return None
    below = [tone for tone in pool if tone < current]
    if below:
        return min(below, key=lambda tone: (current - tone, tone))
    return None


def walk_step(
    current: int,
    direction: int,
    candidates: Sequence[int],
    history: Sequence[int],
) -> Tuple[Optional[int], int]:
    """One step of the walk, and the direction it leaves behind.

    **Both clauses are load-bearing and both were measured.** The nearest different
    tone alone oscillates (`67,64,67,64`); a carried direction alone bounces at the
    band's edge (`E4,F4,E4,F4`); together they produce a walk, and the reversal at the
    edge is what keeps the line inside the band instead of leaving it.
    """
    forbidden = set(history[-2:]) if history else set()
    pool = [tone for tone in candidates if tone != current and tone not in forbidden]
    chosen = _nearest_in_direction(pool, current, direction)
    new_direction = direction
    if chosen is None:
        new_direction = -direction
        chosen = _nearest_in_direction(pool, current, new_direction)
    if chosen is None and pool:
        chosen = min(pool, key=lambda tone: (abs(tone - current), tone))
    return (chosen, new_direction)


def opening_no_melody(shapes: Sequence[LineShape], band: Tuple[int, int]) -> Optional[int]:
    """The opening: the shape placed nearest the home band's middle.

    The register is the only thing that can choose at the head of an arrangement, so
    the comp opens where the band says it lives rather than where `cost`'s hardcoded
    ``fret 9`` used to put it. Read on the **shape's** `avg_fret` rather than on the
    pitch: a band is a register, and the tones a chord offers inside it are several
    pitches of the same chord - ranking those by pitch would open every comp on the
    lowest of them, which is a note rather than a position.
    """
    if not shapes:
        return None
    middle = band_middle(band)
    best = min(shapes, key=lambda shape: (abs(shape.register - middle), shape.tone))
    return best.tone



def _nearest_pitch(pitch_class: int, around: int) -> int:
    """`pitch_class` as the pitch nearest `around` (within an octave, below on a tie)."""
    base = around - (around - pitch_class) % 12
    return min((base, base + 12), key=lambda pitch: (abs(pitch - around), pitch))


def landing_tone(next_tones: Sequence[int], previous_top: int) -> Optional[int]:
    """The next chord's tone the line resolves into, nearest the previous top.

    Read on **pitch classes**: the caller has the chord's tone set, and the octave is
    the palette's business rather than the harmony's. `_nearest_pitch` places each
    class as close to the previous top as it can be placed, so the answer is a pitch
    the hand can reach rather than a number below the neck.
    """
    if not next_tones:
        return None
    return min(
        (_nearest_pitch(pc, previous_top) for pc in next_tones),
        key=lambda tone: (abs(tone - previous_top), tone),
    )


def shared_tones(candidates: Sequence[int], next_tones: Sequence[int]) -> List[int]:
    """The candidates whose pitch class the next chord also states."""
    next_pcs = {pc % 12 for pc in next_tones}
    return [tone for tone in candidates if tone % 12 in next_pcs]


def approach_tone(
    previous_top: int,
    candidates: Sequence[int],
    next_tones: Sequence[int],
) -> Optional[int]:
    """The approach: a tone both chords state, nearest the previous top.

    **A common tone is the pivot a change sounds prepared over**, and it is also why
    the approach moves without a rule of its own: when the nearest shared tone *is* the
    previous top, the next nearest is taken, because a repeat is a hold rather than an
    approach. With nothing in common the line falls back to the current chord's tone
    nearest `landing_tone`, the ordinary way to lead into a chord that shares nothing
    with its predecessor.
    """
    pool = [tone for tone in candidates if tone != previous_top]
    if not pool:
        pool = list(candidates)
    shared = shared_tones(pool, next_tones)
    if shared:
        return nearest_tone(previous_top, shared)
    landing = landing_tone(next_tones, previous_top)
    if landing is None:
        return nearest_tone(previous_top, pool)
    return nearest_tone(landing, pool)


def interpolate(previous_register: float, target: float, n: int) -> List[float]:
    """Fill interpolation: ``i == 0`` is the previous register, ``i == n-1``
    the target; intermediates are evenly spaced.

    ``i / (n - 1)`` rather than ``(i + 1) / n``: the fill's *first* note opens where
    the hand already is, which is the opening rule read on the other axis. The other
    spelling leaves the previous register on the fill's first note, and it was
    measured out.
    """
    if n <= 1:
        return [target]
    step = (target - previous_register) / (n - 1)
    return [previous_register + step * index for index in range(n)]


def fill_run(
    progression: Sequence[Tuple[Optional[str], str]], index: int
) -> Tuple[int, int]:
    """Where a slot falls in the run of melody-less positions that contains it.

    Returns ``(index, count)``: the slot's 0-based place in the run and the run's
    length. The run is the maximal span of **consecutive entries with no melody
    note** - the positions a fill states the chord at - so a two-position fill moves
    once, at its last note, and a four-position one moves in three steps. Read from the
    progression because that is where those positions are: the importer emits one entry
    per position and writes ``None`` as the melody of any the tune is silent at.
    """
    length = len(progression)
    if index < 0 or index >= length:
        return (0, 1)
    start = index
    while start > 0 and progression[start - 1][0] is None:
        start -= 1
    end = index
    while end + 1 < length and progression[end + 1][0] is None:
        end += 1
    return (index - start, end - start + 1)


def next_melody(
    progression: Sequence[Tuple[Optional[str], str]], index: int
) -> Optional[str]:
    """The first written melody note after `index`, or None when the tune has ended.

    Read forward over **written notes only**, so a position the tune sustains through
    or is silent at does not name itself: the fill is joining the note the tune
    returns on, not the rest it is filling.
    """
    for offset in range(index + 1, len(progression)):
        note, _name = progression[offset]
        if note is not None:
            return note
    return None


def read_state(tops: Sequence[int]) -> LineState:
    """The line's state from the tops of **this chord's** sounding steps, oldest first.

    The caller decides the window: a new chord is a new walk, so its first position is
    handed the incoming top alone and the direction starts upward again. Both halves
    are measured. Within a chord the carried sign is what makes bar 3 fall
    (`67,60,59`) instead of climbing out of `59`, and the reset at a change is what
    makes bar 4 open upward from `60` rather than reversing into `57`; the window is
    what keeps the approach's own top - `64` after bar 2 - out of the next chord's
    first step, which is the only way the walk reaches `67` rather than stopping at
    `60` (`docs/history/comp-line.md` §"The four-bar example").

    A window that spans a chord change fails both bars: the approach's top is then
    still forbidden when the new chord starts, and the walk takes the second-nearest
    tone of the *old* direction.
    """
    direction = 1
    if len(tops) >= 2:
        direction = 1 if tops[-1] >= tops[-2] else -1
    return LineState(
        previous_top=tops[-1] if tops else None,
        history=tuple(tops[-2:]),
        direction=direction,
    )


def tune_register(midi: int, soprano_strings: Sequence[int]) -> Optional[float]:
    """The fret the tune sits at, on the first soprano string that can carry it.

    A fill aims at **where the tune is**, which is a physical fact about the neck
    rather than the pitch the horn names: the two are the same number only in the same
    octave. ``None`` when no soprano string can reach the note, which is the caller's
    cue to hold the register it was handed rather than guess one.
    """
    for string in soprano_strings:
        fret = midi - GuitarFretboard.fret_to_midi(string, 0)
        # 18 is the end of the neck - the same reach `GuitarFretboard.note_to_fret`
        # allows a melody that has to be played there.
        if 0 <= fret <= 18:
            return float(fret)
    return None


def chosen_top(
    state: LineState,
    shapes: Sequence[LineShape],
    band: Tuple[int, int],
    *,
    next_tones: Optional[Sequence[int]] = None,
    fill: Optional[FillTarget] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """Which tone goes on top, and the role the tab line reports for it.

    `shapes` is every shape the palette still offers after the requested bass note has
    had its say. **The band is applied here, by the line**, rather than by the generator
    or the ranking: the tones a shape wholly inside it states are the comp's material,
    which is what makes the line win inside its register instead of losing to a shape
    that merely costs less. A tone reachable only outside the band stays in the pool as
    the fallback, so no chord loses a tone.

    A **fill** is the one case that reads every shape, band or not: it bridges toward
    the tune, so its target is an interpolated register rather than a tone.
    """
    if not shapes:
        return (None, TOP_OPENING)
    if fill is not None:
        return _fill_top(shapes, fill)
    pool = [shape for shape in shapes if shape.in_band] or list(shapes)
    tones = [shape.tone for shape in pool]
    if state.previous_top is None:
        return (opening_no_melody(pool, band), TOP_OPENING)
    previous_top = state.previous_top
    if next_tones is not None:
        return _approach_top(previous_top, state, tones, next_tones)
    return _walk_top(previous_top, state.direction, state.history, tones)


def _approach_top(
    previous_top: int,
    state: LineState,
    tones: Sequence[int],
    next_tones: Sequence[int],
) -> Tuple[Optional[int], Optional[str]]:
    """The approach: the shared tone the line pivots onto, and how it gets there.

    When the only tone the line could pick is the one already on top there is no move,
    so no role is reported: claiming a walk or an approach over a static top would be
    false, and the narrowing (the tone stays) is explained elsewhere.
    """
    tone = approach_tone(previous_top, tones, next_tones)
    if tone is None or tone == previous_top:
        return (tone, None)
    return (tone, _approach_role(tone, state, next_tones))


def _walk_top(
    previous_top: int,
    direction: int,
    history: Tuple[int, ...],
    tones: Sequence[int],
) -> Tuple[Optional[int], Optional[str]]:
    """One step of the walk, and the direction it leaves behind.

    When the walk is exhausted or can only restate the previous top there is no move,
    so no role is reported for the same reason as `_approach_top`.
    """
    tone, new_direction = walk_step(previous_top, direction, tones, history)
    if tone is None or tone == previous_top:
        return (tone, None)
    return (tone, TOP_WALK_UP if new_direction > 0 else TOP_WALK_DOWN)


def _approach_role(
    tone: Optional[int], state: LineState, next_tones: Sequence[int]
) -> str:
    """Whether the approach arrives from above or below the tone it resolves into."""
    if tone is None or state.previous_top is None:
        return TOP_APPROACH_FROM_BELOW
    landing = landing_tone(next_tones, state.previous_top)
    if landing is not None and tone != landing:
        return TOP_APPROACH_FROM_BELOW if tone < landing else TOP_APPROACH_FROM_ABOVE
    # The approach *is* the tone it leads to, so the move that got there says which
    # side it came from - the same reading `tone < landing` gives otherwise.
    return (
        TOP_APPROACH_FROM_ABOVE
        if tone < state.previous_top
        else TOP_APPROACH_FROM_BELOW
    )


def _fill_top(
    shapes: Sequence[LineShape], fill: FillTarget
) -> Tuple[Optional[int], str]:
    """The shape a fill position takes: the one nearest its place on the path.

    **The lowest top wins a tie**, because the register is the fact the fill aims at
    and a lower top keeps the chord part under the tune it is joining - the same reason
    `grip_tables.COMPING_EXCLUDED_STRINGS` keeps the high E off this palette.
    """
    path = interpolate(fill.previous, fill.target, fill.count)
    target = path[fill.index] if 0 <= fill.index < len(path) else path[-1]
    best = min(shapes, key=lambda shape: (abs(shape.register - target), shape.tone))
    return (
        best.tone,
        TOP_FILL_UP if best.register >= fill.previous else TOP_FILL_DOWN,
    )
