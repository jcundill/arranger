"""Which finger holds which fret, for one voicing.

Stage 1 of [docs/fingering.md](../docs/fingering.md) §5: the assignment, the barres it
implies, and the movement between two of them. It is built first because the questions
that remain about fingering are empirical (that document's §2.4 and §4.3) and can only be
answered by code that exists.

**Exactly one engine call reaches this module, and it is §4.3's left-hand half.**
`can_fret` is the four-frets-for-four-fingers check, and `bass._place_bass` is its caller:
on a `bass_only` step the thumb is merged into a shape the hand is still *holding*, so the
fret it adds joins frets that are not this step's own. Nothing else in the engine reads
this module - `voicing_cost` does not, `decisions` does not, and every renderer is
untouched. §5 step 3, whether a per-finger criterion earns a place in the cost tuple, is
still open, and §4.2 is why that decision is not taken here.

What is encoded is §2.1 and §2.2 of that document, in its order:

- **One string, one note, one finger**, and **one finger, one fret** - so a shape with `k`
  distinct fretted positions needs `k` distinct fingers. Every grip this library generates
  sounds at most four strings, so the choice is always `C(4, k)` and never empty.
- **Same fret means one finger** (constraint 3), structural rather than stylistic: the
  notes at one fret are held by one finger laid across the strings. That is what makes this
  an assignment over *frets* and not over strings, and it is why a barre that moves one
  fret counts once in `finger_movement` where the per-string metric counts two.
- **Monotone** (convention 6): the lowest fret takes the lowest finger. Assumed rather than
  proved - and named as an assumption rather than buried, because no shape the engine
  generates needs a crossed fingering, so nothing here can be tested against a real one.
- **Classical position** (convention 7) as the *scoring* rule: of the monotone choices, the
  one closest to "index owns f, middle f+1, ring f+2, pinky f+3" wins. That one rule is
  also what spreads the fingers over a wide span and what puts the index on a low barre
  (convention 8), so it is one criterion rather than the three it is written as - see
  `_assignment_score`.

Deliberately **not** modelled, per §2.3 and §4.5: finger-pair asymmetry (fingers 3 and 4
share a tendon), position-dependent reach (fret spacing narrows up the neck), thumb-over
fretting, and crossed fingerings. None of them is a claim this module makes, so no cost
criterion may be built on one from here. The *right* hand has its own two questions in that
document — §2.5 (which strings `p-i-m-a` pluck, and why the thumb-to-index gap is free while
a gap between the fingers is not) and §4.4 (the measurement, which left the engine alone) —
and both are answered in `grips.py`, not here.

Nothing here decides playability. `GRIP_MAX_SPAN` is still the span bound and
`voicing_cost` is still the selection rule; this module answers the narrower question -
*which* finger - and returns `None` rather than guessing when no assignment exists. The one
shape it can refuse, five distinct frets, is not reachable from a generated grip at all: it
is the *merged* walking-bass step of §4.3, which is why the refusal is a return value the
check reads - `can_fret`, called from `bass._place_bass` - rather than an exception or a
silently crossed fingering.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from .tuning import Voicing

# Left-hand finger numbers, in the order a monotone assignment hands them out: the index
# takes the lowest fret and the pinky the highest. They are the numbers a player reads off
# a chord diagram, so a test can state an expected fingering the way a chart would.
INDEX = 1
MIDDLE = 2
RING = 3
PINKY = 4
# The four fingers, lowest fret first. Everything that enumerates fingers walks this.
FINGERS = (INDEX, MIDDLE, RING, PINKY)
# A sounding string with no finger on it: an open string (fret 0), or a muted one (-1). The
# two are not the same note, but they are the same fact *here* - neither costs a finger.
NO_FINGER = 0


@dataclass
class Fingering:
    """Which finger holds which fret, for one voicing.

    `fingers` mirrors `Voicing.frets` string by string (index 0 = low E ... index 5 = high
    E), so the two can be read side by side, with `NO_FINGER` on every string that is muted
    or sounding open. `frets_by_finger` is the same fact keyed by finger, and it is the one
    `finger_movement` measures on - **by finger, not by string** - which is what makes a
    barre that moves one fret count once.
    """

    fingers: List[int]
    frets_by_finger: Dict[int, int]
    # fret -> the finger laid across it, for every fret two or more strings share. The shape
    # `x-x-6-7-6-x` has the single entry {6: INDEX}; a shape sharing two frets has two. The
    # key is the fret, so convention 8's "the index's job" is readable as
    # `barre_finger == INDEX` without re-deriving where the barre is.
    barres: Dict[int, int]

    @property
    def finger_count(self) -> int:
        """How many left-hand fingers this shape uses, 0 to 4."""
        return len(self.frets_by_finger)

    @property
    def barre_fret(self) -> Optional[int]:
        """The lowest fret two or more strings share, or None when nothing is barred.

        When a shape shares two frets both are recorded, and this reports the lower: it is
        the one that blocks reach below it (constraint 4), so it is the one that decides
        which fingers the others lie above.
        """
        return min(self.barres) if self.barres else None

    @property
    def barre_finger(self) -> int:
        """The finger holding `barre_fret`, or `NO_FINGER` when nothing is barred."""
        fret = self.barre_fret
        return NO_FINGER if fret is None else self.barres[fret]

    def fret_of(self, finger: int) -> Optional[int]:
        """The fret `finger` holds, or None when that finger is idle in this shape."""
        return self.frets_by_finger.get(finger)


@dataclass
class FingerMovement:
    """How far the left hand's fingers travel between two shapes.

    Two numbers rather than one because they describe different changes and can disagree
    about the same one. A shape where all four fingers shift one fret totals 4 and has a
    `largest` of 1; a shape where two stay planted and the third leaps three frets totals 3
    with a `largest` of 3. The sum says the second moved less; `largest` says it is the one
    finger doing the reaching. `total` is the barre double-count fix of
    [docs/fingering.md](../docs/fingering.md) §1.1 and `largest` is the anchored leap of
    its §1.2.
    """

    total: int
    largest: int


def _finger_choices(count: int) -> Iterator[Tuple[int, ...]]:
    """Every monotone way to pick `count` of the four fingers, lowest finger first.

    The fingers are already in fret order, so a monotone assignment *is* an increasing
    tuple, and `itertools.combinations` yields those in lexicographic order. That ordering
    is load-bearing: it is what makes the tie-break in `assign_fingers` a plain `min`
    rather than an explicit comparison, because the first choice to reach the best score is
    the lowest-numbered one.
    """
    return combinations(FINGERS, count)


def _assignment_score(offsets: List[int], choice: Tuple[int, ...]) -> int:
    """How far a monotone choice is from one-finger-per-fret; lowest is best.

    `offsets` are the shape's distinct frets measured *up* from its lowest, so a fret four
    above the bottom is a `4`. The classical finger for an offset of `d` is the one numbered
    `d + 1`, so the score is the total miss from that ideal. Zero means the shape fits index
    f, middle f+1, ring f+2, pinky f+3 exactly.

    One rule is enough for the three conventions that read as separate, because the misses
    *are* those conventions: a bunched shape is at zero with adjacent fingers; a four-fret
    reach is pulled towards the pinky (offset 4 against the middle costs 3, against the
    pinky 1); and the lowest fret takes the index whenever it can, since any other finger
    there costs at least 1 - which is convention 8's index barre falling out of the score
    rather than being asserted after it.
    """
    return sum(abs(offset - (finger - INDEX)) for offset, finger in zip(offsets, choice))


def fingers_needed(frets: Iterable[int]) -> int:
    """How many left-hand fingers a fret vector asks for: its distinct frets at 1 or above.

    Frets are grouped exactly, which is constraint 3 of [docs/fingering.md](../docs/fingering.md)
    §2.1, and fret 0 is an open string that costs no finger - the same two rules
    `assign_fingers` applies when it builds `frets_by_finger`. Stated over a bare vector
    rather than a `Voicing` because the caller that needs it has two shapes merged into one
    hand and no single `Voicing` to point at: see `can_fret`.
    """
    return len({fret for fret in frets if fret >= 1})


def can_fret(frets: Iterable[int]) -> bool:
    """False when a fret vector needs more frets than the left hand has fingers.

    This is §4.3's refusal asked *before* the assignment rather than after it: one finger
    holds one fret and no finger holds two, so five distinct frets is not a hard shape but
    an impossible one, and no monotonising score can rescue it.

    `bass._place_bass` is the caller, and it is the only one. Under a `bass_only` step the
    thumb is merged into the shape the hand is still **holding**, so its fret joins frets
    that are not this step's own - which is the one way a fifth can appear in an engine
    whose every generated grip sounds at most four strings.
    """
    return fingers_needed(frets) <= len(FINGERS)


def assign_fingers(voicing: Voicing) -> Optional[Fingering]:
    """Which finger holds which fret for `voicing`, or None when four cannot do it.

    The whole algorithm is §3 steps 1-4 of [docs/fingering.md](../docs/fingering.md), and it
    is an exact enumeration rather than a search because the problem is tiny: a shape sounds
    at most four strings, so it has at most four distinct frets and at most `C(4, k)`
    monotone choices - 1, 4, 6 or 4 of them.

    Frets are grouped exactly, which is constraint 3: two notes at one fret are one finger.
    Fret 0 is an open string and takes no finger, and it does not make the *lowest* fret of
    the shape either - a fretted note a third above an open string is still the bottom of
    the hand.

    `None` means the shape needs **five distinct frets**, which four fingers cannot hold:
    one finger holds one fret and no finger holds two. In this engine's vocabulary that is
    not a generated grip - every family sounds at most four strings - it is the *merged* step
    of §4.3, where the walking-bass note is added under a four-note shape. That is the hook
    the §4.3 measurement reads (`assign_fingers(step.voicing) is None`), and the failure is a
    return value rather than an exception or a crossed fingering, which is convention 6's
    "make the failure mode visible".
    """
    frets = sorted({fret for fret in voicing.frets if fret >= 1})
    if not can_fret(frets):
        return None

    lowest = frets[0] if frets else 0
    offsets = [fret - lowest for fret in frets]
    choice = min(
        _finger_choices(len(frets)), key=lambda pick: _assignment_score(offsets, pick)
    )

    finger_of_fret = dict(zip(frets, choice))
    return Fingering(
        fingers=[NO_FINGER if fret < 1 else finger_of_fret[fret] for fret in voicing.frets],
        frets_by_finger={finger: fret for fret, finger in finger_of_fret.items()},
        barres={
            fret: finger
            for fret, finger in finger_of_fret.items()
            if sum(1 for other in voicing.frets if other == fret) > 1
        },
    )


def finger_movement(previous: Optional[Fingering], current: Fingering) -> FingerMovement:
    """How far the hand's fingers move from `previous` to `current`.

    Keyed on the **finger**, not on the string, which is the whole point. The shape
    `x-x-6-7-6-x` holds fret 6 on the D and B strings with one finger, so moving it to
    `x-x-7-8-7-x` is two fingers moving one fret each and totals 2; summing fret deltas per
    string (`calculate_voice_leading_distance`) counts three, because it has no way to know
    the two notes at fret 6 are one finger. That is the barre double-count of
    [docs/fingering.md](../docs/fingering.md) §1.1, fixed here rather than measured away.

    A finger idle in *either* shape contributes nothing to either number: a lift is not
    travel, and measuring from fret 0 would make a two-finger shape's movement depend on how
    many fingers it did not use.

    **Known under-report, and it is the design's rather than a bug.** A finger handed a fret
    another finger held reads as one finger stopping and another starting - two zeroes -
    rather than as a hand shift, because the two movements share no finger to be measured on.
    So a substitution can total 0 while the hand visibly moved. §5 step 2 is where that is
    weighed against real steps; this docstring is where it is admitted until it is.
    """
    if previous is None:
        return FingerMovement(total=0, largest=0)

    total = 0
    largest = 0
    for finger in FINGERS:
        before = previous.fret_of(finger)
        after = current.fret_of(finger)
        if before is None or after is None:
            continue
        travel = abs(after - before)
        total += travel
        largest = max(largest, travel)
    return FingerMovement(total=total, largest=largest)
