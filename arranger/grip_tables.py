"""The grip tables, and the questions asked of them.

Nothing here builds a shape or chooses one: these are the string sets, spans, tone
rules and right-hand budgets the generators in `grips` read, plus the small queries
over them (`supported_string_sets`, `thumb_safe_grips`, `comping_string_sets`,
`stated_tones`). It sits below `grips` because a generator may read a table and a
table reads nothing above this module.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .chords import ChordParser
from .tuning import MELODY_STRING_CHOICES_FULL, Voicing

# Grip families, in the order they are generated in - which is *also* the order an exact
# tie is broken in: `cost.best_voicing` is a stable `min` and no criterion in
# `cost.voicing_cost` names a family, so of two candidates at the winning cost the one
# generated first wins. This tuple is the default `grips=`, and with the family axis gone
# nothing replaces it: the tuple *is* the order, which is what makes "most preferred first"
# a property of the library rather than of a request. One tuple, one job, and a family's
# position here is load-bearing.
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
    # of the four sets removed for it, and `tests/test_grip_tables.py` holds every reachable set
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
    # the bottom-four block excluded by `BOTTOM_FOUR`: it swaps the A string out for
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
    # a search, not stacking, for the same reason 6-4-3 does.
    #
    # (5, 3, 2) is the *other* 5-3-2: high E, G and D, skipping the B on the way up
    # rather than the D on the way down. It balances the shell sets by soprano - the high
    # E is the *most* used soprano, because `MELODY_STRING_CHOICES_FULL` puts it first, and
    # this gives it a second shape where the B and the G each have two. It is also the
    # three-layer split a walking-bass shell wants (melody on the high E, guide tones on the
    # G and the D, leaving the 5th and 6th strings to the thumb), so it earns its place
    # twice over. Like the other non-contiguous sets it needs a searched placement, not
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


# --- Which of a chord's tones a shape states -----------------------------------
#
# One row per quality: that chord's own tones, most defining first. A shape of `voices`
# voices states the melody's tone and then the next `voices - 1` entries of the row, so a
# four-note drop-2, a three-note shell and a two-note duo are this one rule at three
# arities. It is the rule the hand-written drop-2 tables encoded, and it is now the source
# as well as the rule: `drop2_template_for` reads one degree out of a row, and the 119
# templates the tables held are kept as the witness the rule is asserted against
# (`tests/support.py`, read by `tests/test_generated_grips.py`). The reasoning, the
# measurements and the order that was *not* taken are in `docs/history/generated-grips.md`.
#
# What the rows say, read off the templates that reproduce them:
#
#   - **The first two entries are `SHELL_DEGREES`, in that order** - all 29 qualities. A
#     shell and a drop-2 state the same pair, so the row is the one place that fact lives.
#   - **The tail ranks which tone goes, and it is per-quality.** The nearer the end of a row
#     a tone sits, the sooner a four-voice shape gives it up: a row ending `..., root, 5th`
#     gives up the natural 5th first (`maj7`, `m7`, `7`, `6`), one ending `..., 5th, root`
#     gives up the root first (`9`, `maj9`, `7b9`). Of the 119 templates, 24 drop the root and
#     keep the natural 5th, and 18 drop the natural 5th and keep the root - 6 because the
#     melody *is* the root, and 12 on `7#11`, `7b13` and `maj7#11`. No single global order
#     reproduces them, which is the whole reason this is a table and not one rule.
#   - **An altered 5th is not a 5th.** 39 of the 45 altered-5th occurrences in the tables
#     are stated; the 6 that are not are the `b5` of an `m9b5`, and of `7alt`, which has
#     seven tones and must lose two. So a b5, #5, #11 or b13 ranks near the top of its
#     row, not down beside the natural 5th - and **above the root**, so a reduced-arity
#     shape gives the root up before it.
#   - **A name-given extension is not optional, and one the name does not give is.** A
#     `13` states its 13th and its b7 and drops its 9th, which the name never promised:
#     its row reads 3, 13, b7, 5, root, 9.
#
# The first two entries are pinned by `SHELL_DEGREES` at every quality. Entries beyond
# them only *bite* where a chord has more tones than the shape has voices, which is 11 of
# these 29 - the other 18 are free orderings, and their tail carries no information. Do
# not tidy them into a shared shape: for the 11 that are constrained, the row is the
# decision.
TONE_PRIORITY: Dict[str, Tuple[int, ...]] = {
    "maj7": (4, 11, 0, 7), "6": (4, 9, 0, 7), "m7": (3, 10, 0, 7),
    "m7b5": (3, 10, 6, 0), "dim7": (3, 9, 6, 0), "m6": (3, 9, 0, 7),
    "mMaj7": (3, 11, 0, 7), "7": (4, 10, 0, 7),
    "7b9": (4, 10, 1, 7, 0), "7alt": (4, 10, 1, 8, 0, 3, 6),
    "maj9": (4, 11, 2, 7, 0), "m9": (3, 10, 2, 7, 0), "9": (4, 10, 2, 7, 0),
    "6/9": (4, 9, 2, 7, 0), "13": (4, 9, 10, 7, 0, 2),
    "7#11": (4, 10, 6, 0, 7), "7b13": (4, 10, 8, 0, 7),
    "maj7#11": (4, 11, 6, 0, 7), "m9b5": (3, 10, 2, 6, 0),
    "maj": (4, 7, 0), "m": (3, 7, 0), "aug": (4, 8, 0),
    "sus4": (5, 7, 0), "sus2": (2, 7, 0),
    "add9": (4, 7, 0, 2), "madd9": (3, 7, 0, 2),
    "7sus4": (5, 10, 0, 7), "7b5": (4, 10, 6, 0), "7#5": (4, 10, 8, 0),
}


# The two guide tones a shell is built from - the 3rd and the 7th - as semitones above
# the root. This is `TONE_PRIORITY`'s first two entries per quality, spelled out: it is
# what `_shell_request` and `_duo_offsets` read today, and a quality that is not listed
# simply has no shell, so the selector falls back to a four-note grip for it. Triads and
# suspended chords appear here with their nearest available pair (a triad's "7th" slot is
# its 5th), because a shell under a triad is just the triad in a playable position.
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
BOTTOM_FOUR = frozenset((0, 1, 2, 3))


# Every single-string set, because a one-note shape may legitimately occupy any of them.
#
# Listing all six is the honest statement rather than the convenient one. A single note on
# one string has no span to exceed and no second voice to clash with, so it is playable
# wherever it is wanted; the constraint that makes `drop2` refuse the bottom four strings
# (`BOTTOM_FOUR`) is about four voices crowding there, and does not apply to one.
#
# An invariant a shape can violate is not an invariant, and the one-voice comping shape is
# what showed it: it is generated on the *top* string of a `duo` pair - strings 4 and 3,
# once `COMPING_EXCLUDED_STRINGS` has taken the high E off the comping part - while
# `tests/test_grips.py` asserted the invariant per *shape* and only for its note
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
# `docs/history/voices-axis.md` §8a.
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

    The bottom four strings are excluded, deliberately: see `BOTTOM_FOUR`.

    The single-string sets are included, and that is a **consequence** rather than an
    addition: `SINGLE_NOTE_STRING_SETS` states that one note on one string is playable
    anywhere, and an invariant a shape can violate is not an invariant. See
    `SINGLE_NOTE_STRING_SETS` for how the one-note comping shape showed it.
    """
    sets = {
        frozenset(range(top - 3, top + 1))
        for top in MELODY_STRING_CHOICES_FULL
        if frozenset(range(top - 3, top + 1)) != BOTTOM_FOUR
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
    separate questions (see `docs/history/fingering.md` §4.3).

    An **empty** palette comes back unchanged, because it is not a palette that fails the
    budget - it is the declaration saying "the left hand plays nothing here", and
    "narrowing" it would hand the thumb a chord it was never offered. No shipped texture,
    selection or thumb line yields one (`tests/test_texture.py` sweeps them all), but the
    rule stays for a caller that passes one.

    When every grip the palette names spends all four fingers, the answer is the **widest
    statement that leaves one free** rather than nothing: a target still has to state the
    harmony, which is the rule a walked target's palette already encodes with its
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
# it is above this reach. Measured in `docs/history/fingering.md` §4.4, where narrowing §2.5's
# exemption to this reach moved no count at all: it is the reach the tables already respect.
THUMB_REACH_STRINGS = frozenset((0, 1, 2, 3))


def finger_skip_count(voicing: Voicing) -> int:
    """How many strings a finger has to cross to fret `voicing`: 0, 1, 2 or 3.

    The right hand's second question, after how many strings are plucked. Four adjacent
    strings are no trouble whatever the shape: the thumb takes the bottom note and each
    finger the next string up. The trouble is a **gap** - a string sounding with a silent
    one between it and the string below - because the digit that would take it has to
    reach over a string it is not using, and that is the middle or the ring finger's cost
    (`docs/history/fingering.md` §2.5).

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
    split; `tests/test_grip_tables.py` is what holds the tables to it.
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


def stated_tones(
    quality: str, melody_degree: int, voices: int = 4
) -> Tuple[int, ...]:
    """
    The chord tones a shape of `voices` voices states, the melody's own tone first.

    This is `TONE_PRIORITY` read out: the melody's degree, then the next `voices - 1`
    of that quality's row. It **narrows and never widens** - asking it for more voices
    than the chord has tones returns the whole row - so a shape can never state a note
    the chord does not contain.

    The melody's degree is returned whether or not it is a chord tone, because the
    melody is the caller's note and is never rewritten. Degrees are pitch classes
    relative to the chord's root, which is the unit `drop2_template_for` is asked in.

    Every degree of a quality's row is one of its chord tones, so the drop-2 generator
    only ever asks for one of those - a tone with no place in the row would have no shape
    at all. A melody that is *not* a chord tone is a different question, answered by
    offering `_drop2_palette` rather than by this rule.
    """
    order = TONE_PRIORITY.get(ChordParser.canonical_quality(quality))
    if order is None:
        return ()
    degree = melody_degree % 12
    return tuple(
        [degree] + [t for t in order if t % 12 != degree][: max(0, voices - 1)]
    )


# How those intervals are named in a printed annotation. Keyed by the size in
# semitones, modulo 12, so a 10th reads as the 3rd it is a compound form of - which is
# what a player calls it. "2 notes" is the fallback for a size not in here.
INTERVAL_NAMES: Dict[int, str] = {3: "3rd", 8: "b6", 9: "6th"}


# The one string a **comping shape** never sounds, whatever its arity: the high E.
#
# It is the string the tune itself is pinned to first (`MELODY_STRING_CHOICES_FULL` tries
# it before the B and the G), and a comping part has no tune to put there. A shape whose
# top voice sits on it is therefore heard as a melody - and heard *above* the horn that is
# playing the real one, which is the opposite of what a comping part is for.
#
# Every set that carries it has it as its **soprano** (it is the highest string there is),
# so the filter below reads as one sentence: a comping shape never puts its top voice on
# the high E. Dropping the sets is what makes that a property of the palette rather than a
# criterion in `cost.voicing_cost`; `docs/engine.md` §"`get_comping_voicings`: a chord with
# no melody on top" holds the register that buys and what it costs in shapes.
COMPING_EXCLUDED_STRINGS: Tuple[int, ...] = (5,)


def _comping_family(notes: int, bass_voice: bool) -> List[Tuple[int, ...]]:
    """The sets the arity's own family offers, before the high E is taken off them.

    **The arity picks the family, rather than truncating one.** Truncating a `shell` set
    to two strings looks free and is not: it yields pairs the library has never vetted -
    `(0, 2)` skips the A string, `(5, 3)` skips the B - and those would enter the tab as
    if they had been designed for the job. They have not. A two-note shape is a `duo`,
    the family this library has always offered for exactly that, and its four sets are
    measured for reach and span.

    Three notes take the `shell` sets unchanged, which is the whole point of the shell.
    One note takes the `duo` sets' top strings, since a single note is the limiting case
    of a pair and any of those strings will do.
    """
    if notes <= 1:
        if bass_voice:
            return list(BASS_VOICE_STRING_SETS)
        return [(strings[0],) for strings, _ in GRIP_STRING_SETS["duo"]]
    if notes == 2:
        return [strings for strings, _ in GRIP_STRING_SETS["duo"]]
    return [strings for strings, _ in GRIP_STRING_SETS["shell"]]


def comping_string_sets(
    notes: int, bass_voice: bool = False
) -> List[Tuple[int, ...]]:
    """The string sets a comping shape of `notes` voices may occupy, most preferred first.

    **The high E is not offered at any arity** (`COMPING_EXCLUDED_STRINGS` carries the
    reason). The sets that carry it are dropped rather than ranked lower, so the rule is a
    property of the palette the generator is handed and no criterion has to know about it -
    and no arity reaches the string, because every family is filtered by the same constant.
    Which family an arity takes, and why it is not a truncated one, is `_comping_family`.

    **A set is offered once.** Two `duo` pairs share the G string as their top, so the
    one-note arity would otherwise name the same shape twice - harmless to the ranking, and
    wrong as a palette: it hands the selector the identical candidate twice.

    **`bass_voice` moves the one-note case to the bottom of the neck, and it is a
    different question rather than a different arity.** "A single note is the limiting
    case of a pair" is true of an *inner* voice - an alto or a tenor is a guide tone
    under somebody else's melody, and the top of a duo pair is where a player puts one.
    A bass stated alone is not a guide tone at all; it is the bottom of the band, so on a
    guitar it belongs on the bottom of the neck, which the `duo` sets never offer.

    This is why the flag is a parameter and not a fourth arity: `alto`, `tenor` and `bass`
    all request **one note** and all reach this function, so arity alone cannot tell them
    apart. See `docs/history/voices-axis.md` §8a for what that cost. It applies only at
    arity one, the only arity whose selection names nothing but the bass: at two or more
    voices the lowest note is placed by the shape's own string set, and moving that would
    re-decide a shape that is already correct.
    """
    # One pass, because both rules are about a set that must not be *offered* rather than
    # about a shape that must not be chosen.
    offered: List[Tuple[int, ...]] = []
    for strings in _comping_family(notes, bass_voice):
        if set(strings) & set(COMPING_EXCLUDED_STRINGS) or strings in offered:
            continue
        offered.append(strings)
    return offered
