"""Metric roles and textures: what a slot is *for*.

The arranging guide's method has a shape the cost tuple cannot express: a full
chord belongs on the *principal* melody notes, and the notes between are filled
with something lighter. `voicing_cost` ranks completeness above position, so with
no rhythm at all a bar of running eighths comes out as eight re-struck four-note
chords - a chord list, not an arrangement.

The fix works by changing *which grips are on the table*, not by adding a term to
the cost. "Play fewer notes here" is not a preference competing against "stay in
position"; it is a change of what may be chosen at all, and putting it in the cost
would let a four-fret position outbid a whole texture. That is why `TEXTURE_ARITY`
is a policy `steps` reads and hands to the generator, and why this module imports
nothing from `cost` and nothing from `grips` but the preference tuple and the
string tables the family sizes are read off.

`ROLE_TARGET` and `ROLE_FILL` are *defined* in `tuning` and re-exported here,
because `Voicing.role` and `ArrangementStep.role` both default to `ROLE_TARGET`
and `Voicing` sits below this module. One definition, two spellings.

The load-bearing line in this module is `_metric_weight` returning **-1** when
there is no timing at all. A caller that does not know where its notes fall has
not told us the note is weak; it has told us nothing, and treating the two the same
would thin out every hand-written progression. That one value is what makes the
feature opt-in: with no `timings` every slot is a target, so the output is the one a
caller who names no texture gets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .grips import GRIP_PREFERENCE, GRIP_STRING_SETS, RIGHT_HAND_STRINGS
from .tuning import ROLE_FILL, ROLE_TARGET

__all__ = [
    "ALL",
    "GRID_ANCHORS",
    "GRID_CHARLESTON",
    "GRID_DEFAULT",
    "GRID_EVERY_NOTE",
    "GRID_FINAL_AND",
    "GRID_FREDDIE",
    "GRID_JOE_PASS",
    "GRID_PART_PATTERNS",
    "GRID_PATTERNS",
    "GRID_STYLES",
    "GRID_TIMELINE_PATTERNS",
    "GRID_WALK",
    "GridPattern",
    "LAST",
    "PART_BASS",
    "PART_CHORD",
    "PART_MELODY",
    "PART_NAMES",
    "PARTS_AUTO",
    "ROLE_FILL",
    "ROLE_TARGET",
    "TARGET_BEATS",
    "TEXTURE_ARITY",
    "FILL_THINNING",
    "FILL_ONLY_EXCLUDED",
    "THIN_ENTRIES",
    "families_up_to_arity",
    "families_up_to_with_thin",
    "TEXTURE_STYLES",
    "comping_arity",
    "derived_arity",
    "HARMONY_AUTO",
    "HARMONY_AUTO_POLICIES",
    "HARMONY_FULL",
    "HARMONY_GUIDE",
    "HARMONY_SHELL_ROOT",
    "HARMONY_STYLES",
    "SUB",
    "TICKS_PER_BEAT",
    "grid_allowed",
    "grid_defers_to_melody",
    "grid_positions",
    "grid_resolutions",
    "on_grid",
    "parse_grid",
    "resolve_grid",
    "families_for_arity",
    "grid_bass_pattern",
    "grid_chord_pattern",
    "grid_rows",
    "harmony_allowed",
    "parse_harmony",
    "parse_parts",
    "parts_has_melody_only",
    "parts_have_bass",
    "parts_have_chord",
    "parts_have_melody",
    "resolve_harmony",
    "resolve_parts",
    "texture_arity",
    "texture_palette",
]



# --- The texture axis: the chord part's arity, by metric weight --------------
#
# `texture=` owns **how many notes the chord part states**. It is not a grip list:
# the grip families are an internal search space over the chord part's degrees
# and the neck window ([docs/history/parts.md](../docs/history/parts.md) §4), keyed by the number
# of notes they sound under the melody. What remains a choice is the arity and
# the metric policy that varies it.
#
#   uniform   the most notes the arithmetic allows at that position - the whole
#             chord, and the shipped default
#   targets   the same maximum on a strong beat and a thinner shape between them
#   chord1    exactly one note under the melody
#   chord2    exactly two
#   chord3    exactly three
#
# `chord4` is not built: four notes under a melody is five strings, which the
# right hand's four digits cannot pluck. `docs/history/comping-styles.md` §9.4 holds the
# comping-route version of that shape, where there is no tune on top.
TEXTURE_STYLES: Tuple[str, ...] = (
    "uniform", "targets", "chord1", "chord2", "chord3",
)

#: The chord part's arity under each texture. `None` means **derived**: the most
#: notes the arithmetic allows at that position, which is the whole chord when the
#: parts leave room for it and a thinner shape when a thumb takes a string. A
#: fixed row is the arity the caller asked for, and the arithmetic still refuses a
#: selection it cannot fit.
TEXTURE_ARITY: Dict[str, Optional[int]] = {
    "uniform": None,
    "targets": None,
    "chord1": 1,
    "chord2": 2,
    "chord3": 3,
}

# --- The melody axis: which voices the guitar plays ---
#
# The third axis, and the one this module exists alongside `bass`. Where the axes are
# orthogonal, and the orthogonality is the point rather than an accident of naming:
#
#   parts=     WHICH parts the guitar takes - melody, bass, chord
#   texture=   the chord part's arity, by metric weight
#   harmony=   the chord part's degree order
#   grid=      when each part sounds - positions crossed with parts
#
# The three names are **parts in a band**, not voices in a stack: the melody is
# 0 or 1 note, the bass is 0 or 1 note, and the chord is 0..n - the arity
# `texture=` carries. Four strings may sound at once because the right hand has
# four digits (`grips.RIGHT_HAND_STRINGS`), so `melody + bass + chord <= 4` is
# arithmetic rather than a rule: a selection that does not fit is refused before
# anything is generated.
#
# A band setting is a *combination* of axes, not a mode: `parts=melody,chord`
# with `bass_style=root` is a bassist on the root and a horn on the tune with the
# guitar comping under it. Naming a part is a request for it to sound, and a
# policy named for a part the selection leaves out is refused naming the part
# that would work. Leave the axes alone and it is the guitarist's job.
PARTS_AUTO = "auto"

# The part names, in the order a canonical selection is written (order carries
# no meaning - see `parse_parts`).
PART_MELODY = "melody"
PART_BASS = "bass"
PART_CHORD = "chord"

PART_NAMES: Tuple[str, ...] = (PART_MELODY, PART_BASS, PART_CHORD)

def parse_parts(argument: str) -> Tuple[str, ...]:
    """A `parts` argument as a canonical tuple of part names.

    **Order carries no meaning**, so the result is canonicalised to
    `PART_NAMES` order: `parts=chord,bass` and `parts=bass,chord` are one
    request and must not produce two arrangements.

    `auto` is the shipped default and names every part - the tune on top, the
    thumb underneath, and a chord part whose arity `texture=` states. Any other
    spelling is a comma-separated list of the names above.

    Raises `ValueError` on an unknown name, on an empty argument, and on `auto`
    combined with named parts. The rule is the library's: a spelling nobody
    recognises is a question, and answering it by dropping a part would hand
    back an arrangement missing something nobody asked it to drop. `none` is
    refused for the same reason rather than expanded: it named a voice
    selection, and a selection that names no part has no line to state.
    """
    text = argument.strip().lower()
    if text == PARTS_AUTO:
        return (PARTS_AUTO,)
    if not text:
        raise ValueError(
            f"parts is empty; expected any of {PART_NAMES}, or 'auto'"
        )
    chosen: List[str] = []
    for part in text.split(","):
        name = part.strip().lower()
        if name == PARTS_AUTO:
            raise ValueError(
                f"'auto' cannot be combined with named parts in {argument!r}; "
                f"it means all of them on its own"
            )
        if name not in PART_NAMES:
            raise ValueError(
                f"Unknown part {name!r}; expected any of {PART_NAMES}, or 'auto'"
            )
        if name not in chosen:
            chosen.append(name)
    if not chosen:
        raise ValueError(
            f"parts resolved to nothing in {argument!r}; the guitar has to "
            f"take at least one part"
        )
    return tuple(name for name in PART_NAMES if name in chosen)


def resolve_parts(parts: Tuple[str, ...]) -> Tuple[str, ...]:
    """The parts to actually take: `auto` expanded, everything else as parsed.

    `auto` expands to `PART_NAMES`, which is what keeps the axis inert: an
    arrangement naming no parts builds the tune over a full chord part, the
    arrangement this library has always built.
    """
    if parts == (PARTS_AUTO,):
        return PART_NAMES
    return parts


def parts_have_melody(parts: Tuple[str, ...]) -> bool:
    """Whether the guitar takes the tune.

    One predicate rather than a comparison against `PART_NAMES` at each call
    site, named for the musical question rather than the data: the engine's job
    changes completely depending on whether the tune is ours, because **the
    melody is what pins a voicing** - with no melody part there is no note to
    pin, which is why the comping generator takes none.

    **It is half of the engine's route, not the whole of it.** The route is
    asked **per slot** - `sings_here = parts_have_melody(parts) and a note
    sounds here` - so a melody-naming selection still comps the grid positions
    its tune does not articulate.
    """
    return PART_MELODY in parts


def parts_have_bass(parts: Tuple[str, ...]) -> bool:
    """Whether the guitar takes the bottom - the part the thumb realises.

    The part and the digit are different facts: a shape with no bass line still
    has its lowest note taken by the thumb (`docs/history/fingering.md` §2.5), so this
    asks about the music and not about the right hand.
    """
    return PART_BASS in parts


def parts_have_chord(parts: Tuple[str, ...]) -> bool:
    """Whether the guitar takes the harmonisation between melody and bass."""
    return PART_CHORD in parts


def parts_has_melody_only(parts: Tuple[str, ...]) -> bool:
    """Whether the selection takes the tune and no chord part.

    `parts=melody` is the tune with no left hand under it, and
    `parts=melody,bass` is the same line with a thumb under it. **The chord part
    is what this rules out, and the bass part is deliberately not** - the thumb
    has its own axis (`bass_style=`), and a line with a thumb under it is still
    one note's worth of left hand.
    """
    return PART_MELODY in parts and PART_CHORD not in parts


# --- The harmony axis: the chord part's degree order -------------------------
#
# A **degree order**, and nothing else. It answers "in which order does the chord part
# state its degrees", not "how many notes are on the guitar": the arity is `texture=`'s,
# and the order is `TONE_PRIORITY`'s row for the quality, sliced to that arity. A reduced
# shape therefore gives up the order's **tail** (docs/history/parts.md §4).
#
# The orders are read from tables that already state what a bass may be and what a shell
# must sound, rather than re-derived here - the same rule the rest of the module follows,
# and the reason `guide` is the *shipped* behaviour rather than a description of it.
#
#   HARMONY_FULL       the whole row: every tone the quality defines, in priority order
#   HARMONY_GUIDE      both guide tones - the 3rd and the 7th
#   HARMONY_SHELL_ROOT both guide tones AND a root or 5th underneath them
#
# **`shell_root` is the case the guide-tone table cannot express**: `SHELL_DEGREES` says
# what must sound, `BASS_DEGREES_6432` says what may be the bottom, and a shape needing
# both is a claim neither table makes alone. It is reachable on the **existing** `(5,4,3)`
# shell sets, so it needs no new string sets and no new grip family - the measurement is
# in `docs/history/comping-styles.md` §4.1. At an arity of two it **is** the guide pair, which is
# why the old "room for three" refusal is gone rather than relocated: a reduced shape
# gives up the tail of the order rather than needing a different one.
HARMONY_FULL = "full"
HARMONY_GUIDE = "guide"
HARMONY_SHELL_ROOT = "shell_root"

HARMONY_STYLES: Tuple[str, ...] = (
    HARMONY_FULL,
    HARMONY_GUIDE,
    HARMONY_SHELL_ROOT,
)

#: The arity each named order supplies, for the check that a texture asks for no more
#: degrees than the order names. `HARMONY_FULL` is absent because its length is the
#: chord's own tone set, which varies by quality and lives in `TONE_PRIORITY`; an arity
#: longer than the row is refused there, where the row is known.
HARMONY_LENGTH: Dict[str, int] = {
    HARMONY_GUIDE: 2,
    HARMONY_SHELL_ROOT: 3,
}

HARMONY_AUTO = "auto"

#: `auto` means "whatever this part already says", and it **decides rather than naming
#: its own default**: the two shipped shapes are different. With the melody taken the
#: chord part is the full order - the chord-melody this library has always built - and
#: with the guitar comping under somebody else's tune it is the guide pair. One value
#: cannot be both, which is why this sentinel survives where `grid`'s was withdrawn.
HARMONY_AUTO_POLICIES: Dict[bool, str] = {
    True: HARMONY_FULL,
    False: HARMONY_GUIDE,
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


def resolve_harmony(harmony: str, parts: Tuple[str, ...]) -> str:
    """The degree order to actually state: `auto` resolved, then validated.

    `auto` resolves from the **parts**, through `HARMONY_AUTO_POLICIES`: the full order
    when the melody is the guitar's, and the guide pair when it is not.

    A combination that cannot be stated **raises** rather than degrading to `guide`. An
    arrangement that states something other than what was asked for is worse than one
    that refuses, and there is no inert answer to fall back to here: `guide` is what a
    caller gets by asking for `guide`, so handing it back for `shell_root` would be a
    silent substitution wearing the default's clothes. The message names the part that
    would work, which is the information a caller can act on.

    **The check is on the request, not on the resolution.** `auto` is the engine's own
    choice and is never refused, because what it names is only read by the comping
    route - and a selection that takes no chord part never comps, so the value it
    resolves to is unread rather than wrong. Validating it there would make the
    default unusable on every melody-only selection (`parts=melody` with the shipped
    harmony raised `harmony=full ... does not take it`), which is a refusal of
    something nobody asked for. An explicit family is still checked, so
    `harmony=full, parts=melody` names the part that would work.
    """
    resolved = (
        HARMONY_AUTO_POLICIES[parts_have_melody(parts)]
        if harmony == HARMONY_AUTO
        else harmony
    )
    if harmony == HARMONY_AUTO:
        return resolved
    allowed, reason = harmony_allowed(resolved, parts)
    if not allowed:
        raise ValueError(reason)
    return resolved


def harmony_allowed(harmony: str, parts: Tuple[str, ...]) -> Tuple[bool, str]:
    """Whether this degree order can be stated by this selection, and why not.

    **Derived rather than listed**, from one fact: every `harmony=` value is a claim
    about the **chord part**, so a selection that does not take it has no part to state
    the order on. This is `harmony=root`'s old refusal generalised - a content policy
    for a part the selection does not name is refused, naming the part that would work
    (`docs/history/parts.md` §5 item 7).

    Checked before any voicing work, on the library's standing rule that an impossible
    request is answered by saying what would work rather than by dropping something the
    caller asked for.
    """
    if not parts_have_chord(parts):
        return False, (
            f"harmony={harmony} is a degree order for the chord part, and "
            f"parts={','.join(parts)} does not take it - add 'chord' to parts, or "
            f"drop the harmony"
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

# --- The chord part's family palette: derived from the arity -----------------
#
# **The grip families are an internal search space, not a choice** - `grips=` is not a
# flag any more (`docs/history/parts.md` §4). What a caller chooses is the arity (`texture=`),
# and the families that state exactly that many notes under the melody are the ones the
# selector may use. The mapping is read off `GRIP_STRING_SETS`: a family sounds
# `len(strings)` strings, one of which carries the melody, so the number of chord-part
# notes it states is that length minus one. A family whose sets are not all one size is
# reported at its **smallest**, because the selector has to be able to state the arity
# on every set the family offers.
#
# `interval` and `melody` are not families: a *fill* that is not a grip at all is
# `get_interval_voicing` / `get_melody_only_voicing`, reached through the palette the
# same way a family is, and the **empty** palette is the declaration "the left hand
# plays nothing" - which is how a melody-only selection arrives at
# `decisions.melody_alone_case`. See `docs/history/one-fact.md`.
#: How many notes a **fill** states fewer than a target. One, because that is the whole
#: claim the role makes: a fill is heard *between* two chords and is thinner than the
#: one it sits under. It is a property of the role rather than a per-texture row - the
#: only texture whose slots are ever both (`targets`, which reads the metre) thins by
#: one, and a fixed-arity texture makes every slot a target, so its fills exist only on
#: the routes that never reach a palette at all.
FILL_THINNING = 1

#: The two palette entries that are **not grip families**: an interval and the tune
#: alone, each with the number of chord-part notes it states. Both are thinner than
#: any grip, so a *fill* may reach them where it may not reach a four-note shape; a
#: target may not use them at all, because a target states the chord part's arity and
#: neither of these states a chord part.
THIN_ENTRIES: Dict[str, int] = {
    "interval": 1,
    "melody": 0,
}

#: A family a **fill** does not use, at any arity: `duo` states a 3rd or a 7th, which
#: is a **claim about the chord**, and a fill makes none - it is heard between two
#: chords rather than as one, so the loose reading (`interval`, offered under any
#: melody degree) is the fill's two-note statement and the harmony's is the target's.
#: Naming the family here rather than listing a per-texture palette is the whole
#: point of the arity rule: this is one fact, and it is a fact about the *role*.
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
    texture states is the most the arithmetic allows *here*, so a position where only
    a two-note shape fits is a thinner statement rather than no statement at all.
    That is the difference between "thin here" and "silent here", and the old
    palettes drew it the same way - `uniform` offered every family and let
    `voicing_cost`'s voice-count criterion prefer the fullest one it could place.

    Ordered by `GRIP_PREFERENCE`, so the first shape generated at a position is the
    fullest the position admits, and an exact tie falls to the caller's own order.
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
    """The chord part's arity at a position the guitar does **not sing**.

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


