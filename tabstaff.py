"""Whole-progression tab renderers: the six-line ASCII staff and the HTML page.

These are the two renderers that lay an arrangement out **along one staff in
reading order**, rather than one block per chord as `format_progression()` does:

- `format_tab_staff` - the ASCII staff, for a terminal.
- `format_tab_html` / `write_tab_html` - a self-contained HTML page for a browser.

They live together because they share `_staff_columns`, which places each step on
an absolute beat and decides what is a strike and what is a hold. That sharing is
the point: both renderings place a chord in the same column *by construction* and
cannot drift apart, which is what the two grids have to agree on for the `collapse`
behaviour to mean the same thing in each.

Split out of `arranger.py` so the renderers can grow without making the voicing
engine harder to read. Everything here imports from `arranger`, never the reverse,
except for the public re-exports at the bottom - see the note there.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from arranger.tuning import _MUTED_CELL, STRING_NAMES, ArrangementStep

# The MusicXML and Guitar Pro renderers are ordinary top-level imports, re-exported
# from `arranger` so that `from arranger import format_musicxml` - the spelling in
# the README, the tests and `wjazzd` - keeps working.
#
# They used to be resolved through a module-level `__getattr__`, on the stated
# grounds that `tabxml` and `tabgp` "import this module" and would therefore
# re-enter a half-initialised one. **That stopped being true in Phase 5**: both now
# import `arranger.tuning` - a leaf module with no dependencies of its own - and
# `tabgp` imports `tabxml`, not the reverse. Nothing here imports `tabstaff`.
#
# Nor is the laziness buying anything. `tabxml` needs music21 and `tabgp` needs
# PyGuitarPro, but each imports its extra *inside* the functions that use it, so
# importing either module is free on a machine that has neither. That was
# measured - both import cleanly with `sys.modules['music21'] = None` - rather than
# assumed, because the lazy import was originally added to make the extras
# optional and it is worth knowing whether that is still the reason it exists.
#
# Re-exporting here is what keeps one spelling for the whole rendering surface:
# `from arranger import format_musicxml` resolves through this module, and
# `arranger/__init__.py` re-exports *this* module's names.
from tabgp import format_gp5, write_gp5
from tabxml import format_musicxml, write_musicxml

# The width every fret cell is padded to. Two characters covers frets 0-18, the
# whole range the library allows, and matches the convention `Voicing.tab_block()`
# uses, so the vertical block and the staff put a fret in the same column.
_STAFF_CELL_WIDTH = 2



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


def _staff_columns(
    steps: List[ArrangementStep],
    beats_per_bar: int,
    beat_type: int,
    rhythm: bool,
    collapse: bool = True,
) -> List[Tuple[float, Optional[ArrangementStep], bool]]:
    """
    Places each step on an absolute beat, padding the gaps with rests.

    An absolute beat is `bar * beats_per_bar + (beat - 1)`, the same signed-bar
    arithmetic NoteEvent.beat_position uses, so a pickup in a negative bar sorts
    before bar 0 without a special case. The list is sorted and de-duplicated
    because two steps can share an onset (a chord change inside a held bar), and
    the first step in a column owns that column.

    Each column comes back with a `strikes` flag. With `collapse` on, a step
    sounding exactly the same pitches as the one before it is a *hold*, not a new
    attack: it stays on the grid (so the barlines and the chord line still line
    up) but prints no frets, because the previous shape is still ringing. That is
    what separates chord-melody tab from a chord list - the skeleton voices one
    step per eighth, and a player holds the shape rather than restriking it eight
    times a bar. Comparing sounding pitches rather than fret numbers is what makes
    this work: the same shape reached by a different route is still the same hold.

    The comparison is of the **upper** voices, so a walking bass does not destroy
    it. A thumb line changes the lowest pitch on every quarter, so comparing the
    full pitch set would mark every column a strike and turn the whole arrangement
    back into the chord list the 0.7.0 collapse behaviour exists to prevent.
    `Voicing.upper_midi_notes` does the exclusion, by the recorded bass string
    rather than a constant index, because the thumb moves between strings.

    Without timing - a hand-written progression, or `rhythm=False` - each step
    simply takes the next beat, reproducing a one-chord-per-cell grid.
    """
    if _is_timed(steps, rhythm):
        placed: List[Tuple[float, ArrangementStep]] = [
            (step.bar * beats_per_bar + (step.beat - 1), step)  # type: ignore[operator]
            for step in steps
        ]
    else:
        placed = [(float(index), step) for index, step in enumerate(steps)]

    columns: List[Tuple[float, Optional[ArrangementStep]]] = []
    for onset, step in sorted(placed, key=lambda item: item[0]):
        if columns and abs(columns[-1][0] - onset) < 1e-9:
            continue
        columns.append((onset, step))

    # Fill the holes a real rhythm leaves, so a chord held for two beats is
    # followed by a rest rather than by the next chord jammed up against it.
    # The grid starts at the first onset, not at zero: a head selected from bar 1
    # (or from a negative pickup bar) should not be preceded by a screen of empty
    # bars standing in for the music before it.
    #
    # **But not part-way through its own bar.** Starting at the onset dropped a
    # leading rest *within* the first bar, so a head that enters on beat 2 - a pickup,
    # which is how But Not For Me bar 1 is written - came out with its first fret hard
    # against the opening barline and read as a downbeat. TuxGuitar's export draws the
    # rest as dashes and puts the fret where it falls. The start is therefore rounded
    # *down to the bar containing the first onset*, which preserves the rest inside
    # that bar while still refusing to invent whole empty bars before it.
    filled: List[Tuple[float, Optional[ArrangementStep]]] = []
    current = (
        float(int(columns[0][0] // beats_per_bar) * beats_per_bar)
        if columns else 0.0
    )
    # **Fill at the music's own grain, and advance by what each step is worth.** This
    # used to step one whole beat at a time and always advance `onset + 1.0`, on the
    # assumption that a step is a beat long. It is not: `duration` is in whole notes and
    # the default `eighths` skeleton puts steps half a beat apart, so every gap shorter
    # than a beat was skipped outright. Bar 11 of But Not For Me lost its downbeat
    # column entirely that way, and with it the tie into the bar's early beat.
    #
    # The grain is the shortest thing the progression actually writes, so a rest is
    # emitted at a resolution the music has a word for. `max(1.0, ...)` bounds it from
    # above: a gap longer than a beat is already covered by the barline and does not
    # need a column per beat, which is what kept the grid one column per beat for an
    # untimed progression.
    grain = _rest_grain(columns, beat_type)
    for onset, step in columns:
        while current < onset - 1e-9:
            filled.append((current, None))
            # Land exactly on the next onset rather than overshooting it, so the last
            # rest before a note is never drawn past the note it precedes.
            current = min(onset, current + grain)
        filled.append((onset, step))
        current = onset + (
            step.duration * beat_type if step is not None and step.duration else grain
        )

    # **Pad the last bar out to its own length.** The grid fills the holes *between*
    # onsets but stopped at the final one, so a head whose last note ends early left
    # its final bar short - `|-10--6-|` for a 4/4 bar that should be sixteen slots
    # wide, and the closing barline arriving mid-bar. The rest after the last note is
    # still time, and TuxGuitar draws it as dashes out to the barline. Only the *last*
    # bar is padded: every earlier one is closed by the next onset or the next bar's
    # first column, and padding those would invent silence that is not written.
    #
    # Before the `collapse` split below, deliberately: a padded column is a rest, and a
    # rest breaks the ring, so it has to reach the collapse pass to be marked as one.
    if filled:
        bar_end = float((int(filled[-1][0] // beats_per_bar) + 1) * beats_per_bar)
        while filled[-1][0] < bar_end - 1e-9:
            filled.append((filled[-1][0] + 1.0, None))

    if not collapse:
        return [(onset, step, True) for onset, step in filled]

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
        strikes = pitches != held or step.repeated or step.bass_only
        collapsed.append((onset, step, strikes))
        if strikes:
            held = pitches
    return collapsed

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

    The staff renderers worked in *beats* throughout and never converted to a
    length, which is why they took no `beat_type` at all. Printing note values is
    what ended that: naming a length means measuring it, and a length is measured
    in quarters.
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
#: **Eight slots to the whole note - an eighth-note grid - is the floor**, and it is
#: measured, not guessed: in `jon6.tab`, a bar of a quarter rest and three quarter
#: notes is seventeen characters, which is one lead-in dash plus eight slots of two
#: characters. That is four notes on an eighth-note grid, and no finer grid would
#: make that bar any longer.
#:
#: The floor only rises for music finer than an eighth - `_slots_per_whole` scales it
#: up so the shortest note in the progression still occupies at least one slot. A
#: grid coarser than that would round two different notes to the same width and lose
#: the difference, which is the one thing the width is there to keep.
_SLOTS_PER_WHOLE = 8


def _slots_per_whole(steps: List[ArrangementStep]) -> int:
    """
    The rhythmic grid for a whole note: `_SLOTS_PER_WHOLE`, or finer if needed.

    Scales up only when some note is shorter than half a slot at the floor, so that
    the shortest note in the progression never rounds away to nothing. Half a slot
    rather than a whole one, because a note that rounds *down* to zero width is
    invisible while one that rounds down to half is still a slot wide.
    """
    shortest = min(
        (step.duration for step in steps if step.duration), default=None
    )
    if shortest is None or shortest <= 0:
        return _SLOTS_PER_WHOLE
    return max(_SLOTS_PER_WHOLE, int(-(-0.5 // shortest)))


def _slot_counts(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    beats_per_bar: int,
    beat_type: int,
    slots_per_whole: int,
) -> List[int]:
    """
    How many grid slots each column occupies - the whole of the duration fix.

    **A column used to be one beat wide whatever the note was worth**, so a quarter and
    a half note were drawn identically and the tab said nothing about how long anything
    sounded. The ASCII tab conveys duration by *width*: a note two beats long is drawn
    across two slots, and the dashes between are the sound continuing.

    Three things this has to get right, and each was measured against `jon6.tab`:

    - **The units are whole notes.** `ArrangementStep.duration` is in whole notes
      (`tuning.py`), and this used to multiply it by a slot count as though it were in
      beats - so a quarter note, `duration=0.25`, came out one slot wide instead of
      four and every bar in the piece drew at the same width.
    - **A beat is not a slot-count either.** The grid is per *whole note*, so a bar in
      4/4 and a bar in 2/2 are both sixteen sixteenths and both sixteen slots at a
      finer grid; `beat_type` reaches this as the conversion from beats to whole notes
      rather than as a scale factor.
    - **Holds and rests get their real span.** They were pinned to one slot, which is
      what made a pickup's leading rest too short to see and left a half-note hold as
      narrow as a sixteenth. The rule is the one `_staff_rhythm` already uses: a column
      runs to the next *sounding* column, capped at its own barline.
    """
    bar_in_whole = beats_per_bar / float(beat_type)
    counts: List[int] = []
    for index, (onset, _step, _strikes) in enumerate(columns):
        bar_end = (int(onset // beats_per_bar) + 1) * beats_per_bar
        # The next sounding column is where this one stops making sound. A held column
        # has a step of its own and so counts as sounding, which is what makes an
        # attack and the holds under it add up to the note's real length.
        following = next(
            (later for later in range(index + 1, len(columns))
             if columns[later][1] is not None),
            None,
        )
        span = (columns[following][0] if following is not None else bar_end) - onset
        span = min(span, bar_end - onset, bar_in_whole)
        whole = span / float(beat_type)  # a beat is `1 / beat_type` of a whole note
        counts.append(max(1, int(round(whole * slots_per_whole))))
    return counts


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
    the same rule `tabxml._events` applies to a score - a note lasts until the next
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

    It is computed from the **column grid**, not from `tabxml._events`, because the
    two grids are deliberately different: `_events` keeps every step sharing an
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

    A `bass_only` step is a **fill**, always: a target states the harmony, so the engine
    never marks one (`decisions.is_bass_only`). A step that arrived carrying both flags
    rendered here as a blank column over a moving bass, which is how the chords of nine
    downbeats in "But Not For Me" went missing - see `docs/open-issues.md` item 4.

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
    """True when the melody rides on this string somewhere in the progression."""
    return any(
        step.voicing.frets[string_index] >= 0
        and step.voicing.soprano_string() == string_index
        for step in steps
    )


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

    This is now a different question from `_staff_barlines`, where it used to be the
    same one: a barline says where the metre falls and lands on every bar, while a
    system break says where the printed line ends and is the only thing
    `measures_per_line` still governs. Splitting them is what lets the staff both
    rule every bar and wrap at a readable width, which is what TuxGuitar's export
    does and what the flag's name has always claimed.

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


def format_tab_staff(
    steps: List[ArrangementStep],
    beats_per_bar: int = 4,
    beat_type: int = 4,
    rhythm: bool = True,
    show_chords: bool = False,
    show_melody: bool = False,
    show_melody_string: bool = True,
    show_mutes: bool = False,
    collapse: bool = True,
    measures_per_line: int = 4,
    show_timing: bool = False,
) -> str:
    """
    Renders a whole progression as a standard six-line guitar staff.

    format_progression() gives one line, or one six-line block, *per chord*. This
    instead lays every step along a single staff in reading order - high E on top
    down to low E - which is how printed tab is read, with a barline closing every
    measure.

    **The default output is the tab and nothing else**: six string rows, the fret
    numbers sitting in a drawn line of dashes, and the barlines. No chord names, no
    melody note names, no metre and no note values. That is what a tab file *is*, and
    it is what TuxGuitar's, Guitar Pro's and every other ASCII export produce - a
    thing you drop into a file and read, not a score with annotation. The chord row
    was on by default until this was changed, and it was the wrong default: a reader
    who wants the harmony can read it off the arrangement, and one who wants it on
    the page asked for it. Pass `show_chords` for it.

    Fret cells are a fixed width and the number sits at the left of its column,
    which is how tab is written and what keeps a chord name aligned with the fret
    it belongs to. The width is at least two characters, so a two-digit fret never
    runs into its neighbour. An unsounded string is left blank by default:
    in chord-melody a voice that is still ringing is not restruck, and marking
    it `x` on every chord would be noise. Pass `show_mutes` to spell them out. A
    melody-only (no chord) step always shows its `x`s, because there the other
    strings really are silent.

    `show_timing` adds two rows above the chord names: the **metre** (`4/4`) over the
    first bar, and a **rhythm** row naming the note value in every column - `w` for
    a whole note, `~` for a shape still held from an earlier column, `r` for a rest.
    With them the grid shows not only *where* a chord falls but *how long it sounds*,
    since a whole note and a quarter are drawn identically without them. They are
    **off by default** now, for the same reason the chord row is: they are a score's
    annotation, not the tab. `beat_type` is what the metre needs when they are on: a
    2/2 beat is a half note, so 2/2 reads `h` where 4/4 reads `q` on the same grid.

    Args:
        steps: arranged steps, typically from arrange_progression().
        beats_per_bar: beats in a bar, used to place the barlines.
        beat_type: the denominator of that metre. Pass the notated value, so a head
            in cut time reads `2/2` rather than being restated as `2/4`, and its
            beat is a half note rather than a quarter. The bar length is identical
            either way; only the displayed metre and the note values differ.
        rhythm: space the steps on their real beats. This needs every step to
            carry `bar` and `beat`; if any does not, the uniform grid is used, so
            a hand-written progression still renders sensibly.
        show_chords: draw the chord-name line above the staff. Off by default: the tab
            is the six string rows, and a chord name is a lead sheet's annotation.
        show_melody: draw the melody-note line. Off by default, as above.
        show_melody_string: mark the string carrying the melody with a `*`.
        show_mutes: print `x` on every unsounded string.
        collapse: strike a shape once and let it ring while the melody moves over the
            same pitches, instead of restriking it on every step. This is the
            default, and it is what makes a held chord read as a held chord.
        measures_per_line: bars per printed line of music; the staff wraps there and
            the last line may be shorter. Every bar is ruled regardless - this
            governs only where a line *ends*, not where the barlines fall.
        show_timing: draw the metre and the note-value rows above the chord names.
            Off by default along with them: they say how long each chord sounds,
            which a score needs and a tab file does not carry. Pass `True` for a
            staff that reads as a score rather than as tab.

    Returns:
        The rendered staff as a newline-joined string, or "" for no steps. Pure:
        nothing is printed, so the caller stays in control of the output.

    Raises:
        ValueError: if `beats_per_bar` or `beat_type` is below 1, or
            `measures_per_line` is below 1.
    """
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if beat_type < 1:
        raise ValueError(f"beat_type must be at least 1, got {beat_type!r}")
    if measures_per_line < 1:
        raise ValueError(f"measures_per_line must be at least 1, got {measures_per_line!r}")
    if not steps:
        return ""

    columns = _staff_columns(steps, beats_per_bar, beat_type, rhythm, collapse)
    bars = _staff_bars(columns, beats_per_bar)
    # Two different sets, deliberately: `bar_marks` is every bar (where the metre
    # falls) and `breaks` is every `measures_per_line` bars (where the line wraps).
    bar_marks = _staff_barlines(bars)
    breaks = _staff_breaks(columns, beats_per_bar, measures_per_line)
    # The rhythm row and the column grid go through one predicate, so the row can
    # never claim a written rhythm the columns were not laid out by.
    timed = _is_timed(steps, rhythm)
    values = _staff_rhythm(columns, beats_per_bar, beat_type, timed)
    # How wide each column is drawn, so a note's duration shows as horizontal space.
    # **Only for a timed progression**: an untimed one is laid out one chord per beat
    # and has no durations to show, so every column stays one slot wide and the output
    # is the plain uniform grid it has always been.
    slots = (
        _slot_counts(
            columns, beats_per_bar, beat_type, _slots_per_whole(steps)
        )
        if timed else [1] * len(columns)
    )

    def cell(step: Optional[ArrangementStep], string_index: int, strikes: bool) -> str:
        """One fret cell: a fret number or a mute marker, or empty for a held voice."""
        if step is None or not strikes:
            return ""
        if not _strikes_here(step, string_index):
            return ""
        fret = step.voicing.frets[string_index]
        if fret < 0:
            return _MUTED_CELL if (show_mutes or step.melody_only) else ""
        return str(fret)

    def system_width(system: List[int]) -> int:
        """
        The cell width for one system: the widest label among **its own** columns.

        Every row of a system shares one column width, and the grid widens to the
        longest label rather than letting the chord line push itself out of step with
        the frets underneath it. The metre and the note values go through the same
        calculation: a `4/4` or a `0.67q` fallback is wider than a fret, and
        truncating either would print a note value that is not the one being played.

        **Only labels that are actually drawn count.** The chord name is measured
        under `show_chords` and the melody note under `show_melody`, because a label
        that is not printed cannot knock the grid out of alignment - and counting it
        anyway meant that turning the rows off left the tab *wider* than leaving them
        on, which is the opposite of what the flag says.

        **Per system, not per progression.** It used to be computed once over every
        column, which meant a single two-digit fret anywhere in the piece set the
        width for the whole arrangement: a bar of nothing but single-digit frets was
        drawn two characters per cell because some other bar held a `13`. TuxGuitar's
        export does not do that - its bars are sized independently (measured across
        `jon6.tab`: 7, 14, 17 and 19 characters). Per system is the finest granularity
        that keeps the invariant the alignment tests exist to protect, since two bars
        drawn on one system have to share a grid or a fret stops lining up across the
        six strings. Per *bar* would match the export more closely and would break it.
        """
        width = _STAFF_CELL_WIDTH
        for index in system:
            step = columns[index][1]
            if step is None:
                continue
            if show_chords:
                width = max(width, len(step.chord))
            if show_melody:
                width = max(width, len(step.melody or ""))
        if show_timing:
            width = max(width, len(_meter_label(beats_per_bar, beat_type)))
            for label, _kind in values:
                if label:
                    width = max(width, len(label))
        return width

    def _meter_cells(count: int) -> List[str]:
        """The metre in the first column and nothing elsewhere.

        A time signature is written once, at the head of the staff, and the
        signature holds until it changes - so printing it over every bar would say
        something the score does not. That is the same decision `tabxml` makes when
        it writes `<time>` in the first measure only, and for the same reason: a
        signature over every bar reads as a new one at each, and the bar stops
        reading as a continuation of the one before.
        """
        return [_meter_label(beats_per_bar, beat_type)] + [""] * (count - 1)

    def line(width: int, system: List[int], text_for: Any, when_struck: bool,
             dedupe: bool = False, cells: Optional[Sequence[str]] = None,
             in_force: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Renders a chord, melody, metre or rhythm row for one system of music.

        `width` is `system_width(system)` and is passed rather than recomputed, because
        it is a property of the system and every row of that system must use the same
        one - see `system_width` for why it is per system.

        `system` is the list of column indexes this printed line covers, so every row
        is drawn over the same columns as the six string rows beneath it. It has to
        be passed rather than taken from `columns`, because a staff that wraps draws
        each system separately - and a row built from the whole column list would run
        the full width of the progression while the strings beneath it ran the width
        of one line, which is the misalignment the alignment tests exist to catch.

        `when_struck` is False for the melody line, which must label every step:
        the melody moves on even while the shape underneath it is being held.
        `dedupe` prints a label only where it changes from the previous one, which
        is how a lead sheet spells a chord held across several slots. The chord in
        force is threaded in and out so a chord held across a *system break* is
        named once - the same rule the HTML page follows, for the same reason.

        `cells` supplies the text **by column index** instead of from the step, and
        that is what the metre and rhythm rows need: a held column has a step but no
        note of its own, and a rest column has neither a step nor anything to
        derive a value from. Routing both through this one function is what keeps
        the new rows ruled identically to the string rows - the alignment
        `TestStaffBarlineAlignment` asserts, which would otherwise only hold for the
        two rows that existed when it was written.

        **These rows are not dash-filled.** A `-` between columns is the string's
        *own* line, running through the fret numbers; a chord name or a note value is
        text sitting above the staff, and ruling it would draw a line through the
        words. So the separator is a space here and a dash on the string rows - and
        both are exactly one character, which is what keeps the columns of the two
        kinds of row aligned.
        """
        # Two spaces then a barline, which is the same three-character offset the
        # string lines use (string label, melody marker, '|'), so a chord name
        # starts in the column of its own frets and every row is ruled identically.
        # The closing barline matters as much as the leading one: without it these
        # rows stop short of the string rows and the staff reads as unaligned.
        out = ["  |"]
        previous = in_force
        # **One separator after every barline, including this row's own opening one.**
        # TuxGuitar writes a dash between the barline and the first fret of the bar and
        # never a fret hard against the `|` - measured over `jon6.tab`, the shortest
        # lead-in in the file is one dash, and all 26 of its bars have one. It is a
        # small thing that stops a beat-1 fret reading as glued to the barline it
        # follows. Here it is a space, because these rows are text and unruled; the
        # string rows put a `-` in the same column, and both being exactly one
        # character wide is what keeps the two kinds of row aligned.
        #
        # It is written unconditionally because the row's own opening barline needs it
        # as much as any other, and the loop below already suppresses the *barline*
        # itself for position 0 - so without this, the first column of every system
        # would sit hard against the `|` while every later column had a separator.
        out.append(" ")
        for position, index in enumerate(system):
            # `position`, not `index`: the row has just written its own opening
            # barline, so the first column of a system must not write a second.
            # Every system begins on a barline, so this is not a rare case - without
            # it every line after the first opened with a doubled `||`.
            if index in bar_marks and position:
                # The barline's own lead-in, for the reason given in `string_line`:
                # every barline is followed by a separator, not only the opening one.
                out.append("| ")
            if cells is not None:
                text = cells[index] if index < len(cells) else ""
            else:
                _, step, strikes = columns[index]
                text = text_for(step) if (strikes or not when_struck) else ""
            if dedupe and text and text == previous:
                text = ""
            if text:
                previous = text
            # **The cell spans its own slots, and there is no separate separator.**
            # One slot is one fret cell wide, so a note two slots long is drawn two
            # cells wide and the whole line is the same width whatever it contains.
            # That is what puts our bars where TuxGuitar's are: seventeen characters
            # for a bar of a quarter rest and three quarter notes.
            out.append(text.ljust(width * slots[index]))
        # No rstrip here. The chord and melody rows share their column grid with the
        # string rows, so a trailing blank column has to stay blank rather than be
        # trimmed: trimming shortens the row and leaves its closing barline short of
        # the string rows'. The closing '|' is what makes the trailing spaces read as
        # an empty bar rather than as ragged text.
        return "".join(out) + "|", previous

    def string_line(width: int, system: List[int], string_index: int) -> str:
        out = ["*", "|"] if show_melody_string and _carries_melody(steps, string_index) else [" ", "|"]
        # The lead-in dash, for the reason given in `line`. On a string row it is a
        # real dash rather than the space used there, because here the character is
        # part of the string's own drawn line.
        out.append("-")
        for position, index in enumerate(system):
            # The `position` guard for the reason given in `line`: this row has
            # already written its own opening barline.
            if index in bar_marks and position:
                # A barline inside the line is followed by its own lead-in, exactly as
                # the opening one is. Without it the first fret of the second bar sat
                # hard against the `|`, where TuxGuitar - and the opening bar, and
                # every other bar - all have a dash between the two.
                out.append("|-")
            # **The fill is a dash, not a space** - and this is the whole reason the
            # staff reads as tab rather than as a chord list. A string is one
            # continuous line running the length of the system, with the fret numbers
            # sitting *in* it. Left blank, the six lines were six scattered numbers
            # and the reader had to infer the strings from the labels alone.
            #
            # The cell spans **its own slots**, for the reason given in `line`: one
            # slot is one fret cell, so a note two slots long is drawn two cells wide
            # and the dashes after the fret are the note sounding on.
            _, step, strikes = columns[index]
            out.append(
                cell(step, string_index, strikes).ljust(width * slots[index], "-")
            )
        out.append("|")
        # The highest string is labelled with a lowercase 'e', the usual tab
        # convention, so the top and bottom lines of the staff stay distinct.
        name = "e" if string_index == 5 else STRING_NAMES[string_index]
        return f"{name}{''.join(out)}"

    lines: List[str] = []
    # The chord in force, threaded across systems so a chord held over a system
    # break is named once - the rule `_html_chord_row` already follows for the page.
    in_force: Optional[str] = None
    labels = [label for label, _kind in values]
    for position, system in enumerate(_staff_lines(columns, breaks, beats_per_bar)):
        if position:
            # A blank line between systems. Without it two systems run together and
            # the reader cannot tell where one printed line ends and the next begins,
            # which is the only cue the wrapping itself provides.
            lines.append("")
        # One width for every row of this system. See `system_width` - per system,
        # because two bars drawn on one line have to share a grid or a fret stops
        # lining up across the six strings.
        width = system_width(system)
        if show_timing:
            # The metre goes in the first column of the *first* system, over the bar it
            # governs, which is where a printed score puts a time signature - and not
            # again on the next system, because a signature holds until it changes.
            lines.append(line(
                width, system, lambda step: "", when_struck=True,
                # The cells are addressed by global column index, so the metre row is
                # blank on every column but the very first of the first system.
                cells=(
                    _meter_cells(len(system)) if position == 0
                    else [""] * len(system)
                ),
            )[0])
            # The rhythm row is dropped when there is no rhythm to state. An untimed
            # progression is one chord per beat, so every cell would be the same letter
            # and the row would be a blank line that looks like a missing one.
            if values:
                lines.append(line(
                    width, system, lambda step: "", when_struck=True, cells=labels,
                )[0])
        if show_chords:
            row, in_force = line(
                width, system, lambda step: step.chord if step else "",
                when_struck=True, dedupe=True, in_force=in_force,
            )
            lines.append(row)
        if show_melody:
            lines.append(line(
                width, system, lambda step: (step.melody or "") if step else "",
                when_struck=False,
            )[0])
        lines.extend(string_line(width, system, index) for index in range(5, -1, -1))
    return "\n".join(lines).rstrip()


