"""The pure string layout an annotation is broken into: units, chunks, lines.

`annotation` composes the words a step's explanation is made of; this module breaks
that text into lines. Nothing here reads a chord or a step - the input is a string and
a column count - so it imports no sibling and is testable on its own.

`render` is the only caller today, through `annotation_lines`; the clause boundaries
`_annotation_units` finds are the ones `annotation.step_annotation` composed.
"""

from __future__ import annotations

from typing import List, Tuple


def _annotation_units(body: str) -> List[Tuple[str, str]]:
    """An annotation's clauses as (joiner, text) pairs, in the order they print.

    The joiner is what precedes each clause - the empty string for the first, ` - ` for
    the next clause of the same parenthetical, and ` (` for the **bass** parenthetical,
    which `annotation._bass_annotation` appends after the first one closes. Reading the
    boundaries out of the finished text rather than rebuilding the clause list is
    deliberate: the precedence between the routes is `annotation.step_annotation`'s, and
    a second copy of it here would be a second answer to one question.
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
