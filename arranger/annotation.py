"""The explanation a rendered step carries, and the clauses it is made of.

A step records what it did and what shape it did it with; this module turns those
fields into the trailing prose. The clauses are composed in order rather than
branched at a return site, so a fact that corrects a column reaches every route that
can suffer it. `render` lays the result out beside the tab; the words live here.

This module imports `chords`, `cost`, `grip_tables` and `tuning` only, so it sits
below `render` in the dependency order and above the engine's axis modules.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from musthe import Note

from .chords import (
    ChordParser,
    bass_pitch_class,
    melody_degree_name,
    slash_bass,
    slash_bass_cost,
)
from .cost import SPAN_CRITERION, VOICING_COST_CRITERIA
from .grip_tables import INTERVAL_NAMES
from .tuning import (
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    PITCH_CLASS_NAMES,
    ROLE_FILL,
    SILENCE_GRID,
    SILENCE_NC_COMPING,
    SILENCE_NO_SHAPE,
    SILENCE_OUT_OF_REACH,
    SILENCE_TUNE_SILENT,
    ArrangementStep,
    Voicing,
    note_name,
)

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


def step_annotation(step: ArrangementStep) -> str:
    """
    Returns the non-chord-tone annotation for a step, e.g. '-> Cmaj9 via extension'.

    A melody-only (no chord) step is annotated instead with '(no chord - melody
    alone)'. A chord tone is annotated with the degree it is - '(harmony under b7)' - and
    comes back empty only when there is nothing to name: no melody, or a chord no table can
    read. Every one of those paths also carries the clauses read from the step itself where
    one applies - the octave a sounding melody was moved to, the chord a substitution
    produced, how many voices the shape states and which criterion turned a fuller one away,
    the voices it sounds and the degree each of them states, the neck window, a slash bass
    that is not sounded, and the held shape above a moving thumb (`_annotate`) - so "why is
    this shape like this, and why does this line not match
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
    not playing. A **comping** step (`melody_voiced` False) names every voice it states, each
    as its note and its degree, and
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
        unreadable = not melody_degree_label(step)
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
        # Nothing sounds. Each route that declines to play records its reason on
        # `step.silence`, so the line says which rather than naming a degree the
        # guitar is not playing - this is the one annotation that would be false
        # rather than merely thin. A hand-built silent step with no recorded
        # reason reads as the grid's own answer.
        return _annotate(step, _silence_clause(step))
    if step.bass_only:
        # A hold, and the step exists for the thumb: nothing above it is struck, so the
        # shape in the tab is the previous step's, still ringing. It was explained where
        # it was chosen, so the line says what this step is - a bass note under a shape
        # already down - and nothing about a shape of its own.
        #
        # **Before the comping branch**, because a lone thumb that has a shape ringing is
        # also a step that does not voice the tune, and the two answers differ: the
        # comping clause would name nothing here.
        return _annotate(step, _held_clause(step))
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
                step, f"interval fill - {INTERVAL_NAMES.get(size, '2 notes')}, partial"
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
    return _annotate(step, _degree_clause(step))