# --- The grid axis: when each part sounds -----------------------------------
#
# Positions **crossed with parts**, because the parts do not move together: `joe_pass`
# is a chord on every upbeat and a bass note on every beat, and the two rhythms are
# independent claims rather than one pattern. A grid is one or more `part:pattern`
# rows, comma-separated:
#
#   grid=melody:every_note              the melody's own written slots (the default)
#   grid=chord:joe_pass                 the chord on the upbeat of every beat
#   grid=bass:walk                      the bass on every beat of every bar
#   grid=bass:anchors                   the bass where the harmony changes
#   grid=melody:every_note,bass:walk    two rows at once
#
# **Every row but the one for the melody says when a part that is not the tune
# sounds.** The melody's own rhythm is data - where the notes are written - so
# `melody:every_note` is the row that names it, and it is the default: the chord falls
# under every written note, and every other part that sounds takes those same slots
# until its own row says otherwise.
#
# **`bass:walk` is the rhythm half of the old `bass=` flag** and `bass:anchors` the
# other half (`docs/history/parts.md` §9): the note rules are `bass_style=`'s, and this says
# how often they fire. `walk` is every beat of every bar the melody touches; `anchors`
# is where the **harmony timeline** changes, a position set the timeline derives rather
# than one that is bar-relative.
#
# **Positions are bar-relative, and `LAST` is what makes that true.** The upbeat of the
# bar's final beat is one musical idea that lands on a different beat number in every
# metre - 4.5 in 4/4, 2.5 in 2/2, 3.5 in 3/4 - so a pattern that spells it `[(4, SUB)]`
# would look to a 2/2 head like it named a beat that does not exist. Spelling it
# `[(LAST, SUB)]` and resolving `LAST` against the metre is the same figure in all
# three. This is the `TARGET_BEATS` lesson applied to a rhythm: name *the position*,
# never a literal beat number.
#
# Subdivision is an **integer count of twenty-fourths of a beat**, not a float, for the
# same reason `_BEAT_EPSILON` exists: a notated position is a float in practice (a 3/4
# bar's second beat is 1.666...) and comparing floats for equality to decide whether a
# chord lands is a comparison that will eventually be false for the wrong reason.
#
# **Twenty-fourths rather than halves, because the finest position is a note value.** A
# sixteenth note and an eighth-note triplet are the smallest subdivisions this library
# represents - a quarter and a third of a *quarter* note - and the coarsest beat-relative
# unit holding both is a twelfth of a beat. The cut-time heads need it too, where a
# sixteenth note is an eighth of a *half-note* beat, so the unit is `1/24`. Which of its
# multiples a bar may actually be generated at is `grid_resolutions`; measured over the
# committed heads, every onset of every one of them is already on this lattice and no
# finer one is needed.
GRID_EVERY_NOTE = "every_note"
GRID_FREDDIE = "freddie"
GRID_CHARLESTON = "charleston"
GRID_JOE_PASS = "joe_pass"
GRID_FINAL_AND = "final_and"
GRID_WALK = "walk"
GRID_ANCHORS = "anchors"

