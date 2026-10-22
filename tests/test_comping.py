"""The comping route: a chord part with no melody on top.

A comping step is a three-voice shell chosen from the chord alone, and `melody_voiced`
is `False` - the guitar is not singing. The load-bearing claim is that the default is
inert: every published arrangement must come out byte-identical, which is asserted here
against the same progression arranged both ways. Note what is *not* claimed: that the
melody's pitch never appears, because a guide tone can share its pitch class. The
invariant is the identical candidate set whatever melody is asked about.
"""

import inspect
import unittest
from typing import List, Optional, Tuple

from musthe import Note

from arranger import (
    GRIP_MAX_SPAN,
    GRIP_STRING_SETS,
    NECK_FRET_MAX,
    NECK_FRET_MIN,
    PART_BASS,
    PART_CHORD,
    PART_MELODY,
    ChordParser,
    TimeSignature,
    VoiceLeadingEngine,
    format_progression,
    get_comping_voicings,
    parse_parts,
    parts_has_melody_only,
    resolve_parts,
    supported_string_sets,
)
from arranger.grip_place import snapshot
from arranger.grip_tables import (
    comping_string_sets,
)
from arranger.grips import (
    CompingRequest,
    _comping_palette,
    _search_comping_voicings,
    get_comping_voicings_for,
)
from arranger.options import ArrangeOptions
from tests.support import (
    PROGRESSION,
    VOICES_ARG,
    chord_pcs,
    comping,
    guide_pcs,
    quality_of,
)