def _degree_clause(step: ArrangementStep) -> str:
    """The degree of the chord the tune sits on, where nothing else has claimed the line.

    A chord tone under the stated harmony is worth naming: the chord name alone does not
    say which note of it the melody is on, and the shape can look like any other
    chord-melody without that fact.

    `melody_degree_label` blanks for two different reasons and only one is worth saying.
    A slot the tune is silent at has no degree to name, while a melody over a chord no
    table can read is a fact the reader cannot get anywhere else - the chord column shows
    the spelling, not the problem. A non-chord tone with no degree to name and no chord to
    restate leaves `_substitution_clause` to say what the strategies did.
    """
    if step.non_chord_tone:
        return ""
    degree = melody_degree_label(step)
    if not degree:
        return "" if step.melody is None else "the chord symbol could not be read"
    return f"harmony under {degree}"


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

    Ten clauses are derived here rather than passed in, so that every path out of
    `step_annotation` that can have one carries it. Two correct a **column** and so are
    restated on every line that suffers them - the **octave** the sounding melody is at
    (`_transposition_clause`) and the chord the part actually **states**
    (`_substitution_clause`). Five explain the shape itself, and a hold is the one step that
    suppresses them: the shape **count** (`_shape_clause`, which stays silent on a hold
    because it was explained where the shape was chosen), the **voices** it sounds and the
    degree each states (`_sounding_clause`), the chord **tone** it leaves out
    (`_omission_clause`), the **window** it had to leave
    (`_window_clause`) and the **written bass** it does not sound (`_slash_bass_clause`).
    The **held shape above a moving thumb** (`_held_clause`) is not among them: it is what
    such a step *is*, so it is the step's own statement, as `repeated`'s is. The eighth is
    the shape given up so a **requested bass note** could sound (`_bass_room_clause`), and
    the ninth is the thumb that could not be placed at all (`_bass_refusal_clause`). The
    alternative is a dozen return sites each remembering to append them, which is how a
    fact comes to be printed on one route and silently dropped on another - and
    `_bass_annotation` is threaded the same way, through this list, for the same reason.

    Empty clauses are dropped, so a caller with nothing to say gets `_bass_annotation`'s
    own answer, which is the empty string for a step with no bass.
    """
    parts = [clause for clause in clauses if clause]
    derived = (
        _transposition_clause(step),
        _substitution_clause(step),
        _shape_clause(step),
        _sounding_clause(step),
        _omission_clause(step),
        _window_clause(step),
        _slash_bass_clause(step),
        _bass_alone_clause(step),
        _bass_room_clause(step),
        _bass_refusal_clause(step),
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

    Read only where the route *chose* the shape for a **melody** it pins - never on a
    comping shape, whose voice count belongs to `_comping_clause` because the selection
    asked for that many voices rather than the ranking settling for them - and never on a
    hold, which is annotated by what is *struck* while the shape itself is still ringing
    from the step before. Four voices is every string the right hand has, so a complete
    shape gets the count and no reason (the voices themselves are named by
    `_sounding_clause`).

    A comping step does record a palette, because *which* shape was played is a choice the
    request can force (`Palette.dropped_for_bass`); what a comping step's palette is not for
    is this count.

    The routes that state the count in their **own** clause keep the count to themselves:
    an `NC` bar reads "(no chord - melody alone)" and a melody no shape could voice reads
    "(melody alone - no voicing for this chord)", so restating it here would say the same
    word twice. That is the hold's rule on a second route, and it is about the *count*
    only - the palette a lone note came from is still what `_window_clause` reads.
    """
    palette = step.palette
    if (
        palette is None
        or not step.melody_voiced
        or step.repeated
        or step.bass_only
        or step.melody_only
        or step.chord_unvoiced
    ):
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
    """What the comping guitar states, by note and degree.

    A comping step is thin because the *selection* asked for that many voices - one per
    voice named - so the voice count is not the question a reader has. Which voices sound
    is: the guide pair states the 3rd and the 7th, and a one-voice bass selection states
    the root alone. They are read off the shape against the harmony it states, which is
    `harmonized_as` where the horn's note was accommodated with a substitute.

    Named as `note degree` pairs - `Bb Root, D 3 & G 6` - and not as degrees alone: the
    guitar has no melody here, so a degree with no note leaves the reader to work out which
    note of the chord the shape put where, and the tab gives frets rather than names. The
    spelling is `_voice_name`, the one the melody-bearing routes' `sounding:` clause uses.

    The `partial` label it replaces says "shell - 3rd & 7th" whatever the shape is, which
    is wrong rather than merely unsaid for every selection but the three-voice guide one:
    a single note on the low E string is not a shell's 3rd and 7th.
    """
    if not step.voicing.upper_midi_notes():
        # Nothing above the thumb is not comping: it is the bass part's own slot, and
        # `_bass_alone_clause` (or `_held_clause`) says what it is.
        return ""
    harmony = step.harmonized_as or step.chord
    root_str, _quality = ChordParser.parse_chord_name(harmony)
    # Keyed by degree *name*, so two octaves of one degree read once - at the note of the
    # first voice to state it, which is the lower one - and sorted by the interval from the
    # root, so a shape reads "Bb Root, D 3 & G 6" rather than in string order, which is
    # pitch order and would say "G 6, Bb Root & D 3".
    named: Dict[str, Tuple[int, str]] = {}
    for pitch in step.voicing.upper_midi_notes():
        note = Note(note_name(pitch))
        degree = melody_degree_name(note, harmony)
        if not degree or degree in named:
            continue
        interval = ChordParser.get_melody_degree(root_str, note) if root_str else 0
        named[degree] = (interval, _voice_name(pitch, degree))
    if not named:
        # A comping shape against a chord no table can read: the arity is all there is.
        return f"comping - {_comping_tail(step)}"
    ordered = sorted(named, key=lambda degree: named[degree][0])
    return f"comping - {_and_list([named[degree][1] for degree in ordered])}; {_comping_tail(step)}"


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


