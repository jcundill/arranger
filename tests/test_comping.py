"""The comping route: a chord part with no melody on top.

A comping step is a three-voice shell chosen from the chord alone, and `melody_voiced`
is `False` - the guitar is not singing. The load-bearing claim is that the default is
inert: every published arrangement must come out byte-identical, which is asserted here
against the same progression arranged both ways. Note what is *not* claimed: that the
melody's pitch never appears, because a guide tone can share its pitch class. The
invariant is the identical candidate set whatever melody is asked about.

**The route narrows that set, the generator does not** - `TestTheCompStaysUnderTheTune` is
the other half: on a singing selection the shape's top stays strictly below the tune note in
force, so a stab neither restates it nor takes the string a tie is held on.
"""

import inspect
import unittest
from typing import List, Optional, Tuple

from musthe import Note

from arranger import (
    ChordParser,
    TimeSignature,
    VoiceLeadingEngine,
    Voicing,
    format_progression,
    get_comping_voicings,
    parts_has_melody_only,
    resolve_request,
    supported_string_sets,
)
from arranger.comp_line import LineShape
from arranger.comp_line_route import leaving_room_for_the_tune
from arranger.grip_place import snapshot
from arranger.grip_tables import (
    COMPING_MAX_SPAN,
    GRIP_STRING_SETS,
    comping_string_sets,
)
from arranger.grips import (
    CompingRequest,
    _comping_collapse_key,
    _comping_palette,
    _search_comping_voicings,
    get_comping_voicings_for,
)
from arranger.options import ArrangeOptions, Request
from arranger.tuning import NECK_FRET_MAX, NECK_FRET_MIN, SILENCE_GRID
from tests.support import (
    PROGRESSION,
    TROUBLE_IN_MIND,
    arranged,
    chord_pcs,
    comping,
    guide_pcs,
    make_voicing,
    sweep_head_paths,
)


class TestCompingGenerator(unittest.TestCase):
    """`get_comping_voicings`: a chord stated without the tune on top."""

    def test_every_quality_the_engine_can_voice_has_a_comping_shape(self):
        """No voiceable quality is left without a guide-tone shape.

        Checked over `CHORD_TONES_FROM_ROOT` rather than a hand-picked list, so a
        quality added later cannot join the engine without being measured here - the
        failure being guarded is exactly one that arrives silently.
        """
        missing = [
            quality
            for quality in sorted(ChordParser.CHORD_TONES_FROM_ROOT)
            if not get_comping_voicings(f"C{quality}")
        ]
        self.assertEqual(missing, [], f"no comping shape for {missing}")

    def test_everycandidate_states_the_chord(self):
        """Both guide tones sound, and nothing outside the chord does."""
        for name in ("Cmaj7", "Am7", "G7", "Dm7b5", "Bdim7", "Fmaj7", "C6", "G7sus4"):
            needed, allowed = guide_pcs(name), chord_pcs(name)
            for voicing in comping(name):
                pcs = {midi % 12 for midi in voicing.midi_notes()}
                self.assertTrue(
                    needed <= pcs, f"{name} {voicing.tab_string()} lacks a guide tone"
                )
                self.assertTrue(
                    pcs <= allowed, f"{name} {voicing.tab_string()} sounds a wrong note"
                )

    def test_a_shape_is_three_voices_in_a_supported_set_inside_the_span(self):
        """The playability invariant, minus the melody clause.

        The clause that is dropped is "the melody is on the topmost string", and it is
        dropped for the only reason there is: there is no melody. Everything else -
        three voices, one of the `shell` sets, span within `COMPING_MAX_SPAN` - is
        asserted exactly as it is for every other grip.
        """
        supported = {frozenset(s) for s in supported_string_sets()}
        shell_sets = {frozenset(strings) for strings, _ in GRIP_STRING_SETS["shell"]}
        for name in ("Cmaj7", "G7", "Am7", "Fmaj7"):
            for voicing in comping(name):
                active = frozenset(
                    i for i, fret in enumerate(voicing.frets) if fret >= 0
                )
                self.assertEqual(len(voicing.active_frets()), 3, voicing.tab_string())
                self.assertIn(active, supported, voicing.tab_string())
                self.assertIn(active, shell_sets, voicing.tab_string())
                self.assertLessEqual(
                    voicing.fret_span(), COMPING_MAX_SPAN, voicing.tab_string()
                )

    def test_the_high_e_is_not_on_the_palette_at_any_arity(self):
        """The tune's own string is off the comping part's palette.

        `COMPING_EXCLUDED_STRINGS` carries the reason: the high E is where
        `MELODY_STRING_CHOICES_FULL` pins a tune first, and a comping shape has no tune
        to put there, so a shape whose top voice sits on it is heard as a melody - above
        the horn playing the real one.

        Asserted on the **sets** rather than on a chosen tab, because a set that is
        offered and merely not chosen today is a set that can be chosen tomorrow; and
        over every arity including the bass voice, so a new family cannot reintroduce it.
        """
        for notes in range(1, 5):
            for bass_voice in (False, True):
                sets = comping_string_sets(notes, bass_voice)
                self.assertTrue(sets, (notes, bass_voice))
                for strings in sets:
                    self.assertNotIn(5, strings, (notes, bass_voice, strings))

    def test_a_one_note_shape_is_offered_once_per_string(self):
        """Two `duo` pairs share a top string, and one note is one shape.

        A duplicate is harmless to the ranking and wrong as a palette: it says the same
        position was offered two ways, and it would hand the selector the identical
        candidate twice.
        """
        sets = comping_string_sets(1)
        self.assertEqual(len(sets), len(set(sets)), sets)

    def test_a_chord_with_no_root_is_refused(self):
        """A guide tone is a claim about *this* chord, so no root means no claim.

        The rule survives as a refusal rather than an empty list, which is what the
        quality field used to make it: a symbol with no readable root has no quality
        either, so there is nothing to state and the resolver says so rather than
        guessing the 3rd and 7th and putting a wrong note in the tab.
        """
        with self.assertRaises(ValueError):
            get_comping_voicings(None)
        with self.assertRaises(ValueError):
            get_comping_voicings("H7")
        # A bare root is not rootless - it is a major triad, and it is voiced.
        self.assertTrue(get_comping_voicings("C"))

    def test_the_window_is_a_preference_and_never_a_filter(self):
        """Narrowing it may cost shapes, but it must never cost the chord.

        The rule the whole library states about `fret_min`/`fret_max`: losing a chord of
        the tune is worse than being a fret out of position.
        """
        wide = get_comping_voicings("Cmaj7")
        narrow = get_comping_voicings("Cmaj7", fret_min=0, fret_max=0)
        self.assertTrue(wide)
        self.assertTrue(narrow, "a zero-width window must still voice the chord")