# The subdivision of a beat, in whole twenty-fourths. Integer on purpose - see above.
TICKS_PER_BEAT = 24

#: Half a beat, which is the upbeat every named figure is built from.
SUB = 12

# Beat sentinels, so a pattern can name a position rather than a beat number.
LAST = 0   # the metre's FINAL beat, resolved against `beats_per_bar`
ALL = -1   # every beat the metre has; composes with a subdivision (`(ALL, SUB)`)


@dataclass(frozen=True)
class GridPattern:
    """One rhythm grid: the within-bar positions a part may sound on.

    `positions` is a tuple of `(beat, ticks)` pairs, where `beat` is a beat number,
    `LAST` or `ALL`, and `ticks` is an integer count of twenty-fourths of a beat from
    that beat (`0` is the beat, `SUB` is its upbeat).

    **`bar_relative` is a property of the pattern, not a comment**, and it earns its
    place by saying whether a *silence* is the arranger's mistake. A bar-relative
    pattern (`freddie`, `final_and`, `walk`) is playable in any metre - `LAST`
    resolves, so it never asks for a beat that is not there. A metre-relative one
    (`charleston`, `joe_pass`) is a named figure of a particular metre: asked of a 2/2
    bar it may be wrong, and that is the arranger's calling, not a defect in the
    engine. Left implicit, a pattern that places nothing reads as a bug; recorded as
    data, it is a fact about the pattern and the refusal below can name it.
    """

    positions: Tuple[Tuple[int, int], ...]
    bar_relative: bool


