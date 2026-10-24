"""Per-step rendering: one compact block per chord.

`format_progression` is the compact renderer, and it is **pure** - it returns a
string and prints nothing, so the caller stays in control of the output. The
whole-progression staff renderers are a different shape of output and live in
`tabstaff`; a six-line vertical block for a *single* voicing is
`Voicing.tab_block()`, which is not the same surface.

A step is four fixed columns and, after them, its explanation. A short explanation
stays on the step's own line, and a long one is laid out over as many lines as it
needs, indented to the column the explanation starts in, so the columns stay a table
and the prose stays readable.

`step_annotation` lives in `annotation`, and is shared by `format_progression` and
the demonstration, so the two renderings cannot drift apart. A step can be several
things at once - a non-chord tone, a chord tone with a degree to name, a repeated
melody, a partial shell, a thumb note - and the precedence between them is the whole
content of that function.

The tab-cell primitives (`MUTED_CELL`, `cells_from_frets`) are **not** defined
here: `Voicing.tab_block` calls them and `Voicing` sits below this module, so they
live in `tuning` and are imported from there. `STAFF_CELL_WIDTH` and
`_tab_block_from_cells` live in `tuning` for the same reason and are imported from
there too.
"""

from __future__ import annotations

from typing import List, Optional

from .annotation import melody_degree_label, step_annotation
from .step_types import MUTED_CELL, STAFF_CELL_WIDTH, ArrangementStep, cells_from_frets
from .text_layout import annotation_lines

__all__ = ["MUTED_CELL", "STAFF_CELL_WIDTH", "format_progression", "print_step"]


#: The width `format_progression` lays a step's explanation out to. A line breaks only
#: when its annotation would otherwise run past this, so a short explanation is printed
#: on the step's own line exactly as it always was. It is a **preference and never a
#: truncation**: a clause wider than the room it has is wrapped at its own spaces, and a
#: single word wider than that overflows rather than being cut.
_PROGRESSION_WIDTH = 100

#: The narrowest column the wrapped explanation may be laid out in, for a caller who asks
#: for a width the four fixed columns already fill. Below this the text wraps word by word,
#: which is not a layout anybody wants to read.
_MIN_ANNOTATION_ROOM = 20


def _mute_ringing_bass(step: ArrangementStep, cells: List[str]) -> List[str]:
    """A thumb note still ringing is **not plucked**, and this renderer says what is.

    The fret is in the vector because the string really is sounding - the score ties it
    to the note that struck it - so the cell is muted here rather than left out.
    """
    string = step.voicing.bass_string
    if step.bass_held and string is not None:
        cells[string] = "x"
    return cells


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
    player must not attack reads the same as a mute. A step that is *both* `repeated` and
    `bass_only` is a walking bass under a re-articulated melody, and it plays the soprano
    and the thumb - so the two rules compose rather than override one another, which is
    the case an `elif` chain would silently drop.

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
        return _mute_ringing_bass(step, cells_from_frets(frets))
    struck = set()
    if step.bass_only:
        struck.add(step.voicing.bass_string)
    if step.repeated:
        if not step.melody_voiced:
            # Hold the whole shape: the soprano is not ours to re-strike, and the
            # inner voices are still ringing from the step before. `bass_only` is a
            # separate case above and composes with this one, exactly as it does when
            # the guitar does sing.
            return cells_from_frets(frets)
        struck.add(step.voicing.soprano_string())
        # A repeated melody still moves the thumb: the bass is a moving voice, not a
        # held one, so blanking it here would silently delete the walking line.
        if step.voicing.bass_midi is not None:
            struck.add(step.voicing.bass_string)
    # Every string the step does not play is muted: the line states what is plucked.
    cells = [MUTED_CELL] * len(frets)
    for string_index in struck:
        if string_index is not None and 0 <= string_index < len(frets):
            cells[string_index] = str(frets[string_index])
    return cells