# Why a silent step sounds nothing, in the words the line prints. Keyed by the
# SILENCE_* constants; a step carrying no reason (a hand-built rest) reads as the
# grid's answer, which was the only reason before the other routes learned to emit
# a step of their own.
_SILENCE_PHRASES: Dict[str, str] = {
    SILENCE_GRID: "the guitar rests here - no part was asked to sound at this position",
    SILENCE_NC_COMPING: "the guitar rests here - no chord to comp",
    SILENCE_NO_SHAPE: (
        "the guitar rests here - no voicing for this chord and none for the melody"
    ),
    SILENCE_OUT_OF_REACH: "the guitar rests here - no string reaches the melody",
    SILENCE_TUNE_SILENT: "the guitar rests here - the tune is silent here",
}


def _silence_clause(step: ArrangementStep) -> str:
    """Why a step that sounds nothing is silent, read from `step.silence`.

    The five reasons are the five routes that can decline to play, and an
    all-muted fret vector cannot tell them apart: "the grid placed no chord",
    "there is no chord to comp" and "no string reaches the melody" are the same
    six mutes. A reason the table does not know - a future route, a typo by a
    hand-built caller - spells the grid's answer rather than printing nothing,
    which is the same rule `_criterion_phrase` follows for an unknown criterion.
    """
    return _SILENCE_PHRASES.get(step.silence or SILENCE_GRID, _SILENCE_PHRASES[SILENCE_GRID])


