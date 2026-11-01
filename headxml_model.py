from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from arranger.chords import midi_to_note_name

# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class HeadNote:
    """One melody note read from a score, with the chord in force under it.

    `bar` is the measure number as written and `beat` the beat *within* it, in the
    notated beats - so a 2/2 bar is two beats wide rather than four, its quarter note
    on beat 1.5 and its fourth on 2.5, and the two halves of a cut-time bar are not
    mistaken for two bars. A beat is `4 / beat_type` quarters, which is the one factor
    `_beat_from_onset` converts an onset with. `duration` is in whole notes, the unit
    every renderer in this library takes.

    `chord` is the symbol in force, `quality` the library spelling of it (None when
    the symbol was untranslatable, which is counted in `Head.unmapped`) and `bass`
    a slash bass kept for the voicing preference.
    """

    bar: int
    beat: float
    pitch: int
    duration: float
    # The measure number **as written on the score**. It equals `bar` for a head with
    # no repeat; when a repeat renumbers `bar` to a unique play-order position (a
    # repeated bar is played twice, so two physical bars would otherwise share the
    # written number), this keeps the score's own numbering recoverable. The default
    # `-1` is a hand-built note, which has no score behind it. See `BarMarker` and
    # `expand_repeats`.
    written_bar: int = -1
    # True when the note came from a `<time-modification>`, i.e. it is part of a
    # tuplet. Carried **explicitly** rather than inferred from `duration`, because
    # the inference is wrong: a plain eighth is half a grid step under `eighths`, so
    # "is the duration a whole number of steps" is true for tuplets *and* for every
    # ordinary eighth, and the check silently re-spaced the whole head. Only the
    # file knows which notes were written as a tuplet.
    tuplet: bool = False
    chord: str = ""
    quality: Optional[str] = None
    bass: Optional[str] = None
    lyrics: Tuple[str, ...] = ()

    @property
    def key(self) -> Tuple[int, float]:
        """The `(bar, beat)` this note begins at.

        **The same rounding as `HeadChange.key`, and it must match.** The two timelines
        are compared against each other — `chord_at` against a note's position, and
        `melody_at` against a grid position — so a beat that differs only in the seventh
        decimal has to be the same position to both. Two floats from two different
        expressions are the same beat; two spellings of one key are not.
        """
        return (self.bar, round(self.beat, 6))

    @property
    def note_name(self) -> str:
        """The pitch as a note name, spelled with flats as the library prints."""
        return midi_to_note_name(self.pitch)


@dataclass
class HeadChange:
    """One `<harmony>` element: a chord **becoming** in force at a position.

    **`HeadNote.chord` and this are the same fact read two ways**, and the difference
    is the whole of open-issues item 1. A note carries the chord that was in force
    *where the note is*; this carries the chord that *begins* at a position, whether or
    not any note is ever written there.

    A `<harmony>` followed by no note is not a synthetic edge case: 6 of the 154
    `<harmony>` elements across the committed scores precede no note, and one of those
    bars carries **no notes at all**. Such a change is in force for the rest of the bar
    and **no note ever records it**, which is the loss `docs/history/open-issues.md` item 1
    measures and this field exists to make representable.

    `beat` is the beat **within the bar**, as everywhere else in this module, and
    `quality is None` is never recorded — an untranslatable chord is counted in
    `Head.unmapped` and not guessed, exactly as on the note path.
    """

    bar: int
    beat: float
    chord: str
    quality: Optional[str] = None
    bass: Optional[str] = None
    # The written measure number, exactly as on `HeadNote.written_bar`: equal to `bar`
    # for a head with no repeat, and the score's own number when a repeat renumbered
    # `bar`. Defaults to -1 for a hand-built change.
    written_bar: int = -1

    @property
    def key(self) -> Tuple[int, float]:
        """The `(bar, beat)` this change takes effect at, for timeline lookups."""
        return (self.bar, round(self.beat, 6))


