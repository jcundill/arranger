"""The two command-line front ends' shared argparse block and output dispatch.

`wjazzd.corpus_cli` (a Weimar transcription) and `headxml.head_cli` (a written
MusicXML head) are separate commands over separate sources, and their *output*
legitimately differs: the corpus prints a performer and key, `head` prints the
notated metre. What is not legitimate is that they hand-copied the same argparse
block, because then a flag added to one CLI is silently missing from the other -
defect #4 in `implementation_plan.md`, and the last of the six open.

**The flag semantics were already identical; the help text was not.** Measured on
the tree before this module existed: 17 flags in both parsers, and all 17 agreed
exactly on `type`, `choices`, `default`, `nargs` and `metavar`. Eleven of the 17
disagreed on their `--help` string - `--fret-min` and `--fret-max` had help text in
`corpus` and none at all in `head`. So a bare `add_common_arguments(parser)`
would have quietly changed one command's `--help`, which nothing asserts. Hence
the split below: **the six flags whose help is identical are written once here**,
and the eleven that differ are `CommonHelp` values named for their command.

**Sixteen now, because `--vertical` was removed.** It was one of the six whose
help is identical, and it is gone: the six-line block per chord it selected is
`format_progression`'s former second branch, and a whole-progression staff is what
a player reads, so `tabstaff` covers it. The eleven that differ are untouched, so
the count only fell on this side of the split - five flags are now written once
here. The measurement above is kept as the record of what it was; `tests/
test_cli.py` asserts the current split in both directions, so the removal cannot
silently leave one of the two sides stale.

That is the design constraint worth stating: the duplication this fixes is the
*argument*, not the *prose*. Prose that genuinely differs - `corpus`'s `--bars`
mentions pickups because a Weimar transcription has an anacrusis, `head`'s
`--texture` says "of the notated bar" because a score has a notated metre - is
kept, and now lives in one table instead of two parsers.

**Laziness is deliberate and load-bearing.** `argparse` is imported only under
`TYPE_CHECKING` (the annotations are strings, so nothing at runtime needs it) and
the renderers are imported *inside* `render_and_write`. Importing `tabstaff` at
module scope would execute the package `__init__` through `arranger.tuning`, which
is the cycle Phase 6 measured; keeping it in the function body is also what leaves
`headxml`'s `load_musicxml` as cheap as it was, which is the reason those imports
are function-local today.

This module sits **last** in `tests/test_package_dag.py`'s `ORDER`: it reads
`NECK_FRET_MIN`/`MAX` from `tuning`, `GRIP_PREFERENCE` from `grips`,
`NON_CHORD_TONE_STRATEGIES` from `chords`, `TEXTURE_STYLES` from `textures` and
`format_progression` from `render`, and is imported by nothing below it. It needs
no `ALLOWED_EDGES` entry, which is the test that a new module was placed by its
edges rather than appended.

The reduction vocabularies (`SKELETON_STRATEGIES`, `SLOT_PICKS`) are **parameters**
rather than imports. They belong to `wjazzd`, which is a top-level module outside
the package's DAG and one this package must not reach up into; `headxml` already
borrows both from there, so passing them through costs one argument at each call
site and keeps the one-way dependency honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence

from .chords import NON_CHORD_TONE_STRATEGIES
from .grips import GRIP_PREFERENCE
from .render import format_progression
from .textures import TEXTURE_STYLES
from .tuning import NECK_FRET_MAX, NECK_FRET_MIN, ArrangementStep

if TYPE_CHECKING:  # pragma: no cover - the annotations are strings at runtime
    import argparse

__all__ = [
    "CORPUS_HELP",
    "HEAD_HELP",
    "CommonHelp",
    "add_common_arguments",
    "render_and_write",
]

@dataclass(frozen=True)
class CommonHelp:
    """The `--help` prose for the shared flags whose text differs between commands.

    One field per flag that `corpus` and `head` spell differently. A flag absent
    from this dataclass has its help written once in `add_common_arguments`,
    because the two commands agree on it - `fallback`, `grips`, `non_chord_tone`,
    `pick` and `skeleton` are those five, and there is deliberately no way to add a
    sixth without stating the new text twice. (`vertical` was the sixth until it
    was removed along with the branch of `format_progression` it selected.)

    `Optional` rather than `str` because `head` gives `--fret-min` and
    `--fret-max` no help at all, and `argparse`'s own default for `help` is
    `None`; preserving that difference is the point of the type.
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


#: The `arranger corpus` wording. Longer on the file-writing flags because the
#: corpus command's own README examples use them, and `--bars` names the pickups
#: because a Weimar transcription has an anacrusis: 1,335 `beats` rows across 149
#: transcriptions sit below bar 0, which is why that range's bounds may be
#: negative.
CORPUS_HELP = CommonHelp(
    bars="narrow to a half-open LO-HI bar range; bounds may be negative for pickups",
    bars_per_line="with --tab staff, bars per line",
    fret_min=f"lowest fret the selector aims for (default {NECK_FRET_MIN})",
    fret_max=f"highest fret the selector aims for (default {NECK_FRET_MAX})",
    gp5=(
        "also write the head to PATH as a Guitar Pro 5 file "
        "(e.g. --gp5 head.gp5). Needs the optional extra: "
        "pip install 'jazz-arranger[gp]'"
    ),
    html=(
        "also write the head to PATH as a self-contained HTML page "
        "(e.g. --html head.html), and say where it went"
    ),
    melody="with --tab staff, add a line of melody note names",
    musicxml=(
        "also write the head to PATH as MusicXML, for a notation program "
        "(e.g. --musicxml head.musicxml). A notation staff only; for the "
        "fingering use --gp5. Needs the optional extra: "
        "pip install 'jazz-arranger[xml]'"
    ),
    mutes="with --tab staff, spell out the unsounded strings as x",
    tab=(
        "'staff' lays the head on one six-line staff, spaced on its real "
        "rhythm; 'line' (the default) keeps one line per chord"
    ),
    texture=(
        "'targets' states a full chord on beats 1 and 3 and fills the notes "
        "between with a shell, a 3rd/6th or the melody alone; 'uniform' (the "
        "default) voices every note in full"
    ),
)