class TestTheCompingReach(unittest.TestCase):
    """A comping shape fills its strings and stays inside `COMPING_MAX_SPAN` frets.

    Two rules, and neither implies the other. The **reach** (`COMPING_MAX_SPAN`) is four,
    because a comping shape has no melody pinned to it and every tone it can state on
    adjacent strings is statable inside four; the fifth fret is what a **pinned** melody
    costs (`GRIP_MAX_SPAN["shell"]`). The **hole** (`grip_tables._fills_its_strings`) is
    that the strings between the shape's bottom and its top all sound. The cap alone was
    not enough and `x-6-x-5-9-x` is the shape that proved it: the A string's 6, the G
    string's 5 and the B string's 9, with the D string muted under the fingers - a span of
    four, so it survived the cap, and `grips._comping_collapse_key` ranks a shape's
    register **before** its span, so the wide spelling of that top tone still beat the
    tight one. A skip is the right answer when a melody is pinned to a string or a drop-2
    needs a deep bass; a comp has neither.

    `docs/engine.md` §"`get_comping_voicings`: a chord with no melody on top" carries the
    measurement of what the two rules cost, and the acceptance example's tops are unchanged
    by them (`tests/test_comp_line.py`).
    """

    #: The default band: the palette collapses one shape per top tone only when a band is
    #: present, so a witness built without one would not be the palette a comp reads.
    BAND = (3, 10)

    def _palette(self, name: str, notes: int = 3):
        return get_comping_voicings_for(
            CompingRequest(name, NECK_FRET_MIN, NECK_FRET_MAX, notes, False, self.BAND)
        )

    def test_no_shape_the_palette_offers_crosses_four_frets(self):
        """The limit is the search's own, so it holds at every arity and every quality.

        Swept over `CHORD_TONES_FROM_ROOT` because a quality added later must not be the
        one that reintroduces a stretch, and over the arities because the family changes
        with them (`duo` pairs, `shell` sets, `duo` tops).
        """
        widest = 0
        for quality in sorted(ChordParser.CHORD_TONES_FROM_ROOT):
            for notes in (1, 2, 3):
                for voicing in self._palette(f"C{quality}", notes):
                    widest = max(widest, voicing.fret_span())
        self.assertLessEqual(widest, COMPING_MAX_SPAN)

    def test_no_shape_the_palette_offers_leaves_a_hole_in_its_strings(self):
        """Every string between a shape's bottom and its top sounds, at every arity.

        Read as the sounding strings being a *run* of neighbours: `len(active) ==
        max - min + 1`. A one-note shape is trivially a run, which is why the arities are
        swept rather than asserted one by one - and why the rule is stated as an equality
        on the shape rather than as a list of refused sets.
        """
        for quality in sorted(ChordParser.CHORD_TONES_FROM_ROOT):
            for notes in (1, 2, 3):
                for voicing in self._palette(f"C{quality}", notes):
                    strings = [
                        index for index, fret in enumerate(voicing.frets) if fret >= 0
                    ]
                    self.assertEqual(
                        len(strings),
                        max(strings) - min(strings) + 1,
                        f"C{quality} {notes} voices: {voicing.tab_string()}",
                    )

    def test_a_step_the_thumb_joins_keeps_the_hole_rule_scoped_to_the_shape(self):
        """The skipped string the *bass layer* leaves is not the palette's business.

        `3-x-4-4-8-x` is the C-shape G every player knows - a root on the low E with the
        chord above on the D, G and B - and the A string is muted in it. The rule the
        palette holds is about the **chord part's own shape**; a thumb merged underneath
        is placed by its own cost (`bass_place`), and a comp that refused that shape would
        be refusing an idiom rather than a compromise.
        """
        steps, _head, _notes = arranged(
            "tests/data/synthetic_repeat_slash.musicxml",
            section=(1, 2),
            request=Request(melody=False, bass_on="melody", bass_notes="root"),
        )
        self.assertIn("3-x-4-4-8-x", [step.tab_line() for step in steps])

    def test_the_stretch_a_fifth_fret_bought_is_off_the_palette(self):
        """`Dm7` in the default band: the same top tone, spelled inside the hand's four.

        `8-x-3-7-x-x` states Dm7 with its top on D4 and spans the fifth the **shell's**
        limit allows - the shape the four-bar example's walk used to be played with - and
        it leaves the B string muted between two sounding neighbours. `x-8-10-7-x-x`
        states the same chord with the same top tone on adjacent strings, a span of three.
        What the rules change is the register the lowest voice sits in (C3 becomes F3),
        which is the cost the document states; the harmony and the line are the same,
        which is why the example's tops do not move.
        """
        tabs = [voicing.tab_string() for voicing in self._palette("Dm7")]
        self.assertIn("x-8-10-7-x-x", tabs)
        self.assertNotIn("8-x-3-7-x-x", tabs)

    def test_the_shape_that_named_the_hole_rule_is_off_the_palette(self):
        """`x-6-x-5-9-x`: an A string 6, a G string 5 and a B string 9, and no D string.

        A span of four, so the cap let it through - and its top tone is statable on the
        D, G and B strings, which is what makes it a compromise rather than the only
        spelling. Swept over the roots as well as the qualities, because the pitch classes
        have to be chord tones of *some* chord for the shape ever to be generated, and the
        rule is that it is generated for none of them.
        """
        for root in ("C", "Eb", "E", "G", "Ab", "A"):
            for quality in sorted(ChordParser.CHORD_TONES_FROM_ROOT):
                for notes in (2, 3):
                    tabs = {
                        voicing.tab_string()
                        for voicing in self._palette(f"{root}{quality}", notes)
                    }
                    self.assertNotIn("x-6-x-5-9-x", tabs)
                    self.assertNotIn("5-x-5-9-x-x", tabs)

    def test_no_shape_the_palette_offers_states_a_pitch_twice(self):
        """A unison is not a voice, at every arity and every quality.

        Read as an equality on the shape rather than as a list of refused tabs, because the
        reason is the tuning: the G and B strings are a third apart, so a top tone on the B
        can be repeated four frets up the G. `x-x-8-8-4-x` is the shape that named the rule
        - a Cm7 shell sounding `Eb4` on two strings, which states two pitches where the
        arity claims three.
        """
        for quality in sorted(ChordParser.CHORD_TONES_FROM_ROOT):
            for notes in (1, 2, 3):
                for voicing in self._palette(f"C{quality}", notes):
                    midis = voicing.midi_notes()
                    self.assertEqual(
                        len(set(midis)), len(midis),
                        f"C{quality} {notes} voices: {voicing.tab_string()}",
                    )

    def test_the_shape_that_named_the_unison_rule_is_off_the_palette(self):
        """`x-x-8-8-4-x`: a G string 8 and a B string 4, and both of them `Eb4`.

        A Cm7 shell whose third note is the same pitch as its second, so it states `Bb3`
        and `Eb4` and calls it three voices. Its top tone is statable on other sets, which
        is what makes it a compromise rather than the only spelling: the step it was
        reported on (`synthetic_pickup_cut`, bar 3, under `--no-melody`) now plays
        `x-6-8-8-x-x`, a four-voice Cm7 with the same top.
        """
        for name in ("Cm7", "Cm", "Cm9"):
            tabs = {
                voicing.tab_string()
                for voicing in self._palette(name)
            }
            self.assertNotIn("x-x-8-8-4-x", tabs, name)
        for name in ("Cm7", "Cm", "Cm9"):
            tabs = {
                voicing.tab_string()
                for voicing in self._palette(name)
            }
            self.assertNotIn("x-x-8-8-4-x", tabs, name)

    def test_no_comping_step_of_a_committed_head_crosses_four_frets(self):
        """The rule read on the **step**, not only on the shape the palette offered.

        A step's frets are the chosen shape's plus whatever a later merge writes into
        them, and that is the level at which the four-finger invariant is stated for the
        same reason: a rule asserted over a voicing says nothing about a step assembled
        after the choice.
        """
        steps = 0
        for path in sweep_head_paths():
            head_steps, _head, _notes = arranged(path, request=Request(melody=False))
            for step in head_steps:
                if step.silence is not None or not step.voicing.active_frets():
                    continue
                steps += 1
                self.assertLessEqual(
                    step.voicing.fret_span(),
                    COMPING_MAX_SPAN,
                    f"{path} bar {step.bar} beat {step.beat}: {step.tab_line()}",
                )
        self.assertGreater(steps, 30, "the sweep measured almost no comping steps")


