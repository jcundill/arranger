"""Tests for the Weimar Jazz Database loader.

Every test that needs the 42 MB database is skipped when it is absent, so the
suite still passes on a fresh clone. Tests that need no database (the notation
table, the record types, the selector parser) always run.
"""

import contextlib
import io
import unittest

from arranger import (
    GRIP_STRING_SETS,
    NO_CHORD,
    ChordParser,
    Note,
)
from wjazzd import (
    DEFAULT_DB,
    SECTION_TYPES,
    WEIMAR_QUALITY_ALIASES,
    NoteEvent,
    Section,
    Solo,
    list_sections,
    list_solos,
    load_section,
    load_solo,
    matching_sections,
    parse_section_selector,
    parse_weimar_chord,
    arrange_head,
    bass_cost,
    build_skeleton,
    corpus_cli,
    parse_bar_range,
    promote_slash_chord,
    bass_pitch_class,
    _arrange_step_with_bass,
    select_head,
    skeleton,
    skeleton_slots,
    SKELETON_STRATEGIES,
    _is_transposed_repeat,
    _seed_span,
)

HAS_DB = DEFAULT_DB.is_file()
requires_db = unittest.skipUnless(HAS_DB, "wjazzd.db not present")

class TestWeimarChordParsing(unittest.TestCase):
    """Weimar notation translated into the library's qualities."""

    def test_plain_symbols(self):
        """Roots and simple suffixes resolve to (root, quality, no bass)."""
        self.assertEqual(parse_weimar_chord("Bb6"), ("Bb", "6", None))
        self.assertEqual(parse_weimar_chord("Eb7"), ("Eb", "7", None))
        self.assertEqual(parse_weimar_chord("C-7"), ("C", "m7", None))
        self.assertEqual(parse_weimar_chord("Fj7"), ("F", "maj7", None))
        self.assertEqual(parse_weimar_chord("Dm7b5"), ("D", "m7b5", None))

    def test_empty_suffix_is_a_major_triad(self):
        """In Weimar notation a bare "C" is a major triad, not an unknown chord."""
        self.assertEqual(parse_weimar_chord("C"), ("C", "maj", None))

    def test_dash_suffix_is_a_minor_triad(self):
        """"C-" is a minor triad."""
        self.assertEqual(parse_weimar_chord("C-"), ("C", "m", None))

    def test_no_chord_symbol(self):
        """NC is melody with no harmony: no root, no quality."""
        self.assertEqual(parse_weimar_chord("NC"), (None, None, None))

    def test_empty_symbol(self):
        """An empty chord cell (the 101,781 empty `beats` rows) is not a chord."""
        self.assertEqual(parse_weimar_chord(""), (None, None, None))

    def test_slash_chords_are_split_before_anything_else(self):
        """The bass is stripped, which is what keeps the quality lookup working."""
        self.assertEqual(parse_weimar_chord("A-/G"), ("A", "m", "G"))
        self.assertEqual(parse_weimar_chord("C7/E"), ("C", "7", "E"))
        self.assertEqual(parse_weimar_chord("F-7/Ab"), ("F", "m7", "Ab"))

    def test_sharp_roots_and_basses(self):
        """Enharmonic spellings in the database are preserved verbatim."""
        self.assertEqual(parse_weimar_chord("G#7/D#"), ("G#", "7", "D#"))

    def test_unknown_suffix_is_none_and_never_guessed(self):
        """An untranslatable suffix reports None instead of a nearby quality."""
        root, quality, bass = parse_weimar_chord("Czz9")
        self.assertEqual(root, "C")
        self.assertIsNone(quality)
        self.assertIsNone(bass)

    def test_every_table_entry_resolves_to_a_voicable_quality(self):
        """No table entry may name a quality the library cannot voice."""
        for suffix, expected in WEIMAR_QUALITY_ALIASES.items():
            quality = parse_weimar_chord(f"C{suffix}")[1]
            self.assertIsNotNone(quality, suffix)
            self.assertEqual(quality, expected, suffix)
            self.assertIn(quality, ChordParser.CHORD_TONES_FROM_ROOT, suffix)
            self.assertEqual(ChordParser.canonical_quality(quality), quality, suffix)

class TestSectionSelector(unittest.TestCase):
    """The "type:value" selector parser, which needs no database."""

    def test_simple_selectors(self):
        """Type and value are split on the first colon and upper-cased."""
        self.assertEqual(parse_section_selector("form:A1"), ("FORM", "A1"))
        self.assertEqual(parse_section_selector("chorus:1"), ("CHORUS", "1"))
        self.assertEqual(parse_section_selector("phrase:-1"), ("PHRASE", "-1"))

    def test_type_is_case_insensitive(self):
        """FORM and form name the same thing."""
        self.assertEqual(parse_section_selector("FORM:A1"), ("FORM", "A1"))
        self.assertEqual(parse_section_selector("Form:A1"), ("FORM", "A1"))

    def test_glob_value_is_preserved(self):
        """A `*` value is a pattern for matching_sections, not a literal."""
        self.assertEqual(parse_section_selector("form:A*"), ("FORM", "A*"))

    def test_unknown_type_raises(self):
        """A mistyped kind must not read as "this solo has no such section"."""
        with self.assertRaises(ValueError):
            parse_section_selector("bogus:A1")

    def test_missing_colon_raises(self):
        """A selector without a type is a usage error."""
        with self.assertRaises(ValueError):
            parse_section_selector("A1")

    def test_missing_value_raises(self):
        """An empty value matches nothing and is almost always a typo."""
        with self.assertRaises(ValueError):
            parse_section_selector("form:")

    def test_section_types_are_the_five_the_database_uses(self):
        """The schema has five span kinds; the validator must match."""
        self.assertEqual(SECTION_TYPES, ("CHORD", "IDEA", "PHRASE", "FORM", "CHORUS"))


class TestSectionRecord(unittest.TestCase):
    """The Section dataclass, including the degenerate zero-length span."""

    def test_length_and_membership(self):
        """Spans are half-open [start, end)."""
        section = Section(melid=1, type="FORM", start=7, end=86, value="A1")
        self.assertEqual(section.length, 79)
        self.assertTrue(section.contains_bar(7))
        self.assertTrue(section.contains_bar(85))
        self.assertFalse(section.contains_bar(86))
        self.assertFalse(section.contains_bar(6))

    def test_zero_length_span_selects_nothing(self):
        """melid 44's (114, 114) span is legal and empty, not an error."""
        section = Section(melid=44, type="FORM", start=114, end=114, value="A1")
        self.assertEqual(section.length, 0)
        self.assertFalse(section.contains_bar(114))

    def test_negative_bars_are_ordinary(self):
        """The anacrusis is numbered with negative bars."""
        section = Section(melid=266, type="FORM", start=-12, end=0, value="I1")
        self.assertEqual(section.length, 12)
        self.assertTrue(section.contains_bar(-4))


