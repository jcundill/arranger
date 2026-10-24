"""A chord name the tree spells has to be one the tables can read.

`parse_symbol` reads the quality **out of the name** rather than taking it beside the
name, so a spelling no table carries does not refuse the bar. It drops the chord,
leaves the tune alone, and says so only in the annotation: the arrangement still builds,
every count still adds up, and nothing fails. `Dm(maj7)` is the measured case - the
notation's parenthesis form of a minor-major seventh went unread, and the bar it sits in
lost its chord silently rather than reporting anything.

So the spellings the committed fixtures and the suite's shared progressions use are held
to the tables here. It is a fact about the tree's own chord spellings rather than about
one arrangement, which is why it is in the meta half; `meta_fixture_corpus` owns what
the fixtures *are*, and this owns what they *say*.

`DELIBERATELY_UNREADABLE` names the spellings that are unreadable on purpose, so a third
one is a decision rather than a drift - and it is re-earned rather than trusted, because
an entry left behind after the tables learned its spelling would hide the next fixture
that writes it.
"""

from __future__ import annotations

import os
import unittest
from typing import List, Optional

from arranger.chords import parse_symbol
from arranger.grip_tables import TONE_PRIORITY
from headxml import load_musicxml
from tests.support import DATA, MAJOR_CADENCE, MINOR_CADENCE

#: The spellings that are unreadable **on purpose**, with the reason each one exists.
#: A readable root under a suffix no table has is the only way to reach the "the chord
#: symbol could not be read" clause: a name with no root raises instead, and `NC` asks
#: for no chord. `test_palette` pins that clause with this one.
DELIBERATELY_UNREADABLE = {
    "Czz",
}


def committed_heads() -> List[str]:
    """Every MusicXML fixture in `tests/data`, read from the directory.

    Read rather than listed, so a fixture added for another concern is a spelling the
    tables have to know without anyone remembering to add it here.
    """
    paths = sorted(
        os.path.join(DATA, name)
        for name in os.listdir(DATA)
        if name.endswith((".musicxml", ".mxl"))
    )
    if not paths:
        raise AssertionError(f"no MusicXML fixtures under {DATA}")
    return paths


def unreadable_reason(name: str) -> Optional[str]:
    """Why `name` is not a chord this library can read, or `None` when it is.

    A reason rather than a bool so the caller can put the spelling in its own failure
    message, which is the whole value of the check: the report names the symbol, not
    the file it happens to live in.
    """
    symbol = parse_symbol(name)
    if symbol is None:
        return "the name asks for no chord"
    if symbol.quality not in TONE_PRIORITY:
        return f"the suffix is no quality any table carries ({symbol.quality!r})"
    return None


class TestEveryFixtureChordIsReadable(unittest.TestCase):
    """The committed corpus spells chords the tables know."""

    def test_the_importer_translates_every_harmony(self):
        """A `<harmony>` the kind table cannot reach is counted, never guessed.

        `Head.unmapped` is the importer's own report of the symbols it could not
        translate, so an empty one is the statement that every chord in every committed
        fixture got through - the measure that says a fixture has not quietly become a
        file whose chords are dropped.
        """
        for path in committed_heads():
            with self.subTest(fixture=os.path.basename(path)):
                self.assertEqual(load_musicxml(path).unmapped, ())

    def test_every_symbol_a_fixture_spells_reads(self):
        """Every symbol the corpus carries resolves to a quality a table has.

        `Head.chords` is the chord **timeline**, so this covers a `<harmony>` that
        precedes no note as well as one a note records - the two are the same fact read
        two ways, and a bar with no note in it is exactly where a dropped chord would
        never be noticed.
        """
        for path in committed_heads():
            head = load_musicxml(path)
            for change in head.chords:
                if change.chord in DELIBERATELY_UNREADABLE:
                    continue
                with self.subTest(fixture=os.path.basename(path), chord=change.chord):
                    self.assertIsNone(unreadable_reason(change.chord))


class TestEverySharedProgressionIsReadable(unittest.TestCase):
    """The suite's own progressions are spelled readably too.

    These are the fixtures the published tabs are asserted against, so a spelling that
    stopped reading here would move a pinned tab rather than fail a test - which is how
    the parenthesis form of a minor-major seventh cost a bar its chord.
    """

    def test_the_published_cadences_spell_readable_chords(self):
        for progression in (MINOR_CADENCE, MAJOR_CADENCE):
            for _melody, name in progression:
                with self.subTest(chord=name):
                    self.assertIsNone(unreadable_reason(name))

    def test_the_unreadable_list_is_still_needed(self):
        """An allow-listed name that now reads is a stale entry, not a permission.

        This is also the witness that the check **works**: `unreadable_reason` is called
        with a name it must report on, so a checker that had gone quiet - returning
        `None` for everything, which would make every assertion above pass - fails here.
        The second job is that the list has to keep earning its place: an entry left
        behind after the tables learned its spelling would hide the next fixture that
        writes it.
        """
        for name in DELIBERATELY_UNREADABLE:
            with self.subTest(chord=name):
                self.assertIsNotNone(
                    unreadable_reason(name),
                    f"{name!r} reads now - remove it from DELIBERATELY_UNREADABLE",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
