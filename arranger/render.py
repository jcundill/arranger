"""Per-step rendering: one compact line per chord.

`format_progression` is the compact renderer, and it is **pure** - it returns a
string and prints nothing, so the caller stays in control of the output. The
whole-progression staff renderers are a different shape of output and live in
`tabstaff`; a six-line vertical block for a *single* voicing is
`Voicing.tab_block()`, which is not the same surface.

`_step_annotation` is shared by `format_progression` and the demonstration, so the
two renderings cannot drift apart. A step can be several things at once - a
non-chord tone, a chord tone with a degree to name, a repeated melody, a partial
shell, a thumb note - and the precedence between them is the whole content of that
function.

The tab-cell primitives (`_MUTED_CELL`, `_cells_from_frets`) are **not** defined
here: `Voicing.tab_block` calls them and `Voicing` sits below this module, so they
live in `tuning` and are imported from there. `_STAFF_CELL_WIDTH` and
`_tab_block_from_cells` live in `tuning` for the same reason and are imported from
there too.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from musthe import Note

from .chords import ChordParser, melody_degree_name
from .cost import SPAN_CRITERION, VOICING_COST_CRITERIA
from .grips import _INTERVAL_NAMES
from .slots import _slash_bass, bass_pitch_class, slash_bass_cost
from .tuning import (
    _MUTED_CELL,
    _STAFF_CELL_WIDTH,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    ROLE_FILL,
    ArrangementStep,
    Voicing,
    _cells_from_frets,
    _note_name,
)

__all__ = ["_MUTED_CELL", "_STAFF_CELL_WIDTH", "format_progression"]


# How a duo's **second voice** is named in a printed annotation, keyed by the interval it
# forms with the melody, modulo 12 - so a 9th or a 10th reads as the 3rd it is a compound
# form of, which is what a player calls it.
#
# These name the **interval**, not the chord function, and that is deliberate. A duo is
# built from the chord's guide tone, but the interval it makes with the melody is what the
# reader sees in the tab, and the two do not always agree: Cmaj7 with its root in the
# melody puts the 3rd (E) eight semitones below, which is a major 6th as an interval. So
# the label reads "melody + 6th" for a root-and-3rd pair. Naming it "3rd" there would
# describe the chord degree while contradicting the fretting, and a reader checking one
# against the other is exactly who this annotation is for.
#
# A suspended chord's guide tone is a 4th or a 9th, which is a 5th or a 6th as an interval
# below. A diminished chord's guide tone is a diminished 5th, a tritone below. Every
# semitone count from 2 upward is reachable and listed: a table with a hole in it would
# print "chord tone" for a real interval, which is the one thing worse than no label.
_DUO_SECOND_VOICE_NAMES: Dict[int, str] = {
    2: "2nd", 3: "b3", 4: "3rd", 5: "5th", 6: "b5", 7: "5th",
    8: "b6", 9: "6th", 10: "7th", 11: "7th",
}


def _step_annotation(step: ArrangementStep) -> str:
    """
    Returns the non-chord-tone annotation for a step, e.g. '-> Cmaj9 via extension'.

    A melody-only (no chord) step is annotated instead with '(no chord - melody
    alone)'. A chord tone is annotated with the degree it is - '(harmony under b7)' - and
    comes back empty only when there is nothing to name: no melody, or a chord no table can
    read. Every one of those paths also carries the clauses read from the step itself where
    one applies - the octave a sounding melody was moved to, the chord a substitution
    produced, how many voices the shape states and which criterion turned a fuller one away,
    the neck window, a slash bass that is not sounded, and the held shape above a moving
    thumb (`_annotate`) - so "why is this shape like this, and why does this line not match
    the score?" is answered by the line. Shared by format_progression and the demonstration
    so the two renderings cannot drift apart.
    The bass annotation is appended by `_bass_annotation` on **every** path out of
    this function, including the early returns: a walking step can equally be a
    melody-only fill, a repeated melody or a partial shell, and a bass note that is
    only annotated on some of those would be a worse defect than no annotation at
    all. Steps with no bass - every step of every other texture - come back
    unchanged.

    Three routes are *answered* rather than described, because each is a case where the
    obvious annotation would be false or silent. A step with **nothing sounding** is the
    grid declining to place a chord, and says so rather than naming a degree the guitar is
    not playing. A **comping** step (`melody_voiced` False) names the degrees it states and
    says the tune is not the guitar's, since its thinness is the caller's selection rather
    than a palette limit (`_comping_clause`). And a melody whose chord symbol no table can
    read says *that*, instead of leaving the degree column blank with no reason. Two losses
    the tab cannot show are added on every path that can suffer them: a shape that had to
    leave the preferred frets (`_window_clause`) and a written slash bass no shape sounds
    (`_slash_bass_clause`).
    """
    if step.melody_only:
        return _annotate(step, "no chord - melody alone")
    if step.chord_unvoiced:
        # The chord is in force and nothing here states it: the palette had no shape
        # under this melody note at all. Without this the step reads as a bare note
        # beneath a chord symbol, which is the other case `partial` exists to prevent
        # - and unlike a thin shell or duo there is not even a second voice to count.
        #
        # Composed with the transposition note rather than replacing it: the rescue
        # drops a high note an octave *and* leaves the chord unstated (measured: two
        # steps of "The Jitterbug Waltz"), and printing one of the two facts would hide
        # the other.
        unreadable = not _melody_degree_label(step)
        # A chord no table can read has no shape to offer either, so the *symbol* is the
        # reason here: "no voicing for this chord" would blame the grips for a spelling
        # nobody could parse (`Czz`), which is the opposite of what happened.
        #
        # Composed with the transposition note by `_annotate` rather than here: the rescue
        # drops a high note an octave *and* leaves the chord unstated (measured: two steps of
        # "The Jitterbug Waltz"), and printing one of the two facts would hide the other.
        reason = (
            "the chord symbol could not be read" if unreadable
            else "no voicing for this chord"
        )
        return _annotate(step, f"melody alone - {reason}")
    if not step.voicing.active_frets():
        # Nothing sounds. The grid declined to place a chord on this beat, and the step
        # exists so the horn's position and the thumb's walk keep their place in the tab -
        # so naming a degree under it would claim the guitar is playing something it
        # muted. This is the one annotation that was not merely thin but false.
        return _annotate(step, "the guitar rests here - the grid places no chord")
    if not step.melody_voiced:
        # The comping route: the guitar states harmony and somebody else has the tune.
        # The partial branch below would call a single bass note "shell - 3rd & 7th",
        # which is where the arity and the family are both wrong rather than unsaid.
        return _annotate(step, _comping_clause(step))
    if step.repeated:
        # A hold is annotated by what is **struck**, and the shape it holds was explained on
        # the step that chose it - which is why `_shape_clause` stays silent here. The
        # clauses that correct a *column* are not suppressed: a held note still shows its
        # pitch and its octave.
        return _annotate(step, "melody repeated - single note")
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
            return _annotate(
                step, f"interval fill - {_INTERVAL_NAMES.get(size, '2 notes')}, partial"
            )
        if step.grip == "duo":
            # Name the pair from the notes that actually sound, as the interval branch
            # above does. A duo can produce `(3,7)`, `(4,7)`, `(0,4)` and `(0,3)` - a b3
            # with a 5th, a 3rd with a 5th, a root with a 3rd, a root with a b3 - so a
            # single fixed label would be wrong for all but one of them, and would name
            # degrees the melody is not limited to.
            #
            # The **upper** voices, for the reason given above: the thumb is a walking
            # line underneath and is not part of the pair.
            upper = sorted(step.voicing.upper_midi_notes())
            if len(upper) == 2:
                size = (upper[-1] - upper[0]) % 12
                return _annotate(
                    step,
                    f"duo - melody + {_DUO_SECOND_VOICE_NAMES.get(size, 'chord tone')}, partial",
                )
            return _annotate(step, "duo - partial")
        return _annotate(step, f"{step.grip} - 3rd & 7th, partial")
    if not step.non_chord_tone:
        # A chord tone under the stated harmony: name the degree it is. The chord name
        # alone does not say which note of it the tune is sitting on, and the shape can
        # look like any other chord-melody without that fact.
        degree = _melody_degree_label(step)
        if not degree:
            # `_melody_degree_label` blanks for two different reasons and only one of them
            # is a thing to say: a slot the tune is silent at has no degree to name, while
            # a melody over a chord no table can read is a fact the reader cannot get
            # anywhere else - the chord column shows the spelling, not the problem.
            if step.melody is None:
                return _annotate(step)
            return _annotate(step, "the chord symbol could not be read")
        return _annotate(step, f"harmony under {degree}")
    # A non-chord tone with no degree to name and no chord to restate: the substitution
    # clause says what the strategies did, so this path has nothing left to add.
    return _annotate(step)


def _transposition_clause(step: ArrangementStep) -> str:
    """Says the sounding pitch is an octave below the written one.

    A clause rather than a branch, because the two steps it accompanies both need it *and*
    another fact: the melody column shows the pitch that sounds, so a reader comparing the
    line with the score cannot see the octave for themselves. Measured before this was
    derived: 22 steps stated a substitute chord with the octave unmentioned, and 2 held a
    transposed note under `melody repeated - single note`.
    """
    if step.original_melody is None:
        return ""
    return f"transposed down an octave from {step.original_melody}"


def _substitution_clause(step: ArrangementStep) -> str:
    """What the non-chord-tone strategies did, whether or not they succeeded.

    `step.harmonized_as` is the substitute where one was found, so the melody route and the
    comping route print one sentence for it. Where none was found the written chord stands
    and the strategy is named, which is what tells a substitution that **failed** from one
    that was never attempted: measured over the committed corpus, 2,713 steps kept the
    written chord under a melody outside it.
    """
    if step.harmonized_as:
        return f"non-chord tone -> {step.harmonized_as} via {step.strategy}"
    if step.non_chord_tone and step.strategy:
        return (
            f"non-chord tone - the {step.strategy} strategy found no voicing; "
            "the written chord stands"
        )
    return ""

def _annotate(step: ArrangementStep, *clauses: str) -> str:
    """Wrap a step's clauses - with the clauses read from the step itself - into the line.

    Six clauses are derived here rather than passed in, so that every path out of
    `_step_annotation` that can have one carries it. Two correct a **column** and so are
    restated on every line that suffers them - the **octave** the sounding melody is at
    (`_transposition_clause`) and the chord the part actually **states**
    (`_substitution_clause`). Four explain the shape itself, and a hold is the one step that
    suppresses them: the shape **count** (`_shape_clause`, which stays silent on a hold
    because it was explained where the shape was chosen), the **window** it had to leave
    (`_window_clause`), the **written bass** it does not sound (`_slash_bass_clause`) and the
    **held** shape above a moving thumb (`_held_clause`). The alternative is a dozen return
    sites each remembering to append them, which is how a fact comes to be printed on one
    route and silently dropped on another - and `_bass_annotation` is threaded the same way,
    through this list, for the same reason.

    Empty clauses are dropped, so a caller with nothing to say gets `_bass_annotation`'s
    own answer, which is the empty string for a step with no bass.
    """
    parts = [clause for clause in clauses if clause]
    derived = (
        _transposition_clause(step),
        _substitution_clause(step),
        _shape_clause(step),
        _window_clause(step),
        _slash_bass_clause(step),
        _held_clause(step),
    )
    for clause in derived:
        if clause:
            parts.append(clause)
    if not parts:
        return _bass_annotation(step)
    return _bass_annotation(step, f" ({' - '.join(parts)})")


def _shape_clause(step: ArrangementStep) -> str:
    """How many voices the step states, and why not more, from its recorded palette.

    The chord name above a step describes the harmony rather than every note sounding
    under it, so a reader counting strings cannot tell a shell that had no alternative
    from one that was chosen over a complete chord. `step.palette` is that answer: the
    most voices the palette offered, and the fuller shape it did not take.

    Read only where the route *chose* the shape - `palette` is None on a comping shape, a
    fill and a rescued melody - and never on a hold, which is annotated by what is
    *struck* while the shape itself is still ringing from the step before. Four voices is
    every string the right hand has, so a complete shape gets the count and nothing else.
    """
    palette = step.palette
    if palette is None or step.repeated:
        return ""
    voices = len(step.voicing.upper_midi_notes())
    count = "melody alone" if voices == 1 else f"{voices} voices"
    if palette.alternative is None:
        if voices >= 4:
            return count
        # The palette is thin, and *why* it is thin is worth saying: a fill is a connecting
        # note rather than a chord to state, so the texture asked for fewer voices there -
        # which is a different answer from the library having nothing to offer.
        whose = "a fill's" if step.role == ROLE_FILL else "this"
        return f"{count}, the most {whose} palette offers"
    fuller = palette.alternative
    return (
        f"{count}: the {len(fuller.active_frets())}-voice voicing "
        f"{fuller.tab_string()} {_criterion_phrase(palette.decided_by, fuller)}"
    )


def _criterion_phrase(decided_by: Optional[int], fuller: Voicing) -> str:
    """Why a fuller shape lost, in `cost.voicing_cost`'s own vocabulary.

    The span is the one criterion whose magnitude is visible in the shape, so it is
    spelled with its fret count rather than as an adjective: the stretch can be read off
    the tab, and what a reader wants is how wide it is.
    """
    if decided_by is None:
        # Unreachable for a *fuller* shape - its voice count is a smaller `missing` term
        # on its own, so the two cost tuples cannot be equal. Spelled rather than
        # asserted so that a future criterion cannot turn this into a traceback.
        return "lost to the order the grips are offered in"
    if decided_by == SPAN_CRITERION:
        return f"needs a {fuller.fret_span()}-fret stretch"
    return VOICING_COST_CRITERIA[decided_by]


def _comping_clause(step: ArrangementStep) -> str:
    """What the comping guitar states, in the degrees it sounds.

    A comping step is thin because the *selection* asked for that many voices - one per
    voice named - so the voice count is not the question a reader has. Which degrees sound
    is, and they are the family as well: `harmony=guide` states the 3rd and the 7th,
    `shell_root` puts a root or a 5th under them, and a one-voice bass selection states
    the root alone. They are read off the shape against the harmony it states, which is
    `harmonized_as` where the horn's note was accommodated with a substitute.

    The `partial` label it replaces says "shell - 3rd & 7th" whatever the shape is, which
    is wrong rather than merely unsaid for every selection but the three-voice guide one:
    a single note on the low E string is not a shell's 3rd and 7th.
    """
    harmony = step.harmonized_as or step.chord
    root_str, _quality = ChordParser.parse_chord_name(harmony)
    # Keyed by degree *name*, so two octaves of one degree read once, and sorted by the
    # interval from the root, so a shape reads "3, 5 & 7" rather than in string order -
    # which is pitch order, and would say "5, 7 & 3".
    degrees: Dict[str, int] = {}
    for pitch in step.voicing.upper_midi_notes():
        note = Note(_note_name(pitch))
        degree = melody_degree_name(note, harmony)
        if not degree or degree in degrees:
            continue
        degrees[degree] = (
            ChordParser.get_melody_degree(root_str, note) if root_str else len(degrees)
        )
    if not degrees:
        # A comping shape against a chord no table can read: the arity is all there is.
        return f"comping - {_comping_tail(step)}"
    ordered = sorted(degrees, key=lambda named: degrees[named])
    return f"comping - {_and_list(ordered)}; {_comping_tail(step)}"


def _comping_tail(step: ArrangementStep) -> str:
    """Whether the guitar is declining the tune or the tune is not there to decline.

    `melody_voiced` False alone cannot tell the two apart, and the line said "the guitar
    does not play the tune" for both: measured over the corpus, 2,107 steps are positions
    the *tune* is silent at - a grid stab with no note under it - where that reads as a
    claim about a note that is not sounding at all.
    """
    if step.melody is None:
        return "the tune is silent here"
    return "the guitar does not play the tune"


def _and_list(items: List[str]) -> str:
    """`3rd & 7th`, `root, 3rd & 7th` - a shape's degrees as a reader would say them."""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} & {items[-1]}"


