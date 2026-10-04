"""The decisions both step loops make, in one implementation each.

`VoiceLeadingEngine.arrange_progression` and `wjazzd.arrange_slots` are two loops
over the same slots, and between them they used to hold **two copies** of six
decisions. The code said so itself, in comments that are the most honest thing in
the repository:

    "Both copies must agree. A head read from a MusicXML file comes here and a
     hand-built progression goes through `arrange_progression`, so fixing only one
     leaves the same flag behaving two different ways depending on the entry
     point."

    "This is a *fallback*, tried last, and it mirrors the one in
     `arrange_progression`."

A comment asking two copies to stay in step is not a mechanism. It works until
someone edits one of them on a Tuesday. The project has already paid for that once:
the corpus path was built separately from the library, drifted, and voiced an
`Am7` under a written `Bbm7` for twenty-five transcriptions before anyone noticed -
which is why `prepare_step` was extracted in the first place.

So the decisions live here, and each loop calls them. Nothing in this module knows
about slots, textures or arrangements; it is one function per decision, each taking
the few values it needs and returning the answer.

**The one place the two loops genuinely differ is not here.** The corpus honours a
slash bass by partitioning candidates before selection, and the library does not.
That difference is a filter over a list rather than a control-flow fork, and it is
folded into one `select_step_voicing` when Phase 4 rewrites `arrange_slots` to
delegate. It is not extracted in this phase because it is not a *duplicated*
decision - only the corpus has it - and extracting it here would mean reaching
back into `wjazzd` for `bass_cost`, which would close an import cycle.

**Why this module imports the engine's vocabulary and the engine imports this
module.** The dependency runs one way: `decisions` needs the engine's own
constants (`GRIP_PREFERENCE`, `ROLE_FILL`, `GRIP_MAX_SPAN`, `sounding_harmony`)
and the engine needs the decisions. So `steps` imports this module, and this
module imports `grips`, `chords`, `cost` and `tuning` - all of which sit *below*
`steps` in the package's DAG. When the engine was one module, that meant a
function-local `from arranger import ...` to dodge a cycle; inside the package the
imports are ordinary top-level ones, and there is no cycle left to dodge.
"""

from __future__ import annotations

from typing import Any, Callable, Container, List, Optional, Sequence, Tuple

from .chords import sounding_harmony
from .cost import _best_voicing
from .diagnostics import Diagnostics
from .grips import GRIP_MAX_SPAN, GRIP_PREFERENCE
from .tuning import NO_CHORD, ROLE_FILL, ROLE_TARGET, ArrangementStep, Voicing

# The three answers to "how is this slot played". Named rather than a bool because
# the two non-default routes build different steps - see `melody_alone_case`.
MELODY_ALONE_NONE = "none"        # look it up through the grips, as usual
MELODY_ALONE_TEXTURE = "texture"  # a texture case: has a harmony, not spelled out
MELODY_ALONE_NO_CHORD = "nc"      # an NC bar: no harmony to voice at all


def resolve_texture_grips(
    role: str,
    texture: str,
    texture_grips: Any,
    requested: Tuple[str, ...],
    diagnostics: Diagnostics,
) -> Tuple[str, ...]:
    """Which grips this slot may use: the role's palette, narrowed by the caller.

    `requested` **narrows** the texture's palette; it never widens it and never
    silently deletes from it. It used to be discarded outright
    (`slot_grips = texture_grips[role]`), so `--grips shell --texture targets` asked
    for shell-only and got a four-note drop-2 on every strong beat with nothing said.

    The default is the case that matters, and it is why this is **not** a plain set
    intersection. `GRIP_PREFERENCE` is the order a *caller* ranks grips in, and it
    deliberately does not list `interval`, `melody` or `drop3` - a `targets` fill is
    `("shell", "interval", "melody")` and a target is `("drop2", "drop3")`, so
    intersecting with it would delete `interval` and `drop3` from the texture and
    change every default arrangement. The texture table is the authority on what a
    role may play; `GRIP_PREFERENCE` only says what order a caller ranks them in.

    So the rule is: an explicit restriction intersects, and the default - which is
    not a restriction, just the absence of one - does not.

    An empty intersection is a caller asking for a grip the texture never uses. The
    step still sounds, and says so: losing a chord of the tune is worse than
    ignoring a flag, so the texture's own set stands.

    A palette that is **itself** empty is the one case that is not a caller error, and
    it is not reported. `walking_bass`'s fill palette is `()` deliberately - it means
    "the left hand plays nothing between the anchors" - so `--grips shell --texture
    walking_bass` intersects to nothing on *every* fill, and warning on each printed
    the same line 76 times over one arrangement. The distinction is the difference
    between a texture that cannot use the grip and a texture that means to play
    nothing: only the former is worth interrupting the output to mention.
    """
    role_grips: Tuple[str, ...] = texture_grips[role]
    if requested == GRIP_PREFERENCE:
        return role_grips
    narrowed = tuple(g for g in requested if g in role_grips)
    if narrowed:
        return narrowed
    if not role_grips:
        return role_grips  # nothing to fall back *from*, and nothing to say
    diagnostics.warn(
        f"Warning: {texture} uses {role_grips} for a "
        f"{role}, none of which is in the requested {requested}; "
        f"using the texture's own set"
    )
    return role_grips