# --- HTML tab ---
#
# format_tab_staff above is ASCII, because that is what goes in a terminal. A browser
# can do better: a table gives every column its own box, so fret numbers, chord names
# and barlines align by construction rather than by counting characters, and the
# page can be styled, reflowed and printed. The output is one self-contained file -
# the stylesheet is inlined - so it can be emailed or opened from disk.
#
# Everything here reuses _staff_columns and _staff_breaks, so the two renderings
# place a chord in the same column by construction and cannot drift.

# Cell classes used by both the stylesheet and the row builder below. They are
# named here rather than spelled inline so a rename cannot half-apply.
_CLASS_SYSTEM = "system"
_CLASS_MEASURE = "measure"
_CLASS_STRING = "string"
_CLASS_CHORD = "chord"
_CLASS_MELODY = "melody"
_CLASS_MUTE = "mute"
_CLASS_SOPRANO = "soprano"
_CLASS_BARNUM = "barnum"
# Marks every cell of a repeated-melody column. Those cells are otherwise empty, so
# without this a repeated note reads as a gap in the music rather than as a deliberate
# single note.
_CLASS_REPEAT = "repeat"
# Marks every cell of a `bass_only` column, for the same reason `_CLASS_REPEAT`
# exists and it is the mirror image of it: those cells are empty too, and a thumb
# note with a blank column above it has to read as a deliberate held shape rather
# than as silence under a moving bass.
_CLASS_BASS = "bass"
# The written metre, and the note value of every column. Both sit above the chord
# row, where a score puts them, and both are the ASCII staff's `show_timing` rows -
# named here for the same reason as the rest, so a rename cannot half-apply.
_CLASS_METER = "meter"
_CLASS_RHYTHM = "rhythm"
_CLASS_HOLD = "hold"
_CLASS_REST = "rest"