#: The `arranger head` wording. Says "of the notated bar" where the corpus cannot:
#: three of the four committed scores are in cut time, so the bar the `targets`
#: rule fills is not four beats long, and the help is where that is first stated.
HEAD_HELP = CommonHelp(
    bars="narrow to a half-open LO-HI bar range; bounds may be negative",
    bars_per_line="bars per system on the staff",
    fret_min=None,
    fret_max=None,
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
    *,
    skeleton_strategies: Sequence[str],
    slot_picks: Sequence[str],
) -> None:
    """Add the 16 flags both front ends take, to `parser`.

    `help_text` supplies the prose for the eleven flags whose wording differs
    between the commands; the other five are written once here because the two
    agree on them. `skeleton_strategies` and `slot_picks` are the reduction
    vocabularies, passed in because they belong to `wjazzd` - see the module
    docstring for why they are not imported.

    The order the flags are added in is the order they appear in `--help`. Each
    command now adds its own flags first and this block after, so the shared
    sixteen appear in the same relative order in both. `head`'s listing is
    unchanged by this; `corpus`'s moves `--lift` up to sit with its other
    corpus-specific flags rather than between `--pick` and `--non-chord-tone`,
    which is the only visible difference either command's `--help` has.
    """
    parser.add_argument("--bars", default=None, help=help_text.bars)
    parser.add_argument("--skeleton", choices=skeleton_strategies, default="eighths")
    parser.add_argument("--pick", choices=slot_picks, default="first")
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
        "--grips",
        nargs="+",
        choices=GRIP_PREFERENCE,
        default=list(GRIP_PREFERENCE),
        help="grip families to use, most preferred first (default: all of them)",
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


def render_and_write(
    args: argparse.Namespace,
    steps: List[ArrangementStep],
    *,
    title: str,
    subtitle: str = "",
    notes: Sequence[str] = (),
    beats_per_bar: Optional[int] = None,
    beat_type: Optional[int] = None,
) -> int:
    """Print the arrangement and write whatever files `args` asked for.

    Returns a process exit code: 0, or 1 if an optional renderer could not be
    imported. A missing extra is a usage problem rather than a crash, and it is
    reported *after* the tab has been printed - a run that asked for a GP5 file
    has already produced the thing it came for, and losing that to a missing
    dependency would be worse than the missing file.

    `beats_per_bar` and `beat_type` are the notated metre, and both fall back to
    this writer's own default of 4 when `None`. That is what lets one function
    serve both commands: `corpus` passes nothing (a Weimar transcription is 4/4,
    so its writers' defaults were already right) and `head` passes the score's
    own. Passing the default and omitting the argument are indistinguishable at
    every writer, which was checked against `format_tab_html`, `format_musicxml`
    and `format_gp5` rather than assumed.

    `notes` goes only to the HTML page, the one renderer that shows them; the two
    file writers have no notes list. `subtitle` defaults to `""`, which is also
    `format_musicxml`'s and `format_gp5`'s own default, so the `head` command
    passing nothing here is indistinguishable from passing an empty string - which
    is what makes one dispatch correct for a command that names a performer and one
    that does not.
    """
    from tabgp import write_gp5
    from tabstaff import format_tab_staff, write_tab_html
    from tabxml import write_musicxml

    # A count without a denominator is not a metre, and the score commands are
    # the ones that have to say which. Four is the writer's own default, so a
    # corpus run passes nothing and lands in the same place.
    bars = 4 if beats_per_bar is None else beats_per_bar
    beat = 4 if beat_type is None else beat_type

    if args.tab == "staff":
        # The staff is the only renderer that uses the step timing, so it is the
        # one that can show where a chord actually falls in the bar - and, with its
        # `show_timing` rows, the only one that says how long it sounds. `beat_type`
        # reaches it for the same reason it reaches the two score writers: a head
        # in cut time is 2/2, and a count without a denominator is not a metre.
        print(
            format_tab_staff(
                steps,
                beats_per_bar=bars,
                beat_type=beat,
                measures_per_line=args.bars_per_line,
                show_melody=args.melody,
                show_mutes=args.mutes,
            )
        )
    else:
        print(format_progression(steps))

    if args.html:
        written = write_tab_html(
            steps,
            args.html,
            title=title,
            subtitle=subtitle,
            beats_per_bar=bars,
            beat_type=beat,
            measures_per_line=args.bars_per_line,
            show_melody=args.melody,
            show_mutes=args.mutes,
            notes=list(notes),
        )
        print(f"\nwrote {written}")

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
            written = writer(
                steps,
                target,
                title=title,
                subtitle=subtitle,
                beats_per_bar=bars,
                beat_type=beat,
            )
        except ImportError as error:
            print(f"\n{error}")
            return 1
        print(f"wrote {written}")
    return 0