def melody_alone_case(
    texture: str,
    role: str,
    slot_grips: Tuple[str, ...],
    quality: str,
    name: str,
    has_thumb: bool = False,
    melody_voiced: bool = True,
) -> str:
    """Which of the three "play this as a single note" routes this slot takes.

    Returns one of `MELODY_ALONE_NONE`, `MELODY_ALONE_TEXTURE` or
    `MELODY_ALONE_NO_CHORD`. The two non-default answers reach the same *route* -
    `get_melody_only_voicing` rather than grip lookup - but they build different
    steps, which is why this returns a kind rather than a bool: an `NC` bar sets
    `melody_only=True`, and a texture case must **not**, because the step does have
    a harmony, it is simply not being spelled out, and the flag would make the
    annotation read "(no chord - melody alone)" and claim a lie.

    Why each is a branch rather than a missing case:

    - **an `NC` bar** carries melody but no harmony, so there is nothing to voice.
      Taken before any chord logic, so it is never reharmonised and never warns.
    - **a fill under a thumb texture**, **a target no shell can sound**, and **every
      slot of a melody-only texture.** A fill is *meant* to be thin; a target that
      cannot be voiced must not be dropped, because the note of the tune survives and
      the harmony is stated at the next target; and a `melody` or `melody_bass` slot
      is *defined* to be a single note. All three reach it the same way, and the
      condition is deliberately **two** clauses rather than one:

      - `slot_grips == ()` is the declaration. `TEXTURE_GRIPS` says "the left hand
        plays nothing" with an empty tuple and never by omitting a key, so this is
        where a melody-only texture, a walking-bass fill, and a narrowed-to-nothing
        palette all arrive.
      - `texture in THUMB_TEXTURES and role == ROLE_FILL` covers the one case the
        declaration misses: `--grips shell --texture walking_bass`, where the caller
        narrows a fill to `("shell",)` and the palette is no longer empty. Without
        this clause that fill would try to voice a shell, which is the opposite of
        what the texture means.

      Both are needed because the first alone would change `--grips shell
      --texture walking_bass`, and the second alone would miss every narrowed palette.

    **`melody_voiced` is the fourth clause, and it is a guard rather than a route.**
    Every answer here ends at `get_melody_only_voicing`, which is the melody on its
    own - so under `melody="none"` this function cannot be allowed to answer
    `MELODY_ALONE_TEXTURE`, or a fill would put the tune straight back on the guitar
    and the axis would be honoured only on targets. Measured: under
    `--texture targets --bass walk` every fill came back `x-7-x-x-x-8`, a bare melody
    note, which is exactly the part that was supposed to be somebody else's.

    So when the guitar is not singing, only an `NC` bar may take this route - and that
    one is *also* wrong, for a different reason: an NC bar has no chord, so there is no
    guide tone to state and nothing for the guitar to play. It is answered as
    `MELODY_ALONE_NONE` and the caller warns instead, which keeps the tune's silence
    visible rather than quietly handing the horn's line to the guitarist.
    """
    if not melody_voiced:
        return MELODY_ALONE_NONE
    if quality == NO_CHORD or name == NO_CHORD:
        return MELODY_ALONE_NO_CHORD
    if (has_thumb and role == ROLE_FILL) or slot_grips == ():
        return MELODY_ALONE_TEXTURE
    return MELODY_ALONE_NONE