class TestTheCompingPaletteIsRemembered(unittest.TestCase):
    """`_search_comping_voicings` is answered through `_comping_palette`; the answer may not move.

    An invisible memo stops being invisible in the same three ways the placement memo
    does (`tests/test_placement.py` holds that one to them), and each has an assertion
    here: an answer that differs from the enumeration's, a caller's write reaching the
    next caller, and a memo that is never read - which would leave every other test in
    this file passing while the engine paid for a cache it never used.
    """

    #: Representative requests rather than the whole parameter space, because the
    #: *enumeration* is the expensive half and this is the one test that has to run it
    #: bypassing the memo. Every other test in this file, and every pinned corpus tab in
    #: the suite, reads the memo.
    CASES: List[Tuple[str, str]] = [
        ("maj7", "Cmaj7"),
        ("m7", "Dm7"),
        ("7", "A7"),
        ("9", "C9"),
        ("m7b5", "Bm7b5"),
        ("dim7", "Bdim7"),
    ]

    def setUp(self):
        # These assertions are about the *entry point*, so the memo starts empty and no
        # test here inherits another's entries.
        _comping_palette.cache_clear()

    def test_the_memo_answers_what_the_enumeration_answers(self):
        """One request asked both ways: what the memo stores *is* the search's answer.

        Compared as snapshots rather than as tabs, so a rebuilt `Voicing` cannot hide a
        field the memo dropped - `top_fret`, `avg_fret`, `role` and the bass fields all
        come out of it.
        """
        checked = 0
        for _quality, name in self.CASES:
            for notes in (1, 3):
                for bass_voice in (False, True):
                    request = CompingRequest(
                        name,
                        NECK_FRET_MIN,
                        NECK_FRET_MAX,
                        notes,
                        bass_voice,
                    )
                    searched = _search_comping_voicings(request)
                    remembered = _comping_palette(request)
                    self.assertEqual(
                        [snapshot(voicing) for voicing in searched],
                        list(remembered),
                        f"{name} notes={notes} bass_voice={bass_voice}",
                    )
                    checked += 1
        self.assertGreater(checked, 20, "the memo was compared over almost nothing")

    def test_a_caller_writing_into_its_shape_does_not_reach_the_next_caller(self):
        """The memo may not hand one object out twice, because the engine writes into it.

        The comping route is where this bites hardest: `decisions.select_step_voicing`
        returns one of the palette's **own objects**, and `bass_merge.attach_bass` then
        merges the walked thumb into its fret vector and `bass_pc`. A shared object would
        let one step's bass line become the next step's palette, silently and only in the
        tab, so the identity assertion is the witness: it is the *sharing* that is
        forbidden, not the equality of the two answers.
        """
        first = get_comping_voicings("Cmaj7")
        second = get_comping_voicings("Cmaj7")
        self.assertTrue(first)
        self.assertIsNot(first, second, "the memo handed one list out twice")
        self.assertIsNot(first[0], second[0], "the memo handed one object out twice")
        pristine_tab = first[0].tab_string()
        pristine_bass = first[0].bass_pc
        # Exactly what `attach_bass` does, down to the string: the thumb takes a string
        # the shape left muted and writes its fret there.
        muted = [index for index, fret in enumerate(first[0].frets) if fret < 0]
        self.assertTrue(muted, "no muted string for the thumb note to be written onto")
        first[0].frets[muted[0]] = 7
        first[0].bass_pc = None if pristine_bass is None else (pristine_bass + 1) % 12

        third = get_comping_voicings("Cmaj7")
        self.assertEqual(third[0].tab_string(), pristine_tab)
        self.assertEqual(third[0].bass_pc, pristine_bass)

    def test_the_request_is_the_memo_key(self):
        """The object entry point and the primitive one share one memo entry."""
        request = CompingRequest(
            "Cmaj7", NECK_FRET_MIN, NECK_FRET_MAX, 3, False
        )
        before = _comping_palette.cache_info()
        by_object = get_comping_voicings_for(request)
        after = _comping_palette.cache_info()
        self.assertEqual(after.misses - before.misses, 1)
        by_keyword = get_comping_voicings("Cmaj7")
        self.assertEqual(
            [voicing.tab_string() for voicing in by_object],
            [voicing.tab_string() for voicing in by_keyword],
        )
        self.assertEqual(_comping_palette.cache_info().hits - after.hits, 1)

    def test_the_memo_is_read_rather_than_bypassed(self):
        """A memo nothing hits is a claim with no effect - an invisible knob.

        Pinned as a *count* rather than as a timing, because the second call being fast
        is exactly what a reader cannot see from the code.
        """
        before = _comping_palette.cache_info()
        get_comping_voicings("Dm7")
        after_first = _comping_palette.cache_info()
        get_comping_voicings("Dm7")
        after_second = _comping_palette.cache_info()
        self.assertEqual(after_first.misses - before.misses, 1)
        self.assertEqual(after_first.hits - before.hits, 0)
        self.assertEqual(after_second.misses - after_first.misses, 0)
        self.assertEqual(after_second.hits - after_first.hits, 1)

    def test_clearing_the_memo_runs_the_enumeration_again(self):
        """The seam the checks above need, and the one a changed table would need.

        After `cache_clear` the enumeration runs and the same shapes come back, which is
        what makes "the search is still the thing under test" a fact about this file
        rather than a hope.
        """
        first = get_comping_voicings("A7")
        self.assertGreater(_comping_palette.cache_info().currsize, 0)
        _comping_palette.cache_clear()
        self.assertEqual(_comping_palette.cache_info().currsize, 0)
        self.assertEqual(
            [voicing.tab_string() for voicing in get_comping_voicings("A7")],
            [voicing.tab_string() for voicing in first],
        )


class TestTheBandedCollapseReadsOneBand(unittest.TestCase):
    """The collapse and the line answer "inside the band?" the same way.

    A banded palette keeps **one shape per top tone**, and the comp line then filters
    that palette on `LineShape.in_band`. When the two asked different questions - an
    average here, every fret there - the collapse could keep a shape the line refused
    to walk, so the tone's in-band shape never reached the selector
    (`docs/history/comp-line.md`). `grip_place.frets_in_band` is now the one answer.
    """

    @staticmethod
    def _voicing(frets: Tuple[int, ...]) -> Voicing:
        """A `Voicing` sounding `frets` on the top three strings."""
        padded = [-1, -1, -1, -1, -1, -1]
        for index, fret in zip((3, 4, 5), frets):
            padded[index] = fret
        return Voicing(
            frets=padded,
            top_fret=max(frets),
            avg_fret=sum(frets) / len(frets),
        )

    def test_the_collapse_and_the_line_agree_shape_by_shape(self):
        """Over a spread of registers, the two predicates never disagree."""
        band = (3, 10)
        for frets in [(3, 5, 10), (7, 9, 12), (2, 5, 9), (4, 6, 8), (3, 11, 11)]:
            with self.subTest(frets=frets):
                _window, outside_band, _middle, _span = _comping_collapse_key(
                    frets, band, NECK_FRET_MIN, NECK_FRET_MAX
                )
                in_band = LineShape.of(self._voicing(frets), band).in_band
                self.assertEqual(outside_band, 0 if in_band else 1)

    def test_the_measured_shape_is_outside_for_both(self):
        """`x-7-x-9-12-x`: average 9.3 inside the band, top voice at fret 12 outside."""
        frets = (7, 9, 12)
        band = (3, 10)
        _window, outside_band, _middle, _span = _comping_collapse_key(
            frets, band, NECK_FRET_MIN, NECK_FRET_MAX
        )
        self.assertEqual(outside_band, 1)
        self.assertFalse(LineShape.of(self._voicing(frets), band).in_band)


