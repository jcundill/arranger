from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Container, List, Optional, Sequence, Tuple, Dict, Any
from musthe import Note, Chord, Interval

# Standard tuning pitches in MIDI / Pitch class equivalents
# String 6 (Low E, index 0) to String 1 (High E, index 5)
STANDARD_TUNING = [
    Note("E2"), Note("A2"), Note("D3"), 
    Note("G3"), Note("B3"), Note("E4")
]

STRING_NAMES = ["E", "A", "D", "G", "B", "E"]

# Pitch-class names, used when a substitution has to be spelled back into a chord
# name (e.g. the dim7 a semitone below a resolution target). Flats are preferred
# because that is the common jazz spelling for the chords this library builds.
PITCH_CLASS_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# The Weimar Jazz Database's "no chord" marker: a bar that carries melody but no
# harmony. Such a step is voiced as melody alone - no harmonisation, no
# reharmonisation, no warning (see VoiceLeadingEngine.get_melody_only_voicing).
NO_CHORD = "NC"

# Soprano (melody) string indices a Drop-2 voicing may be pinned to, and the four
# contiguous strings each one uses. Index 0 = low E ... index 5 = high E.
#   5 -> strings D-G-B-E, melody on the high E string (traditional shape)
#   4 -> strings A-D-G-B, melody on the B string, one position lower on the neck
MELODY_STRING_CHOICES = (5, 4)

# The full set of strings a melody may be voiced on: high E (string 1), B (string 2)
# and G (string 3). Adding the G string is what lets a melodic position be held by
# *changing strings* rather than by moving the hand up or down the neck, which is the
# whole point of the position-aware selector in VoiceLeadingEngine._best_voicing.
#
# A G-string melody only ever reaches a three-note shape, because only the D and low
# E strings lie below it - and a shell on those two is the 6-4-3 grip. The A string
# and the low E string are therefore *inner voices only*: no harmonised grip puts the
# soprano on either. The floor of the melody range consequently rises from B3 to G3
# (the open G string) while the *chord* range extends down to E2 as a bass voice.
MELODY_STRING_CHOICES_FULL = (5, 4, 3)

# The comfortable neck window. Both ends are a strong *preference*, not a filter: a
# voicing is penalised by how many of its frets fall outside, never rejected for
# falling outside. A filter would silently drop every step whose melody has no
# in-window shape, and arrange_progression already skips such a step with a warning -
# losing a chord of the tune to keep a fretboard preference would be a bad trade.
NECK_FRET_MIN = 2
NECK_FRET_MAX = 13

# Grip families, in the order that breaks an exact tie. A four-note drop-2 shape is
# listed first so it is never displaced by a shell when the two cost the same.
#
# `drop2_6432` is the 6-4-3-2 block (low E, D, G, B), listed second and after the
# contiguous blocks because it is the *alternative* rather than the default reading of
# "drop-2": `grips=("drop2",)` still means the contiguous four strings only, which is
# the idiom that reproduces the library's original output exactly. It is a separate
# family, not a third string set for `drop2`, precisely so that idiom survives.
#
# `drop3` and `closed` are generated but deliberately *not* listed here, because neither
# can be played within this library's span limit. A close-position four-note chord
# under a melody spans a seventh or more, and the four strings below the high E are only
# five semitones apart in tuning, so the frets come out more than five apart: Cmaj7 in
# close position under C5 wants frets 8, 12, 12 and 14. Drop-3 is worse, spanning a
# twelfth by construction. The generators stay, so a caller who raises GRIP_MAX_SPAN
# can reach them, but advertising them as a default would be a promise the span
# invariant cannot keep.
GRIP_PREFERENCE: Tuple[str, ...] = ("drop2", "drop2_6432", "shell", "duo")

# The maximum distance, in frets, from the soprano to any other finger. Five for every
# four-note shape and every three-note shell; a duo is only ever two fingers, so it is
# held to a tighter four.
GRIP_MAX_SPAN: Dict[str, int] = {
    "drop2": 5,
    "drop2_6432": 5,
    "drop3": 5,
    "closed": 5,
    "shell": 5,
    "duo": 4,
    # Two fingers, like a duo, so it is held to the same tighter four. An interval
    # is a texture, not a harmony, so it is never wider than a hand needs to be.
    "interval": 4,
}

# --- Metric roles and textures ---
#
# The arranging guide's method has a shape the cost tuple cannot express: a full
# chord belongs on the *principal* melody notes, and the notes in between are filled
# with something lighter. `voicing_cost` ranks completeness above position, so with
# no rhythm at all a bar of running eighths comes out as eight re-struck four-note
# chords - a chord list, not an arrangement.
#
# These two roles are the fix, and they work by changing *which grips are on the
# table* rather than by adding a term to the cost tuple. "Play fewer notes here" is
# not a preference competing against "stay in position"; it is a change of what may
# be chosen at all, and putting it in the cost would let a four-fret position
# outbid a whole texture. Generation and selection therefore stay separate exactly
# as they already are.

# A principal melody note: the chord is spelled out in full.
ROLE_TARGET = "target"
# A connecting note: a shell, an interval, or the melody alone.
ROLE_FILL = "fill"

# Texture styles, in the order that breaks a tie. `@/walking_bass.md  lets continue implementinguniform` is the historical
# behaviour - every slot is a target and the cost tuple's completeness criterion
# decides, which is why it is the default and why existing output is unchanged.
TEXTURE_STYLES: Tuple[str, ...] = ("uniform", "targets", "walking_bass")

# The beats of a bar that carry a full chord under the "targets" texture, counted
# from 1. Beats 1 and 3 are the guide's rule verbatim: in 4/4 they are the two
# half-note pulses, and they are where the harmony wants to be stated.
#
# Expressed as *beats*, not as an absolute onset, so the rule reads the metre it is
# given rather than assuming one: a 2/2 bar (two notated beats) gets beat 1 only, and
# a 3/4 bar gets 1 and 3 as it would in 4/4. A beat is a counting position, not a
# quarter note - see the cut-time notes in AGENTS.md.
TARGET_BEATS: Tuple[int, ...] = (1, 3)

# The grip families each role may use, by texture. This is the whole texture policy
# in one table, and it is read by `_roles_for_slot` and its caller.
#
# `drop3` is listed among a target's grips but generates nothing at
# GRIP_MAX_SPAN["drop3"] == 5, because drop-3 spans a twelfth by construction. That is
# where the library already stands, so listing it costs nothing and means a future
# span change takes effect without touching this code.
TEXTURE_GRIPS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "uniform": {"target": GRIP_PREFERENCE, "fill": GRIP_PREFERENCE},
    "targets": {
        "target": ("drop2", "drop3"),
        "fill": ("shell", "interval", "melody"),
    },
    # A walking bass is a *texture*, expressed in the table that already exists: a
    # shell (3rd & 7th) states the harmony on a target beat and nothing above the
    # melody sounds between them.
    #
    # The empty fill tuple is the point, not an omission: it means the left hand
    # plays **nothing** on a fill, which is why two four-note grips that would
    # collide with the thumb are never offered (drop2_6432 is the only four-note
    # grip that reaches the low E, and a shell is the only set that leaves both the
    # 6th and the 5th free under a high-E melody). `arrange_progression` resolves
    # the empty tuple through `get_melody_only_voicing` rather than through grip
    # lookup, and the same route is the fallback for a target no shell can sound -
    # `grips=("shell",)` has no second option, so without it a melody like D over
    # Bbm7 would disappear with only a warning.
    "walking_bass": {
        "target": ("shell",),
        "fill": (),
    },
}

# How close a notated beat has to be to a whole beat to count as it. A 2/2 bar's
# eighths land on 1.0, 1.5, 2.0, 2.5, and a 3/4 bar's on 1.0, 1.666..., so an exact
# comparison would call almost none of them downbeats. Measured in beats, not in
# quarters, so this is the same tolerance in any metre.
_BEAT_EPSILON = 1e-6

# --- Walking bass ---
#
# The three strings a thumb line may use: the low E, the A and the D. All three are in
# play, and which one carries a given note is decided *per note* rather than fixed.
#
# The reason is that the thumb is part of the hand. Adjacent strings are five semitones
# apart, so the same pitch sits five frets lower on each string you move up - D3 is fret
# 10 on the low E, fret 5 on the A, and the open D string itself - which puts "prefer the
# lowest string" and "stay where the hand already is" in direct opposition, always, by
# exactly five frets. A hand sitting at fret 5 plays D3 on the A string under the
# position it is already in; on the low E the same D3 is five frets of travel for an
# identical pitch.
#
# So the placement step orders by fret proximity to the upper voicing and takes the
# nearest, the same economy `voicing_cost` already applies to the upper voices. The 4th
# string is therefore used only when the hand is genuinely low, and the 6th only when the
# note is below the A string's open A2 or when the A and the D are both occupied by the
# upper shape - the two cases the upper strings cannot cover.
BASS_STRING_INDICES: Tuple[int, ...] = (0, 1, 2)

# The roles a walking-bass note may take, for annotation and tests. Plain strings rather
# than an enum, for the same reason `grip` and `role` are: the module has no `enum`
# import and pyright must stay clean.
#
# "target" is deliberately **not** reused for beat 4, because that word already means the
# *left hand's* principal note (ROLE_TARGET) and one word cannot carry both:
#
#   anchor    beat 1, or any strong beat where the harmony changes: the root, always
#   connect   beats 2 and 3: a chord tone, an extension, or passing motion
#   approach  beat 4: a half step from the next bar's anchor
#   enclosure beat 3 or 4: half step above, then half step below the next anchor
#   hold      any beat: the previous note repeated, when nothing better is reachable
BASS_ROLE_ANCHOR = "anchor"
BASS_ROLE_CONNECT = "connect"
BASS_ROLE_APPROACH = "approach"
BASS_ROLE_ENCLOSURE = "enclosure"
BASS_ROLE_HOLD = "hold"

# Every string set a grip may occupy, as (active string indices, soprano string
# index), ordered by preference. Index 0 = low E ... index 5 = high E, so the
# conventional string number is 6 - index.
#
# (0, 2, 3) is the 6-4-3 shell: low E, D and G, deliberately skipping the A string.
# It is the only non-contiguous set here, and it is the reason a G-string soprano can
# carry a full three-note shell at all - without it only the D string lies below the
# G string, which would cap a G-string melody at two voices.
GRIP_STRING_SETS: Dict[str, Tuple[Tuple[Tuple[int, ...], int], ...]] = {
    # The two traditional four-string blocks. There is deliberately no four-note block
    # for a G-string soprano: 6-5-4-3 with the melody on top does not sound good, so a
    # low melody is harmonised with a three-note shell instead - see the note below.
    #   (2, 3, 4, 5) -> strings 4-3-2-1, melody on the high E
    #   (1, 2, 3, 4) -> strings 5-4-3-2, melody on the B string
    "drop2": (((2, 3, 4, 5), 5), ((1, 2, 3, 4), 4)),
    # 6-4-3-2: low E, D, G and B with the melody on the B string, skipping the A
    # string so the low E can carry the bass. It is the one default four-note set that
    # reaches the low E, which is where a root actually lives, so it is what turns a
    # root bass from a consequence of the string set into a decision. Note it is *not*
    # the bottom-four block excluded by `_BOTTOM_FOUR`: it swaps the A string out for
    # the B, and its soprano is the B rather than the G.
    "drop2_6432": (((0, 2, 3, 4), 4),),
    "drop3": (((2, 3, 4, 5), 5), ((1, 2, 3, 4), 4)),
    "closed": (((2, 3, 4, 5), 5), ((1, 2, 3, 4), 4)),
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
    # Duos: 1-2, 2-3 and 3-4, each with the higher note carrying the melody.
    "duo": (((5, 4), 5), ((4, 3), 4), ((3, 2), 3)),
    # Intervals reuse the three adjacent pairs a duo already declares, for the same
    # physical reason: a 3rd or a 6th under the melody is two fingers on two
    # neighbouring strings, and there is nothing to gain from a wider set. What
    # differs from a duo is the *rule* that builds it, not where it sits - see
    # _interval_offsets, which is deliberately not gated on DUO_DEGREES.
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

# The only soprano degrees a duo is generated for. When the melody is the root or the
# 5th the ear supplies the missing guide tones, so two voices are enough; under a 3rd
# or a 7th they are the entire definition of the chord's function, and a bare duo
# there is the voicing that sounds wrong. This is a hard rule - get_grip_voicings
# returns nothing for any other melody - and not a cost preference, so there is no
# last-resort escape hatch.
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

# The neck position above which the melody is transposed down an octave and voiced on
# the B string instead of up at the top of the high E string. The B string is five
# semitones below the high E, so the same written pitch sits five frets *higher* on it
# (D5 is fret 10 on the high E, fret 15 on the B) - the only way to bring a high melody
# down the neck is to drop it an octave and let the B string play it an octave lower.
# A voicing whose soprano is above this fret is therefore re-voiced an octave down.
HIGH_FRET_LIMIT = 13

# Library version. Kept here as the single source of truth; pyproject.toml reads
# it via [tool.setuptools.dynamic] instead of duplicating the number.
# 0.4.0 added the optional Weimar Jazz Database corpus integration (wjazzd.py).
# 0.5.0 added MusicXML export (tabxml.py), behind the optional `xml` extra.
# 0.7.0 gave the engine metric and textural awareness (TEXTURE_STYLES).
# 0.8.0 added 6-4-3-2 (grip `drop2_6432`) and a root-or-5th bass tie-break, so the
# lowest voice can be a root by decision rather than by string-set accident.
# 0.9.0 adds the walking-bass texture: a thumb line on the bass strings under a light
# left hand. The types land first and are inert until the texture is wired up.
__version__ = "0.9.0"


def _metric_weight(
    bar: Optional[int], beat: Optional[float], beats_per_bar: int = 4
) -> int:
    """
    How metrically strong a slot is: 2 on beat 1, 1 on beat 3, 0 on any other beat.

    Returns **-1 when there is no timing at all** (`bar` or `beat` is None), which is
    the load-bearing part. A caller that does not know where its notes fall has not
    told us the note is weak - it has told us nothing - and treating those two the
    same would thin out every hand-written progression and every existing test. The
    -1 is what keeps the default behaviour byte-identical.

    `beats_per_bar` is honoured rather than assumed, because a count without a
    denominator is not a metre. TARGET_BEATS names *beats*, so in 2/2 (two notated
    beats) beat 3 does not exist and only the downbeat is a target; in 3/4 beats 1
    and 3 are targets exactly as they are in 4/4. This is the same reasoning the
    MusicXML importer needed when it discovered 2/2 is not 2/4.

    A beat is compared with `_BEAT_EPSILON` because a notated beat is a float: a
    3/4 bar's second beat is 1.666..., and an exact comparison would call almost no
    real note a downbeat.
    """
    if bar is None or beat is None:
        return -1
    for index, target in enumerate(TARGET_BEATS):
        if target > beats_per_bar:
            # Beyond the end of the bar: a 2/2 signature has two beats, so beat 3
            # does not exist. Compared as a beat number, not as a position in the
            # tuple, or a 2/2 bar would inherit 4/4's second target.
            break
        if abs(float(beat) - target) <= _BEAT_EPSILON:
            return 2 - index
    return 0


@dataclass
class BassNote:
    """
    One walked beat of a bass line: where it falls, what note it is, and why.

    The note is a **pitch class**, not a pitch, and that is load-bearing rather than
    a simplification. This pass runs before the melody loop, so before any upper
    voicing exists, and neither the octave nor the string can be known then: a
    descending C4-B3-A3-G3 under a held Dm7 is a beautiful walk and completely
    unplayable under a shell at fret 5, because C4 is fret 15 on the 5th string.
    The same line an octave down is not. Only the placement step, which can see
    `hand_fret`, resolves the octave and the string together.

    This is the split the library already draws for the melody: the pitch is
    musical, the string and the position are physical, and they are not decided in
    the same place.

    One entry per **walked beat**, not per melody slot - the bass grid is finer than
    the melody grid, which is what lets a held whole note sound one melody note over
    four thumb notes.
    """

    bar: Optional[int]
    beat: Optional[float]
    # Pitch class 0-11. The octave and the string are the placement step's business.
    pitch_class: int
    # One of the BASS_ROLE_* constants: what this note is *for*.
    role: str


def _bass_harmony(
    root: Optional[str], quality: str
) -> Optional[Tuple[int, Tuple[int, ...]]]:
    """
    A chord's bass-relevant facts: its root's pitch class, and every pitch class a
    thumb may play under it without leaving the chord's vocabulary.

    The permitted set is the chord's own tones **plus** the extensions this quality's
    `NON_CHORD_TONE_EXTENSIONS` row can name - not purity. Two thirds of the notes in
    a textbook walk are not chord tones of the chord they sit under, and a
    purity-first rule returns the arpeggio the arranging guide explicitly warns
    against ("pure arpeggios can sound like exercise drills"). Reaching for the
    extension table rather than a scale is also what keeps the "no key model" claim
    true: strip the extensions out and diatonic movement becomes unreachable, at
    which point a key model really would be necessary.

    Returns **None** for a chord this library cannot speak - an unparseable root, or
    a quality with no tone table. Never a guess, the same rule
    `WEIMAR_QUALITY_ALIASES` and `MUSICXML_KIND_QUALITIES` already follow; a walk
    that invents a harmony under the thumb is worse than no walk at all.
    """
    canonical = ChordParser.canonical_quality(quality)
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical, ())
    if not root or not tones:
        return None
    try:
        root_pc = Note(f"{root}4").midi_note() % 12
    except (KeyError, ValueError, TypeError):
        return None
    extensions = VoiceLeadingEngine.NON_CHORD_TONE_EXTENSIONS.get(canonical, {})
    permitted = {(root_pc + degree) % 12 for degree in tones}
    permitted.update((root_pc + degree) % 12 for degree in extensions)
    return root_pc, tuple(sorted(permitted))


