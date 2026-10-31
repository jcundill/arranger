"""The MusicXML front end's argparse block and its output dispatch.

`add_common_arguments` writes the flags once rather than making each caller copy them, so
a flag cannot be added in one place and silently missed in another. The idea behind the
split is that **the duplication worth removing is the *argument*, not the *prose***: the
flags whose help is identical are written once here, and prose that genuinely differs is
kept and lives in one table. `HEAD_HELP` holds the prose for every flag whose wording
carries a musical decision, and `_CommonHelp` is one dataclass with one field per such
flag, so a flag added here has nowhere else to be forgotten - `tests/test_cli.py`
asserts every declared field reaches `add_argument` with its text.

**Laziness is deliberate and load-bearing.** `argparse` is imported only under
`TYPE_CHECKING` (the annotations are strings, so nothing at runtime needs it) and the
renderers are imported *inside* `render_and_write`. Importing `tabstaff` at module scope
would execute the package `__init__` through `arranger.tuning`, so the import stays in the
function body - which is also what leaves `headxml`'s `load_musicxml` cheap.

`tuning` is now a top-level module, so `tabstaff` imports it directly and no longer
reaches into `arranger` at module scope. The import stays function-local anyway, both to
avoid loading the optional-extras renderers on every `import arranger` and to keep
`headxml`'s `load_musicxml` cheap.

This module sits **last** in `tests/meta_package_dag.py`'s `ORDER`: it reads
`NECK_FRET_MIN`/`MAX` from `tuning`,
`NON_CHORD_TONE_STRATEGIES` from `chords`, `TEXTURE_STYLES` from `texture` and
`format_progression` from `render`, and is imported by nothing below it. It needs
no `ALLOWED_EDGES` entry, which is the test that a new module was placed by its
edges rather than appended.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .chords import NON_CHORD_TONE_STRATEGIES
from .grid import RHYTHM_NONE
from .options import (
    BASS_NOTES_ROOT,
    CHORD_FILLS,
    CHORD_FILLS_NONE,
    CHORD_NOTES,
    CHORD_NOTES_FULL,
)
from .render import format_progression
from .step_types import ArrangementStep
from .tuning import NECK_FRET_MAX, NECK_FRET_MIN

if TYPE_CHECKING:  # pragma: no cover - the annotations are strings at runtime
    import argparse

__all__ = [
    "HEAD_HELP",
    "_REQUEST_DESTS",
    "_CommonHelp",
    "ScoreMeta",
    "add_common_arguments",
    "render_and_write",
]


@dataclass(frozen=True)
class _CommonHelp:
    """The `--help` prose for the flags whose wording is not mechanical.

    One field per flag whose help is *written* rather than derived. A flag absent
    from this dataclass has its help written once in `add_common_arguments`, because
    the text is the same wherever it is read - `fallback`, `non_chord_tone`, `grid`
    and `bass` are those four.

    **A table rather than inline strings.** A flag's
    help text is the one place a flag's *meaning* is stated in prose, and it needs
    to be findable by reading one block rather than by grepping a function body.
    `arranger head --help` is the consumer, and the separation is kept
    because the alternative - help text interpolated into `add_argument` calls -
    scatters the explanation of a flag across the call that registers it.

    `Optional` rather than `str` because `fret_min` and `fret_max` were `None` in
    the `head` half of the pair for a while, and `argparse`'s own default for
    `help` is `None`. The type is kept so the distinction between "no help" and
    "empty help" stays expressible.
    """

    bars: str
    bars_per_line: str
    fret_min: Optional[str]
    fret_max: Optional[str]
    gp5: str
    html: str
    note_names: str
    musicxml: str
    mutes: str
    tab: str
    no_melody: str
    chord_on: str
    chord_notes: str
    chord_fills: str
    bass_on: str
    bass_notes: str


#: The six request questions, as `(the Request field, the flag's argparse dest)`.
#:
#: One list, because the six are one vocabulary spelled twice - by these flags and by
#: `Request(...)` - and a seventh question added to one spelling but not the other
#: would be a question one of the two front ends could not ask. `melody` is the one
#: name that differs: the flag states the exception (`--no-melody`) where the field
#: states the shipped default. The order is the flags' own, grouped by layer, which is
#: why it is not the dataclass field order; `tests/test_request.py` holds the two
#: spellings to this list as a set rather than a sequence.
_REQUEST_DESTS: Tuple[Tuple[str, str], ...] = (
    ("melody", "no_melody"),
    ("chord_on", "chord_on"),
    ("chord_notes", "chord_notes"),
    ("chord_fills", "chord_fills"),
    ("bass_on", "bass_on"),
    ("bass_notes", "bass_notes"),
)


@dataclass(frozen=True)
class ScoreMeta:
    """The score-level facts every writer needs, as one value.

    `None` for the metre and the key is the same "the caller did not state it"
    convention the writers already use, so this object does not force a default
    into a call that deliberately omitted one. `markers` are the head's repeat and
    ending instructions; a hand-built arrangement passes none.

    `first_bar_implicit` is the same convention applied to the first bar: `None`
    means nothing said it, `False` states a whole bar, `True` an anacrusis. It is
    threaded to all four writers, because a pickup bar is a fact about the score and
    not about the file format - a staff that drew a short bar as a pickup when the
    score says it is whole is the same error as a MusicXML `<measure implicit="yes">`
    that should not be there.
    """

    title: str
    subtitle: str = ""
    composer: str = ""
    beats_per_bar: Optional[int] = None
    beat_type: Optional[int] = None
    fifths: Optional[int] = None
    mode: str = ""
    markers: Sequence[Any] = ()
    first_bar_implicit: Optional[bool] = None


#: The `arranger head` wording. Says "of the notated bar" because three of the four
#: committed scores are in cut time, so the bar the `targets` rule fills is not four
#: beats long, and the help is where this is first stated.
#:
#: `fret_min`/`fret_max` were `None` here while the corpus half explained them -
#: the one flag pair one command had and the other did not. That was deliberate,
#: and `tests/test_cli.py` pinned it as a deliberate difference rather than an
#: oversight so a future agent would have to look before "tidying" it. Filling it
#: was still the right call: a flag the reader can pass but not understand is worse
#: than either state. What survives says what the deleted half could not - that the
#: window is an aim, not a filter, and that a head read from a score may want a
#: narrower one than a solo would.
HEAD_HELP = _CommonHelp(
    bars="narrow to a half-open LO-HI bar range; bounds may be negative",
    bars_per_line="bars per system on the staff",
    fret_min=(
        f"lowest fret to aim for (default {NECK_FRET_MIN}; an aim, not a filter). "
        f"The comp's own register starts one fret above it, so this flag moves the "
        f"comp as well as the tune"
    ),
    fret_max=(
        f"highest fret to aim for (default {NECK_FRET_MAX}; a chord with no "
        f"voicing inside the window is still played, outside it)"
    ),
    gp5="also write a Guitar Pro 5 file (needs: pip install 'jazz-arranger[gp]')",
    html="also write a self-contained HTML page",
    note_names="with --tab staff, add melody note names",
    musicxml="also write a MusicXML score (needs: pip install 'jazz-arranger[xml]')",
    mutes="with --tab staff, spell out the unsounded strings",
    tab="'staff' lays the head on one six-line staff, spaced on its real rhythm",
    no_melody=(
        "hand the tune to another instrument and comp instead. The chord keeps "
        "the tune's own written onsets, so the comp falls where the tune does - "
        "pass --chord-on every-beat for one on every felt beat, or name positions"
    ),
    chord_on=(
        "when the chord attacks, comma-separated, in felt beats: 'melody' (the "
        "default) at every written melody note, 'sustain' only at onsets whose note "
        "runs at least one felt beat, 'none', 'every-beat', or positions "
        "such as '1', '1and' (the and of 1) or 'lastand'. A list replaces the "
        "default, so '1and' is only the stab and 'melody,1and' is the harmonisation "
        "plus the stab. A position the metre does not have is refused, not dropped. "
        "Colon-separate the bars of a longer figure ('1,3:none'), which repeats "
        "from the form's first complete bar"
    ),
    chord_notes=(
        "how many chord notes to state: 'full' (the default) is the most the right "
        "hand can fit - three under the melody, two once a bass note takes a string "
        "- 'targets' is that same maximum on a strong beat and a thinner shape "
        "between them, and 3, 2 or 1 is exactly that many everywhere"
    ),
    chord_fills=(
        "what the chord does in a notated melody rest: 'none' (the default) rests "
        "with the tune, 'hold' states the written chord once at the rest's onset, "
        "and 'comp' states it on each felt beat through the rest. A rest with no "
        "chord gets nothing, and this never adds a bass note - that is --bass-on's"
    ),
    bass_on=(
        "when the bass attacks, comma-separated, in felt beats: 'none' (the "
        "default), 'every-beat', or positions such as '1' or '1and' (the and of "
        "1). The melody alone is the default, so a bass line is always asked for. "
        "A colon-separated cycle works here too ('1,3:none'); 'melody' is refused, "
        "because the thumb has no written onsets of its own"
    ),
    bass_notes=(
        "what each bass attack states: 'root' (the default), 'root-5th' "
        "alternating, 'walk' for the anchor/connect/approach line, or the note "
        "rules themselves as a comma-separated list ('root,approach'). The order "
        "is the resolution order. The rhythm is --bass-on's, so 'root' on every "
        "beat is a pedal rather than the old anchors-only rule"
    ),
)


def add_common_arguments(
    parser: argparse.ArgumentParser,
    help_text: _CommonHelp,
) -> None:
    """Add the flags the front end takes, to `parser`.

    **One caller.** Two flags are deliberately absent rather than forgotten:
    `--skeleton` and `--pick` are **not** offered, because this path does not reduce -
    every written note of a score gets its own slot. Where chords fall is the request's
    `chord_on`, and which notes the guitar plays is derived from the whole request.

    The order the flags are added in is the order they appear in `--help`.
    """
    parser.add_argument("--bars", default=None, help=help_text.bars)
    parser.add_argument(
        "--non-chord-tone",
        choices=NON_CHORD_TONE_STRATEGIES,
        default="extension",
    )
    parser.add_argument(
        "--fallback",
        choices=["diminished"],
        default=None,
        help="retry unresolved tensions as dim7 substitutions; replaces the written chord",
    )
    parser.add_argument(
        "--no-melody",
        action="store_true",
        help=help_text.no_melody,
    )
    parser.add_argument(
        "--chord-on",
        default=None,
        metavar="POSITIONS",
        help=help_text.chord_on,
    )
    parser.add_argument(
        "--chord-notes",
        choices=list(CHORD_NOTES),
        default=CHORD_NOTES_FULL,
        help=help_text.chord_notes,
    )
    parser.add_argument(
        "--chord-fills",
        choices=list(CHORD_FILLS),
        default=CHORD_FILLS_NONE,
        help=help_text.chord_fills,
    )
    parser.add_argument(
        "--bass-on",
        default=RHYTHM_NONE,
        metavar="POSITIONS",
        help=help_text.bass_on,
    )
    parser.add_argument(
        "--bass-notes",
        metavar="RULES",
        default=BASS_NOTES_ROOT,
        help=help_text.bass_notes,
    )
    parser.add_argument(
        "--fret-min",
        type=int,
        default=NECK_FRET_MIN,
        help=help_text.fret_min,
    )
    parser.add_argument(
        "--fret-max",
        type=int,
        default=NECK_FRET_MAX,
        help=help_text.fret_max,
    )
    parser.add_argument(
        "--tab",
        choices=["line", "staff"],
        default="line",
        help=help_text.tab,
    )
    parser.add_argument("--note-names", action="store_true", help=help_text.note_names)
    parser.add_argument("--mutes", action="store_true", help=help_text.mutes)
    parser.add_argument("--bars-per-line", type=int, default=4, help=help_text.bars_per_line)
    parser.add_argument("--html", default=None, metavar="PATH", help=help_text.html)
    parser.add_argument(
        "--musicxml",
        default=None,
        metavar="PATH",
        help=help_text.musicxml,
    )
    parser.add_argument("--gp5", default=None, metavar="PATH", help=help_text.gp5)


def _as_written(
    steps: List[ArrangementStep],
    markers: Sequence[Any],
    written_bars: Optional[Mapping[int, int]],
) -> Tuple[List[ArrangementStep], List[Any]]:
    """Folds a *played* arrangement onto the score's *written* bars, with the markers.

    The engine arranges the bars a performer plays - a repeat's section is expanded, so
    `synthetic_repeat_slash` is 66 bars. A notation file must not then write those 66 bars
    out **and** loop them with repeat signs: a reader would take the repeated section
    twice more. So a renderer that draws the signs is given **one pass of each written
    bar**, in written order, with each marker moved to the bar the score writes it on.

    `written_bars` is `Head.written_bars` (absolute -> written). A head with no repeat,
    no markers or no map is returned unchanged, so this is a no-op for every non-head
    caller and every non-repeating score. The first play-order occurrence of a written
    bar is the one kept, which is the pass a score reads first.
    """
    if not markers or not written_bars:
        return list(steps), list(markers)

    first: Dict[int, int] = {}
    for step in steps:
        if step.bar is None:
            continue
        written = written_bars.get(step.bar)
        if written is None:
            continue
        if written not in first or step.bar < first[written]:
            first[written] = step.bar

    kept: List[ArrangementStep] = []
    for step in steps:
        if step.bar is None:
            continue
        written = written_bars.get(step.bar)
        if written is None or step.bar != first.get(written):
            continue
        kept.append(replace(step, bar=written))
    kept.sort(key=lambda s: (s.bar if s.bar is not None else 0, s.beat or 0.0))

    moved = [replace(m, bar=m.written_bar) for m in markers]
    moved.sort(key=lambda m: (m.bar, m.kind))
    return kept, moved


def render_and_write(
    args: argparse.Namespace,
    steps: List[ArrangementStep],
    meta: ScoreMeta,
    *,
    notes: Sequence[str] = (),
    written_bars: Optional[Mapping[int, int]] = None,
) -> int:
    """Print the arrangement and write whatever files `args` asked for.

    `meta` is the score-level facts as one value: the title and credits, the
    notated metre, the key and the head's repeat markers. `head` already holds them
    together, and a hand-built arrangement names only the title it wants.

    Returns a process exit code: 0, or 1 if an optional renderer could not be
    imported. A missing extra is a usage problem rather than a crash, and it is
    reported *after* the tab has been printed - a run that asked for a GP5 file
    has already produced the thing it came for, and losing that to a missing
    dependency would be worse than the missing file.

    `meta.beats_per_bar` and `meta.beat_type` fall back to this writer's own
    default of 4 when `None`. `meta.fifths` / `meta.mode` follow the same
    convention: `None` means 0, which is C major and what an absent `<key>`
    already means in a MusicXML document. The key reaches the two **file** writers
    only - `format_musicxml` writes `<key>` and `format_gp5` a `KeySignature` - and
    deliberately not `format_tab_staff` or `write_tab_html`, which show fret numbers
    rather than pitches and so have nothing for a signature to say.

    `notes` goes only to the HTML page, the one renderer that shows them; the two
    file writers have no notes list.

    `meta.markers` are the head's repeat and ending instructions
    (`headxml.BarMarker`s), or empty for none - every non-head caller, and a head
    with no repeat. Each reaches every sign-drawing writer, which draws it as a
    `|:` / `:|` and a `1.` / `2.` bracket.

    `written_bars` is `Head.written_bars` (absolute -> written), and it is what makes the
    written score come out written: the arrangement is the bars a player *plays*, so a
    renderer that draws the signs is handed the **written** bars instead - see
    `_as_written`. The plain `line` tab keeps the played arrangement, which is the one
    place every bar of a repeated head is still listed.

    `meta.first_bar_implicit` reaches **every** writer, the two on-screen ones
    included: whether the first bar is an anacrusis is a fact about the score, and it
    is not one the onsets can say.
    """
    from tabgp import write_gp5
    from tabstaff import format_tab_staff, write_tab_html
    from tabxml import write_musicxml

    # The score the sign-drawing renderers get: one pass of each written bar.
    written_steps, written_markers = _as_written(steps, meta.markers, written_bars)

    # A count without a denominator is not a metre, and `head` is the command that
    # has to say which. Four is the writer's own default, so a caller with no metre
    # lands in the same place rather than raising.
    bars = 4 if meta.beats_per_bar is None else meta.beats_per_bar
    beat = 4 if meta.beat_type is None else meta.beat_type
    # The key, on the same terms as the metre above: 0 is C major, which is what a
    # MusicXML document with no `<key>` already means, so passing nothing is not a
    # change.
    key_fifths = 0 if meta.fifths is None else meta.fifths

    if args.tab == "staff":
        # The staff is the only renderer that uses the step timing, so it is the
        # one that can show where a chord actually falls in the bar - and, with its
        # `show_timing` rows, the only one that says how long it sounds. `beat_type`
        # reaches it for the same reason it reaches the two score writers: a head
        # in cut time is 2/2, and a count without a denominator is not a metre.
        print(
            format_tab_staff(
                written_steps,
                beats_per_bar=bars,
                beat_type=beat,
                measures_per_line=args.bars_per_line,
                show_melody=args.note_names,
                show_mutes=args.mutes,
                markers=written_markers,
                first_bar_implicit=meta.first_bar_implicit,
            )
        )
    else:
        print(format_progression(steps))

    if args.html:
        out_path = write_tab_html(
            written_steps,
            args.html,
            title=meta.title,
            subtitle=meta.subtitle,
            beats_per_bar=bars,
            beat_type=beat,
            measures_per_line=args.bars_per_line,
        )
        print(f"\nwrote {out_path}")

    # The two optional renderers are written separately from each other and from
    # the HTML, so a run asking for one does not need the others' dependency, and
    # a missing one is a usage problem rather than a crash. Each is on its own
    # extra: a run asking for a GP5 file and a run asking for MusicXML must not
    # require each other's dependency.
    for flag, writer in (("musicxml", write_musicxml), ("gp5", write_gp5)):
        target = getattr(args, flag)
        if not target:
            continue
        try:
            out_path = writer(
                written_steps,
                target,
                title=meta.title,
                subtitle=meta.subtitle,
                composer=meta.composer,
                beats_per_bar=bars,
                beat_type=beat,
                fifths=key_fifths,
                mode=meta.mode,
                markers=written_markers,
                first_bar_implicit=meta.first_bar_implicit,
            )
        except ImportError as error:
            print(f"\n{error}")
            return 1
        print(f"wrote {out_path}")
    return 0
