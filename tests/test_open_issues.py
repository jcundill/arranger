"""The figures `docs/open-issues.md` states must be the figures the tree produces.

An open issue is filed with its measurement — that document's header says so, and the
measurement is what makes an item an issue rather than a complaint. Nothing enforced it.
`tests/test_docs.py` fails when a stated **version**, a **module count** or a relative
**link** goes stale, but a count inside `open-issues.md` could rot in silence, and did:
once when the `Diagnostics` collector was deleted, once when the loader began playing
repeats, and once when `bass_refused` started counting every refused thumb where the old
warning counted a single call site.

So every figure that document states is re-measured here and compared against what it
says. A number that moves fails the gate naming the document, and the fix is to re-measure
and write the new one down — the same discipline the hardcoded tab strings in the other
test modules enforce for the voicings, and for the same reason: a check that regenerates
its own expectation cannot catch a regression.

Two limits are deliberate. The measurement is *read* from the document and re-taken, so a
figure this file does not know about is not checked — the counts re-measured here are the
ones that moved. And item 2's cause split needs a **replica** of `_place_bass`'s three
filters, because `ArrangementStep.bass_refused` carries the wanted pitch class and not the
reason it could not be placed; the replica is justified where it is written.
"""

from __future__ import annotations

import contextlib
import glob
import io
import re
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import arranger.bass as bass
import arranger.movement as movement
import headxml
from arranger.chords import ChordParser
from arranger.fingers import can_fret
from arranger.tuning import STANDARD_TUNING

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "open-issues.md"

#: Every committed head, in the order the document lists them.
HEADS: List[str] = (
    sorted(glob.glob(str(ROOT / "tests" / "data" / "*.musicxml")))
    + sorted(glob.glob(str(ROOT / "tests" / "data" / "*.mxl")))
)

#: The rows that place a thumb note under a texture that has one. `uniform` carries a thumb
#: line now too, but item 2's chain of counts — 53 at `d9403e5`, 39 at `246ff69` — was taken
#: over these four, so staying on them is what keeps the figures comparable with it.
THUMB_ROWS: Tuple[Tuple[str, str], ...] = (
    ("targets", "anchors"),
    ("targets", "walk"),
    ("walking_bass", "anchors"),
    ("walking_bass", "walk"),
)


def _union_added() -> Dict[str, int]:
    """Per head, the slots the bar-level union adds.

    A bar the melody never enters contributes no melody slot at all, so every grid position
    in one is the union's — which is why this needs neither a monkeypatch nor a \"before\"
    tree (trap 8): the two methods agreeing is what made the figure trustworthy.
    """
    added: Dict[str, int] = {}
    for path in HEADS:
        head = headxml.load_musicxml(path, None)
        melody_bars = {bar for _t, bar, _b, _d in headxml.head_skeleton(head, None)}
        added[Path(path).name] = len(
            [
                slot
                for slot in headxml.chord_slots(head, None, "every_note")
                if slot[3] not in melody_bars
            ]
        )
    return added


def _cause(upper: Any, pitch_class: int, held: Any) -> str:
    """Which of `_place_bass`'s three filters emptied the palette, as a label.

    **A replica, and that is the honest description of it.** `ArrangementStep.bass_refused`
    records the wanted pitch class and not the reason it could not be placed, so naming the
    cause means running the function's own three tests again: the free-string set, the
    octaves of the wanted pitch below the shape's own lowest note, and the `can_fret`
    four-fret budget — in that order, because the first that comes back empty is the reason.
    It is validated by agreement rather than by inspection: over all 2,624 calls it agrees
    with the real `_place_bass` on every outcome, which is what lets the split count as a
    measurement. Recording the cause on the field would delete this function.
    """
    upper_midis = upper.midi_notes()
    if not upper_midis:
        return "empty upper"
    lowest = min(upper_midis)
    sounding = list(upper.frets)
    hand_base = list(upper.frets)
    if held is not None:
        held_frets, held_thumb = held
        structure = [
            -1 if index == held_thumb else fret
            for index, fret in enumerate(held_frets)
        ]
        structure_midis = [
            STANDARD_TUNING[index].midi_note() + fret
            for index, fret in enumerate(structure)
            if 0 <= index < len(STANDARD_TUNING) and fret >= 0
        ]
        if structure_midis:
            lowest = min(lowest, min(structure_midis))
        sounding = [
            upper.frets[index]
            if upper.frets[index] >= 0
            else (structure[index] if index < len(structure) else -1)
            for index in range(len(upper.frets))
        ]
        hand_base = list(held_frets)
    free = [
        index
        for index in bass.BASS_STRING_INDICES
        if not (0 <= index < len(sounding) and sounding[index] >= 0)
    ]
    if not free:
        return "no free string"
    below = []
    for string_index in free:
        open_midi = STANDARD_TUNING[string_index].midi_note()
        first = (pitch_class - open_midi) % 12
        for fret in range(first, 19, 12):
            if open_midi + fret >= lowest:
                continue
            below.append((string_index, fret))
    if not below:
        return "no octave below"
    for string_index, fret in below:
        hand = list(hand_base)
        hand[string_index] = fret
        if can_fret(hand):
            return "reachable"
    return "fifth fret"