def _bass_distance(first: int, second: int) -> int:
    """How far apart two pitch classes are, in semitones, the short way round."""
    return min((first - second) % 12, (second - first) % 12)


def _roles_for_slot(
    weight: int,
    texture: str,
    harmony_changed: bool = True,
    melody_moves: bool = False,
) -> List[str]:
    """
    The metric roles a slot of the given weight may take under `texture`.

    This is the whole texture policy in one function, so changing the target-note
    rule is a change here and not a change spread through the selector:

      - an unknown texture is a programming error and raises, rather than silently
        arranging as `uniform`;
      - `uniform` makes every slot a target, which is the historical behaviour and
        the reason `arrange_progression` is unchanged unless a caller opts in;
      - a weight below zero means no timing was supplied, so the slot is a target;
      - a strong beat is a target and any other beat is a fill.

    Raises ValueError for an unknown texture, checked before any voicing work so a
    typo cannot cost a caller a full arrangement before it is reported.

    `harmony_changed` and `melody_moves` are the walking bass's extra condition and
    are defaulted to the values that leave every other texture untouched. Under
    `walking_bass` a slot is a target only when it is metrically strong **and**
    something new happens there: the harmony differs from the previous target's, or
    the melody moves onto it. The first half is the off-beat-change rule - a chord
    arriving on beat 4-and is voiced under the *new* chord by the harmony timeline,
    but is left as a fill, because a passing slot is exactly where the non-chord-tone
    strategies would rewrite the harmony. The second half is decision F: under
    `targets` the second bar of a two-bar chord is a fill, so a player who re-articulates
    the melody on that downbeat gets no chord under it. `TARGET_BEATS` alone cannot say
    either of those things, which is why the extra test lives here rather than in
    `_metric_weight`.

    Both arguments are ignored by every other texture, so `uniform` and `targets`
    stay byte-identical.
    """
    table = TEXTURE_GRIPS.get(texture)
    if table is None:
        raise ValueError(
            f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
        )
    if texture == "uniform" or weight < 0:
        # Historical behaviour, and "we were never told where this note falls".
        return [ROLE_TARGET]
    if texture == "walking_bass":
        # `weight > 0` is kept *inside* the conjunction, and that is the off-beat
        # change rule rather than a detail of it. A chord arriving on the 4-and is
        # voiced under the new chord by the harmony timeline - which axis says what is
        # harmonised is not this function's business - but it must not be a *target*:
        # off-beat slots are exactly where the melody is a passing tone, and a shell
        # there goes through the non-chord-tone strategies, which on a weak beat under
        # a note that was only passing through is mud rather than colour. The texture
        # would get busier precisely where it is meant to get lighter.
        #
        # So a target is a **strong** beat with something new on it: a harmony not yet
        # stated (the mid-bar change, decision E) or a melody that moves onto it
        # (decision F, which is what lets the second bar of a two-bar chord restate
        # its shell when the player re-articulates the line and stay thin when they do
        # not). Everything else is a fill, and a fill is the melody alone.
        #
        # Checked before `uniform`'s catch-all below so no later branch can return
        # TARGET first; `uniform` itself never reaches here.
        if weight > 0 and (harmony_changed or melody_moves):
            return [ROLE_TARGET]
        return [ROLE_FILL]
    if weight > 0:
        return [ROLE_TARGET]
    return [ROLE_FILL]


def bass_cost(
    pitch_class: int,
    role: str,
    previous_pc: Optional[int],
    next_anchor_pc: Optional[int],
    root_pc: Optional[int],
    permitted_pcs: Tuple[int, ...],
) -> Tuple[int, ...]:
    """
    The selection rule for one walking-bass candidate, as one comparable tuple.

    Lexicographic, never a weighted sum, matching the house rule `voicing_cost`
    states why it must be - and **role-conditional**, so the tuple is built per role
    rather than shared. That is the substantive rule here: being outside the chord is
    a *hard filter* for the anchor and a mere tie-break for a connective note, and no
    single ordering of criteria can say both at once.

      anchor    not-the-root. A hard filter, not a preference: the lowest voice
                defines the chord, which is the argument `BASS_DEGREES_6432` already
                makes for a 6-4-3-2 shape.
      approach  how far the note is from the next anchor, then motion from the
                previous note. A half step outranks a fourth below / fifth above.
      connect   out of the permitted set, then motion from the previous note, then a
                preference for stepwise motion
      enclosure as `connect`, for the note a half step *above* the next anchor
      hold      always last: the previous note, when nothing better is reachable

    The role rank comes first, which is what makes `hold` genuinely last rather than
    a peer of the alternatives.

    Note what is **not** in any of these: anything about the hand, the octave or the
    string. All three are physical, all three are decided in the placement step, and
    none of them is knowable here. An earlier draft of the design carried a
    "distance from the ideal octave of the previous note" term in exactly this tuple,
    which quietly re-decided the octave in the wrong place - a descending line would
    have committed to C4 before anything knew the hand was at fret 5.
    """
    motion = 0 if previous_pc is None else _bass_distance(pitch_class, previous_pc)
    out_of_chord = 0 if pitch_class in permitted_pcs else 1

    if role == BASS_ROLE_ANCHOR:
        return (0, 0 if pitch_class == root_pc else 1, 0, 0, 0, pitch_class)

    if role == BASS_ROLE_APPROACH:
        if next_anchor_pc is None:
            reach = 2
        else:
            interval = _bass_distance(pitch_class, next_anchor_pc)
            reach = 0 if interval == 1 else (1 if interval == 5 else 2)
        # `motion == 0` is penalised for the same reason it is on a connect: a
        # beat-4 note that merely repeats beat 3 has not approached anything, and
        # an enclosure whose two halves are the same pitch is not an enclosure.
        return (0, reach, 1 if motion == 0 else 0, motion, out_of_chord, 0, pitch_class)

    if role == BASS_ROLE_ENCLOSURE:
        # Ranked with the approach rather than the connects, because it is a
        # *deliberate* shape: the beat above the next anchor, to be answered by the
        # half step below it. It is only ever offered on the beat before an
        # approach, so ranking it with the connects would mean it was reachable
        # only by accident.
        return (0, out_of_chord, motion, 0, 0, pitch_class)

    if role == BASS_ROLE_HOLD:
        return (2, 0, 0, 0, 0, pitch_class)

    # connect. Three elements here are what make a walk a walk. `motion == 0` is
    # ranked ahead of everything, so a bar of four beats under one chord comes out a
    # line rather than a held note - without it, zero motion would win on every beat.
    # Motion itself is the *first* musical criterion, which is what makes being
    # outside the permitted set a tie-break rather than a veto: the design is
    # explicit that "out-of-chord tones" is not the first criterion of this role, and
    # ranking it first would make the chromatic-approach candidates dead code - they
    # could never beat a chord tone at any distance. And on a tie in distance the
    # line prefers to *rise*, because a walk ascends towards its next anchor; without
    # it a bar under a single chord oscillates between two chord tones (D-C-D-C),
    # which is a held figure wearing a walk's clothes.
    return (1, 1 if motion == 0 else 0, motion, out_of_chord,
            0 if motion <= 2 else 1,
            0 if previous_pc is not None and pitch_class > previous_pc else 1,
            0, pitch_class)


def _previous_bass(arrangements: List[ArrangementStep]) -> Optional[int]:
    """
    The most recent thumb note placed, or None at the head of the phrase.

    Scans backwards for the first step that actually carries a bass rather than the
    first that was *offered* one: the two differ as soon as a walk note cannot be
    placed, and continuing from a note that never sounded would drag the line towards
    an octave it was not in.
    """
    for step in reversed(arrangements):
        if step.bass is not None:
            return step.bass
    return None


def _place_bass(
    upper: Voicing, pitch_class: int, previous_bass: Optional[int] = None
) -> Optional[Tuple[int, int, int]]:
    """
    Resolves one thumb note's octave and string against an upper voicing.

    Returns `(midi, string_index, fret)`, or None when no candidate survives. The
    pure pass returned a pitch *class* because neither the octave nor the string can
    be decided before the upper shape exists; this is where they are decided, together
    and in that order, because a note an octave away is a different fret on every
    string.

    The rule is proximity, not string order. The thumb is part of the hand, and
    adjacent strings are five semitones apart, so "play the lowest string" and "stay
    where the fingers already are" differ by exactly five frets on every note. A hand
    at fret 5 plays D3 on the A string under itself; on the low E the same D3 is fret
    10 and the hand moves for an identical pitch. So the survivors are ranked by
    `abs(fret - hand_fret)` and the nearest wins.

    `hand_fret` is the upper voicing's **lowest active fret**, not `avg_fret` and not
    `top_fret`. That is the measured choice: over the plan's own worked example,
    measuring to the lowest active fret matches 26 of the 28 readable bass notes
    against 24 for the average, because a shell's low voice is the note the thumb is
    trying to join. `avg_fret` and `top_fret` agree with each other on every one of
    those notes, so neither is contradicted by the evidence - the average is simply
    dragged up by the melody, which is up an octave from the position the hand is in.

    Two filters are **not** tie-breaks, because each rejects candidates that would be
    wrong rather than merely further away:

    - the string must not already sound in the upper voicing;
    - the note must sound below it. This is required rather than preferred because
      the tuning is not monotonic in the useful direction - the A string is five
      semitones *above* the D string it may neighbour, and a 5-3-2 shell's A-string
      note can sound below its G-string note - so a candidate can be reachable, can
      be at the hand, and still belong above the chord it is meant to support.

    Reach (`0..18`) is a third, separate test: `note_to_fret` returning a fret says
    the pitch is playable and says nothing at all about where it lands.

    With no survivor the caller leaves the step without a bass and reports it, which
    is the "penalty, never a filter" argument the neck window already makes: a step
    is never dropped because the thumb could not reach it.
    """
    upper_midis = upper.midi_notes()
    if not upper_midis:
        return None
    lowest_upper = min(upper_midis)
    active = upper.active_frets()
    if not active:
        return None
    hand_fret = float(min(active))

    best: Optional[Tuple[Tuple[float, int, int], Tuple[int, int, int]]] = None
    for string_index in BASS_STRING_INDICES:
        if 0 <= string_index < len(upper.frets) and upper.frets[string_index] >= 0:
            continue  # the upper shape already speaks on this string
        open_midi = STANDARD_TUNING[string_index].midi_note()
        # Every fret on this string that sounds the wanted pitch class: the class
        # recurs every octave, so the candidates are a fixed offset plus twelves.
        first = (pitch_class - open_midi) % 12
        for fret in range(first, 19, 12):
            midi = open_midi + fret
            if midi >= lowest_upper:
                continue  # the thumb must sound below the structure it supports
            # Nearest the hand first; then continuity with the previous thumb note,
            # so a line does not leap octaves for no reason; then the lower pitch.
            key = (
                abs(float(fret) - hand_fret),
                0 if previous_bass is None or abs(midi - previous_bass) <= 4 else 1,
                midi,
            )
            candidate = (key, (midi, string_index, fret))
            if best is None or candidate[0] < best[0]:
                best = candidate
    return None if best is None else best[1]


@dataclass
class _Slot:
    """
    One entry of the slot list `arrange_progression` actually loops over.

    For `uniform` and `targets` this is exactly one slot per progression triple and
    the three timing fields are read off `timings` with the guard the corpus loader
    already applies. It exists as a type rather than a tuple because under
    `walking_bass` the list is the **union** of the melody slots and the walked
    beats, so an entry can name a progression index that is not its own position -
    which is the price of decision B, and the reason the union has to be built
    *before* the melody loop rather than spliced into its output.

    `bass_only` marks the entries the walk invented: they carry the previous melody
    pitch (so `index` points at it) and exist so the thumb has a beat to sound on.
    """

    # Which progression triple this slot's melody and harmony come from.
    index: int
    bar: Optional[int] = None
    beat: Optional[float] = None
    duration: Optional[float] = None
    # The walked beat landing on this slot, if any.
    bass: Optional[BassNote] = None
    # True when the slot exists only for the thumb and nothing above it strikes.
    bass_only: bool = False