def _window_clause(step: ArrangementStep) -> str:
    """Says a shape had to leave the preferred frets, and what was inside them.

    The neck window is a **preference, never a filter**: a shape outside frets 2-13 is
    played rather than dropped, because losing a chord of the tune is worse than being a
    fret out of position. What a reader cannot see is whether the engine had anything
    inside. `Palette.inside_window` answers it, and the answer is provable in both
    directions: window penalties (element 1) are consulted before voice count (2) but
    after correctness (0), so a wholly in-window shape can only lose to an out-of-position
    one by sounding a note outside the chord.
    """
    frets = step.voicing.active_frets()
    if not frets or all(NECK_FRET_MIN <= fret <= NECK_FRET_MAX for fret in frets):
        return ""
    palette = step.palette
    if palette is None and len(step.voicing.upper_midi_notes()) < 2:
        # The tune alone with no palette consulted - an NC step, or a melody nothing could
        # voice. There was no shape to choose, so the melody's own fret is the melody's
        # business and not a decision to explain.
        return ""
    where = f"reaches outside the preferred frets {NECK_FRET_MIN}-{NECK_FRET_MAX}"
    if palette is None:
        # A comping shape: the window is the caller's selection's business, and there is no
        # palette to report on.
        return where
    if palette.inside_window:
        return f"{where} - the shapes inside the window sound a note outside the chord"
    return f"{where} - nothing in this palette sits inside the window"


