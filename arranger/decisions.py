"""The decisions both step loops make, in one implementation each.

`VoiceLeadingEngine.arrange_progression` and the corpus path's `arrange_slots` (now
`arranger.slots`, and a delegate rather than a loop) were two loops over the same
slots, and between them they used to hold **two copies** of six
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
what `select_step_voicing` folds in - it is not a *duplicated* decision, which is
why it was never extracted as one. The ranking itself lives in `arranger.slots`,
which reaches this module through `steps`, so injecting it is what keeps the
dependency acyclic and the preference visible at the call site.

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
from .grips import GRIP_MAX_SPAN, GRIP_PREFERENCE, thumb_safe_grips
from .tuning import NO_CHORD, ROLE_FILL, ROLE_TARGET, ArrangementStep, Voicing

# The three answers to "how is this slot played". Named rather than a bool because
# the two non-default routes build different steps - see `melody_alone_case`.
MELODY_ALONE_NONE = "none"        # look it up through the grips, as usual
MELODY_ALONE_TEXTURE = "texture"  # a texture case: has a harmony, not spelled out
MELODY_ALONE_NO_CHORD = "nc"      # an NC bar: no harmony to voice at all
MELODY_ALONE_REST = "rest"        # off the grid: the guitar plays nothing here


def resolve_texture_grips(
    role: str,
    texture: str,
    texture_grips: Any,
    requested: Tuple[str, ...],
    diagnostics: Diagnostics,
    has_thumb: bool = False,
) -> Tuple[str, ...]:
    """Which grips this slot may use: the role's palette, narrowed by the caller.

    `requested` **narrows** the texture's palette; it never widens it and never
    silently deletes from it. It used to be discarded outright
    (`slot_grips = texture_grips[role]`), so `--grips shell --texture targets` asked
    for shell-only and got a four-note drop-2 on every strong beat with nothing said.

    `has_thumb` narrows it too, and it is a budget rather than a preference: the right
    hand plucks with thumb, index, middle and ring, so a **target** may sound at most
    three strings while a bass note is being placed under it - four fingers, and the
    thumb is one of them. `thumb_safe_grips` is the rule, derived from the string
    tables; a target palette of four-note grips (`targets`' `drop2`/`drop3`) resolves to
    the widest statement that leaves a finger free, which is the `("shell",)` palette
    `walking_bass` already names. Applied *before* `requested` narrows, so
    `--grips drop2 --texture targets --bass walk` still reads as "that grip is not
    available here" and takes the existing reported fallback rather than resurrecting a
    five-pluck step.

    **`has_thumb` is a fact about *this slot*, not about the arrangement**, and the
    caller passes it that way: a bass policy places a note on some beats and not others
    (`anchors` only where the harmony changes), and a target with nothing underneath it
    may use all four strings. Narrowing every target in the arrangement would thin
    chords the thumb never plays under.

    A **fill** is not touched. A fill is heard *between* the thumb's notes rather than
    under one, and the texture's fill palettes already hold inside the budget.

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
    # The right hand's budget first, because it is a fact about the hand rather than a
    # preference: a target that sounds four strings has no finger left for the thumb.
    # A fill is left alone - it is heard between the thumb's notes, not under one.
    if has_thumb and role == ROLE_TARGET:
        role_grips = thumb_safe_grips(role_grips)
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
    on_grid: bool = True,
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
      slot of a melody-only voice selection.** A fill is *meant* to be thin; a target that
      cannot be voiced must not be dropped, because the note of the tune survives and
      the harmony is stated at the next target; and a melody-only selection's slot
      is *defined* to be a single note. All three reach it the same way, and the
      condition is deliberately **two** clauses rather than one:

      - `slot_grips == ()` is the declaration. `TEXTURE_GRIPS` says "the left hand
        plays nothing" with an empty tuple and never by omitting a key, and the loop
        hands an empty palette to a melody-only selection for the same reason, so
        this is where a melody-only selection, a walking-bass fill, and a
        narrowed-to-nothing palette all arrive.
      - `has_thumb and role == ROLE_FILL` covers the one case the
        declaration misses: `--grips shell --texture walking_bass`, where the caller
        narrows a fill to `("shell",)` and the palette is no longer empty. Without
        this clause that fill would try to voice a shell, which is the opposite of
        what the texture means.

      Both are needed because the first alone would change `--grips shell
      --texture walking_bass`, and the second alone would miss every narrowed palette.

    **`melody_voiced` is the fourth clause, and it is a guard rather than a route -
    and it is asked per *slot*, not once per arrangement.** Under §9.3 step D of
    `docs/comping-styles.md` the engine passes `sings_here` here, not the arrangement's
    route: a slot the guitar does not sing is either one whose selection has no soprano
    or one carrying no melody note. Every answer here ends at
    `get_melody_only_voicing`, which is the melody on its own - so this function cannot
    be allowed to answer `MELODY_ALONE_TEXTURE` for a slot the guitar is not singing, or
    a fill would put the tune straight back on the guitar and the axis would be honoured
    only on targets. Measured: under `--texture targets --bass walk` every fill came
    back `x-7-x-x-x-8`, a bare melody note, which is exactly the part that was supposed
    to be somebody else's. The per-slot reading is what keeps that true for a note-less
    grid position a *singing* selection receives: the guitar has no note there, so it
    must not answer the texture case.

    So for a slot the guitar is not singing, only an `NC` bar may take this route - and
    that one is *also* wrong, for a different reason: an NC bar has no chord, so there is
    no guide tone to state and nothing for the guitar to play. It is answered as
    `MELODY_ALONE_NONE` and the caller warns instead, which keeps the tune's silence
    visible rather than quietly handing the horn's line to the guitarist.

    **`on_grid=False` is the grid axis, and it is the one case where the guitar plays
    nothing rather than one note.** Every other answer ends at
    `get_melody_only_voicing`, which is the tune on its own; there is no such thing
    when the tune is somebody else's, so an off-grid slot on the comping route is a
    **rest** - `MELODY_ALONE_REST`, a fourth kind. This is `docs/comping-styles.md`
    §4.2's "a melody note with no chord position on it sounds alone", and it needs two
    different answers rather than one: with the guitar singing, the note still sounds
    (the texture case); with it not singing, the note is the horn's and the guitar has
    nothing to add. A single bool would have had to pick one.
    """
    # **The ordering of the three guards below is load-bearing, and each one has been
    # got wrong in a way its test caught.**
    #
    # The grid is asked *inside* the voice guard rather than after it. Answering the
    # voice guard first made `grid=` silently inert on the comping route: measured, all
    # four patterns returned 80 of 80 comps on `but_not_for_me` under
    # `melody=alto,tenor`, byte-identical to the default. That is safe because a grid
    # only ever *removes* chords, so it cannot reintroduce a soprano the voice
    # selection removed.
    if not melody_voiced:
        # An `NC` bar is **not** a rest. It has no chord, so there is no guide tone to
        # place and nothing to comp: the caller drops the bar and warns, which is the
        # honest report. Answering `REST` here would emit a step where there should be
        # none and swallow that warning - measured: the `NC` bar reappeared in the
        # arrangement as a silent step, and
        # `test_an_nc_bar_is_reported_rather_than_silently_dropped` caught it
        # returning `['Dm7', 'NC', 'A7']` where it had returned `['Dm7', 'A7']`.
        #
        # So the grid only decides whether the guitar is silent *about a chord it
        # could otherwise state*. "Nothing here to play" and "nothing to say here" are
        # different claims, and only the first is a rest.
        if quality == NO_CHORD or name == NO_CHORD:
            return MELODY_ALONE_NONE
        return MELODY_ALONE_REST if not on_grid else MELODY_ALONE_NONE
    # The singing route answers `NC` the way it always has, and it must keep doing so
    # even though the comping route above returns `NONE` for the same slot: the two
    # routes build different steps there (the caller drops the bar and warns, versus
    # `get_melody_only_voicing` with `melody_only=True`), which is the reason this
    # function returns a *kind* and not a bool. Dropping the `NC` answer along with the
    # comping one sent the note through the harmonised path instead, where it found no
    # voicing and vanished - 11 tests across four files, all `NC`.
    if quality == NO_CHORD or name == NO_CHORD:
        return MELODY_ALONE_NO_CHORD
    if not on_grid:
        # **Off the grid.** The answer depends on whether the guitar is singing, which
        # is the whole reason this cannot be a bool on the texture case:
        #
        # - singing: the note of the tune still sounds, alone. This is
        #   `docs/comping-styles.md` §4.2's "a melody note with no chord position on
        #   it sounds alone", and it is the *texture* case - the step has a harmony,
        #   it is simply not being spelled out here, so `melody_only` must stay False.
        # - not singing: there is no melody on this guitar to play alone, and the
        #   tune belongs to the horn. The guitar is **silent**, which is what a comping
        #   grid means - a stab on the ands and nothing on the beats - and it is a
        #   fourth kind because no existing answer is that.
        #
        # Without the second case an off-grid slot fell through to the comping route
        # and comped anyway, the exact opposite of what `grid=joe_pass` asks for.
        # Without the first case it rested, and the guitar lost notes of the tune it
        # was supposed to be singing - measured at 39 of 80 steps on
        # `but_not_for_me` under `grid=freddie`, where every note off the beat went
        # silent instead of sounding alone.
        # Reached only when the guitar **is** singing, since the guard above answers
        # the comping route - so this is unconditionally the texture case: the note of
        # the tune still sounds, alone.
        return MELODY_ALONE_TEXTURE
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
    melody_only: bool = False,
) -> bool:
    """Whether a fill that produced nothing should be re-prepared as a principal note.

    A fill that cannot be filled must not cost the tune its chord: the texture is a
    lighter *texture*, never a missing harmony. So the step is retried as a target
    before it is reported as missing - the same argument that makes `NECK_FRET_MIN`
    a penalty rather than a filter.

    Disabled wherever a fill is *meant* to be empty - under `walking_bass`, and on a
    melody-only voice selection (`voices=soprano`) - because the melody-alone branch
    has already handled it, so promoting here would undo the selection one step at a
    time. The caller passes the selection fact from `melody_only_selection`, so it is
    derived in one place rather than re-decided here.

    `slot_grips != requested` is the "the role narrowed the caller's grips" case. If
    the two are equal the retry would ask for exactly what just failed, so it is
    skipped rather than repeated.
    """
    if has_thumb or melody_only:
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

    This is the rule the Weimar corpus brought (rule C), and it is what let
    `wjazzd.arrange_slots` - now `arranger.slots` - delegate to `arrange_progression`
    instead of running a second step loop. The
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

    `bass_cost` is passed in rather than imported because it lives in
    `arranger.slots`, which reaches this module through `steps`; a module-level
    import either way would be a cycle. Passing it also makes the dependency visible
    at the call site, which is the point: wanting a slash-bass preference is the only
    reason to supply one.
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