def _bass_slots(
    progression: List[Tuple[str, str, str]],
    timings: Optional[List[Tuple[int, float, Optional[float]]]],
    bass_line: List[BassNote],
) -> List[_Slot]:
    """
    The union of the melody grid and the walked beats, as one ordered slot list.

    Decision B: the bass grid may be **finer** than the melody grid, because a bar
    whose melody is a single whole note still has four beats to walk. Every walked
    beat that has no melody slot becomes an extra slot carrying the previous melody
    pitch, marked `bass_only` - the renderer holds the upper voices across it and
    strikes only the thumb.

    Two properties are load-bearing and both are about ordering:

    - the union is built **before** the melody loop, so the loop's index still means
      what it meant - `arrange_head`'s timings guard and `arrange_slots`' retry index
      index into the skeleton, not into the result;
    - an extra slot's `index` is the *previous* melody slot, so the melody it carries
      is the one actually sounding, and the harmonic timeline the walk reads is
      unchanged by the union itself.

    With no usable timing there is no beat grid to union against, and the gridless
    degradation stands: one thumb note per anchor, one per slot. That is the
    documented `timings=None` case, not a failure.
    """
    located: List[Tuple[int, int, float, Optional[float]]] = []
    for index in range(len(progression)):
        timing = timings[index] if timings is not None and index < len(timings) else None
        if timing is None:
            continue
        bar, beat, duration = timing
        located.append((index, bar, beat, duration))

    if not located:
        # Gridless: one note per slot, attached by position and guarded, because the
        # bass line can be shorter than the progression when a chord is unparseable.
        slots: List[_Slot] = []
        for index in range(len(progression)):
            slots.append(_Slot(
                index=index,
                bass=bass_line[index] if index < len(bass_line) else None,
            ))
        return slots

    melody_at: Dict[Tuple[int, float], Tuple[int, Optional[float]]] = {
        (bar, float(beat)): (index, duration) for index, bar, beat, duration in located
    }

    entries: List[Tuple[Tuple[int, float], int, Optional[BassNote], bool]] = []
    for index, bar, beat, _duration in located:
        key = (bar, float(beat))
        bass = next((note for note in bass_line
                     if note.bar == bar and note.beat is not None
                     and abs(note.beat - float(beat)) <= _BEAT_EPSILON), None)
        entries.append((key, index, bass, False))

    # The walked beats with no melody slot. Ordered by onset, and each takes the
    # melody slot in force before it - which is why the nearest preceding slot is
    # found rather than "the previous index".
    previous_melody = -1
    for note in bass_line:
        if note.bar is None or note.beat is None:
            continue
        key = (note.bar, float(note.beat))
        if key in melody_at:
            previous_melody = melody_at[key][0]
            continue
        entries.append((key, previous_melody if previous_melody >= 0 else 0, note, True))

    # Sort by onset, with a melody slot ahead of a bass-only slot on the same onset
    # so the step that strikes the melody is the step that carries that walk note.
    entries.sort(key=lambda entry: (entry[0][0], entry[0][1], entry[3], entry[1]))

    slots = []
    for key, index, bass, bass_only in entries:
        duration = melody_at.get(key, (index, None))[1]
        slots.append(_Slot(
            index=index,
            bar=key[0],
            beat=key[1],
            duration=duration,
            bass=bass,
            bass_only=bass_only,
        ))
    return slots


def _walking_bass_line(
    chords: List[Tuple[Optional[str], str, str]],
    onsets: Optional[List[Optional[Tuple[int, float]]]],
    beats_per_bar: int = 4,
) -> List[BassNote]:
    """
    The bass line for a progression: one `BassNote` per **walked beat**.

    A pure, phrase-level pass. It reads harmony and timing only, never the melody
    pitches, because *what note to play* is a harmonic question and *where to play
    it* is a physical one - and only the second depends on the upper voicing, which
    does not exist yet at this point in the pipeline.

    The governing rule: **beat 1 is the anchor, the last beat is the target.** A
    walking line does two jobs, marking time and bridging one chord to the next, and
    they fall on predictable beats:

      anchor    the current chord's root, on every downbeat *and* on any strong beat
                where the harmony changes - bar 10's mid-bar `Eb7` gets its root
                there, on the same slot where the left hand states the chord
      connect   the beats in between: a chord tone, a nameable extension, or a
                chromatic approach
      approach  the last beat of the bar, chosen **backwards** from the next anchor.
                This is the strongest argument for the pass being phrase-level: beat
                4 is defined by a note that has not happened yet, so it cannot be
                generated per step.
      enclosure the beat before an approach, a half step above the next anchor
      hold      the previous note, when nothing else is reachable

    A chord lasting two bars is re-anchored on the second downbeat, because the
    anchor is a **metric** event, not a harmonic one: re-striking the root is what
    marks the bar, and suppressing it would leave that bar unmarked. An earlier draft
    of the design held the opposite, and was wrong.

    `onsets=None` - `timings=None`, or a `chords` skeleton - means there is no beat
    grid, so there is nothing to walk four quarters across. It degrades to one note
    per slot, every slot an anchor, rather than failing. This is documented rather
    than silent because it is the path every hand-written progression takes.
    """
    if not chords:
        return []

    located = (
        [
            (onset[0], onset[1], index)
            for index, onset in enumerate(onsets)
            if onset is not None
        ]
        if onsets is not None
        else []
    )

    if not located:
        # No beat grid: one note per slot, and every slot is an anchor.
        notes: List[BassNote] = []
        for root, quality, _name in chords:
            harmony = _bass_harmony(root, quality)
            if harmony is None:
                continue
            notes.append(BassNote(None, None, harmony[0], BASS_ROLE_ANCHOR))
        return notes

    # One walked beat per quarter of every bar the melody touches. Signed bars sort
    # correctly, and a bar whose melody is a single whole note still yields four
    # notes - the grid, not the melody, is what the line is written on.
    bars = sorted({bar for bar, _beat, _index in located})
    walked: List[Tuple[int, float]] = [
        (bar, float(beat)) for bar in bars for beat in range(1, beats_per_bar + 1)
    ]

    # The harmony in force at each walked beat, by forward fill on the (bar, beat)
    # tuple - the same rule the corpus loader and the MusicXML importer apply, and
    # the same one the left hand reads. An `NC` bar continues the last known harmony
    # rather than being given a guessed one, and a bar with no harmony behind it yet
    # gets no notes at all.
    onsets_sorted = sorted(located)
    harmonies: List[Optional[Tuple[int, Tuple[int, ...]]]] = []
    keys: List[Optional[Tuple[Optional[str], Optional[str]]]] = []
    cursor = 0
    carried: Optional[Tuple[int, Tuple[int, ...]]] = None
    carried_key: Optional[Tuple[Optional[str], Optional[str]]] = None
    for bar, beat in walked:
        while (
            cursor < len(onsets_sorted)
            and (onsets_sorted[cursor][0], onsets_sorted[cursor][1]) <= (bar, beat)
        ):
            root, quality, _name = chords[min(onsets_sorted[cursor][2], len(chords) - 1)]
            parsed = _bass_harmony(root, quality)
            if parsed is not None:
                carried = parsed
                carried_key = normalised_harmony(f"{root}{quality}")
            # Otherwise the slot is NC or unspeakable, and `carried` holds unchanged.
            cursor += 1
        harmonies.append(carried)
        keys.append(carried_key)

    # An anchor is every downbeat, plus any strong beat whose harmony is not already
    # stated. The second clause is the mid-bar change, and it is the *same* predicate
    # `_roles_for_slot` already applies to the left hand - strong beat, and a harmony
    # differing from the previous target's - so the thumb and the fingers fire on one
    # slot by construction rather than by a second mechanism kept in step by hand.
    is_anchor: List[bool] = []
    previous_anchor: Optional[Tuple[Optional[str], Optional[str]]] = None
    for index, (bar, beat) in enumerate(walked):
        if harmonies[index] is None:
            is_anchor.append(False)
            continue
        strong = _metric_weight(bar, beat, beats_per_bar) > 0
        downbeat = abs(beat - 1.0) <= _BEAT_EPSILON
        anchor = downbeat or (strong and keys[index] != previous_anchor)
        is_anchor.append(anchor)
        if anchor:
            previous_anchor = keys[index]

    # The next anchor after each walked beat, which is what `approach` and
    # `enclosure` are chosen *against*. This backwards scan is the lookahead.
    next_anchor: List[Optional[int]] = [None] * len(walked)
    upcoming: Optional[int] = None
    for index in range(len(walked) - 1, -1, -1):
        next_anchor[index] = upcoming
        harmony = harmonies[index]
        if is_anchor[index] and harmony is not None:
            upcoming = harmony[0]

    # One note per walked beat, with the previous note carried forward so the cost
    # can measure motion. `previous_pc` is the only state the pass keeps, which is
    # what makes a single forward pass enough: the lookahead is already resolved
    # above, into `next_anchor`.
    notes = []
    previous_pc: Optional[int] = None
    for index, (bar, beat) in enumerate(walked):
        harmony = harmonies[index]
        if harmony is None:
            # No harmony has sounded yet: nothing to anchor and nothing to walk
            # under. Skipping rather than guessing is the rule this module keeps
            # everywhere else.
            continue
        root_pc, permitted = harmony
        anchor_pc = next_anchor[index]
        if is_anchor[index]:
            notes.append(BassNote(bar, beat, root_pc, BASS_ROLE_ANCHOR))
            previous_pc = root_pc
            continue

        is_last_beat = abs(beat - beats_per_bar) <= _BEAT_EPSILON
        is_penultimate = abs(beat - (beats_per_bar - 1)) <= _BEAT_EPSILON

        candidates: List[Tuple[int, str]] = [
            (pitch_class, BASS_ROLE_CONNECT) for pitch_class in permitted
        ]
        if previous_pc is not None:
            candidates.append((previous_pc, BASS_ROLE_HOLD))
        if anchor_pc is not None:
            # A chromatic approach to the next root. This is how a connective note
            # reaches a pitch that is neither a chord tone nor a nameable extension,
            # and it is a large part of why the walk needs no key model: the
            # "diatonic" movement of a real line (G-A-Bb) is extensions of the chord
            # it sits under, and the one genuinely chromatic note is exactly this.
            candidates.append(((anchor_pc + 1) % 12, BASS_ROLE_CONNECT))
            candidates.append(((anchor_pc - 1) % 12, BASS_ROLE_CONNECT))
            candidates.append(((anchor_pc + 7) % 12, BASS_ROLE_CONNECT))
            if is_last_beat:
                # The approach role is offered the half step above, the half step
                # below and the fourth below / fifth above, and `bass_cost` ranks a
                # half step first. Nothing here decides the note; the cost does, so
                # the same rule holds whichever chord is on either side.
                candidates.append(((anchor_pc + 1) % 12, BASS_ROLE_APPROACH))
                candidates.append(((anchor_pc - 1) % 12, BASS_ROLE_APPROACH))
                candidates.append(((anchor_pc + 7) % 12, BASS_ROLE_APPROACH))
            elif is_penultimate:
                # Half step above the next anchor, so the beat after it can take the
                # half step below: the simplest form of an enclosure, and the only
                # one in scope.
                candidates.append(((anchor_pc + 1) % 12, BASS_ROLE_ENCLOSURE))

        best_pc, best_role = min(
            candidates,
            key=lambda candidate: bass_cost(
                candidate[0], candidate[1], previous_pc, anchor_pc, root_pc, permitted
            ),
        )
        notes.append(BassNote(bar, beat, best_pc, best_role))
        previous_pc = best_pc

    return notes


@dataclass
class Voicing:
    """Represents a specific fretboard voicing."""
    frets: List[int]
    top_fret: int
    avg_fret: float
    # Which grip family produced this shape, one of GRIP_PREFERENCE. Purely
    # informational - nothing about playability or rendering depends on it - but it is
    # how a caller (and the tests) can tell a four-note drop-2 from a three-note shell.
    # Defaulted, so existing construction and the __getitem__ shim are unaffected.
    grip: str = "drop2"
    # The pitch class of the lowest sounding voice, or None for an all-muted shape.
    # Cached so the corpus slash-bass rule (wjazzd.bass_cost) does not have to
    # re-derive it, and so a caller can ask "what is the bass of this grip" directly.
    bass_pc: Optional[int] = None
    # Which metric role produced this shape, mirroring ArrangementStep.role: ROLE_TARGET
    # for a shape that is meant to state the chord, ROLE_FILL for one that is only
    # connecting. Set by whichever generator produced the shape, so a caller
    # inspecting a candidate directly - rather than a chosen step - can still tell.
    # Defaulted, so every existing construction and the __getitem__ shim are
    # unaffected. A plain string rather than an enum, for the same reason `grip` is.
    role: str = ROLE_TARGET
    # A walking-bass thumb note merged into the fret vector, and the string carrying it.
    # Set **only after** `_best_voicing` has chosen the upper shape, never as a
    # candidate: `voicing_cost`'s `missing = 4 - len(active)` counts the voices that
    # sound, and a merged fifth voice would corrupt it. Selecting first and merging
    # after is what keeps the bass out of the cost tuple by construction rather than by
    # discipline.
    #
    # `bass_string` is recorded rather than assumed to be the low E, because the string
    # is chosen per note by proximity to the hand and the thumb genuinely moves between
    # strings as the left hand moves up the neck. `tabstaff` reads it to exclude the
    # bass from its hold comparison, and any renderer that wants to know which voice is
    # the thumb reads it here rather than guessing index 0.
    bass_midi: Optional[int] = None
    bass_string: Optional[int] = None

    def tab_string(self) -> str:
        """Returns standard tab representation, e.g. 'x-x-12-13-13-13'."""
        return "-".join(str(f) if f >= 0 else "x" for f in self.frets)

    def tab_block(self) -> List[str]:
        """
        Renders the voicing as a six-line vertical tab, highest string first.

        Each line is labelled with the string name and holds the fret cell for
        that string, right-aligned to two characters so frets 0-9, 10-18 and
        the muted 'x' all line up in a column:

            e|--0---3---|
            B|--1---3---|
            G|--0---2---|
            D|--3---3---|
            A|-x-------|
            E|-x-------|

        Returns exactly six lines, one per string, ordered high E (string 1)
        down to low E (string 6) the way tab is read. A fully muted voicing
        renders as six 'x' lines rather than raising. Purely a render: it
        prints nothing, so callers decide how to display it.
        """
        return _tab_block_from_cells(_cells_from_frets(self.frets))

    def tab(self) -> str:
        """Returns tab_block() as a single newline-joined string."""
        return "\n".join(self.tab_block())

    def upper_midi_notes(self) -> List[int]:
        """
        Every sounding pitch except the walking-bass thumb note.

        The comparison both renderers use to decide hold-versus-strike reads this
        rather than `midi_notes()`, because a walking line changes the lowest pitch
        on every quarter: comparing the full set would break the hold chain
        permanently and destroy the "held shape, not a chord list" behaviour for the
        whole arrangement. Excluding the thumb is what lets a `bass_only` step read
        as a *held* upper shape with a moving thumb.

        The exclusion is by the **recorded string**, not by pitch or by a constant
        index, because the thumb is placed per note and genuinely moves between the
        6th, 5th and 4th strings. A step with no bass is unchanged.
        """
        if self.bass_midi is None or self.bass_string is None:
            return self.midi_notes()
        bass_string = self.bass_string
        # Filtered by string index, never by position in a filtered list: the two are
        # different things, and comparing a string number against a list offset drops
        # whichever voice happens to come first.
        return [
            midi
            for index, midi in enumerate(
                GuitarFretboard.fret_to_midi(index, fret)
                for index, fret in enumerate(self.frets)
                if fret >= 0
            )
            if index != bass_string
        ]

    def active_frets(self) -> List[int]:
        """Returns list of fret positions for played strings."""
        return [f for f in self.frets if f >= 0]

    def fret_span(self) -> int:
        """Returns the physical fret span between lowest and highest active fret."""
        active = self.active_frets()
        if not active:
            return 0
        return max(active) - min(active)

    def midi_notes(self) -> List[int]:
        """Calculates MIDI pitches played on each active string."""
        midis = []
        for s_idx, f in enumerate(self.frets):
            if f >= 0:
                midis.append(GuitarFretboard.fret_to_midi(s_idx, f))
        return midis

    def pitch_classes(self) -> List[int]:
        """Calculates pitch classes (0-11) of the active notes."""
        return [m % 12 for m in self.midi_notes()]

    def soprano_string(self) -> int:
        """
        Returns the index of the highest sounding string (0 = low E ... 5 = high E).

        This is the **index** used everywhere else in this module; the conventional
        guitar string number is 6 - index (index 5 = string 1 = high E, index 4 =
        string 2 = B). Returns -1 when every string is muted.
        """
        active = [s_idx for s_idx, f in enumerate(self.frets) if f >= 0]
        return max(active) if active else -1

    @property
    def active_strings(self) -> List[int]:
        """
        The indices of the strings that sound, in ascending (low to high) order.

        This is the shape of the grip: two to four strings, all of them from one
        GRIP_STRING_SETS entry. It is what a caller checks when it wants to know
        whether a voicing really is the shape it claims to be.
        """
        return [s_idx for s_idx, f in enumerate(self.frets) if f >= 0]

    @property
    def fret_on_soprano(self) -> int:
        """
        The fret under the highest sounding string, or -1 when all strings are muted.

        Compared against another voicing's this measures *neck position*, which is the
        thing a player has to travel: fret numbers mean the same place on the neck
        whichever string they are on, so this stays meaningful when a melody holds its
        place by moving to a different string.
        """
        soprano = self.soprano_string()
        return -1 if soprano < 0 else self.frets[soprano]

    # Backward compatibility: dictionary-like indexing step["voicing"]["frets"]
    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)