@dataclass(frozen=True)
class BarInstruction:
    """One bar-level play-order instruction, as the reader saw it.

    This is the **vocabulary** every reader of a written head shares: the MusicXML
    walk (`_parse_barline`, `_parse_direction`) and, through `expand_repeats`, any
    other importer that can state the same facts. It stays primitive on purpose:

    - `repeat_start` / `repeat_end` (with `times`) are a repeat's two ends;
    - `ending_start` / `ending_stop` (with `numbers`) bracket a volta;
    - `segno` / `coda` are **destinations**, named so a `to_coda` can pair with one;
    - `fine` and `to_coda` are the two places a jump may end;
    - `da_capo` / `da_segno` (naming its `segno`) are the jumps themselves.

    "D.C. al Fine" is therefore not an instruction: it is a `da_capo` whose return
    path passes a `fine`, and `_expand_play_order` is the only place that decides
    which of the six resolved forms it is.

    A frozen dataclass rather than a tuple: a raw marker has four fields, and a
    positional unpack is where a fifth would go unnoticed. `name` is empty except on a
    destination and the jump to one.
    """

    kind: str
    numbers: Tuple[int, ...] = ()
    times: int = 2
    name: str = ""


@dataclass
class BarMarker:
    """A repeat, ending or navigation instruction, on the **absolute** play-order bar
    the loader assigned.

    `kind` is `BarInstruction`'s vocabulary, plus the four **resolved** jump forms
    `da_capo_al_fine`, `da_capo_al_coda`, `da_segno_al_fine` and `da_segno_al_coda`.
    The resolution happens once, in `_expand_play_order`: a writer that had to decide
    for itself whether a D.C. ends at a Fine or a Coda would be a second source for a
    decision the play order already made.

    `numbers` is a volta's number set - "1", "2", or "1,2" for a bracket played on
    more than one pass - and `times` is a repeat's play count (2 unless the file says
    otherwise). `name` is the Segno or Coda a destination or jump is spelled with;
    it is empty elsewhere.

    These are what the writers draw as `|:` / `:|`, the `1.` / `2.` brackets and the
    D.C. / D.S. / Fine / Coda directions, and what `_expand_play_order` uses to build
    the sequence a performer actually plays.
    """

    bar: int
    kind: str
    written_bar: int
    numbers: Tuple[int, ...] = ()
    times: int = 2
    name: str = ""