def _refusals() -> List[Tuple[Any, int, Any, str]]:
    """Every refusal over the committed heads and the four thumb rows.

    Each entry is `(upper voicing, wanted pitch class, held shape, chord name)`. The chord is
    captured through `_attach_bass` rather than read off the step afterwards because the
    walk's *pitch* is the only thing the fourth lever is allowed to change, so the chord's
    tones have to be known at the instant of the refusal.
    """
    captured: List[Tuple[Any, int, Any, str]] = []
    context: Dict[str, Any] = {"chord": ""}
    original_attach = movement._attach_bass
    original_place = bass._place_bass

    def attach(step: Any, note: Any, arrangements: Any) -> None:
        context["chord"] = step.chord
        original_attach(step, note, arrangements)

    def place(
        upper: Any, pitch_class: Any, previous_bass: Any = None, held: Any = None
    ) -> Any:
        placed = original_place(upper, pitch_class, previous_bass, held)
        if placed is None:
            captured.append((upper, pitch_class, held, context["chord"]))
        return placed

    # Plain assignment rather than `setattr`: a module attribute is not a classmethod, so the
    # pyright/B010 clash of AGENTS.md trap 4 does not arise here. Both wrappers take `Any`
    # for the same reason — they are seams, not reimplementations.
    movement._attach_bass = attach
    bass._place_bass = place
    movement._place_bass = place
    try:
        for path in HEADS:
            for texture, row in THUMB_ROWS:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    headxml.arrange_xml_head(path, texture=texture, bass=row)
    finally:
        movement._attach_bass = original_attach
        bass._place_bass = original_place
        movement._place_bass = original_place
    return captured


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