class TestTheAxisIsInertByDefault(unittest.TestCase):
    """`voices=auto` and `voices=guitar` are the arrangement that always was."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_the_default_still_pins_the_melody_to_the_soprano(self):
        """And every step says the guitar is singing."""
        for step in self.engine.arrange_progression(PROGRESSION):
            self.assertTrue(step.melody_voiced)
            self.assertEqual(
                max(step.voicing.midi_notes()), Note(step.melody).midi_note()
            )

    def test_one_request_two_places_to_name_it(self):
        """One request reaches the engine whether it sits beside `options=` or inside it.

        Both halves are what a second spelling would cost: the comping selection
        reaches the engine as `Request(melody=False)`, and the bare call is the shipped
        request rather than a different default.
        """
        by_option = self.engine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(request=Request(melody=False))
        )
        self.assertTrue(all(not step.melody_voiced for step in by_option))
        self.assertEqual(
            format_progression(self.engine.arrange_progression(PROGRESSION)),
            format_progression(
                self.engine.arrange_progression(PROGRESSION, options=ArrangeOptions())
            ),
        )

    def test_the_axis_is_not_a_keyword_on_the_entry_point(self):
        """The five axes are the implementation, so they have no keyword spelling.

        A call naming one is unspellable rather than conflicting;
        `tests/meta_structure.py` holds the whole entry-point surface to it.
        """
        signature = inspect.signature(self.engine.arrange_progression)
        self.assertNotIn("parts", signature.parameters)


class TestTheCompingArrangement(unittest.TestCase):
    """A comping request with a thumb line: what the guitarist is handed."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.timings = [(0, 1.0, 1.0), (0, 2.0, 1.0), (0, 3.0, 1.0), (0, 4.0, 1.0)]

    def comped(self, timings=None, **request_kwargs):
        # `melody=False` with a chord position: the thumb line is the **bass part**,
        # and a bass style is refused without it ("add 'bass' to parts"). The arity is
        # unaffected - `comping_arity` reads the chord part and the hand, not how many
        # parts are named - so the shapes are the same as a chord-only selection's.
        steps = self.engine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(
                request=Request(melody=False, **request_kwargs), timings=timings
            ),
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_the_generator_never_reads_the_melody(self):
        """The load-bearing claim of the whole feature, stated so it cannot pass by luck.

        The first version of this test asserted that no comping step *contains* the
        melody's pitch, which reads well and is false: measured over the three committed
        sweep heads under `--no-melody --chord-notes 2`, **37 of the 93 comping steps do
        contain it**. That is not a defect but it is
        worth being exact about, because the two claims are not the same claim:

        - the guitar is not *singing* - the shape was chosen from the chord alone;
        - a chord tone in the shell may *coincide* with the melody's pitch class,
          which is unremarkable and happens on a fifth of all steps.

        So the invariant asserted here is the first one, and it is asserted the only way
        that can be conclusive: **the candidate set is identical whatever melody is
        asked about.** A generator that read the melody could not produce the same
        shapes for `D5` and `G3` under the same chord.
        """
        from arranger.grips import get_comping_voicings

        for chord in ("Dm7", "G7", "Fmaj7"):
            sets = {
                tuple(sorted(v.tab_string() for v in get_comping_voicings(chord)))
                for _melody in ("D5", "C5", "A4", "F4", "Bb4", "E5", "G3", "D6")
            }
            self.assertEqual(
                len(sets), 1, f"{chord}: the generator's output varies with the melody"
            )

    def test_no_step_is_marked_as_singing(self):
        """What a renderer reads, and what the whole feature is for.

        This is the honest form of the claim: the guitar's part is *not the tune*, and
        `melody_voiced=False` is the flag that says so. It is deliberately **not** the
        stronger "the melody's pitch never appears", which is coincidence-dependent.
        """
        for step in self.comped():
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_the_melody_is_never_pinned_to_a_top_string(self):
        """No soprano is reserved for the tune, because there is no tune to pin.

        Checked over the corpus, where the stronger per-step claim fails. The sets are
        the **comping** ones - the same `comping_string_sets` the generator builds
        from - because the comping part is not a truncated grip palette: `(0, 2)` is a
        pair no `supported_string_sets()` entry lists, and truncating a shell set is
        how it would get into the tab.
        """
        comping_sets = {
            frozenset(s) for s in comping_string_sets(3)
        }
        for step in self.comped():
            active = frozenset(
                i for i, fret in enumerate(step.voicing.frets) if fret >= 0
            )
            self.assertIn(active, comping_sets, step.tab_line())

    def test_no_comping_step_over_the_committed_heads_sounds_the_high_e(self):
        """The palette's rule, asserted at the level the tab is read at.

        `comping_string_sets` drops the high E; this is the same claim about the
        **step**, because a rule stated over a shape says nothing about a step the
        engine builds afterwards - and a thumb line merges into the fret vector after
        selection. It cannot put the string back (the thumb lives on the low E, the A
        and the D), which is why the assertion is on the whole step's sounding strings
        rather than on the upper shape's.

        Every arity is swept, since each takes a different family. A count as well as an
        assertion, because a palette that stopped offering shapes at all would satisfy
        "nothing sounds the high E" silently.
        """
        from tests.support import arranged, sweep_head_paths

        checked = 0
        for path in sweep_head_paths():
            for notes in ("1", "2", "3"):
                steps, _head, _notes = arranged(
                    path, request=Request(melody=False, chord_notes=notes)
                )
                for step in steps:
                    active = [
                        i for i, fret in enumerate(step.voicing.frets) if fret >= 0
                    ]
                    if not active:
                        continue
                    checked += 1
                    self.assertNotIn(
                        5,
                        active,
                        f"{path} --chord-notes {notes}: {step.tab_line()}",
                    )
        self.assertGreater(checked, 50, "the sweep found too few comping steps")

    def test_the_step_still_carries_the_written_melody(self):
        """It is the horn's line, and the band lines up against it.

        Dropping it would leave the guitar part with nothing to check the chord name
        against, so `step.melody` is the written note and only the *playing* of it is
        given away.
        """
        for step, triple in zip(self.comped(), PROGRESSION):
            self.assertEqual(step.chord, triple[1])

    def test_every_step_is_a_guide_tone_shape_of_the_requested_arity(self):
        """`partial` is set, because the chord name above describes the harmony only.

        The arity is asserted rather than assumed, because `Request(melody=False)` states
        the chord alone, and the first version of the generator always built a three-note
        shell regardless.
        """
        for step in self.comped():
            self.assertEqual(step.grip, "shell")
            self.assertEqual(
                len(step.voicing.active_frets()), 3,
                step.tab_line(),
            )
            self.assertTrue(step.partial)

    def test_every_step_states_the_guide_pair(self):
        """Both guide tones sound: the 3rd and the 7th, which is what a shell claims.

        The degree rule the comping route ships with, asserted here because nothing else
        pins it: a shell states *which* chord it is through its 3rd and 7th, so a shape
        that sounds a root and a 5th instead would be a different part with the same
        arity. The chord part states the guide pair, and `texture` is what decides how
        many of the chord's other tones join them.
        """
        for step, triple in zip(self.comped(), PROGRESSION):
            name = triple[1]
            sounding = {midi % 12 for midi in step.voicing.upper_midi_notes()}
            self.assertTrue(
                guide_pcs(name) <= sounding,
                f"{name}: {step.tab_line()} sounds {sorted(sounding)} without both "
                f"guide tones {sorted(guide_pcs(name))}",
            )

    def test_the_texture_axis_still_decides_where_notes_fall(self):
        """`voices` and `texture` are orthogonal, not one mode between them."""
        steps = self.comped(chord_notes="targets", timings=self.timings)
        roles = [step.role for step in steps]
        self.assertIn("target", roles)
        self.assertIn("fill", roles)

    def test_a_fill_comps_rather_than_singing(self):
        """A texture fill is thin, but it is thin *with a chord*.

        Measured: before `melody_alone_case` learned about the axis, every fill under
        `--texture targets --bass-style root,5th,approach,nearest` came back as a bare melody note - the guitar
        playing the tune it had been told to give away, on the weak beats only. The
        assertion is on the *shape*, not on the melody's pitch class, which a comping
        shape may legitimately share; see `test_the_generator_never_reads_the_melody`.
        """
        for step in self.comped(chord_notes="targets", timings=self.timings):
            self.assertEqual(
                len(step.voicing.active_frets()), 3,
                step.tab_line(),
            )
            self.assertEqual(step.grip, "shell", step.tab_line())
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_the_bass_axis_still_decides_the_bottom(self):
        """`bass_notes="walk"` walks under a comping part, and `bass_on="none"` does not.

        This is the band setting as a whole: both layers named, and neither inferred
        from the other.
        """
        walked = self.comped(
            chord_notes="targets",
            bass_on="every-beat",
            bass_notes="walk",
            timings=self.timings,
        )
        self.assertTrue(any(step.bass is not None for step in walked))
        silent = self.comped(chord_notes="targets", bass_on="none", timings=self.timings)
        self.assertTrue(all(step.bass is None for step in silent))
        for step in silent:
            self.assertFalse(step.melody_voiced)

    def test_the_bass_notes_reach_the_engine_through_the_options(self):
        """The request's bass content reaches the engine rather than being dropped.

        The walk is handed over as options - which is how the slot layer hands over
        every request, `arranger head` among them - so a request whose bass content
        never reached the engine would be dropped silently, with every tab unchanged.
        """
        by_request = self.engine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(
                request=Request(
                    melody=False,
                    chord_notes="targets",
                    bass_on="every-beat",
                    bass_notes="walk",
                ),
                timings=self.timings,
            ),
        )
        self.assertTrue(any(step.bass is not None for step in by_request))

    def test_the_bass_axis_is_not_a_keyword_on_the_entry_point(self):
        """The five axes are the implementation, so they have no keyword spelling.

        A call naming one is unspellable rather than conflicting.
        """
        signature = inspect.signature(self.engine.arrange_progression)
        self.assertNotIn("bass", signature.parameters)

    def test_the_bass_axis_survives_the_slot_layer(self):
        """The head command's own path: the request becomes an `ArrangeOptions` here.

        `arrange_slots` is the layer that builds the options and calls the engine, so
        this is the route `arranger head` actually takes. Asserted on the thumb notes,
        because a walk that reached the layer and was dropped inside it would leave
        every tab unchanged.
        """
        from arranger.slots import arrange_slots

        steps, _rescued, _notes = arrange_slots(
            PROGRESSION,
            self.timings,
            options=ArrangeOptions(
                request=Request(melody=False, bass_on="every-beat", bass_notes="walk"),
            ),
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        self.assertTrue(any(step.bass is not None for step in steps))

    def test_an_nc_bar_is_emitted_silent_with_the_reason(self):
        """An `NC` bar has no chord, so there is no guide tone to state.

        The guitar is genuinely silent there, and the position is still **emitted**
        (item 4): a part that quietly omits a bar reads as a mistake, and a reader
        lining the comp against the tune needs the bar to be there. `silence` is
        what the tab's line reads for the reason, so it is what is asserted.
        """
        steps = self.engine.arrange_progression(
            [("D5", "Dm7"), ("C5", "NC"), ("A4", "A7")],
            options=ArrangeOptions(request=Request(melody=False)),
        )
        self.assertEqual([step.chord for step in steps], ["Dm7", "NC", "A7"])
        self.assertEqual(steps[1].silence, "nc_comping")
        self.assertEqual(steps[1].voicing.frets, [-1] * 6)

    def test_the_corpus_nc_bar_keeps_its_place_in_the_tab(self):
        """The measured case: `Trouble_in_Mind_Blues` bar 1 is `NC`.

        The bar is present under every selection that reaches the comping route, and
        every position in it is silent with the same reason - so a reader lining the two
        parts up is not one bar short with nothing to say which bar went, while the horn
        plays in it.
        """
        from tests.support import arranged

        path = "tests/data/Trouble_in_Mind_Blues.musicxml"
        rows = (
            ("chord", Request(melody=False)),
            ("chord+bass", Request(melody=False, bass_on="melody", bass_notes="root")),
            (
                "bass",
                Request(melody=False, chord_on="none", bass_on="melody", bass_notes="root"),
            ),
        )
        for label, selection in rows:
            steps, head, _notes = arranged(path, request=selection)
            bars = sorted(
                bar for bar in {step.bar for step in steps} if bar is not None
            )
            self.assertIn(1, bars, f"bar 1 vanished under {label}")
            nc = [step for step in steps if step.silence == "nc_comping"]
            self.assertTrue(nc, f"no silent NC position under {label}")
            self.assertTrue(
                all(not step.voicing.active_frets() for step in nc),
                f"a silent NC position sounds something under {label}",
            )
            # Every bar the tune has is in the tab, bar 1 included.
            tune_bars = {note.bar for note in head.notes}
            self.assertTrue(
                tune_bars <= set(bars),
                f"bars missing under {label}: {sorted(tune_bars - set(bars))}",
            )


class TestCompingMelodyIndependence(unittest.TestCase):
    """What a melody pitch may and may not change on the comping route.

    The *placement* invariant holds: a slot's `bar`/`beat` never depends on the melody, so
    scrambling every pitch moves no fret. The *harmony* does depend on it, under a
    strategy that substitutes. Both halves are asserted below;
    `docs/history/comping-styles.md` §9.3 holds the reasoning.
    """

    #: The bars these tests arrange. See `_arrange`: the claim is about how a melody pitch
    #: reaches the comping part, which eight bars of the tune settle.
    SECTION = (1, 8)

    def _arrange(self, head, request, non_chord_tone="extension"):
        """The `arrange_xml_head` comping path over an already-loaded head.

        `onsets` is computed the way `arrange_xml_head` computes it, so this exercises
        the real §9.2 guard rather than the all-onsets default a bare `arrange_slots`
        call would take.

        **`SECTION` bounds it, and the claim is why.** What is asserted is *how* a melody
        pitch reaches the comping part - the placement is blind to it, the harmony is not -
        and eight bars of the tune exhibit both. The scramble is the same function of the
        pitch either way, so the extra bars of a 32-bar tune were repeated evidence.
        """
        from arranger.slots import arrange_slots
        from headxml import _merge_chord_slots, head_skeleton, melody_state

        slots = head_skeleton(head, self.SECTION)
        resolved = resolve_request(request, head.beats_per_bar, head.grouping)
        if not parts_has_melody_only(resolved.parts):
            slots = _merge_chord_slots(slots, head, None) or slots
        onsets = {
            index
            for index, slot in enumerate(slots)
            if melody_state(head, slot[1], slot[2]) == "onset"
        }
        steps, _, _ = arrange_slots(
            [slot[0] for slot in slots],
            [(slot[1], slot[2], slot[3]) for slot in slots],
            options=ArrangeOptions(
                request=request,
                time_signature=TimeSignature(head.beats_per_bar, head.beat_type),
                non_chord_tone=non_chord_tone,
            ),
            onsets=onsets,
        )
        return tuple((step.bar, step.beat, step.chord, tuple(step.voicing.frets)) for step in steps)

    def _scrambled(self, head):
        """The head's chords, bars, beats and durations intact; only the pitches wild."""
        import copy

        scrambled = copy.deepcopy(head)
        for index, note in enumerate(scrambled.notes):
            note.pitch = 81 + (index * 3) % 14  # F#5-F6, mostly outside
        scrambled.notes.sort(key=lambda n: (n.bar, n.beat))
        return scrambled

    def _path(self):
        import os

        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data",
            "synthetic_cut_time.mxl",
        )

    def test_scrambling_the_melody_moves_no_fret_without_a_strategy(self):
        """Under `sustain` the melody cannot move a fret - the original step 0 claim.

        `sustain` substitutes nothing on the comping route (its hold-the-previous-voices
        move is a melody-route one), so this is the placement invariant alone: every
        pitch replaced by a wild high non-chord tone and nothing moves. `HeadNote.note_name`
        derives from `pitch`, so assigning `pitch` alone is enough - assigning
        `note_name` raises.
        """
        from headxml import load_musicxml

        for label, selection in (
            ("chord", Request(melody=False)),
            ("chord+bass", Request(melody=False, bass_on="melody", bass_notes="root")),
            (
                "bass",
                Request(melody=False, chord_on="none", bass_on="melody", bass_notes="root"),
            ),
        ):
            with self.subTest(selection=label):
                head = load_musicxml(self._path())
                before = self._arrange(head, selection, non_chord_tone="sustain")
                self.assertTrue(before, "an arrangement with no steps at all is a defect")
                self.assertEqual(
                    self._arrange(
                        self._scrambled(head), selection, non_chord_tone="sustain"
                    ),
                    before,
                    f"{label}: a melody pitch reached the comping part with no strategy",
                )

    def test_a_substituted_melody_reaches_the_harmony_and_not_the_placement(self):
        """Under the default strategy the melody moves the *harmony*, never a *position*.

        Two claims in one, and the split between them is why step 0 existed: the
        `(bar, beat)` positions are identical whatever the melody does (the placement
        invariant survives), while the chord the guitar states at an onset now follows
        the horn's note (step C's intended change).
        """
        from headxml import load_musicxml

        head = load_musicxml(self._path())
        scrambled = self._scrambled(head)
        substituted = self._arrange(scrambled, Request(melody=False))  # default extension
        unsubstituted = self._arrange(
            scrambled, Request(melody=False), non_chord_tone="sustain"
        )
        self.assertEqual(
            [(step[0], step[1]) for step in substituted],
            [(step[0], step[1]) for step in unsubstituted],
            "a melody pitch moved a slot's position",
        )
        self.assertNotEqual(
            substituted,
            unsubstituted,
            "the non-chord-tone strategy did not reach the comping harmony",
        )


