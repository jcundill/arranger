"""Grip families: the tables, the builders, and the candidate generators.

Everything that turns a chord quality and a melody note into a *set of candidate
voicings* is here, and nothing here chooses between them. That split is what lets
this module be read on its own: `cost` holds the selection rule, and no generator
below knows what came before it, what the neck window is, or what the answer
turned out to be.

**The generators are free functions, and `VoiceLeadingEngine` keeps one-line
`@classmethod` delegates.** Roughly forty call sites in the tests and the front ends
spell them `VoiceLeadingEngine.get_drop2_voicings(...)`, and the delegate keeps those
spellings working. It leaves one implementation, so there is nothing to keep in step.

The four non-contiguous string sets - 6-4-3, both 5-3-2s and 6-4-3-2 - are
*searched* rather than stacked, because their voices are not in descending pitch
order down the strings: the A string is tuned five semitones above the D. See
`_place_shell` and `_place_drop2_6432`.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from musthe import Note

from .chords import ChordParser
from .tuning import (
    HIGH_FRET_LIMIT,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    STANDARD_TUNING,
    GuitarFretboard,
    Voicing,
    _note_name,
)

# Grip families, in the order they are generated in - which is *also* the order an exact
# tie is broken in: `cost._best_voicing` is a stable `min` and no criterion in
# `cost.voicing_cost` names a family, so of two candidates at the winning cost the one
# generated first wins. This tuple is the default `grips=`, and a caller's own order
# replaces it, which is what makes `--grips`' "most preferred first" a promise rather than
# a description. One tuple, one job, and a family's position here is load-bearing.
#
# It is **not** what decides how many notes a step sounds. That is criterion 2,
# `missing = 4 - len(active)`, so a shell never beats a four-note shape by sitting early
# here; a family's place only orders shapes of the same arity against each other.
#
# `drop2` is first so the idiomatic reading of the name is the default one.
#
# `drop2_6432` is the 6-4-3-2 block (low E, D, G, B), listed after the contiguous blocks
# because it is the *alternative* rather than the default reading of "drop-2":
# `grips=("drop2",)` means the contiguous four strings only, which is the idiom that
# reproduces the library's original output exactly. It is a separate family, not a third
# string set for `drop2`, precisely so that idiom survives.
#
# `closed` (close position) is **second**, and it holds that place on the tie-break
# rather than on reachability: it is the tightest four-note shape there is, so where a
# melody *can* fret it at all it is usually the shape the hand wants most - and it beats
# every other four-note family it ties with. It is widely unreachable, because a close
# stack under a melody is a seventh or more of pitch laid on four strings only four or
# five semitones apart in tuning, but an unreachable family is simply never generated,
# and criterion 2 covers any note-count gap between two that are. `docs/engine.md`
# §"Known limitations" holds the reachability measurement.
#
# `drop3` and `drop24` are here because a melody that is *not* a chord tone leaves drop-2
# with no template and no shell, so its quality-only fallback offers shapes carrying notes
# the chord does not contain. Both derive from the close stack under the melody, which
# keeps every *other* voice a chord tone, so offering them is what puts a correct voicing
# in the candidate set for the selector to find - see `cost.voicing_cost`, whose first
# criterion counts wrong notes rather than flagging them.
GRIP_PREFERENCE: Tuple[str, ...] = (
    "drop2", "closed", "drop3", "drop24", "drop2_6432", "shell", "duo",
)


def parse_grips(argument: str) -> Tuple[str, ...]:
    """The grip families named in `argument`, in the order they are named.

    The spelling: comma-separated family names, matched case-insensitively, with
    whitespace around the commas ignored, so `"closed,shell"` and `" Closed , SHELL "`
    are one request. **The order is part of the request**, not formatting: this is a
    preference list and an exact tie is broken by generation order, so
    `"shell,drop2"` and `"drop2,shell"` are two arrangements. A repeat is dropped
    keeping its first occurrence, and nothing is re-sorted - deliberately *not* what
    `textures.parse_voices` does to `VOICE_NAMES`, whose order is not a preference.

    Raises `ValueError` on an empty request, or on a name outside `GRIP_PREFERENCE`,
    naming the palette. The rule is the library's: a spelling nobody recognises is a
    question, and answering it by dropping a family would hand back an arrangement
    missing something nobody asked it to drop.
    """
    text = argument.strip().lower()
    if not text:
        raise ValueError(f"grips is empty; expected any of {GRIP_PREFERENCE}")
    chosen: List[str] = []
    for part in text.split(","):
        name = part.strip().lower()
        if name not in GRIP_PREFERENCE:
            raise ValueError(f"Unknown grip {name!r}; expected any of {GRIP_PREFERENCE}")
        if name not in chosen:
            chosen.append(name)
    return tuple(chosen)

# The maximum distance, in frets, from the lowest to the highest active fret. Five for
# every four-note shape and every three-note shell; a duo and an interval are only ever
# two fingers, so they are held to a tighter four.
#
# This is a *distance*, `max(frets) - min(frets)`, not a count of frets touched: a shape
# on frets 6 and 10 spans four, because the hand reaches four frets from index to pinky.
# Counting the touched frets inclusively would describe something the hand does not do.
# See `docs/engine.md` §"Span outranks neck position".
GRIP_MAX_SPAN: Dict[str, int] = {
    "drop2": 5,
    "drop2_6432": 5,
    "drop3": 5,
    "drop24": 5,
    "closed": 5,
    "shell": 5,
    "duo": 4,
    # Two fingers, like a duo, so it is held to the same tighter four. An interval
    # is a texture, not a harmony, so it is never wider than a hand needs to be.
    "interval": 4,
}


# Every string set a grip may occupy, as (active string indices, soprano string
# index), ordered by preference. Index 0 = low E ... index 5 = high E, so the
# conventional string number is 6 - index.
#
# (0, 2, 3) is the 6-4-3 shell: low E, D and G, deliberately skipping the A string.
# It is the only non-contiguous set here, and it is the reason a G-string soprano can
# carry a full three-note shell at all - without it only the D string lies below the
# G string, which would cap a G-string melody at two voices.
GRIP_STRING_SETS: Dict[str, Tuple[Tuple[Tuple[int, ...], int], ...]] = {
    # The two traditional four-string blocks, each with a **bass-skipping** variant.
    # There is deliberately no four-note block for a G-string soprano: 6-5-4-3 with the
    # melody on top does not sound good, so a low melody is harmonised with a
    # three-note shell instead - see the note below.
    #   (2, 3, 4, 5) -> strings 4-3-2-1, melody on the high E
    #   (1, 2, 3, 4) -> strings 5-4-3-2, melody on the B string
    #
    # **A four-note shape does not have to occupy four neighbouring strings.** The bass
    # voice may skip to a *lower* string, and this is a general rule rather than a
    # special case for one grip - it is what `drop2_6432` already does with the low E,
    # generalised to the whole four-note family.
    #
    # Why it helps, and it is not a matter of taste: the voices of a drop-2 are laid on
    # descending strings, and a string is tuned *higher* than the one below it, so a
    # lower voice needs a *lower* string to reach its pitch on the board. When the bass
    # of the shape is deep, the contiguous block cannot fret it - the D string runs out
    # of frets long before the low E would. Skipping gives the bass a longer string to
    # sit on, and the shape moves down the neck as a unit rather than stretching.
    #
    # The skip is always *downward* for the lowest voice, and never for an inner one.
    # Two of the entries below are the skip; the rest are the plain block, listed first
    # so the idiomatic reading of each name wins a tie:
    #   (2, 3, 4, 5)  strings 4-3-2-1   the traditional block
    #   (1, 3, 4, 5)  strings 5-4-3-2   bass on the A instead of the D
    #   (1, 2, 3, 4)  strings 5-4-3-2   the lower traditional block
    #   (0, 2, 3, 4)  strings 6-4-3-2   bass on the low E instead of the A
    "drop2": (
        ((2, 3, 4, 5), 5), ((1, 3, 4, 5), 5),
        ((1, 2, 3, 4), 4), ((0, 2, 3, 4), 4),
    ),
    # Drop-2 & 4: the second and fourth voices of a close stack each lowered an octave.
    #
    # The widest four-note shape there is - twenty semitones from the melody to the bass
    # for a Cmaj7 - and it is *unplayable on four neighbouring strings*: the low voice
    # lands more than an octave below where a contiguous block can put it. What makes it
    # playable is the same bass-skipping rule as everywhere else: the bass voice takes a
    # lower string. The plain block is listed first, as for drop-2, so the idiomatic
    # reading of the name wins a tie.
    #
    # No set here skips an *inner* string: the digit that takes a string above an
    # unplucked one has to reach over it, and that is the right hand's cost rather than
    # the left's. `finger_skip_count` states the rule, `docs/engine.md` records the price
    # of the four sets removed for it, and `tests/test_grips.py` holds every reachable set
    # to it.
    #
    # Stored as **string indices**, high to low, like every other entry - so the
    # conventional numbers read 1-2-4-5 as (5, 4, 2, 1). Written the other way round these
    # would name string index 6, which does not exist.
    "drop24": (
        ((5, 4, 3, 2), 5), ((5, 4, 3, 1), 5),
        ((4, 3, 2, 1), 4), ((4, 3, 2, 0), 4),
    ),
    # 6-4-3-2: low E, D, G and B with the melody on the B string, skipping the A
    # string so the low E can carry the bass. It is the one default four-note set that
    # reaches the low E, which is where a root actually lives, so it is what turns a
    # root bass from a consequence of the string set into a decision. Note it is *not*
    # the bottom-four block excluded by `_BOTTOM_FOUR`: it swaps the A string out for
    # the B, and its soprano is the B rather than the G.
    "drop2_6432": (((0, 2, 3, 4), 4),),
    # Drop-3 and close position are given the same bass-skipping sets as drop-2, because
    # the rule is about the *shape*, not the family: a bass that reaches below the block
    # can still be fretted on a longer string, and where that rescues a shape the span
    # limit would otherwise refuse it.
    "drop3": (
        ((2, 3, 4, 5), 5), ((1, 3, 4, 5), 5),
        ((1, 2, 3, 4), 4), ((0, 2, 3, 4), 4),
    ),
    "closed": (
        ((2, 3, 4, 5), 5), ((1, 3, 4, 5), 5),
        ((1, 2, 3, 4), 4), ((0, 2, 3, 4), 4),
    ),
    # Three-note shells: 1-2-3, 2-3-4, 5-4-3, the 6-4-3 that skips the A string, the
    # 5-3-2 that skips the D string, and the 5-3-2 that skips the B. A G-string melody has
    # two shapes available, 5-4-3 and 6-4-3, and the selector chooses between them like
    # any other pair.
    #
    # 5-3-2 (A, G, B, melody on the B string) is the only shell whose A-string note
    # sounds *below* its G-string neighbour without the low E: the A is tuned five
    # semitones above the D it skips, and the G is five above that, so the pitches
    # descend while the string numbers ascend. It adds no coverage - it is never the only
    # shape for a melody - but it relocates steps onto a better melodic position by letting
    # the melody hold its place and change strings, which is the whole point of that; the
    # measurement is in `docs/engine.md` §"Grips, and the position-aware selector". It needs
    # the search in `_place_shell`, not stacking, for the same reason 6-4-3 does.
    #
    # (5, 3, 2) is the *other* 5-3-2: high E, G and D, skipping the B on the way up
    # rather than the D on the way down. It balances the shell sets by soprano - the high
    # E is the *most* used soprano, because `MELODY_STRING_CHOICES_FULL` puts it first, and
    # this gives it a second shape where the B and the G each have two. It is also the
    # three-layer split a walking-bass shell wants (melody on the high E, guide tones on the
    # G and the D, leaving the 5th and 6th strings to the thumb), so it earns its place
    # twice over. Like the other non-contiguous sets it needs `_place_shell`'s search, not
    # stacking: its D-string note can sound above its G-string note, so the voices are not
    # in descending pitch order down the strings.
    "shell": (
        ((5, 4, 3), 5), ((4, 3, 2), 4), ((1, 2, 3), 3),
        ((0, 2, 3), 3), ((1, 3, 4), 4), ((5, 3, 2), 5),
    ),
    # Duos: 1-2, 2-3 and 3-4, each with the higher note carrying the melody - and **one** pair
    # that skips a string, 3-5, which exists for a single measured reason.
    #
    # A duo's second voice is the chord's guide tone, and the guide tone can land a **2nd**
    # below the melody. A 2nd in two voices is where they fight rather than agree, and the
    # cure is to drop the guide tone an octave, making a 9th. **That cure is unreachable on
    # the adjacent pairs**: a 9th spans 14 semitones and two adjacent strings are tuned 4
    # or 5 apart, so the lower note needs a fret difference of 9 or 10, against
    # GRIP_MAX_SPAN["duo"] of 4.
    #
    # A skipped string has more tuning between its open notes, so the 9th costs a smaller
    # fret difference. Of the pairs that reach it, `(3, 1)` - strings 3-5, the 3rd string
    # under the G - is the narrower and the more idiomatic, so it is the one kept. Adding
    # the equivalent `(5, 2)` would enlarge `supported_string_sets()` by a set that reaches
    # nothing the first does not, which is what the "load-bearing" test below exists to
    # prevent. The measurement, including the two `sus` cases no pair reaches, is in
    # `docs/engine.md` §"Grips, and the position-aware selector".
    #
    # The span cap is NOT widened to suit it. This works because (3,1) is wide in
    # *tuning* (10 semitones between the open strings) and still narrow in *frets* - a
    # comfortable two-finger reach, not a stretch.
    "duo": (
        ((5, 4), 5), ((4, 3), 4), ((3, 2), 3),
        ((3, 1), 3),
    ),
    # Intervals use the three **adjacent** pairs only, and are deliberately *not* the
    # widened duo set. A 3rd or a 6th has tuning to spare, so the extra reach of a skipped
    # string buys it nothing - and an interval is a fill texture that never has to voice a
    # 9th, which is the whole reason the duo needed the wider pair. What differs between
    # the families is the rule that builds them, not where a short one sits - see
    # _interval_offsets.
    "interval": (((5, 4), 5), ((4, 3), 4), ((3, 2), 3)),
}

# The two guide tones a shell is built from - the 3rd and the 7th - as semitones above
# the root. The table is explicit rather than derived because the house rule is never
# to guess a chord: a quality that is not listed simply has no shell, and the
# selector falls back to a four-note grip for it. Triads and suspended chords appear
# here with their nearest available pair (a triad's "7th" slot is its 5th), because a
# shell under a triad is just the triad in a playable position.
SHELL_DEGREES: Dict[str, Tuple[int, int]] = {
    "maj7": (4, 11), "m7": (3, 10), "m7b5": (3, 10), "dim7": (3, 9),
    "m6": (3, 9), "mMaj7": (3, 11), "maj9": (4, 11), "m9": (3, 10),
    "m9b5": (3, 10), "maj7#11": (4, 11),
    "6": (4, 9), "6/9": (4, 9), "madd9": (3, 7), "add9": (4, 7),
    "7": (4, 10), "9": (4, 10), "13": (4, 9), "7b9": (4, 10), "7alt": (4, 10),
    "7b13": (4, 10), "7#11": (4, 10), "7b5": (4, 10), "7#5": (4, 10),
    "7sus4": (5, 10),
    "maj": (4, 7), "m": (3, 7), "aug": (4, 8), "sus4": (5, 7), "sus2": (2, 7),
}

# The four lowest strings. A four-note voicing here is deliberately NOT offered, and
# this constant is the only place that says so.
#
# With the melody on the G string, a four-note shape would necessarily occupy all four
# of 6-5-4-3, and that does not sound good: it puts four voices in the bottom fourth of
# the compass, where the low E and the A string crowd each other and the chord loses
# its top. A low melody is harmonised with a three-note **shell** instead - 5-4-3 or
# 6-4-3 - which is the ordinary answer for a chord-melody line in this register, and
# which drops the 5th degree, the one the four-note shape was contributing there.
# A low melody is therefore never harmonised with more than three voices here.
# A frozenset, because it is compared against a set of sounding strings.
_BOTTOM_FOUR = frozenset((0, 1, 2, 3))

# The degrees a duo's **second voice** may take: the root, or the 5th.
#
# It gates the *second voice*, not the melody. A duo under a 3rd or a 7th in the melody
# is still a duo: that melody note is exactly the note a guide tone is there to support -
# the guide tone *beneath* it states the function - and it is the one case where the pair
# is unmistakably the chord rather than two passing notes. A melody gate on this list
# would suppress exactly those cases, so there is none; see `_duo_offsets`, which takes
# its second voice from SHELL_DEGREES and skips a unison so the fallback is never the
# melody itself.
#
# A melody that is not a chord tone never reaches the duo at all: the non-chord-tone
# strategies rewrite the chord before generation, which is why a b6 arrives here as the
# 9th or 13th of a resolved chord rather than as a passing note with a duo under it.
#
# It is still the root and the 5th, and still for the reason stated above: they are the
# two notes that carry no information about the chord's quality, so a pair built on
# either leaves the guide tone to do the work. `BASS_DEGREES_6432` below is the same
# rule applied to the bass rather than to a melody.
DUO_DEGREES: Tuple[int, int] = (0, 7)

# The degrees the low-E note may take in a 6-4-3-2 shape. The same rule as
# DUO_DEGREES, applied to the bass rather than to the melody, and for a stronger reason:
# the lowest voice is what *defines* the chord, so a 3rd or a 7th down there sounds like
# the wrong harmony rather than a voicing of this one. With no 5-4-3-2, a root in the
# bass is a consequence of which string set was chosen and never a decision; 6-4-3-2 is
# the one default shape that reaches the low E, and this rule is what makes it place a
# root there.
#   0 = root, 7 = 5th
BASS_DEGREES_6432: Tuple[int, ...] = (0, 7)


# Every single-string set, because a one-note shape may legitimately occupy any of them.
#
# Listing all six is the honest statement rather than the convenient one. A single note on
# one string has no span to exceed and no second voice to clash with, so it is playable
# wherever it is wanted; the constraint that makes `drop2` refuse the bottom four strings
# (`_BOTTOM_FOUR`) is about four voices crowding there, and does not apply to one.
#
# An invariant a shape can violate is not an invariant, and the one-voice comping shape is
# what showed it: it is generated on the *top* string of a `duo` pair - strings 5, 4 and 3 -
# while `tests/test_grips.py` asserted the invariant per *shape* and only for its note
# count, so nothing noticed. Which of the six a given voice *may* use is a separate
# question, and that question is `BASS_VOICE_STRING_SETS` below.
SINGLE_NOTE_STRING_SETS: Tuple[Tuple[int, ...], ...] = tuple((s,) for s in range(6))

# The strings a **single bass voice** may occupy: the bottom three - low E, A and D.
#
# The bass voice is the one selection whose register is part of what it *is*. An alto or a
# tenor stated alone is a guide tone under somebody else's melody, and the top of a duo
# pair is where a player puts one. A bass stated alone is not a guide tone at all: it is
# the bottom of the band, and on a guitar that means the bottom of the neck. The
# measurement behind the table, and the three defects it fixed, are in
# `docs/voices-axis.md` §8a.
#
# Six strings would technically reach further down, but the root of any chord is
# reachable on these three well inside the neck window, so the wider choice would only
# add positions for the selector to reject.
BASS_VOICE_STRING_SETS: Tuple[Tuple[int, ...], ...] = ((0,), (1,), (2,))


def supported_string_sets() -> List[frozenset]:
    """
    Every set of strings a generated voicing may sound, as a set of frozensets.

    This is the playability invariant, stated in one place: a voicing's sounding
    strings must be exactly one of these, and must contain the melody on its topmost
    one. It includes the four-string drop-2 blocks, which `GRIP_STRING_SETS` does not
    list because drop-2 is defined generically - "the four strings below the soprano" -
    so that a caller passing their own `top_string` still works. Tests use this rather
    than re-deriving the rule, so a new grip cannot quietly escape the invariant.

    The bottom four strings are excluded, deliberately: see `_BOTTOM_FOUR`.

    The single-string sets are included, and that is a **consequence** rather than an
    addition: `SINGLE_NOTE_STRING_SETS` states that one note on one string is playable
    anywhere, and an invariant a shape can violate is not an invariant. See
    `SINGLE_NOTE_STRING_SETS` for how the one-note comping shape showed it.
    """
    sets = {
        frozenset(range(top - 3, top + 1))
        for top in MELODY_STRING_CHOICES_FULL
        if frozenset(range(top - 3, top + 1)) != _BOTTOM_FOUR
    }
    for shapes in GRIP_STRING_SETS.values():
        sets.update(frozenset(strings) for strings, _ in shapes)
    sets.update(frozenset(strings) for strings in SINGLE_NOTE_STRING_SETS)
    return sorted(sets, key=lambda s: sorted(s))


# The right hand plucks with thumb, index, middle and ring - `p-i-m-a`, four digits - so
# four strings is the most that can sound at once. `supported_string_sets()` states the
# same four from the shape's side ("two to four strings, every other muted"); this is the
# same limit stated from the hand's, because a *step* is what has to be measured against
# it once a thumb note is merged underneath the shape.
RIGHT_HAND_STRINGS = 4


def grip_pluck_count(grip: str) -> int:
    """How many strings `grip` can sound at once: its widest string set.

    The right hand's budget question, asked of one grip. `melody` is a palette entry
    rather than a grip - a texture names it to mean "the left hand plays the tune alone" -
    so it answers one, which is the shape that entry builds. A name the table does not
    know answers one as well rather than raising, on the same reasoning: this measures a
    palette the texture owns, and an entry that sounds one note cannot spend a finger the
    thumb needs.
    """
    if grip == "melody":
        return 1
    sets = GRIP_STRING_SETS.get(grip, ())
    return max((len(strings) for strings, _ in sets), default=1)


def thumb_safe_grips(palette: Tuple[str, ...]) -> Tuple[str, ...]:
    """The grips in `palette` a hand with a thumb on the bottom string can still play.

    Four digits, one of them the thumb, so a target may sound at most **three** strings
    while a thumb line is running: the fourth string is the bass note. A four-note grip
    plus a thumb is five simultaneous plucks, which no right hand has at any fret - the
    left hand can barre a four-fret shape, and that is exactly why the two budgets are
    separate questions (see `docs/fingering.md` §4.3).

    An **empty** palette comes back unchanged, because it is not a palette that fails the
    budget - it is the table saying "the left hand plays nothing here" (`walking_bass`'s
    fills), and "narrowing" it would hand the thumb a chord it was never offered.

    When every grip the palette names spends all four fingers, the answer is the **widest
    statement that leaves one free** rather than nothing: a target still has to state the
    harmony, which is the rule `TEXTURE_GRIPS["walking_bass"]` already encodes with its
    `("shell",)` target palette. Derived from `GRIP_PREFERENCE` and the string tables, so
    a three-string grip added later is admitted here without an edit - and when two are
    equally wide the winner is the fuller one, which is `shell`.
    """
    if not palette:
        return palette
    kept = tuple(g for g in palette if grip_pluck_count(g) < RIGHT_HAND_STRINGS)
    if kept:
        return kept
    safe = tuple(g for g in GRIP_PREFERENCE if grip_pluck_count(g) < RIGHT_HAND_STRINGS)
    widest = max(grip_pluck_count(g) for g in safe)
    return tuple(g for g in safe if grip_pluck_count(g) == widest)


# The strings the right hand's **thumb** can reach: the four lowest, E A D G. A gap between
# two sounding strings is normally the thumb's - the thumb is on the bottom note and the
# index on the next string up - so the gap only stops being the thumb's where the note under
# it is above this reach. Measured in `docs/fingering.md` §4.4, where narrowing §2.5's
# exemption to this reach moved no count at all: it is the reach the tables already respect.
THUMB_REACH_STRINGS = frozenset((0, 1, 2, 3))


def finger_skip_count(voicing: Voicing) -> int:
    """How many strings a finger has to cross to fret `voicing`: 0, 1, 2 or 3.

    The right hand's second question, after how many strings are plucked. Four adjacent
    strings are no trouble whatever the shape: the thumb takes the bottom note and each
    finger the next string up. The trouble is a **gap** - a string sounding with a silent
    one between it and the string below - because the digit that would take it has to
    reach over a string it is not using, and that is the middle or the ring finger's cost
    (`docs/fingering.md` §2.5).

    The bottom gap is the exception, and it is checked on the **lowest sounding string**:
    while that string is inside the thumb's reach the thumb is the digit on the bottom
    note, so the gap above it is the index's and costs nothing - which is exactly the
    bass-skipping rule this table's four-note sets were built on. Any *other* gap is
    counted, so `(5,4,2,1)` answers 1 - the middle crosses the G - while `(5,4,3,1)`
    answers 0, its gap being the bottom one.

    Note the direction of the asymmetry: the exemption is for the **first** gap only, so a
    set whose bottom note is inside the reach and whose *second* gap is not still counts
    that second gap. Where the bottom note sits above the reach, every gap counts.

    This is a **shape**-level rule, which is the limit of its reach: a `bass_only` step
    merges a thumb note in *after* selection, so that gap is invisible here and §4.4
    measures the merged case at step level instead. And no selector reads this at all -
    the engine enforces the rule by **not offering** the shapes that fail it, so no
    inner-skip `drop24` set is in the table above. Only the `(5,3,2)`
    shell can answer nonzero, kept on purpose for the walking bass's three-layer
    split; `tests/test_grips.py` is what holds the tables to it.
    """
    sounded = sorted(index for index, fret in enumerate(voicing.frets) if fret >= 0)
    total = 0
    for position in range(1, len(sounded)):
        gap = sounded[position] - sounded[position - 1] - 1
        if gap <= 0:
            continue
        if position == 1 and sounded[0] in THUMB_REACH_STRINGS:
            continue           # the thumb has the bottom note: the index's gap, not a skip
        total += gap
    return total


# --- Grip generation -------------------------------------------------------
#
# Everything below turns a chord quality and a melody note into semitone offsets
# below the soprano. It is deliberately separate from VoiceLeadingEngine so the
# theory - which notes go in a grip, and in what order - is stated once and can be
# read without reading the search that follows it.


def _nearest_tone_below(midi: int, pitch_class: int, max_drop: int = 24) -> Optional[int]:
    """
    The highest pitch at or below `midi` that has `pitch_class`, or None.

    Working in real pitches rather than in differences of pitch classes is what keeps
    octave placement honest. The root below a major 3rd is a major sixth down, not a
    major third down: taking the mod-12 difference and calling it the distance puts
    the root a fourth too high and produces voicings that spell the wrong octave.
    """
    for drop in range(max_drop + 1):
        candidate = midi - drop
        if candidate % 12 == pitch_class % 12:
            return candidate
    return None


def _close_stack_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: Optional[int] = None
) -> List[int]:
    """
    A four-voice close-position stack under the melody, as semitone offsets.

    Each voice is the nearest chord tone below the one above it, so the result is the
    tightest four-note chord that fits under the melody. `tones` are pitch classes,
    absolute or relative to `root_pc`; passing the root makes the search a walk *down
    the chord* rather than down the keyboard, which is what a triad needs - with only
    three tones the walk simply wraps to the root an octave below, doubling it, so
    there is no special case for triads.

    Returns fewer than four offsets when the walk cannot continue, which the caller
    treats as "this quality has no four-note shape here".
    """
    if not tones:
        return []
    offsets = [0]
    current = melody_midi
    for _ in range(3):
        nxt: Optional[int] = None
        for tone in tones:
            absolute = tone if root_pc is None else (root_pc + tone) % 12
            found = _nearest_tone_below(current - 1, absolute)
            if found is not None and (nxt is None or found > nxt):
                nxt = found
        if nxt is None:
            break
        current = nxt
        offsets.append(current - melody_midi)
    return offsets


# How far below the melody the guide-tone fallback will look for a voice, in semitones.
# A fourth's breadth, which is about what the four strings below a soprano can voice
# without the shape spanning past a hand: the tuning there is five semitones across, so
# anything wider than this stops being one grip. Generous enough for the deepest guide
# tone (a b7 sits a tone below the melody's octave) and its ninth, and no wider - the
# point is to refuse a root that would name the right notes unplayably rather than to
# search further for one.
_REACH = 14


# The gap between two adjacent strings on a contiguous four-string block, in
# semitones: high E to B is 5, B to G is 5. Consecutive voices must clear each other by
# at least this or the shape cannot be fretted - two voices a semitone apart land on the
# same fret of neighbouring strings and collapse into one note. Read from the tuning
# rather than hardcoded, so a retuning cannot leave this lying.
_BLOCK_SPACING = min(
    abs(
        STANDARD_TUNING[hi].midi_note() - STANDARD_TUNING[lo].midi_note()
    )
    for lo in range(len(STANDARD_TUNING))
    for hi in (lo + 1, lo + 2)
    if hi < len(STANDARD_TUNING)
)


def _duplicates_pitch(pitch: int, placed: List[int]) -> bool:
    """
    Whether `pitch` would land on a note that is *already sounding* at that octave.

    Deliberately almost nothing, and the reason is musical rather than technical: the
    engine's own tables contain adjacent voices a semitone and a tone apart, because a b7
    under a 3rd is the tritone a dominant chord is named for and a b5 against a 3 is what
    "altered" means. A rule that rejected a small interval would refuse the chord's own 3rd
    whenever the melody sat a tone above it - the ordinary case for an altered chord, since
    a b5 over its 3rd *is* a minor 3rd. So the only real constraints are that a voice must
    be a *chord tone* (checked by the caller) and must not duplicate one already placed at
    the same pitch.

    Kept as a named predicate because "no doubled pitch" is a real requirement: two voices
    on one fret would be one note played twice, not a four-note voicing.
    """
    return any(pitch == other for other in placed)


def _guide_tones(tones: Tuple[int, ...], root_pc: Optional[int]) -> Tuple[int, ...]:
    """
    The degrees of this chord that define it: its 3rd (or 4th) and its 7th.

    Read off the tone set rather than tabulated, because it is a property of the chord
    and not of any voicing. The **major** 3rd is preferred where the set holds both
    (7alt carries b3 and 3, since it is an altered chord and either may be asked for),
    because the major one is the chord's actual identity; the b3 there is an option.

    **A suspended chord's guide tone is the 4th, not the 3rd.** Dsus7 is 1 4 5 b7: it has
    no 3rd at all, so a lookup for one finds nothing and reports *no* third - where the note
    that defines the sus chord as a sus chord is exactly that 4th. Two sus voicings have to
    agree about which note
    plays that role, and the hand tables already say so: `SHELL_DEGREES` gives 7sus4
    `(4, b7)` and sus4 `(4, 5)`, and every drop-2 template for those qualities keeps the
    same pair. Reading the tables here rather than re-deriving the rule is what keeps the
    three in step.

    A triad has no 7th, so either may be absent - the caller treats "no 7th" as
    "nothing to preserve" rather than as a failure.
    """
    present = set(t % 12 for t in tones)
    if root_pc is not None:
        present = {(t - root_pc) % 12 for t in tones}
    # The note standing in for the 3rd. In order of preference: a real 3rd, then the 4th
    # of a sus chord, then the 9th of sus2 (whose defining tone is the 9th, not the 2nd -
    # SHELL_DEGREES gives sus2 `(9, 5)`), then the 5th, which is all a bare 6/9 or an
    # incomplete chord leaves.
    third = next(
        (d for d in (4, 3, 5, 2, 7) if d in present), None
    )
    # The note standing in for the 7th: a real b7, a major 7th, or the 6th that replaces
    # both on a 6 or 6/9 chord - SHELL_DEGREES gives 6 and 6/9 `(3, 6)`, not `(3, b7)`.
    seventh = next(
        (d for d in (10, 11, 9) if d in present), None
    )
    return tuple(d for d in (third, seventh) if d is not None)


def _drop2_for_untabled_degree(
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: int,
) -> List[List[int]]:
    """
    A drop-2 for a melody degree the hand tables have no inversion for.

    Two steps, in this order, because they answer different questions.

    **1. Derive it.** The close stack under *this* melody, with its second voice lowered
    an octave, which is the textbook definition and what keeps the result a real drop-2
    of this inversion rather than a template borrowed from another one. For a 5th in the
    melody of a 7#11 that is `5 3 1 b5`.

    **2. Check the guide tones.** A four-note voicing states the chord's 3rd and 7th.
    The derivation does not guarantee it - a walk takes the nearest chord tone below and
    keeps going, so for a melody low in the chord it will spend its voices on the root
    and the 5th and drop the 7th, which changes the chord rather than thinning it. When
    the derived shape is missing a guide tone it is rebuilt from `_guide_tone_drop2`.

    Returns `[]` when neither route produces a shape, and the caller then keeps the
    table's own templates - which is the pre-existing behaviour, and is still better than
    inventing one.
    """
    stack = _close_stack_offsets(tones, melody_midi, root_pc)
    if len(stack) >= 4:
        derived = [0, stack[2], stack[3], stack[1] - 12]
        # `_guide_tones` answers in degrees from the root; the template is absolute
        # pitches below the melody. Comparing the two directly would test a degree
        # against a pitch class and fail for every chord but C, so the sounding set is
        # reduced back to degrees first.
        sounding = {
            (melody_midi + offset - root_pc) % 12 for offset in derived
        }
        if all(degree % 12 in sounding for degree in _guide_tones(tones, root_pc)):
            return [derived]
    return _guide_tone_drop2(tones, melody_midi, root_pc)


def _guide_tone_drop2(
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: int,
) -> List[List[int]]:
    """
    A drop-2 for a melody the hand tables have no inversion for, built from guide tones.

    **Every four-note voicing states the chord's 3rd and 7th.** That is the rule this
    exists to satisfy: the two notes that decide whether the ear hears a major or minor
    chord, and a dominant or a minor 7th. A shape that drops either is not a thinner
    version of the chord, it is a different one - which is why the tables keep them in
    all four inversions rather than treating them as optional.

    So when the melody is a chord tone with no template, the shape is built *backwards
    from the guide tones* instead of from a close stack under the melody. A stack walk
    takes the nearest chord tone below and keeps going, so it will happily spend its
    voices on the root and the 5th and leave the 7th out, producing `4 7 b9 5` for a 5th in
    the melody of a 7#11: a major 3rd and a major 7th against a chord whose identity is 3
    and b7.

    The construction, top to bottom:
      - the melody, which is the soprano by definition;
      - both guide tones, each at the nearest octave below the melody that fits;
      - then the nearest remaining chord tone below, to give the bass something to say.

    "Fits" is the whole difficulty, and it is not a rule about intervals. Two
    *consecutive* voices on a contiguous four-string block are separated by the tuning
    between those strings - five semitones from the high E down to the B, five more to
    the G - so consecutive voices must be at least that far apart or the shape cannot be
    fretted at all. That is why a naive walk produces templates like `[0, -1, -2, -9]`,
    two adjacent voices a semitone apart: `_place_template` then puts both on the same
    fret of adjacent strings and returns a *three*-note shape, which is not a four-note
    voicing and is not a member of any supported string set.

    So each voice is accepted only where it clears every voice above it by at least the
    block's own spacing, and where it is not already sounding. Both are checked against
    `_BLOCK_SPACING`, the real tuning rather than a guess.

    Returns a template only when both guide tones fit. When they do not - the melody is
    very low, or the chord is a sus with no 3rd to find - this returns nothing and the
    caller falls back to the table, because a shape that cannot state the chord's
    identity is worse than an honest absence of one.
    """
    guide = _guide_tones(tones, root_pc)
    if not guide:
        return []

    melody_pc = melody_midi % 12
    chosen: List[int] = [melody_midi]
    # Guide tones first, so the two notes that define the chord are never the ones
    # squeezed out by a later voice competing for the same octave.
    for degree in guide:
        target = (root_pc + degree) % 12
        if target == melody_pc:
            continue  # the melody already states this guide tone
        pitch: Optional[int] = None
        for candidate in range(melody_midi - 1, melody_midi - _REACH, -1):
            if candidate % 12 != target:
                continue
            if _duplicates_pitch(candidate, chosen):
                continue  # already sounding at this octave
            if (melody_midi - candidate) < _BLOCK_SPACING:
                continue  # too close under the melody to be fretted
            pitch = candidate
            break
        if pitch is not None:
            chosen.append(pitch)

    if len(chosen) < 3:
        return []  # could not state both guide tones; do not fake a chord

    def clashes(pitch: int) -> bool:
        """
        Whether this pitch cannot be voiced *below* the voices already placed.

        Two conditions, and the second is the one that actually shapes the result:
        it must not duplicate a pitch already sounding, and it must clear the nearest
        voice above it by at least the string spacing. A voice a semitone or a tone
        under another is fine *musically* - the tables are full of minor 3rds and
        tritones - but two voices that close together cannot both be fretted on
        neighbouring strings, because the strings themselves are four or five semitones
        apart. That is a property of the instrument rather than of the chord, and it is
        why a b7 in the melody of a dominant yields no four-note shape here: the 3rd
        sits a tone below it, so the two cannot be placed in sequence.
        """
        if _duplicates_pitch(pitch, chosen):
            return True
        above = [placed for placed in chosen if placed > pitch]
        if not above:
            return False
        return (min(above) - pitch) < _BLOCK_SPACING

    chord_degrees = {(t - root_pc) % 12 for t in tones}
    # The bass should be a *new* chord tone rather than the melody an octave down.
    # Doubling the melody at the bottom is what the nearest-tone walk keeps choosing,
    # and it gives `5 3 b7 5` for a 5th in the melody of a 7#11: the melody heard twice
    # and the root missing. Preferring the root is also the musically stronger choice -
    # it puts the chord's identity in the bass, which is the same reason voicing_cost
    # has a bass-function tie-break.
    #
    # Placed *before* the generic fill, not after it. Filling first would take the
    # octave of the melody as the fourth voice and leave nothing for the root, which is
    # how `5 3 b7 5` survived a bass preference that was otherwise correct.
    preferred_bass = 0 if 0 in chord_degrees else min(chord_degrees)
    # Bounded by what a hand can hold, not by a two-octave search. The guide tones
    # already sit a 4th and a 7th below the melody here, so a root a further octave
    # down would be a fifth below *those* - `5 3 b7 1` spanning nineteen semitones.
    # That names the right four notes and cannot be played as one shape, so
    # _place_template rejects it and the step loses its chord entirely. Preferring
    # the root is only useful while the root is reachable.
    for candidate in range(melody_midi - 1, melody_midi - _REACH, -1):
        if len(chosen) >= 4:
            break
        if candidate % 12 != (root_pc + preferred_bass) % 12:
            continue
        if clashes(candidate):
            continue
        chosen.append(candidate)

    for pitch in range(min(chosen) - 1, min(chosen) - _REACH, -1):
        if len(chosen) >= 4:
            break
        if (pitch - root_pc) % 12 not in chord_degrees:
            continue
        if clashes(pitch):
            continue
        chosen.append(pitch)
    if len(chosen) < 4:
        return []

    chosen.sort(reverse=True)
    # A drop-2 is a close stack with its second voice lowered an octave, and the
    # lowest note is that lowered voice - so the template is simply the four pitches,
    # top to bottom. What makes it *this* rather than close position is the gap
    # between the top two, which is now a fourth or more because the guide tones sit
    # below the melody rather than beside it.
    return [[pitch - melody_midi for pitch in chosen]]


def _interval_set_for_grip(
    quality: str,
    grip: str,
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: Optional[int] = None,
) -> List[List[int]]:
    """
    The interval templates for a quality under a given grip, as offsets from the
    soprano (0 for the melody itself, negative below it).

    `drop2` returns DROP2_INTERVAL_SETS verbatim and derives nothing. Those tables are
    hand-authored: the extended qualities are voiced *rootless* on purpose, so a 9 or a
    13 that fits into four voices without the root is a musical decision rather than an
    accident of a stack search. Deriving drop-3 and close position from the same chord
    tones therefore gives a fuller chord - a legitimate but different voicing - and it
    is precisely why drop-2's own table is left alone.

    drop-2, drop-3 and close position share one close-position stack of four voices,
    taken as v1, v2, v3, v4 from the top:

        close position    v1  v2  v3  v4
        drop 2            v1  v3  v4  (v2 down an octave)
        drop 3            v1  v2  v4  (v3 down an octave)

    which is the usual definition: a drop-N voicing is a close-position stack with the
    Nth voice from the top lowered by an octave. The last voice of a drop-2 is
    therefore the octave of v2, not v4 - which is what makes the 3rd and the 7th of a
    seventh chord land on the D and G strings in the familiar 4-3-2-1 shell shape.
    """
    if grip == "drop2":
        return DROP2_INTERVAL_SETS.get(quality, [])

    if grip not in ("drop3", "closed", "drop24"):
        return []

    stack = _close_stack_offsets(tones, melody_midi, root_pc)
    if len(stack) < 4:
        return []

    # stack[0] is the melody itself, so the three voices below it are stack[1:]. The
    # templates then read 0 (soprano), v1, v2, v3 as the four voices in the order they
    # sound.
    _, v1, v2, v3 = stack
    if grip == "closed":
        return [[0, v1, v2, v3]]

    # Drop 2 & 4: the SECOND and FOURTH voices each drop an octave. In the names below
    # `v1` is the *second* voice (stack[1]), `v2` the third and `v3` the fourth - which is
    # the source of the confusion this shape invites. So the two that drop are `v1` and
    # `v3`, and `v2` is the one that stays, nearest the melody. The sounding order top to
    # bottom is therefore v2, then v1 and v3 an octave down: `[0, v2, v1 - 12, v3 - 12]`.
    if grip == "drop24":
        # The same root-doubled triad problem as drop-3, and worse: a triad's fourth
        # voice is the doubled root, and dropping *it* as well as v1 puts the chord's
        # identity a further octave down while the third voice keeps the one it has.
        # The doubled root stays where the stack put it.
        if root_pc is not None and (melody_midi + v3) % 12 == root_pc % 12:
            return [[0, v2, v1 - 12, v3]]
        return [[0, v2, v1 - 12, v3 - 12]]

    # Drop 3: the THIRD voice from the top drops an octave. It therefore lands below
    # the bottom voice, so it is the *last* note in the template rather than the
    # third - the shape closes with a 2nd at the bottom. Writing [0, v1, v2 - 12, v3]
    # instead drops the second voice and strands v3 above it, which is not a drop-3 of
    # anything: for a Cmaj7 close stack of C5 B4 G4 E4 it produced C5 B4 G3 E4, with
    # E4 sounding above the G3 that was supposed to be the bass.
    #
    # A triad's fourth voice is the **doubled root** - `_close_stack_offsets` wraps to
    # it an octave down, which is how a three-note chord reaches four. Dropping that
    # voice an octave further is not a drop-3, it is a different chord: for Ebmaj under
    # G4 the stack is G4 Eb4 Bb3 G3, and dropping v2 (Eb4) gives G4 Bb3 G3 Eb3 - a b3
    # and a b7 against a major triad, which sounds as Eb minor. So where the voice
    # being dropped is the root, it is left where the stack put it and v3 takes the
    # octave instead.
    if root_pc is not None and (melody_midi + v2) % 12 == root_pc % 12:
        return [[0, v1, v3 - 12, v2]]
    return [[0, v1, v3, v2 - 12]]


def _duo_offsets(
    tones: Tuple[int, ...],
    melody_midi: int,
    root_pc: int,
    canonical: str,
) -> List[int]:
    """
    A two-note grip under the melody, or an empty list.

    The second voice is **the chord's own guide tone**, read from `SHELL_DEGREES`
    rather than from a list written out here. That is the same table a shell is built
    from, and it already encodes the arranging guide's rule: the 3rd, or the **4th** on
    a suspended chord, with the 7th as the alternative. A hand-written `(4, 3, 0)` scan
    here would list no sus degree, so `sus4`, `sus2` and `7sus4` - whose guide tone is
    the 4th, the 9th and the 4th - would admit **no duo anywhere**; reading the shared
    table gives them one and cannot drift from the shell.

    Preference within the table is `[0]`, then `[1]`. The fallback is **load-bearing,
    not decorative**: when the melody *is* the 3rd, `[0]` would place a unison under it -
    the common case, the 3rd being the melody's own guide tone. A unison is not a second
    voice, so the 7th takes over and the pair becomes a 6th.

    **A 2nd under the melody is dropped an octave.** When the guide tone lands within
    two semitones of the melody the shape is a 2nd, which in two voices is where they
    fight rather than agree; the same pitch class an octave lower makes it a 9th, which
    sits. This is why the duo owns a skipped-string pair: on the adjacent pairs a 9th is
    unreachable inside `GRIP_MAX_SPAN["duo"]`, so a wider pair is what makes it voiceable at
    all. Two cases remain unreachable even now and return nothing rather than sound a 2nd;
    `tests/test_grips.py` names both.

    The melody may be **any** chord tone, not only a root or a 5th. A guide tone beneath a
    3rd or a 7th is exactly what states that note's function, and putting the guide tone
    first is what makes the pair read as the chord rather than as two passing notes. A
    melody that is not a chord tone at all never reaches here: the non-chord-tone
    strategies rewrite the chord before the generator runs, so a duo is always placed
    against a resolved harmony.
    """
    guide = SHELL_DEGREES.get(canonical)
    if guide is None:
        return []

    for degree in guide:
        if degree not in tones:
            continue
        pitch_class = (root_pc + degree) % 12
        # A unison is not a second voice: skip this guide tone and try the other.
        if pitch_class == melody_midi % 12:
            continue
        pitch = _nearest_tone_below(melody_midi, pitch_class)
        if pitch is None:
            continue
        # A 2nd under the melody becomes a 9th - see the docstring.
        while pitch >= 0 and melody_midi - pitch <= 2:
            pitch -= 12
        if pitch < 0:
            continue
        return [0, pitch - melody_midi]
    return []


# The intervals an `interval` grip will pair with the melody, in preference order:
# a minor 3rd, then a major 6th, then a minor 6th. All three are consonant with any
# melody note, which is what a *filling* texture needs - unlike a duo, which is
# claiming to state the chord.
_INTERVAL_CLASSES = (3, 9, 8)

# How those intervals are named in a printed annotation. Keyed by the size in
# semitones, modulo 12, so a 10th reads as the 3rd it is a compound form of - which is
# what a player calls it. "2 notes" is the fallback for a size not in here.
_INTERVAL_NAMES: Dict[int, str] = {3: "3rd", 8: "b6", 9: "6th"}


def _interval_offsets(
    tones: Tuple[int, ...], melody_midi: int, root_pc: int
) -> List[List[int]]:
    """
    Two-note interval shapes under the melody: a 3rd, a 6th or a 10th, as templates.

    This is the arranging guide's "2-note intervals (3rds or 6ths)" - the texture it
    calls for in the gaps between a chord on a strong beat and the next one. It is a
    **texture, not a harmony**, and that distinction is the whole reason it is a
    separate grip rather than a widening of `_duo_offsets`:

      - It is NOT gated on `DUO_DEGREES`. A duo refuses to sound under a 3rd or a 7th
        in the melody, because there those two notes *are* the chord's function and a
        bare pair sounds like a mistake. An interval is not claiming the harmony, so
        it is free to sit under any melody note - which is exactly the case a fill
        most often has to cover, since a passing tone is by definition not a chord
        tone.
      - Because it is confined to fill slots, the looser rule cannot leak into a
        position where a chord is being stated. `TEXTURE_GRIPS` is what enforces that,
        and it is the reason this can safely be more permissive than a duo.

    The second voice is the nearest pitch a 3rd, a 6th or a 10th below the melody that
    is one of the chord's own tones. When the melody is *not* a chord tone, the walk
    also considers the diatonic tones of the prevailing key, so a passing note can
    still be accompanied rather than left naked - and only for the key's own notes,
    never for a chromatic one. That limit is what keeps a fill from quietly
    reharmonising the bar.

    Returns an empty list when the chord has no root or no tone set, on the same
    argument as the shell: an interval named against a chord we cannot identify is a
    guess, and a guess here is how a wrong note gets in.
    """
    if not tones or root_pc is None:
        return []

    # The major scale's pitch classes, used only as a fallback for a melody that is
    # not in the chord. A fill under a passing note should still have a bottom note,
    # but it must be a note the *key* contains - reaching for a chromatic one would be
    # reharmonising, not filling.
    key_pcs = {0, 2, 4, 5, 7, 9, 11}
    chord_pcs = {pc % 12 for pc in tones}

    templates: List[List[int]] = []
    seen: set = set()
    for source in (chord_pcs, key_pcs):
        for size in _INTERVAL_CLASSES:
            # A 3rd or a 6th may sit either side of the octave line, so both are
            # tried; a 10th is the same classes an octave lower.
            for octave in (0, 12):
                candidate = melody_midi - size - octave
                if candidate % 12 not in source:
                    continue
                offset = candidate - melody_midi
                if offset in seen:
                    continue
                seen.add(offset)
                templates.append([0, offset])
        if templates:
            # The chord's own tones are enough on their own; the key is a fallback
            # for a melody that is not in the chord, never an addition to it.
            break
    return templates


def _place_shell(
    quality: str,
    tones: Tuple[int, ...],
    root_pc: int,
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
) -> Optional[Voicing]:
    """
    A three-note shell on one string set, found by searching rather than stacking.

    This needs its own placement for the same reason 6-4-3 does, and the reason is not
    specific to that shape: **a shell's notes are not in descending pitch order down the
    strings.** The tuning is not monotonic in the useful direction. The A string is
    tuned five semitones *above* the D string, and the D string five above the G, so a
    note fretted on the lower string can easily sound higher than its neighbour. A G7
    shell under G3 is `2-3-0-x-x-x` - B2 on the A string, F3 on the D string, G3 on the
    G - and the A string is carrying the *lower* note while being the higher string.
    Any model that lays the voices on strings from the top down by pitch gets this
    backwards and finds nothing.

    So the shape is found by searching: the melody is held at `top_fret` on the soprano
    string and every combination of frets within the span limit is tried on the
    remaining strings, keeping the ones where the guide tones sound and nothing outside
    the chord does. Because the search window is exactly the span limit, the search is
    *exhaustive within the playability invariant* - if a playable shell exists in this
    position, this finds it, which is a stronger guarantee than stacking a nearest-tone
    stack and hoping.

    Ties are broken by fret spread, then by position, so the shape a player would pick
    wins over the first one the search happens to reach.
    """
    guide = SHELL_DEGREES.get(quality)
    if guide is None or len(strings) < 3:
        return None
    allowed = {(root_pc + t) % 12 for t in tones}
    needed = {(root_pc + g) % 12 for g in guide}
    limit = GRIP_MAX_SPAN["shell"]

    lo = max(0, top_fret - limit)
    hi = top_fret + limit
    if hi > 18:
        return None

    best: Optional[Tuple[int, float, Voicing]] = None
    for first in range(lo, hi + 1):
        for second in range(lo, hi + 1):
            frets = [-1] * len(STANDARD_TUNING)
            frets[strings[0]] = top_fret
            frets[strings[1]] = first
            frets[strings[2]] = second
            active = [top_fret, first, second]
            if max(active) - min(active) > limit:
                continue
            midis = sorted(
                GuitarFretboard.fret_to_midi(str, fret)
                for str, fret in zip(strings, (top_fret, first, second))
            )
            pcs = {m % 12 for m in midis}
            # Both guide tones have to sound, and nothing outside the chord may.
            if not needed <= pcs or not pcs <= allowed:
                continue
            spread = max(active) - min(active)
            voicing = Voicing(
                frets=frets,
                top_fret=top_fret,
                avg_fret=sum(active) / len(active),
                grip="shell",
                bass_pc=min(midis) % 12,
            )
            key = (spread, voicing.avg_fret)
            if best is None or key < best[:2]:
                best = (spread, voicing.avg_fret, voicing)
    return best[2] if best else None


def _place_drop2_6432(
    tones: Tuple[int, ...],
    root_pc: int,
    melody_midi: int,
    top_fret: int,
) -> Optional[Voicing]:
    """
    A four-note 6-4-3-2 shape (low E, D, G and the B under the melody), found by
    searching rather than stacking.

    It needs its own placement for the reason 6-4-3 does, and the reason is
    structural: **this set skips the A string, so its strings are not in descending
    pitch order.** The D string is tuned a fifth above the low E, so the low E's note is
    frequently *not* the lowest sounding pitch - a hand-authored drop-2 table, which lays
    voices down by interval, cannot express a shape whose bottom string is not the bottom
    voice. Reusing _place_shell's approach is the answer rather than a second way to
    place notes: hold the melody, search every combination of frets within the span
    limit, keep the legal ones. Because the window is exactly the span limit, the search
    is *exhaustive within the playability invariant*.

    The one extra rule is BASS_DEGREES_6432: the low E carries the chord's root or its
    5th. That is the entire point of the shape, and it is also why it needs a root at
    all - a rootless quality has nothing to measure the low E against, and gets nothing.

    Ties are broken by fret spread then by position, matching _place_shell, so the shape
    a player would pick wins over the first one the search reaches. Ranking the survivors
    is not cosmetic: an unranked search returns whatever comes first, so the grip can look
    as though it is never selected when it is merely ranked last.
    """
    allowed = {(root_pc + t) % 12 for t in tones}
    limit = GRIP_MAX_SPAN["drop2_6432"]

    lo = max(0, top_fret - limit)
    hi = top_fret + limit
    if hi > 18:
        return None

    best: Optional[Tuple[int, float, Voicing]] = None
    for low_e in range(lo, hi + 1):
        for d_fret in range(lo, hi + 1):
            for g_fret in range(lo, hi + 1):
                active = (top_fret, low_e, d_fret, g_fret)
                spread = max(active) - min(active)
                if spread > limit:
                    continue
                frets = [-1] * len(STANDARD_TUNING)
                frets[4] = top_fret
                frets[0] = low_e
                frets[2] = d_fret
                frets[3] = g_fret
                midis = sorted(
                    GuitarFretboard.fret_to_midi(s, frets[s]) for s in (0, 2, 3, 4)
                )
                # The melody stays the top voice, nothing outside the chord sounds, and
                # the low E carries a root or a 5th.
                if midis[-1] != melody_midi:
                    continue
                if not {m % 12 for m in midis} <= allowed:
                    continue
                # The *low E string's* note, which is not the same as the lowest
                # sounding pitch: the D string is a fifth above it.
                if (GuitarFretboard.fret_to_midi(0, low_e) % 12 - root_pc) % 12 not in (
                    BASS_DEGREES_6432
                ):
                    continue
                voicing = Voicing(
                    frets=frets,
                    top_fret=top_fret,
                    avg_fret=sum(active) / len(active),
                    grip="drop2_6432",
                    bass_pc=midis[0] % 12,
                )
                key = (spread, voicing.avg_fret)
                if best is None or key < best[:2]:
                    best = (spread, voicing.avg_fret, voicing)
    return best[2] if best else None


def _place_template(
    template: List[int],
    strings: Tuple[int, ...],
    melody_midi: int,
    top_fret: int,
    grip: str,
) -> Optional[Voicing]:
    """
    Fits an interval template onto a string set, or returns None if it will not play.

    The voices go on the strings from the top down, so the template's order is the
    order they are heard. Playability is the rule the drop-2 engine has always used:
    every fret on the board, and a hand that does not stretch -
    `fret_span() <= GRIP_MAX_SPAN[grip]`.

    The span is checked on the frets actually placed, not as "within N of the soprano".
    Those are not the same condition: bounding each finger to five frets either side of
    the soprano permits a span of ten. That is reachable in practice - the low E and D
    strings are five semitones apart in tuning, so a 6-4-3 shell that sounds correctly
    on them can sit at frets 8 and 0.

    Strings in the set the template does not use are left muted, which is how a
    three-note shell sits inside a four-string set and how 6-4-3 leaves the A string
    alone without saying anything special about it.
    """
    if len(template) > len(strings):
        return None

    frets = [-1] * len(STANDARD_TUNING)
    frets[strings[0]] = top_fret
    limit = GRIP_MAX_SPAN.get(grip, 5)

    for position, offset in enumerate(template[1:], start=1):
        string_idx = strings[position]
        fret = melody_midi + offset - STANDARD_TUNING[string_idx].midi_note()
        if not 0 <= fret <= 18:
            return None
        frets[string_idx] = fret

    active = [f for f in frets if f >= 0]
    if max(active) - min(active) > limit:
        return None
    midis = sorted(
        GuitarFretboard.fret_to_midi(s, f) for s, f in enumerate(frets) if f >= 0
    )
    return Voicing(
        frets=frets,
        top_fret=top_fret,
        avg_fret=sum(active) / len(active),
        grip=grip,
        bass_pc=midis[0] % 12 if midis else None,
    )
_INTERVAL_CLASSES = (3, 9, 8)

# How those intervals are named in a printed annotation. Keyed by the size in
# semitones, modulo 12, so a 10th reads as the 3rd it is a compound form of - which is
# what a player calls it. "2 notes" is the fallback for a size not in here.
_INTERVAL_NAMES: Dict[int, str] = {3: "3rd", 8: "b6", 9: "6th"}



# Accurate Drop-2 interval structures relative to top melody voice for top 4 strings (Strings 4-3-2-1: D, G, B, E).
# Semitone offsets from the soprano (String 1 / High E) down to String 2 (B), String 3 (G), and String 4 (D).
DROP2_INTERVAL_SETS = {
    # --- Major Family ---
    "maj7": [
        [0, -7, -11, -16],  # 7th in top voice
        [0, -5, -8, -13],   # Root in top voice
        [0, -5, -9, -16],   # 3rd in top voice
        [0, -7, -8, -15],   # 5th in top voice
    ],
    "6": [
        [0, -5, -9, -14],   # 6th in top voice
        [0, -5, -8, -15],   # Root in top voice
        [0, -7, -9, -16],   # 3rd in top voice
        [0, -7, -10, -15],  # 5th in top voice
    ],

    # --- Minor Family (Essential for Minor Tunes) ---
    "m7": [
        [0, -7, -10, -15],  # b7 in top voice
        [0, -5, -9, -14],   # Root in top voice
        [0, -5, -8, -15],   # b3 in top voice
        [0, -7, -9, -16],   # 5th in top voice
    ],
    "m7b5": [
        [0, -7, -10, -16],  # b7 in top voice (half-diminished ii chord)
        [0, -6, -9, -14],   # Root in top voice
        [0, -5, -9, -15],   # b3 in top voice
        [0, -6, -8, -15],   # b5 in top voice
    ],
    "dim7": [
        [0, -6, -9, -15],   # bb7 / dim7 in top voice (symmetrical)
        [0, -6, -9, -15],   # Root in top voice
        [0, -6, -9, -15],   # b3 in top voice
        [0, -6, -9, -15],   # b5 in top voice
    ],
    "m6": [
        [0, -6, -9, -14],   # 6th in top voice (tonic minor)
        [0, -5, -9, -15],   # Root in top voice
        [0, -6, -8, -15],   # b3 in top voice
        [0, -7, -10, -16],  # 5th in top voice
    ],
    "mMaj7": [
        [0, -8, -11, -16],  # 7th in top voice (melodic minor tonic)
        [0, -5, -9, -13],   # Root in top voice
        [0, -4, -8, -15],   # b3 in top voice
        [0, -7, -8, -16],   # 5th in top voice
    ],

    # --- Dominant Family (Resolutions in Major & Minor Keys) ---
    "7": [
        [0, -6, -10, -15],  # b7 in top voice
        [0, -5, -8, -14],   # Root in top voice
        [0, -6, -9, -16],   # 3rd in top voice
        [0, -7, -9, -15],   # 5th in top voice
    ],
    "7b9": [
        [0, -6, -9, -15],   # b9 in top voice (rootless diminished 7th shell: 3, 5, b7, b9)
        [0, -6, -9, -15],   # 3rd in top voice
        [0, -6, -9, -15],   # 5th in top voice
        [0, -6, -9, -15],   # b7 in top voice
        [0, -8, -11, -14],  # Root in top voice (5th omitted: 1, b9, 3, b7)
    ],
    "7alt": [
        [0, -6, -9, -14],   # b7 in top voice (altered dominant: 3, b7, b9, b13)
        [0, -5, -9, -15],   # b9 in top voice
        [0, -6, -8, -15],   # 3rd in top voice
        [0, -7, -10, -16],  # b13 in top voice
        [0, -8, -11, -14],  # Root in top voice (b13 omitted: root, b9, 3, b7)
    ],

    # --- Extended / colour qualities ---
    # These are voiced rootless (root, 5th or 13th omitted as needed) so the
    # five chord tones of a ninth always fit the four strings. They are what
    # the 'extension' non-chord-tone strategy reharmonises into, e.g. the 9th
    # of Cmaj7 (D) becomes a Cmaj9, so D is a genuine chord tone again.
    "maj9": [
        [0, -8, -10, -13],  # Root in top voice (5th omitted)
        [0, -5, -9, -14],   # 3rd in top voice (rootless 3-5-7-9)
        [0, -5, -8, -15],   # 5th in top voice
        [0, -7, -9, -16],   # 7th in top voice
        [0, -7, -10, -15],  # 9th in top voice
    ],
    "m9": [
        [0, -9, -10, -14],  # Root in top voice (5th omitted)
        [0, -5, -8, -13],   # b3 in top voice (rootless b3-5-b7-9)
        [0, -5, -9, -16],   # 5th in top voice
        [0, -7, -8, -15],   # b7 in top voice
        [0, -7, -11, -16],  # 9th in top voice
    ],
    "9": [
        [0, -8, -10, -14],  # Root in top voice (5th omitted)
        [0, -6, -9, -14],   # 3rd in top voice (rootless 3-5-b7-9)
        [0, -5, -9, -15],   # 5th in top voice
        [0, -6, -8, -15],   # b7 in top voice
        [0, -7, -10, -16],  # 9th in top voice
    ],
    "6/9": [
        [0, -8, -10, -15],  # Root in top voice (5th omitted)
        [0, -7, -9, -14],   # 3rd in top voice (rootless 3-5-6-9)
        [0, -5, -10, -15],  # 5th in top voice
        [0, -5, -7, -14],   # 6th in top voice
        [0, -7, -10, -17],  # 9th in top voice
    ],
    "13": [
        [0, -3, -8, -14],   # Root in top voice (5th omitted)
        [0, -7, -9, -18],   # 3rd in top voice (rootless 3-5-b7-13)
        [0, -9, -10, -15],  # 5th in top voice
        [0, -3, -6, -13],   # b7 in top voice
        [0, -5, -11, -14],  # 13th in top voice
    ],

    # --- Triads (four voices: the root is doubled an octave below the stack) ---
    "maj": [
        [0, -8, -12, -17],  # Root in top voice (root doubled underneath)
        [0, -9, -12, -16],  # 3rd in top voice
        [0, -7, -12, -15],  # 5th in top voice
    ],
    "m": [
        [0, -9, -12, -17],  # Root in top voice (root doubled underneath)
        [0, -8, -12, -15],  # b3 in top voice
        [0, -7, -12, -16],  # 5th in top voice
    ],
    "aug": [
        # Symmetrical, so every inversion fingers identically (like dim7).
        [0, -8, -12, -16],  # Root in top voice
        [0, -8, -12, -16],  # 3rd in top voice
        [0, -8, -12, -16],  # #5 in top voice
    ],

    # --- Suspended chords ---
    "sus4": [
        [0, -7, -12, -17],   # Root in top voice
        [0, -10, -12, -17],  # 4th in top voice
        [0, -7, -12, -14],   # 5th in top voice
    ],
    "sus2": [
        [0, -10, -12, -17],  # Root in top voice
        [0, -7, -12, -14],   # 2nd (9th) in top voice
        [0, -7, -12, -17],   # 5th in top voice
    ],
    "7sus4": [
        [0, -5, -7, -14],   # Root in top voice (3rd replaced by the 4th)
        [0, -7, -10, -17],  # 4th in top voice
        [0, -7, -9, -14],   # 5th in top voice
        [0, -5, -10, -15],  # b7 in top voice
    ],

    # --- Added-note colours ---
    "add9": [
        [0, -8, -10, -17],  # Root in top voice (5th omitted)
        [0, -7, -10, -14],  # 9th in top voice
        [0, -4, -9, -14],   # 3rd in top voice
        [0, -5, -7, -15],   # 5th in top voice
    ],
    "madd9": [
        [0, -9, -10, -17],  # Root in top voice (5th omitted)
        [0, -7, -11, -14],  # 9th in top voice
        [0, -3, -8, -13],   # b3 in top voice
        [0, -5, -7, -16],   # 5th in top voice
    ],

    # --- Altered and Lydian dominants ---
    "7b5": [
        # Symmetrical, so only two distinct shapes cover the four inversions.
        [0, -6, -8, -14],   # Root in top voice
        [0, -6, -10, -16],  # 3rd in top voice
        [0, -6, -8, -14],   # b5 in top voice
        [0, -6, -10, -16],  # b7 in top voice
    ],
    "7#5": [
        [0, -4, -8, -14],   # Root in top voice
        [0, -6, -8, -16],   # 3rd in top voice
        [0, -8, -10, -16],  # #5 in top voice
        [0, -6, -10, -14],  # b7 in top voice
    ],
    "7#11": [
        # The #11 replaces the perfect 5th: root, 3rd, #11, b7.
        [0, -6, -8, -14],   # Root in top voice (5th omitted)
        [0, -6, -10, -16],  # 3rd in top voice
        [0, -6, -8, -14],   # #11 in top voice
        [0, -6, -10, -16],  # b7 in top voice
    ],
    "7b13": [
        # b13 is enharmonic with #5, so the shapes match 7#5.
        [0, -4, -8, -14],   # Root in top voice (natural 5th omitted)
        [0, -6, -8, -16],   # 3rd in top voice
        [0, -8, -10, -16],  # b13 in top voice
        [0, -6, -10, -14],  # b7 in top voice
    ],
    "maj7#11": [
        [0, -6, -8, -13],   # Root in top voice (5th omitted)
        [0, -5, -10, -16],  # 3rd in top voice
        [0, -6, -7, -14],   # #11 in top voice
        [0, -7, -11, -17],  # 7th in top voice
    ],
    "m9b5": [
        # Half-diminished ninth: the m9 shapes with the 5th flattened.
        [0, -9, -10, -14],  # Root in top voice (b5 omitted: root-9-b3-b7)
        [0, -5, -9, -13],   # b3 in top voice (rootless b3-b5-b7-9)
        [0, -4, -8, -15],   # b5 in top voice
        [0, -7, -8, -16],   # b7 in top voice
        [0, -8, -11, -16],  # 9th in top voice
    ],
}

# Aliases for flexible chord quality notation
DROP2_INTERVAL_SETS["min7"] = DROP2_INTERVAL_SETS["m7"]
DROP2_INTERVAL_SETS["min7b5"] = DROP2_INTERVAL_SETS["m7b5"]
DROP2_INTERVAL_SETS["ø7"] = DROP2_INTERVAL_SETS["m7b5"]
DROP2_INTERVAL_SETS["ø"] = DROP2_INTERVAL_SETS["m7b5"]
DROP2_INTERVAL_SETS["half-dim"] = DROP2_INTERVAL_SETS["m7b5"]
DROP2_INTERVAL_SETS["°7"] = DROP2_INTERVAL_SETS["dim7"]
DROP2_INTERVAL_SETS["°"] = DROP2_INTERVAL_SETS["dim7"]
DROP2_INTERVAL_SETS["dim"] = DROP2_INTERVAL_SETS["dim7"]
DROP2_INTERVAL_SETS["min6"] = DROP2_INTERVAL_SETS["m6"]
DROP2_INTERVAL_SETS["minMaj7"] = DROP2_INTERVAL_SETS["mMaj7"]
DROP2_INTERVAL_SETS["mmaj7"] = DROP2_INTERVAL_SETS["mMaj7"]
DROP2_INTERVAL_SETS["dom7"] = DROP2_INTERVAL_SETS["7"]
DROP2_INTERVAL_SETS["M7"] = DROP2_INTERVAL_SETS["maj7"]

# Degree pitch classes relative to chord root (matches the soprano note to an inversion).
# Each entry lines up one-to-one with DROP2_INTERVAL_SETS[quality]: entry i is the
# chord tone sitting in the top voice of template i.
DEGREE_OFFSETS_FROM_ROOT = {
    "maj7": [11, 0, 4, 7],
    "6": [9, 0, 4, 7],
    "m7": [10, 0, 3, 7],
    "m7b5": [10, 0, 3, 6],
    "dim7": [9, 0, 3, 6],
    "m6": [9, 0, 3, 7],
    "mMaj7": [11, 0, 3, 7],
    "7": [10, 0, 4, 7],
    "7b9": [1, 4, 7, 10, 0],
    "7alt": [10, 1, 4, 8, 0],
    "maj9": [0, 4, 7, 11, 2],
    "m9": [0, 3, 7, 10, 2],
    "9": [0, 4, 7, 10, 2],
    "6/9": [0, 4, 7, 9, 2],
    "13": [0, 4, 7, 10, 9],
    "maj": [0, 4, 7],
    "m": [0, 3, 7],
    "aug": [0, 4, 8],
    "sus4": [0, 5, 7],
    "sus2": [0, 2, 7],
    "add9": [0, 2, 4, 7],
    "madd9": [0, 2, 3, 7],
    "7sus4": [0, 5, 7, 10],
    "7b5": [0, 4, 6, 10],
    "7#5": [0, 4, 8, 10],
    "7#11": [0, 4, 6, 10],
    "7b13": [0, 4, 8, 10],
    "maj7#11": [0, 4, 6, 11],
    "m9b5": [0, 3, 6, 10, 2],
}


def _parse_chord_name(name: str) -> Tuple[Optional[str], Optional[str]]:
    """Delegates to ChordParser for backward compatibility."""
    return ChordParser.parse_chord_name(name)


def _string_sets_for(grip: str, top_string: int) -> List[Tuple[int, ...]]:
    """
    Every string set `grip` can occupy with its soprano on `top_string`, each
    **ordered from the soprano downwards**, which is the order _place_template
    assigns voices in.

    A list rather than one set, because a grip can have more than one shape for the
    same string: a G-string shell is either 5-4-3 or 6-4-3, and returning only the
    first would silently hide 6-4-3 behind 5-4-3.

    For drop-2 the set is simply the four strings from the soprano down, which
    uses the four strings below the soprano for *any* top_string and so keeps
    get_drop2_voicings working for callers who pass their own. The other grips come
    from a fixed table (GRIP_STRING_SETS, stored low-to-high for readability) because
    they are named shapes: a 6-4-3 shell is that shape or it is nothing, and it is
    not available on every string.

    The table lists each set low-to-high, so the soprano is found by *searching* for
    it rather than by assuming an end: for a 1-2-3 shell the soprano is the first
    entry, for 6-4-3 it is the last, and a duo like (5, 4) happens to start on it.
    Every entry names its soprano as its **highest** string, so ordering the set
    descending is what puts the soprano first.

    Descending order, and specifically *not* a rotation. Rotating the stored
    low-to-high tuple from the soprano (`strings[pivot:] + strings[:pivot]`) looks
    equivalent and is not: for the four-string block stored (2, 3, 4, 5) with the
    soprano on 5 it yields (5, 2, 3, 4), which walks *up* the neck for the next
    three voices. That hands a voice the G-string note on the G string, the D-string
    note on the D string and the B-string note on the B string while claiming to
    descend - the pitches are right and the strings are not, and the span check then
    measures frets on strings the voice was never meant for. A rotation is only
    order-preserving if the tuple is already in the order being rotated *into*, and
    this one is stored the other way up.
    """
    if grip == "drop2":
        # A caller may pass any `top_string`, and the rule is that the four strings below
        # it are used, so a top_string with no table entry still works. The table is
        # consulted only where it has an entry - which is what adds the bass-skipping
        # sets, since they are keyed on the soprano they belong to.
        tabulated = [
            tuple(sorted(strings, reverse=True))
            for strings, soprano in GRIP_STRING_SETS["drop2"]
            if soprano == top_string
        ]
        if tabulated:
            return tabulated
        if top_string < 3:
            return []
        strings = tuple(range(top_string, top_string - 4, -1))
        # A G-string soprano has no four-note block: see _BOTTOM_FOUR. Shells and
        # duos still apply there, and the table below lists them.
        if frozenset(strings) == _BOTTOM_FOUR:
            return []
        return [strings]
    sets: List[Tuple[int, ...]] = []
    for strings, soprano in GRIP_STRING_SETS.get(grip, ()):
        if soprano == top_string and soprano in strings:
            sets.append(tuple(sorted(strings, reverse=True)))
    return sets


def _chord_context(
    chord_type: str, chord_name: Optional[str]
) -> Tuple[str, Optional[int], Tuple[int, ...]]:
    """
    The canonical quality, the root's pitch class, and the chord's tones **as
    degrees from that root**.

    The degrees are deliberately not absolute. Every grip builder wants to reason
    in intervals - "the 3rd of a minor 7th is three semitones up" - and only the
    final pitch placement wants an absolute note. Keeping one frame throughout means
    there is a single place (the search for a pitch at or below the soprano) where
    degrees become pitches, and a chord whose root cannot be found simply yields
    nothing rather than being transposed by accident.

    Note this is *not* ChordParser.get_chord_tones(quality, chord_name), which
    returns absolute pitch classes once a name is supplied. The tones are the full
    set for the quality, not the four the drop-2 tables voice, so a shell or a duo
    is built from every tone the chord really has.

    A quality with no usable root - a bare quality symbol with no chord name, or an
    unparseable root - has root_pc of None, and only the drop-2 path still serves it,
    because those tables are written as offsets from the soprano and need no root.
    """
    canonical = ChordParser.canonical_quality(chord_type)
    root_pc: Optional[int] = None
    root_str, _ = ChordParser.parse_chord_name(chord_name) if chord_name else (None, None)
    if root_str:
        try:
            root_pc = Note(f"{root_str}4").midi_note() % 12
        except (KeyError, ValueError, TypeError):
            root_pc = None
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical, ())
    return canonical, root_pc, tones


def _shell_voicing(
    frets_by_string: Tuple[int, ...],
    frets: Tuple[int, ...],
    midis: List[int],
    canonical: str,
    root_pc: int,
    tones: Tuple[int, ...],
    notes: int = 3,
    bass_voice: bool = False,
    shell_root: bool = False,
) -> Optional[Voicing]:
    """
    One comping candidate, or None when it does not state the chord.

    Both guide tones must sound and nothing outside the chord may, which is the rule
    `_place_shell` already enforces and the reason this is a helper rather than being
    written twice. Shared by the melody-bearing shell and the melody-free one so the
    two cannot drift apart on what counts as a shell.

    `notes` is **how many voices the guitar was asked to play**, which is the arity of the
    shape: `alto,tenor` is two notes and `alto,tenor,tenor`-style requests are still two
    because a voice is a *role* in the stack, not a count. The pair case is the reason
    this is a parameter and not a constant -- with two voices there is no room for the
    third note a three-voice shell spends on the root or the 5th, and asking for a shape
    that sounds three notes when two were named is how a part ends up with a voice in it
    that belongs to somebody else.

    **`bass_voice` changes which note the shape must sound, because it changes what the
    shape is.** Every other selection here is stating a chord *quality* to somebody
    else's ear, so the guide tones are the claim. A lone bass note is stating the chord's
    *function*, and a 3rd or a 7th down there does not sound like a bass note at all - it
    sounds like the wrong chord. The library already states that rule for the one place
    it had to: `BASS_DEGREES_6432` carries the comment "the lowest voice is what *defines*
    the chord, so a 3rd or a 7th down there sounds like the wrong harmony rather than a
    voicing of this one", and this is that same rule read from that same table rather than
    a second one written here.

    So a bass voice takes the **root, or the 5th where the root is unreachable**, in
    preference order, and keeps the same rule as every other shape: nothing outside the
    chord may sound. The 5th is a fallback rather than a co-equal choice because the
    root is the note that names the chord; a 5th names it only in company.

    **`shell_root` is the third way to spend the bottom of the shape**, and the only one
    that asks for *more* than a plain guide-tone shape: both guide tones, and a bass
    degree underneath them, so the ear hears which chord it is as well as what quality.
    It is checked as the conjunction of the two rules above rather than as a third list,
    which is why it can be added without deciding anything new about degrees - see
    `HARMONY_STYLES` in `textures.py`, which is where the *vocabulary* lives.
    """
    guide = SHELL_DEGREES.get(canonical)
    if guide is None:
        return None
    if len(frets_by_string) < notes:
        return None
    pcs = {midi % 12 for midi in midis}
    if bass_voice:
        # The same containment check every other candidate makes, before anything else.
        allowed = {(root_pc + tone) % 12 for tone in tones}
        if not pcs <= allowed:
            return None
        # Root first, then the 5th: the degree order is `BASS_DEGREES_6432`'s, and it is
        # tried as a preference rather than required, so a chord whose root cannot be
        # fretted here still gets a bass note instead of no note.
        for degree in BASS_DEGREES_6432:
            if (root_pc + degree) % 12 in pcs:
                break
        else:
            return None
    elif shell_root:
        # **The new case, and it is a conjunction of two rules rather than a third one.**
        # A `shell_root` shape says both things at once: the guide tones state the chord's
        # *quality*, and a bass degree underneath says which chord it is. Each half is
        # already stated by a table - `SHELL_DEGREES` for the first, `BASS_DEGREES_6432`
        # for the second - so the check is both of those, applied, and not a new list
        # written here that could drift from either.
        #
        # The containment check comes first and unconditionally, exactly as in every
        # other branch: a shape sounding a note outside the chord is not a voicing of
        # this one whatever else it gets right.
        allowed = {(root_pc + tone) % 12 for tone in tones}
        if not pcs <= allowed:
            return None
        needed = {(root_pc + degree) % 12 for degree in guide}
        if not needed <= pcs:
            return None
        # **The lowest note, not merely *a* note of that degree.** This is the whole
        # difference between this family and a guide-tone shape, and it is the part that
        # is easy to get wrong: on an `Ebmaj` whose guide tones are D and G, a shape of
        # `D G Bb` already *contains* a fifth (Bb), so a check for "some bass degree is
        # sounding" is satisfied by the plain guide-tone shape and this family would
        # silently be a synonym for `guide`. Stating the harmony from the bottom up
        # means the bass degree is the one the ear hears **first**, so it is checked on
        # the lowest sounding note rather than on the set.
        #
        # Root first, 5th as the fallback: the same preference order `BASS_DEGREES_6432`
        # states, read here rather than re-decided, because the root is the note that
        # names the chord and a 5th names it only in company.
        lowest = min(midis) % 12
        if lowest not in {(root_pc + degree) % 12 for degree in BASS_DEGREES_6432}:
            return None
    else:
        # **One voice is a weaker claim, and the rule says so rather than refusing.** Two
        # notes can sound both guide tones, which is what states the chord; one note cannot,
        # and a single note *is* the whole of a `duo` - the grip family this library has
        # always offered for "the melody plus one guide tone". So a one-voice selection keeps
        # the **first** guide tone (the 3rd, or the 4th on a sus chord) and drops the second,
        # which is the same preference order `_duo_offsets` already applies.
        #
        # Refusing here would instead make `--voices alto` fall through to the ordinary
        # melody-bearing route, which warns on every step and hands the horn's line back
        # to the guitarist - the opposite of what naming one voice asked for.
        keep = 2 if notes >= 2 else 1
        needed = {(root_pc + degree) % 12 for degree in guide[:keep]}
        allowed = {(root_pc + tone) % 12 for tone in tones}
        if not needed <= pcs or not pcs <= allowed:
            return None

    vector = [-1] * len(STANDARD_TUNING)
    for string, fret in zip(frets_by_string, frets):
        vector[string] = fret
    active = list(frets)
    return Voicing(
        frets=vector,
        top_fret=frets[0],
        avg_fret=sum(active) / len(active),
        grip="shell",
        bass_pc=min(midis) % 12,
    )


def get_comping_voicings(
    chord_type: str,
    chord_name: Optional[str] = None,
    fret_min: int = NECK_FRET_MIN,
    fret_max: int = NECK_FRET_MAX,
    notes: int = 3,
    bass_voice: bool = False,
    shell_root: bool = False,
) -> List[Voicing]:
    """
    Guide-tone comping shapes: the chord stated **without** the melody on top.

    This is the guitarist's part when somebody else has the tune - a horn in front of
    the band - which is why it takes no melody argument at all. Every other candidate
    in this module is built around pinning the melody to the soprano string; this is
    the one that has none to pin.

    **It is `_place_shell`'s own search with nothing held at the top.** A shell is
    already a claim about the chord's 3rd and 7th rather than about the tune, so
    `_place_shell` needed no change: it already tries every fret combination on the
    remaining strings and keeps the ones where both guide tones sound and nothing
    outside the chord does. The only difference is that the top fret is searched too
    rather than fixed by a melody, and the shape is ranked on spread and position
    instead of against a pinned note. Because the window is exactly `GRIP_MAX_SPAN`,
    the search stays exhaustive within the playability invariant.

    Only the `shell` string sets are offered, and that is the musical claim rather
    than a limitation: with no melody to support, a fourth voice would be the root or
    the 5th - the two notes that carry no information about the chord's quality. The
    guide tones are what state whether the ear hears a major or a minor chord.

    `notes` is the **arity asked for**, and it is honoured rather than treated as a
    preference: `2` is the alto-and-tenor comping pair, `3` the shell. A string set too
    small for the request is **skipped rather than padded**, because a part sounding more
    notes than the caller named is worse than a thinner one - the extra note is a voice
    somebody else was supposed to have.

    **`bass_voice` is what stops the arity from being the whole question.** It is True
    only for a selection naming the bass and nothing else, and it does two things: it
    offers the bottom-of-neck string sets instead of the `duo` tops (so the note lands
    in a bass register rather than the middle of the neck), and it takes the note from
    `BASS_DEGREES_6432` rather than `SHELL_DEGREES` (so it is a root or a 5th rather than
    a 3rd). Both are needed and neither is enough: a low 3rd is still not a bass note.

    **`shell_root` asks for both guide tones *and* a root or 5th under them**, which is
    the claim neither flag above can state: `bass_voice` spends the whole shape on the
    bass, and the default spends it on the guide tones alone. It is a `harmony=` value
    rather than a change of arity, because it is a claim about *which degrees sound* and
    not about how many notes there are - the same reason `HARMONY_STYLES` is a table of
    degree families and not a count. It resolves on the **existing** `(5,4,3)` shell sets,
    so no new string set is involved - `docs/comping-styles.md` holds the measurement.

    Every candidate sounds only chord tones, holds a fret span of at most
    `GRIP_MAX_SPAN["shell"]`, and occupies one string set from `GRIP_STRING_SETS["shell"]`
    - or, for a bass voice, one from `BASS_VOICE_STRING_SETS` / the `duo` tops. **Unlike
    every other candidate in the library, none of these carries a melody**, so the
    invariant that a voicing sounds the melody on its topmost string does not apply to
    them and is not asserted - see `tests/test_comping.py`.

    `fret_min`/`fret_max` bound the search the way they bound the selector everywhere
    else: as a **preference**, never a filter. A chord whose comping shape sits
    outside the window is still generated and still playable, because losing a chord
    of the tune is worse than being a fret out of position.
    """
    canonical, root_pc, tones = _chord_context(chord_type, chord_name)
    # No root, no claim to make: a guide tone is a claim about *this* chord's 3rd and
    # 7th, and guessing them without a root is how a wrong note gets in. The same
    # rule, and the same reason, as `get_grip_voicings`'s shell and duo branches.
    if root_pc is None:
        return []

    limit = GRIP_MAX_SPAN["shell"]
    # The board, not the window: `fret_max` is a preference `voicing_cost` applies, so
    # searching past it and letting the selector rank is what keeps a chord of the tune
    # from vanishing. Clamped at 18, which is the end of the neck.
    hi = min(fret_max + limit, 18)
    lo = max(0, fret_min - limit)

    valid: List[Voicing] = []
    for used in _comping_string_sets(notes, bass_voice):
        best: Optional[Tuple[Tuple[int, float], Voicing]] = None
        for frets in _frets_in_span(used, lo, hi, limit):
            midis = sorted(
                GuitarFretboard.fret_to_midi(string, fret)
                for string, fret in zip(used, frets)
            )
            found = _shell_voicing(
                used, frets, midis, canonical, root_pc, tones, notes, bass_voice,
                shell_root,
            )
            if found is None:
                continue
            # Ranked here rather than by `voicing_cost`, because this is a *generator*
            # and choosing is the selector's job - the split every other family keeps.
            # One per string set: a tighter shape lower on the neck is the one a player
            # would pick, and offering the rest would only give the selector a worse
            # shape to lose.
            key = (max(frets) - min(frets), sum(frets) / len(frets))
            if best is None or key < best[0]:
                best = (key, found)
        if best is not None:
            valid.append(best[1])
    return valid


def _comping_string_sets(
    notes: int, bass_voice: bool = False
) -> List[Tuple[int, ...]]:
    """The string sets a comping shape of `notes` voices may occupy, most preferred first.

    **The arity picks the family, rather than truncating one.** Truncating a `shell` set
    to two strings looks free and is not: it yields pairs the library has never vetted -
    `(0, 2)` skips the A string, `(5, 3)` skips the B - and those would enter the tab as
    if they had been designed for the job. They have not. A two-note shape is a `duo`,
    the family this library has always offered for exactly that, and its four sets are
    measured for reach and span.

    Three notes take the `shell` sets unchanged, which is the whole point of the shell.
    One note takes the `duo` sets' top strings, since a single note is the limiting case
    of a pair and any of those strings will do.

    **`bass_voice` moves the one-note case to the bottom of the neck, and it is a
    different question rather than a different arity.** "A single note is the limiting
    case of a pair" is true of an *inner* voice - an alto or a tenor is a guide tone
    under somebody else's melody, and the top of a duo pair is where a player puts one.
    A bass stated alone is not a guide tone at all; it is the bottom of the band, so on a
    guitar it belongs on the bottom of the neck, which the `duo` sets never offer.

    This is why the flag is a parameter and not a fourth arity: `alto`, `tenor` and `bass`
    all request **one note** and all reach this function, so arity alone cannot tell them
    apart. See `docs/voices-axis.md` §8a for what that cost.

    It applies only at arity one, because that is the only arity where the selection
    names nothing but the bass: at two or more voices the shape is a pair or a shell
    whose lowest note is placed by its own string set, and moving that would be
    re-deciding a shape that is already correct.
    """
    if notes <= 1:
        if bass_voice:
            return list(BASS_VOICE_STRING_SETS)
        return [(strings[0],) for strings, _ in GRIP_STRING_SETS["duo"]]
    if notes == 2:
        return [strings for strings, _ in GRIP_STRING_SETS["duo"]]
    return [strings for strings, _ in GRIP_STRING_SETS["shell"]]


def _frets_in_span(
    strings: Tuple[int, ...], lo: int, hi: int, limit: int
) -> Iterable[Tuple[int, ...]]:
    """Every fret tuple on `strings` inside `lo`..`hi` whose span is at most `limit`.

    Written as a recursive generator rather than one nested loop per arity, because
    `notes` is a parameter and the alternative is a separate copy of this search for
    every arity - which is exactly how the melody-bearing shell and this one drifted
    apart the first time they were written separately.

    The window narrows as it recurses (`first - limit` .. `first + limit`), so the
    search is still exhaustive over span-legal combinations and never materialises the
    ones the span rule would reject.
    """
    if not strings:
        yield ()
        return
    rest = strings[1:]
    for first in range(lo, hi + 1):
        window_lo = max(lo, first - limit)
        window_hi = min(hi, first + limit)
        for tail in _frets_in_span(rest, window_lo, window_hi, limit):
            yield (first,) + tail


def get_grip_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_string: int = 5,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """
    Generates fingerings for `grips` on one string block, pinned to the melody.

    This is the general form of get_drop2_voicings, and with `grips=("drop2",)` it
    produces exactly what that method always has. The other families differ in what
    they carry rather than in where they sit:

      drop2   four voices, from the hand-authored tables
      drop3   four voices, a close stack with the third voice dropped
      drop24  four voices, a close stack with the second *and* fourth dropped
      closed  four voices in close position under the melody
      shell   three voices: the 3rd, the 7th, and one more
      duo     two voices, and only under a root or a 5th (see DUO_DEGREES)
      interval  two voices a 3rd, 6th or 10th apart - a fill, and under *any*
               melody degree (see _interval_offsets for why that is safe)

    Candidate generation is *pure*. It does not filter by neck position, does not
    transpose, and does not know what came before - choosing among the results is
    _best_voicing's job. Keeping that split is what stops the grip families and the
    octave-down rescue from having to know about each other.

    Every candidate sounds only chord tones, uses 2-4 strings all belonging to one
    GRIP_STRING_SETS entry, carries the melody on its topmost string, and holds a
    fret span of at most GRIP_MAX_SPAN[grip].
    """
    melody_midi = melody_note.midi_note()

    top_fret = GuitarFretboard.note_to_fret(top_string, melody_note)
    if top_fret < 0 or top_fret > 18:
        return []

    canonical, root_pc, tones = _chord_context(chord_type, chord_name)

    # Which inversion of a drop-2 table puts this melody in the top voice. The
    # derived families build their shape from the chord tones themselves and so
    # need no steering; this only narrows the table lookup.
    target_idx: Optional[int] = None
    deg_offsets = DEGREE_OFFSETS_FROM_ROOT.get(canonical)
    if chord_name and deg_offsets and root_pc is not None:
        mel_degree = (melody_midi - root_pc) % 12
        for idx, d in enumerate(deg_offsets):
            if d % 12 == mel_degree:
                target_idx = idx
                break

    valid_voicings: List[Voicing] = []
    for grip in grips:
        for strings in _string_sets_for(grip, top_string):
            if grip in ("shell", "duo", "interval", "drop2_6432"):
                # These three are defined by the guide tones, so a chord with no root
                # to measure them from gets nothing. That is a real limitation
                # rather than a fallback: a shell is a claim about *this* chord's
                # 3rd and 7th, and guessing them without a root is how a chord gets
                # a wrong note in it. An interval is measured from the root for the
                # same reason - it is placed against a named chord, not a key.
                if root_pc is None:
                    continue
                if grip == "duo":
                    duo = _duo_offsets(tones, melody_midi, root_pc, canonical)
                    templates = [duo] if duo else []
                elif grip == "drop2_6432":
                    # Found by its own search, like every other non-contiguous
                    # shape: a skipped-string set cannot come from a table, and
                    # the bass rule needs a root to measure against. No inversion
                    # is narrowed here, because `target_idx` picks a template for a
                    # contiguous block and has no meaning for a set of four
                    # strings the voices were not laid on.
                    if root_pc is None:
                        continue
                    found = _place_drop2_6432(
                        tones, root_pc, melody_midi, top_fret
                    )
                    if found is not None:
                        valid_voicings.append(found)
                    continue
                elif grip == "interval":
                    # A texture rather than a claim about the chord, so it is built
                    # from templates and placed like a drop-2 - no search needed,
                    # because an interval *is* the two notes it names.
                    templates = _interval_offsets(tones, melody_midi, root_pc)
                else:
                    # Every shell set is placed by the same search, 6-4-3 included:
                    # a shell's notes are not in descending pitch order down the
                    # strings, so none of them can come from a stack.
                    found = _place_shell(
                        canonical, tones, root_pc, strings, melody_midi, top_fret
                    )
                    if found is not None:
                        valid_voicings.append(found)
                    continue
            else:
                templates = _interval_set_for_grip(
                    canonical, grip, tones, melody_midi, root_pc
                )
                if grip == "drop2":
                    if (
                        target_idx is not None
                        and 0 <= target_idx < len(templates)
                    ):
                        templates = [templates[target_idx]]
                    elif (
                        root_pc is not None
                        and tones
                        and (melody_midi - root_pc) % 12
                        in {(t - root_pc) % 12 for t in tones}
                        # Only for a quality whose table is genuinely *incomplete*. Every
                        # triad and every four-note quality has a template for each of its
                        # tones, so `target_idx` is None there only when the melody is
                        # not a chord tone at all - and then the derivation below would
                        # invent the missing voices. It did: Ebmaj under G4, whose tones
                        # are Eb G Bb, came out `b7 5 b3 5` - a b3 and a 5th against a
                        # major triad, which is Eb minor. The guard is the tone count,
                        # because a chord that has more tones than four cannot have a
                        # template for every one of them.
                        and len({(t - root_pc) % 12 for t in tones}) > 4
                    ):
                        # The melody is a chord tone with no inversion in the table.
                        # The templates that *do* exist are for other soprano degrees,
                        # so offering them here would pin this melody to the soprano
                        # string and put each template's own top note *below* it - the
                        # shape stops being that inversion and sounds whatever the
                        # offsets happen to spell over this melody. For a 5th in the
                        # melody of a 7#11 that produced `5 b9 7 4`: a b9 and a major
                        # 3rd against a chord whose identity is 3, b5 and b7.
                        #
                        # So the shape is derived from the close stack under this
                        # melody, which keeps it a genuine drop-2 of *this* inversion,
                        # and is then held to the rule that a four-note voicing states
                        # the chord's 3rd and 7th.
                        #
                        # An empty result means no four-note voicing of this inversion is
                        # playable, and the honest answer is to offer *none*: falling
                        # back to another degree's template reintroduces exactly the
                        # defect above. A step with no voicing is demoted to the melody
                        # alone or promoted to a shell, both of which still state the
                        # chord; a step with a borrowed template states a different one.
                        templates = _drop2_for_untabled_degree(
                            tones, melody_midi, root_pc,
                        )

            for template in templates:
                voicing = _place_template(
                    template, strings, melody_midi, top_fret, grip
                )
                if voicing is not None:
                    valid_voicings.append(voicing)

    return valid_voicings


def get_drop2_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_string: int = 5,
) -> List[Voicing]:
    """
    Generates valid 4-string Drop-2 fretboard fingerings pinned to the melody note.

    top_string is the index of the string carrying the melody: 5 (high E) yields the
    traditional D-G-B-E shape, while 4 (B) yields the lower A-D-G-B shape used when
    the melody sits below the high E string's open pitch. When chord_name (e.g.
    'Dm7b5') is provided, it matches the specific inversion where melody_note
    functions as the correct chord tone.

    Kept as a named entry point because it is what callers reach for directly and
    its output is part of the library's published behaviour. It is exactly
    get_grip_voicings with the grip pinned to drop-2.
    """
    return get_grip_voicings(
        melody_note, chord_type, chord_name, top_string, grips=("drop2",)
    )


def get_interval_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_string: int = 5,
) -> List[Voicing]:
    """
    Two-note interval fingerings under the melody: a 3rd, a 6th or a 10th.

    The arranging guide's fill for the notes between a chord on a strong beat and
    the next one. It is a **texture and not a harmony** - it says nothing about
    what the chord is, and it is meant to sit on a weak beat - so unlike a duo it
    is offered under *any* melody degree, including a 3rd or a 7th that a duo
    refuses. `TEXTURE_GRIPS` is what confines it to fill slots, which is what makes
    the looser rule safe.

    Kept as a named entry point for the same reason as `get_drop2_voicings`: every
    grip family is reachable from the public surface, so a caller who wants a
    single one does not have to know the tuple spelling. It is exactly
    get_grip_voicings with the grip pinned to "interval".

    Returns an empty list when the chord has no usable root, or when the melody is
    unreachable on that string - the same limitation every root-measured grip has.
    """
    return get_grip_voicings(
        melody_note, chord_type, chord_name, top_string, grips=("interval",)
    )


def _lower_soprano_strings(top_strings: Tuple[int, ...]) -> Tuple[int, ...]:
    """
    The subset of `top_strings` below the high E, so a transposed melody is voiced
    on the B string rather than back on the high E. Falls back to `top_strings`
    when it contains nothing below the high E, so a caller restricted to (5,)
    still gets a (higher) voicing instead of nothing.
    """
    lower = tuple(s for s in top_strings if s < len(STANDARD_TUNING) - 1)
    return lower or tuple(top_strings)


def _melody_only_string_order(prefer: Tuple[int, ...]) -> List[int]:
    """
    String indices to try for a melody-only voicing: those in `prefer` first (in
    the order given), then every other string from the highest sounding one down.

    Duplicates and out-of-range indices in `prefer` are ignored, so a caller
    cannot make the search repeat a string or index past the fretboard.
    """
    order: List[int] = []
    top = len(STANDARD_TUNING) - 1
    for string_index in list(prefer) + list(range(top, -1, -1)):
        if 0 <= string_index <= top and string_index not in order:
            order.append(string_index)
    return order


def get_octave_down_candidates(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """
    Candidates for melody_note an octave lower, on the strings below the high E.

    A melody whose only position sits outside the neck window is re-voiced here so
    the whole harmonisation comes down the neck. Because the B string is five
    semitones below the high E, the octave-down transposition lands seventeen
    semitones - exactly a major tenth - below where the same note sat on the high
    E, which is what actually brings it into a playable position.

    The wider candidate pool matters here as much as anywhere: a high melody that no
    four-note shape can reach inside the window may still have a three-note shell
    under it, and taking that beats skipping the step.

    Returns an empty list when the octave-down melody cannot be voiced at all, so
    the caller can keep the original candidates rather than losing the step.
    """
    octave_down = Note(_note_name(melody_note.midi_note() - 12))
    return get_all_grip_voicings(
        octave_down,
        chord_type,
        chord_name=chord_name,
        top_strings=_lower_soprano_strings(top_strings),
        grips=grips,
    )


def get_all_grip_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
    grips: Tuple[str, ...] = GRIP_PREFERENCE,
) -> List[Voicing]:
    """
    Collects fingerings for every allowed soprano string in `top_strings`.

    High-E candidates come first, so a caller that simply takes the first result
    keeps the traditional top-string fingering. Candidate generation tries the
    chord-tone-matched inversion first and falls back to quality-only voicings, so
    nothing is lost when chord_name cannot place the melody on a chord tone. A
    melody below the high E string's open pitch (E4) simply yields no high-E
    candidates and is arranged on a lower string instead of being skipped.

    This is pure candidate generation: it neither filters by neck position nor
    transposes. A melody whose only position lies outside the window is re-voiced
    an octave down by get_octave_down_candidates, which arrange_progression calls -
    so the two cannot recurse into each other.
    """
    candidates: List[Voicing] = []
    for top_string in top_strings:
        candidates.extend(
            get_grip_voicings(
                melody_note, chord_type, chord_name, top_string, grips
            )
        )

    if not candidates and chord_name:
        for top_string in top_strings:
            candidates.extend(
                get_grip_voicings(
                    melody_note, chord_type, None, top_string, grips
                )
            )

    return candidates


def get_all_drop2_voicings(
    melody_note: Note,
    chord_type: str,
    chord_name: Optional[str] = None,
    top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES,
) -> List[Voicing]:
    """
    Collects Drop-2 fingerings for every allowed soprano string in top_strings.

    High-E candidates come first, so a caller that simply takes the first result
    keeps the traditional top-string fingering. Candidate generation tries the
    chord-tone-matched inversion first and falls back to quality-only voicings, so
    nothing is lost when chord_name cannot place the melody on a chord tone. A
    melody below the high E string's open pitch (E4) simply yields no high-E
    candidates and is arranged on the B string instead of being skipped.

    This is pure candidate generation: it neither filters by neck position nor
    transposes. A melody whose only position lies above HIGH_FRET_LIMIT is
    re-voiced an octave down by get_octave_down_candidates, which
    arrange_progression calls - so the two cannot recurse into each other.
    """
    return get_all_grip_voicings(
        melody_note, chord_type, chord_name, top_strings, grips=("drop2",)
    )


def get_melody_only_voicing(
    melody_note: Note,
    prefer: Tuple[int, ...] = MELODY_STRING_CHOICES,
) -> Optional[Voicing]:
    """
    Returns a single-fret Voicing that plays melody_note alone, or None.

    This is the voicing used for a NO_CHORD ("NC") step: a bar of melody with
    no harmony behind it, which is voiced as written rather than harmonised or
    reharmonised. It is deliberately NOT a drop-2 voicing and so does not obey
    the four-contiguous-strings playability invariant - there is exactly one
    active fret, and fret_span() is 0.

    The strings in `prefer` (high E, then B) are tried in order; when none of
    them can reach the note - or the preferred ones are exhausted - the
    remaining strings are tried from the high E downwards, so a low melody
    such as G3 still sounds on the open G string.

    A melody that is playable but only above HIGH_FRET_LIMIT is retried an octave
    down on the strings below the high E, so a high note is played in a
    comfortable position.

    A melody that is unreachable at the written pitch at all still returns None
    rather than being respelled: None is the documented signal that a note cannot
    sound (B5 is fret 19, C6 is fret 20 - both past the end of the board), and
    quietly playing it an octave down would hide that from the caller.
    """
    # Reachability at the written pitch, across every string, decides whether the
    # octave-down attempt is legitimate at all. Without this a genuinely
    # unplayable note would be silently respelled and reported as playable.
    if not any(
        0 <= GuitarFretboard.note_to_fret(s, melody_note) <= 18
        for s in range(len(STANDARD_TUNING))
    ):
        return None

    attempts: List[Tuple[Tuple[int, ...], int]] = [
        (prefer, 0),
        (_lower_soprano_strings(prefer), -12),
    ]
    for strings, octave_shift in attempts:
        for string_index in _melody_only_string_order(strings):
            shifted = Note(_note_name(melody_note.midi_note() + octave_shift))
            fret = GuitarFretboard.note_to_fret(string_index, shifted)
            if 0 <= fret <= HIGH_FRET_LIMIT:
                frets = [-1] * len(STANDARD_TUNING)
                frets[string_index] = fret
                # `grip` is set rather than left at its "drop2" default: this is a
                # single-fret shape, and a caller reading `voicing.grip` would
                # otherwise conclude a four-note drop-2 had been chosen. The
                # playability invariant keys off this field.
                return Voicing(
                    frets=frets,
                    top_fret=fret,
                    avg_fret=float(fret),
                    grip="melody",
                )
    return None


def sustain_inner_voices(previous_voicing: Voicing | dict, melody_note: Note) -> Optional[Voicing]:
    """
    Strategy 3: hold the previous chord's three inner voices and move only the
    soprano to the new melody note, the way a player sustains a shape under a
    passing tone. Returns None when the melody is unreachable on the same
    string within a playable span, so the caller can reharmonise instead.
    """
    frets = previous_voicing["frets"] if isinstance(previous_voicing, dict) else previous_voicing.frets
    frets = list(frets)

    soprano = max((s_idx for s_idx, fret in enumerate(frets) if fret >= 0), default=-1)
    if soprano < 0:
        return None

    top_fret = GuitarFretboard.note_to_fret(soprano, melody_note)
    if top_fret < 0:
        return None

    frets[soprano] = top_fret
    active = [fret for fret in frets if fret >= 0]
    if max(active) - min(active) > 5:
        return None

    # Divided by the number of *sounding* fingers, not by four: the previous voicing may be
    # a three-note shell or a two-note duo, and a shell's mean fret is not one quarter of
    # its sum. Getting this wrong misreports where the shape is, which is exactly what the
    # selector compares.
    prev_grip = (
        previous_voicing.grip if isinstance(previous_voicing, Voicing) else "drop2"
    )
    midis = [
        GuitarFretboard.fret_to_midi(s, fret) for s, fret in enumerate(frets) if fret >= 0
    ]
    return Voicing(
        frets=frets,
        top_fret=top_fret,
        avg_fret=sum(active) / len(active),
        grip=prev_grip,
        bass_pc=min(midis) % 12 if midis else None,
    )