def _slash_bass_clause(step: ArrangementStep) -> str:
    """Says when the written slash bass is not among the notes played.

    A symbol like `Cmaj/D` asks for the D *as the lowest voice*, and the engine prefers
    that by partitioning the palette on `slots.slash_bass_cost` before the cost tuple runs.
    The partition only **prefers** it: a best score of at most
    `decisions.SLASH_BASS_SATISFIED` keeps the candidates within a tone of the written bass,
    and a chord nothing can reach is treated as if the slash had not been written. Either
    way the reader sees a symbol asking for a note the tab does not contain, and no part of
    the tab can say why - so the line says it, with the distance the selection settled for.

    Read from the step alone: the written bass comes out of the chord symbol
    (`slots._slash_bass`, the one place that rule lives) and the distance is
    `slash_bass_cost`'s own measure, the smallest interval from the written bass to the
    lowest sounding note.

    Reported on **every** route, comping included, because the fact is about the shape: a
    part that does not cover the written bass is worth knowing even where another
    instrument may be playing it.
    """
    written = _slash_bass(step.chord)
    if written is None:
        return ""
    sounding = step.voicing.midi_notes()
    if not sounding:
        return ""
    wanted = bass_pitch_class(written)
    assert wanted is not None  # `_slash_bass` returned a pitch name
    if any(pitch % 12 == wanted for pitch in sounding):
        return ""
    distance = slash_bass_cost(sounding, wanted)
    semitones = "semitone" if distance == 1 else "semitones"
    return (
        f"the written bass {written} is not sounded - the lowest voice "
        f"({_note_name(min(sounding))}) is {distance} {semitones} from it"
    )