@dataclass
class Head:
    """A loaded head: the melody, its timing, and everything the loader learned.

    `title`, `composer` and `part` identify the source for the CLI header, and
    `beats_per_bar` is the notated bar length in beats, so a cut-time head is
    rendered two beats to the bar rather than four. `first_bar_implicit` is the source's
    own statement that bar 1 is an anacrusis, which the arrangement must not fill.

    `key_fifths` / `key_mode` are the key signature, so a renderer can state the key
    the tune is in instead of falling back to the format's default of C major. See
    their comments for the encoding, and `_key_signature` for how it is read.

    The notes are the reason a chord can go missing without the user
    wondering why: `unmapped` lists the chord symbols this library cannot voice,
    `skipped` the notes that were not melodic, and `report` the prose for the
    terminal. `report` is a separate field from `notes` because `notes` is the
    melody itself.
    """

    notes: List[HeadNote] = field(default_factory=list)
    title: str = ""
    composer: str = ""
    part: str = ""
    beats_per_bar: int = 4
    # The notated value of one beat, as the denominator of the time signature: 4 for
    # 4/4, 2 for the cut time most standards are written in. Carried because
    # `beats_per_bar` alone cannot say which - a 2/2 and a 2/4 bar are both two
    # beats wide, and printing one as the other misstates the metre.
    beat_type: int = 4
    # The score's own statement of the **grouping** - which denominator units are
    # felt as one beat - in those units, and the channel that stated it: "text" (an
    # `N+N` direction), "beams" (the primary beaming), "metronome" (a pulse mark),
    # or "" when the file says nothing. Empty is "not stated", not "one per beat":
    # an unbeamed score and a hand-built `Head` both take `grouping.auto`, and the
    # engine resolves that from `beats_per_bar` and `beat_type`.
    #
    # A tuple rather than the string the engine takes, because this is the file's
    # fact and `ArrangeOptions` is the request. `_head_request` converts it.
    grouping: Tuple[int, ...] = ()
    grouping_source: str = ""
    # Tri-state for the first measure: `True` when the score marks it
    # `implicit="yes"` (or numbers it 0) - an anacrusis whose missing time is a
    # pickup and not comping space; `False` when the source states a whole bar
    # however short its music is; `None` when the score says nothing - the
    # renderers infer the pickup from the bar's own content.
    first_bar_implicit: Optional[bool] = None
    # True when the source closes bar 1 with a double barline - the notation's own
    # statement that an unmarked short first bar is an anacrusis rather than a whole
    # bar. `_parse_barline` discards bar styles for play-order purposes, so this is
    # recorded separately for `first_complete_bar`, which needs to know where the
    # form begins. Only bar 1 is checked: a double barline elsewhere is a section
    # change, not a pickup.
    first_bar_ends_with_double_barline: bool = False
    # The key signature as MusicXML states it: `key_fifths` counts sharps (positive)
    # or flats (negative), so -3 is Eb major or C minor, and `key_mode` is which -
    # "major", "minor", or "" where the score did not say. Kept as the format's own
    # numbers rather than as a tonic name, because that is what a renderer needs to
    # write a signature back, and it is the one spelling every convention agrees on.
    #
    # Carried at all because a head with no key is C major, not *unknown*: a score
    # that omits `<key>` states no accidentals, and that is a key this library can
    # arrange and export.
    key_fifths: int = 0
    key_mode: str = ""
    unmapped: Tuple[str, ...] = ()
    skipped: Tuple[str, ...] = ()
    report: Tuple[str, ...] = ()
    # Every `<harmony>` in the part, in document order, as a **chord timeline**
    # independent of the melody. Empty by default, so a `Head` built by hand or by a
    # test keeps working, and `head_skeleton` reads `notes` only — this is recorded
    # and nothing else yet consumes it.
    #
    # It exists because `notes` cannot say what is in force where no note is written,
    # and open-issues item 1 measures what that costs: on `synthetic_repeat_slash` bars
    # 8, 16, 24 and 32 vanish from the arrangement entirely, and on
    # `synthetic_triplets` bar 34. See `HeadChange`.
    chords: List[HeadChange] = field(default_factory=list)
    # The (first, last) measure numbers the loader walked, or `None` for a `Head`
    # built by hand. `bars` reads it, so the head's length is a fact about the
    # **file** rather than about the melody - §9.3 step A' of `docs/comping-styles.md`.
    #
    # It is carried because a chords-only lead sheet has no notes to measure and still
    # knows how long it is, and because a head whose changes outlast its last note must
    # not be cut short at the tune's end. `None` keeps a hand-built `Head`'s note span
    # working, since it has no file behind it to state a range.
    measure_range: Optional[Tuple[int, int]] = None
    # Every repeat and ending (volta) instruction the score's barlines carried, on the
    # absolute play-order bars. Empty by default, so a hand-built `Head` and a score
    # with no repeat are both unaffected. The writers draw these; `Head.bars` is the
    # expanded length, so a repeated head arranges every bar a player actually plays.
    markers: List[BarMarker] = field(default_factory=list)
    # Absolute play-order bar -> the measure number the score writes for it. Empty for
    # a head with no repeat, where the two are the same number. A renderer that draws the
    # repeat signs needs it to fold the played arrangement back onto the **written**
    # score: writing the played bars out *and* looping them with signs would make a
    # reader play the repeated section twice more. See `arranger.cli._as_written`.
    written_bars: Dict[int, int] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.notes)

    def __iter__(self):
        return iter(self.notes)

    @property
    def bars(self) -> Tuple[int, int]:
        """The (first, last + 1) measure range the head occupies.

        **A fact about the file, not about the melody** (§9.3 step A'). The loader
        records the measures it walked, so this is right for a head whose last chord
        outlasts its last note and for one with no notes at all - a chords-only lead
        sheet. Nothing to guess: an empty file still has its measure count.

        A `Head` built by hand carries no such range, so it falls back to the melody's
        span, which is what every fixture in the tests is.
        """
        if self.measure_range is not None:
            first, last = self.measure_range
            return (first, last + 1)
        if not self.notes:
            return (1, 1)
        return min(n.bar for n in self.notes), max(n.bar for n in self.notes) + 1