class TestTheSopranoIsPerSlotNotPerRoute(unittest.TestCase):
    """§9.3 step D: the guitar sings a slot only where the tune *articulates*.

    `parts_have_melody` answers the arrangement-level half of the route; the other
    half is per slot. A soprano-named selection still **comps** the positions its tune is
    silent at, or merely sustains through, so a rhythm of the **ands** with the tune still
    ours places chords on the offbeats instead of being ignored. The written onsets are
    untouched - that is the acceptance criterion, and the engine's own union generates
    positions of its own too (at each bar's own subdivision), so an axis spelling is not
    inert either but still invents no melody - see
    `test_the_default_request_invents_no_melody`.

    "Does the guitar sing this slot?" reuses §9.2's onset signal rather than re-deriving
    it: a position the melody only *holds* through is not an onset, so the guitar states
    the chord there rather than re-articulating a note it did not begin under.
    """

    def _path(self):
        import os

        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "synthetic_cut_time.mxl"
        )

    def _arrange(self, request=None, chord_on="1and,2and"):
        """A **requested** rhythm over the cut-time head, so the comps land on the ands.

        `chord_on` spells the rhythm for the callers that want the shipped selection; a
        caller with a selection of its own passes the whole request, because a
        melody-only selection names no chord position for a rhythm to move.
        """
        from tests.support import arranged

        return arranged(
            self._path(),
            request=Request(chord_on=chord_on) if request is None else request,
        )

    def test_a_singing_selection_comps_the_positions_it_does_not_sing(self):
        """A requested rhythm is not ignored when the guitar has the tune."""
        steps, _head, _notes = self._arrange()
        comps = [s for s in steps if not s.melody_voiced]
        self.assertTrue(comps, "the rhythm was ignored on a singing selection")
        for step in comps:
            # A comp states the chord and invents no melody; the written symbol is kept.
            self.assertTrue(step.voicing.active_frets(), step.tab_line())
            self.assertFalse(step.grip == "melody", step.tab_line())

    def test_the_comp_arity_excludes_the_silent_soprano(self):
        """The shape is the voices that will sound: four voices state a three-note shell.

        The soprano has no note to sing at these positions, so it is not one of the
        sounding voices - which is why `soprano,alto,tenor,bass` states three notes on
        the offbeats, not a four-voice shape with a redundant root. (The four-note
        comping shape is §9.4 and needs new string sets - deliberately not this step.)
        """
        steps, _head, _notes = self._arrange()
        comps = [s for s in steps if not s.melody_voiced]
        self.assertTrue(comps)
        for step in comps:
            self.assertEqual(len(step.voicing.active_frets()), 3, step.tab_line())

    def test_every_comp_sounds_only_chord_tones(self):
        """A comping shape is held to the full tone set of the chord it states."""
        steps, head, _notes = self._arrange()
        for step in steps:
            if step.melody_voiced:
                continue
            allowed = chord_pcs(step.chord)
            sounding = {pitch % 12 for pitch in step.voicing.midi_notes()}
            self.assertTrue(sounding <= allowed, step.tab_line())

    def test_no_written_note_is_dropped_by_the_rhythm(self):
        """The rhythm *adds* positions; it never removes a written note's slot."""
        from headxml import head_skeleton

        steps, head, _notes = self._arrange()
        at = {(step.bar, step.beat): step for step in steps}
        written = head_skeleton(head, None)
        self.assertTrue(written)
        for triple, bar, beat, _duration in written:
            note = triple[0]
            self.assertIn((bar, beat), at, f"{note} at bar {bar} beat {beat} went missing")
            self.assertEqual(at[(bar, beat)].melody, note)

    def test_the_default_request_invents_no_melody(self):
        """The default request adds no position, and never a *note* of the tune.

        What must hold is that **no invented pitch reaches a singing part**: every step
        either carries a written note at its written position, or carries none at all -
        and the ones that carry none are positions the tune is *silent* at rather than
        positions it wrote. The engine's own union, which does add positions, is held to
        the same rule by
        `test_headxml_timeline.py::TestChordSlots::test_every_added_position_is_one_the_tune_is_silent_at`.
        """
        from headxml import head_skeleton, melody_state

        steps, head, _notes = self._arrange(chord_on="melody")
        written = {(bar, round(beat, 6)) for _t, bar, beat, _d in head_skeleton(head, None)}
        self.assertTrue(steps)
        for step in steps:
            bar, beat = step.bar or 0, step.beat or 0.0
            if (bar, round(beat, 6)) in written:
                continue
            self.assertIsNone(step.melody, step.tab_line())
            self.assertEqual(
                melody_state(head, bar, beat),
                "silent",
                step.tab_line(),
            )

    def test_a_melody_only_selection_adds_nothing(self):
        """The guitar plays the tune and nothing else, so it never comps a grid position."""
        steps, _head, _notes = self._arrange(request=Request(chord_on="none"))
        self.assertTrue(steps)
        self.assertTrue(all(step.melody_voiced for step in steps))
        self.assertTrue(all(len(step.voicing.active_frets()) == 1 for step in steps))


