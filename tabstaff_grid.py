"""Shared grid placement for the two whole-progression staff renderers.

`tabstaff_grid` owns everything the ASCII staff and the HTML page agree on:
placing each step on an absolute beat, deciding what is a strike and what is a
hold, computing rhythm values and bar positions. Both renderers call the same
functions, so a chord sits in the same column on the page and in the terminal
by construction and cannot drift apart.

The ASCII renderer (`tabstaff_ascii`) and the HTML renderer (`tabstaff_html`)
each import from here and add their own drawing on top. `tabstaff.py` is the
public facade that re-exports both renderers plus the MusicXML and GP5 writers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from arranger.step_types import ArrangementStep

# ---------------------------------------------------------------------------
# Grid placement
# ---------------------------------------------------------------------------

# Placing every step on an absolute beat, deduping onsets that collide, and
# filling the gaps between them with rests. `_staff_columns` is the one function
# both renderers call, so the ASCII staff and the HTML page place a chord in the
# same column by construction and cannot drift apart.


def _rest_grain(
    columns: Sequence[Tuple[float, Optional[ArrangementStep]]],
    beat_type: int,
) -> float:
    """
    The smallest gap, in beats, that this progression has a word for.

    `_staff_columns` emits a rest column per grain, so this is what decides whether a
    silence shorter than a beat is drawn at all. It is the shortest written duration in
    beats - `duration` is in whole notes and one beat is `1 / beat_type` of a whole
    note - bounded to at most one beat, because a gap of more than a beat is already
    covered by the barline and does not need a column for every beat of it.

    An untimed progression writes no durations and gets a grain of one beat, which is
    the one-column-per-beat grid it has always used.
    """
    written = [
        step.duration * beat_type
        for _onset, step in columns
        if step is not None and step.duration
    ]
    if not written:
        return 1.0
    return max(min(written), 1e-6)


def _placed_steps(
    steps: List[ArrangementStep],
    beats_per_bar: int,
    rhythm: bool,
) -> List[Tuple[float, ArrangementStep]]:
    """Every step on its absolute beat, or one per beat when there is no timing.

    An absolute beat is `bar * beats_per_bar + (beat - 1)`, the same signed-bar
    arithmetic NoteEvent.beat_position uses, so a pickup in a negative bar sorts
    before bar 0 without a special case. Without timing - a hand-written
    progression, or `rhythm=False` - each step simply takes the next beat,
    reproducing a one-chord-per-cell grid.
    """
    if _is_timed(steps, rhythm):
        return [
            (step.bar * beats_per_bar + (step.beat - 1), step)  # type: ignore[operator]
            for step in steps
        ]
    return [(float(index), step) for index, step in enumerate(steps)]


def _dedupe_onsets(
    placed: List[Tuple[float, ArrangementStep]],
) -> List[Tuple[float, Optional[ArrangementStep]]]:
    """One column per onset, sorted; the first step to claim an onset owns it.

    Two steps can share an onset (a chord change inside a held bar), and the onset
    is compared with an epsilon rather than for equality because it is a sum of
    floats.
    """
    columns: List[Tuple[float, Optional[ArrangementStep]]] = []
    for onset, step in sorted(placed, key=lambda item: item[0]):
        if columns and abs(columns[-1][0] - onset) < 1e-9:
            continue
        columns.append((onset, step))
    return columns


def _first_bar_content_end(
    columns: List[Tuple[float, Optional[ArrangementStep]]],
    beats_per_bar: int,
    beat_type: int,
) -> Optional[float]:
    """Where the first bar's music stops, if it stops before the bar line.

    `None` when the first bar is full, which is every head whose tune begins on a
    downbeat and runs through to the bar line. A value means the first bar is an
    **anacrusis**: `_fill_rests` leaves the silence after it unwritten so the bar
    stays short, and `format_tab_staff` closes it with the thin double bar line an
    engraver uses for a pickup. The value is in the same bar/beat units as the
    columns (a bar is `beats_per_bar` wide).
    """
    if not columns:
        return None
    first_bar = int(columns[0][0] // beats_per_bar)
    bar_end = float((first_bar + 1) * beats_per_bar)
    end = columns[0][0]
    for onset, step in columns:
        if int(onset // beats_per_bar) != first_bar:
            break
        if step is not None:
            if not step.duration:
                # A step with no written length runs to the next onset or the bar
                # line, so it fills whatever is left. A hand-built progression is
                # drawn that way, and it is not an anacrusis.
                return None
            end = max(end, onset + step.duration * beat_type)
    return end if end < bar_end - 1e-9 else None


def _fill_rests(
    columns: List[Tuple[float, Optional[ArrangementStep]]],
    beats_per_bar: int,
    beat_type: int,
    first_bar_implicit: Optional[bool] = None,
) -> List[Tuple[float, Optional[ArrangementStep]]]:
    """The grid: every onset, every hole between them, and the last bar padded out.

    Fill the holes a real rhythm leaves, so a chord held for two beats is
    followed by a rest rather than by the next chord jammed up against it.
    The grid starts at the first onset, not at zero: a head selected from bar 1
    (or from a negative pickup bar) should not be preceded by a screen of empty
    bars standing in for the music before it.

    **But not part-way through its own bar.** Starting at the onset dropped a
    leading rest *within* the first bar, so a head that enters on beat 2 - a pickup,
    which is how But Not For Me bar 1 is written - came out with its first fret hard
    against the opening barline and read as a downbeat. TuxGuitar's export draws the
    rest as dashes and puts the fret where it falls. The start is therefore rounded
    *down to the bar containing the first onset*, which preserves the rest inside
    that bar while still refusing to invent whole empty bars before it.

    `first_bar_implicit` is what the source said about the first bar. `False` means the
    bar is whole, so a short first bar is **filled** to its bar line like any other:
    the silence after its last note is a rest the score states, not an anacrusis. On
    `True` or `None` a short first bar is left short instead - the pickup convention
    this renderer has always drawn - because a source that says nothing gives the
    shortfall as the only evidence there is.
    """
    filled: List[Tuple[float, Optional[ArrangementStep]]] = []
    first_bar = int(columns[0][0] // beats_per_bar) if columns else 0
    first_bar_end = (
        None
        if first_bar_implicit is False
        else _first_bar_content_end(columns, beats_per_bar, beat_type)
    )
    current = (
        float(first_bar * beats_per_bar)
        if columns else 0.0
    )
    # **Fill at the music's own grain, and advance by what each step is worth.** A step
    # is not one beat long: `duration` is in whole notes and the default `eighths`
    # skeleton puts steps half a beat apart, so stepping a whole beat at a time (and
    # always advancing `onset + 1.0`) would skip every gap shorter than a beat and drop
    # the column at a bar's downbeat, and with it the tie into the bar's early beat.
    #
    # The grain is the shortest thing the progression actually writes, so a rest is
    # emitted at a resolution the music has a word for. `max(1.0, ...)` bounds it from
    # above: a gap longer than a beat is already covered by the barline and does not
    # need a column per beat, which is what kept the grid one column per beat for an
    # untimed progression.
    grain = _rest_grain(columns, beat_type)
    for onset, step in columns:
        while current < onset - 1e-9:
            if (
                first_bar_end is not None
                and current >= first_bar_end - 1e-9
                and int(current // beats_per_bar) == first_bar
            ):
                # **An incomplete first bar is an anacrusis.** Its silence after the
                # last note is not written, so the bar stays short and the double
                # bar line closes it where the music stops. Without this the grid
                # filled the bar out with rests and the pickup read as a downbeat.
                current = onset
                break
            filled.append((current, None))
            # Land exactly on the next onset rather than overshooting it, so the last
            # rest before a note is never drawn past the note it precedes.
            current = min(onset, current + grain)
        filled.append((onset, step))
        current = onset + (
            step.duration * beat_type if step is not None and step.duration else grain
        )
        # Cap `current` at bar end so a held note doesn't skip bars.
        bar_end = float((int(onset // beats_per_bar) + 1) * beats_per_bar)
        current = min(current, bar_end)

    # **Pad the last bar out to its own length.** The grid fills the holes *between*
    # onsets but stopped at the final one, so a head whose last note ends early left
    # its final bar short - `|-10--6-|` for a 4/4 bar that should be sixteen slots
    # wide, and the closing barline arriving mid-bar. The rest after the last note is
    # still time, and TuxGuitar draws it as dashes out to the barline. Only the *last*
    # bar is padded: every earlier one is closed by the next onset or the next bar's
    # first column, and padding those would invent silence that is not written.
    #
    # Before the `collapse` pass, deliberately: a padded column is a rest, and a rest
    # breaks the ring, so it has to reach that pass to be marked as one.
    if filled:
        bar_end = float((int(filled[-1][0] // beats_per_bar) + 1) * beats_per_bar)
        while filled[-1][0] < bar_end - 1e-9:
            filled.append((filled[-1][0] + 1.0, None))
    return filled


def _moved_thumb(
    step: Optional[ArrangementStep], previous: Optional[ArrangementStep]
) -> bool:
    """True when this column's thumb is a **new attack** under a shape it does not restate.

    `_collapse_holds` compares the *upper* voices, deliberately: a walking bass changes
    the lowest pitch every beat, so including it would mark every column a strike and
    turn the arrangement back into the chord list. The cost of that choice is that a
    column whose shape is held and whose thumb **moves** is drawn as a hold - and a
    hold draws nothing, so the new bass note vanished from the ASCII staff and the HTML
    while the one-line tab and the MusicXML both had it. This is the comparison that
    puts it back.

    Compared as `(bass_midi, bass_string)`, not by role: a thumb note can move to a
    different octave of the same pitch class (`--bass-on every-beat` does exactly that
    at a chord change), and a note that has changed octave is a note that is plucked.
    A **carried** thumb compares equal to the note it is still ringing from
    (`ArrangementStep.bass_held`), so it is not drawn again - which is this function's
    other half, and the reason the two features have to agree here.
    """
    if step is None or previous is None or step.voicing.bass_midi is None:
        return False
    return (step.voicing.bass_midi, step.voicing.bass_string) != (
        previous.voicing.bass_midi,
        previous.voicing.bass_string,
    )


def _draws(
    step: Optional[ArrangementStep],
    previous: Optional[ArrangementStep],
    string_index: int,
    strikes: bool,
) -> bool:
    """Whether this column draws a fret on this string.

    Three answers, and the third is the one the two halves of a hold need: a **strike**
    column follows `_strikes_here` (which knows about `repeated` and `bass_only`), a
    **hold** column draws nothing - except the thumb, when it has moved. Both renderers
    ask this one function, so the ASCII staff and the HTML cannot disagree about a
    column the way they did about the moved thumb.
    """
    if step is None:
        return False
    if string_index == step.voicing.bass_string and _moved_thumb(step, previous):
        return True
    return strikes and _strikes_here(step, string_index)


def _collapse_holds(
    filled: List[Tuple[float, Optional[ArrangementStep]]],
) -> List[Tuple[float, Optional[ArrangementStep], bool]]:
    """Mark each column as a fresh strike or a hold of the shape already ringing.

    A step sounding exactly the same pitches as the one before it is a *hold*: it
    stays on the grid (so the barlines and the chord line still line up) but prints
    no frets, because the previous shape is still ringing. That is what separates
    chord-melody tab from a chord list - the skeleton voices one step per eighth,
    and a player holds the shape rather than restriking it eight times a bar.
    Comparing sounding pitches rather than fret numbers is what makes this work:
    the same shape reached by a different route is still the same hold.

    The comparison is of the **upper** voices, so a walking bass does not destroy
    it. A thumb line changes the lowest pitch on every quarter, so comparing the
    full pitch set would mark every column a strike and turn the whole arrangement
    back into the chord list the 0.7.0 collapse behaviour exists to prevent.
    `Voicing.upper_midi_notes` does the exclusion, by the recorded bass string
    rather than a constant index, because the thumb moves between strings.

    What that exclusion costs is a **held column whose thumb moves**: it is a hold for
    the shape and a new attack for the bass, and a hold draws nothing at all - so
    without `_moved_thumb` the new note vanishes from this renderer and from the HTML
    while the one-line tab and the score both have it. `_moved_thumb` is that fact, and
    `_draws` is the one place both renderers act on it.
    """
    collapsed: List[Tuple[float, Optional[ArrangementStep], bool]] = []
    held: Optional[Tuple[int, ...]] = None
    for onset, step in filled:
        if step is None:
            # A rest breaks the ring: whatever was sounding has stopped, so the
            # next step is a fresh attack even when it is the same shape.
            held = None
            collapsed.append((onset, None, False))
            continue
        # The **upper** voices decide the hold: a walking bass moves the lowest pitch
        # every quarter, and comparing the full set would break the chain permanently.
        pitches = tuple(sorted(step.voicing.upper_midi_notes()))
        # A repeated melody still strikes: the soprano is re-articulated even when the
        # shape underneath is the one already ringing, so the note is heard again. The
        # renderers show the soprano alone and blank the held inner voices. A
        # `bass_only` step is the other half of that rule and is a strike for the
        # opposite reason: its *upper* voices are held while the thumb moves, so it
        # would otherwise be collapsed away entirely and the walking line with it.
        # A column with **no upper voices at all** cannot be holding a shape: whatever it
        # sounds - the thumb on its own - is struck. Without this a bass line of repeated
        # roots read as one note and three holds, so the staff showed two notes where the
        # tab showed four.
        #
        # `chord_attack` is the arrangement's own answer to "is this the same shape still
        # ringing, or did the rhythm ask for it again?". Pitches cannot say: a comp on
        # `--chord-on every-beat` repeats the identical shape on every beat, and the
        # pitches are equal whether the player holds it or strikes it. It is the mirror
        # of `repeated` - the tune re-articulated is a strike, the chord re-articulated
        # is one too - and the one exemption that has to be recorded rather than
        # compared. `_chord_attacks` is where the rule lives.
        sounding = sum(1 for fret in step.voicing.frets if fret >= 0)
        strikes = (
            pitches != held
            or step.repeated
            or step.bass_only
            or sounding <= 1
            or step.chord_attack
        )
        collapsed.append((onset, step, strikes))
        if strikes:
            held = pitches
    return collapsed


def _staff_columns(
    steps: List[ArrangementStep],
    beats_per_bar: int,
    beat_type: int,
    rhythm: bool,
    collapse: bool = True,
    first_bar_implicit: Optional[bool] = None,
) -> List[Tuple[float, Optional[ArrangementStep], bool]]:
    """
    The grid both renderers draw: every step on an absolute beat, the holes a real
    rhythm leaves padded with rests, and each column marked as a strike or a hold.

    Four stages, each stated once for both renderers. `_placed_steps` puts each step
    on its absolute beat; `_dedupe_onsets` gives one column per onset;
    `_fill_rests` adds the rests and pads the last bar out; `_collapse_holds` marks a
    repeated shape as a hold rather than a new attack. `collapse=False` skips only
    the last - the columns are the same, and every one of them strikes.

    `first_bar_implicit` is the source's statement about the first bar and reaches
    `_fill_rests`, the stage that decides whether a short first bar is left short.
    """
    placed = _placed_steps(steps, beats_per_bar, rhythm)
    columns = _dedupe_onsets(placed)
    filled = _fill_rests(columns, beats_per_bar, beat_type, first_bar_implicit)
    if not collapse:
        return [(onset, step, True) for onset, step in filled]
    return _collapse_holds(filled)


def _is_timed(steps: List[ArrangementStep], rhythm: bool) -> bool:
    """
    True when these steps carry a rhythm worth placing and worth printing.

    The single predicate both the column grid and the rhythm row go through, so the
    rhythm row can never claim a written rhythm the columns were not laid out by. A
    progression of hand-built steps carries no `bar`/`beat`, and then the grid is
    one chord per beat - which is also why there is no rhythm to print.
    """
    return bool(rhythm) and bool(steps) and all(step.has_timing for step in steps)


def _beat_in_quarters(beat_type: int) -> float:
    """
    How many quarter notes one **beat** is: `4 / beat_type`.

    The divisor is the load-bearing part, and `docs/renderers.md` records four
    separate bugs caused by getting it wrong. A 2/2 beat is a **half** note - two
    quarters - so the tempting `beat_type / 4` is right in 4/4 and four times too
    small in 2/2, which is the one metre that cannot catch it.

    Printing a note value is what requires it: a *beat* is a counting position and a
    *length* is measured in quarters, so a renderer that only counts beats needs no
    `beat_type` and one that prints a duration does.
    """
    return 4.0 / float(beat_type)


# The note values a rhythm row can print, as (quarters, label). A whole note down
# to a thirty-second, then the dotted and triplet forms of the same, so the common
# cases are two characters and fit the fret cell width without widening the grid.
_NOTE_VALUES: Tuple[Tuple[float, str], ...] = (
    (4.0, "w"), (2.0, "h"), (1.0, "q"), (0.5, "e"), (0.25, "s"), (0.125, "32"),
    (3.0, "w."), (1.5, "h."), (0.75, "q."), (1.25, "e."),
    (4.0 / 3.0, "3w"), (2.0 / 3.0, "3h"), (1.0 / 3.0, "3q"), (0.5 / 3.0, "3e"),
)

# Printed in a rhythm row for a column that continues a note begun earlier - a held
# shape, or the space a longer note occupies. `~` is the tie, which is what the
# MusicXML and GP5 renderers write for the same event.
_HOLD_LABEL = "~"

# Printed for a column with no step on it: the silence is a rest, and it is time.
_REST_LABEL = "r"


#: The rhythmic grid a whole note is divided into when drawing a staff.
#:
#: **Eight slots to the whole note - an eighth-note grid - is the floor**, and a bar
#: of a quarter rest and three quarter notes is what sets it: four notes on an
#: eighth-note grid, so no finer grid would make that bar any longer.
#: `docs/renderers.md` holds the measurement against `jon6.tab`.
#:
#: The floor only rises for music finer than an eighth - `_slots_per_whole` scales it
#: up so the shortest note in the progression still occupies at least one slot. A
#: grid coarser than that would round two different notes to the same width and lose
#: the difference, which is the one thing the width is there to keep.
_SLOTS_PER_WHOLE = 8


def _note_value(quarters: float) -> str:
    """
    One note value as the two-or-three characters a rhythm cell can hold.

    The nearest nameable value wins, within a small tolerance - so a triplet eighth
    is `3e` and a dotted quarter is `q.`, the two the score renderers write for the
    same length, rather than something this module invented.

    A length nothing names falls back to **the number of quarters**, e.g. `0.67q`,
    rather than to the nearest legal note. That is the honest answer: a transcribed
    head does contain onsets that are not a clean power of two, and rounding one to
    a neighbouring note value would print a note that is not being played. It is
    also wider than a fret cell, so it widens the grid through the same `width`
    computation every other label goes through - which is the point of that being
    one calculation.
    """
    for length, label in _NOTE_VALUES:
        if abs(length - quarters) < 1e-6:
            return label
    return f"{quarters:.2f}q"


def _staff_rhythm(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    beats_per_bar: int,
    beat_type: int,
    timed: bool,
) -> List[Tuple[str, str]]:
    """
    The note value of every column, as (label, kind) parallel to `columns`.

    `kind` is `note`, `hold` or `rest`, and it is what makes a rhythm row readable
    rather than a row of letters: a held shape and a rest both print something in
    a column with no new attack, and they mean opposite things.

    **A column's length runs to the next column that has a step on it**, which is
    the same rule `tabscore.score_events` applies to a score - a note lasts until the next
    sound - and the `None` columns in between are *not* the next sound. They are
    rests `_staff_columns` invented to fill a gap, and treating the first of them
    as an ending is what made this print a quarter note where the score writes a
    whole one. The length is then capped at **the end of its own bar**: a note is
    written in the bar it starts in, and sounding past the barline is a tie, which
    this grid has no way to draw.

    Two further consequences of sharing the rule rather than inventing one:

    - the transcribed `duration` **caps** the gap and is never stretched to it. A
      note written as a quarter followed by a quarter of silence is `q` and then a
      rest, not `h`. `duration` is in whole notes, so it is scaled by 4 here.
    - a column whose step is a *hold* prints the tie rather than a note value,
      because the note it belongs to began in an earlier column. `tabxml` writes
      that as a `<tie>` and `tabgp` as `NoteType.tie`; this is the same event.

    It is computed from the **column grid**, not from `tabscore.score_events`, because the
    two grids are deliberately different: `score_events` keeps every step sharing an
    onset and divides the span between them, while `_staff_columns` gives the column
    to the first and drops the rest. Sharing the tuple would be lossy in one
    direction or the other. What is shared is the *rule* above - and where a step
    does share its onset, the two renderers will therefore disagree about the
    length, because the staff has one column for two notes and the score has two
    notes. That is the column grid's own documented lossiness, not a third
    convention, and `TestStaffRhythmAgreesWithTheScore` checks the cases where the
    grids do line up.

    `timed` false means there is no rhythm to state: a hand-written progression, or
    `rhythm=False`, puts one chord on every beat, so every value would be the same
    letter and the row would say nothing. The caller drops it in that case.
    """
    if not timed or not columns:
        return []

    beat_in_quarters = _beat_in_quarters(beat_type)
    bar_length = float(beats_per_bar)
    rhythm: List[Tuple[str, str]] = []
    for index, (onset, step, strikes) in enumerate(columns):
        if step is None:
            # Silence, one beat of it. `_staff_columns` fills holes one beat at a
            # time, so the next column is a whole beat away.
            rhythm.append((_REST_LABEL, "rest"))
            continue
        if not strikes:
            # A held shape: the note began in an earlier column and is still
            # sounding, so this column is the tie rather than a fresh note value.
            rhythm.append((_HOLD_LABEL, "hold"))
            continue
        # The next **sounding** column, skipping the rests in between. Those rests are
        # gap-filling, not music: `_staff_columns` invents a column wherever onsets
        # skip a beat, and treating the first as an ending is what made this print a
        # quarter note where the score writes a whole one.
        following = next(
            (later for later in range(index + 1, len(columns))
             if columns[later][1] is not None),
            None,
        )
        if following is not None:
            span = (columns[following][0] - onset) * beat_in_quarters
        else:
            # No next sound at all: the note runs to the end of its own bar, which is
            # the same default `tabxml` uses for the last group. Left at zero it would
            # print `0.00q`.
            span = float("inf")
        # **Capped at the end of its own bar.** A note is written in the bar it starts
        # in: sounding past the barline is a tie in a score, and this grid has no tie
        # to draw - the columns after the barline are its own. Without the cap a
        # transcription with a four-beat hole in it printed a six-quarter "note" in one
        # cell and widened the whole staff to fit it.
        bar_end = (int(onset // bar_length) + 1) * bar_length
        span = min(span, max(bar_end - onset, 1.0) * beat_in_quarters)
        # The transcribed duration caps it further, and is never stretched to.
        # A hand-built step has none, and then the gap stands on its own.
        if step.duration:
            span = min(span, step.duration * 4.0)
        rhythm.append((_note_value(span), "note"))
    return rhythm


def _meter_label(beats_per_bar: int, beat_type: int) -> str:
    """
    The written metre as it is notated: `4/4`, `2/2`, `3/4`.

    **A count without a denominator is not a metre.** 2/2 and 2/4 are both two beats
    to the bar and the same bar length, so `beats_per_bar` alone cannot say which
    one a head is in - and a tune in cut time displayed as common time is the kind
    of error that reads as a rendering bug rather than as a misreading of the score.
    Three of the four committed test scores are 2/2.

    It is the same string `tabxml` writes into `<time>` and `tabgp` into its
    `TimeSignature`, from the same two arguments, so the three renderers cannot
    state three different metres for one arrangement.
    """
    return f"{beats_per_bar}/{beat_type}"


def _strikes_here(step: ArrangementStep, string_index: int) -> bool:
    """True when this step sounds a string, given the two partial-attack cases.

    Three states, and the difference between the last two is the whole texture:

    - **ordinary** - every sounding string is struck;
    - **`repeated`** - the melody re-articulates under an unchanged harmony, so the
      soprano alone strikes and the inner voices are held;
    - **`bass_only`** - the slot exists for the thumb, so the bass alone strikes and
      every voice above it is held from the previous shape.

    A `bass_only` step is the step the thumb invented: the chord's rhythm did not name
    this position, the harmony did not change, and the melody is the note still ringing
    (`decisions.is_bass_only`). Nothing above the thumb is struck there, so the column is
    the bass alone and the shape ringing is the previous step's. A step that arrived
    carrying both `bass_only` and `repeated` rendered here as a blank column over a moving
    bass, which is how the chords of nine downbeats in "But Not For Me" went missing - the
    engine cannot produce one now (`is_bass_only` clears `repeated`), and the union below
    is what makes a hand-built step behave.

    A `repeated` step under a walking bass is the intersection: the soprano **and**
    the thumb both strike, and only the inner voices are held. The two rules are
    opposites rather than variants - one holds everything above the thumb, the other
    everything below the soprano - and a step that is both must honour both, which is
    why this is a union of two sets rather than a chain of `elif`.

    Shared by the ASCII cell and the HTML cell so the two renderings cannot disagree
    about which strings sound; both go through `_staff_columns`, and this is the
    other half of that guarantee.

    This says nothing about whether an unsounded string is drawn as `x`: a mute is
    an **absence** of a note rather than an attack withheld, which is why an ordinary
    step returns True here and leaves the fret check to the caller. Filtering muted
    strings out of this predicate is what would silence `show_mutes` and the `x`s a
    melody-only step spells out.
    """
    if step.bass_held and string_index == step.voicing.bass_string:
        # The thumb is still ringing: the note was drawn where it was struck, and this
        # column does not pluck it again. Asked before `melody_only` because a
        # melody-only selection still has a bass part, and before `repeated` because the
        # soprano re-strike and the ringing thumb are different strings.
        return False
    if step.melody_only:
        return True
    if step.bass_only:
        return string_index == step.voicing.bass_string
    if step.repeated:
        if not step.melody_voiced:
            # No soprano to re-strike: the whole comping shape is held, because the
            # horn repeating the note is not something the guitar articulates. The same
            # rule `render._step_cells` applies, and the reason it is stated in both is
            # that this pair is what keeps the ASCII staff, the HTML and the one-line
            # renderer from disagreeing about what attacks.
            return True
        struck = {step.voicing.soprano_string()}
        if step.voicing.bass_midi is not None:
            struck.add(step.voicing.bass_string)  # type: ignore[arg-type]
        return string_index in struck
    return True


def _carries_melody(steps: List[ArrangementStep], string_index: int) -> bool:
    """True when the melody rides on this string somewhere in the progression.

    `melody_voiced` is read rather than re-derived from the shape, because the two
    disagree on the comping route: a guide-tone shell built from the chord alone
    still has a highest sounding note, so deriving the marker from the shape stars
    a string on a part that is not singing - and the staff claims the tune for the
    guitar exactly where the arrangement handed it to the horn. The marker is a
    claim about *who has the melody*, and `melody_voiced` is that claim; the shape
    only says where a note sits.
    """
    return any(
        step.melody_voiced
        and step.voicing.frets[string_index] >= 0
        and step.voicing.soprano_string() == string_index
        for step in steps
    )


def _melody_label(step: Optional[ArrangementStep]) -> str:
    """The melody row's cell for one step: the note's name, or blank once it is released.

    The row labels every step, because the tune moves on while the shape underneath is
    held - which is exactly why the one cell it must not label is a note a **chord attack
    ended**. That note is not sounding, and its name on the row would claim the tune is
    still in. `annotation._comping_tail` says which note the stab took.
    """
    if step is None or step.melody_released:
        return ""
    return step.melody or ""


def _staff_bars(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    beats_per_bar: int,
) -> List[int]:
    """
    The bar number of every column, as a list parallel to `columns`.

    Both renderers need this and neither should compute it twice: a barline and a
    system break are two *different* questions asked of the same numbers (see
    `_staff_barlines` and `_staff_breaks`), and answering them from one list is what
    stops the two renderers from disagreeing about where a bar ends.
    """
    return [int(onset // beats_per_bar) for onset, _step, _strikes in columns]


def _staff_barlines(bars: List[int]) -> set:
    """
    The column indexes that open a new bar.

    **Every bar is marked, not every `measures_per_line`th one.** This was the
    opposite decision once - barlines were spaced by `measures_per_line`, on the
    reasoning that a barline every bar cluttered a grid already dense with columns.
    But a barline is not clutter: it is the one mark that says where the metre
    falls, and without one at every bar a reader cannot tell a two-bar phrase from a
    four-bar one, or see where a held chord crosses into the next measure. TuxGuitar,
    Guitar Pro and printed tab all mark every bar, and this is the staff agreeing
    with them rather than a cosmetic preference.

    Index 0 is never marked: the line opens with a barline of its own, so marking
    the first column too would draw two.
    """
    return {index for index in range(1, len(bars)) if bars[index] != bars[index - 1]}


def _staff_breaks(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    beats_per_bar: int,
    measures_per_line: int,
) -> set:
    """
    The column indexes that begin a new *system* - a fresh line of music.

    A distinct question from `_staff_barlines`: a barline says where the metre falls and
    lands on every bar, while a system break says where the printed line ends and is the
    only thing `measures_per_line` governs. Keeping them separate lets the staff both
    rule every bar and wrap at a readable width, which is what TuxGuitar's export does
    and what the flag's name claims.

    A system begins on the first column of a bar, so a column qualifies only when
    its bar differs from the previous column's. Testing the bar number alone would
    flag every column of that bar - and since a bar holds several columns, the
    staff would come out with a break between every chord.

    Breaks are measured from the first column's own bar rather than from bar 0,
    because a head picked up mid-transcription (a negative pickup bar, or a
    `--bars` range that starts at 12) must not be padded out by the bars before it.
    """
    bars = _staff_bars(columns, beats_per_bar)
    start_bar = bars[0] if bars else 0
    return {
        index
        for index in _staff_barlines(bars)
        if (bars[index] - start_bar) % measures_per_line == 0
    }


_NAVIGATION_LABELS = {
    "segno": "Segno",
    "coda": "Coda",
    "fine": "Fine",
    "to_coda": "To Coda",
    "da_capo": "D.C.",
    "da_capo_al_fine": "D.C.",
    "da_capo_al_coda": "D.C.",
    "da_segno": "D.S.",
    "da_segno_al_fine": "D.S.",
    "da_segno_al_coda": "D.S.",
}


def _marker_columns(
    bars: List[int],
    markers: Sequence[Any],
) -> Tuple[Dict[int, str], Dict[int, str]]:
    """The repeat, ending and navigation signs, keyed by the column a bar opens at.

    **Repeat and ending signs are keyed by the global column a bar opens at.** A
    repeated head has had its bars expanded by the importer, so the arrangement already
    contains every bar a player plays; these markers put the `|:` / `:|` and `1.` / `2.`
    back on the page so a reader can see the repeat rather than only its effects.
    `_staff_bars` counts in the same bar numbers the steps carry (`onset = bar *
    beats_per_bar + ...`, so bar N is the value N), which is what makes a marker's bar
    the key to find its column. A bar opens with `|:` when a repeat starts there and
    `:|` when the bar before it was the repeat's end; an ending's number and a
    navigation sign are labels on their opening bar.

    Returns `(barline_token, label_at)`, both empty when there is nothing to draw.
    """
    open_column: Dict[int, int] = {}
    for index, value in enumerate(bars):
        open_column.setdefault(value, index)
    barline_token: Dict[int, str] = {}
    label_at: Dict[int, str] = {}
    for marker in markers:
        if marker.kind == "repeat_start":
            index = open_column.get(marker.bar)
            if index is not None:
                barline_token[index] = "|:"
        elif marker.kind == "repeat_end":
            # The `:|` is drawn where the *next* bar opens - the end of this one.
            index = open_column.get(marker.bar + 1)
            if index is not None:
                barline_token[index] = ":|"
        else:
            label = None
            if marker.kind == "ending_start":
                label = ",".join(str(n) for n in marker.numbers) + "."
            elif marker.kind in _NAVIGATION_LABELS:
                label = _NAVIGATION_LABELS[marker.kind]
            index = open_column.get(marker.bar)
            if label is not None and index is not None:
                # Two labels on one bar share the cell rather than one replacing the
                # other; a volta and a D.C. on the same bar is rare, but losing one of
                # them silently is exactly what this row exists to prevent.
                existing = label_at.get(index)
                label_at[index] = f"{existing} {label}" if existing else label
    return barline_token, label_at
def _validate_staff_arguments(
    beats_per_bar: int, beat_type: int, measures_per_line: int
) -> None:
    """Reject a metre or line width the staff cannot be drawn with."""
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if beat_type < 1:
        raise ValueError(f"beat_type must be at least 1, got {beat_type!r}")
    if measures_per_line < 1:
        raise ValueError(
            f"measures_per_line must be at least 1, got {measures_per_line!r}"
        )


def _staff_lines(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    breaks: set,
    beats_per_bar: int,
) -> List[List[int]]:
    """
    Splits the columns into the systems of music that will be drawn, in order.

    A system ends at a barline, so a break both closes one system and opens the
    next. Columns that fall between barlines are all kept, including the rests.
    The last system may be short, which is why this returns a list of lists rather
    than a single count.
    """
    lines: List[List[int]] = []
    current: List[int] = []
    for index, _column in enumerate(columns):
        if index in breaks and current:
            lines.append(current)
            current = []
        current.append(index)
    if current:
        lines.append(current)
    return lines