class TestNoteEventRecord(unittest.TestCase):
    """NoteEvent's derived position, which is what the skeletons index on."""

    def test_beat_position_is_absolute(self):
        """beat is within its bar, so the absolute position adds the bar."""
        self.assertEqual(NoteEvent(bar=4, beat=3.0, pitch=60, duration=1.0).beat_position, 6.0)

    def test_beat_position_handles_negative_bars(self):
        """A pickup note orders correctly without a special case."""
        self.assertEqual(NoteEvent(bar=-2, beat=3.0, pitch=60, duration=1.0).beat_position, 0.0)

    def test_no_chord_flag(self):
        """The NC marker is recognised on the note."""
        self.assertTrue(NoteEvent(bar=0, beat=1.0, pitch=60, duration=1.0, chord="NC").is_no_chord)
        self.assertFalse(NoteEvent(bar=0, beat=1.0, pitch=60, duration=1.0, chord="Eb7").is_no_chord)

class TestSoloRecord(unittest.TestCase):
    """Solo's bar range and bar filtering, no database needed."""

    def setUp(self):
        self.solo = Solo(
            melid=1,
            notes=[
                NoteEvent(bar=-2, beat=3.0, pitch=60, duration=1.0, chord="C7"),
                NoteEvent(bar=0, beat=1.0, pitch=62, duration=1.0, chord="F7"),
                NoteEvent(bar=3, beat=1.0, pitch=64, duration=1.0, chord="G-7"),
            ],
        )

    def test_bars_covers_negative_starts(self):
        """The range is (first, last + 1) and may begin below zero."""
        self.assertEqual(self.solo.bars, (-2, 4))

    def test_empty_solo_has_an_empty_range(self):
        """No notes means no range, rather than an exception."""
        self.assertEqual(Solo(melid=1).bars, (0, 0))

    def test_notes_in_bars_is_half_open(self):
        """hi is exclusive, so --bars 0-3 selects bars 0, 1 and 2."""
        self.assertEqual([n.bar for n in self.solo.notes_in_bars(0, 3)], [0])

    def test_notes_in_bars_accepts_negative_bounds(self):
        """Pickup material is selectable, which --bars -4-8 needs."""
        self.assertEqual([n.bar for n in self.solo.notes_in_bars(-4, 1)], [-2, 0])

    def test_notes_in_bars_defaults_to_everything(self):
        """Omitting both bounds returns the whole solo."""
        self.assertEqual(len(self.solo.notes_in_bars()), 3)

    def test_chords_collapses_repeats(self):
        """One entry per change, not one per note."""
        solo = Solo(
            melid=1,
            notes=[
                NoteEvent(bar=0, beat=1.0, pitch=60, duration=1.0, chord="C7"),
                NoteEvent(bar=0, beat=2.0, pitch=62, duration=1.0, chord="C7"),
                NoteEvent(bar=1, beat=1.0, pitch=64, duration=1.0, chord="F7"),
            ],
        )
        self.assertEqual(solo.chords(), [(0, "C7"), (1, "F7")])


@requires_db
class TestDatabaseContents(unittest.TestCase):
    """The real schema, checked against the figures in CORPUS_PLAN.md."""

    def test_the_database_has_456_transcriptions(self):
        """list_solos returns the whole solo_info table."""
        self.assertEqual(len(list_solos()), 456)

    def test_blue_train_metadata(self):
        """melid 218 is Coltrane's Blue Train in Eb."""
        solo = next(s for s in list_solos() if s.melid == 218)
        self.assertEqual(solo.title, "Blue Train")
        self.assertEqual(solo.performer, "John Coltrane")
        self.assertEqual(solo.key, "Eb-maj")

    def test_section_kinds_match_the_plan(self):
        """All five span kinds are valid filters for this schema."""
        kinds = {s.type for s in list_sections(218)}
        self.assertTrue(kinds.issubset(set(SECTION_TYPES)))

    def test_unknown_section_type_raises(self):
        """list_sections validates its filter like the selector does."""
        with self.assertRaises(ValueError):
            list_sections(218, type="NOT_A_KIND")

    def test_glob_selector_matches_every_a_block(self):
        """form:A* finds A1 and A2 alike; a bare form:A1 finds only A1.

        melid 1 (Anthropology) is an AABA form stated four times, so it has both
        A1 and A2 spans and the glob is a genuine widening.
        """
        globbed = matching_sections(1, "form:A*")
        exact = matching_sections(1, "form:A1")
        self.assertTrue(all(s.value.startswith("A") for s in globbed))
        self.assertEqual({s.value for s in globbed}, {"A1", "A2", "A3"})
        self.assertEqual({s.value for s in exact}, {"A1"})
        self.assertGreater(len(globbed), len(exact))

    def test_unknown_melid_raises(self):
        """A typo is not silently an empty transcription."""
        with self.assertRaises(ValueError):
            load_solo(999999)

    def test_missing_database_reports_clearly(self):
        """A wrong path explains what to download."""
        with self.assertRaises(FileNotFoundError):
            load_solo(218, db_path="/nonexistent/wjazzd.db")