def _held_clause(step: ArrangementStep) -> str:
    """Says the upper shape is held, on the steps that exist for the thumb alone.

    `bass_only` is exactly that claim, and the tab cannot show it: the shape printed there
    is the previous step's, still ringing, with a new bass note under it. A reader who
    re-strikes it plays a chord the engine deliberately did not.
    """
    if not step.bass_only:
        return ""
    return "the shape above is held"




def _bass_annotation(step: ArrangementStep, existing: str = "") -> str:
    """Appends the walking-bass role and motion to another step's annotation.

    The role is worth printing because the thumb line is not uniformly chord
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


def _step_cells(step: ArrangementStep) -> List[str]:
    """The tab cells for one step, honouring step.repeated and step.bass_only.

    Every string this step does not play is marked muted ('x'), so the line states
    which strings are plucked and nothing else. That is the rule for all three cases
    the flags describe, including a bass slot.

    A repeated melody is played as a **single note**: only the soprano string is
    struck, and its shape has collapsed to that note, so the other strings are stopped
    rather than held.

    `bass_only` is the mirror image arithmetically - the thumb alone is new - but its
    upper voices are **held** from the previous shape rather than restruck. They are
    still printed as 'x': this renderer answers "what is plucked here", so a string the
    player must not attack reads the same as a mute. It only ever describes a **fill**,
    because a target states its harmony instead (`decisions.is_bass_only`) - a step
    marked both rendered here as a blank column, which is how a chord the engine had
    already voiced went missing. A step that is *both* `repeated` and `bass_only` is a
    walking bass under a re-articulated melody, and it plays the soprano and the thumb -
    so the two rules compose rather than override one another, which is the case an
    `elif` chain would silently drop.

    The step still carries a full drop-2 `voicing`: the engine voice-leads from
    it and a caller wanting the literal shape still has `step.tab_line()`.

    **`melody_voiced=False` removes the soprano from the `repeated` rule.** A repeat is
    a soprano-only re-strike, which presumes there *is* a soprano carrying the tune; under
    `melody="none"` the guitar has none, so striking "the soprano" would strike a
    guide tone and the shape would change on a beat where nothing has. The rule becomes
    **hold the whole shape**, which is what a guitarist comping behind a horn actually
    does while the horn repeats the note.

    This is not a corner case: a filter that assumed a soprano carries the tune renders
    every such step as a single moving note, and the part would then play a melody line the
    arrangement had explicitly given away. `tabstaff._strikes_here` reads the same
    predicate, so the ASCII staff, the HTML and this one cannot disagree about what
    attacks.
    `docs/engine.md` holds the measurement.
    """
    frets = step.voicing.frets
    partial = (step.repeated or step.bass_only) and not step.melody_only
    if not partial:
        return _cells_from_frets(frets)
    struck = set()
    if step.bass_only:
        struck.add(step.voicing.bass_string)
    if step.repeated:
        if not step.melody_voiced:
            # Hold the whole shape: the soprano is not ours to re-strike, and the
            # inner voices are still ringing from the step before. `bass_only` is a
            # separate case above and composes with this one, exactly as it does when
            # the guitar does sing.
            return _cells_from_frets(frets)
        struck.add(step.voicing.soprano_string())
        # A repeated melody still moves the thumb: the bass is a moving voice, not a
        # held one, so blanking it here would silently delete the walking line.
        if step.voicing.bass_midi is not None:
            struck.add(step.voicing.bass_string)
    # Every string the step does not play is muted: the line states what is plucked.
    cells = [_MUTED_CELL] * len(frets)
    for string_index in struck:
        if string_index is not None and 0 <= string_index < len(frets):
            cells[string_index] = str(frets[string_index])
    return cells


def _melody_degree_label(step: ArrangementStep) -> str:
    """The melody's degree above its chord: its chord tone, or the tension it names.

    Blank when there is nothing to measure - no melody (a comping slot at a position
    the tune is silent at), or a chord no table can read (`NC`, or a quality with no
    tone set). A `chord_unvoiced` step keeps its degree, because the chord is still in
    force even though nothing here states it, and a transposed melody is unaffected:
    the degree is a pitch class, and dropping an octave does not change it.
    """
    if step.melody is None:
        return ""
    return melody_degree_name(Note(step.melody), step.chord)


def _format_step(step: ArrangementStep) -> str:
    """One compact line: chord, melody, degree column, tab, then any annotation.

    The first three columns are fixed width, and the annotation - whose text length
    varies - is **appended after the tab** rather than printed between the melody and
    it. That is what stops the shape drifting: an inline annotation is as wide as its
    own text, so every annotated step used to start its tab in a different column
    from every unannotated one.

    Each tab is **hyphen-joined and ragged** - `x-11-x` is wider than `x-x-x` - so a
    shape's own width varies. The field holding it is padded to the widest a six-cell
    tab can be, which is what starts every annotation in the same column.
    """
    cells = _step_cells(step)
    tab = "-".join(cells)
    # Two characters per cell - a fret reaches 18 - plus one hyphen between each pair.
    width = len(cells) * _STAFF_CELL_WIDTH + len(cells) - 1
    line = (
        f"{step.chord:<8} {(step.melody or ''):<3} "
        f"{_melody_degree_label(step):<4} {tab:<{width}}"
    )
    annotation = _step_annotation(step)
    if not annotation:
        # No explanation, so no column to hold open: drop the field's padding rather
        # than leave a run of trailing spaces.
        return line.rstrip()
    return f"{line} {annotation}"


def format_progression(steps: List[ArrangementStep]) -> str:
    """
    Renders an arranged progression as tab and returns it as a string.

    This is a pure renderer: it prints nothing and writes nothing to stdout, so
    the caller stays in control of the output. Each step is one line in four fixed
    columns - chord, melody, the melody's degree above the chord, and the tab - so
    every shape starts in the same column:

        Dm7      D5  Root x-x-10-10-10-10    (harmony under Root - 4 voices)
        G7       B4  3    13-x-12-12-12-x    (harmony under 3 - 4 voices)
        Cmaj7    C5  Root x-x-9-9-8-8        (harmony under Root - 4 voices)

    Each tab is hyphen-joined and ragged, so shapes differ in width; the **field** is
    padded to the widest a six-cell tab can be, which starts every **annotation**
    (below) in the same column rather than wherever the shape happens to end.

    The **degree column** names the melody's relationship to its chord - a chord tone
    as the degree it is (`Root`, `3`, `b7`), a note outside the chord as the tension it
    spells (`b9`, `#11`, `13`). It is `chords.melody_degree_name`, and it is blank when
    there is no melody or no readable chord to measure against.

    The **annotation** (`_step_annotation`) is appended after the tab rather than
    inline, which is what keeps the tab column fixed: an inline annotation is as wide
    as its own text, so an annotated step's tab would start further right than an
    unannotated one's.

    The six-line vertical form is not this renderer's: a whole-progression staff is what
    a player reads, and `format_tab_staff` in `tabstaff` renders one, with the chords on
    their real beats. **This renderer is the compact one-line summary and nothing else**,
    which is the shape the demo and `make demo` print.

    A single voicing still renders vertically through `Voicing.tab_block()` / `.tab()` and
    `ArrangementStep.tab_block()`, which is where `_tab_block_from_cells` lives.

    Args:
        steps: arrangement steps, typically from VoiceLeadingEngine.arrange_progression.

    Returns:
        The rendered tab, with steps separated by newlines.
    """
    return "\n".join(_format_step(step) for step in steps)


def _print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    print(
        f"Chord: {step.chord:<8} | Melody: {(step.melody or ''):<3}{_step_annotation(step)} | "
        f"Tab [E-A-D-G-B-E]: {'-'.join(_step_cells(step))} | Melody string: {melody_string}"
    )