_HTML_STYLESHEET = """
:root { color-scheme: light dark; --ink: #1b1b1b; --rule: #b8b8b8;
        --fret: #1b1b1b; --accent: #7a2f2f; --mute: #a9a9a9;
        --strike: #f2ede2; --page: #fdfdfb; --faint: #8a8a8a; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #e8e6e1; --rule: #4a4a4a; --fret: #f2efe9; --accent: #e0a3a3;
          --mute: #6f6f6f; --strike: #2b2b2b; --page: #16181c; --faint: #8f8f8f; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 2.5rem 1.5rem 4rem; background: var(--page);
       color: var(--ink);
       font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 68rem; margin: 0 auto; }
h1 { font-size: 1.5rem; font-weight: 650; margin: 0 0 .25rem; letter-spacing: -.01em; }
p.sub { margin: 0 0 .35rem; color: var(--faint); font-size: .9rem; }
p.meta { margin: 0 0 2rem; font-size: .8rem; color: var(--faint); }
.systems { display: flex; flex-direction: column; gap: 1.6rem; }
.system { display: flex; align-items: stretch; overflow-x: auto; }
.measure { border-left: 1px solid var(--rule); padding: 0 .5rem; }
.measure:first-of-type { border-left: 2px solid var(--rule); }
.barnum { font-variant-numeric: tabular-nums; font-size: .7rem; color: var(--faint);
          align-self: flex-start; padding-top: .1rem; min-width: 1.6rem;
          text-align: right; }
table { border-collapse: collapse;
        font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
th, td { padding: .05rem .28rem; text-align: left; white-space: nowrap; }
/* Chord names share a column with the frets beneath them, so a name wider than a
   fret widens the column instead of shifting the staff out of alignment. */
tr.chord td { font-family: ui-sans-serif, system-ui, sans-serif; font-weight: 600;
              color: var(--accent); font-size: .82rem; padding-bottom: .15rem; }
tr.melody td { font-size: .72rem; color: var(--faint); padding-bottom: .3rem; }
/* The metre and the note values, which are the two rows the ASCII staff draws from
   `show_timing`. They are small and quiet because they are read once and then the
   eye goes to the chords; the metre is a touch stronger since it is the one piece
   of information a reader cannot infer from the tab. */
tr.meter td { font-size: .78rem; font-weight: 600; color: var(--ink);
              padding-bottom: .1rem; }
tr.rhythm td { font-size: .68rem; color: var(--faint); padding-bottom: .25rem;
               font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
/* A tie and a rest both sit in a column with no new attack, and they mean opposite
   things: `~` is the note begun earlier still sounding, `r` is silence. They are
   dimmed rather than blanked so neither reads as a missing cell. */
td.hold, td.rest { color: var(--mute); }
tr.string th { font-weight: 500; font-size: .72rem; color: var(--faint); width: 1ch;
               padding-right: .5rem; }
tr.string th.soprano { color: var(--accent); }
tr.string td { font-size: .9rem; color: var(--fret);
               font-variant-numeric: tabular-nums; min-width: 1.1ch; }
/* A struck chord is tinted; a held one is left plain, because the shape is still
   ringing from the attack before it. */
td.strike { background: var(--strike); border-radius: 2px; }
td.mute { color: var(--mute); }
/* A repeated melody is played as a single note: the other strings are left empty and
   the column is tinted, so it reads as a deliberate single note rather than as a gap
   in the music. */
td.repeat { background: var(--strike); border-radius: 2px; }
/* The mirror image of td.repeat: a bass-only column holds every voice above the thumb
   and moves only the thumb, so its empty cells are tinted for the same reason. */
td.bass { background: var(--strike); border-radius: 2px; }
.notes { margin: 2.5rem 0 0; font-size: .78rem; color: var(--faint); }
.notes li { margin: .2rem 0; }
@media print { body { padding: 0; } .system { overflow: visible; } }
"""