#: Which patterns each part may take. A pattern outside its part's row is refused
#: rather than silently ignored: `chord:walk` is a question, not a request for
#: `chord:freddie`.
GRID_PART_PATTERNS: Dict[str, Tuple[str, ...]] = {
    PART_MELODY: (GRID_EVERY_NOTE,),
    PART_CHORD: (
        GRID_EVERY_NOTE, GRID_FREDDIE, GRID_JOE_PASS, GRID_FINAL_AND, GRID_CHARLESTON,
    ),
    PART_BASS: (GRID_EVERY_NOTE, GRID_WALK, GRID_ANCHORS),
}

#: Every row name a caller can write, part-qualified.
GRID_STYLES: Tuple[str, ...] = tuple(
    f"{part}:{pattern}"
    for part, patterns in GRID_PART_PATTERNS.items()
    for pattern in patterns
)

#: The shipped grid: the melody's own slots govern every part.
GRID_DEFAULT = f"{PART_MELODY}:{GRID_EVERY_NOTE}"

#: The named patterns, **all of them bar-or-metre relative**. `anchors` is absent
#: because it is not a within-bar figure: its positions come from the harmony
#: **timeline**, so it is in `GRID_TIMELINE_PATTERNS` instead and the head layer is
#: what resolves it.
GRID_PATTERNS: Dict[str, GridPattern] = {
    GRID_EVERY_NOTE: GridPattern(positions=(), bar_relative=True),
    GRID_FREDDIE: GridPattern(positions=((ALL, 0),), bar_relative=True),
    GRID_FINAL_AND: GridPattern(positions=((LAST, SUB),), bar_relative=True),
    GRID_CHARLESTON: GridPattern(positions=((1, 0), (2, SUB)), bar_relative=False),
    GRID_JOE_PASS: GridPattern(positions=((ALL, SUB),), bar_relative=False),
    # Every beat of every bar, which is what makes a thumb line a *walk*.
    GRID_WALK: GridPattern(positions=((ALL, 0),), bar_relative=True),
}