@requires_db
class TestChordForwardFill(unittest.TestCase):
    """Each note's chord is reconstructed by a forward fill over `beats`."""

    @classmethod
    def setUpClass(cls):
        cls.solo_1 = load_solo(1)
        cls.solo_218 = load_solo(218)
        cls.solo_266 = load_solo(266)

    def chords_at(self, solo, bar, beat):
        """The chords of every note at one (bar, beat); several may share it."""
        return {n.chord for n in solo.notes if n.bar == bar and n.beat == beat}

    def test_ground_truth_melid_1(self):
        """The three checked positions in CORPUS_PLAN.md section 1.3."""
        self.assertEqual(self.chords_at(self.solo_1, 0, 1), {"Bb6"})
        self.assertEqual(self.chords_at(self.solo_1, 3, 3), {"G-7"})
        self.assertEqual(self.chords_at(self.solo_1, 4, 3), {"F7"})

    def test_ground_truth_melid_218(self):
        """Blue Train: bar 0 is NC, bar 1 Eb7, bar 8 C7."""
        self.assertEqual(self.chords_at(self.solo_218, 0, 2), {"NC"})
        self.assertEqual(self.chords_at(self.solo_218, 1, 1), {"Eb7"})
        self.assertEqual(self.chords_at(self.solo_218, 8, 2), {"C7"})

    def test_notes_inherit_the_chord_across_a_bar(self):
        """A note with no chord of its own still knows the active chord."""
        late = [n for n in self.solo_218.notes if n.bar == 3]
        self.assertTrue(late)
        self.assertTrue(all(n.chord for n in late))

    def test_negative_bars_resolve(self):
        """The anacrusis fill works: melid 266 reaches back to bar -12."""
        pickups = [n for n in self.solo_266.notes if n.bar < 0]
        self.assertTrue(pickups)
        self.assertTrue(all(n.chord for n in pickups))
        self.assertEqual(min(n.bar for n in self.solo_266.notes), -12)

    def test_qualities_translate_for_blue_train(self):
        """Every Blue Train chord maps to a quality the library can voice."""
        for _, chord in self.solo_218.chords():
            if chord == "NC":
                continue
            self.assertIsNotNone(parse_weimar_chord(chord)[1], chord)
        self.assertEqual(self.solo_218.unmapped_suffixes, {})


@requires_db
class TestLoadSection(unittest.TestCase):
    """load_section narrows a transcription to the spans a selector matches."""

    def test_notes_are_narrowed_to_the_span(self):
        """Only notes inside the selected bars are kept."""
        solo, sections = load_section(218, "form:I1")
        self.assertEqual(sections[0].value, "I1")
        self.assertTrue(solo.notes)
        self.assertTrue(all(s.contains_bar(n.bar) for s in sections for n in solo.notes))

    def test_metadata_survives_narrowing(self):
        """Narrowing drops notes, not the transcription's identity."""
        solo, _ = load_section(218, "form:I1")
        self.assertEqual(solo.melid, 218)
        self.assertEqual(solo.title, "Blue Train")

    def test_bars_narrows_further(self):
        """A bar range is a filter within the span, not a separate selector."""
        wide, _ = load_section(218, "form:A1")
        narrow, _ = load_section(218, "form:A1", bars=(10, 14))
        self.assertLess(len(narrow.notes), len(wide.notes))
        self.assertTrue(all(10 <= n.bar < 14 for n in narrow.notes))

    def test_unmatched_selector_raises(self):
        """Selecting a section the solo does not have is an error, not silence."""
        with self.assertRaises(ValueError):
            load_section(218, "chorus:99")

    def test_attya_head_chords_all_translate(self):
        """The ATTYA head (bars 1-8) uses only m7, 7 and maj7, in all four.

        Restricted to the head bars on purpose: the rest of the form modulates
        and brings in Bo7, which is outside what this asserts.
        """
        expected = {"m7", "7", "maj7"}
        for melid in (266, 328, 342, 451):
            solo = load_solo(melid)
            head = [n for n in solo.notes if 1 <= n.bar < 9]
            self.assertTrue(head, melid)
            for note in head:
                if note.chord in ("", "NC"):
                    continue
                self.assertIn(note.quality, expected, f"{melid} bar {note.bar} {note.chord}")


class TestSeedSpan(unittest.TestCase):
    """The A-block seed and its extension back over an intro, no database needed."""

    def test_no_a_block_returns_none(self):
        """A transcription with no A-form has no seed to search."""
        self.assertIsNone(_seed_span([Section(1, "FORM", 0, 8, "I1")]))

    def test_a_block_alone_is_the_seed(self):
        """With no preceding intro the seed starts at the A-block."""
        forms = [Section(1, "FORM", 0, 6, "I1"), Section(1, "FORM", 20, 60, "A1")]
        seed, lo, hi = _seed_span(forms)  # type: ignore[misc]
        self.assertEqual((lo, hi), (20, 60))
        self.assertEqual(seed.value, "A1")

    def test_seed_extends_back_over_a_contiguous_intro(self):
        """An I-block ending where the A-block starts is absorbed into the seed.

        This is the case a form-label-only design gets wrong: the head sits in the
        intro, so seeding from A1 alone would miss it entirely.
        """
        forms = [Section(1, "FORM", 0, 8, "I1"), Section(1, "FORM", 8, 44, "A1")]
        _, lo, _ = _seed_span(forms)  # type: ignore[misc]
        self.assertEqual(lo, 0)

    def test_a_distant_intro_does_not_swallow_the_head(self):
        """An I-block far from the A-block is a different section, not a prefix."""
        forms = [Section(1, "FORM", 0, 4, "I1"), Section(1, "FORM", 60, 100, "A1")]
        _, lo, _ = _seed_span(forms)  # type: ignore[misc]
        self.assertEqual(lo, 60)

    def test_only_i_and_a_forms_count(self):
        """A B-block adjacent to the A-block is not an intro."""
        forms = [Section(1, "FORM", 0, 8, "B1"), Section(1, "FORM", 8, 44, "A1")]
        _, lo, _ = _seed_span(forms)  # type: ignore[misc]
        self.assertEqual(lo, 8)


