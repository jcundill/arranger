"""Grip families: the tables, the builders, and the candidate generators.

Everything that turns a chord quality and a melody note into a *set of candidate
voicings* is here, and nothing here chooses between them. That split is what lets
this module be read on its own: `cost` holds the selection rule, and no generator
below knows what came before it, what the neck window is, or what the answer
turned out to be.

**The generators are free functions, and `VoiceLeadingEngine` keeps one-line
`@classmethod` delegates.** They used to be classmethods, and roughly forty call
sites in the tests and the front ends spell them
`VoiceLeadingEngine.get_drop2_voicings(...)`; a refactor is not the moment to
break those spellings. A delegate leaves one implementation, so there is nothing
to keep in step.

The four non-contiguous string sets - 6-4-3, both 5-3-2s and 6-4-3-2 - are
*searched* rather than stacked, because their voices are not in descending pitch
order down the strings: the A string is tuned five semitones above the D. See
`_place_shell` and `_place_drop2_6432`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from musthe import Note

from .chords import ChordParser
from .tuning import (
    HIGH_FRET_LIMIT,
    MELODY_STRING_CHOICES,
    MELODY_STRING_CHOICES_FULL,
    STANDARD_TUNING,
    GuitarFretboard,
    Voicing,
    _note_name,
)

# Grip families, in the order that breaks an exact tie. A four-note drop-2 shape is
# listed first so it is never displaced by a shell when the two cost the same.
#
# `drop2_6432` is the 6-4-3-2 block (low E, D, G, B), listed second and after the
# contiguous blocks because it is the *alternative* rather than the default reading of
# "drop-2": `grips=("drop2",)` still means the contiguous four strings only, which is
# the idiom that reproduces the library's original output exactly. It is a separate
# family, not a third string set for `drop2`, precisely so that idiom survives.
#
# `drop3` and `drop24` are offered; `closed` still is not.
#
# Drop-3 and close position were originally excluded because neither produces a playable
# shape at this span limit: a close-position four-note chord under a melody spans a
# seventh or more, and the four strings below the high E are only five semitones apart,
# so the frets come out more than five apart. **That was true of the contiguous block and
# stopped being true of the shape.** With a bass permitted to skip to a lower string,
# drop-3 is playable across most of the register and drop-2 & 4 across nearly all of it,
# and measured on the Weimar corpus both are as tight as drop-2 - frequently span 0 to 2.
#
# They are here for a second reason too, which is the one that matters. A melody that is
# *not* a chord tone leaves drop-2 with no template and no shell, so its quality-only
# fallback offers shapes carrying two to four notes the chord does not contain. Drop-3 and
# drop-2 & 4 derive from the close stack under the melody, which keeps every *other*
# voice a chord tone: measured over every quality and every melody, they produce zero
# wrong notes where drop-2 produces hundreds. Offering them is what puts a correct
# voicing in the candidate set for the selector to find - see `cost.voicing_cost`, whose
# first criterion counts wrong notes rather than flagging them. `closed` stays out
# because it is the one of the three that still cannot be fretted inside the budget.
#
# Ordered after drop-2 so the idiomatic four-note reading wins a tie, and before the
# shells so a complete chord is preferred to a partial harmonisation.
GRIP_PREFERENCE: Tuple[str, ...] = (
    "drop2", "drop3", "drop24", "drop2_6432", "shell", "duo",
)

# The maximum distance, in frets, from the lowest to the highest active fret. Five for
# every four-note shape and every three-note shell; a duo is only ever two fingers, so
# it is held to a tighter four.
#
# This is a *distance*, `max(frets) - min(frets)`, not a count of frets touched: a
# shape on frets 6 and 10 spans four, because the hand reaches four frets from index
# to pinky. That is the ordinary, comfortable four-finger span - frets 6, 7, 8, 9, 10
# are five separate frets but the stretch across them is four, which is what a
# guitarist means by "a four-fret span". Counting the touched frets inclusively
# instead would make the limit describe something the hand does not do.
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
    # playable is the same bass-skipping rule as everywhere else, and here it has to skip
    # an **inner** string as well, because the shape is not just deeper but differently
    # spaced. Measured across sevenths, ninths and sixths over the whole working register,
    # two sets win essentially every melody:
    #
    #   (1, 2, 4, 5)  strings 1-2-4-5   skip the G; 49 wins at span 2, 47 at span 1
    #   (2, 3, 5, 6)  strings 2-3-5-6   skip the B; 24 wins at span 1, 11 at span 2
    #
    # against 1 win for everything else combined. Both keep the melody on a long string
    # and put the two dropped voices on strings whose tuning suits their spacing. The
    # contiguous blocks are offered too, so a shape that does fit one is still reachable
    # and the selector can prefer the familiar layout on a tie.
    #
    # Stored as **string indices**, high to low, like every other entry - so the
    # conventional numbers above read 1-2-4-5 as (5, 4, 2, 1). Written the other way
    # round these produced a set containing string index 6, which does not exist, and
    # `_place_template` indexed off the end of the fret list.
    "drop24": (
        ((5, 4, 2, 1), 5), ((5, 3, 2, 0), 5),
        ((5, 4, 3, 2), 5), ((5, 4, 3, 1), 5),
        ((4, 3, 1, 0), 4), ((4, 2, 1, 0), 4),
        ((4, 3, 2, 1), 4), ((4, 3, 2, 0), 4),
    ),
    # 6-4-3-2: low E, D, G and B with the melody on the B string, skipping the A
    # string so the low E can carry the bass. It is the one default four-note set that
    # reaches the low E, which is where a root actually lives, so it is what turns a
    # root bass from a consequence of the string set into a decision. Note it is *not*
    # the bottom-four block excluded by `_BOTTOM_FOUR`: it swaps the A string out for
    # the B, and its soprano is the B rather than the G.
    "drop2_6432": (((0, 2, 3, 4), 4),),
    # Drop-3 and close position span more than a hand can hold on four neighbouring
    # strings, which is why neither is in GRIP_PREFERENCE. They are given the same
    # bass-skipping sets as drop-2 because the rule is about the *shape*, not the
    # family: a bass that reaches below the block can still be fretted on a longer
    # string, and where that rescues a shape the span limit would otherwise refuse it.
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
    # descend while the string numbers ascend. Measured across 120 transcriptions it
    # adds no coverage at all - never the only shape for a melody - but it relocates
    # 1.3% of steps, always onto a better melodic position: F7 with a Db4 soprano
    # moves from `x-6-7-6-x-x` to `x-6-x-2-2-x`, the same three pitches with the
    # melody at B-string fret 2 instead of G-string fret 6. That is the whole point of
    # allowing the melody to hold its place by changing strings. It needs the search
    # in _place_shell, not stacking, for the same reason 6-4-3 does.
    #
    # (5, 3, 2) is the *other* 5-3-2: high E, G and D, skipping the B on the way up
    # rather than the D on the way down. It was added to close an asymmetry in this
    # table rather than for any grip-specific reason - counting the shell sets by
    # soprano, the high E had exactly one shape ((5,4,3)) while the B and the G had
    # two each, and the high E is the *most* used soprano because
    # MELODY_STRING_CHOICES_FULL puts it first, so every arrangement tries it before
    # the others. It is also the three-layer split a walking-bass shell wants (melody
    # on the high E, guide tones on the G and the D, leaving the 5th and 6th strings to
    # the thumb), so it earns its place twice over. Like the other non-contiguous sets
    # it needs _place_shell's search, not stacking: its D-string note can sound above
    # its G-string note, so the voices are not in descending pitch order down the
    # strings.
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
    # fret difference. Four candidates were measured against every quality and every
    # chord-tone melody in G3-Bb5 - **812** cases where the guide tone is displaced -
    # counting only those a pair can actually place:
    #
    #   (3, 1)  strings 3-5   810 recovered   <- kept
    #   (5, 2)  strings 1-4   810 recovered   <- equivalent, and wider in tuning
    #   (4, 2)  strings 2-4    31 recovered   <- rejected
    #   (5, 3)  strings 1-3   118 recovered   <- rejected
    #
    # **One pair is enough, so one pair was added.** The 2 that no combination reaches are
    # a `sus4` and a `7sus4` with G3 in the melody - the 4th is a 2nd there, and the 9th
    # that would replace it is out of reach at the bottom of the register. They return no
    # duo rather than sound a 2nd, and `tests/test_grips.py` names both.
    #
    # `(3,1)` is the narrower of the two equivalent pairs and the more idiomatic of the
    # two shapes - the 3rd string under the G - so it is the one kept. Adding the second
    # would enlarge `supported_string_sets()` by a set that reaches nothing the first does
    # not, which is what the "load-bearing" test below exists to prevent.
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
# This used to be the *melody's* degree list too, and it gated the whole family: a duo
# was generated only under a root or a 5th in the melody, on the reasoning that a 3rd or
# a 7th there "is the entire definition of the chord's function" and a bare pair under it
# sounds like a mistake. That reasoning does not survive contact with the guide-tone
# rule the duo is actually built from. A 3rd or a 7th in the melody is exactly the note
# a guide tone is there to support - the guide tone *beneath* it states the function -
# and it is the one case where the pair is unmistakably the chord rather than two passing
# notes. So the melody gate is gone; see `_duo_offsets`, which takes its second voice
# from SHELL_DEGREES and skips a unison so the fallback is never the melody itself.
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
    """
    sets = {
        frozenset(range(top - 3, top + 1))
        for top in MELODY_STRING_CHOICES_FULL
        if frozenset(range(top - 3, top + 1)) != _BOTTOM_FOUR
    }
    for shapes in GRIP_STRING_SETS.values():
        sets.update(frozenset(strings) for strings, _ in shapes)
    return sorted(sets, key=lambda s: sorted(s))


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

    Deliberately almost nothing. Two earlier versions of this were over-strict and both
    cost real voicings:

    - rejecting every interval under 3 semitones refused the chord's own 3rd whenever
      the melody sat a tone above it, which is the ordinary case for an altered chord
      (a b5 over its 3rd *is* a minor 3rd), so the guide-tone search gave up and the
      step fell back to templates that stated neither guide tone;
    - rejecting every minor 3rd then refused that same pair by a different route.

    The engine's own tables are the evidence that the strict rules were wrong: they
    contain adjacent voices a semitone and a tone apart, because a b7 under a 3rd is
    the tritone a dominant chord is named for and a b5 against a 3 is what "altered"
    means. So the only real constraint is that a voice must be a *chord tone* - checked
    by the caller - and must not duplicate one already placed at the same pitch.

    Kept as a named predicate because "no doubled pitch" is still a real requirement:
    two voices on one fret would be one note played twice, not a four-note voicing.
    """
    return any(pitch == other for other in placed)


def _guide_tones(tones: Tuple[int, ...], root_pc: Optional[int]) -> Tuple[int, ...]:
    """
    The degrees of this chord that define it: its 3rd (or 4th) and its 7th.

    Read off the tone set rather than tabulated, because it is a property of the chord
    and not of any voicing. The **major** 3rd is preferred where the set holds both
    (7alt carries b3 and 3, since it is an altered chord and either may be asked for),
    because the major one is the chord's actual identity; the b3 there is an option.

    **A suspended chord's guide tone is the 4th, not the 3rd**, and that is the case
    this originally got wrong. Dsus7 is 1 4 5 b7: it has no 3rd at all, so a lookup for
    one finds nothing and reports *no* third - where the note that defines the sus chord
    as a sus chord is exactly that 4th. Two sus voicings have to agree about which note
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
    voices on the root and the 5th and leave the 7th out - which is what the old
    fallback did, producing `4 7 b9 5` for a 5th in the melody of a 7#11: a major 3rd
    and a major 7th against a chord whose identity is 3 and b7.

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
    voicing and is not a member of any supported string set. An earlier version of this
    function got that wrong and it surfaced as single-note steps in the corpus tests.

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
    a suspended chord, with the 7th as the alternative. Re-encoding it here as a
    `(4, 3, 0)` scan is what this used to do, and it had two faults. It listed no sus
    degree at all, so `sus4`, `sus2` and `7sus4` - whose guide tone is the 4th, the 9th
    and the 4th - admitted **no duo anywhere**, and its `0` (root) fallback was
    unreachable in any case, filtered out by its own `d not in DUO_DEGREES` guard.
    Reading the shared table agrees with the old behaviour for 25 of the 28 qualities,
    supplies precisely the three that were dead, and cannot drift from the shell.

    Preference within the table is `[0]`, then `[1]`. The fallback is **load-bearing,
    not decorative**: when the melody *is* the 3rd, `[0]` would place a unison under it,
    and a measured 252 of these cases are exactly that. A unison is not a second voice,
    so the 7th takes over and the pair becomes a 6th.

    **A 2nd under the melody is dropped an octave.** When the guide tone lands within
    two semitones of the melody the shape is a 2nd, which in two voices is where they
    fight rather than agree; the same pitch class an octave lower makes it a 9th, which
    sits. This is why the duo owns two skipped-string pairs: on the adjacent pairs a
    9th is unreachable inside `GRIP_MAX_SPAN["duo"]`, so **0 of the 48 cases this
    affects** were voiceable before `GRIP_STRING_SETS` was widened. Two remain
    unreachable even now and return nothing rather than sound a 2nd;
    `tests/test_grips.py` names both.

    The melody may be **any** chord tone, not only a root or a 5th. The old
    `DUO_DEGREES` gate refused a duo under a 3rd or a 7th on the grounds that those
    notes "are the chord's function" - but a guide tone beneath them is exactly what
    states that function, and putting the guide tone first is what makes the pair read
    as the chord rather than as two passing notes. A melody that is not a chord tone at
    all never reaches here: the non-chord-tone strategies rewrite the chord before the
    generator runs, so a duo is always placed against a resolved harmony.
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
    is not cosmetic: an unranked search returns whatever comes first, which is how an
    earlier measurement concluded this grip "would never be selected".
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
    the soprano permits a span of ten, which is exactly what the 6-4-3 shell produced
    before this was caught - the low E and D strings are five semitones apart in tuning,
    so a shell that sounds correctly on them can sit at frets 8 and 0.

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

# Degree pitch classes relative to chord root (used to match soprano note to inversion).
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
    reproduces the historical behaviour for *any* top_string and so keeps
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
    three voices. That handed `drop3` and `closed` the G-string note on the G
    string, the D-string note on the D string and the B-string note on the B
    string while claiming to descend - the pitches were right and the strings were
    not, and the span check then measured frets on strings the voice was never
    meant for. Nothing noticed because neither grip generates anything at the
    default span limit. A rotation is only order-preserving if the tuple is already
    in the order being rotated *into*, and this one is stored the other way up.
    """
    if grip == "drop2":
        # A caller may pass any `top_string`, and the historical behaviour is that the
        # four strings below it are used, so a top_string with no table entry still
        # works. The table is consulted only where it has an entry - which is what adds
        # the bass-skipping sets, since they are keyed on the soprano they belong to.
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

    # Divided by the number of *sounding* fingers, not by four. The previous
    # voicing can now be a three-note shell or a two-note duo, and a shell's mean
    # fret is not one quarter of its sum - getting this wrong misreports where the
    # shape is, which is exactly what the selector compares.
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
