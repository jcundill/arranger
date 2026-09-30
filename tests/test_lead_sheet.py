"""Tests for the Weimar Jazz Database lead-sheet exporter.

Everything here is guarded by ``skipUnless`` on the presence of the 42 MB
``wjazzd.db`` (ignored via ``.gitignore``), so the suite still passes without it.

The expectations are the ground-truth rows of ``docs/history/corpus-plan.md`` section 1.3.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from lead_sheet import NO_CHORD, export_wjd_leadsheet, midi_to_note_name

DB_PATH = Path(__file__).resolve().parent.parent / "wjazzd.db"
HAS_DB = DB_PATH.is_file()


@unittest.skipUnless(HAS_DB, "wjazzd.db not present")
class TestLeadSheet(unittest.TestCase):
    """Tests for export_wjd_leadsheet against the real database."""

    def test_metadata_uses_avgtempo(self):
        """Should read the tempo from 'avgtempo', the real column name."""
        sheet = export_wjd_leadsheet(str(DB_PATH), 1)
        self.assertEqual(sheet["title"], "Anthropology")
        self.assertEqual(sheet["performer"], "Art Pepper")
        self.assertEqual(sheet["key"], "Bb-maj")
        self.assertEqual(sheet["time_signature"], "4/4")
        self.assertAlmostEqual(float(sheet["tempo"]), 218.8, places=1)

    def test_forward_fill_ground_truth(self):
        """Should bind each note to the last chord at or before its (bar, beat).

        These are the verified rows of docs/history/corpus-plan.md section 1.3.
        """
        sheet = export_wjd_leadsheet(str(DB_PATH), 1)
        by_bar = {m["measure"]: m for m in sheet["measures"]}
        # Bar 0: only Bb6 is in force for the whole bar.
        self.assertEqual({n["active_chord"] for n in by_bar[0]["melody"]}, {"Bb6"})
        # Bar 3 beat 3 is G-7; every note in the bar is at or after it.
        self.assertEqual({n["active_chord"] for n in by_bar[3]["melody"]}, {"G-7"})
        # Bar 4 changes mid-bar: C-7 at beat 1, F7 from beat 3.
        self.assertEqual(
            [n["active_chord"] for n in by_bar[4]["melody"]][:2], ["C-7", "C-7"]
        )
        self.assertEqual(by_bar[4]["melody"][3]["active_chord"], "F7")

    def test_chords_carry_the_beat_they_start_on(self):
        """Should keep chord onset beats, not a flat list of symbols.

        A flat list cannot say which note falls under which chord, and cannot
        distinguish a note under 'NC' from one under a real chord.
        """
        sheet = export_wjd_leadsheet(str(DB_PATH), 1)
        by_bar = {m["measure"]: m for m in sheet["measures"]}
        self.assertEqual(
            by_bar[1]["chords"],
            [
                {"beat": 1, "symbol": "Bb6", "is_no_chord": False},
                {"beat": 3, "symbol": "G7", "is_no_chord": False},
            ],
        )

    def test_chord_only_measures_are_kept(self):
        """Should emit a measure that has harmony but no melody note.

        Bars 2 and 8 of melid 1 carry chords but no note at all; collecting
        chords from the note rows would drop the harmony there.
        """
        sheet = export_wjd_leadsheet(str(DB_PATH), 1)
        by_bar = {m["measure"]: m for m in sheet["measures"]}
        self.assertEqual(by_bar[2]["melody"], [])
        self.assertEqual([c["symbol"] for c in by_bar[2]["chords"]], ["C-7", "F7"])

    def test_no_chord_is_flagged(self):
        """Should mark an 'NC' bar and forward-fill NC onto its notes."""
        sheet = export_wjd_leadsheet(str(DB_PATH), 218)
        by_bar = {m["measure"]: m for m in sheet["measures"]}
        # Blue Train's only NC bar is bar 0, outside its A1 block (bars 7-86).
        self.assertEqual(by_bar[0]["chords"][0]["symbol"], NO_CHORD)
        self.assertTrue(by_bar[0]["chords"][0]["is_no_chord"])
        self.assertEqual({n["active_chord"] for n in by_bar[0]["melody"]}, {NO_CHORD})
        # The next bar is harmonised, and NC does not leak past it.
        self.assertEqual(by_bar[1]["chords"][0]["symbol"], "Eb7")

    def test_negative_bars_lead_the_sheet(self):
        """Should order anacrusis material ahead of bar 0.

        149 transcriptions have negative-bar notes, to bar -31; melid 266 (Lee
        Konitz on All the Things You Are) reaches back to bar -12.
        """
        sheet = export_wjd_leadsheet(str(DB_PATH), 266)
        bars = [m["measure"] for m in sheet["measures"]]
        self.assertEqual(min(bars), -12)
        self.assertEqual(bars, sorted(bars))
        # The fill resolves real chords across the pickups.
        self.assertEqual(sheet["measures"][0]["chords"][0]["symbol"], "C7")

    def test_bars_range_accepts_negative_bounds(self):
        """Should select a half-open range, including negative anacrusis bars."""
        sheet = export_wjd_leadsheet(str(DB_PATH), 266, bars=(-4, 8))
        self.assertEqual([m["measure"] for m in sheet["measures"]], list(range(-4, 8)))
        # The upper bound is exclusive, so bar 8 is absent.
        self.assertNotIn(8, [m["measure"] for m in sheet["measures"]])

    def test_bars_range_filters_chords_as_well_as_notes(self):
        """Should drop out-of-range chord onsets, not just out-of-range notes."""
        sheet = export_wjd_leadsheet(str(DB_PATH), 1, bars=(0, 4))
        self.assertEqual([m["measure"] for m in sheet["measures"]], [0, 1, 2, 3])
        for measure in sheet["measures"]:
            for chord in measure["chords"]:
                self.assertLess(chord["beat"], 5)

    def test_unknown_melid_raises(self):
        """Should raise ValueError rather than returning an empty sheet."""
        with self.assertRaises(ValueError):
            export_wjd_leadsheet(str(DB_PATH), 999999)

    def test_json_export_round_trips(self):
        """Should write a JSON file that reloads to the same structure."""
        sheet = export_wjd_leadsheet(str(DB_PATH), 1, bars=(0, 4))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sheet.json")
            export_wjd_leadsheet(str(DB_PATH), 1, output_json_path=path, bars=(0, 4))
            with open(path, encoding="utf-8") as f:
                reloaded = json.load(f)
        self.assertEqual(reloaded, sheet)


class TestMidiToNoteName(unittest.TestCase):
    """Tests for the MIDI-to-spelling conversion, which needs no database."""

    def test_octave_boundaries(self):
        """Should compute the octave as (midi // 12) - 1, i.e. C4 is MIDI 60.

        59 -> B3 and 94 -> Bb6 are the two ends of the library's melody window
        (docs/history/corpus-plan.md section 1.4); the 16th fret of the high E string is Bb5,
        MIDI 82.
        """
        self.assertEqual(midi_to_note_name(60), "C4")
        self.assertEqual(midi_to_note_name(59), "B3")
        self.assertEqual(midi_to_note_name(82), "Bb5")
        self.assertEqual(midi_to_note_name(94), "Bb6")
        self.assertEqual(midi_to_note_name(36), "C2")
        self.assertEqual(midi_to_note_name(96), "C7")
        self.assertEqual(midi_to_note_name(97), "Db7")

    def test_rounds_float_pitches(self):
        """Should round the REAL 'pitch' column, which is stored as a float."""
        self.assertEqual(midi_to_note_name(60.4), "C4")
        self.assertEqual(midi_to_note_name(59.6), "C4")
        self.assertEqual(midi_to_note_name(59.4), "B3")


if __name__ == "__main__":
    unittest.main()