def is_bass_only(slot_bass_only: bool, role: str) -> bool:
    """
    Whether this step's upper voices really are held across it.

    `slot_bass_only` is what the **bass grid** said: the walk invented this beat,
    because the bass moves on a finer grid than the melody does (decision B). That
    is a statement about where the beat came from, not about what the left hand
    plays, and the two come apart.

    A **target** is the case that matters. `_roles_for_slot` promotes a strong beat to
    a target when the melody moves onto it, and under `walking_bass` the walk
    invents downbeats the melody grid never had - so a slot can arrive with
    `bass_only=True` *and* `role == ROLE_TARGET` at the same time. Those two flags
    contradict each other: `bass_only` means "nothing above the thumb strikes, the
    upper voices are held from the last shape", while a target means "a full chord
    states the harmony here". The engine voices a real `shell` or `melody` grip on
    such a step, and then `bass_only` told all four renderers to suppress it - so the
    chord of the tune vanished from the tab, the GP5 file and the score while existing
    in the engine's own output. `tabxml` was the only renderer that showed it, and
    only because `_sounding` filters on `fret >= 0` and never applies the rule at all.

    A **fill** is the other half and is untouched: under decision C a fill is the
    melody alone, and the melody it carries is the one already sounding, so holding it
    is exactly right. That is why this is a role test rather than a pitch comparison -
    on "But Not For Me" 13 of the 22 `bass_only` steps are fills that are correctly
    held, and 9 are targets that were wrongly silenced.

    The answer is a flag the renderers read, so it has to be right here rather than in
    four renderers that would each have to re-derive it - and it also has to be right
    before `_attach_bass` reads it, because a target measures its thumb against its own
    voicing rather than against a shape it is holding.
    """
    return slot_bass_only and role != ROLE_TARGET


def should_promote_fill(
    texture: str,
    role: str,
    prepared_is_none: bool,
    slot_grips: Tuple[str, ...],
    requested: Tuple[str, ...],
    has_thumb: bool = False,
    melody_only_texture: bool = False,
) -> bool:
    """Whether a fill that produced nothing should be re-prepared as a principal note.

    A fill that cannot be filled must not cost the tune its chord: the texture is a
    lighter *texture*, never a missing harmony. So the step is retried as a target
    before it is reported as missing - the same argument that makes `NECK_FRET_MIN`
    a penalty rather than a filter.

    Disabled wherever a fill is *meant* to be empty - `walking_bass`, and the two
    melody-only textures - because the melody-alone branch has already handled it, so
    promoting here would undo the texture one step at a time. Named by table rather
    than by literal, so a texture added to `TEXTURE_STYLES` cannot join the melody-alone
    route while missing this.

    `slot_grips != requested` is the "the role narrowed the caller's grips" case. If
    the two are equal the retry would ask for exactly what just failed, so it is
    skipped rather than repeated.
    """
    if has_thumb or melody_only_texture:
        return False
    return prepared_is_none and role == ROLE_FILL and slot_grips != requested


def should_demote_to_melody_alone(voicing: Voicing, role: str) -> bool:
    """Whether a complete chord at the very top of the span budget is demoted.

    A shape that spans the whole fret budget is legal and often unplayable, and a
    texture's *target* role may offer only the four-note grips - so the narrow
    alternative was never a candidate to be ranked against, and the cost tuple would
    not have chosen it anyway (`missing` sits above span, so a complete wide shape
    beats a partial narrow one). `x-6-5-3-8-x` for Ebmaj under G4 is the real case:
    the engine *could* sound `x-x-8-8-8-x` there, span 0, but a `targets` target is
    never offered a shell.

    This is a **fallback, not a re-ranking**, and it is deliberately last. Lowering
    `GRIP_MAX_SPAN` is a filter that deletes the voicing everywhere; promoting span
    above `missing` would dissolve the shell and duo families across the whole
    library. Here a complete chord is still what you get whenever it is playable,
    and only a shape at the very top of the budget is demoted.

    The demotion is to the melody alone, which is playable for every reachable
    melody. Preferring a shell was measured: it is better as music, but it is only
    reachable when the role's palette contains a shell, and where it does not - a
    `targets` target - there is nothing to demote *to*. Losing a note of the tune is
    worse than a thin one.
    """
    return voicing.fret_span() >= GRIP_MAX_SPAN["drop2"] and role == ROLE_TARGET