#: Rows whose positions the **timeline** supplies rather than the metre.
GRID_TIMELINE_PATTERNS: Tuple[str, ...] = (GRID_ANCHORS,)


def grid_rows(grid: str) -> Dict[str, str]:
    """A canonical grid as its rows: part name to pattern name.

    The one reader every other function here goes through, so a row spelled
    `bass:walk` cannot mean one thing to the parser and another to the selector.
    """
    rows: Dict[str, str] = {}
    for row in grid.split(","):
        part, _sep, pattern = row.partition(":")
        rows[part.strip()] = pattern.strip()
    return rows


def grid_chord_pattern(grid: str) -> str:
    """Where the **chord part** falls: its own row, or the melody's slots."""
    return grid_rows(grid).get(PART_CHORD, GRID_EVERY_NOTE)


def grid_bass_pattern(grid: str) -> str:
    """When the **bass part** sounds: its own row, or the melody's slots."""
    return grid_rows(grid).get(PART_BASS, GRID_EVERY_NOTE)


def grid_defers_to_melody(grid: str) -> bool:
    """Whether the chord part takes the melody's slots rather than a pattern.

    `every_note` is the *absence* of a chord pattern rather than one, which is why it
    is read from the named pattern's own emptiness instead of from a special case:
    "places nothing" and "has no positions to place" are different claims, and only
    the first is a mismatch (see `grid_allowed`).
    """
    pattern = grid_chord_pattern(grid)
    if pattern in GRID_TIMELINE_PATTERNS:
        return False
    row = GRID_PATTERNS.get(pattern)
    return row is None or not row.positions