def _window_clause(step: ArrangementStep) -> str:
    """Says a shape had to leave the preferred frets, and what was inside them.

    The neck window is a **preference, never a filter**: a shape outside frets 2-13 is
    played rather than dropped, because losing a chord of the tune is worse than being a
    fret out of position. What a reader cannot see is whether the engine had anything
    inside. `Palette.inside_window` answers it, and the answer is provable in both
    directions: window penalties (element 1) are consulted before voice count (2) but
    after correctness (0), so a wholly in-window shape can only lose to an out-of-position
    one by sounding a note outside the chord.

    A **lone note** carries a palette of its own - one position per eligible string - and
    therefore ever gets only the second answer: every candidate sounds the same pitch
    class, so element 0 ties and element 1 decides, which means a palette with anything
    inside the window cannot have produced a shape outside it. "Nothing in this palette
    sat inside" is thus a fact about the palette rather than an excuse for the shape.
    """
    frets = step.voicing.active_frets()
    if not frets or all(NECK_FRET_MIN <= fret <= NECK_FRET_MAX for fret in frets):
        return ""
    where = f"reaches outside the preferred frets {NECK_FRET_MIN}-{NECK_FRET_MAX}"
    palette = step.palette
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
    that by partitioning the palette on `chords.slash_bass_cost` before the cost tuple runs.
    The partition only **prefers** it: a best score of at most
    `decisions.SLASH_BASS_SATISFIED` keeps the candidates within a tone of the written bass,
    and a chord nothing can reach is treated as if the slash had not been written. Either
    way the reader sees a symbol asking for a note the tab does not contain, and no part of
    the tab can say why - so the line says it, with the distance the selection settled for.

    Read from the step alone: the written bass comes out of the chord symbol
    (`chords.slash_bass`, the one place that rule lives) and the distance is
    `slash_bass_cost`'s own measure, the smallest interval from the written bass to the
    lowest sounding note.

    Reported on **every** route, comping included, because the fact is about the shape: a
    part that does not cover the written bass is worth knowing even where another
    instrument may be playing it.
    """
    written = slash_bass(step.chord)
    if written is None:
        return ""
    sounding = step.voicing.midi_notes()
    if not sounding:
        return ""
    wanted = bass_pitch_class(written)
    assert wanted is not None  # `slash_bass` returned a pitch name
    if any(pitch % 12 == wanted for pitch in sounding):
        return ""
    distance = slash_bass_cost(sounding, wanted)
    semitones = "semitone" if distance == 1 else "semitones"
    return (
        f"the written bass {written} is not sounded - the lowest voice "
        f"({note_name(min(sounding))}) is {distance} {semitones} from it"
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




def _bass_alone_clause(step: ArrangementStep) -> str:
    """Says a step is the thumb on its own, with no chord stated and none held.

    The bass part can have a slot the chord part does not: a `--chord-on` rhythm that
    does not name this position, or a selection with no chord part at all. Nothing
    above the thumb sounds there, and the tab cannot say what that is - six mutes and a
    fret look the same whether the chord ran out or was never asked for. A step with a
    shape still *ringing* is `_held_clause`'s, so this names the case where there is no
    shape at all, which is the opening of a bass line.
    """
    if step.bass is None or step.bass_only or step.voicing.upper_midi_notes():
        return ""
    return "the thumb alone - the chord part is not stated here"


def _bass_refusal_clause(step: ArrangementStep) -> str:
    """Says a thumb note the arrangement asked for could not be placed.

    `step.bass_refused` is the wanted pitch class, and the step is emitted with
    its upper voicing intact: only the thumb is missing. So the tab's fret vector
    has no hole in it a reader could count, and the walk reads as complete -
    which is the false reading this clause corrects.

    Four independent causes reach it, and the clause names **all four** rather
    than the one that fired, because they are indistinguishable from outside:
    no free string below the melody, no octave of the wanted pitch below the
    shape's own lowest note, a fifth fret for four fingers, or a reach wider than
    the hand's five frets. Measured over the committed heads the second one is
    almost the whole of it (`docs/open-issues.md` item 2), which is not the
    intuitive answer - so the list is the honest form. A per-cause spelling would
    need `place_bass` to return its reason, and that is the follow-on rather than
    the clause.

    Not suppressed on a hold, and it cannot be one: `bass_only` restates nothing
    above the thumb, but the step still carries the refusal for *this* beat's
    note, and a held shape's previous chord is a different fact.
    """
    if not step.bass_refused:
        return ""
    return (
        f"no playable bass note for bass {step.bass_refused} - no free string "
        f"below the melody, no octave of that pitch below the shape, the hand "
        f"would need a fifth fret, or the reach is wider than five frets; the "
        f"step keeps its upper voicing"
    )


def _bass_room_clause(step: ArrangementStep) -> str:
    """Says a shape was placed where the requested bass note could sound under it.

    A requested grid bass note is part of the request, so the palette is narrowed to the
    shapes the thumb can reach that note under *before* the ranking runs. What a reader
    counting strings cannot see is that the shape played is **not** the ranking's first
    choice: a wider fret position or a lower grip is exactly what it looks like, and
    neither says whether the engine had a better shape and gave it up.

    `Palette.dropped_for_bass` is that shape, read here rather than re-derived - a clause
    that recomputed "could the thumb reach it" would be the fact agreeing with itself. Not
    suppressed on a hold: the shape chosen here is what a hold is holding.
    """
    palette = step.palette
    if palette is None or palette.dropped_for_bass is None:
        return ""
    return (
        "placed to leave room for the requested bass note, where the ranking's own "
        "first choice "
        f"{palette.dropped_for_bass.tab_string()} could not sound it"
    )


def _omission_clause(step: ArrangementStep) -> str:
    """Says which of the chord's tones a four-voice shape leaves out.

    `TONE_PRIORITY` decides which tone a four-voice shape gives up when the chord has more
    tones than voices - the root first, then the natural 5th, and a name-given extension
    never. The tab cannot show that: the chord name above the step describes the harmony
    rather than the notes sounding under it, and four strings that count as a complete
    shape read as a complete chord. So the line names the tone the rule dropped.

    Only the **four-voice** shape is asked about, because that is the shape the rule is
    about. Fewer voices is a different decision with its own answer - a count from
    `_shape_clause`, or `partial`'s `shell - 3rd & 7th` - and a hold, a `bass_only` step
    and a melody alone were explained where the shape was chosen. A thin shell is
    therefore silent here even though it leaves tones out, which is the same boundary
    `_shape_clause` draws.

    Read from the step alone: the tones come from `chords.ChordParser` and the chord the
    part **states** (`harmonized_as` where a substitute was found), so this composes with
    `_substitution_clause` instead of contradicting it. The sounding pitches are
    `Voicing.midi_notes()` - the **whole** step, so a thumb that lands on the root counts
    as stating it, exactly as `_slash_bass_clause` reasons.
    """
    if step.repeated or step.bass_only or step.partial or step.melody_only:
        return ""
    if step.chord_unvoiced:
        return ""
    if len(step.voicing.upper_midi_notes()) != 4:
        return ""
    harmony = step.harmonized_as or step.chord
    root_str, quality = ChordParser.parse_chord_name(harmony)
    canonical = ChordParser.canonical_quality((quality or "").split("/", 1)[0])
    tones = ChordParser.CHORD_TONES_FROM_ROOT.get(canonical)
    if not root_str or not tones:
        return ""
    root_pc = Note(root_str + "4").midi_note() % 12
    sounding = {pitch % 12 for pitch in step.voicing.midi_notes()}
    missing = [tone for tone in tones if (root_pc + tone) % 12 not in sounding]
    if not missing:
        return ""
    # Named through `melody_degree_name`, the same vocabulary `_comping_clause` names the
    # degrees a shape *states* with, so one line's omission is the other line's list. Any
    # octave will do: the name depends on the interval from the root, not the register.
    names = [
        melody_degree_name(Note(note_name(48 + (root_pc + tone) % 12)), harmony)
        for tone in missing
    ]
    names = [name for name in names if name]
    if not names:
        return ""
    if len(names) == 1:
        return f"the chord tone it leaves out is {names[0]}"
    return f"the chord tones it leaves out are {_and_list(names)}"


def _voice_name(pitch: int, degree: str) -> str:
    """One voice as `note degree` - `Bb 5`, `Eb Root`.

    The spelling every clause shares: a bare degree cannot be checked against the tab, and
    a bare note name does not say what the note is to the chord.
    """
    return f"{PITCH_CLASS_NAMES[pitch % 12]} {degree}"


def _voice_pairs(step: ArrangementStep) -> List[str]:
    """Every upper voice as `note degree`, in the order the tab reads.

    The pitches are `Voicing.upper_midi_notes()` - the thumb is not one of them - and the
    order is the tab's, lowest string first, which is ascending pitch for a grip. The
    degree comes from `melody_degree_name`, the vocabulary the degree column and the
    omission clause already use, measured against the chord the part **states**
    (`harmonized_as` where a substitute was found), so one line cannot name a degree two
    ways or against a chord the guitar is not playing.
    """
    harmony = step.harmonized_as or step.chord
    return [
        _voice_name(pitch, melody_degree_name(Note(note_name(pitch)), harmony))
        for pitch in step.voicing.upper_midi_notes()
    ]


def _sounding_names(step: ArrangementStep) -> str:
    """Every voice of the shape as its note and its degree, or `""` if unnameable.

    Returns the empty string when the harmony cannot be read, so a caller prints
    nothing rather than a column of bare note names.
    """
    names = _voice_pairs(step)
    if not all(name.split(" ", 1)[-1] for name in names):
        return ""
    return ", ".join(names)


def _sounding_clause(step: ArrangementStep) -> str:
    """Names every voice the shape sounds, and the degree each of them states.

    The chord name above a step describes the harmony rather than the notes under the
    melody, and the tab gives frets rather than names, so the line says which notes
    make up the shape and how each stands against the chord.

    Every shape that sounds **two or more** upper voices answers, on any route the
    guitar sings the tune: a drop-2 chord-melody, a substituted one, a duo, an
    interval fill, a thin shell. Four routes stay silent, and each has its answer
    elsewhere on the same line:

    - a **repeated** melody is a soprano-only re-strike, whose other strings are
      stopped rather than held, so there is no shape sounding to list;
    - a **`chord_unvoiced`** step states no chord tone by construction, which is the
      fact its own clause reports;
    - the **thumb** is not in the list at all: `upper_midi_notes()` excludes it, and
      it has its own `bass:` clause, because it is a line under the shape rather than
      a voice of the harmony;
    - a **comping** step (`melody_voiced` False) is named by `_comping_clause` in the
      degrees it states, so listing them here would say the same word twice.

    A note may appear twice - a triad's fourth voice is its root doubled an octave
    below - and that is the shape rather than a defect, so duplicates are kept.
    """
    if (
        not step.melody_voiced
        or step.repeated
        or step.bass_only
        or step.chord_unvoiced
    ):
        return ""
    if len(step.voicing.upper_midi_notes()) < 2:
        return ""
    names = _sounding_names(step)
    if not names:
        return ""
    return f"sounding: {names}"


def _bass_annotation(step: ArrangementStep, existing: str = "") -> str:
    """Appends the walking-bass role and motion to another step's annotation.

    The role is worth printing because the thumb line is not uniformly chord
    tones - two thirds of the notes in a textbook walk are extensions or chromatic
    approaches - so a reader counting strings would otherwise wonder why the bass is
    not playing the chord the name above it says.

    The motion needs the *previous* step, which `step_annotation` is not given, so
    it is spelled from the step alone as `Ab (approach)`: enough to say what the note
    is for, which is the part that is not visible in the tab. `format_progression`
    prints one step per line and the chord name is already there, so a reader can
    see the descent by eye.

    Returns `existing` unchanged when the step carries no bass, which is every step
    of every other texture - so this cannot affect existing output.
    """
    if step.bass is None:
        return existing
    spelled = note_name(step.bass)
    # A ringing note rather than a struck one, said in the one place the reader looks
    # for the thumb: the tab draws a mute on that string, so without this the line
    # would show a bass note that is sounding with nothing to say it sounds.
    if step.bass_held:
        return f"{existing} (bass: {spelled}, held)"
    role = step.bass_role or "bass"
    return f"{existing} (bass: {spelled}, {role})"


def melody_degree_label(step: ArrangementStep) -> str:
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


def _annotation_units(body: str) -> List[Tuple[str, str]]:
    """An annotation's clauses as (joiner, text) pairs, in the order they print.

    The joiner is what precedes each clause - the empty string for the first, ` - ` for
    the next clause of the same parenthetical, and ` (` for the **bass** parenthetical,
    which `_bass_annotation` appends after the first one closes. Reading the boundaries
    out of the finished text rather than rebuilding the clause list is deliberate: the
    precedence between the routes is `step_annotation`'s, and a second copy of it here
    would be a second answer to one question.
    """
    units: List[Tuple[str, str]] = []
    joiner = ""
    for piece in body.split(" - "):
        head, marker, tail = piece.partition(") (")
        if marker:
            units.append((joiner, f"{head})"))
            units.append((" (", tail))
        else:
            units.append((joiner, piece))
        joiner = " - "
    return units


def _word_chunks(text: str, room: int) -> List[str]:
    """`text` split at its own spaces into chunks that fit `room` columns.

    A chunk is a run of whole words, and joining the chunks with a space gives `text`
    back. A single word wider than `room` is a chunk of its own and overflows, because
    cutting a word would put a syllable on one line and the rest on the next.
    """
    chunks: List[str] = []
    current = ""
    for word in text.split(" "):
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= room:
            current = f"{current} {word}"
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def annotation_lines(body: str, room: int) -> List[str]:
    """One annotation laid out over as many lines of at most `room` columns.

    The **clause boundaries are the break points**, so a line ends where a clause does
    rather than mid-phrase - which is what stops a line ending on the last word of a
    list (`… Ab 3, D` / `b7)`). A clause too wide for a line of its own is wrapped at its
    own spaces, and a single word wider than `room` overflows rather than being cut.

    Every character is printed, in order: a break stands in for the space it removes, so
    a line may end on a ` - ` and the next begin with the `(` of the bass parenthetical.
    """
    lines: List[str] = []
    current = ""
    for joiner, text in _annotation_units(body):
        chunks = _word_chunks(text, room)
        if current and len(current) + len(joiner) + len(text) > room:
            # A break stands in for a space, never for a character: the ` - ` separator
            # ends the line it was on, and the ` (` that opens the bass parenthetical
            # starts the next one, the `)` that closed the first having ended the line
            # before it.
            if joiner == " (":
                lines.append(current)
                current = "(" + chunks[0]
            elif len(current) + 2 <= room:
                lines.append(f"{current} -")
                current = chunks[0]
            else:
                # The line already reaches the margin, so the `-` opens the next line
                # instead of ending this one: the same three characters, one newline
                # later, and no line past the width.
                lines.append(current)
                current = f"- {chunks[0]}"
        else:
            current += joiner + chunks[0]
        for chunk in chunks[1:]:
            lines.append(current)
            current = chunk
    if current:
        lines.append(current)
    return lines