def is_repeated_step(
    previous_step: Optional[ArrangementStep],
    voicing: Voicing,
    harmony: Tuple[Optional[str], Optional[str]],
) -> bool:
    """Whether this step is a soprano-only re-strike of the step before it.

    The melody sounds the same pitch, under an unchanged harmony. Compared on the
    **sounding** pitch rather than the written name, because a step either side of
    this may itself have been transposed down an octave by the `HIGH_FRET_LIMIT`
    rule.

    The harmony must also be unchanged, and that is the half that is easy to get
    wrong. A note repeating across a *chord change* is not a hold: the inner voices
    still ringing belong to the chord the hold began on, so printing the new chord's
    name over a single struck note claims a harmony that is not sounding. Those
    steps are harmonised against the new chord instead, which is what the voicing
    already does - only the rendering was discarding it.

    A melody-only (`NC`) step is never marked: it has one active fret and no inner
    voices to hold, so the flag would mean nothing.

    **The same argument applies to any step that sounds a single note**, and that is
    not the same set. A `texture` fill is the melody alone under `walking_bass` and
    carries `melody_only=False` - it is a deliberate exception, per the comment at
    the call site that builds it - so the check above does not catch it. But it plays
    one note, there are no inner voices ringing to hold, and marking the *next* step
    `repeated` then instructs every renderer to suppress that step's inner voices.

    That is not a cosmetic flag error. Measured on "But Not For Me" bar 3 under
    `walking_bass`: the engine voiced `C3 Bb3 Eb4` for a `Cm7` target, and
    `_step_cells` returned a single `8` on the G string - `C3` and `Bb3`, the two notes
    that make it a `Cm7` rather than a bare melody note, reached **none** of the four
    renderers. The chord of the tune was voiced and then thrown away by a rule that
    meant "hold what is already ringing", applied when nothing was.

    So the test is on what the previous step **sounds**, not on its flag: one active
    fret means there is nothing to hold. `melody_only` is then a special case of it
    and is kept as a named check because it reads as the intent rather than the
    arithmetic.
    """
    if previous_step is None or previous_step.melody_only:
        return False
    if len([fret for fret in previous_step.voicing.frets if fret >= 0]) < 2:
        # A melody-alone step: the melody is held by the hand, not by ringing inner
        # voices, so the next step has to state whatever it voices rather than
        # suppress it. See the docstring for the bar this was measured on.
        return False
    if max(previous_step.voicing.midi_notes()) != max(voicing.midi_notes()):
        return False
    return sounding_harmony(previous_step) == harmony



def select_step_voicing(
    candidates: List[Voicing],
    previous: Optional[Voicing],
    fret_min: int,
    fret_max: int,
    allowed_tones: Optional[Container[int]],
    root_pc: Optional[int],
    melody_pc: Optional[int] = None,
    bass_pc: Optional[int] = None,
    bass_cost: Optional[Callable[[Sequence[int], Optional[int]], int]] = None,
) -> Optional[Voicing]:
    """The candidate the engine's own rule prefers, honouring a slash bass first.

    This is the Weimar corpus's rule C, and it is what lets `wjazzd.arrange_slots`
    delegate to `arrange_progression` instead of running a second step loop. The
    library passes no `bass_pc` and gets exactly the behaviour it always had.

    The two rules that select a candidate - the slash bass and voice leading - are
    **combined, not applied in sequence**. The candidates are partitioned by how
    well they honour the bass, and the engine's own selection rule then decides
    *within the best group*. Applying them one after the other would let whichever
    ran last always override the other, which is precisely the bug that was fixed
    by writing them this way in the first place.

    The partition is skipped when the bass is unsatisfiable (`best > 2`), so an
    unachievable slash chord behaves exactly as if it had not been written - which
    is the same "never guess" rule the rest of this module follows.

    `bass_cost` is passed in rather than imported because it lives in `wjazzd` and
    `wjazzd` imports this module; a module-level import either way would be a cycle.
    Passing it also makes the dependency visible at the call site, which is the
    point: the corpus is the only caller that supplies one.
    """
    if bass_pc is not None and bass_cost is not None and candidates:
        costs = [bass_cost(v.midi_notes(), bass_pc) for v in candidates]
        best = min(costs)
        if best <= 2:
            candidates = [v for v, c in zip(candidates, costs) if c == best]

    return _best_voicing(
        candidates,
        previous,
        fret_min,
        fret_max,
        allowed_tones=allowed_tones,
        root_pc=root_pc,
        melody_pc=melody_pc,
    )