@dataclass
class ArrangementStep:
    """Represents one chord-melody step in an arranged progression."""
    chord: str
    melody: str
    voicing: Voicing
    # Non-chord-tone bookkeeping, filled in by arrange_progression. Defaults keep
    # the dataclass and its dict-style shim backward compatible.
    non_chord_tone: bool = False
    strategy: Optional[str] = None
    harmonized_as: Optional[str] = None
    # True for a step that was arranged melody-only because its chord slot was
    # NO_CHORD. Defaulted, so existing construction and the __getitem__ shim are
    # unaffected. A melody-only step is deliberately NOT a drop-2 voicing: it has
    # a single active fret and does not obey the four-string playability invariant.
    melody_only: bool = False
    # The melody as written, when the step was transposed down an octave to keep the
    # voicing below HIGH_FRET_LIMIT (see VoiceLeadingEngine.get_octave_down_candidates).
    # In that case `melody` holds the transposed note that actually sounds and this
    # holds the pitch the progression asked for, so the renderer can show both.
    # Defaulted to None, so an ordinary step is unaffected.
    original_melody: Optional[str] = None
    # Optional timing, in the same units the Weimar Jazz Database uses: `bar` is
    # signed (pickups are negative), `beat` is the beat *within* the bar, and
    # `duration` is in whole notes. All three default to None so plain
    # construction and the __getitem__ shim are unaffected, and so a progression
    # written by hand simply has no rhythm to render. When they are present the
    # staff renderer can space the chords on their real beats instead of one per
    # cell; when they are absent it falls back to a uniform grid.
    bar: Optional[int] = None
    beat: Optional[float] = None
    duration: Optional[float] = None
    # True when this step's melody sounds the same pitch as the step before it. The
    # step is then played as a *single note*: only the soprano string is struck and
    # the rest are muted, the way a player reads a held melody rather than re-fingering
    # the chord. The voicing is still generated in full - the engine needs a real shape
    # to voice lead from, and `tab_line()` returns it for a caller who wants it.
    # Defaulted to False, so an ordinary step and every existing construction are
    # unaffected. See VoiceLeadingEngine.arrange_progression, which sets it.
    #
    # Note the consequence across a chord change (ATTYA bars 61-63 hold C4 over
    # F-7, Bb-7, Eb7): the inner voices sounding under the held note belong to the
    # chord the hold started on, not the one written above it.
    repeated: bool = False
    # Which grip family harmonised this step, mirroring voicing.grip. One of
    # GRIP_PREFERENCE for an ordinary chord, "melody" for a no-chord step. Defaulted,
    # so an existing hand-built ArrangementStep is unaffected.
    grip: str = "drop2"
    # True when a chorded step is harmonised with fewer than four voices, i.e. it is a
    # shell or a duo rather than a complete chord. The chord name printed above such a
    # step describes the harmony, not every note sounding under it, so the renderers
    # annotate it. Defaulted, so an ordinary four-note step is unaffected.
    partial: bool = False
    # Which metric role the texture rules gave this step: ROLE_TARGET on a principal
    # melody note (a full chord states the harmony there), ROLE_FILL on a connecting
    # note (a shell, an interval or the melody alone). Set by
    # VoiceLeadingEngine.arrange_progression from the slot's timing, and defaulted
    # to target so a hand-built step and every existing construction are unaffected.
    role: str = ROLE_TARGET
    # How metrically strong the slot was: 2 on beat 1, 1 on beat 3, 0 on any other
    # beat, and **-1 when the step carries no timing at all**. The -1 matters: it
    # separates "we know this note is weak" from "we were never told where it falls",
    # and it is what makes a progression with no rhythm behave exactly as it did
    # before this feature existed. See _metric_weight.
    metric_weight: int = 0
    # --- Walking bass (texture="walking_bass") ---
    #
    # MIDI pitch of the thumb note under this step, or None when there is none. Like
    # Voicing.bass_midi it is attached only after the upper shape has been chosen, so it
    # never enters the voicing cost.
    bass: Optional[int] = None
    # The bass note's role, one of the BASS_ROLE_* constants. Defaulted and a plain
    # string, like `grip` and `role`.
    bass_role: Optional[str] = None
    # The step exists for the thumb and **nothing above it strikes**: the upper voices
    # are held from the previous strike and the melody is not re-attacked. This is the
    # opposite of `repeated`, not a variant of it - `repeated` marks a melody that *is*
    # re-articulated (the soprano strikes, the inner voices are held) - so setting one
    # never sets the other, and an NC step is never marked either.
    #
    # It is what lets the bass grid be finer than the melody grid: a bar whose melody is
    # a single whole note still gets four thumb notes, one of them on the step that
    # carries the melody and three bass-only. `arrange_progression` therefore returns
    # more steps than the progression it was given under this texture, and this field is
    # how a renderer tells which is which.
    bass_only: bool = False

    @property
    def has_timing(self) -> bool:
        """
        True when this step carries a bar and beat, i.e. it can be placed on a
        rhythmic grid. A hand-written progression has no timing, so the renderer
        has to fall back to a uniform grid for it.
        """
        return self.bar is not None and self.beat is not None

    def tab_line(self) -> str:
        """Returns the one-line tab for this step, e.g. 'x-x-12-13-13-13'."""
        return self.voicing.tab_string()

    def tab_block(self) -> List[str]:
        """Returns the six-line vertical tab for this step's voicing."""
        return self.voicing.tab_block()

    # Backward compatibility: dictionary-like indexing step["chord"], step["voicing"]
    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)


class GuitarFretboard:
    """Handles mapping notes to physical guitar fretboard positions."""
    
    @staticmethod
    def note_to_fret(string_index: int, note: Note) -> int:
        """Calculates the fret number for a given note on a specific string (0 = Low E)."""
        if string_index < 0 or string_index >= len(STANDARD_TUNING):
            return -1
        open_note = STANDARD_TUNING[string_index]
        semitones = note.midi_note() - open_note.midi_note()
        return semitones if 0 <= semitones <= 18 else -1

    @staticmethod
    def fret_to_midi(string_index: int, fret: int) -> int:
        """Calculates MIDI note number for a string and fret."""
        if string_index < 0 or string_index >= len(STANDARD_TUNING) or fret < 0:
            return -1
        return STANDARD_TUNING[string_index].midi_note() + fret


def _note_name(midi: int) -> str:
    """
    Spells a MIDI number as a pitch-class name plus octave, e.g. 82 -> 'Bb5'.

    Used when a step has been transposed down an octave and has to report the pitch
    that actually sounds. Flats are preferred, matching PITCH_CLASS_NAMES and the
    jazz spelling used elsewhere in this module. Takes a raw MIDI number because
    musthe.Note only parses a string, so an octave-transposed pitch has to be
    spelled before it can be rebuilt as a Note.
    """
    return f"{PITCH_CLASS_NAMES[midi % 12]}{midi // 12 - 1}"


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
        return VoiceLeadingEngine.DROP2_INTERVAL_SETS.get(quality, [])

    if grip not in ("drop3", "closed"):
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
    # Drop 3: the third voice from the top drops an octave, so it lands below the
    # bottom voice and the shape closes with a 2nd at the bottom.
    return [[0, v1, v2 - 12, v3]]


def _duo_offsets(tones: Tuple[int, ...], melody_midi: int, root_pc: int) -> List[int]:
    """
    A two-note grip under the melody, or an empty list.

    Only ever a root or a 5th in the melody (DUO_DEGREES): there the ear supplies the
    guide tones, so two voices carry the harmony. A 3rd or a 7th in the melody is
    precisely the note that defines the chord's function, and pairing it with one
    other note is the voicing that sounds like a mistake - so this returns nothing and
    the selector has to find a shell or a complete shape instead.

    The second voice is the 3rd, which is what keeps the pair from being an empty
    fifth. A triad has no 3rd-and-7th distinction, so a 5th-top triad falls back to
    its own third, or to the root when the chord is a suspended fourth.
    """
    if (melody_midi - root_pc) % 12 not in DUO_DEGREES:
        return []

    # Preference order: the chord's own 3rd, then the minor 3rd for a chord that has
    # no major one, then the root for a suspended chord with nothing else available.
    third = next((d for d in (4, 3, 0) if d in tones and d not in DUO_DEGREES), None)
    if third is None:
        return []

    pitch = _nearest_tone_below(melody_midi, (root_pc + third) % 12)
    if pitch is None:
        return []
    return [0, pitch - melody_midi]


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
    every fret on the board, and a hand that does not stretch - `fret_span() <= 5`.

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