class TestTransposedRepeat(unittest.TestCase):
    """_is_transposed_repeat: the matching rule the head is cut with."""

    def grid(self, rows):
        """Builds a dense bar grid from [(bar, chords), ...].

        Bars between the first and last listed one are filled with None (an NC
        wildcard), matching what _bar_grid produces for a real span. A sparse
        grid would let a comparison see only one pair of chords, and a single
        pair can never violate the constant-interval rule.
        """
        listed = {bar: chords for bar, chords in rows}
        if not listed:
            return {}
        lo, hi = min(listed), max(listed)
        return {bar: tuple(listed[bar]) if bar in listed else None for bar in range(lo, hi + 1)}

    def test_identical_progression_matches(self):
        """The same chords in the same key repeat."""
        rows = [(bar, [("m7", 5)]) for bar in range(0, 17, 4)]
        self.assertTrue(_is_transposed_repeat(self.grid(rows), 0, 8, 17))

    def test_transposed_progression_matches(self):
        """A progression returning a tone higher is the same one.

        This is the case ATTYA depends on: its A section comes back a whole tone
        higher, so an exact-root comparison would never find the head.
        """
        rows = [(bar, [("m7", 5 + 2 * (bar // 4))]) for bar in range(0, 17, 4)]
        self.assertTrue(_is_transposed_repeat(self.grid(rows), 0, 8, 17))

    def test_different_qualities_do_not_match_without_tolerance(self):
        """A minor seventh and a dominant seventh are not the same statement.

        Checked at tolerance 0 because one differing chord *is* tolerated by
        default - that tolerance is what lets a dropped change through.
        """
        rows = [(bar, [("m7" if bar < 8 else "7", 5)]) for bar in range(0, 17, 4)]
        self.assertFalse(_is_transposed_repeat(self.grid(rows), 0, 8, 17, tolerance=0))

    def test_same_quality_different_interval_is_not_a_transposition(self):
        """A constant interval is required, not merely matching qualities.

        Without this a blues head - nearly all dominant sevenths - would match
        itself at every offset, each chord being allowed its own shift.
        """
        rows = [(bar, [("7", bar % 3)]) for bar in range(0, 17)]
        self.assertFalse(_is_transposed_repeat(self.grid(rows), 0, 4, 17))

    def test_a_constant_interval_is_enough_however_large(self):
        """The rule allows any transposition, not just close keys."""
        rows = [(bar, [("m7", (5 + 6 * (bar // 4)) % 12)]) for bar in range(0, 17, 4)]
        self.assertTrue(_is_transposed_repeat(self.grid(rows), 0, 8, 17))

    def test_one_dropped_change_is_tolerated(self):
        """Transcriptions omit changes; a single difference still matches."""
        rows = [(bar, [("m7" if bar != 9 else "maj7", 7)]) for bar in range(0, 17, 4)]
        self.assertTrue(_is_transposed_repeat(self.grid(rows), 0, 8, 17))

    def test_two_dropped_changes_are_not(self):
        """Two differences also match unrelated progressions, so they are refused."""
        rows = [(bar, [("m7" if bar < 8 else "maj7", 7)]) for bar in range(0, 16, 2)]
        self.assertFalse(_is_transposed_repeat(self.grid(rows), 0, 8, 17))

    def test_a_bar_with_two_chords_keeps_both(self):
        """Sims's ATTYA puts D-7 and G7 both in bar 6; neither may be lost."""
        rows = [(bar, [("m7", 2), ("7", 9)] if bar < 8 else [("m7", 4), ("7", 11)])
                for bar in range(0, 17, 8)]
        self.assertTrue(_is_transposed_repeat(self.grid(rows), 0, 8, 17))

    def test_a_bar_with_a_missing_chord_is_a_dropped_change(self):
        """One bar holding two chords against one holding one is a difference.

        Checked at tolerance 0, because a single dropped chord is exactly what
        the default tolerance of 1 exists to absorb.
        """
        rows = [(0, [("m7", 2), ("7", 9)]), (8, [("m7", 4)]), (16, [])]
        self.assertFalse(_is_transposed_repeat(self.grid(rows), 0, 8, 17, tolerance=0))
        self.assertTrue(_is_transposed_repeat(self.grid(rows), 0, 8, 17))

    def test_a_span_too_short_is_not_a_repeat(self):
        """The restatement must lie inside the span being searched."""
        self.assertFalse(_is_transposed_repeat(self.grid([(0, [("m7", 5)]), (8, [("m7", 7)])]), 0, 8, 9))

    def test_no_chord_bars_do_not_disprove_a_repeat(self):
        """NC bars are wildcards, so an unaccompanied intro cannot veto a match."""
        rows = [(0, []), (1, [("m7", 5)]), (8, []), (9, [("m7", 7)])]
        self.assertTrue(_is_transposed_repeat(self.grid(rows), 0, 2, 17))


@requires_db
class TestSelectHead(unittest.TestCase):
    """select_head: the head found on the chord progression, not the form label."""

    def test_blue_train_head_is_one_blues_statement(self):
        """melid 218 yields the 12-bar head, not the 79-bar A1 block.

        The A1 label spans bars 7-86 - six and a half statements of the changes -
        so a form-label selector returns a form cycle rather than the head.
        """
        head = select_head(218)
        assert head is not None
        self.assertEqual(head.start, 1)
        self.assertEqual(head.length, 12)
        self.assertEqual(head.anchor_chords[0], "Eb7")

    def test_head_is_not_the_form_a1_span(self):
        """The regression that the original form-label design would have failed."""
        head = select_head(218)
        assert head is not None
        a1 = [s for s in list_sections(218, "FORM") if s.value == "A1"][0]
        self.assertNotEqual((head.start, head.end), (a1.start, a1.end))
        self.assertLess(head.length, a1.length)

    def test_attya_head_is_found_inside_the_intro(self):
        """Konitz's and Metheny's heads are the 8 bars before FORM A1 begins.

        The plan's validation case: `FORM A1` starts at bars 78 and 15
        respectively, while the head is at bars 1-8 in both.
        """
        for melid, a1_start in ((266, 78), (342, 15)):
            head = select_head(melid)
            assert head is not None, melid
            self.assertEqual((head.start, head.length), (1, 8), melid)
            self.assertLess(head.end, a1_start, melid)

    def test_attya_head_progression_is_the_canonical_a_section(self):
        """The anchor chords are ATTYA's A1, in the database's own spelling."""
        head = select_head(342)
        assert head is not None
        self.assertEqual(
            list(head.anchor_chords[:6]), ["F-7", "Bb-7", "Eb7", "Abj7", "Dbj7", "G7"]
        )

    def test_trim_is_modulo_transposition(self):
        """The head is found even though its return is in a new key.

        ATTYA's A section comes back a whole tone higher, so a selector comparing
        absolute roots would not find the repeat at all.
        """
        head = select_head(266)
        assert head is not None
        self.assertEqual(head.length, 8)

    def test_no_a_form_returns_none(self):
        """melid 6 is the one transcription in 456 with no A-form."""
        self.assertIsNone(select_head(6))

    def test_head_is_not_assumed_to_start_at_bar_zero(self):
        """A head may open with a pickup, so the selector must not assume bar 0."""
        head = select_head(218)
        assert head is not None
        self.assertEqual(head.start, 1)

    def test_degenerate_a_block_is_reported_not_crashed_on(self):
        """A block yielding no usable repeat is flagged rather than raising."""
        head = select_head(44)
        assert head is not None
        self.assertTrue(head.degraded)
        self.assertIn("no repeated progression", head.note)

    def test_describe_reports_the_bars_and_the_anchor(self):
        """The caller can see what was selected and override it."""
        head = select_head(218)
        assert head is not None
        self.assertIn("bars 1-12", head.describe())
        self.assertIn("Eb7", head.describe())

    def test_every_transcription_selects_without_raising(self):
        """The selector runs over the whole corpus and reports, never crashes.

        456 transcriptions with degenerate A-forms, NC bars, negative bars and
        unmapped chords among them.
        """
        found = 0
        for solo in list_solos():
            head = select_head(solo.melid)
            if head is None:
                continue
            found += 1
            self.assertGreater(head.length, 0, solo.melid)
            self.assertLessEqual(head.start, head.end, solo.melid)
        # The plan records 455 of 456 transcriptions carrying an A-form.
        self.assertGreaterEqual(found, 400)


class TestSlashChordRules(unittest.TestCase):
    """Rules B and C: the slash bass, handled in the loader with the engine frozen."""

    def test_rule_b_promotes_a_minor_triad_over_its_seventh(self):
        """A-/G and C-/Bb are Am7/G and Cm7/Bb: a triad whose bass is the 7th."""
        self.assertEqual(promote_slash_chord("A", "m", "G"), "m7")
        self.assertEqual(promote_slash_chord("C", "m", "Bb"), "m7")
        self.assertEqual(promote_slash_chord("D", "m", "C"), "m7")

    def test_rule_b_promotes_a_major_triad_over_its_seventh(self):
        """C/Bb is written for what a musician reads as C7."""
        self.assertEqual(promote_slash_chord("C", "maj", "Bb"), "maj7")

    def test_rule_b_leaves_other_basses_alone(self):
        """A first-inversion triad is still a triad; only the 7th implies a 7th."""
        self.assertEqual(promote_slash_chord("A", "m", "C"), "m")
        self.assertEqual(promote_slash_chord("C", "maj", "E"), "maj")

    def test_rule_b_leaves_non_triads_alone(self):
        """A seventh chord already says what it is."""
        self.assertEqual(promote_slash_chord("F", "m7", "Ab"), "m7")
        self.assertEqual(promote_slash_chord("E", "7", "G"), "7")

    def test_rule_b_without_a_bass_is_a_no_op(self):
        """No bass, nothing to promote."""
        self.assertEqual(promote_slash_chord("A", "m", None), "m")

    def test_rule_c_measures_the_lowest_note(self):
        """The cost is the distance from the bass to the lowest sounding pitch."""
        self.assertEqual(bass_cost([60, 64, 67], 0), 0)   # C in the bass
        self.assertEqual(bass_cost([62, 65, 69], 0), 2)   # D above a C bass
        self.assertEqual(bass_cost([61, 64, 67], 0), 1)   # C# above a C bass

    def test_rule_c_wraps_around_the_octave(self):
        """B is one semitone below C, not eleven above it."""
        self.assertEqual(bass_cost([59, 62, 65], 0), 1)

    def test_rule_c_without_a_bass_costs_nothing(self):
        """An unslashed chord has no bass preference to honour."""
        self.assertEqual(bass_cost([60, 64], None), 0)

    def test_rule_c_changes_the_pick_in_a_real_corpus_case(self):
        """The bass preference is not a no-op on real material.

        melid 46 is C-/Bb - a minor triad over its own seventh, so rule B makes
        it Cm7/Bb - with Db in the melody. The engine's hand-position rule alone
        picks x-x-9-9-9-9, whose lowest note is D; the bass rule picks
        x-x-8-10-9-9, which actually sounds the Bb the notation asks for.
        """
        from arranger import VoiceLeadingEngine

        root, quality, bass, melody, name = "C", "m", "Bb", "Db5", "Cm7"
        promoted = promote_slash_chord(root, quality, bass)
        self.assertEqual(promoted, "m7")
        plain = min(
            VoiceLeadingEngine.get_all_drop2_voicings(Note(melody), promoted, chord_name=name),
            key=lambda v: abs(v.avg_fret - 9),
        )
        with_bass = _arrange_step_with_bass(
            VoiceLeadingEngine(),
            [(melody, promoted, name)],
            0,
            bass=bass,
        )
        self.assertIsNotNone(with_bass)
        assert with_bass is not None
        with_bass, _prepared = with_bass
        self.assertNotEqual(plain.tab_string(), with_bass.tab_string())
        self.assertEqual(bass_cost(with_bass.midi_notes(), bass_pitch_class(bass)), 0)


@requires_db
class TestSkeletonStrategies(unittest.TestCase):
    """The five reductions, measured on selected heads rather than assumed."""

    def head_section(self, melid):
        head = select_head(melid)
        assert head is not None
        return load_solo(melid), (head.start, head.end)

    def test_strategies_are_ordered_by_density(self):
        """Each strategy is at least as dense as the one before it."""
        solo, section = self.head_section(218)
        counts = [len(skeleton(solo, name, section)) for name in SKELETON_STRATEGIES]
        self.assertEqual(counts, sorted(counts), counts)

    def test_blue_train_head_step_counts(self):
        """Blue Train's 12-bar head, pinned so a change to the grid is visible."""
        solo, section = self.head_section(218)
        self.assertEqual(
            {name: len(skeleton(solo, name, section)) for name in SKELETON_STRATEGIES},
            {"chords": 7, "beats": 36, "eighths": 62, "sixteenths": 80, "notes": 80},
        )

    def test_attya_head_step_counts(self):
        """The trimmed 8-bar ATTYA head, the case the feature usually sees."""
        solo, section = self.head_section(342)
        self.assertEqual(
            {name: len(skeleton(solo, name, section)) for name in SKELETON_STRATEGIES},
            {"chords": 7, "beats": 27, "eighths": 29, "sixteenths": 31, "notes": 31},
        )

    def test_sixteenths_and_notes_agree_at_division_four(self):
        """A note-per-slot grid and a sixteenth grid coincide here.

        They differ only where a player doubles notes inside one sixteenth, or
        where the division is not 4, which is why `notes` is kept for
        diagnostics rather than as a finer default than `sixteenths`.
        """
        solo, section = self.head_section(218)
        divisions = {n.division for n in solo.notes_in_bars(*section)}
        self.assertIn(4, divisions)
        self.assertEqual(
            len(skeleton(solo, "sixteenths", section)), len(skeleton(solo, "notes", section))
        )

    def test_a_slot_carries_no_notated_duration(self):
        """The Weimar slots' `duration` is None, and that is deliberate.

        The regression this pins. `melody.duration` in the database is a
        *performance measurement* in beats - 0.21 for a triplet eighth, 1.75 for a
        note held through a bar line - and it is not a notated length. It is also
        not in whole notes, which is the unit `headxml` and every renderer use, so
        the two loaders were handing the renderers the same field in two different
        units under one name.

        Nothing was wrong with that while the value went unused. It became a bug
        when `tabxml._events` began *capping* a step's span by `duration` to stop a
        note being held across a rest - a cap that only means anything against a
        written length. Handing it a performance measurement truncated every corpus
        step to a fraction of its real length: melid 106's 8-bar head came out with
        44 rests against 31 notes, each chord a sixteenth stub. The corpus path
        therefore offers no duration, and the rhythm comes from the onsets as it
        always did.
        """
        solo, section = self.head_section(106)
        slots = skeleton_slots(solo, "eighths", section)
        self.assertTrue(slots)
        self.assertTrue(
            all(slot[3] is None for slot in slots),
            "a corpus slot offered a performance measurement as a notated duration",
        )
        # The `bar` and `beat` the staff renderer spaces on are still there, so the
        # slot is not left untimed - only its unusable length is dropped.
        self.assertTrue(all(slot[1] is not None and slot[2] is not None for slot in slots))

    def test_unknown_strategy_raises(self):
        """A typo is a usage error, not a silent fallback."""
        solo, section = self.head_section(218)
        with self.assertRaises(ValueError):
            skeleton(solo, "quavers", section)

    def test_unknown_pick_raises(self):
        """A typo in the slot pick is a usage error too."""
        solo, section = self.head_section(218)
        with self.assertRaises(ValueError):
            skeleton(solo, "eighths", section, pick="middle")

    def test_pick_longest_prefers_the_sustained_note(self):
        """Both picks are exercised; the beat grid is where they differ."""
        solo, section = self.head_section(218)
        first = skeleton(solo, "beats", section, pick="first")
        longest = skeleton(solo, "beats", section, pick="longest")
        self.assertEqual(len(first), len(longest))
        self.assertTrue(first)
        self.assertNotEqual(first, longest)

    def test_section_narrows_to_the_head(self):
        """A skeleton of a span is shorter than one of the whole transcription."""
        solo, section = self.head_section(218)
        self.assertLess(
            len(skeleton(solo, "eighths", section)), len(skeleton(solo, "eighths", None))
        )

    def test_every_triple_carries_a_usable_quality(self):
        """No step reaches the engine with a quality it cannot voice."""
        solo, section = self.head_section(218)
        for melody, quality, name in skeleton(solo, "eighths", section):
            if quality == NO_CHORD:
                continue
            self.assertIn(quality, ChordParser.CHORD_TONES_FROM_ROOT, name)


@requires_db
class TestRegisterLift(unittest.TestCase):
    """`--lift auto`: the whole head, moved only when that measurably helps."""

    def head_section(self, melid):
        head = select_head(melid)
        assert head is not None
        return load_solo(melid), head, (head.start, head.end)

    def test_auto_lifts_a_head_that_is_an_octave_too_low(self):
        """Metheny's ATTYA head is 15 notes below B3; lifting voices all of it."""
        solo, head, section = self.head_section(342)
        self.assertTrue([n for n in solo.notes_in_bars(*section) if n.pitch < 59])
        built = build_skeleton(solo, "eighths", section, lift="auto")
        self.assertEqual(built.lift, 12)
        self.assertGreater(built.coverage_lifted[0], built.coverage[0])
        self.assertTrue(all(Note(m).midi_note() >= 59 for m, _, _ in built.triples))

    def test_none_never_lifts(self):
        """`none` leaves the head exactly as transcribed."""
        solo, head, section = self.head_section(342)
        built = build_skeleton(solo, "eighths", section, lift="none")
        self.assertEqual(built.lift, 0)
        self.assertEqual(list(built), skeleton(solo, "eighths", section))

    def test_always_lifts_regardless(self):
        """`always` is the manual override, not a measurement."""
        solo, head, section = self.head_section(218)
        self.assertEqual(build_skeleton(solo, "eighths", section, lift="always").lift, 12)

    def test_per_note_lifts_only_the_unplayable_notes(self):
        """`per-note` is opt-in because it tears the line; it is still available."""
        solo, head, section = self.head_section(218)
        built = build_skeleton(solo, "eighths", section, lift="per-note")
        self.assertTrue(any("per-note" in n for n in built.notes))
        self.assertTrue(any(Note(m).midi_note() >= 59 for m, _, _ in built.triples))

    def test_whole_head_lift_preserves_every_interval(self):
        """A uniform transposition cannot distort the line.

        This is what makes whole-head lifting safe and per-note lifting dangerous:
        a descending 3rd stays a descending 3rd. Compared note-for-note on the
        same triples, since the reduction drops steps that cannot be translated.
        """
        solo, head, section = self.head_section(342)
        base = skeleton(solo, "eighths", section)
        lifted = list(build_skeleton(solo, "eighths", section, lift="always"))
        self.assertEqual(len(base), len(lifted))
        for (original, quality, _), (moved, moved_quality, _) in zip(base, lifted):
            self.assertEqual(quality, moved_quality)
            if quality == NO_CHORD:
                self.assertEqual(original, moved)
                continue
            self.assertEqual(Note(moved).midi_note() - Note(original).midi_note(), 12)

    def test_unknown_lift_mode_raises(self):
        """A typo is a usage error."""
        solo, head, section = self.head_section(218)
        with self.assertRaises(ValueError):
            build_skeleton(solo, "eighths", section, lift="maybe")

    def test_nc_steps_are_not_transposed(self):
        """An unaccompanied bar keeps the pitch it was transcribed at."""
        solo = load_solo(218)
        plain = build_skeleton(solo, "eighths", (0, 1), lift="none")
        lifted = build_skeleton(solo, "eighths", (0, 1), lift="always")
        nc = [(m, q) for m, q, _ in plain.triples if q == NO_CHORD]
        self.assertTrue(nc)
        lifted_nc = [m for m, q, _ in lifted.triples if q == NO_CHORD]
        self.assertEqual([m for m, _ in nc], lifted_nc)


@requires_db
class TestArrangeHead(unittest.TestCase):
    """The end-to-end path: head -> skeleton -> register -> voicings."""

    def arrange(self, melid, **kwargs):
        head = select_head(melid)
        assert head is not None
        return arrange_head(load_solo(melid), head, **kwargs)

    def test_every_harmonised_step_obeys_the_playability_invariant(self):
        """A supported string set, a fret span of 5 or less, the melody on top.

        The invariant is no longer "four contiguous strings": a shell uses three
        strings and a duo two, and 6-4-3 deliberately skips the A string. What still
        holds is that the sounding strings are exactly one GRIP_STRING_SETS entry, that
        the melody is on that entry's soprano, and that the hand does not stretch.
        """
        # drop-2 is "four contiguous strings under the soprano" for any soprano, so it
        # is generated rather than read from the table; shell and duo are named shapes
        # and are read from theirs.
        supported = {frozenset(range(top - 3, top + 1)) for top in (5, 4, 3)}
        supported |= {frozenset(s) for s, _ in GRIP_STRING_SETS["shell"]}
        supported |= {frozenset(s) for s, _ in GRIP_STRING_SETS["duo"]}
        for melid in (218, 342, 266):
            for step in self.arrange(melid).steps:
                if step.melody_only:
                    self.assertEqual(len(step.voicing.active_frets()), 1, melid)
                    continue
                active = step.voicing.active_strings
                self.assertIn(frozenset(active), supported, f"{melid} {step.tab_line()}")
                self.assertIn(len(active), (2, 3, 4), f"{melid} {step.tab_line()}")
                self.assertLessEqual(step.voicing.fret_span(), 5, melid)
                self.assertTrue(all(0 <= f <= 18 for f in step.voicing.active_frets()))
                # The soprano is the melody, and it is one of the three allowed strings.
                self.assertIn(step.voicing.soprano_string(), (5, 4, 3), melid)
                self.assertEqual(
                    max(step.voicing.midi_notes()),
                    Note(step.melody).midi_note(),
                    f"{melid} {step.tab_line()}",
                )

    def test_nc_bars_become_melody_only_steps(self):
        """Blue Train's bar 0 is NC; it is voiced alone, not harmonised."""
        result = arrange_head(load_solo(218), section=(0, 1))
        self.assertTrue(result.steps)
        for step in result.steps:
            self.assertTrue(step.melody_only)
            self.assertFalse(step.non_chord_tone)
            self.assertIsNone(step.harmonized_as)
            self.assertEqual(len(step.voicing.active_frets()), 1)

    def test_diminished_fallback_is_off_by_default(self):
        """Without the flag, no written chord is replaced."""
        plain = self.arrange(218)
        self.assertEqual(plain.rescued, ())
        self.assertFalse(any("diminished" in n for n in plain.notes))

    def test_diminished_fallback_rescues_unresolved_steps(self):
        """With the flag on, the steps nothing else could resolve get a dim7."""
        result = self.arrange(218, fallback="diminished")
        self.assertTrue(result.rescued, "expected some steps to be rescued")
        self.assertEqual(len(result.rescued), result.skeleton.rescued)
        self.assertTrue(any("diminished" in n for n in result.notes))

    def test_the_recovery_count_is_reported_without_the_flag(self):
        """A user can see what they would gain without opting in."""
        self.assertGreater(self.arrange(218).skeleton.rescued, 0)

    def test_unknown_fallback_raises(self):
        """A typo is a usage error."""
        with self.assertRaises(ValueError):
            self.arrange(218, fallback="dominant")

    def test_a_head_arranges_to_real_voicings(self):
        """The worked example produces printable tab."""
        result = self.arrange(218)
        self.assertGreater(len(result.steps), 20)
        self.assertTrue(all(step.tab_line() for step in result.steps))


class TestBarRangeParsing(unittest.TestCase):
    """--bars parsing, including the negative bounds the anacrusis needs."""

    def test_plain_range(self):
        """LO-HI, half-open."""
        self.assertEqual(parse_bar_range("0-8"), (0, 8))
        self.assertEqual(parse_bar_range("10-14"), (10, 14))

    def test_negative_low_bound(self):
        """'-4-8' is a negative low bound, not a malformed range."""
        self.assertEqual(parse_bar_range("-4-8"), (-4, 8))

    def test_negative_high_bound(self):
        """A negative HI is a real bound, reached through the pickups."""
        self.assertEqual(parse_bar_range("-8--1"), (-8, -1))

    def test_open_ended(self):
        """A single number means 'from here to the end'."""
        self.assertEqual(parse_bar_range("12"), (12, None))

    def test_whitespace_is_tolerated(self):
        """Quoted arguments often carry spaces."""
        self.assertEqual(parse_bar_range(" -4 - 8 "), (-4, 8))

    def test_empty_range_raises(self):
        """An empty string is a usage error."""
        with self.assertRaises(ValueError):
            parse_bar_range("")

    def test_inverted_range_raises(self):
        """A range with HI <= LO selects nothing and is almost always a typo."""
        with self.assertRaises(ValueError):
            parse_bar_range("9-3")

    def test_non_numeric_raises(self):
        """Text where a bar number belongs is a usage error."""
        with self.assertRaises(ValueError):
            parse_bar_range("start-end")


@requires_db
class TestCorpusCli(unittest.TestCase):
    """The `corpus` front end, exercised end to end against the real database."""

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = corpus_cli(list(argv))
        return code, buffer.getvalue()

    def test_blue_train_head_renders_tab(self):
        """The default invocation prints a header and real tab."""
        code, output = self.run_cli("--melid", "218")
        self.assertEqual(code, 0)
        self.assertIn("Blue Train", output)
        self.assertIn("John Coltrane", output)
        self.assertIn("head at bars 1-12", output)
        self.assertIn("x-x-", output)

    def test_the_head_is_the_default_selection(self):
        """No --section means the head, and the CLI says which one it chose."""
        _, output = self.run_cli("--melid", "218")
        self.assertIn("head at bars 1-12 (12 bars)", output)

    def test_head_path_agrees_with_the_library_on_a_non_chord_tone(self):
        """
        The head path used to build its own candidates and call `_best_voicing` with
        no `allowed_tones`, which skipped the non-chord-tone strategies, the
        tone-purity criterion and the octave-down rescue. The same chord therefore
        harmonised differently depending on which door it came through.
        """
        from arranger import VoiceLeadingEngine as Engine

        solo = load_solo(266)
        arrangement = arrange_head(solo)
        triples = list(arrangement.skeleton.triples)
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            library = Engine.arrange_progression(triples)

        self.assertTrue(
            any(step.non_chord_tone for step in arrangement.steps),
            "the head path should now resolve non-chord tones",
        )
        self.assertEqual(
            [s.tab_line() for s in arrangement.steps if not s.melody_only],
            [s.tab_line() for s in library if not s.melody_only],
        )

    def test_attya_held_note_is_reharmonised_across_a_chord_change(self):
        """
        Where ATTYA holds C4 across a chord change, the held soprano is harmonised
        against each new chord instead of being held as a bare single note.

        The ringing inner voices of a held shape belong to the chord the hold began
        on, so printing a new chord's name over a single struck note claims a harmony
        that is not sounding. The voicing was already built against the new chord -
        only the rendering used to discard it - so the fix is that such a step is no
        longer marked as a repeat. A repeat under the *same* chord is still a repeat,
        which is what the final Eb7 here is.
        """
        from arranger import ChordParser

        steps = arrange_head(load_solo(266)).steps
        held = [s for s in steps if s.bar in (61, 62, 63) and s.melody == "C4"]
        self.assertEqual([s.chord for s in held], ["F-7", "Bb-7", "Eb7", "Eb7"])
        # Each chord change re-harmonises; only the second Eb7 holds.
        self.assertEqual([s.repeated for s in held], [False, False, False, True])

        # The two changes are resolved as genuine extensions, and the held soprano
        # sounds as the new chord's 9th/6th over its 3rd and 7th. Before the head
        # path shared the engine's step logic, bar 62 was voiced `x-0-2-0-1-x` -
        # A2, E3, G3, C4, an Am7 sharing no pitch class at all with Bbm7.
        expected = [("m9", "Bbm9"), ("13", "Eb13")]
        for step, (quality, name) in zip(held[1:3], expected):
            self.assertEqual(step.harmonized_as, name)
            tones = set(ChordParser.get_chord_tones(quality, name))
            inner = set(step.voicing.pitch_classes()) - {max(step.voicing.midi_notes()) % 12}
            self.assertTrue(
                inner <= tones,
                f"{step.chord} sounded inner voices outside {name}: "
                f"{sorted(inner - tones)}",
            )

    def test_attya_low_chord_tone_is_voiced_on_the_g_string(self):
        """
        The Ab3 in bar 61 sits below the B string's open pitch and used to be
        unvoiceable and silently skipped. It is now harmonised as a 6-4-3 shell on the G
        string - a three-note shell, because no four-note shape fits under a note that
        low without the bottom-four block that does not sound good. So a note of the
        transcription is played rather than dropped.

        Both are three-note shells on the G string, and both sound only tones of their
        own chord - a full voicing was available for neither, and a four-note shape on
        6-5-4-3 is deliberately not offered.
        """
        steps = arrange_head(load_solo(266)).steps
        # Spelled out rather than re-derived from the chord symbol: parse_chord_name
        # returns the *suffix*, and "-7" is an alias for a minor triad in the quality
        # table, so feeding it back would check this shape against the wrong chord.
        expected = {("F-7", "Ab3"): {0, 3, 5, 8}, ("Bb-7", "Bb3"): {1, 5, 8, 10}}
        for bar, melody in ((61, "Ab3"), (62, "Bb3")):
            found = [s for s in steps if s.bar == bar and s.melody == melody]
            self.assertTrue(found, f"the {melody} in bar {bar} should be voiced")
            step = found[0]
            self.assertEqual(step.grip, "shell")
            self.assertEqual(step.voicing.soprano_string(), 3)   # the G string
            self.assertEqual(step.voicing.active_strings, [1, 2, 3])
            self.assertEqual(max(step.voicing.midi_notes()), Note(melody).midi_note())
            tones = expected[(step.chord, melody)]
            self.assertTrue(
                set(step.voicing.pitch_classes()) <= tones,
                f"{step.chord} {melody} {step.tab_line()}",
            )

    def test_explicit_section_overrides_the_head(self):
        """--section selects a named span instead."""
        _, output = self.run_cli("--melid", "218", "--section", "form:I1")
        self.assertIn("section form:I1: bars 0-5", output)

    def test_glob_section(self):
        """A * glob selects every matching span."""
        _, output = self.run_cli("--melid", "218", "--section", "form:I*")
        self.assertIn("form:I*", output)

    def test_negative_bars_reach_the_pickups(self):
        """--bars -4-1 renders the anacrusis, which sits below bar 0."""
        _, output = self.run_cli("--melid", "266", "--bars", "-4-1", "--skeleton", "chords")
        self.assertIn("All the Things You Are", output)
        self.assertIn("x-", output)

    def test_vertical_rendering(self):
        """--vertical switches to six-line tab blocks."""
        _, output = self.run_cli("--melid", "218", "--bars", "1-2", "--vertical")
        self.assertIn("e|", output)
        self.assertIn("B|", output)

    def test_the_diminished_offer_is_reported_without_the_flag(self):
        """The user is told what the opt-in would buy before opting in."""
        _, output = self.run_cli("--melid", "218")
        self.assertIn("--fallback diminished", output)

    def test_fallback_flag_is_honoured(self):
        """With the flag the substitution note appears instead of the offer."""
        _, output = self.run_cli("--melid", "218", "--fallback", "diminished")
        self.assertIn("diminished fallback replaced the written chord", output)

    def test_lift_decision_is_reported(self):
        """The register decision is visible, because it moves the music."""
        _, output = self.run_cli("--melid", "342")
        self.assertIn("lifted an octave", output)

    def test_list_does_not_require_a_melid(self):
        """--list enumerates the corpus on its own."""
        code, output = self.run_cli("--list")
        self.assertEqual(code, 0)
        self.assertIn("Blue Train", output)

    def test_bad_selector_is_a_usage_error(self):
        """An unknown span kind exits cleanly rather than raising."""
        with self.assertRaises(SystemExit):
            self.run_cli("--melid", "218", "--section", "bogus:x")

    def test_missing_melid_is_a_usage_error(self):
        """--melid is required unless --list is given."""
        with self.assertRaises(SystemExit):
            self.run_cli("--skeleton", "chords")

    def test_unknown_skeleton_is_rejected_by_the_parser(self):
        """argparse rejects an unknown choice before any work happens."""
        with self.assertRaises(SystemExit):
            self.run_cli("--melid", "218", "--skeleton", "quavers")


if __name__ == "__main__":
    unittest.main()