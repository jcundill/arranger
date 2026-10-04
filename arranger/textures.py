"""Metric roles and textures: what a slot is *for*.

The arranging guide's method has a shape the cost tuple cannot express: a full
chord belongs on the *principal* melody notes, and the notes between are filled
with something lighter. `voicing_cost` ranks completeness above position, so with
no rhythm at all a bar of running eighths comes out as eight re-struck four-note
chords - a chord list, not an arrangement.

The fix works by changing *which grips are on the table*, not by adding a term to
the cost. "Play fewer notes here" is not a preference competing against "stay in
position"; it is a change of what may be chosen at all, and putting it in the cost
would let a four-fret position outbid a whole texture. That is why `TEXTURE_GRIPS`
is a table `steps` reads and hands to the generator, and why this module imports
nothing from `cost` and nothing from `grips` but the one preference tuple.

`ROLE_TARGET` and `ROLE_FILL` are *defined* in `tuning` and re-exported here,
because `Voicing.role` and `ArrangementStep.role` both default to `ROLE_TARGET`
and `Voicing` sits below this module. One definition, two spellings.

The load-bearing line in this module is `_metric_weight` returning **-1** when
there is no timing at all. A caller that does not know where its notes fall has
not told us the note is weak; it has told us nothing, and treating the two the same
would thin out every hand-written progression. That one value is what makes the
feature opt-in: with no `timings` every slot is a target, and the output is
byte-identical to what it always was.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .grips import GRIP_PREFERENCE
from .tuning import ROLE_FILL, ROLE_TARGET

__all__ = [
    "ALL",
    "GRID_AUTO",
    "GRID_CHARLESTON",
    "GRID_EVERY_NOTE",
    "GRID_FINAL_AND",
    "GRID_FREDDIE",
    "GRID_JOE_PASS",
    "GRID_PATTERNS",
    "GRID_POLICIES",
    "GRID_STYLES",
    "GridPattern",
    "LAST",
    "MELODY_ALTO",
    "MELODY_AUTO",
    "MELODY_BASS",
    "MELODY_ONLY_TEXTURES",
    "MELODY_POLICIES",
    "MELODY_SOPRANO",
    "MELODY_TENOR",
    "ROLE_FILL",
    "ROLE_TARGET",
    "TARGET_BEATS",
    "TEXTURE_GRIPS",
    "TEXTURE_STYLES",
    "THUMB_TEXTURES",
    "HARMONY_AUTO",
    "HARMONY_BUILT",
    "HARMONY_FULL",
    "HARMONY_GUIDE",
    "HARMONY_POLICIES",
    "HARMONY_ROOT",
    "HARMONY_SHELL_ROOT",
    "HARMONY_STYLES",
    "SUB",
    "grid_allowed",
    "grid_positions",
    "on_grid",
    "parse_grid",
    "resolve_grid",
    "VOICES_ALL",
    "VOICES_NONE",
    "VOICE_NAMES",
    "harmony_allowed",
    "melody_allowed",
    "parse_harmony",
    "parse_voices",
    "resolve_harmony",
    "resolve_voices",
    "voices_have_soprano",
]



# Texture styles, in the order that breaks a tie. `uniform` is the historical
# behaviour - every slot is a target and the cost tuple's completeness criterion
# decides, which is why it is the default and why existing output is unchanged.
TEXTURE_STYLES: Tuple[str, ...] = (
    "uniform", "targets", "walking_bass", "melody", "melody_bass",
)


# Textures that **harmonise nothing**: every slot is the melody alone, whatever the
# chord symbol says. Declared by name so that the four places that decide "does this
# slot become a single note" all read one table instead of each naming `walking_bass`
# in its own words - which is how a texture added to `TEXTURE_STYLES` silently misses
# a branch and harmonises nothing, or drops its melody.
#
# The pair differs in exactly one thing, which is the other table below: `melody` has
# no thumb line and `melody_bass` has one. Both are declared here rather than derived
# from `TEXTURE_GRIPS`, because a texture whose palettes happen to be empty is not the
# same claim as one that means to harmonise nothing.
MELODY_ONLY_TEXTURES: Tuple[str, ...] = ("melody", "melody_bass")

# Textures that build a **thumb line**: the walked-beat grid is unioned with the melody
# grid before the step loop, so a bar whose melody is one whole note still carries four
# bass notes. Separate from `MELODY_ONLY_TEXTURES` because `walking_bass` has a thumb
# and *does* harmonise, on its strong beats.
THUMB_TEXTURES: Tuple[str, ...] = ("walking_bass", "melody_bass")

# --- The melody axis: which voices the guitar plays ---
#
# The third axis, and the one this module exists alongside `bass`. Where the axes are
# orthogonal, and the orthogonality is the point rather than an accident of naming:
#
#   texture=   where notes fall and how thick the left hand is
#   bass=      the bass voice - none / anchors / walk
#   voices=    WHICH voices the guitar sounds - soprano, alto, tenor, bass
#
# A band setting is then a *combination* of axes, not a mode: `--bass none --voices
# alto,tenor` is a bassist on the root and a sax on the tune with the guitar comping the
# two middle voices. "I am sitting next to a bass player, so I want none of the 1s and 5s
# and none of the walking motion" is `bass="none"`; "and the melody is not mine either"
# is dropping `soprano` from `voices`. Leave either alone and it is the guitarist's job.
#
# The four voice names are **the SATB quartet**, highest to lowest, and they are named
# rather than numbered because the question is never "how many notes" but "which voices
# am I playing". The default is all four, so `voices=` names the same four parts a chord
# symbol implies.
MELODY_SOPRANO = "soprano"
MELODY_ALTO = "alto"
MELODY_TENOR = "tenor"
MELODY_BASS = "bass"

# The voices, in the order they are named in a four-part stack: highest first.
VOICE_NAMES: Tuple[str, ...] = (
    MELODY_SOPRANO, MELODY_ALTO, MELODY_TENOR, MELODY_BASS,
)

# What `--voices none` means. **Not** "the guitar plays nothing" - that would be silence,
# and silence is not an arrangement. It is the ordinary ensemble answer: the tune belongs
# to the horn, the root to the bass player, and the guitar takes the two voices in
# between. Named as a constant rather than spelled out at the call sites, because "the two
# middle voices" is one musical decision and not four strings.
VOICES_NONE: Tuple[str, ...] = (MELODY_ALTO, MELODY_TENOR)

# Every voice: the historical behaviour, the guitar playing the whole chord with the
# melody on top.
VOICES_ALL: Tuple[str, ...] = VOICE_NAMES

MELODY_AUTO = "auto"

# --- Reading and validating a `--voices` argument ---
#
# `voices` is a **comma-separated list of voice names**, not one identifier out of a fixed
# set, because the useful combinations are named by the *arranger*, not by us. The
# argument is parsed once, here, into a canonical tuple and everything downstream reads
# the tuple - which is also what keeps `MELODY_POLICIES` a registry rather than a flag.


def parse_voices(argument: str) -> Tuple[str, ...]:
    """A `--voices` argument as a canonical, ordered tuple of voice names.

    Voices come back **highest first**, always deduplicated, so `alto,tenor` and
    `tenor,alto` are one request rather than two that happen to agree - a caller listing
    voices in score order and one listing them bottom-up must not get two arrangements.

    Two spellings are accepted beyond the bare names, because both are things a player
    says: `auto`, which means *whatever this instrument does* and is resolved by
    `resolve_voices`, and `none`, which is `VOICES_NONE`.

    Raises `ValueError` on an unknown name. The rule is the library's: a spelling nobody
    recognises is a question, and answering it by dropping the voice would hand back a
    part missing something nobody asked it to drop.
    """
    text = argument.strip().lower()
    if text == MELODY_AUTO:
        return (MELODY_AUTO,)
    if text == "none":
        return VOICES_NONE
    if not text:
        raise ValueError(
            f"voices is empty; expected any of {VOICE_NAMES}, 'none', or 'auto'"
        )
    chosen: List[str] = []
    for part in text.split(","):
        name = part.strip().lower()
        if name == "none":
            chosen.extend(VOICES_NONE)
            continue
        if name == MELODY_AUTO:
            raise ValueError(
                f"'auto' cannot be combined with named voices in {argument!r}; it "
                f"means all of them on its own"
            )
        if name not in VOICE_NAMES:
            raise ValueError(
                f"Unknown voice {name!r}; expected any of {VOICE_NAMES}, "
                f"'none', or 'auto'"
            )
        if name not in chosen:
            chosen.append(name)
    if not chosen:
        raise ValueError(
            f"voices resolved to nothing in {argument!r}; the guitar has to play "
            f"something"
        )
    return tuple(name for name in VOICE_NAMES if name in chosen)


def voices_have_soprano(voices: Tuple[str, ...]) -> bool:
    """Whether the guitar sounds the melody under this voice selection.

    One predicate rather than a comparison against `VOICES_ALL` at each call site, named
    for the musical question rather than the data: the engine's job changes completely
    depending on whether the top voice is ours, because **the melody is what pins a
    voicing** - with no soprano there is no note to pin, which is why
    `get_comping_voicings` exists and takes none.
    """
    return MELODY_SOPRANO in voices


def melody_allowed(texture: str, voices: Tuple[str, ...]) -> Tuple[bool, str]:
    """Whether `texture` can carry this voice selection, and why not when it cannot.

    **The refusal rule, and it is derived rather than listed.** `MELODY_ONLY_TEXTURES`
    are the textures that harmonise nothing: every slot is the melody alone, whatever
    the chord symbol says (see `TEXTURE_GRIPS`, where both of their palettes are the
    empty tuple). So a selection without the soprano is self-contradictory there - the
    texture *is* the melodic voice, and removing it leaves the guitar with nothing to
    play.

    Measured across this tree, `melody` and `melody_bass` are the only two that fail;
    every other texture keeps at least one voice to play. A selection that *does* keep the
    soprano is allowed everywhere, because then the guitar plays the tune as it always has.
    """
    if voices_have_soprano(voices):
        return True, ""
    if texture not in MELODY_ONLY_TEXTURES:
        return True, ""
    return False, (
        f"{texture} plays the melody and nothing else, so it cannot also give the "
        f"melody away - every slot would be empty. Try texture='targets' with "
        f"voices='alto,tenor' for a guide-tone comping part."
    )


def resolve_voices(
    voices: Tuple[str, ...], texture: str, diagnostics: Any
) -> Tuple[str, ...]:
    """The voices to actually play: validated, ordered, or refused with the guitar intact.

    `auto` resolves to `VOICES_ALL`, which is what keeps the axis inert. Note the one
    asymmetry with `bass`: `BASS_AUTO` reads the texture because `walking_bass` *means* a
    thumb line, whereas **no texture means "somebody else sings"** - a fact about the band
    rather than about the texture.

    A selection with **no soprano** is refused on a melody-only texture, and refused
    rather than degraded, on the rule `bass_allowed` follows: an arrangement that says
    nothing is worse than one that says something, and the caller is told which texture
    would work.
    """
    if voices == (MELODY_AUTO,):
        return VOICES_ALL
    allowed, reason = melody_allowed(texture, voices)
    if not allowed:
        diagnostics.warn(f"Warning: {reason}")
        return VOICES_ALL
    return voices


# The policies a named selection resolves to. A **registry** rather than a flag, for the
# reason `BASS_POLICY_ROLES` is one: the set of patterns is open and meant to stay open,
# and a named comping pattern - Freddie Green, Charleston - is a row here rather than
# another branch at each of the call sites that decide which voices sound. The voices a
# row keeps are stated with the same four names a caller passes, so the table and the
# argument vocabulary cannot drift apart.
MELODY_POLICIES: Dict[str, Tuple[str, ...]] = {
    MELODY_AUTO: VOICES_ALL,
    "none": VOICES_NONE,
}

# --- The harmony axis: which degrees the guitar states when it is NOT singing ---
#
# A **degree family**, and nothing else. It answers "what does this part say about the
# chord", not "which notes are on the guitar" and not "how many": arity still comes from
# the voice selection, and whether the tune is ours at all is a separate axis again. So
# the three are genuinely orthogonal, which is the whole point of having this table.
#
# The families are read from tables that already state what a bass may be and what a
# shell must sound, rather than re-derived here - the same rule the rest of the module
# follows, and the reason `guide` and `root` are the *shipped* behaviour rather than a
# description of it.
#
#   HARMONY_FULL       the chord in full: every tone the quality defines
#   HARMONY_GUIDE      both guide tones - the 3rd and the 7th
#   HARMONY_SHELL_ROOT both guide tones AND a root or 5th underneath them
#   HARMONY_ROOT       the lowest note only: a root, else a 5th
#
# **`shell_root` is the one that is new**, and it is the case the guide-tone table cannot
# express: `SHELL_DEGREES` says what must sound, `BASS_DEGREES_6432` says what may be the
# bottom, and a shape needing both is a claim neither table makes alone. Measured at 11 of
# 11 chords on the head in `tests/data/`, on the **existing** `(5,4,3)` shell sets, so it
# needs no new string sets and no new grip family.
HARMONY_FULL = "full"
HARMONY_GUIDE = "guide"
HARMONY_SHELL_ROOT = "shell_root"
HARMONY_ROOT = "root"

HARMONY_STYLES: Tuple[str, ...] = (
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_SHELL_ROOT,
    HARMONY_ROOT,
)

#: The one harmony family this engine can already voice. The other three are named here
#: so the vocabulary exists and `harmony=` has something to validate against, but nothing
#: is built on them yet - see `docs/comping-styles.md` §4.1 and §8 Stage C. `full` is the
#: historical chord-melody, which the ordinary grip route voices rather than the comping
#: generator, so it is **not** the comping route's default either.
HARMONY_BUILT: Tuple[str, ...] = (HARMONY_GUIDE,)

HARMONY_AUTO = "auto"

#: `auto` means "whatever this part already says", which is the shipped behaviour and the
#: reason the axis is inert by default. It resolves to `guide` rather than to `full`
#: because the comping generator is only reached when the guitar is *not* singing, and a
#: part that states no harmony is stated with its guide tones.
HARMONY_POLICIES: Dict[str, str] = {
    HARMONY_AUTO: HARMONY_GUIDE,
}


def parse_harmony(argument: str) -> str:
    """A `harmony` argument as one of `HARMONY_STYLES`, or the `HARMONY_AUTO` sentinel.

    A single identifier out of a closed set rather than a comma-separated list, because
    unlike the voice selection this axis names **one** degree family and not a subset of
    roles in a stack. Parsed here rather than inline at the call site so the vocabulary
    and the refusal live in one place, on the same rule as `parse_voices`.

    Raises `ValueError` on an unknown name: a spelling nobody recognises is a question,
    and answering it by falling back to `guide` would hand back a part that states
    something other than what was asked for.
    """
    text = argument.strip().lower()
    if text == HARMONY_AUTO:
        return HARMONY_AUTO
    if text not in HARMONY_STYLES:
        raise ValueError(
            f"Unknown harmony {argument!r}; expected any of "
            f"{', '.join(HARMONY_STYLES)}, or 'auto'"
        )
    return text


def resolve_harmony(
    harmony: str, voices: Tuple[str, ...], diagnostics: Any
) -> str:
    """The degree family to actually voice: `auto` resolved, validated, or refused.

    `auto` resolves through `HARMONY_POLICIES`, which is what keeps the axis inert: the
    resolved value is the shipped behaviour, so an arrangement that names no harmony is
    byte-identical to one that never had the axis.

    A combination the generator cannot voice is **refused rather than degraded**, on the
    rule `melody_allowed` and `bass_allowed` both follow: an arrangement that says
    something other than what was asked for is worse than one that says nothing, and the
    caller is told which selection would work. Returning `guide` here is deliberate and
    is the *inert* answer rather than a silent substitution - it is what the part said
    before this axis existed.
    """
    resolved = HARMONY_POLICIES.get(harmony, harmony)
    allowed, reason = harmony_allowed(resolved, voices)
    if not allowed:
        diagnostics.warn(f"Warning: {reason}")
        return HARMONY_GUIDE
    return resolved


def harmony_allowed(harmony: str, voices: Tuple[str, ...]) -> Tuple[bool, str]:
    """Whether this degree family can be voiced under this voice selection, and why not.

    **Derived rather than listed**, from two facts rather than a table someone has to
    remember to extend. A family that asks for the bass voice *alone* is a one-note
    claim, so it can only be voiced by a selection that names one voice; and the
    converse, a family sounding three notes, needs a selection with room for three.

    Checked before any voicing work, on the library's standing rule that an impossible
    request is answered by saying what would work rather than by dropping something the
    caller asked for.
    """
    if harmony == HARMONY_ROOT:
        if voices != (MELODY_BASS,):
            return False, (
                f"harmony={HARMONY_ROOT} is a bass voice on its own, so it needs a "
                f"selection of exactly one voice naming the bass "
                f"(voices={MELODY_BASS}); {', '.join(voices)} asks for "
                f"{len(voices)} note(s)"
            )
        return True, ""
    if harmony == HARMONY_SHELL_ROOT and len(voices) < 3:
        return False, (
            f"harmony={HARMONY_SHELL_ROOT} sounds three notes - both guide tones and a "
            f"root or 5th under them - so it needs a selection with room for three; "
            f"{', '.join(voices)} asks for {len(voices)}"
        )
    return True, ""


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
    # `melody` is the lead sheet in, the tune out: every slot is the melody alone, so
    # nothing under it is ever harmonised and the chord name above it is context rather
    # than a claim about what is sounding. It is a texture rather than a grip because
    # "what may be played at all" is the question it answers, and a grip would have to
    # win a cost comparison it should not be in - see `GRIP_PREFERENCE`.
    #
    # The empty tuple on **both** roles is the declaration, in the same words
    # `walking_bass`'s fill uses for its fills: `arrange_progression` reads `()` as "the
    # left hand plays nothing" and routes the slot through `get_melody_only_voicing`.
    # It is never absent and never approximated by an empty list elsewhere.
    "melody": {"target": (), "fill": ()},
    # The same line with a thumb under it, and no shell above it anywhere: a bass voice
    # walking under the tune with nothing harmonising it. `walking_bass` states the
    # harmony on its strong beats and leaves the thumb to fill the gaps; this one is
    # thumb-and-melody throughout, which is why its **target** palette is empty too and
    # not only its fill's.
    "melody_bass": {"target": (), "fill": ()},
}

# --- The grid axis: where a chord FALLS inside the bar -------------------------
#
# The second half of a comping style, and the half `harmony=` cannot express. The
# degree family says *what* a stab states; this says *where* one lands. They are
# orthogonal on purpose: a full chord on every beat and a shell on the ands are
# two different questions, and a user who wants one does not thereby get the other.
#
# **Positions are bar-relative, and `LAST` is what makes that true.** The upbeat of
# the bar's final beat is one musical idea that lands on a different beat number in
# every metre - 4.5 in 4/4, 2.5 in 2/2, 3.5 in 3/4 - so a pattern that spells it
# `[(4, SUB)]` would look to a 2/2 head like it named a beat that does not exist.
# Spelling it `[(LAST, SUB)]` and resolving `LAST` against the metre is the same
# figure in all three. This is the `TARGET_BEATS` lesson applied to a rhythm: name
# *the position*, never a literal beat number.
#
# Subdivision is an **integer count of eighths**, not a float, for the same reason
# `_BEAT_EPSILON` exists: a notated position is a float in practice (a 3/4 bar's
# second beat is 1.666...) and comparing floats for equality to decide whether a
# chord lands is a comparison that will eventually be false for the wrong reason.
GRID_EVERY_NOTE = "every_note"
GRID_FREDDIE = "freddie"
GRID_CHARLESTON = "charleston"
GRID_JOE_PASS = "joe_pass"
GRID_FINAL_AND = "final_and"

# The subdivision of a beat, in whole eighths. Integer on purpose - see above.
SUB = 1

# Beat sentinels, so a pattern can name a position rather than a beat number.
LAST = 0   # the metre's FINAL beat, resolved against `beats_per_bar`
ALL = -1   # every beat the metre has; composes with a subdivision (`(ALL, SUB)`)


@dataclass(frozen=True)
class GridPattern:
    """One rhythm grid: the within-bar positions a chord may fall on.

    `positions` is a tuple of `(beat, eighths)` pairs, where `beat` is a beat
    number, `LAST` or `ALL`, and `eighths` is an integer count of eighths from that
    beat (`0` is the beat, `SUB` is its upbeat).

    **`bar_relative` is a property of the pattern, not a comment**, and it earns its
    place by saying whether a *silence* is the arranger's mistake. A bar-relative
    pattern (`freddie`, `final_and`) is playable in any metre - `LAST` resolves, so
    it never asks for a beat that is not there. A metre-relative one (`charleston`,
    `joe_pass`) is a named figure of a particular metre: asked of a 2/2 bar it may
    be wrong, and that is the arranger's calling, not a defect in the engine. Left
    implicit, a pattern that places nothing reads as a bug; recorded as data, it is
    a fact about the pattern and the refusal below can name it.
    """

    positions: Tuple[Tuple[int, int], ...]
    bar_relative: bool


GRID_STYLES: Tuple[str, ...] = (
    GRID_EVERY_NOTE,
    GRID_FREDDIE,
    GRID_CHARLESTON,
    GRID_JOE_PASS,
    GRID_FINAL_AND,
)

#: The named grids. `every_note` is the **shipped** behaviour - one chord per written
#: melody note - and is what keeps the axis inert: an arrangement naming no grid is
#: byte-identical to one from before this axis existed.
#:
#: `joe_pass` is not invented here. It is
#: [history/Arranging_Guide.md](history/Arranging_Guide.md) §"Joe Pass", which
#: specifies the chord pops living "primarily on the and of beats" - so the grid is
#: every beat's upbeat, and the walking thumb underneath it is the **bass axis**,
#: not this one. Keeping those separate is what lets `bass=walk` compose with any
#: grid instead of being baked into one row.
GRID_PATTERNS: Dict[str, GridPattern] = {
    GRID_EVERY_NOTE: GridPattern(positions=(), bar_relative=True),
    GRID_FREDDIE: GridPattern(positions=((ALL, 0),), bar_relative=True),
    GRID_FINAL_AND: GridPattern(positions=((LAST, SUB),), bar_relative=True),
    GRID_CHARLESTON: GridPattern(
        positions=((1, 0), (2, SUB)), bar_relative=False
    ),
    GRID_JOE_PASS: GridPattern(positions=((ALL, SUB),), bar_relative=False),
}

#: `auto` means "wherever a chord already fell", which is the shipped behaviour and
#: the reason the axis is inert by default. It resolves to `every_note` because a
#: head read from a score gives every written note its own slot, and that is what
#: this axis must reproduce exactly when nobody has asked for anything.
GRID_AUTO = "auto"
GRID_POLICIES: Dict[str, str] = {GRID_AUTO: GRID_EVERY_NOTE}


def parse_grid(argument: str) -> str:
    """A `grid` argument as one of `GRID_STYLES`, or the `GRID_AUTO` sentinel.

    The same rule as `parse_harmony`: a single name out of a closed set, and
    `ValueError` on anything else. A pattern name is a musical claim about where a
    chord lands, so guessing one would return a part that comps somewhere the caller
    did not ask for - worse than refusing, and worse than silence.
    """
    text = argument.strip().lower()
    if text == GRID_AUTO:
        return GRID_AUTO
    if text not in GRID_STYLES:
        raise ValueError(
            f"Unknown grid {argument!r}; expected any of "
            f"{', '.join(GRID_STYLES)}, or 'auto'"
        )
    return text


def grid_positions(
    grid: str, beats_per_bar: int
) -> Tuple[Tuple[int, Tuple[float, ...]], ...]:
    """Resolve a named grid against a metre: beat numbers paired with their beats.

    Returns one entry per distinct beat the pattern touches, each holding every
    within-bar position on that beat. `ALL` expands to every beat of the bar and
    `LAST` to the metre's final beat, which is the whole reason those two sentinels
    exist - `final_and` is 2.5 in 2/2 and 4.5 in 4/4 without being written twice.

    An **empty** result means the pattern places nothing in this metre, and that is
    a real answer rather than a bug: `charleston` is a 4/4 figure, so asked of a
    2/2 bar it has nowhere to go. `grid_allowed` is what turns that into a warning
    naming the pattern; this function only reports the geometry.
    """
    pattern = GRID_PATTERNS[grid]
    beats: Dict[int, List[float]] = {}
    for beat, eighths in pattern.positions:
        if beat == ALL:
            numbers: Tuple[int, ...] = tuple(range(1, beats_per_bar + 1))
        elif beat == LAST:
            numbers = (beats_per_bar,)
        else:
            # A literal beat the metre does not have is dropped rather than clamped:
            # clamping would silently turn `charleston` asked of a 2/2 bar into a
            # *different* figure that happens to fit, which is the guessing this
            # library refuses everywhere else.
            numbers = (beat,) if 1 <= beat <= beats_per_bar else ()
        for number in numbers:
            # 1-based, because that is what a beat *is* everywhere else in this
            # library: `headxml` writes `1.0 + ...` for a downbeat and
            # `_metric_weight` compares against `TARGET_BEATS = (1, 3)`. Subtracting
            # one here would make `final_and` resolve to 1.5 in a 2/2 bar, which is
            # the upbeat of the *first* beat - measured, not reasoned: the whole
            # point of the `LAST` sentinel is that the same pattern lands on the
            # bar's final beat in every metre.
            beats.setdefault(number, []).append(number + eighths * 0.5)
    return tuple(
        (number, tuple(sorted(set(positions))))
        for number, positions in sorted(beats.items())
    )


# How close a notated beat has to be to a whole beat to count as it. A 2/2 bar's
# eighths land on 1.0, 1.5, 2.0, 2.5, and a 3/4 bar's on 1.0, 1.666..., so an exact
# comparison would call almost none of them downbeats. Measured in beats, not in
# quarters, so this is the same tolerance in any metre.
_BEAT_EPSILON = 1e-6


def on_grid(beat: Optional[float], grid: str, beats_per_bar: int) -> bool:
    """Whether a chord falls on this beat of the bar under this grid.

    **`beat=None` is on the grid.** A slot nobody located has no position to be off,
    and this is the rule `_metric_weight` already follows with its `-1`: not being
    told where a note falls is not being told it is weak. Returning `True` is what
    keeps a hand-written progression - which carries no timings at all -
    byte-identical, and it is the same reason the default is inert.

    `every_note` is `True` for every beat, which is what makes the axis inert by
    default rather than merely defaulting to something harmless.
    """
    if beat is None or grid == GRID_EVERY_NOTE:
        return True
    target = float(beat)
    return any(
        abs(target - position) <= _BEAT_EPSILON
        for _number, positions in grid_positions(grid, beats_per_bar)
        for position in positions
    )


def grid_allowed(grid: str, beats_per_bar: int) -> Tuple[bool, str]:
    """Whether this grid places at least one chord in this metre, and why not.

    **Derived rather than listed**, and the *direction* of the test is the point. The
    question asked is one-directional - can the pattern be expressed at all here? -
    and deliberately not "does every bar carry a note on one of its positions". The
    second question has a correct answer of "no, and that is fine": a bar whose
    melody is all on the beat has nothing at 2.5 for `final_and` to land on, the
    melody-alone route handles it, and a warning would be noise. Only a pattern that
    places **nothing anywhere** is a real mismatch, and it is nearly always a
    metre-relative figure asked of a metre it was not written for.
    `every_note` is not a pattern with positions at all - it is the absence of a
    restriction - so it is **allowed unconditionally**. Reading it off
    `grid_positions` instead would report it as placing nothing in every metre,
    which is the false reading that this check exists to avoid: "places nothing" and
    "has no positions to place" are different claims about a pattern, and only the
    first is a mismatch.
    """
    if grid == GRID_EVERY_NOTE:
        return True, ""
    if grid_positions(grid, beats_per_bar):
        return True, ""
    if GRID_PATTERNS[grid].bar_relative:
        return False, (
            f"grid={grid} places no chord in a {beats_per_bar}-beat bar, and it is "
            f"a bar-relative pattern, which should resolve in any metre - so this "
            f"is a defect in the pattern rather than a mismatch with the metre"
        )
    return False, (
        f"grid={grid} is a metre-relative figure and places no chord in "
        f"{beats_per_bar}/4: it is right, or it is a figure of another metre asked "
        f"of this one. Try a bar-relative pattern such as 'freddie' or "
        f"'final_and', or grid=every_note"
    )


def resolve_grid(grid: str, beats_per_bar: int, diagnostics: Any) -> str:
    """The grid to actually place chords on: `auto` resolved, validated, or refused.

    The same two-step shape as `resolve_harmony` and for the same reason: the
    resolved value is the shipped behaviour, so an arrangement naming no grid is
    byte-identical to one from before this axis existed.

    A grid this metre cannot express is **refused rather than degraded**, on the rule
    every axis in this module follows. The fallback is `every_note` - one chord per
    written note - which is the *inert* answer and what the part said before this
    axis existed, rather than a silent substitution of some other figure that does
    fit.
    """
    resolved = GRID_POLICIES.get(grid, grid)
    allowed, reason = grid_allowed(resolved, beats_per_bar)
    if not allowed:
        diagnostics.warn(f"Warning: {reason}")
        return GRID_EVERY_NOTE
    return resolved


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


def _roles_for_slot(
    weight: int,
    texture: str,
    harmony_changed: bool = True,
    melody_moves: bool = False,
    has_thumb: bool = False,
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
    if has_thumb:
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
        #
        # `has_thumb` rather than the texture name, because the thumb line is now an
        # argument of its own (`bass=`): any texture may carry one. The reason this
        # branch exists is the role's, not the shell's - `is_bass_only` reads it to
        # decide whether a beat invented for the thumb holds the melody or re-strikes
        # it, and a beat invented for the thumb must hold it. A texture with no thumb
        # has no invented beats and no use for either role, so it falls through to the
        # metric rule below.
        if weight > 0 and (harmony_changed or melody_moves):
            return [ROLE_TARGET]
        return [ROLE_FILL]
    if weight > 0:
        return [ROLE_TARGET]
    return [ROLE_FILL]