class ChordParser:
    """Parses chord symbols and identifies harmonic degrees."""

    # Canonical chord-quality spellings. Keys are every accepted spelling; values
    # are the keys used by DROP2_INTERVAL_SETS / DEGREE_OFFSETS_FROM_ROOT. The
    # lookup is case-sensitive on purpose: "M7" is a major seventh while "m7" is a
    # minor seventh, so normalising with .lower() would confuse the two families.
    QUALITY_ALIASES = {
        # minor family
        "min7": "m7",
        "min7b5": "m7b5",
        "ø7": "m7b5",
        "ø": "m7b5",
        "half-dim": "m7b5",
        "min6": "m6",
        "minMaj7": "mMaj7",
        "mmaj7": "mMaj7",
        "min9": "m9",
        # diminished
        "°7": "dim7",
        "°": "dim7",
        "dim": "dim7",
        # dominant family
        "dom7": "7",
        "dom9": "9",
        "dom13": "13",
        # major family
        "M7": "maj7",
        "M9": "maj9",
        "69": "6/9",
        # triads and suspended chords. Note the bare major-third symbol "M" is a
        # triad here while "M7" stays a major seventh; "dim" deliberately keeps
        # resolving to dim7 (the diminished triad is not voiced by this library).
        "M": "maj",
        "min": "m",
        "-": "m",
        # The Weimar Jazz Database spells a minor seventh with a leading hyphen
        # ("F-7"), and its own table already maps that to m7. Recognising the suffix
        # here as well means a chord name written either way resolves to one chord,
        # which is what comparing two steps' harmony depends on. Without it a name
        # like "D-7" parsed to the unusable quality "-7".
        "-7": "m7",
        "+": "aug",
        "sus": "sus4",
        "7sus": "7sus4",
    }

    # Every chord tone of each quality, as pitch classes relative to the root
    # (0 = root). This is deliberately *separate* from the drop-2 templates: it
    # answers "is this melody note in the chord?", including tones the four-note
    # voicings omit (the root of a rootless 7b9, or the 9th of a maj9).
    CHORD_TONES_FROM_ROOT: Dict[str, Tuple[int, ...]] = {
        # Seventh/sixth chords whose four tones are all voiced
        "maj7": (0, 4, 7, 11),
        "6": (0, 4, 7, 9),
        "m7": (0, 3, 7, 10),
        "m7b5": (0, 3, 6, 10),
        "dim7": (0, 3, 6, 9),
        "m6": (0, 3, 7, 9),
        "mMaj7": (0, 3, 7, 11),
        "7": (0, 4, 7, 10),
        # Altered dominants voiced without their root; the root is still a chord tone
        "7b9": (0, 1, 4, 7, 10),
        "7alt": (0, 1, 3, 4, 6, 8, 10),
        # Extended qualities, voiced rootless as four-note drop-2 shapes
        "maj9": (0, 2, 4, 7, 11),
        "m9": (0, 2, 3, 7, 10),
        "9": (0, 2, 4, 7, 10),
        "6/9": (0, 2, 4, 7, 9),
        "13": (0, 2, 4, 7, 9, 10),
        # Triads and suspended chords. A drop-2 shape needs four voices, so the
        # triad templates double the root an octave below the stack.
        "maj": (0, 4, 7),
        "m": (0, 3, 7),
        "aug": (0, 4, 8),
        "sus4": (0, 5, 7),
        "sus2": (0, 2, 7),
        # Added-note colours
        "add9": (0, 2, 4, 7),
        "madd9": (0, 2, 3, 7),
        # Suspended and altered dominants
        "7sus4": (0, 5, 7, 10),
        "7b5": (0, 4, 6, 10),
        "7#5": (0, 4, 8, 10),
        # Colour qualities whose four-note shapes omit a tone, so the full tone
        # set is deliberately wider than the notes any one shape sounds.
        "7#11": (0, 4, 6, 7, 10),
        "7b13": (0, 4, 7, 8, 10),
        "maj7#11": (0, 4, 6, 7, 11),
        "m9b5": (0, 2, 3, 6, 10),
    }

    @staticmethod
    def canonical_quality(chord_type: Optional[str]) -> str:
        """
        Normalises a chord quality to its canonical spelling.

        Aliases are resolved case-sensitively (so 'M7' -> 'maj7' but 'm7' stays
        'm7'), which also fixes the historical case bug where 'mMaj7'.lower()
        produced 'mmaj7' and silently missed every table lookup. Unknown
        qualities are returned unchanged so callers can report them.
        """
        if not chord_type:
            return ""
        quality = chord_type.strip()
        return ChordParser.QUALITY_ALIASES.get(quality, quality)

    @staticmethod
    def parse_chord_name(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Extracts root pitch and quality string from chord name (e.g. 'Dm7b5' -> ('D', 'm7b5'))."""
        if not name:
            return None, None
        m = re.match(r"^([A-G][#b]?)(.*)$", name.strip())
        if m:
            return m.group(1), m.group(2)
        return None, None

    @staticmethod
    def get_melody_degree(root_str: str, melody_note: Note) -> int:
        """Returns the melody note interval class (0-11) relative to chord root."""
        root_midi = Note(root_str + "4").midi_note()
        return (melody_note.midi_note() - root_midi) % 12

    @staticmethod
    def get_chord_tones(chord_type: str, chord_name: Optional[str] = None) -> Tuple[int, ...]:
        """
        Returns the pitch classes (0-11) of every tone in a chord quality.

        With chord_name the pitch classes are absolute; without it they are
        relative to the root (0 = root). Unknown qualities return an empty tuple.
        """
        tones = ChordParser.CHORD_TONES_FROM_ROOT.get(ChordParser.canonical_quality(chord_type), ())
        if not tones or not chord_name:
            return tones
        root_str, _ = ChordParser.parse_chord_name(chord_name)
        if not root_str:
            return tones
        root_pc = Note(root_str + "4").midi_note() % 12
        return tuple((root_pc + pc) % 12 for pc in tones)

@dataclass
class StepPreparation:
    """One step's voicing candidates, plus the bookkeeping to report the step.

    Returned by `VoiceLeadingEngine.prepare_step` so a caller that needs extra
    per-step control - the corpus loader honours a slash bass and attaches the
    slot's timing - can choose from these candidates using the engine's own rule
    rather than re-deriving the voicing itself.

    That distinction is load-bearing. The loader used to build its own
    candidates and call `_best_voicing` directly, which silently skipped the
    non-chord-tone strategies, the selector's tone-purity criterion (because
    `allowed_tones` defaults to None) and the octave-down rescue. `chord_type`
    and `chord_name` stay the *written* chord even when `harmonized_as` names a
    substitute, because `allowed_tones` has always been built from the written
    chord and changing that would move the library's published output.
    """

    candidates: List["Voicing"]
    written_melody: str
    melody: str
    original_melody: Optional[str]
    chord_type: str
    chord_name: str
    is_non_chord_tone: bool
    strategy: Optional[str]
    harmonized_as: Optional[str]


def normalised_harmony(
    chord: str, harmonized_as: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """A (root, quality) pair for a chord, however it is spelled.

    `harmonized_as` wins when a non-chord-tone strategy substituted a chord,
    otherwise the written name. Normalised through `ChordParser` so `D-7` and
    `Dm7` are the same chord rather than two, which matters because the corpus
    writes Weimar notation and the library writes its own.
    """
    root, quality = ChordParser.parse_chord_name(harmonized_as or chord)
    return (root, ChordParser.canonical_quality(quality) if quality else quality)


def sounding_harmony(step: ArrangementStep) -> Tuple[Optional[str], Optional[str]]:
    """The harmony a step actually sounds, normalised so two spellings compare equal.

    Used to decide whether a repeated melody is still a hold: a note repeating
    across a *chord change* is not a held shape, it is a new harmony that the
    held soprano has to be heard against.
    """
    return normalised_harmony(step.chord, step.harmonized_as)


class VoiceLeadingEngine:
    """Generates and voice-leads jazz guitar voicings dynamically."""
    
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

    # Non-chord-tone strategy routing: canonical base quality -> {melody degree
    # (relative to root): extension quality that absorbs it as a chord tone}.
    # Only entries that are musically unambiguous are listed; anything missing
    # leaves the melody to the existing quality-only fallback.
    NON_CHORD_TONE_EXTENSIONS = {
        "maj7": {2: "maj9", 6: "maj7#11", 9: "6/9"},   # 9th, #11, 6th/13th
        "6": {2: "6/9"},                               # 9th
        "m7": {2: "m9"},                               # 9th
        "m7b5": {2: "m9b5"},                           # 9th (half-diminished 9)
        # 9th, 11th (the suspended dominant), #11, b13, 13th
        "7": {2: "9", 5: "7sus4", 6: "7#11", 8: "7b13", 9: "13"},
        "7b9": {5: "7sus4", 6: "7#11", 8: "7b13"},     # 11th, #11, b13
        "9": {6: "7#11", 9: "13"},                     # #11, 13th
        "13": {6: "7#11"},                             # #11
    }

    # Accepted values for arrange_progression(non_chord_tone=...).
    NON_CHORD_TONE_STRATEGIES = ("extension", "diminished", "sustain", "legacy")

    @staticmethod
    def _parse_chord_name(name: str) -> Tuple[Optional[str], Optional[str]]:
        """Delegates to ChordParser for backward compatibility."""
        return ChordParser.parse_chord_name(name)

    @staticmethod
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
        Rotating from wherever it actually is what keeps every grip's soprano on the
        melody.
        """
        if grip == "drop2":
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
                pivot = strings.index(soprano)
                sets.append(tuple(strings[pivot:]) + tuple(strings[:pivot]))
        return sets

    @classmethod
    def _chord_context(
        cls, chord_type: str, chord_name: Optional[str]
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

    @classmethod
    def get_grip_voicings(
        cls,
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
        GRIP_STRING_SETS entry, carries the melody on its topmost string, and keeps
        every finger within GRIP_MAX_SPAN of it.
        """
        melody_midi = melody_note.midi_note()

        top_fret = GuitarFretboard.note_to_fret(top_string, melody_note)
        if top_fret < 0 or top_fret > 18:
            return []

        canonical, root_pc, tones = cls._chord_context(chord_type, chord_name)

        # Which inversion of a drop-2 table puts this melody in the top voice. The
        # derived families build their shape from the chord tones themselves and so
        # need no steering; this only narrows the table lookup.
        target_idx: Optional[int] = None
        deg_offsets = cls.DEGREE_OFFSETS_FROM_ROOT.get(canonical)
        if chord_name and deg_offsets and root_pc is not None:
            mel_degree = (melody_midi - root_pc) % 12
            for idx, d in enumerate(deg_offsets):
                if d % 12 == mel_degree:
                    target_idx = idx
                    break

        valid_voicings: List[Voicing] = []
        for grip in grips:
            for strings in cls._string_sets_for(grip, top_string):
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
                        duo = _duo_offsets(tones, melody_midi, root_pc)
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
                    if (
                        target_idx is not None
                        and grip == "drop2"
                        and 0 <= target_idx < len(templates)
                    ):
                        templates = [templates[target_idx]]

                for template in templates:
                    voicing = _place_template(
                        template, strings, melody_midi, top_fret, grip
                    )
                    if voicing is not None:
                        valid_voicings.append(voicing)

        return valid_voicings

    @classmethod
    def get_drop2_voicings(
        cls,
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
        return cls.get_grip_voicings(
            melody_note, chord_type, chord_name, top_string, grips=("drop2",)
        )

    @classmethod
    def get_interval_voicings(
        cls,
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
        return cls.get_grip_voicings(
            melody_note, chord_type, chord_name, top_string, grips=("interval",)
        )

    @staticmethod
    def _lower_soprano_strings(top_strings: Tuple[int, ...]) -> Tuple[int, ...]:
        """
        The subset of `top_strings` below the high E, so a transposed melody is voiced
        on the B string rather than back on the high E. Falls back to `top_strings`
        when it contains nothing below the high E, so a caller restricted to (5,)
        still gets a (higher) voicing instead of nothing.
        """
        lower = tuple(s for s in top_strings if s < len(STANDARD_TUNING) - 1)
        return lower or tuple(top_strings)

    @classmethod
    def get_octave_down_candidates(
        cls,
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
        return cls.get_all_grip_voicings(
            octave_down,
            chord_type,
            chord_name=chord_name,
            top_strings=cls._lower_soprano_strings(top_strings),
            grips=grips,
        )

    @classmethod
    def get_all_grip_voicings(
        cls,
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
                cls.get_grip_voicings(
                    melody_note, chord_type, chord_name, top_string, grips
                )
            )

        if not candidates and chord_name:
            for top_string in top_strings:
                candidates.extend(
                    cls.get_grip_voicings(
                        melody_note, chord_type, None, top_string, grips
                    )
                )

        return candidates

    @classmethod
    def get_all_drop2_voicings(
        cls,
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
        return cls.get_all_grip_voicings(
            melody_note, chord_type, chord_name, top_strings, grips=("drop2",)
        )

    @classmethod
    def get_melody_only_voicing(
        cls,
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
            (cls._lower_soprano_strings(prefer), -12),
        ]
        for strings, octave_shift in attempts:
            for string_index in _melody_only_string_order(strings):
                shifted = Note(_note_name(melody_note.midi_note() + octave_shift))
                fret = GuitarFretboard.note_to_fret(string_index, shifted)
                if 0 <= fret <= HIGH_FRET_LIMIT:
                    frets = [-1] * len(STANDARD_TUNING)
                    frets[string_index] = fret
                    return Voicing(frets=frets, top_fret=fret, avg_fret=float(fret))
        return None

    # ------------------------------------------------------------------
    # Non-chord melody tones
    # ------------------------------------------------------------------
    @classmethod
    def is_chord_tone(cls, melody_note: Note, chord_type: str, chord_name: Optional[str] = None) -> bool:
        """
        True when melody_note is one of the chord's tones.

        Detection uses ChordParser.CHORD_TONES_FROM_ROOT (every chord tone), not
        DEGREE_OFFSETS_FROM_ROOT (only the four notes a drop-2 shape can voice),
        so the root of a rootless quality such as 7b9 still counts as a chord
        tone and is not needlessly reharmonised. Unknown qualities return False.
        """
        canonical = ChordParser.canonical_quality(chord_type)
        tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical)
        if not tones:
            return False

        root_pc = 0
        if chord_name:
            root_str, _ = ChordParser.parse_chord_name(chord_name)
            if root_str:
                root_pc = Note(root_str + "4").midi_note() % 12

        return ((melody_note.midi_note() - root_pc) % 12) in {t % 12 for t in tones}

    @classmethod
    def resolve_non_chord_tone(
        cls,
        melody_note: Note,
        chord_type: str,
        chord_name: str,
        strategy: str = "extension",
        next_melody: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Picks a substitute (chord quality, chord name) that turns a non-chord
        melody note into a genuine chord tone, so get_drop2_voicings can voice it.
        Returns None when the strategy cannot help, leaving the caller's existing
        behaviour untouched.

        strategy:
          'extension'  - keep the harmony and absorb the note as an extension,
                         e.g. D over Cmaj7 (the 9th) -> Cmaj9.
          'diminished' - Barry Harris 6/dim7: voice the note inside a dim7 built a
                         semitone below the pitch the line resolves to, e.g. the
                         passing D over Cmaj7 -> Bdim7.
          'legacy'     - no substitution.
        """
        if strategy == "legacy" or not chord_name:
            return None

        canonical = ChordParser.canonical_quality(chord_type)
        root_str, _ = ChordParser.parse_chord_name(chord_name)
        if not root_str:
            return None

        if strategy == "extension":
            degree = ChordParser.get_melody_degree(root_str, melody_note)
            extension = cls.NON_CHORD_TONE_EXTENSIONS.get(canonical, {}).get(degree)
            if extension:
                return extension, f"{root_str}{extension}"
            return None

        if strategy == "diminished":
            target_pc = cls._resolution_pitch_class(melody_note, root_str, canonical, next_melody)
            if target_pc is None:
                return None
            # A dim7 is symmetrical, so naming the root a semitone below the
            # resolution target is the idiomatic Barry Harris spelling; all four
            # enharmonic roots finger identically.
            dim_root = PITCH_CLASS_NAMES[(target_pc - 1) % 12]
            return "dim7", f"{dim_root}dim7"

        return None

    @classmethod
    def _resolution_pitch_class(
        cls,
        melody_note: Note,
        root_str: str,
        canonical_type: str,
        next_melody: Optional[str],
    ) -> Optional[int]:
        """
        Pitch class the non-chord tone resolves into: the next chord tone of the
        line when one is known, otherwise the nearest chord tone of the underlying
        chord at or below the melody.
        """
        if next_melody:
            return Note(next_melody).midi_note() % 12

        tones = sorted(
            (Note(root_str + "4").midi_note() + tone) % 12
            for tone in ChordParser.CHORD_TONES_FROM_ROOT.get(canonical_type, ())
        )
        if not tones:
            return None

        melody_pc = melody_note.midi_note() % 12
        below = [tone for tone in tones if tone <= melody_pc]
        return below[-1] if below else tones[-1]

    @staticmethod
    def _window_penalty(
        candidates: List[Voicing],
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
    ) -> int:
        """
        How many frets the best of `candidates` puts outside the neck window.

        Zero means at least one candidate lies wholly inside it. This is the test the
        octave-down rescue uses to decide whether a melody is *badly placed* - and it
        deliberately asks the best candidate rather than the average, so one
        comfortable voicing is enough to leave the melody where it was written.
        """
        return min(
            (
                sum(1 for fret in v.active_frets() if not fret_min <= fret <= fret_max)
                for v in candidates
            ),
            default=0,
        )

    @classmethod
    def voicing_cost(
        cls,
        voicing: Voicing,
        previous: Optional[Voicing],
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        allowed_tones: Optional[Container[int]] = None,
        root_pc: Optional[int] = None,
    ) -> Tuple[float, ...]:
        """
        The whole selection rule as one comparable number, lowest wins.

        It is a *tuple* rather than a weighted sum on purpose. These six priorities are
        genuine trade-offs that must not be traded against each other - "stay in
        position" is not worth a semitone of inner-voice movement, but both are worth
        far more than preferring drop-2 over a shell - and a weighted sum would hide
        that behind magic numbers whose values nobody can defend. Lexicographic order
        states the ranking directly, so the second criterion is only consulted when the
        first is exactly tied.

        In order:

        0. notes outside the chord, when `allowed_tones` is given. This is a
           *correctness* criterion and it outranks every preference, because a wrong note
           is not playable at all while an awkward position is merely awkward. It exists
           because the hand-authored drop-2 tables do not have an inversion for every
           chord tone - a 9th in the melody of a 13 chord, for instance - and the
           quality-only fallback that covers the gap is free to sound a note the chord
           does not contain. Several of the derived grips always pass this.
        1. frets outside the window. This is a *penalty*, not a filter. A melody that
           cannot be voiced between the two frets is still played, one fret-pair at a
           time out of position, because a chord of the tune is worth more than a
           fretboard preference. See NECK_FRET_MIN.
        2. missing voices. A partial harmonisation is a *fallback*, not a style: where a
           complete chord can be played at all, it is used, and it outranks staying in
           exactly the same spot. This sits below the window and above position because
           both of those are about comfort and this is about whether the chord is
           actually there - a root-and-3rd duo is a real voicing of a root-and-3rd, not a
           Cmaj7. A permitted root-or-5th duo scores zero here, so where two notes really
           are enough it competes on equal terms with a four-note shape.
        3. distance in neck position from the previous voicing, measured as the
           difference of average frets. Absolute fret numbers mean the same place on the
           neck whichever string they are on, so this stays meaningful when a melody
           holds its place by moving to a different string - which is the behaviour the
           G-string soprano exists to enable. With no previous chord this becomes the
           long-standing "start near the middle of the neck" rule.
        4. total pitch movement of the voices, the historical voice-leading measure.
        5. fret span: a tighter shape is easier to hold and to move.
        6. bass function, when `root_pc` is given: 0 for a root or a 5th in the lowest
           voice, 1 otherwise. This is a *tie-break*, not a priority - it is consulted
           only when two shapes already agree on everything above, which is exactly the
           situation 6-4-3-2 creates. Its whole point is to make the low-E root bass
           reachable at all: the contiguous 5-4-3-2 block places its lowest note on the A
           string, so a root there is a consequence of the string set and never a
           decision, and without this term `voicing_cost` declines the alternative on
           neck position before it ever reaches the bass. Putting it at 6 rather than
           near the front is deliberate: "the bass should be the root" must not outbid
           "do not sound a wrong note" or "keep the hand where it is". The same rule as
           BASS_DEGREES_6432, applied to whatever shape won rather than to one family,
           so a contiguous shape with a root bass is not penalised either.
        7. grip preference, so a four-note drop-2 wins an exact tie against a shell.
        """
        active = voicing.active_frets()
        outside = sum(1 for fret in active if not fret_min <= fret <= fret_max)
        foreign = (
            1.0
            if allowed_tones is not None
            and not all(pc in allowed_tones for pc in voicing.pitch_classes())
            else 0.0
        )

        if previous is None:
            # The first chord of a progression has nothing to lead from, so "stay near
            # where we are" becomes "start in a comfortable part of the neck".
            position = abs(voicing.avg_fret - 9)
            movement = 0.0
        else:
            position = abs(voicing.avg_fret - previous.avg_fret)
            movement = cls.calculate_pitch_leading_distance(previous, voicing)

        grip_rank = (
            GRIP_PREFERENCE.index(voicing.grip)
            if voicing.grip in GRIP_PREFERENCE
            else len(GRIP_PREFERENCE)
        )
        missing = 4 - len(active)
        # No root, no claim to make: an unparseable chord name simply does not get this
        # criterion, which is why it is opt-in per call rather than derived.
        bass_root_or_fifth = (
            0.0
            if root_pc is not None
            and voicing.bass_pc is not None
            and (voicing.bass_pc - root_pc) % 12 in BASS_DEGREES_6432
            else 1.0
        )

        return (
            foreign,
            float(outside),
            float(missing),
            position,
            movement,
            float(voicing.fret_span()),
            bass_root_or_fifth,
            float(grip_rank),
        )

    @classmethod
    def _best_voicing(
        cls,
        candidates: List[Voicing],
        previous: Optional[Voicing] = None,
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        allowed_tones: Optional[Container[int]] = None,
        root_pc: Optional[int] = None,
    ) -> Optional[Voicing]:
        """
        The candidate voicing_cost likes best, or None when there are no candidates.

        Python's min is stable, so two candidates that cost exactly the same are
        decided by generation order, which is high-E strings first and GRIP_PREFERENCE
        within a string. That keeps the whole engine deterministic: the same progression
        always arranges to the same tab, which is what makes its output worth asserting
        on in tests.

        `root_pc` is passed straight through to voicing_cost and is what enables the
        bass-function tie-break. A caller that does not have a root simply omits it and
        gets the previous behaviour, unchanged.
        """
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda v: cls.voicing_cost(
                v, previous, fret_min, fret_max, allowed_tones, root_pc
            ),
        )

    @classmethod
    def sustain_inner_voices(cls, previous_voicing: Voicing | dict, melody_note: Note) -> Optional[Voicing]:
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

    @staticmethod
    def calculate_voice_leading_distance(voicing_a: Voicing | dict, voicing_b: Voicing | dict) -> float:
        """Calculates total physical movement across all active strings."""
        frets_a = voicing_a["frets"] if isinstance(voicing_a, dict) else voicing_a.frets
        frets_b = voicing_b["frets"] if isinstance(voicing_b, dict) else voicing_b.frets
        total_distance = 0
        for f_a, f_b in zip(frets_a, frets_b):
            if f_a >= 0 and f_b >= 0:
                total_distance += abs(f_a - f_b)
        return float(total_distance)

    @staticmethod
    def calculate_pitch_leading_distance(voicing_a: Voicing | dict, voicing_b: Voicing | dict) -> float:
        """
        Sums the movement of every voice between two voicings, measured in semitones.

        This is the string-set agnostic counterpart to calculate_voice_leading_distance:
        it compares sounding pitches rather than fret numbers, so it stays meaningful
        when one chord puts the melody on the high E string and the next puts it on the
        B string (the same pitch sounding on a different string). Within a single string
        set the two metrics agree exactly, since a fret delta is a semitone delta.
        """
        frets_a = voicing_a["frets"] if isinstance(voicing_a, dict) else voicing_a.frets
        frets_b = voicing_b["frets"] if isinstance(voicing_b, dict) else voicing_b.frets
        pitches_a = sorted(
            GuitarFretboard.fret_to_midi(s_idx, f) for s_idx, f in enumerate(frets_a) if f >= 0
        )
        pitches_b = sorted(
            GuitarFretboard.fret_to_midi(s_idx, f) for s_idx, f in enumerate(frets_b) if f >= 0
        )
        return float(sum(abs(p_a - p_b) for p_a, p_b in zip(pitches_a, pitches_b)))

    @classmethod
    def prepare_step(
        cls,
        progression: List[Tuple[str, str, str]],
        index: int,
        previous: Optional[Voicing] = None,
        previous_chord: Optional[str] = None,
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
    ) -> Optional[StepPreparation]:
        """
        Builds one step's candidates, leaving the choice of shape to the caller.

        This is a whole step up to selection: the candidates across every allowed
        soprano string and grip family, the octave-down rescue, and the
        non-chord-tone strategies. `arrange_progression` selects with
        `_best_voicing` straight afterwards, and the corpus loader selects the
        same way after honouring a slash bass, so the two cannot drift.

        Returns None when the step has no voicing at all. `previous` is only read
        by the `sustain` strategy, and `previous_chord` is what that strategy
        reports as `harmonized_as`.
        """
        note_str, chord_type, name = progression[index]
        melody_note = Note(note_str)

        # Chord-tone match first, quality-only fallback second, across every
        # allowed soprano string and every grip family.
        candidates = cls.get_all_grip_voicings(
            melody_note, chord_type, chord_name=name,
            top_strings=top_strings, grips=grips,
        )

        # A melody whose best position sits outside the neck window is re-voiced an
        # octave down on the B string. The written pitch is kept in original_melody.
        # Decided before the non-chord-tone strategies run, so a substituted chord
        # is voiced at the transposed pitch too rather than snapping back up.
        #
        # The guard requires candidates to exist: this repositions a voicing that
        # is playable but sits too high. A melody unreachable at the written pitch
        # (C6, fret 20 - past the end of the board) is left alone, because there is
        # no shape to move down and respelling it would hide the real problem.
        sounding_melody = melody_note
        original_melody: Optional[str] = None
        if candidates and cls._window_penalty(candidates, fret_min, fret_max) > 0:
            octave_down = cls.get_octave_down_candidates(
                melody_note, chord_type, chord_name=name,
                top_strings=top_strings, grips=grips,
            )
            # Only take the lower octave when it genuinely improves the placement,
            # or a merely slightly out-of-window melody would be moved for nothing.
            here = cls._window_penalty(candidates, fret_min, fret_max)
            there = cls._window_penalty(octave_down, fret_min, fret_max)
            if octave_down and there < here:
                candidates = octave_down
                sounding_melody = Note(_note_name(melody_note.midi_note() - 12))
                original_melody = note_str

        strategy_used: Optional[str] = None
        harmonized_as: Optional[str] = None
        is_non_chord_tone = (
            ChordParser.canonical_quality(chord_type) in ChordParser.CHORD_TONES_FROM_ROOT
            and not cls.is_chord_tone(melody_note, chord_type, name)
        )

        if is_non_chord_tone and non_chord_tone != "legacy":
            # Strategy 3 first: holding the shape moves less than any re-voicing.
            if non_chord_tone == "sustain" and previous is not None:
                sustained = cls.sustain_inner_voices(previous, sounding_melody)
                if sustained is not None:
                    candidates = [sustained]
                    strategy_used = "sustain"
                    harmonized_as = previous_chord

            # Strategies 1 and 2 reharmonise the note as a genuine chord tone.
            if strategy_used is None:
                resolved = cls.resolve_non_chord_tone(
                    sounding_melody,
                    chord_type,
                    name,
                    non_chord_tone,
                    next_melody=cls._next_resolution_melody(progression, index),
                )
                if resolved is not None:
                    substitute_quality, substitute_name = resolved
                    substituted = cls.get_all_grip_voicings(
                        sounding_melody,
                        substitute_quality,
                        chord_name=substitute_name,
                        top_strings=top_strings,
                        grips=grips,
                    )
                    if substituted:
                        candidates = substituted
                        strategy_used = non_chord_tone
                        harmonized_as = substitute_name

            if strategy_used is None:
                print(
                    f"Warning: melody {note_str} is not a chord tone of {name} and the "
                    f"'{non_chord_tone}' strategy found no voicing; keeping the fallback"
                )

        if not candidates:
            return None

        return StepPreparation(
            candidates=candidates,
            written_melody=note_str,
            # The transposed pitch when moved down an octave: the step reports
            # what actually sounds.
            melody=(
                note_str
                if original_melody is None
                else _note_name(sounding_melody.midi_note())
            ),
            original_melody=original_melody,
            chord_type=chord_type,
            chord_name=name,
            is_non_chord_tone=is_non_chord_tone,
            strategy=strategy_used,
            harmonized_as=harmonized_as,
        )

    @classmethod
    def arrange_progression(
        cls,
        progression: List[Tuple[str, str, str]],
        top_strings: Tuple[int, ...] = MELODY_STRING_CHOICES_FULL,
        non_chord_tone: str = "extension",
        fret_min: int = NECK_FRET_MIN,
        fret_max: int = NECK_FRET_MAX,
        grips: Tuple[str, ...] = GRIP_PREFERENCE,
        timings: Optional[List[Tuple[int, float, Optional[float]]]] = None,
        texture: str = "uniform",
        beats_per_bar: int = 4,
    ) -> List[ArrangementStep]:
        """
        Takes a progression of (Melody Note, Chord Quality, Name) tuples
        and computes the optimal voice-led arrangement.

        top_strings selects which strings may carry the melody (see
        MELODY_STRING_CHOICES_FULL). The default allows the high E, the B *and* the G
        string, so a melody can hold its place on the neck by changing strings rather
        than by moving the hand, and a melody below the high E string's open pitch is
        still arranged rather than skipped.

        fret_min and fret_max bound the comfortable neck window the selector aims for
        (frets 2-13 by default). They are a strong preference, not a constraint: a step
        with no voicing inside the window is still played, just outside it, because
        losing a chord of the tune is worse than being a fret out of position.

        grips limits which grip families may be used, in the order they break a tie
        (see GRIP_PREFERENCE). The default offers all of them. `grips=("drop2",)` with
        `top_strings=MELODY_STRING_CHOICES` reproduces this library's original,
        four-string-drop-2-only output exactly, which is what a caller wants when they
        need a known arrangement rather than the best one.

        non_chord_tone selects what happens when a melody note is not a chord tone
        (one of NON_CHORD_TONE_STRATEGIES):
          'extension'  - reharmonise the note as a chord extension (D over Cmaj7
                         becomes Cmaj9), the default;
          'diminished' - Barry Harris 6/dim7 substitution (D over Cmaj7 -> Bdim7);
          'sustain'    - keep the previous chord's inner voices and move only the
                         melody, for brief passing tones;
          'legacy'     - keep the original quality-only fallback behaviour.
        Steps whose melody is already a chord tone are unaffected by this choice.

        A step whose chord_type or name is NO_CHORD ("NC") is voiced as the melody
        alone on a single fret (get_melody_only_voicing) and flagged
        melody_only=True. Such a step is short-circuited before any chord logic,
        so it is never reharmonised and never warns; it also does not take part in
        voice-leading minimisation, and being neither a drop-2 voicing nor a
        four-string shape it is exempt from that playability invariant.

        **Texture and rhythm.** `timings` is each slot's own `(bar, beat, duration)`
        in the caller's units - a signed bar, the beat within it, and a length in
        whole notes - the same triple `ArrangementStep` already carries. `None`, the
        default, means the caller has told us nothing about where its notes fall, and
        then every slot is a principal note and this function behaves exactly as it
        always has.

        `texture="targets"` uses the timing to arrange the way the guide describes:
        a full four-note chord on beats 1 and 3 of the bar, and a shell, a 3rd/6th
        interval or the melody alone in between. `beats_per_bar` is what the rule
        reads to decide which beats exist, so a 3/4 or 2/2 head is not treated as
        4/4 (see TARGET_BEATS). The rule changes *which grips are offered*, never
        the cost tuple, so the selection order and the engine's determinism are
        untouched.

        A `timings` list shorter than `progression` is not an error: the unlocated
        trailing steps are simply treated as principal notes, which is the same
        "we know nothing" rule that governs `timings=None`. The guard is the one
        `wjazzd.arrange_slots` already applies to its own timings, for the same
        reason - a hand-built list must not silently shift the rhythm.

        `texture="walking_bass"` adds a thumb line on the bass strings under a light
        left hand: a **shell** (3rd & 7th) on a target beat, the **melody alone**
        between, and a four-quarter walk underneath. Three consequences are part of
        its contract rather than details of it:

        - **It may return more steps than it was given.** The bass grid is finer than
          the melody grid, so a bar whose melody is a whole note yields four steps -
          one carrying the melody and three marked `bass_only`, whose upper voices are
          held rather than re-struck. Callers that zip their progression against the
          result, or derive a bar count from `len(steps)`, are wrong under this texture
          only; `uniform` and `targets` are untouched.
        - **A fill is the melody alone**, and so is a target no shell can sound. The
          chord name above such a step describes the harmony rather than everything
          sounding, which is the texture rather than a defect - the harmony is stated
          in full at the next target.
        - **With `timings=None` the walk degrades to one note per slot.** There is no
          beat grid to place four quarters on, and that is the path every existing
          hand-written caller takes, so it is documented rather than silent.

        The bass is merged into `Voicing.frets` *after* `_best_voicing` has chosen the
        upper shape, so it cannot enter `voicing_cost`'s tuple by construction. That
        also means the combined string set is deliberately **not** a member of
        `supported_string_sets()`: the playability invariant applies to the upper
        voices, with exactly one `BASS_STRING_INDICES` string outside that set carrying
        the thumb below it.
        """
        if non_chord_tone not in cls.NON_CHORD_TONE_STRATEGIES:
            raise ValueError(
                f"Unknown non_chord_tone strategy {non_chord_tone!r}; "
                f"expected one of {cls.NON_CHORD_TONE_STRATEGIES}"
            )
        # Checked up front, so a typo costs a message rather than a full arrangement
        # followed by a surprise.
        texture_grips = TEXTURE_GRIPS.get(texture)
        if texture_grips is None:
            raise ValueError(
                f"Unknown texture {texture!r}; expected one of {TEXTURE_STYLES}"
            )

        arrangements: List[ArrangementStep] = []

        # The walking bass is computed here, over the **walked beats** rather than
        # over the slots, and it yields a pitch *class* rather than a pitch and a
        # string: neither the octave nor the string can be decided before an upper
        # voicing exists, and only this function is downstream of one. `_place_bass`
        # resolves both together, after selection.
        bass_line: List[BassNote] = []
        slots: Optional[List[_Slot]] = None
        if texture == "walking_bass":
            # `parse_chord_name` gives (root, quality); the name rides along only for
            # the caller's benefit, since the walk reads harmony and never the melody.
            # An unspeakable name leaves the quality None, and it is spelled as an
            # empty string rather than narrowed away: `_bass_harmony` returns None for
            # it, the walk contributes no notes, and nothing is guessed - which is the
            # "never guess a chord" rule the notation tables already follow.
            chords: List[Tuple[Optional[str], str, str]] = []
            for _note, _quality, name in progression:
                root, quality = ChordParser.parse_chord_name(name)
                chords.append((root, quality or "", name))
            onsets: List[Optional[Tuple[int, float]]] = [
                (timing[0], float(timing[1]))
                if timings is not None and index < len(timings) and timing is not None
                else None
                for index, timing in enumerate(timings or [])
            ]
            if len(onsets) < len(progression):
                onsets.extend([None] * (len(progression) - len(onsets)))
            bass_line = _walking_bass_line(chords, onsets, beats_per_bar)
            # Decision B: the union is built here, before the melody loop, so the
            # loop's index still indexes the skeleton it was given.
            slots = _bass_slots(progression, timings, bass_line)

        # Harmony and melody state for the walking-bass role rule. Both are read from
        # what actually sounds, not from the written chord, so a substituted chord
        # compares as itself (the same `normalised_harmony` the `repeated` hold uses).
        last_target_harmony: Optional[Tuple[Optional[str], Optional[str]]] = None
        previous_melody_midi: Optional[int] = None

        loop: List[_Slot] = (
            slots if slots is not None
            else [
                _Slot(
                    index=index,
                    bar=(timings[index][0]
                         if timings is not None and index < len(timings) else None),
                    beat=(float(timings[index][1])
                          if timings is not None and index < len(timings) else None),
                    duration=(timings[index][2]
                              if timings is not None and index < len(timings) else None),
                )
                for index in range(len(progression))
            ]
        )

        for slot in loop:
            index = slot.index
            note_str, chord_type, name = progression[index]
            melody_note = Note(note_str)

            # Where this slot falls in the bar, and therefore what it is for. Read
            # defensively, exactly as wjazzd.arrange_slots guards its own timings: a
            # short list leaves the trailing steps unlocated, and an unlocated step is
            # a principal note rather than a fill. The bar and beat are also stamped
            # onto the step, because a caller that supplied the rhythm wants to read it
            # back off the result rather than have to correlate two lists.
            bar, beat, duration = slot.bar, slot.beat, slot.duration
            weight = _metric_weight(bar, beat, beats_per_bar)
            # _roles_for_slot re-validates the texture, which is harmless: the table was
            # already checked before the loop, so this cannot raise here.
            #
            # Under walking_bass a strong beat is only a target when something new
            # happens on it: a different harmony from the last target's (the off-beat
            # change rule), or the melody actually moving onto it (decision F, which is
            # what lets the second bar of a two-bar chord restate its shell when the
            # player re-articulates the line there and stay thin when they do not).
            harmony_key = normalised_harmony(name)
            role = _roles_for_slot(
                weight,
                texture,
                harmony_changed=(last_target_harmony is None
                                 or harmony_key != last_target_harmony),
                melody_moves=(previous_melody_midi is None
                              or melody_note.midi_note() != previous_melody_midi),
            )[0]
            if role == ROLE_TARGET:
                last_target_harmony = harmony_key
            previous_melody_midi = melody_note.midi_note()
            # The texture decides which grips are *available* on this step. It is not a
            # term in the cost, so a fill cannot be outbid for being in position - the
            # point is that fewer notes are played here, not that this shape is better.
            slot_grips = grips if texture == "uniform" else texture_grips[role]

            # A walking-bass **fill** is the melody alone, and so is a target no
            # shell can sound. Both take the same route, which is the route an `NC`
            # step already takes - `get_melody_only_voicing` rather than grip lookup.
            # Two things make it a branch rather than a missing case:
            #
            # - the fill's grip tuple is *empty*, so the generic path would read "no
            #   candidates" as a failure and promote the fill to a target, which is
            #   the exact opposite of the texture ("nothing under the passing note");
            # - `grips=("shell",)` is the whole target tuple, so a melody with no
            #   shell - D over Bbm7, the B section's bar-10 appoggiatura - would be
            #   dropped with only a warning. Losing a note of the tune is worse than
            #   a thin one, so the step survives as melody plus thumb.
            #
            # `melody_only` stays **False** here: the step does have a harmony, it is
            # simply not being spelled out. Setting it would make the annotation read
            # "(no chord - melody alone)" and claim a lie.
            if texture == "walking_bass" and role == ROLE_FILL:
                solo_voicing = cls.get_melody_only_voicing(
                    melody_note, prefer=top_strings
                )
                if solo_voicing is not None:
                    fill = ArrangementStep(
                        chord=name,
                        melody=note_str,
                        voicing=solo_voicing,
                        grip="melody",
                        partial=False,
                        bar=bar,
                        beat=beat,
                        duration=duration,
                        role=role,
                        metric_weight=weight,
                        bass_only=slot.bass_only,
                    )
                    cls._attach_bass(fill, slot.bass, arrangements)
                    arrangements.append(fill)
                    continue
                # An unreachable melody is genuinely unplayable, so fall through to
                # the harmonised path rather than inventing one.

            # A NO_CHORD step carries melody but no harmony: it is voiced as the
            # melody alone. This happens before any chord logic, so there is no
            # non-chord-tone strategy, no substitute chord and no warning.
            if chord_type == NO_CHORD or name == NO_CHORD:
                solo_voicing = cls.get_melody_only_voicing(melody_note, prefer=top_strings)
                if solo_voicing is None:
                    print(
                        f"Warning: melody {note_str} is unreachable on any string; "
                        f"skipping the no-chord step"
                    )
                    continue
                # get_melody_only_voicing may have dropped the note an octave to stay
                # below HIGH_FRET_LIMIT. Compare the pitch that actually sounds rather
                # than the fret number: an octave-down note lands at a *lower* fret, so
                # only the sounding pitch reveals that the transposition happened.
                sounding_midi = max(solo_voicing.midi_notes())
                written_midi = melody_note.midi_note()
                transposed = (
                    note_str
                    if sounding_midi == written_midi
                    else _note_name(written_midi - 12)
                )
                arrangements.append(ArrangementStep(
                    chord=name,
                    melody=transposed,
                    voicing=solo_voicing,
                    original_melody=(
                        None if transposed == note_str else note_str
                    ),
                    melody_only=True,
                    bar=bar,
                    beat=beat,
                    duration=duration,
                    role=role,
                    metric_weight=weight,
                ))
                # An `NC` bar is still a place the thumb walks: the walk reads the last
                # known harmony (or skips), and the melody-alone shape leaves every bass
                # string free. Attaching it here rather than only on harmonised steps is
                # what keeps a bar of no-chord melody from being a hole in the walk.
                arrangements[-1].bass_only = slot.bass_only
                cls._attach_bass(arrangements[-1], slot.bass, arrangements)
                continue

            # Everything up to choosing a shape is shared with the corpus loader,
            # which needs the same candidates but honours a slash bass first. See
            # prepare_step.
            prepared = cls.prepare_step(
                progression, index,
                previous=arrangements[-1].voicing if arrangements else None,
                previous_chord=arrangements[-1].chord if arrangements else None,
                top_strings=top_strings,
                non_chord_tone=non_chord_tone,
                fret_min=fret_min,
                fret_max=fret_max,
                grips=slot_grips,
            )
            if prepared is None:
                # A target under walking_bass has one grip and no second option, so a
                # melody no shell can sound (D over Bbm7 - the major 3rd over a minor
                # chord, which `NON_CHORD_TONE_EXTENSIONS` has no route for) would be
                # *dropped*, with a warning as the only sign. The melody-alone route a
                # fill takes is the right one here too: the note of the tune survives,
                # the thumb still walks, and the harmony is stated at the next target.
                if texture == "walking_bass":
                    solo_voicing = cls.get_melody_only_voicing(
                        melody_note, prefer=top_strings
                    )
                    if solo_voicing is not None:
                        step = ArrangementStep(
                            chord=name,
                            melody=note_str,
                            voicing=solo_voicing,
                            grip="melody",
                            partial=False,
                            bar=bar,
                            beat=beat,
                            duration=duration,
                            role=role,
                            metric_weight=weight,
                            bass_only=slot.bass_only,
                        )
                        cls._attach_bass(step, slot.bass, arrangements)
                        arrangements.append(step)
                        continue
                # A fill slot with nothing thin to play must not lose the chord of
                # the tune - the whole point of the texture is a lighter *texture*,
                # never a missing harmony. So a fill that cannot be filled is
                # re-prepared as a principal note before it is reported as missing.
                # Same argument as NECK_FRET_MIN being a penalty and not a filter.
                if role == ROLE_FILL and slot_grips != grips:
                    prepared = cls.prepare_step(
                        progression, index,
                        previous=arrangements[-1].voicing if arrangements else None,
                        previous_chord=arrangements[-1].chord if arrangements else None,
                        top_strings=top_strings,
                        non_chord_tone=non_chord_tone,
                        fret_min=fret_min,
                        fret_max=fret_max,
                        grips=grips,
                    )
                    if prepared is not None:
                        role = ROLE_TARGET
                if prepared is None:
                    print(
                        f"Warning: No valid drop-2 voicing found for {name} "
                        f"with melody {note_str}"
                    )
                    continue
            candidates = prepared.candidates
            chord_type = prepared.chord_type
            name = prepared.chord_name
            original_melody = prepared.original_melody
            strategy_used = prepared.strategy
            harmonized_as = prepared.harmonized_as
            is_non_chord_tone = prepared.is_non_chord_tone

            # The whole selection rule lives in voicing_cost. The first chord has no
            # previous shape to lead from, so it falls back to "somewhere comfortable on
            # the neck"; every later chord is scored against the one before it, which is
            # what keeps the hand from jumping and lets a melody hold its place by
            # changing strings.
            prev_voicing = arrangements[-1].voicing if arrangements else None
            # The tones the *written* chord allows, so the selector can prefer a
            # shape that is merely out of position over one that sounds a wrong note.
            # The root enables the bass-function tie-break in voicing_cost; it is None
            # for a chord whose name cannot be parsed, which simply leaves that
            # criterion unasked rather than guessing a bass.
            best_voicing = cls._best_voicing(
                candidates,
                prev_voicing,
                fret_min,
                fret_max,
                allowed_tones=ChordParser.get_chord_tones(
                    ChordParser.canonical_quality(chord_type), name
                ),
                root_pc=cls._chord_context(chord_type, name)[1],
            )
            # `candidates` is non-empty here (the step is skipped otherwise), so this
            # cannot fire. Written as an assertion rather than left to Optional
            # narrowing at every use below.
            assert best_voicing is not None
                
            # A melody that repeats the previous step's pitch is a soprano-only
            # re-strike: the shape is held, so the renderers show just the melody
            # string and leave the inner voices ringing. Compared on the sounding
            # pitch rather than the written name, because a step either side of this
            # may itself have been transposed down an octave.
            #
            # The harmony must be unchanged too. A note repeating across a *chord
            # change* is not a hold: the inner voices ringing belong to the chord
            # the hold started on, so printing the new chord's name over a single
            # note claims a harmony that is not sounding. Those steps are
            # harmonised against the new chord instead, which is what the voicing
            # already does - only the rendering was discarding it.
            previous_step = arrangements[-1] if arrangements else None
            repeated = bool(
                previous_step is not None
                and not previous_step.melody_only
                and max(previous_step.voicing.midi_notes()) == max(best_voicing.midi_notes())
                and sounding_harmony(previous_step)
                == normalised_harmony(name, harmonized_as)
            )

            arrangements.append(ArrangementStep(
                chord=name,
                # The transposed pitch when the step was moved down an octave, so the
                # step reports what actually sounds; original_melody keeps the written one.
                melody=prepared.melody,
                voicing=best_voicing,
                non_chord_tone=is_non_chord_tone,
                strategy=strategy_used,
                harmonized_as=harmonized_as,
                original_melody=original_melody,
                repeated=repeated,
                grip=best_voicing.grip,
                # A shell or a duo leaves part of the chord unsounded, so the chord name
                # printed above the step describes the harmony rather than every note in
                # it. The renderers annotate this.
                #
                # Counted over the **upper voices**: the thumb is merged after this, so
                # a shell plus a bass note is still a shell and stays annotated
                # "(shell - 3rd & 7th, partial)". The merge happens below, which is what
                # makes that true by ordering rather than by a second count.
                partial=len(best_voicing.active_frets()) < 4,
                bar=bar,
                beat=beat,
                duration=duration,
                role=role,
                metric_weight=weight,
                # Decision B: this slot exists for the thumb. The upper voices are held
                # across it by the renderers rather than re-struck, and the melody is
                # not re-attacked - the opposite of `repeated`, and never set together.
                bass_only=slot.bass_only,
            ))
            # Select first, merge after: the bass is written into the fret vector only
            # once `_best_voicing` has returned, so it cannot enter the cost tuple by
            # construction rather than by discipline.
            cls._attach_bass(arrangements[-1], slot.bass, arrangements)

        return arrangements

    @classmethod
    def _attach_bass(
        cls,
        step: ArrangementStep,
        note: Optional[BassNote],
        arrangements: List[ArrangementStep],
    ) -> None:
        """
        Merges one walked beat into a step: records it, then places it on a string.

        Deliberately after selection (see the caller). Two independent failures are
        both handled the same way - **the step survives and the bass is reported**:

        - no candidate string survives `_place_bass`'s filters, so there is nowhere to
          put the thumb. Same argument as the neck window being a penalty rather than
          a filter: losing a step is worse than losing its bass.
        - a step that already carries a bass, which cannot happen while the union is
          one walked note per slot, but is checked rather than assumed.

        The previous thumb note is the search's continuity term, so a line does not
        leap octaves between beats purely because a nearer-in-fret candidate happened
        to be two octaves away.
        """
        if note is None:
            return
        step.bass_role = note.role
        if step.bass is not None:
            return
        placed = _place_bass(
            step.voicing,
            note.pitch_class,
            previous_bass=_previous_bass(arrangements),
        )
        if placed is None:
            print(
                f"Warning: no bass string free below the melody for bass "
                f"{PITCH_CLASS_NAMES[note.pitch_class % 12]}; "
                f"the step keeps its upper voicing"
            )
            return
        midi, string_index, fret = placed
        step.bass = midi
        step.voicing.bass_midi = midi
        step.voicing.bass_string = string_index
        step.voicing.frets[string_index] = fret
        # `bass_pc` is the lowest sounding voice, which the thumb now is by
        # construction: it sounds below every upper voice, or it was not placed.
        step.voicing.bass_pc = midi % 12

    @classmethod
    def _next_resolution_melody(
        cls, progression: List[Tuple[str, str, str]], index: int
    ) -> Optional[str]:
        """
        The pitch the melody line resolves into: the first following step whose
        melody is a chord tone of its own chord (None when the phrase never
        resolves). Used to spell the dim7 substitution's root.
        """
        for note_str, chord_type, name in progression[index + 1:]:
            if cls.is_chord_tone(Note(note_str), chord_type, name):
                return note_str
        return None


def _step_annotation(step: ArrangementStep) -> str:
    """
    Returns the non-chord-tone annotation for a step, e.g. '-> Cmaj9 via extension'.

    A melody-only (no chord) step is annotated instead with '(no chord - melody
    alone)'. A step that was transposed down an octave to stay below
    HIGH_FRET_LIMIT is annotated with the written pitch, since its `melody` is the
    transposed note. Empty string for an ordinary chord tone. Shared by
    format_progression and the demonstration so the two renderings cannot drift
    apart.
    The bass annotation is appended by `_bass_annotation` on **every** path out of
    this function, including the early returns: a walking step can equally be a
    melody-only fill, a repeated melody or a partial shell, and a bass note that is
    only annotated on some of those would be a worse defect than no annotation at
    all. Steps with no bass - every step of every other texture - come back
    unchanged.
    """
    if step.melody_only:
        return _bass_annotation(step, " (no chord - melody alone)")
    if step.repeated:
        return _bass_annotation(step, " (melody repeated - single note)")
    if step.original_melody is not None:
        return _bass_annotation(
            step, f" (transposed down an octave from {step.original_melody})"
        )
    # A partial harmonisation is worth saying out loud: the chord name above the step
    # describes the harmony, not every note sounding under the melody, so a reader
    # counting strings would otherwise wonder where the rest of the chord went.
    if step.partial and not step.non_chord_tone:
        if step.grip == "interval":
            # A fill texture, so name the interval rather than the grip: the reader
            # needs to know it is a 6th under a passing note rather than that a chord
            # went missing, and the two notes are right there in the tab.
            #
            # The **upper** voices, because the thumb is not part of the interval - it
            # is a walking line underneath, and counting it would turn every
            # two-note fill under a bass into a seven-note "interval" that has no
            # name in the table and would silently render as "2 notes".
            upper = sorted(step.voicing.upper_midi_notes())
            size = (upper[-1] - upper[0]) % 12 if len(upper) == 2 else 0
            return _bass_annotation(
                step, f" (interval fill - {_INTERVAL_NAMES.get(size, '2 notes')}, partial)"
            )
        if step.grip == "duo":
            return _bass_annotation(step, " (root & 5th duo - partial)")
        return _bass_annotation(step, f" ({step.grip} - 3rd & 7th, partial)")
    if not step.non_chord_tone:
        return _bass_annotation(step)
    if step.harmonized_as:
        return _bass_annotation(
            step, f" (non-chord tone -> {step.harmonized_as} via {step.strategy})"
        )
    return _bass_annotation(step, " (non-chord tone)")


def _bass_annotation(step: ArrangementStep, existing: str = "") -> str:
    """Appends the walking-bass role and motion to another step's annotation.

    The role is worth printing because the thumb line is no longer uniformly chord
    tones - two thirds of the notes in a textbook walk are extensions or chromatic
    approaches - so a reader counting strings would otherwise wonder why the bass is
    not playing the chord the name above it says.

    The motion needs the *previous* step, which `_step_annotation` is not given, so
    it is spelled from the step alone as `Ab (approach)`: enough to say what the note
    is for, which is the part that is not visible in the tab. `format_progression`
    prints one step per line and the chord name is already there, so a reader can
    see the descent by eye.

    Returns `existing` unchanged when the step carries no bass, which is every step
    of every other texture - so this cannot affect existing output.
    """
    if step.bass is None:
        return existing
    spelled = _note_name(step.bass)
    role = step.bass_role or "walk"
    return f"{existing} (bass: {spelled}, {role})"


# --- Standard six-line staff tab ---

# What an unsounded string renders as when the caller asks to see mutes, and the
# width every fret cell is padded to. Two characters covers frets 0-18, which is
# the whole range the library allows, and it is the same convention tab_block()
# uses - so the two renderings put a fret in the same column.
_MUTED_CELL = "x"
_STAFF_CELL_WIDTH = 2

# A string that is not part of this step at all. A repeated melody strikes the
# soprano alone, and the rest are left blank rather than marked 'x': the player is
# not muting them, they are simply not played. This is the same blank the staff and
# HTML already use for a voice that is not struck, so a repeated note reads as a
# single note instead of as five mutes.
_BLANK_CELL = ""


def _cells_from_frets(frets: List[int]) -> List[str]:
    """
    Renders each fret as a one-character tab cell, muted strings as 'x'.

    A string that is sounding but not being struck is handled by the caller
    (_step_cells), which blanks it; this function renders a literal voicing.
    """
    return [_MUTED_CELL if fret < 0 else str(fret) for fret in frets]

def _tab_block_from_cells(cells: List[str]) -> List[str]:
    """Lays six one-character cells out as a six-line vertical tab block."""
    padded = [cell.rjust(2) for cell in cells]
    lines = []
    for string_index in range(len(cells) - 1, -1, -1):
        # The highest string is labelled with a lowercase 'e', the usual tab
        # convention, so the top and bottom lines of the block stay distinct.
        name = "e" if string_index == 5 else STRING_NAMES[string_index]
        lines.append(f"{name}|{padded[string_index]}-|")
    return lines


def _step_cells(step: ArrangementStep) -> List[str]:
    """The tab cells for one step, honouring step.repeated and step.bass_only.

    A repeated melody is played as a **single note**: only the soprano string is
    struck. Every other string is left blank rather than marked 'x', because the
    player is not being asked to mute anything - the other strings are simply not
    part of this step, and 'x' on five strings says more than the gesture does.

    `bass_only` is the mirror image and the same reasoning: the thumb alone strikes
    and every voice above it is held from the previous shape. A step that is *both*
    is a walking bass under a re-articulated melody, and it plays the soprano and
    the thumb - so the two rules compose rather than override one another, which is
    the case an `elif` chain would silently drop.

    The step still carries a full drop-2 `voicing`: the engine voice-leads from
    it and a caller wanting the literal shape still has `step.tab_line()`.
    """
    frets = step.voicing.frets
    partial = (step.repeated or step.bass_only) and not step.melody_only
    if not partial:
        return _cells_from_frets(frets)
    struck = set()
    if step.bass_only:
        struck.add(step.voicing.bass_string)
    if step.repeated:
        struck.add(step.voicing.soprano_string())
        # A repeated melody still moves the thumb: the bass is a moving voice, not a
        # held one, so blanking it here would silently delete the walking line.
        if step.voicing.bass_midi is not None:
            struck.add(step.voicing.bass_string)
    cells = [_BLANK_CELL] * len(frets)
    for string_index in struck:
        if string_index is not None and 0 <= string_index < len(frets):
            cells[string_index] = str(frets[string_index])
    return cells


# The whole-progression staff renderers live in `tabstaff`, which imports this
# module. They are exposed here through a module-level __getattr__ rather than a
# top-level `from tabstaff import ...`, because that would be an import cycle:
# importing `tabstaff` first would re-enter this half-initialised module and fail to
# find the names. PEP 562 resolves each name on first access instead, so
# `from arranger import format_tab_html` keeps working - the spelling the README,
# the tests and wjazzd all use - without a lazy import at every call site. This is
# the same lazy-import discipline main() uses for wjazzd, for the same reason.
_TABSTAFF_EXPORTS = {
    # name -> the module it lives in. The MusicXML and Guitar Pro renderers live in
    # `tabxml` and `tabgp`, which `tabstaff` re-exports, so resolving them through
    # `tabstaff` as well keeps one spelling for the whole rendering surface.
    "format_tab_staff": "tabstaff",
    "format_tab_html": "tabstaff",
    "write_tab_html": "tabstaff",
    "format_musicxml": "tabstaff",
    "write_musicxml": "tabstaff",
    "format_gp5": "tabstaff",
    "write_gp5": "tabstaff",
}


def __getattr__(name: str) -> Any:
    """Resolves the renderer modules on first access. See _TABSTAFF_EXPORTS."""
    if name in _TABSTAFF_EXPORTS:
        return getattr(importlib.import_module(_TABSTAFF_EXPORTS[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    """Lists the lazily-exported renderers alongside the module's own names."""
    return sorted(__all__)


def format_progression(steps: List[ArrangementStep], vertical: bool = False) -> str:
    """
    Renders an arranged progression as tab and returns it as a string.

    This is a pure renderer: it prints nothing and writes nothing to stdout, so
    the caller stays in control of the output.

    With vertical=False (the default) each step is one line, most compact first:

        Dm7      D5  x-x-10-10-10-10
        G7       B4  x-x-5-7-6-7
        Cmaj7    C5  x-x-9-9-8-8

    With vertical=True each step is rendered as a full six-line vertical tab
    block, preceded by its chord, melody and any non-chord-tone annotation.

    Args:
        steps: arrangement steps, typically from VoiceLeadingEngine.arrange_progression.
        vertical: render the six-line vertical tab instead of the one-line form.

    Returns:
        The rendered tab, with steps separated by newlines.
    """
    if not vertical:
        return "\n".join(
            f"{step.chord:<8} {step.melody:<3} "
            f"{_step_annotation(step)} {'-'.join(_step_cells(step))}".rstrip()
            for step in steps
        )

    blocks = []
    for step in steps:
        header = f"{step.chord} ({step.melody}){_step_annotation(step)}"
        blocks.append("\n".join([header, *_tab_block_from_cells(_step_cells(step))]))
    return "\n\n".join(blocks)


# --- Demonstration ---
def _print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    print(
        f"Chord: {step.chord:<8} | Melody: {step.melody:<3}{_step_annotation(step)} | "
        f"Tab [E-A-D-G-B-E]: {'-'.join(_step_cells(step))} | Melody string: {melody_string}"
    )


def main() -> None:
    """
    Entry point: the built-in demonstration, or a subcommand.

    With no arguments this prints the built-in demonstration arrangements.

    With `corpus` as the first argument it hands over to `wjazzd.corpus_cli`, the
    Weimar Jazz Database front end, which is where the transcribed-head feature
    lives. The import is deliberately lazy and inside the branch: the database
    module is optional glue over a 42 MB file that most users do not have, and
    `import arranger` must never depend on it.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "corpus":
        from wjazzd import corpus_cli

        raise SystemExit(corpus_cli(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "head":
        # The MusicXML importer, imported here for the same reason as the corpus
        # front end above: both are optional entry points, and neither may be a
        # cost - or a dependency - to somebody who only wants the library.
        from headxml import head_cli

        raise SystemExit(head_cli(sys.argv[2:]))

    engine = VoiceLeadingEngine()

    # Example 1: Minor ii - V - i cadence in C Minor (Dm7b5 -> G7b9 -> Cm7)
    # The staple progression for minor jazz standards (Autumn Leaves, Alone Together, Blue Bossa, etc.)
    minor_progression = [
        ("F5", "m7b5", "Dm7b5"),
        ("F5", "7b9", "G7b9"),
        ("Eb5", "m7", "Cm7")
    ]
    result_minor = engine.arrange_progression(minor_progression)

    print("\n--- MINOR ii - V - i ARRANGEMENT (Dm7b5 -> G7b9 -> Cm7) ---")
    for step in result_minor:
        _print_step(step)

    # Example 2: Major ii - V - I in C Major over a melody on the top string (D5 -> B4 -> C5)
    major_progression = [
        ("D5", "m7", "Dm7"),
        ("B4", "7", "G7"),
        ("C5", "maj7", "Cmaj7")
    ]
    result_major = engine.arrange_progression(major_progression)

    print("\n--- MAJOR ii - V - I ARRANGEMENT (Dm7 -> G7 -> Cmaj7) ---")
    for step in result_major:
        _print_step(step)

    # Example 3: The same low melody arranged two ways. Pinning grips=("drop2",) with
    # the two traditional soprano strings reproduces the library's original
    # four-string-only output, which is what a caller wants when they need a known
    # arrangement rather than the best one.
    #
    # The difference is the Cmaj7. D4 and C4 sit at the very bottom of the B string's
    # range, where the original engine put the whole phrase up at frets 2-3 on strings
    # A-D-G-B. With the G string available the last chord can drop to a three-note
    # shell on 5-4-3, an octave lower, and still sound its 3rd and 7th.
    low_progression = [
        ("D4", "m7", "Dm7"),
        ("D4", "7", "G7"),
        ("C4", "maj7", "Cmaj7")
    ]
    for label, kwargs in (
        ("every grip, frets 2-13", {}),
        ("drop-2 only, high E and B strings", {"top_strings": (5, 4), "grips": ("drop2",)}),
    ):
        print(f"\n--- LOW-REGISTER CADENCE, {label} (Dm7 -> G7 -> Cmaj7) ---")
        for step in engine.arrange_progression(low_progression, **kwargs):
            _print_step(step)

    # Example 4: Texture. The same four melody notes under Fmaj7, arranged twice.
    # Without timings every slot is a principal note and all four are full chords.
    # Given the rhythm, the `targets` texture states the harmony on beats 1 and 3 and
    # fills the notes between with a shell or an interval - the arranging guide's
    # method, and the difference between an arrangement and a chord list.
    texture_progression = [
        ("C5", "maj7", "Fmaj7"),
        ("E5", "maj7", "Fmaj7"),
        ("A4", "maj7", "Fmaj7"),
        ("F4", "maj7", "Fmaj7"),
    ]
    texture_timings = [(0, 1.0, None), (0, 1.5, None), (0, 2.0, None), (0, 3.0, None)]

    for label, kwargs in (
        ("no timing - every note is a chord", {}),
        (
            "texture=targets - chords on beats 1 and 3, fills between",
            {"timings": texture_timings, "texture": "targets"},
        ),
    ):
        print(f"\n--- TEXTURE: one bar of Fmaj7, {label} ---")
        for step in engine.arrange_progression(texture_progression, **kwargs):
            _print_step(step)

    # Example 5: Non-chord melody tones. Bar 2 of "All of Me" moves C5 -> D5 -> C5
    # over Cmaj7; D5 is the 9th, not a chord tone, so each strategy harmonises it
    # differently: as an extension (Cmaj9), as a Barry Harris dim7 substitution
    # (Bdim7), by holding the inner voices under the passing tone, or not at all
    # (the historical quality-only fallback).
    all_of_me = [
        ("C5", "maj7", "Cmaj7"),
        ("D5", "maj7", "Cmaj7"),
        ("C5", "maj7", "Cmaj7"),
    ]

    print("\n--- NON-CHORD MELODY TONES: 'All of Me' bar 2 (C5 -> D5 -> C5 over Cmaj7) ---")
    for strategy in VoiceLeadingEngine.NON_CHORD_TONE_STRATEGIES:
        print(f"  strategy: {strategy}")
        for step in engine.arrange_progression(all_of_me, non_chord_tone=strategy):
            _print_step(step)

    # Example 8: Tab rendering. format_progression() returns the tab as a string
    # and prints nothing itself, so callers choose what to do with it. Here it is
    # used once horizontally and once as vertical six-line tab blocks.
    print("\n--- TAB RENDERING: format_progression(), one line per chord ---")
    print(format_progression(result_major))

    print("\n--- TAB RENDERING: format_progression(vertical=True), six lines per chord ---")
    print(format_progression(result_major, vertical=True))

    # Example 8: The whole progression on one six-line staff. format_tab_staff()
    # is the standard reading order - high E on top, chord names above, barlines
    # between bars - so it is what a player would actually read off the page. These
    # steps carry no timing, so the chords fall on consecutive beats; a transcribed
    # head (see `arranger.py corpus --tab staff`) is spaced on its real rhythm.
    # The renderer is reached through the module's lazy export rather than imported
    # at the top, which is what keeps tabstaff importable on its own; see __getattr__.
    import tabstaff

    print("\n--- TAB RENDERING: format_tab_staff(), one progression on a six-line staff ---")
    print(tabstaff.format_tab_staff(result_major, show_melody=True))

    # Example 8: The same cadence with the timing the corpus loader supplies, so the
    # chords sit on their own beats and a barline falls between the two bars.
    timed_major = engine.arrange_progression(major_progression)
    for index, step in enumerate(timed_major):
        step.bar, step.beat, step.duration = index, 1.0, 1.0
    print("\n--- TAB RENDERING: format_tab_staff() on a timed progression, barline per bar ---")
    print(tabstaff.format_tab_staff(timed_major, show_melody=True, measures_per_line=1))


if __name__ == "__main__":
    main()


# The three renderers are re-exported lazily (see __getattr__), which a static
# checker cannot follow. A TYPE_CHECKING import gives it the real declarations, so
# `from arranger import format_tab_html` type-checks and IDEs resolve it, while at
# runtime the names still come from __getattr__ and never trigger an import cycle.
if TYPE_CHECKING:
    from tabstaff import (
        format_gp5,
        format_musicxml,
        format_tab_html,
        format_tab_staff,
        write_gp5,
        write_musicxml,
        write_tab_html,
    )

# Star-import support. This module never had an __all__, so `from arranger import *`
# used to export every public name; the lazy __getattr__ above hides the tabstaff
# renderers from that, so they are listed here explicitly. Keep it in step when
# adding a public name - test_dunder_all_matches_the_public_surface checks that.
__all__ = [
    "BASS_DEGREES_6432",
    "BASS_ROLE_ANCHOR",
    "BASS_ROLE_APPROACH",
    "BASS_ROLE_CONNECT",
    "BASS_ROLE_ENCLOSURE",
    "BASS_ROLE_HOLD",
    "BASS_STRING_INDICES",
    "BassNote",
    "DUO_DEGREES",
    "GRIP_MAX_SPAN",
    "GRIP_PREFERENCE",
    "GRIP_STRING_SETS",
    "HIGH_FRET_LIMIT",
    "MELODY_STRING_CHOICES",
    "MELODY_STRING_CHOICES_FULL",
    "NECK_FRET_MAX",
    "NECK_FRET_MIN",
    "NO_CHORD",
    "PITCH_CLASS_NAMES",
    "ROLE_FILL",
    "ROLE_TARGET",
    "SHELL_DEGREES",
    "STANDARD_TUNING",
    "STRING_NAMES",
    "TARGET_BEATS",
    "TEXTURE_GRIPS",
    "TEXTURE_STYLES",
    "ArrangementStep",
    "ChordParser",
    "GuitarFretboard",
    "StepPreparation",
    "VoiceLeadingEngine",
    "Voicing",
    "bass_cost",
    "format_progression",
    "format_gp5",
    "format_musicxml",
    "format_tab_html",
    "format_tab_staff",
    "main",
    "normalised_harmony",
    "sounding_harmony",
    "supported_string_sets",
    "write_musicxml",
    "write_tab_html",
    "write_gp5",
]