class TestTheStatedNumbersAreTheMeasuredOnes(unittest.TestCase):
    """Item 1's and item 2's figures, re-taken and compared with what the document says."""

    @classmethod
    def setUpClass(cls) -> None:
        # Once: the refusals are a pass over every head across four rows.
        cls.added = _union_added()
        cls.refusals = _refusals()

    def test_item_one_states_the_measured_union_delta(self) -> None:
        """87 steps across six of the eight heads, and every per-head figure named."""
        total = sum(self.added.values())
        contributing = len([count for count in self.added.values() if count])
        self.assertEqual((total, contributing), (87, 6), self.added)
        text = _doc()
        self.assertIn(f"**{total} steps** were added across six of the eight", text)
        for name, count in sorted(self.added.items()):
            if count:
                self.assertIn(f"`{Path(name).stem}` {count}", text)

    def test_item_one_names_the_two_heads_with_no_gap_bar(self) -> None:
        """The zeros are the claim that this is a fix rather than a behaviour change."""
        silent = sorted(Path(name).stem for name, count in self.added.items() if not count)
        self.assertEqual(silent, ["but_not_for_me", "tenor_madness"])
        for stem in silent:
            self.assertIn(stem, _doc())

    def test_item_two_states_the_measured_refusal_count_and_causes(self) -> None:
        """161 refusals on the four thumb rows, split 0 / 160 / 1 down `_place_bass`'s three."""
        counted = Counter(_cause(upper, pc, held) for upper, pc, held, _c in self.refusals)
        split = {
            name: counted.get(name, 0)
            for name in ("no free string", "no octave below", "fifth fret")
        }
        self.assertEqual(len(self.refusals), 161)
        self.assertEqual(
            split, {"no free string": 0, "no octave below": 160, "fifth fret": 1}
        )
        text = _doc()
        self.assertIn(f"refusals number **{len(self.refusals)}** today", text)
        self.assertIn("| no free string | **0** |", text)
        self.assertIn(
            f"| **no octave of the walk's pitch below the shape**"
            f" | **{split['no octave below']}** |",
            text,
        )
        self.assertIn(f"| five frets for four fingers | **{split['fifth fret']}** |", text)

    def test_item_two_states_the_measured_doubling_split(self) -> None:
        """How many refusals wanted the pitch class the shape already sounds underneath."""
        doubling = Counter(
            "doubling" if min(upper.midi_notes()) % 12 == pc else "absent"
            for upper, pc, _held, _c in self.refusals
        )
        self.assertEqual(dict(doubling), {"doubling": 92, "absent": 69})
        self.assertIn(f"{doubling['doubling']} of the {len(self.refusals)} are a", _doc())

    def test_item_two_states_the_measured_walk_pitch_lever(self) -> None:
        """The fourth lever: another pitch under the chosen shape, and whether it is a tone.

        The one lever that costs the cost tuple nothing, so its reach is the whole argument —
        and the shape-level retry is not measurable without the candidate pool, which is why
        the document marks those two figures *not re-measured* instead of restating them.
        """
        by_any = by_tone = by_none = 0
        for upper, _pc, held, chord in self.refusals:
            _root, quality = ChordParser.parse_chord_name(chord)
            tones = (
                set(ChordParser.get_chord_tones(quality or "", chord)) if chord else set()
            )
            placeable = [
                pitch
                for pitch in range(12)
                if bass._place_bass(upper, pitch, None, held) is not None
            ]
            if not placeable:
                by_none += 1
            else:
                by_any += 1
                if any(pitch in tones for pitch in placeable):
                    by_tone += 1
        self.assertEqual((by_any, by_tone, by_none), (93, 64, 68))
        text = _doc()
        self.assertIn(f"reaches **{by_any} of the {len(self.refusals)}**", text)
        self.assertIn(f"only **{by_tone}** of those", text)
        self.assertIn(f"**{by_none} of the {len(self.refusals)}** cannot be", text)


class TestTheReproductionSnippetsRun(unittest.TestCase):
    """Every snippet in the `Reproducing` block runs, and prints what it says it prints.

    The failure this catches is the one that was actually in the file: a snippet that ran
    happily and printed something other than its own comment (`36 of 37` against a head that
    plays 66 bars), and a recipe naming `steps._place_bass`, which is a module that has no
    such function. Neither is visible to a reader and neither failed anything.
    """

    #: Every line the block's own comments claim, in the order the block lists them.
    EXPECTED: Tuple[str, ...] = (
        "bars arranged: 66 of 66",
        "bar 32 (no notes at all): [(1.0, 'Am7'), (2.0, 'D9')]",
        "steps: 16",
        "steps: 0",
        "total added: 87",
        "bar 2 present: False",
        "bars walked: [1, 3]",
    )

    @classmethod
    def setUpClass(cls) -> None:
        block = re.search(r"```bash\n(.*?)```", _doc(), re.S)
        assert block is not None, "open-issues.md has no fenced bash block"
        cls.snippets = re.findall(r'python -c "(.*?)"\n', block.group(1), re.S)
        cls.outputs = []
        for snippet in cls.snippets:
            completed = subprocess.run(
                [sys.executable, "-c", snippet],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
            cls.outputs.append(completed.stdout)

    def test_the_block_still_holds_every_snippet(self) -> None:
        self.assertEqual(len(self.snippets), 6)

    def test_each_snippet_prints_what_its_comment_claims(self) -> None:
        joined = "\n".join(self.outputs)
        for expected in self.EXPECTED:
            self.assertIn(expected, joined, joined)
