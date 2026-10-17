"""The MusicXML front end's argparse block and its output dispatch.

`add_common_arguments` writes the flags once rather than making each caller copy them, so
a flag cannot be added in one place and silently missed in another. The idea behind the
split is that **the duplication worth removing is the *argument*, not the *prose***: the
flags whose help is identical are written once here, and prose that genuinely differs is
kept and lives in one table. `head`'s `--texture` says "of the notated bar" because a
score has a notated metre, and `HEAD_HELP` holds the rest. `CommonHelp` is one dataclass
with one field per flag, so a flag added here has nowhere else to be forgotten, and
`tests/test_cli.py` asserts every declared field reaches `add_argument` with its text.

**Laziness is deliberate and load-bearing.** `argparse` is imported only under
`TYPE_CHECKING` (the annotations are strings, so nothing at runtime needs it) and the
renderers are imported *inside* `render_and_write`. Importing `tabstaff` at module scope
would execute the package `__init__` through `arranger.tuning`, so the import stays in the
function body - which is also what leaves `headxml`'s `load_musicxml` cheap.

This module sits **last** in `tests/test_package_dag.py`'s `ORDER`: it reads
`NECK_FRET_MIN`/`MAX` from `tuning`,
`NON_CHORD_TONE_STRATEGIES` from `chords`, `TEXTURE_STYLES` from `texture` and
`format_progression` from `render`, and is imported by nothing below it. It needs
no `ALLOWED_EDGES` entry, which is the test that a new module was placed by its
edges rather than appended.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .bass_rules import (
    BASS_STYLE_AUTO,
)
from .chords import NON_CHORD_TONE_STRATEGIES
from .grid import GRID_DEFAULT
from .harmony import HARMONY_AUTO, HARMONY_STYLES
from .parts import PARTS_AUTO
from .render import format_progression
from .texture import TEXTURE_STYLES
from .tuning import NECK_FRET_MAX, NECK_FRET_MIN, ArrangementStep

if TYPE_CHECKING:  # pragma: no cover - the annotations are strings at runtime
    import argparse

__all__ = [
    "HEAD_HELP",
    "CommonHelp",
    "ScoreMeta",
    "add_common_arguments",
    "render_and_write",
]

@dataclass(frozen=True)
class CommonHelp:
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
    melody: str
    musicxml: str
    mutes: str
    tab: str
    texture: str


@dataclass(frozen=True)
class ScoreMeta:
    """The score-level facts every writer needs, as one value.

    `None` for the metre and the key is the same "the caller did not state it"
    convention the writers already use, so this object does not force a default
    into a call that deliberately omitted one. `markers` are the head's repeat and
    ending instructions; a hand-built arrangement passes none.
    """

    title: str
    subtitle: str = ""
    composer: str = ""
    beats_per_bar: Optional[int] = None
    beat_type: Optional[int] = None
    fifths: Optional[int] = None
    mode: str = ""
    markers: Sequence[Any] = ()


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
HEAD_HELP = CommonHelp(
    bars="narrow to a half-open LO-HI bar range; bounds may be negative",
    bars_per_line="bars per system on the staff",
    fret_min=f"lowest fret to aim for (default {NECK_FRET_MIN}; an aim, not a filter)",
    fret_max=(
        f"highest fret to aim for (default {NECK_FRET_MAX}; a chord with no "
        f"voicing inside the window is still played, outside it)"
    ),
    gp5="also write a Guitar Pro 5 file (needs: pip install 'jazz-arranger[gp]')",
    html="also write a self-contained HTML page",
    melody="with --tab staff, add melody note names",
    musicxml="also write a MusicXML score (needs: pip install 'jazz-arranger[xml]')",
    mutes="with --tab staff, spell out the unsounded strings",
    tab="'staff' lays the head on one six-line staff, spaced on its real rhythm",
    texture=(
        "'targets' states a full chord on beats 1 and 3 of the notated bar and "
        "fills the notes between with a shell, a 3rd/6th or the melody alone; "
        "'uniform' (the default) voices every note in full"
    ),
)

def add_common_arguments(
    parser: argparse.ArgumentParser,
    help_text: CommonHelp,
) -> None:
    """Add the flags the front end takes, to `parser`.

    **One caller now.** This was written for two commands that shared a block of
    flags, and its prose spoke throughout of "both" and "the other" - which is how
    `--skeleton` and `--pick` are **not** offered, and the reason is a policy
    rather than an omission: the MusicXML path does not reduce - every written note of a
    score gets its own slot. Where chords fall is the `grid=` axis, and which notes the
    guitar plays is the `parts=` axis.

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
        "--texture",
        choices=list(TEXTURE_STYLES),
        default="uniform",
        help=help_text.texture,
    )
    parser.add_argument(
        "--bass-style",
        default=BASS_STYLE_AUTO,
        help=(
            "which note rules the thumb line may state, comma-separated and in "
            "resolution order, any of root, 5th, approach, nearest. The full "
            "'root,5th,approach,nearest' puts a note on every beat, which is what makes "
            "the line a walk; 'root' alone sounds only where the harmony anchors. "
            "'none' is no line at all, and 'auto' - the default - follows the parts "
            "selection: a selection that takes the bass part writes the full list, and "
            "one that leaves it out writes no line. Refused outright where the "
            "selection does not take the bass part; a single note the left hand cannot "
            "reach is dropped from that step and named on it"
        ),
    )
    parser.add_argument(
        "--parts",
        default=PARTS_AUTO,
        help=(
            "which of melody, bass and chord the guitar takes, comma-separated "
            "(default: auto = all three). 'melody' is the tune on top, 'bass' the "
            "bottom the thumb realises, 'chord' the harmonisation between them, "
            "whose arity --texture states and whose degree order --harmony states. "
            "Leaving the melody out hands the tune to another instrument and leaves "
            "a comping part; melody alone is the tune and nothing else (with a thumb "
            "under it when bass is named too). A policy named for a part the "
            "selection leaves out is refused, naming the part that would work"
        ),
    )
    parser.add_argument(
        "--harmony",
        choices=list(HARMONY_STYLES) + [HARMONY_AUTO],
        default=HARMONY_AUTO,
        help=(
            "the order the chord part states its degrees in: 'auto' (the default) is "
            "the full chord when the guitar sings and the guide pair (3rd and 7th) "
            "when it comps, 'guide' is the pair, 'shell_root' adds a root or 5th under "
            "them, 'full' is the whole tone set. --texture takes the first n of the "
            "order, so a thinner part gives up the tail. Refused where the selection "
            "does not take the chord part"
        ),
    )
    parser.add_argument(
        "--grid",
        default=GRID_DEFAULT,
        help=(
            "when each part sounds, as comma-separated PART:PATTERN rows. The "
            "default is melody:every_note - the chord under every written melody "
            "note - and a row overrides one part: chord:every_note|freddie|joe_pass|"
            "final_and|charleston, bass:every_note|walk|anchors. So "
            "'melody:every_note,bass:walk' is a chord under the tune with the thumb "
            "walking every beat, and 'bass:anchors' walks only where the harmony "
            "changes. Positions are bar-relative, so final_and is the same musical "
            "idea in 2/2, 3/4 and 4/4. Where the guitar is singing, a note with no "
            "chord on it sounds alone; where it is comping, the guitar rests"
        ),
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
    parser.add_argument("--melody", action="store_true", help=help_text.melody)
    parser.add_argument("--mutes", action="store_true", help=help_text.mutes)
    parser.add_argument(
        "--bars-per-line", type=int, default=4, help=help_text.bars_per_line
    )
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
    `heres_that_rainy_day` is 66 bars. A notation file must not then write those 66 bars
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
    """
    from tabgp import write_gp5
    from tabstaff import format_tab_staff, write_tab_html
    from tabxml import write_musicxml

    # The score the sign-drawing renderers get: one pass of each written bar.
    written_steps, written_markers = _as_written(
        steps, meta.markers, written_bars
    )

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
                show_melody=args.melody,
                show_mutes=args.mutes,
                markers=written_markers,
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
            show_melody=args.melody,
            show_mutes=args.mutes,
            notes=list(notes),
            markers=written_markers,
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
            )
        except ImportError as error:
            print(f"\n{error}")
            return 1
        print(f"wrote {out_path}")
    return 0