def parse_grid(argument: str) -> str:
    """A `grid` argument as its canonical spelling.

    Rows are `part:pattern`, comma-separated, and the result is **sorted and
    de-duplicated**, so `bass:walk,melody:every_note` and
    `melody:every_note,bass:walk` are one request rather than two that happen to
    agree. An empty argument is the shipped grid.

    Raises `ValueError` on an unknown part, an unknown pattern, or a pair the part
    cannot take. The rule is the library's: a spelling nobody recognises is a
    question, and answering it by falling back to the default would hand back a part
    that comps somewhere nobody asked for.
    """
    text = argument.strip().lower()
    if not text:
        return GRID_DEFAULT
    rows: Dict[str, str] = {}
    for row in text.split(","):
        part, sep, pattern = row.partition(":")
        part, pattern = part.strip(), pattern.strip()
        if not sep or not part or not pattern:
            raise ValueError(
                f"Unknown grid row {row!r}; expected PART:PATTERN, any of "
                f"{', '.join(GRID_STYLES)}"
            )
        if part not in GRID_PART_PATTERNS:
            raise ValueError(
                f"Unknown grid part {part!r}; expected any of "
                f"{', '.join(GRID_PART_PATTERNS)}"
            )
        if pattern not in GRID_PART_PATTERNS[part]:
            raise ValueError(
                f"Unknown {part} grid {pattern!r}; expected any of "
                f"{', '.join(GRID_PART_PATTERNS[part])}"
            )
        rows[part] = pattern
    return ",".join(f"{part}:{rows[part]}" for part in sorted(rows))