def _escape(text: str) -> str:
    """HTML-escapes a value taken from the arrangement.

    Chord names and note names can come from the corpus database, so they are
    treated as untrusted text rather than assumed safe to interpolate.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _html_timing_rows(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
    values: Sequence[Tuple[str, str]],
    meter: str,
    show_meter: bool,
) -> List[str]:
    """
    The metre and note-value rows for one measure, in that order.

    **The metre appears on the first measure only.** A time signature holds until
    it changes, so writing one over every bar says something the score does not -
    and the same reasoning is why `tabxml` writes `<time>` into the first measure
    alone, since MuseScore draws a repeated signature over every bar and the bar
    stops reading as a continuation of the one before. `show_meter` is the page's
    "is this the first measure" flag.

    The note-value row repeats on every measure, because a rhythm is per-measure
    and a bar of rests is not the same information twice. It is omitted entirely
    when `values` is empty - an untimed progression has no written rhythm to show,
    and an empty row would read as a rendering failure rather than as an absence.

    The cells come from the shared `_staff_rhythm`, which the ASCII staff also
    reads, so the page and the terminal cannot disagree about how long a note is.
    """
    rows: List[str] = []
    if show_meter:
        meter_cells = [_html_cell(tag="th")]
        meter_cells += [
            _html_cell(_escape(meter) if position == 0 else "")
            for position in range(len(measure))
        ]
        rows.append(_html_row(_CLASS_METER, meter_cells))
    if values:
        cells = [_html_cell(tag="th")]
        for index in measure:
            label, kind = values[index] if index < len(values) else ("", "note")
            css = _CLASS_HOLD if kind == "hold" else _CLASS_REST if kind == "rest" else ""
            cells.append(_html_cell(_escape(label), css))
        rows.append(_html_row(_CLASS_RHYTHM, cells))
    return rows


def _html_cell(text: str = "", class_name: str = "", tag: str = "td") -> str:
    """
    One table cell, with its class attribute only when there is a class to give it.

    An empty `class_name` omits the attribute entirely, so a plain cell stays
    `<td>3</td>` rather than becoming `<td class="">3</td>`. The row builders below
    use this instead of assembling tags inline, which is what made the repeat
    marking a nested conditional: deciding the class and emitting the cell are the
    same decision, so they belong in one call.

    `tag` is "th" only for the leading label cell, which has to be a header for
    the string rows to line their labels up and to keep the chord and melody rows
    in the same columns as the frets beneath them.
    """
    attribute = f' class="{class_name}"' if class_name else ""
    return f"<{tag}{attribute}>{text}</{tag}>"


def _html_row(class_name: str, cells: Sequence[str]) -> str:
    """One table row, from cells that are already built by `_html_cell`."""
    return f'<tr class="{class_name}">{"".join(cells)}</tr>'


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


def _html_chord_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
    previous: Optional[str],
) -> Tuple[str, Optional[str]]:
    """
    One row of chord names, plus the chord now in force for the next measure.

    A name is printed only where it changes from the one in force, and only on a
    struck chord, which is how a lead sheet spells a chord held across several
    slots. The running `previous` is threaded through the whole page rather than
    kept in module state or reset per measure, so a chord spanning a barline is
    named once, and two calls in a row cannot see each other's chords.
    """
    # The leading empty <th> matches the string rows' label cell. Without it the
    # whole row would sit one column left of the frets it belongs to, because a
    # table column is shared by every row above and below it.
    cells: List[str] = [_html_cell(tag="th")]
    for index in measure:
        _, step, strikes = columns[index]
        # A name is printed only where the chord changes and only on a strike; every
        # other column is left empty so a held chord is not spelled out again.
        if step is None or not strikes or step.chord == previous:
            cells.append(_html_cell())
            continue
        cells.append(_html_cell(_escape(step.chord)))
        previous = step.chord
    return _html_row(_CLASS_CHORD, cells), previous


def _html_melody_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
) -> str:
    """
    One row of melody note names.

    Labelled on every step, not only on a strike: the melody moves on even while
    the shape underneath it is being held, so the held columns are exactly where a
    note name is most useful.
    """
    cells = [_html_cell(tag="th")]
    for index in measure:
        # An empty cell is one with no step on it; pyright cannot see that the
        # conditional already guards it, so the binding is named explicitly.
        step = columns[index][1]
        cells.append(_html_cell(_escape(step.melody or "") if step else ""))
    return _html_row(_CLASS_MELODY, cells)


def _html_string_row(
    columns: List[Tuple[float, Optional[ArrangementStep], bool]],
    measure: List[int],
    string_index: int,
    sopranos: set,
    show_mutes: bool,
) -> str:
    """
    One row of fret numbers for a measure, on the string given.

    A ringing voice is not restruck, so a muted string is left as an empty cell
    rather than marked x on every chord - that would be noise. `show_mutes` spells
    them out, and a melody-only step always shows its x, because there the other
    strings really are silent.
    """
    is_soprano = string_index in sopranos
    cells = [
        _html_cell(
            "*" if is_soprano else "", _CLASS_SOPRANO if is_soprano else "",
            tag="th",
        )
    ]
    for index in measure:
        _, step, strikes = columns[index]
        if step is None or not strikes:
            cells.append(_html_cell())
            continue
        # A `repeated` or `bass_only` column sounds only some of its strings, and the
        # rest stay empty. The whole column is tinted by that single class either way,
        # which is what keeps such a column visible as deliberate rather than as a gap
        # in the music. Which strings sound is `_strikes_here`'s decision - the same
        # one the ASCII cell makes - so the two renderings cannot disagree.
        partial_column = step.repeated or step.bass_only
        column_class = _CLASS_REPEAT if step.repeated else _CLASS_BASS
        if partial_column and not _strikes_here(step, string_index):
            cells.append(_html_cell(class_name=column_class))
            continue
        fret = step.voicing.frets[string_index]
        if fret < 0:
            cells.append(
                _html_cell("x", _CLASS_MUTE)
                if (show_mutes or step.melody_only)
                else _html_cell(column_class if partial_column else "")
            )
        else:
            cells.append(_html_cell(str(fret), column_class if partial_column else ""))
    return _html_row(_CLASS_STRING, cells)


def format_tab_html(
    steps: List[ArrangementStep],
    title: str = "Chord-melody arrangement",
    subtitle: str = "",
    beats_per_bar: int = 4,
    beat_type: int = 4,
    rhythm: bool = True,
    show_melody: bool = True,
    show_mutes: bool = False,
    collapse: bool = True,
    measures_per_line: int = 4,
    notes: Optional[Sequence[str]] = None,
    show_timing: bool = True,
) -> str:
    """
    Renders a whole progression as a self-contained HTML tab page.

    The same layout the ASCII staff draws, in a form a browser can present well:
    every column is a table cell, so chord names, fret numbers and barlines stay
    aligned by the table rather than by counting characters, and the page carries
    its own stylesheet (including a dark-mode one), so it needs no network access
    and no sibling files.

    `show_timing` adds the two rows the score renderers both carry and this page
    used to omit: the **metre** over the first measure, and a **note value** per
    column. They are the same rows `format_tab_staff` draws and come from the same
    `_staff_rhythm`, so the page and the terminal cannot disagree about the rhythm.

    Args:
        steps: arranged steps, typically from arrange_progression().
        title: the page heading, and the browser window title.
        subtitle: an optional line under the heading, e.g. the performer.
        beats_per_bar: beats in a bar, used to place the barlines.
        beat_type: the denominator of that metre. Pass the notated value, so a head
            in cut time reads `2/2` rather than being restated as `2/4`, and its
            beat is a half note rather than a quarter.
        rhythm: space the chords on their real beats. Falls back to a uniform grid
            when the steps carry no timing, exactly as format_tab_staff does.
        show_melody: draw the melody-note line.
        show_mutes: spell out the unsounded strings as a dimmed x. A melody-only
            step always shows its x, since there the strings really are silent.
        collapse: strike each shape once and let it ring, rather than restriking
            an unchanged shape on every step.
        measures_per_line: bars per system of music.
        notes: optional lines of provenance, e.g. the register lift decision.
        show_timing: draw the metre and the note-value rows. On by default; `False`
            restores the page this renderer produced before them.

    Returns:
        A complete HTML document as a string, or "" for no steps. Pure: nothing is
        printed and no file is written, so the caller stays in control.

    Raises:
        ValueError: if `beats_per_bar` or `beat_type` is below 1, or
            `measures_per_line` is below 1.
    """
    if beats_per_bar < 1:
        raise ValueError(f"beats_per_bar must be at least 1, got {beats_per_bar!r}")
    if beat_type < 1:
        raise ValueError(f"beat_type must be at least 1, got {beat_type!r}")
    if measures_per_line < 1:
        raise ValueError(f"measures_per_line must be at least 1, got {measures_per_line!r}")
    if not steps:
        return ""

    columns = _staff_columns(steps, beats_per_bar, beat_type, rhythm, collapse)
    breaks = _staff_breaks(columns, beats_per_bar, measures_per_line)
    # The same predicate and the same rhythm the ASCII staff reads, so the page and
    # the terminal cannot disagree about how long a note is.
    values = _staff_rhythm(
        columns, beats_per_bar, beat_type, _is_timed(steps, rhythm)
    )
    meter = _meter_label(beats_per_bar, beat_type)
    # Which strings carry the melody somewhere in the progression, so those rows
    # can be marked once for the whole page rather than per chord.
    sopranos = {index for index in range(6) if _carries_melody(steps, index)}

    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(title)}</title>",
        f"<style>{_HTML_STYLESHEET}</style>",
        "</head>",
        "<body><main>",
        f"<h1>{_escape(title)}</h1>",
    ]
    if subtitle:
        parts.append(f'<p class="sub">{_escape(subtitle)}</p>')
    parts.append(
        f'<p class="meta">{len(steps)} step{"" if len(steps) == 1 else "s"}'
        f'{" · " + _escape(meter) if show_timing else ""}</p>'
    )
    parts.append('<div class="systems">')

    start_bar = int(columns[0][0] // beats_per_bar)
    # The chord in force, carried across systems so a chord held over a system
    # break is not named a second time.
    in_force: Optional[str] = None
    # Only the first measure of the page carries the metre; a signature holds until
    # it changes. See `_html_timing_rows`.
    first_measure = True

    def bar_of(index: int) -> int:
        return int(columns[index][0] // beats_per_bar) - start_bar

    for line in _staff_lines(columns, breaks, beats_per_bar):
        parts.append(f'<div class="{_CLASS_SYSTEM}">')
        parts.append(f'<span class="{_CLASS_BARNUM}">{bar_of(line[0]) + 1}</span>')
        # Split the system into measures at each bar change, so every measure gets
        # its own ruled box. The last measure of a system may be short.
        measures: List[List[int]] = []
        for index in line:
            if measures and bar_of(measures[-1][0]) == bar_of(index):
                measures[-1].append(index)
            else:
                measures.append([index])
        for measure in measures:
            parts.append(f'<div class="{_CLASS_MEASURE}"><table>')
            if show_timing:
                parts.extend(
                    _html_timing_rows(columns, measure, values, meter, first_measure)
                )
                first_measure = False
            chord_row, in_force = _html_chord_row(columns, measure, in_force)
            parts.append(chord_row)
            if show_melody:
                parts.append(_html_melody_row(columns, measure))
            for string_index in range(5, -1, -1):
                parts.append(
                    _html_string_row(
                        columns, measure, string_index, sopranos, show_mutes
                    )
                )
            parts.append("</table></div>")
        parts.append("</div>")

    parts.append("</div>")

    if notes:
        items = "".join(f"<li>{_escape(note)}</li>" for note in notes)
        parts.append(f'<ul class="notes">{items}</ul>')

    parts.append("</main></body></html>")
    return "\n".join(parts)


def write_tab_html(steps: List[ArrangementStep], path: str, **kwargs: Any) -> str:
    """
    Renders `format_tab_html` to a file and returns the path written.

    The one function in this module that touches the filesystem, which is what
    lets every renderer stay pure. Writing is separated from rendering so a caller
    who only wants the string never creates a file by accident.
    """
    html = format_tab_html(steps, **kwargs)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return str(path)


# The seven names a star-import of this module must carry. Spelled out as one
# literal rather than `+=`, which a static checker cannot follow.
__all__ = [
    "format_tab_staff",
    "format_tab_html",
    "write_tab_html",
    "format_musicxml",
    "write_musicxml",
    "format_gp5",
    "write_gp5",
]