class TestTheNonChordToneStrategyReachesTheCompingRoute(unittest.TestCase):
    """§9.3 step C: `--non-chord-tone` harmonises the guitar's *comping* part too.

    The melody is the horn's, so the flag moves the chord the guitar **states** and
    nothing it sings: `melody_voiced` stays `False`, the shape is still a guide-tone
    comping shape, drawn now from the substituted chord, and `melody_pc` stays `None`
    so that shape is held to the substitute's full tone set.
    """

    def _comp(self, progression, strategy, **kwargs):
        steps = VoiceLeadingEngine.arrange_progression(
            progression,
            options=ArrangeOptions(
                request=Request(melody=False), non_chord_tone=strategy, **kwargs
            ),
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_extension_absorbs_the_note_as_an_extension(self):
        steps = self._comp([("D5", "Cmaj7")], "extension")
        self.assertEqual([s.harmonized_as for s in steps], ["Cmaj9"])
        # `chord` stays the written symbol; `harmonized_as` says what was stated.
        self.assertEqual([s.chord for s in steps], ["Cmaj7"])
        self.assertTrue(steps[0].non_chord_tone)
        self.assertEqual(steps[0].strategy, "extension")

    def test_diminished_states_the_dim7_a_semitone_below_the_resolution(self):
        steps = self._comp([("D5", "Cmaj7")], "diminished")
        self.assertEqual([s.harmonized_as for s in steps], ["Bdim7"])
        self.assertEqual(steps[0].strategy, "diminished")

    def test_the_guitar_still_does_not_sing_the_substitute(self):
        """`melody_voiced` stays false and the shape is only the substitute's tones.

        `melody_pc` is `None` on this route, so the selector cannot excuse a wrong note
        for coinciding with the tune - every sounding pitch must be a tone of the chord
        actually stated, `Bdim7`.
        """
        steps = self._comp([("D5", "Cmaj7")], "diminished")
        self.assertFalse(steps[0].melody_voiced)
        sounding = {pitch % 12 for pitch in steps[0].voicing.midi_notes()}
        self.assertTrue(sounding <= chord_pcs("Bdim7"), steps[0].tab_line())

    def test_sustain_substitutes_nothing(self):
        """The one strategy with no comping meaning leaves the written chord alone.

        A comping shape is built fresh on every slot, so `sustain`'s hold-the-previous
        move has nothing to act on and it must fall through to no substitution.
        """
        steps = self._comp([("D5", "Cmaj7")], "sustain")
        self.assertIsNone(steps[0].harmonized_as)
        self.assertIsNone(steps[0].strategy)
        self.assertFalse(steps[0].non_chord_tone)

    def test_a_chord_tone_melody_is_untouched(self):
        """A melody the chord already contains is not reharmonised under any strategy."""
        for strategy in ("extension", "diminished"):
            with self.subTest(strategy=strategy):
                steps = self._comp([("C5", "Cmaj7")], strategy)
                self.assertIsNone(steps[0].harmonized_as, strategy)

    def test_the_onset_guard_skips_a_held_position(self):
        """§9.2: a non-chord note is substituted where it **begins**, not where it holds.

        Index 1 is deliberately absent from `melody_onsets`, so it is a held position
        carrying the same note - it must be voiced as the written chord, not re-decided
        under a note whose onset already decided it.
        """
        progression = [("D5", "Cmaj7"), ("D5", "Cmaj7")]
        steps = self._comp(progression, "diminished", melody_onsets={0})
        self.assertEqual(steps[0].harmonized_as, "Bdim7")
        self.assertIsNone(steps[1].harmonized_as)

    def test_a_bare_call_with_no_timeline_treats_every_slot_as_an_onset(self):
        """`melody_onsets=None` (the default) is all-onsets - the hand-built caller's rule."""
        progression = [("D5", "Cmaj7"), ("D5", "Cmaj7")]
        steps = self._comp(progression, "diminished")
        self.assertEqual([s.harmonized_as for s in steps], ["Bdim7", "Bdim7"])

    def test_the_substitution_is_reported(self):
        """A guitarist with no melody on their part must be told why the chord moved.

        Asserted on the step's `harmonized_as` and `strategy`, which are the fields
        `annotation._substitution_clause` reads - so this is the same fact the tab line
        phrases, rather than a second spelling of it. One triple in, one step out:
        the fixture is a single slot, so a second element would mean the route
        duplicated it.
        """
        steps = self._comp([("D5", "Cmaj7")], "diminished")
        self.assertEqual(len(steps), 1)
        self.assertEqual([s.harmonized_as for s in steps], ["Bdim7"])
        self.assertTrue(all(s.strategy for s in steps))

    def test_the_fallback_fires_at_onsets_only(self):
        """`--fallback` obeys the same §9.2 guard, at the slot layer where it lives.

        `D` over `Bbm7` is the major 3rd over a minor chord - no `NON_CHORD_TONE_EXTENSIONS`
        route - so `--fallback diminished` rescues it at an onset. The same note held at
        index 1 is not an onset and must be left alone.
        """
        from arranger.slots import arrange_slots

        progression = [("D5", "Bbm7"), ("D5", "Bbm7")]
        timings = [(0, 1.0, 1.0), (0, 1.5, 0.5)]
        steps, rescued, _notes = arrange_slots(
            progression,
            timings,
            options=ArrangeOptions(request=Request(melody=False)),
            fallback="diminished",
            onsets={0},
        )
        self.assertEqual(rescued, [0])
        self.assertNotEqual(steps[0].chord, "Bbm7")
        self.assertEqual(steps[1].chord, "Bbm7")


class TestTheCompingRouteCarriesAThumb(unittest.TestCase):
    """The thumb line must not be refused for a palette the comping route never plays.

    **`bass_allowed` was asked about `TEXTURE_GRIPS` on a route where it is inert.**
    That table describes the shapes `get_all_grip_voicings` generates; on the comping
    route the shapes come from `get_comping_voicings` and the chord content is a
    meaningless name there - measured on `tests/data/synthetic_cut_time.mxl`, all 80
    comping shapes are byte-identical under `chord_notes="full"` and `chord_notes="targets"`.

    So the walk beside a comping selection - `Request(melody=False, bass_on="every-beat",
    bass_notes="walk")` - was refused under the default content, naming a chord setting
    that could not change the outcome, and emitted no thumb at all; the same request with
    `chord_notes="targets"` emitted 127.

    The existing `test_the_bass_axis_still_decides_the_bottom` passed throughout, because
    it spelled `chord_notes="targets"` - the one content that happened to fit. These tests
    pin the invariant rather than the workaround: **the chord content is inert on this
    route, so it must not appear in the decision.**
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        # The same hand-written progression and timings the arrangement class above
        # uses. `test_the_walked_beats_reach_the_part` depends on the timings being
        # denser than the four notes, since it asserts that a walk can invent beats -
        # so they are spread over four beats rather than sitting on all four slots.
        self.timings = [(0, 1.0, 1.0), (0, 2.0, 1.0), (0, 2.5, 0.5), (0, 3.5, 0.5)]

    def comped(self, **request_kwargs):
        # `melody=False` with a bass position: the thumb line is the bass part, and a
        # bass style with no bass part is refused ("add 'bass' to parts"). This class
        # is the one that carries a thumb, so it names both.
        steps = self.engine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(
                request=Request(melody=False, **request_kwargs),
                timings=self.timings,
            ),
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_the_default_texture_admits_a_thumb_line(self):
        """The regression itself: a walk under the default texture.

        Asserted on the *thumb notes* rather than on the warning, because a fix that
        merely quieted the warning while still dropping the line would pass otherwise.
        """
        steps = self.comped(bass_on="every-beat", bass_notes="walk")
        self.assertTrue(
            any(step.bass is not None for step in steps),
            "the comping route emitted no thumb notes at all",
        )

    def test_the_texture_changes_the_arity_and_nothing_else_on_this_route(self):
        """How many notes the comping part states is the texture's; the slots are not.

        The claim is the split between the two: the texture decides the count
        (`chord1`/`chord2`/`chord3`), and the harmony timeline, the slot structure and the
        role are untouched by it.
        """
        baseline: Optional[list] = None
        for notes, ceiling in (
            ("1", 1), ("2", 2), ("3", 3), ("full", 3),
        ):
            steps = self.comped(bass_on="every-beat", bass_notes="walk", chord_notes=notes)
            for step in steps:
                # The **upper** voices: the thumb is merged into the fret vector
                # after the comping shape is chosen, so it is not one of the notes
                # the arity counts.
                self.assertLessEqual(
                    len(step.voicing.upper_midi_notes()), ceiling, step.tab_line()
                )
            structure = [(s.bar, s.beat, s.chord, s.role) for s in steps]
            if baseline is None:
                baseline = structure
                continue
            self.assertEqual(
                structure, baseline,
                f"chord_notes={notes} moved a slot rather than thinning one",
            )

    def test_bass_none_is_still_honoured_on_this_route(self):
        """The fix removed a refusal, not the axis.

        Without this, "the thumb line now appears" and "the thumb line always appears"
        would be indistinguishable, and the second is the bug's mirror image.
        """
        steps = self.comped(bass_on="none", chord_notes="full")
        self.assertTrue(all(step.bass is None for step in steps))

    def test_the_walked_beats_reach_the_part(self):
        """The union is built on this route now, so a walk invents its own beats.

        `walking_slots` unions the melody grid with the walked beats. It was never
        called here, because the refusal made `has_thumb` False first - so this is the
        observable consequence of the fix rather than of the axis: a bar the melody
        barely visits still carries four quarters, and the part has more steps than the
        head had notes.

        **Compared against `bass_on="none"` and not against a texture.** Both textures build
        the same union, because the texture does not reach this decision. A test asserting
        the texture *changes* the step count here would pin a bug.
        """
        walked = self.comped(bass_on="every-beat", bass_notes="walk")
        silent = self.comped(bass_on="none")
        # Four written notes, and the walk adds the two beats the melody skips.
        self.assertEqual(len(silent), 4, "the head is four notes in one bar")
        self.assertEqual(len(walked), 6, "the walk should add the two empty beats")
        self.assertGreater(
            len(walked), len(silent),
            "a walking line adds no beats, so the walk is not being heard",
        )


class TestTheRhythmAttacksPositionsTheProgressionAlreadyHas(unittest.TestCase):
    """`chord_on` selects among the arrangement's own positions; it never adds one.

    The producer that *invents* positions is the importer's - one per subdivision of each
    bar's own rhythm (`headxml.chord_slots`) - which is what lets a comping part state the
    chord of the tune in a bar the tune never enters. A progression written in code has no
    such generator: its positions are its entries and their `timings`, so a rhythm naming a
    position none of them occupies leaves the guitar **resting** rather than inventing the
    beat - and the rest is emitted, so the part still lines up against the tune. Spelling
    the rhythm in the progression is how a caller comps one.
    """

    NAMES = ("Dm7", "G7", "Cmaj7", "A7")

    def _steps(self, chord_on, progression=None, timings=None):
        return VoiceLeadingEngine().arrange_progression(
            [(None, name) for name in self.NAMES]
            if progression is None
            else progression,
            timings=timings,
            request=Request(melody=False, chord_on=chord_on),
        )

    @staticmethod
    def _sounding(steps):
        """The beats a chord is actually struck on, read off the tab rather than a flag."""
        return [step.beat for step in steps if step.voicing.active_frets()]

    def test_a_named_position_the_progression_occupies_attacks(self):
        """Beats 1 and 3 are entries, so `1,3` comps them and rests the two between.

        The rests are asserted to be **steps of their own** carrying the chord's name and
        a reason, which is what keeps the comp lined up against the tune rather than being
        one bar short.
        """
        steps = self._steps("1,3")
        self.assertEqual([step.beat for step in steps], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(self._sounding(steps), [1.0, 3.0])
        for step in steps:
            if step.voicing.active_frets():
                self.assertIsNone(step.silence, step.tab_line())
                continue
            self.assertEqual(step.silence, SILENCE_GRID, step.tab_line())
            self.assertIn(step.chord, self.NAMES, step.tab_line())

    def test_a_named_position_the_progression_does_not_occupy_is_a_rest(self):
        """`1and` is a position four entries at 1-4 do not have, so nothing sounds.

        A count as well as the assertion: a request that emitted no step at all would
        satisfy "nothing sounds" silently, and the point is that the *rests* are emitted.
        """
        steps = self._steps("1and")
        self.assertEqual(len(steps), 4)
        self.assertEqual(self._sounding(steps), [])
        for step in steps:
            self.assertEqual(step.silence, SILENCE_GRID, step.tab_line())

    def test_the_rhythm_is_compped_when_the_progression_spells_it(self):
        """The positive half: the offbeats are reachable, as entries of their own.

        A bar whose entries include 1.5 and 2.5 answers `every-beat` with the two beats -
        the same request that left a four-entry bar silent above.
        """
        progression = [(None, name) for name in ("Dm7", "Dm7", "G7", "G7")]
        timings = [(1, beat, 0.5) for beat in (1.0, 1.5, 2.0, 2.5)]
        steps = self._steps("every-beat", progression=progression, timings=timings)
        self.assertEqual([step.beat for step in steps], [1.0, 1.5, 2.0, 2.5])
        self.assertEqual(self._sounding(steps), [1.0, 2.0])

    def test_the_importer_is_the_other_producer_of_positions(self):
        """The same request that leaves a bare progression silent comps a written head.

        The difference between the two entry points, asserted rather than assumed: the
        importer's union generates the position, so `1and` is a place on the metre's grid
        there and no place at all here.
        """
        import os

        from tests.support import arranged

        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "synthetic_cut_time.mxl"
        )
        steps, _head, _notes = arranged(
            path, request=Request(melody=False, chord_on="1and")
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        self.assertTrue(
            self._sounding(steps),
            "the importer's union did not produce the requested position",
        )
        for step in steps:
            if not step.voicing.active_frets():
                continue
            self.assertEqual(step.beat % 1, 0.5, step.tab_line())


class TestTheCompStaysUnderTheTune(unittest.TestCase):
    """A stab never sounds at or above the tune note in force.

    The comp part is an accompaniment, so its top voice sits below the tune: a shape whose
    soprano *is* the tune's pitch restrikes the note, and where the tune is holding it the
    shape takes the fingered string and cuts the tie (`TestATieEndsAtAStab`). The narrowing
    is `comp_line_route.leaving_room_for_the_tune`, applied before the ranking so the cost
    tuple is unchanged and no criterion learns about the tune.
    """

    def test_the_ceiling_is_strict(self):
        """A shape whose top *is* the tune's pitch is refused; one below it is kept.

        Strict rather than "not above": a shape that tops out on the tune's own pitch is
        the note restruck on the chord's string, which is the sound the rule exists to
        avoid. Measured on B3-string shapes over a held `Eb4`: the `Eb4` shape and the
        `E4` one both go, the `D4` one stays.
        """
        below = make_voicing([-1, -1, -1, 7, -1, -1])   # G string 7 = D4
        at = make_voicing([-1, -1, -1, -1, 4, -1])      # B string 4 = Eb4
        above = make_voicing([-1, -1, -1, 9, -1, -1])   # G string 9 = E4
        kept = leaving_room_for_the_tune(
            [above, at, below], Note("Eb4"), melody_voiced=True
        )
        self.assertEqual([voicing.midi_notes() for voicing in kept], [[62]])

    def test_nothing_below_the_tune_leaves_the_palette_alone(self):
        """A tune above every shape loses the narrowing, not the chord.

        The ceiling is a *preference* over shapes - the same trade the neck window makes -
        so a chord that cannot sit under the note is still stated. Losing the chord of the
        tune is worse than playing it high.
        """
        above = make_voicing([-1, -1, -1, 9, -1, -1])
        self.assertEqual(
            leaving_room_for_the_tune([above], Note("C4"), melody_voiced=True), [above]
        )

    def test_a_horn_line_is_not_the_guitars_ceiling(self):
        """`melody_voiced=False` is the other part's tune, so the comp stays melody-blind.

        This is the half that keeps the default inert: a comping selection's shapes are
        chosen from the chord alone, which is `TestCompingMelodyIndependence`'s claim
        about the generator holding at this layer too.
        """
        shapes = [
            make_voicing([-1, -1, -1, 7, -1, -1]),
            make_voicing([-1, -1, -1, 9, -1, -1]),
        ]
        self.assertEqual(
            leaving_room_for_the_tune(shapes, Note("Eb4"), melody_voiced=False), shapes
        )
        self.assertEqual(
            leaving_room_for_the_tune(shapes, None, melody_voiced=True), shapes
        )

    def test_the_tune_is_the_ceiling_on_a_real_slot(self):
        """`Trouble_in_Mind_Blues` bar 5 beat 1: `x-x-2-0-x-x`, top `G3`, under a held `C4`.

        The pinned tab is the acceptance gate. The ranking's answer before the ceiling was
        `x-x-5-9-x-x` - the same `G` string the tied `C4` was holding, fretted at 9, with
        its top a third *above* the tune. Under the ceiling the shape is stated an octave
        down instead, so the accompaniment is under the line rather than through it.
        """
        steps, _head, _notes = arranged(
            TROUBLE_IN_MIND,
            section=(1, 8),
            request=Request(chord_on="1", chord_notes="2"),
        )
        slot = [step for step in steps if step.bar == 5 and step.beat == 1.0]
        self.assertEqual(len(slot), 1)
        step = slot[0]
        self.assertEqual(step.melody, "C4")
        self.assertFalse(step.melody_voiced)
        self.assertEqual(step.tab_line(), "x-x-2-0-x-x")
        self.assertLess(max(step.voicing.midi_notes()), Note("C4").midi_note())

    def test_every_comp_under_a_tune_note_stays_below_it(self):
        """The corpus sweep: no comping attack reaches the tune note's pitch.

        A sweep rather than one slot, because the shape comes from a ranking: a cost
        criterion that preferred a higher top voice would satisfy the pinned slot above
        and fail here. Both a positional rhythm and the tune's own onsets are swept, so
        the held-note case and the silent-position case are both covered.
        """
        checked = 0
        for head in sweep_head_paths():
            for request in (
                Request(chord_on="1", chord_notes="2"),
                Request(chord_on="every-beat"),
            ):
                steps, _head, _notes = arranged(head, request=request)
                for step in steps:
                    if step.melody_voiced or step.melody is None:
                        continue
                    if not step.voicing.active_frets():
                        continue
                    tune = Note(step.melody).midi_note()
                    self.assertLess(
                        max(step.voicing.midi_notes()), tune,
                        f"{head} {step.chord} {step.melody} {step.tab_line()}",
                    )
                    checked += 1
        self.assertGreater(checked, 20, "the sweep stopped arranging a comp under a tune")