def _format_step(
    step: ArrangementStep, width: Optional[int] = _PROGRESSION_WIDTH
) -> List[str]:
    """One compact block: chord, melody, degree column, tab, then the annotation.

    The first three columns are fixed width, and the annotation - whose text length
    varies - is **appended after the tab** rather than printed between the melody and
    it. That is what stops the shape drifting: an inline annotation is as wide as its
    own text, so an annotated step would otherwise start its tab in a different column
    from every unannotated one.

    Each tab is **hyphen-joined and ragged** - `x-11-x` is wider than `x-x-x` - so a
    shape's own width varies. The field holding it is padded to the widest a six-cell
    tab can be, which is what starts every annotation in the same column.

    A step whose annotation fits `width` is **one line**, so a short explanation reads
    exactly as it always has. A longer one continues on the lines below, each indented
    to the column the explanation starts in - the four fields and the space between the
    tab field and the prose - so the columns stay a table. `width=None` asks for one line
    per step however long it runs.
    """
    cells = _step_cells(step)
    tab = "-".join(cells)
    # Two characters per cell - a fret reaches 18 - plus one hyphen between each pair.
    field = len(cells) * STAFF_CELL_WIDTH + len(cells) - 1
    # A note a stab released is not sounding, so neither the melody column nor its
    # degree names it. `_comping_tail` says which note the stab ended, which is the fact
    # the blank column would otherwise hide.
    melody = "" if step.melody_released else (step.melody or "")
    line = (
        f"{step.chord:<8} {melody:<3} "
        f"{melody_degree_label(step):<4} {tab:<{field}}"
    )
    annotation = step_annotation(step).strip()
    if not annotation:
        # No explanation, so no column to hold open: drop the field's padding rather
        # than leave a run of trailing spaces.
        return [line.rstrip()]
    indent = " " * (len(line) + 1)
    if width is None:
        return [f"{line} {annotation}"]
    room = max(width - len(indent), _MIN_ANNOTATION_ROOM)
    laid_out = annotation_lines(annotation, room)
    return [f"{line} {laid_out[0]}"] + [indent + part for part in laid_out[1:]]


def format_progression(
    steps: List[ArrangementStep], width: Optional[int] = _PROGRESSION_WIDTH
) -> str:
    """
    Renders an arranged progression as tab and returns it as a string.

    This is a pure renderer: it prints nothing and writes nothing to stdout, so
    the caller stays in control of the output. Each step is one **block** in four fixed
    columns - chord, melody, the melody's degree above the chord, and the tab - so
    every shape starts in the same column:

        Dm7      D5  Root x-x-10-10-10-10    (harmony under Root - 4 voices - sounding: C b7, F b3, A 5, D Root)
        G7       B4  3    13-x-12-12-12-x    (harmony under 3 - 4 voices - sounding: F b7, D 5, G Root, B 3)
        Cmaj7    C5  Root x-x-9-9-8-8        (harmony under Root - 4 voices - sounding: B 7, E 3, G 5, C Root)

    Each tab is hyphen-joined and ragged, so shapes differ in width; the **field** is
    padded to the widest a six-cell tab can be, which starts every **annotation**
    (below) in the same column rather than wherever the shape happens to end.

    The **degree column** names the melody's relationship to its chord - a chord tone
    as the degree it is (`Root`, `3`, `b7`), a note outside the chord as the tension it
    spells (`b9`, `#11`, `13`). It is `chords.melody_degree_name`, and it is blank when
    there is no melody or no readable chord to measure against.

    The **annotation** (`step_annotation`) is appended after the tab rather than
    inline, which is what keeps the tab column fixed: an inline annotation is as wide
    as its own text, so an annotated step's tab would start further right than an
    unannotated one's. An explanation longer than `width` continues on the lines below
    its step, each indented to the column the explanation starts in, so the four
    columns stay a table to read down and the prose stays on lines of a readable length:

        Ebmaj7   B4  b13  x-10-x-8-11-7     (non-chord tone -
                                            the extension strategy found no voicing; the written chord
                                            stands - 4 voices - sounding: G 3, Eb Root, Bb 5, B b13 -
                                            the chord tone it leaves out is 7)

    The width is a **preference and never a truncation** - nothing is dropped, and a
    single word wider than the room it has overflows rather than being cut. `width=None`
    asks for one line per step however long it runs, which is what the renderer returned
    before the continuation lines existed.

    The six-line vertical form is not this renderer's: a whole-progression staff is what
    a player reads, and `format_tab_staff` in `tabstaff` renders one, with the chords on
    their real beats. **This renderer is the compact summary and nothing else**, which is
    the shape the demo and `make demo` print.

    A single voicing still renders vertically through `Voicing.tab_block()` / `.tab()` and
    `ArrangementStep.tab_block()`, which is where `_tab_block_from_cells` lives.

    Args:
        steps: arrangement steps, typically from VoiceLeadingEngine.arrange_progression.
        width: the line width the explanations are laid out to, or None for one line per
            step. A step whose annotation fits is one line either way.

    Returns:
        The rendered tab, with steps separated by newlines and a long explanation
        continued on the lines below its step.
    """
    return "\n".join(
        line for step in steps for line in _format_step(step, width)
    )


def print_step(step: ArrangementStep) -> None:
    """Prints one arranged step, including which string carries the melody."""
    melody_string = 6 - step.voicing.soprano_string()  # guitar string number, 1 = high E
    melody = "" if step.melody_released else (step.melody or "")
    print(
        f"Chord: {step.chord:<8} | Melody: {melody:<3}{step_annotation(step)} | "
        f"Tab [E-A-D-G-B-E]: {'-'.join(_step_cells(step))} | Melody string: {melody_string}"
    )