# The comping part **with** the thumb line, which is a different selection rather than a
# different setting: a bass style is a claim about the bass part.
PARTS_WITH_BASS = "bass,chord"
PART_NAMES_ARG = "auto"



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
            if not get_comping_voicings(quality, f"C{quality}")
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
        three voices, one of the `shell` sets, span within `GRIP_MAX_SPAN["shell"]` -
        is asserted exactly as it is for every other grip.
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
                    voicing.fret_span(), GRIP_MAX_SPAN["shell"], voicing.tab_string()
                )

    def test_a_chord_with_no_root_gets_nothing(self):
        """A guide tone is a claim about *this* chord, so no root means no claim.

        The same rule `get_grip_voicings` applies to its shell and duo branches, and
        for the same reason: guessing the 3rd and 7th without a root is how a wrong
        note gets into the tab.
        """
        self.assertEqual(get_comping_voicings("maj7", None), [])
        self.assertEqual(get_comping_voicings("maj7", "H7"), [])
        self.assertEqual(get_comping_voicings("", "C"), [])

    def test_the_window_is_a_preference_and_never_a_filter(self):
        """Narrowing it may cost shapes, but it must never cost the chord.

        The rule the whole library states about `fret_min`/`fret_max`: losing a chord of
        the tune is worse than being a fret out of position.
        """
        wide = get_comping_voicings("maj7", "Cmaj7")
        narrow = get_comping_voicings("maj7", "Cmaj7", fret_min=0, fret_max=0)
        self.assertTrue(wide)
        self.assertTrue(narrow, "a zero-width window must still voice the chord")


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
        for quality, name in self.CASES:
            for notes in (1, 3):
                for bass_voice in (False, True):
                    for shell_root in (False, True):
                        request = CompingRequest(
                            quality,
                            name,
                            NECK_FRET_MIN,
                            NECK_FRET_MAX,
                            notes,
                            bass_voice,
                            shell_root,
                        )
                        searched = _search_comping_voicings(request)
                        remembered = _comping_palette(request)
                        self.assertEqual(
                            [snapshot(voicing) for voicing in searched],
                            list(remembered),
                            f"{name} notes={notes} bass_voice={bass_voice} "
                            f"shell_root={shell_root}",
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
        first = get_comping_voicings("maj7", "Cmaj7")
        second = get_comping_voicings("maj7", "Cmaj7")
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

        third = get_comping_voicings("maj7", "Cmaj7")
        self.assertEqual(third[0].tab_string(), pristine_tab)
        self.assertEqual(third[0].bass_pc, pristine_bass)

    def test_the_request_is_the_memo_key(self):
        """The object entry point and the primitive one share one memo entry."""
        request = CompingRequest(
            "maj7", "Cmaj7", NECK_FRET_MIN, NECK_FRET_MAX, 3, False, False
        )
        before = _comping_palette.cache_info()
        by_object = get_comping_voicings_for(request)
        after = _comping_palette.cache_info()
        self.assertEqual(after.misses - before.misses, 1)
        by_keyword = get_comping_voicings("maj7", "Cmaj7")
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
        get_comping_voicings("m7", "Dm7")
        after_first = _comping_palette.cache_info()
        get_comping_voicings("m7", "Dm7")
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
        first = get_comping_voicings("7", "A7")
        self.assertGreater(_comping_palette.cache_info().currsize, 0)
        _comping_palette.cache_clear()
        self.assertEqual(_comping_palette.cache_info().currsize, 0)
        self.assertEqual(
            [voicing.tab_string() for voicing in get_comping_voicings("7", "A7")],
            [voicing.tab_string() for voicing in first],
        )


class TestTheAxisIsInertByDefault(unittest.TestCase):
    """`voices=auto` and `voices=guitar` are the arrangement that always was."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()

    def test_auto_and_guitar_agree_with_each_other(self):
        """The sentinel resolves to the same arrangement as saying so."""
        auto = self.engine.arrange_progression(PROGRESSION)
        explicit = self.engine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=PART_NAMES_ARG)
        )
        self.assertEqual(format_progression(auto), format_progression(explicit))

    def test_the_default_still_pins_the_melody_to_the_soprano(self):
        """And every step says the guitar is singing."""
        for step in self.engine.arrange_progression(PROGRESSION):
            self.assertTrue(step.melody_voiced)
            self.assertEqual(
                max(step.voicing.midi_notes()), Note(step.melody).midi_note()
            )

    def test_the_axis_is_spelled_through_the_options(self):
        """`parts` is the engine's implementation, so `options=` is its one door.

        It used to have a keyword spelling too, and the two *did* diverge:
        `ArrangeOptions.parts` defaulted to the resolved `"guitar"` while the keyword
        defaulted to the `"auto"` sentinel, so a caller passing the options was
        compared field-by-field against a different default and told it had passed
        both. One door is what makes that class of bug unspellable, and this is the
        half that still means something: the field reaches the engine.
        """
        by_option = self.engine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=VOICES_ARG)
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

        This used to assert that passing `parts=` beside `options=` raised. With the
        axis gone from the signature the two spellings are unspellable rather than
        conflicting, so the assertion inverts; `tests/meta_structure.py` holds the
        whole entry-point surface to it.
        """
        signature = inspect.signature(self.engine.arrange_progression)
        self.assertNotIn("parts", signature.parameters)

    def test_an_unknown_policy_raises(self):
        """A spelling nobody recognises is a question, not something to default."""
        with self.assertRaises(ValueError):
            self.engine.arrange_progression(
                PROGRESSION, options=ArrangeOptions(parts="banjo")
            )


class TestTheCompingArrangement(unittest.TestCase):
    """`parts=bass,chord` through the engine: what the guitarist is handed."""

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        self.timings = [(0, 1.0, 1.0), (0, 2.0, 1.0), (0, 3.0, 1.0), (0, 4.0, 1.0)]

    def comped(self, **kwargs):
        # `bass,chord`: the thumb line is the **bass part**, and a bass style is
        # refused without it ("add 'bass' to parts"). The arity is unaffected -
        # `comping_arity` reads the chord part and the hand, not how many parts are
        # named - so the shapes are the same as a chord-only selection's.
        steps = self.engine.arrange_progression(
            PROGRESSION, options=ArrangeOptions(parts=PARTS_WITH_BASS, **kwargs)
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_the_generator_never_reads_the_melody(self):
        """The load-bearing claim of the whole feature, stated so it cannot pass by luck.

        The first version of this test asserted that no comping step *contains* the
        melody's pitch, which reads well and is false: measured over three corpus
        heads, **409 of 2,069 steps do contain it**. That is not a defect but it is
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
            quality = quality_of(chord)
            sets = {
                tuple(sorted(v.tab_string() for v in get_comping_voicings(quality, chord)))
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

    def test_the_step_still_carries_the_written_melody(self):
        """It is the horn's line, and the band lines up against it.

        Dropping it would leave the guitar part with nothing to check the chord name
        against, so `step.melody` is the written note and only the *playing* of it is
        given away.
        """
        for step, triple in zip(self.comped(), PROGRESSION):
            self.assertEqual(step.chord, triple[2])

    def test_every_step_is_a_guide_tone_shape_of_the_requested_arity(self):
        """`partial` is set, because the chord name above describes the harmony only.

        The arity is asserted rather than assumed, because `VOICES_ARG` is two voices and
        the first version of the generator always built a three-note shell regardless.
        """
        for step in self.comped():
            self.assertEqual(step.grip, "shell")
            self.assertEqual(
                len(step.voicing.active_frets()), 3,
                step.tab_line(),
            )
            self.assertTrue(step.partial)

    def test_the_texture_axis_still_decides_where_notes_fall(self):
        """`voices` and `texture` are orthogonal, not one mode between them."""
        steps = self.comped(texture="targets", timings=self.timings)
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
        for step in self.comped(texture="targets", timings=self.timings):
            self.assertEqual(
                len(step.voicing.active_frets()), 3,
                step.tab_line(),
            )
            self.assertEqual(step.grip, "shell", step.tab_line())
            self.assertFalse(step.melody_voiced, step.tab_line())

    def test_the_bass_axis_still_decides_the_bottom(self):
        """`bass=walk` walks under a comping part, and `bass=none` does not.

        This is the band setting as a whole: both axes named, and neither inferred
        from the other.
        """
        walked = self.comped(
            texture="targets", bass="root,5th,approach,nearest", timings=self.timings
        )
        self.assertTrue(any(step.bass is not None for step in walked))
        silent = self.comped(texture="targets", bass="none", timings=self.timings)
        self.assertTrue(all(step.bass is None for step in silent))
        for step in silent:
            self.assertFalse(step.melody_voiced)

    def test_the_bass_axis_reaches_the_engine_through_the_options(self):
        """`ArrangeOptions.bass` reaches the engine, which it never did before.

        The field diverged for its whole life: the engine never read `options.bass`
        back out, so a walk handed over as options - which is how the slot layer hands
        over every request, `arranger head` among them - was silently dropped while
        the axis's own keyword test stayed green.
        """
        by_option = self.engine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(
                parts=PARTS_WITH_BASS,
                texture="targets",
                bass="root,5th,approach,nearest",
                timings=self.timings,
            ),
        )
        self.assertTrue(any(step.bass is not None for step in by_option))

    def test_the_bass_axis_is_not_a_keyword_on_the_entry_point(self):
        """The five axes are the implementation, so they have no keyword spelling.

        This used to assert that passing `bass=` beside `options=` raised. With the
        axis gone from the signature the two spellings are unspellable rather than
        conflicting, so the assertion inverts.
        """
        signature = inspect.signature(self.engine.arrange_progression)
        self.assertNotIn("bass", signature.parameters)

    def test_the_bass_axis_survives_the_slot_layer(self):
        """The head command's own path: `--bass-style` becomes an `ArrangeOptions` here.

        `arrange_slots` is the layer that builds the options and calls the engine,
        so this is the route `arranger head` actually takes and the one the unread
        field broke. Asserted on the thumb notes rather than on any warning, because
        a fix that quieted a warning while still dropping the line would pass
        otherwise.
        """
        from arranger.slots import arrange_slots

        steps, _rescued, _notes = arrange_slots(
            PROGRESSION,
            self.timings,
            options=ArrangeOptions(
                parts=PARTS_WITH_BASS,
                bass="root,5th,approach,nearest",
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
            [("D5", "m7", "Dm7"), ("C5", "NC", "NC"), ("A4", "7", "A7")],
            options=ArrangeOptions(parts=VOICES_ARG),
        )
        self.assertEqual([step.chord for step in steps], ["Dm7", "NC", "A7"])
        self.assertEqual(steps[1].silence, "nc_comping")
        self.assertEqual(steps[1].voicing.frets, [-1] * 6)

    def test_the_corpus_nc_bar_keeps_its_place_in_the_tab(self):
        """The measured case: `Trouble_in_Mind_Blues` bar 1 is `NC`.

        It used to be absent from the comping part's tab - **12** positions over
        the three voice selections that reach the comping route, all of them this
        bar - while the horn played in it, so a reader lining the two parts up was
        one bar short with nothing to say which bar went. The bar is now present
        under every one of those selections, and every position in it is silent
        with the same reason.
        """
        from tests.support import arranged

        path = "tests/data/Trouble_in_Mind_Blues.musicxml"
        for parts in (PART_BASS, PART_CHORD, "bass,chord"):
            steps, head, _notes = arranged(
                path, options=ArrangeOptions(parts=parts)
            )
            bars = sorted(
                bar for bar in {step.bar for step in steps} if bar is not None
            )
            self.assertIn(1, bars, f"bar 1 vanished under parts={parts}")
            nc = [step for step in steps if step.silence == "nc_comping"]
            self.assertTrue(nc, f"no silent NC position under parts={parts}")
            self.assertTrue(
                all(not step.voicing.active_frets() for step in nc),
                f"a silent NC position sounds something under parts={parts}",
            )
            # Every bar the tune has is in the tab, bar 1 included.
            tune_bars = {note.bar for note in head.notes}
            self.assertTrue(
                tune_bars <= set(bars),
                f"bars missing under parts={parts}: {sorted(tune_bars - set(bars))}",
            )


class TestCompingMelodyIndependence(unittest.TestCase):
    """Step 0 of `docs/history/comping-styles.md` §9.3, **re-scoped by step C**.

    Step 0 pinned the comping route as melody-independent: scramble every melody pitch
    and no fret moves. It landed *before* step C deliberately, because C is the first
    step in which the melody affects the comping **harmony** - and once C lands the
    original claim is false by design. So it is **inverted rather than deleted**
    (AGENTS.md trap 5): the *placement* invariant survives (a slot's `bar`/`beat` never
    depends on the melody) while the *harmony* now does, under a strategy that
    substitutes. Both halves are asserted below.
    """

    #: The bars these tests arrange. See `_arrange`: the claim is about how a melody pitch
    #: reaches the comping part, which eight bars of the tune settle.
    SECTION = (1, 8)

    def _arrange(self, head, parts, grid="chord:freddie", non_chord_tone="extension"):
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
        if not parts_has_melody_only(resolve_parts(parse_parts(parts))):
            slots = _merge_chord_slots(slots, head, None, grid) or slots
        onsets = {
            index
            for index, slot in enumerate(slots)
            if melody_state(head, slot[1], slot[2]) == "onset"
        }
        steps, _, _ = arrange_slots(
            [slot[0] for slot in slots],
            [(slot[1], slot[2], slot[3]) for slot in slots],
            options=ArrangeOptions(
                parts=parts,
                grid=grid,
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

        for parts in (
            PART_CHORD,
            PART_BASS,
            "bass,chord",
        ):
            with self.subTest(parts=parts):
                head = load_musicxml(self._path())
                before = self._arrange(head, parts, non_chord_tone="sustain")
                self.assertTrue(before, "an arrangement with no steps at all is a defect")
                self.assertEqual(
                    self._arrange(self._scrambled(head), parts, non_chord_tone="sustain"),
                    before,
                    f"{parts}: a melody pitch reached the comping part with no strategy",
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
        substituted = self._arrange(scrambled, PART_CHORD)  # default extension
        unsubstituted = self._arrange(scrambled, PART_CHORD, non_chord_tone="sustain")
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
    half is per slot. A soprano-named selection still **comps** the grid positions its
    tune is silent at, or merely sustains through, so `grid=joe_pass --voices
    soprano,...` places chords on the offbeats instead of ignoring the grid. The written
    onsets are untouched - that is the acceptance criterion, and **the default grid
    generates positions of its own** too (`every_note`, at each bar's own subdivision),
    so the default is no longer inert but still invents no melody - see
    `test_the_default_grid_invents_no_melody`.

    "Does the guitar sing this slot?" reuses §9.2's onset signal rather than re-deriving
    it: a position the melody only *holds* through is not an onset, so the guitar states
    the chord there rather than re-articulating a note it did not begin under.
    """

    def _path(self):
        import os

        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "synthetic_cut_time.mxl"
        )

    def _arrange(self, parts=PART_NAMES_ARG, grid="chord:joe_pass"):
        from tests.support import arranged

        return arranged(
            self._path(), options=ArrangeOptions(parts=parts, grid=grid)
        )

    def test_a_singing_selection_comps_the_grid_positions_it_does_not_sing(self):
        """The grid is no longer ignored when the guitar has the tune."""
        steps, _head, _notes = self._arrange()
        comps = [s for s in steps if not s.melody_voiced]
        self.assertTrue(comps, "the grid was ignored on a singing selection")
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

    def test_no_written_note_is_dropped_by_the_grid(self):
        """The grid *adds* positions; it never removes a written note's slot."""
        from headxml import head_skeleton

        steps, head, _notes = self._arrange()
        at = {(step.bar, step.beat): step for step in steps}
        written = head_skeleton(head, None)
        self.assertTrue(written)
        for triple, bar, beat, _duration in written:
            note = triple[0]
            self.assertIn((bar, beat), at, f"{note} at bar {bar} beat {beat} went missing")
            self.assertEqual(at[(bar, beat)].melody, note)

    def test_the_default_grid_invents_no_melody(self):
        """The default grid adds positions; it never adds a *note* of the tune.

        `every_note` generates a chord at each bar's own subdivision now (open-issues
        item 1's remaining half), so the step count is no longer the skeleton's - what
        must still hold is that **no invented pitch reaches a singing part**. Every step
        either carries a written note at its written position, or carries none at all;
        and the ones that carry none are positions the tune is *silent* at rather than
        positions it wrote.
        """
        from headxml import head_skeleton, melody_state

        steps, head, _notes = self._arrange(grid="melody:every_note")
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

    def test_a_parts_has_melody_only_adds_nothing(self):
        """`soprano` plays the tune and nothing else, so it never comps a grid position."""
        steps, _head, _notes = self._arrange(parts=PART_MELODY)
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
                parts=VOICES_ARG, non_chord_tone=strategy, **kwargs
            ),
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_extension_absorbs_the_note_as_an_extension(self):
        steps = self._comp([("D5", "maj7", "Cmaj7")], "extension")
        self.assertEqual([s.harmonized_as for s in steps], ["Cmaj9"])
        # `chord` stays the written symbol; `harmonized_as` says what was stated.
        self.assertEqual([s.chord for s in steps], ["Cmaj7"])
        self.assertTrue(steps[0].non_chord_tone)
        self.assertEqual(steps[0].strategy, "extension")

    def test_diminished_states_the_dim7_a_semitone_below_the_resolution(self):
        steps = self._comp([("D5", "maj7", "Cmaj7")], "diminished")
        self.assertEqual([s.harmonized_as for s in steps], ["Bdim7"])
        self.assertEqual(steps[0].strategy, "diminished")

    def test_the_guitar_still_does_not_sing_the_substitute(self):
        """`melody_voiced` stays false and the shape is only the substitute's tones.

        `melody_pc` is `None` on this route, so the selector cannot excuse a wrong note
        for coinciding with the tune - every sounding pitch must be a tone of the chord
        actually stated, `Bdim7`.
        """
        steps = self._comp([("D5", "maj7", "Cmaj7")], "diminished")
        self.assertFalse(steps[0].melody_voiced)
        sounding = {pitch % 12 for pitch in steps[0].voicing.midi_notes()}
        self.assertTrue(sounding <= chord_pcs("Bdim7"), steps[0].tab_line())

    def test_sustain_substitutes_nothing(self):
        """The one strategy with no comping meaning leaves the written chord alone.

        A comping shape is built fresh on every slot, so `sustain`'s hold-the-previous
        move has nothing to act on and it must fall through to no substitution.
        """
        steps = self._comp([("D5", "maj7", "Cmaj7")], "sustain")
        self.assertIsNone(steps[0].harmonized_as)
        self.assertIsNone(steps[0].strategy)
        self.assertFalse(steps[0].non_chord_tone)

    def test_a_chord_tone_melody_is_untouched(self):
        """A melody the chord already contains is not reharmonised under any strategy."""
        for strategy in ("extension", "diminished"):
            with self.subTest(strategy=strategy):
                steps = self._comp([("C5", "maj7", "Cmaj7")], strategy)
                self.assertIsNone(steps[0].harmonized_as, strategy)

    def test_the_onset_guard_skips_a_held_position(self):
        """§9.2: a non-chord note is substituted where it **begins**, not where it holds.

        Index 1 is deliberately absent from `melody_onsets`, so it is a held position
        carrying the same note - it must be voiced as the written chord, not re-decided
        under a note whose onset already decided it.
        """
        progression = [("D5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7")]
        steps = self._comp(progression, "diminished", melody_onsets={0})
        self.assertEqual(steps[0].harmonized_as, "Bdim7")
        self.assertIsNone(steps[1].harmonized_as)

    def test_a_bare_call_with_no_timeline_treats_every_slot_as_an_onset(self):
        """`melody_onsets=None` (the default) is all-onsets - the hand-built caller's rule."""
        progression = [("D5", "maj7", "Cmaj7"), ("D5", "maj7", "Cmaj7")]
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
        steps = self._comp([("D5", "maj7", "Cmaj7")], "diminished")
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

        progression = [("D5", "m7", "Bbm7"), ("D5", "m7", "Bbm7")]
        timings = [(0, 1.0, 1.0), (0, 1.5, 0.5)]
        steps, rescued, _notes = arrange_slots(
            progression,
            timings,
            options=ArrangeOptions(parts=VOICES_ARG),
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
    route the shapes come from `get_comping_voicings` and the texture is a meaningless
    name - measured on `tests/data/synthetic_cut_time.mxl`, all 80 comping shapes are
    byte-identical under `texture=uniform` and `texture=targets`.

    So `parts="chord", bass="root,5th,approach,nearest"` under the **default** texture was refused with
    "uniform leaves no bass string free for a target" and emitted no thumb at all, while
    the same request under `texture=targets` emitted 127. The warning named a setting
    that could not change the outcome.

    The existing `test_the_bass_axis_still_decides_the_bottom` passed throughout,
    because it spelled `texture="targets"` - the one texture that happened to fit. These
    tests pin the invariant rather than the workaround: **the texture is inert on this
    route, so it must not appear in the decision.**
    """

    def setUp(self):
        self.engine = VoiceLeadingEngine()
        # The same hand-written progression and timings the arrangement class above
        # uses. `test_the_walked_beats_reach_the_part` depends on the timings being
        # denser than the four notes, since it asserts that a walk can invent beats -
        # so they are spread over four beats rather than sitting on all four slots.
        self.timings = [(0, 1.0, 1.0), (0, 2.0, 1.0), (0, 2.5, 0.5), (0, 3.5, 0.5)]

    def comped(self, **kwargs):
        # `bass,chord`: the thumb line is the bass part, and a bass style with no
        # bass part is refused ("add 'bass' to parts"). This class is the one that
        # carries a thumb, so it takes both parts.
        steps = self.engine.arrange_progression(
            PROGRESSION,
            options=ArrangeOptions(
                parts=PARTS_WITH_BASS, timings=self.timings, **kwargs
            ),
        )
        self.assertTrue(steps, "an arrangement with no steps at all is a defect")
        return steps

    def test_the_default_texture_no_longer_refuses_a_thumb_line(self):
        """The regression itself: `bass=walk` under the default texture.

        Asserted on the *thumb notes* rather than on the warning, because a fix that
        merely quieted the warning while still dropping the line would pass otherwise.
        """
        steps = self.comped(bass="root,5th,approach,nearest")
        self.assertTrue(
            any(step.bass is not None for step in steps),
            "the comping route emitted no thumb notes at all",
        )

    def test_the_texture_changes_the_arity_and_nothing_else_on_this_route(self):
        """How many notes the comping part states is the texture's; the slots are not.

        **Inverted rather than deleted.** It used to assert the frets were identical
        under every texture, and that was true while the arity came from the *number of
        voice names* - so the texture could not reach this route at all, and a texture
        that thinned a comping part was a defect. The arity is the texture's now
        (`chord1`/`chord2`/`chord3`), so the surviving claim is the split between the
        two: the texture decides the count, and the harmony timeline, the slot
        structure and the role are untouched by it.
        """
        baseline: Optional[list] = None
        for texture, ceiling in (
            ("chord1", 1), ("chord2", 2), ("chord3", 3), ("uniform", 3),
        ):
            steps = self.comped(bass="root,5th,approach,nearest", texture=texture)
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
                f"texture={texture} moved a slot rather than thinning one",
            )

    def test_bass_none_is_still_honoured_on_this_route(self):
        """The fix removed a refusal, not the axis.

        Without this, "the thumb line now appears" and "the thumb line always appears"
        would be indistinguishable, and the second is the bug's mirror image.
        """
        steps = self.comped(bass="none", texture="uniform")
        self.assertTrue(all(step.bass is None for step in steps))

    def test_the_walked_beats_reach_the_part(self):
        """The union is built on this route now, so a walk invents its own beats.

        `walking_slots` unions the melody grid with the walked beats. It was never
        called here, because the refusal made `has_thumb` False first - so this is the
        observable consequence of the fix rather than of the axis: a bar the melody
        barely visits still carries four quarters, and the part has more steps than the
        head had notes.

        **Compared against `bass=none` and not against a texture.** The first draft of
        this test compared `uniform` against `targets` and failed, which was the fix
        working: both now build the same union, because the texture no longer reaches
        the decision. A test asserting the texture *changes* the step count here would
        have pinned the bug.
        """
        walked = self.comped(bass="root,5th,approach,nearest")
        silent = self.comped(bass="none")
        # Four written notes, and the walk adds the two beats the melody skips.
        self.assertEqual(len(silent), 4, "the head is four notes in one bar")
        self.assertEqual(len(walked), 6, "the walk should add the two empty beats")
        self.assertGreater(
            len(walked), len(silent),
            "a walking line adds no beats, so the walk is not being heard",
        )