def grid_positions(
    grid: str, beats_per_bar: int
) -> Tuple[Tuple[int, Tuple[float, ...]], ...]:
    """Resolve the **chord part's** row against a metre: beats and their positions.

    Returns one entry per distinct beat the pattern touches, each holding every
    within-bar position on that beat. `ALL` expands to every beat of the bar and `LAST`
    to the metre's final beat, which is the whole reason those two sentinels exist -
    `final_and` is 2.5 in 2/2 and 4.5 in 4/4 without being written twice.

    An **empty** result means the pattern places nothing in this metre, and that is a
    real answer rather than a bug: `charleston` is a 4/4 figure, so asked of a 2/2 bar
    it has nowhere to go. `grid_allowed` is what turns that into a refusal naming the
    pattern; this function only reports the geometry.
    """
    pattern = grid_chord_pattern(grid)
    row = GRID_PATTERNS.get(pattern)
    if row is None:
        return ()
    beats: Dict[int, List[float]] = {}
    for beat, ticks in row.positions:
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
            beats.setdefault(number, []).append(number + ticks / TICKS_PER_BEAT)
    return tuple(
        (number, tuple(sorted(set(positions))))
        for number, positions in sorted(beats.items())
    )


def grid_resolutions(beat_type: int) -> Tuple[int, ...]:
    """The densities a **generated** bar may take, coarsest first, in ticks of a beat.

    A bar the default grid generates inside is subdivided at the coarsest of these that
    holds every note its own melody writes, so this is the vocabulary of rhythms a bar can
    be read as having. **It is note values, read against the quarter note**: the half note,
    the quarter note, the quarter-note triplet, the eighth note, the eighth-note triplet
    and the sixteenth note, with the metre's own beat added to them. A sixteenth note and
    an eighth-note triplet are the finest note values this library represents, so a bar is
    never generated at a thirty-second or at a sixteenth-note triplet however busy its tune
    reads.

    **The intermediate values are not decorative, and leaving one out is a real defect.**
    With only the beat, an eighth note, an eighth-note triplet and a sixteenth, a 2/2 bar
    whose tune moves in quarter notes has no resolution to fit - a quarter note is *half* a
    beat there - so the rule falls through to the **sixteenth** and generates eight chords
    in a bar whose melody writes three. Measured on `but_not_for_me`: that reading added 28
    steps where the correct one adds 14.

    **Every value is converted through the metre, which is why this takes `beat_type`.** A
    beat is `4 / beat_type` quarters, so a quarter note is `6 * beat_type` ticks of `1/24`
    beat and the rest are multiples and fractions of it. Common time gives `(24, 12, 8, 6)`;
    cut time `(24, 12, 8, 6, 4, 3)`, where a quarter note is *half* a beat and a sixteenth an
    eighth of one; an eighth-note beat, in 6/8, `(24, 12)`. Reading a beat as a quarter would
    generate a 2/2 or a 6/8 bar at the wrong density, which is `AGENTS.md` trap 9 arriving in
    the grid.

    **Every entry divides the beat**, so the beat is always on a generated bar's grid. That
    is the one property the caller depends on: a note value that does not divide the beat
    evenly - a quarter-note triplet in 6/8, say - is dropped rather than used, because a
    grid missing its own downbeat would leave a bar's strongest position silent. A metre
    whose beat is not a quarter note therefore offers fewer of them, and that is reported as
    the fewer it is rather than padded.
    """
    quarter = 6 * beat_type
    candidates = {
        TICKS_PER_BEAT,           # the beat
        2 * quarter,              # a half note: the beat itself in cut time
        quarter,                  # a quarter note: half a beat in cut time
        (2 * quarter) // 3,       # a quarter-note triplet
        quarter // 2,             # an eighth note
        quarter // 3,             # an eighth-note triplet - the floor
        quarter // 4,             # a sixteenth note - the floor
    }
    return tuple(
        resolution
        for resolution in sorted(candidates, reverse=True)
        if resolution > 0 and TICKS_PER_BEAT % resolution == 0
    )


# How close a notated beat has to be to a whole beat to count as it. A 2/2 bar's
# eighths land on 1.0, 1.5, 2.0, 2.5, and a 3/4 bar's on 1.0, 1.666..., so an exact
# comparison would call almost none of them downbeats. Measured in beats, not in
# quarters, so this is the same tolerance in any metre.
_BEAT_EPSILON = 1e-6


def on_grid(beat: Optional[float], grid: str, beats_per_bar: int) -> bool:
    """Whether a chord falls on this beat of the bar under this grid.

    **`beat=None` is on the grid.** A slot nobody located has no position to be off,
    and this is the rule `_metric_weight` already follows with its `-1`: not being told
    where a note falls is not being told it is weak. Returning `True` is what keeps a
    hand-written progression - which carries no timings at all - byte-identical, and it
    is the same reason the default is inert.

    A melody-anchored chord row (`every_note`) is `True` for every beat, and so is a
    **timeline-derived** row (`anchors`), whose positions this function has no metre to
    resolve: the timeline supplies them, so nothing here can call a beat off it.
    """
    if beat is None or grid_defers_to_melody(grid):
        return True
    if grid_chord_pattern(grid) in GRID_TIMELINE_PATTERNS:
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
    question asked is one-directional - can the pattern be expressed at all here? - and
    deliberately not "does every bar carry a note on one of its positions". The second
    question has a correct answer of "no, and that is fine": a bar whose melody is all
    on the beat has nothing at 2.5 for `final_and` to land on, the melody-alone route
    handles it, and a refusal would be wrong. Only a pattern that places **nothing
    anywhere** is a real mismatch, and it is nearly always a metre-relative figure asked
    of a metre it was not written for.

    `every_note` is not a pattern with positions at all - it is the absence of a chord
    pattern - so it is **allowed unconditionally**, and a timeline row (`anchors`) is
    allowed for the same reason: its positions come from the harmony, not the metre, so
    this function has nothing to refuse.
    """
    pattern = grid_chord_pattern(grid)
    if grid_defers_to_melody(grid) or pattern in GRID_TIMELINE_PATTERNS:
        return True, ""
    if grid_positions(grid, beats_per_bar):
        return True, ""
    row = GRID_PATTERNS[pattern]
    if row.bar_relative:
        return False, (
            f"grid=chord:{pattern} places no chord in a {beats_per_bar}-beat bar, and "
            f"it is a bar-relative pattern, which should resolve in any metre - so "
            f"this is a defect in the pattern rather than a mismatch with the metre"
        )
    return False, (
        f"grid=chord:{pattern} is a metre-relative figure and places no chord in "
        f"{beats_per_bar}/4: it is right, or it is a figure of another metre asked "
        f"of this one. Try a bar-relative pattern such as 'freddie' or "
        f"'final_and', or grid=melody:every_note"
    )


def resolve_grid(grid: str, beats_per_bar: int) -> str:
    """The grid to actually place chords on: parsed and validated.

    Unlike `resolve_harmony` there is no sentinel to resolve - `grid=auto` is
    withdrawn and the default is the melody's own slots - so an arrangement naming no
    grid takes `GRID_DEFAULT`.

    A grid this metre cannot express **raises** rather than degrading to the
    melody-anchored grid. `every_note` is what a caller gets by asking for it, so
    returning it for a metre-relative figure would be a silent substitution wearing the
    default's clothes - and a figure asked of the wrong metre is a question the caller
    can answer, which is the reason to raise rather than to guess. The message names a
    pattern that would fit, which is the same information the refusal used to print.
    """
    parsed = parse_grid(grid)
    allowed, reason = grid_allowed(parsed, beats_per_bar)
    if not allowed:
        raise ValueError(reason)
    return parsed



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
    and 3 are targets exactly as they are in 4/4. `headxml`'s onset conversion and
    `bass._melody_timeline` honour the same denominator.

    A beat is compared with `_BEAT_EPSILON` because a notated beat is a float and a
    tune rarely lands only on the integers: the middle note of a triplet inside beat 1
    of a 3/4 bar is at 1.333..., and a note a third of a beat away from a target is not
    the target. An exact comparison would call almost no real note a downbeat.
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
    `_metric_weight`.

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
        # The fixed-arity rule, and the "no timing supplied" case. `uniform` and the
        # `chordN` rows state the same arity on every slot; `targets` is the texture
        # that reads the metre and thins between the strong beats.
        # The one case that must not land here is a melody-only selection with a
        # thumb - `parts=melody,bass` under this, the default, texture: the walk
        # invents beats the melody never articulated, and whether those hold the
        # tune or re-strike it is the strong-beat rule below. `uniform`'s "every
        # slot a target" would re-strike the melody on every walked beat, which is
        # the one thing a tune-with-a-thumb part must not do.
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
        # TARGET first; `uniform` reaches here only through a melody-only selection
        # with a thumb, which is the case the catch-all's own comment names.
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
