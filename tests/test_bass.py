"""The walking-bass generator: `_walking_bass_line` and `bass_cost`.

This is the **pure pass** of the walking-bass texture - the one that decides *what
note* the thumb plays, and nothing else. It is deliberately not integrated into
`arrange_progression` yet, so nothing here can move an existing arrangement: the
tests below are the specification the integration (phase 5) will be held to.

What the pass is responsible for:

  - the **anchor** rule: beat 1 is the current chord's root, on every bar including
    the second bar of a two-bar chord, plus any strong beat where the harmony
    changes (decision E);
  - the **backwards** choice of beat 4, from the next anchor (decision D);
  - extensions on connective notes, so a walk is not an arpeggio and needs no key
    model;
  - the degradation when there is no beat grid at all.
"""

import unittest
from typing import List, Optional, Tuple

from arranger import (
    BASS_POLICY_ROLES,
    BASS_ROLE_ANCHOR,
    BASS_ROLE_APPROACH,
    BASS_ROLE_CONNECT,
    BASS_ROLE_ENCLOSURE,
    BASS_ROLE_HOLD,
    BASS_STYLES,
    NO_CHORD,
    PITCH_CLASS_NAMES,
    TEXTURE_STYLES,
    _bass_harmony,
    _comping_no_room_reason,
    _walking_bass_line,
    bass_allowed,
    bass_cost,
    bass_line_for,
    comping_capacity,
    thumb_capacity,
)


def line(chords, onsets, beats_per_bar=4):
    """The walked line as (bar, beat, pitch-class name, role) tuples."""
    return [
        (note.bar, note.beat, PITCH_CLASS_NAMES[note.pitch_class], note.role)
        for note in _walking_bass_line(chords, onsets, beats_per_bar)
    ]


def names(chords, onsets, beats_per_bar=4):
    """Just the notes, in order - what a reader of the tab would see."""
    return [entry[2] for entry in line(chords, onsets, beats_per_bar)]


def semitones(first, second):
    """The distance between two pitch-class names, the short way round."""
    a, b = PITCH_CLASS_NAMES.index(first), PITCH_CLASS_NAMES.index(second)
    return min((a - b) % 12, (b - a) % 12)


def permitted_for(root, quality):
    """
    A chord's bass vocabulary, asserting the chord is speakable first.

    The assertion is deliberate: a test that subscripted the Optional directly would
    raise `TypeError` rather than fail with a message, and pyright does not narrow
    through `self.assertIsNotNone` - which is exactly why the check lives here rather
    than at each call site.
    """
    harmony = _bass_harmony(root, quality)
    assert harmony is not None, f"{root}{quality} is not speakable"
    return harmony[1]


class TestAnchorRule(unittest.TestCase):
    """Beat 1 is the root, always, and a mid-bar change re-anchors."""

    def test_beat_one_is_the_root_of_every_bar(self):
        """The anchor is the chord's root, not a chord tone that happens to be near."""
        chords = [("F", "maj7", "Fmaj7"), ("G", "7", "G7"),
                  ("C", "maj7", "Cmaj7"), ("D", "7", "D7")]
        onsets = [(bar, 1.0) for bar in range(1, 5)]
        anchors = [
            entry for entry in line(chords, onsets) if entry[3] == BASS_ROLE_ANCHOR
        ]
        self.assertEqual(
            [entry[:3] for entry in anchors],
            [(1, 1.0, "F"), (2, 1.0, "G"), (3, 1.0, "C"), (4, 1.0, "D")],
        )

    def test_a_two_bar_chord_re_anchors_on_the_second_downbeat(self):
        """
        The anchor is a **metric** event, not a harmonic one. Re-striking the root
        is what marks the bar; suppressing it would leave the second bar unmarked.
        This is the regression for an earlier draft of the design, which held the
        opposite and was wrong.
        """
        walked = line([("G", "7", "G7")], [(1, 1.0), (2, 1.0)])
        downbeats = [entry for entry in walked if entry[1] == 1.0]
        self.assertEqual(
            [(entry[2], entry[3]) for entry in downbeats],
            [("G", BASS_ROLE_ANCHOR), ("G", BASS_ROLE_ANCHOR)],
        )

    def test_a_mid_bar_change_re_anchors(self):
        """
        Decision E. Bar 10 is `Bbm7` for two beats and `Eb7` from beat 3, and the
        guide's thumb states the new **root** `Eb` there. Beat 3 is already a
        left-hand target (TARGET_BEATS = (1, 3)), so without this the two hands
        would name different chords on the same beat - the one thing this texture
        must never do.
        """
        chords = [("Bb", "m7", "Bbm7"), ("Eb", "7", "Eb7")]
        anchors = [
            entry for entry in line(chords, [(10, 1.0), (10, 3.0)])
            if entry[3] == BASS_ROLE_ANCHOR
        ]
        self.assertEqual([entry[:3] for entry in anchors], [(10, 1.0, "Bb"), (10, 3.0, "Eb")])

    def test_an_unchanged_harmony_on_a_strong_beat_is_not_an_anchor(self):
        """
        The second clause of the anchor rule is a harmony *change*, so a strong beat
        that repeats the chord already stated is a connective note. Both readings of
        decision F are pinned apart here, so a later switch is a one-line change to
        this test rather than a rewrite.
        """
        walked = line([("G", "7", "G7")], [(1, 1.0), (1, 3.0)])
        beat_three = [entry for entry in walked if entry[1] == 3.0]
        self.assertEqual(len(beat_three), 1)
        self.assertNotEqual(beat_three[0][3], BASS_ROLE_ANCHOR)


class TestApproachRule(unittest.TestCase):
    """Beat 4 is chosen backwards from the next anchor (decision D)."""

    def test_the_last_beat_reaches_the_next_anchor(self):
        """
        The published tab in the design document does *not* obey this rule on most of
        its bars, so the fixture asserts the rule and the published notes are recorded
        as expected divergences rather than as expectations.
        """
        chords = [("D", "m7", "Dm7"), ("G", "7", "G7"), ("C", "maj7", "Cmaj7")]
        walked = line(chords, [(1, 1.0), (2, 1.0), (3, 1.0)])
        approaches = [entry for entry in walked if entry[3] == BASS_ROLE_APPROACH]
        self.assertEqual([(entry[0], entry[1]) for entry in approaches], [(1, 4.0), (2, 4.0)])
        # A half step from the next anchor, either way round: the cost ranks any
        # semitone ahead of a fourth, so this is the rule and not one chord's answer.
        for approach, next_anchor in zip(approaches, ("G", "C")):
            self.assertEqual(
                semitones(approach[2], next_anchor), 1,
                f"{approach[2]} does not reach {next_anchor}",
            )

    def test_the_next_anchor_is_not_yet_known_when_the_approach_is_chosen(self):
        """
        The lookahead is the reason the pass is phrase-level: beat 4 is defined by a
        note that has not happened. Dropping the last bar of the progression must
        therefore change what the previous bar's beat 4 says.
        """
        chords = [("D", "m7", "Dm7"), ("G", "7", "G7")]
        with_next = line(chords, [(1, 1.0), (2, 1.0)])
        without_next = line(chords, [(1, 1.0)])
        self.assertEqual(
            [entry[3] for entry in with_next if entry[0] == 1 and entry[1] == 4.0],
            [BASS_ROLE_APPROACH],
        )
        self.assertEqual(
            [entry[3] for entry in without_next if entry[1] == 4.0],
            [BASS_ROLE_CONNECT],
            "without a following bar there is no next anchor, so there is no approach",
        )

    def test_the_last_beat_with_no_next_anchor_is_a_connect(self):
        """Nothing to approach, so the beat falls back to the connective vocabulary."""
        self.assertEqual(line([("G", "7", "G7")], [(1, 1.0)])[-1][3], BASS_ROLE_CONNECT)


class TestEnclosure(unittest.TestCase):
    """The simplest form: a half step above the next anchor, then a half step below."""

    def test_an_enclosure_brackets_the_next_anchor(self):
        chords = [("D", "m7", "Dm7"), ("G", "7", "G7")]
        walked = line(chords, [(1, 1.0), (2, 1.0)])
        enclosures = [entry for entry in walked if entry[3] == BASS_ROLE_ENCLOSURE]
        approaches = [entry for entry in walked if entry[3] == BASS_ROLE_APPROACH]
        self.assertEqual([entry[1] for entry in enclosures], [3.0])
        self.assertEqual([entry[1] for entry in approaches], [4.0])
        for note in (enclosures[0][2], approaches[0][2]):
            self.assertEqual(semitones(note, "G"), 1, f"{note} does not bracket G")


class TestExtensions(unittest.TestCase):
    """
    The single most important property in the file. A purity-first cost ranks every
    one of these last and returns the arpeggio the arranging guide warns against
    ("pure arpeggios can sound like exercise drills").
    """

    def test_every_extension_the_table_names_is_permitted(self):
        """
        E over Dm7, A over G7, Eb over G7 and A over Cmaj7: each is a real note in
        a real walk, and each is reachable only because the permitted set includes
        the extension rather than only the chord's own tones.

        The design document calls the third of these `Bb` and a b13; Bb over G7 is
        the b5, and Eb is the b13, so `NON_CHORD_TONE_EXTENSIONS`'s `7b13` row is
        keyed on the degree that actually produces it. The library follows the table,
        which is the same "never guess a chord" rule the notation tables follow.
        """
        cases = [
            (("D", "m7", "Dm7"), 2, "E"),       # the 9th
            (("G", "7", "G7"), 2, "A"),         # the 9th
            (("G", "7", "G7"), 8, "Eb"),        # the b13
            (("C", "maj7", "Cmaj7"), 9, "A"),   # the 6th, a 6/9
        ]
        for (root, quality, name), degree, expected in cases:
            harmony = _bass_harmony(root, quality)
            self.assertIsNotNone(harmony, f"{name} is not speakable")
            # A bare `assert` rather than only `assertIsNotNone`, because pyright
            # narrows through the former and not the latter.
            assert harmony is not None
            root_pc, permitted = harmony
            self.assertEqual(PITCH_CLASS_NAMES[(root_pc + degree) % 12], expected)
            self.assertIn(
                (root_pc + degree) % 12, permitted,
                f"{expected} is not reachable under {name}",
            )

    def test_a_permitted_extension_is_not_a_chord_tone(self):
        """
        The permitted set is only interesting because it is *wider* than the chord.
        This asserts that, so a future change that quietly narrows it to purity
        cannot pass unnoticed.
        """
        permitted = permitted_for("D", "m7")
        self.assertNotEqual(set(permitted), {2, 5, 9, 0})  # D F A C
        self.assertIn(4, permitted)  # E, the 9th of Dm7

    def test_a_bar_of_four_beats_under_one_chord_is_not_an_arpeggio(self):
        """
        Asserted as a property rather than an exact string: the line under a held
        chord must move, and at least one of its notes must leave the chord's own
        tones. A cost ranking purity first would fail this.
        """
        played = names([("D", "m7", "Dm7")], [(1, 1.0)])
        self.assertEqual(len(played), 4)
        self.assertEqual(played[0], "D")
        self.assertGreater(len(set(played)), 1, "the line is a held note, not a walk")
        self.assertTrue(
            any(note not in {"D", "F", "A", "C"} for note in played),
            f"{played} is a pure arpeggio of Dm7",
        )


class TestNoKeyModel(unittest.TestCase):
    """
    The claim under test is that chord tones, the extension table and root-relative
    approaches between them are enough - so if a line needs a scale to pass, the
    extension set has a hole.
    """

    def test_a_three_bar_ii_v_i_walks_without_a_scale(self):
        chords = [("D", "m7", "Dm7"), ("G", "7", "G7"), ("C", "maj7", "Cmaj7")]
        played = names(chords, [(1, 1.0), (2, 1.0), (3, 1.0)])
        self.assertEqual([played[index] for index in (0, 4, 8)], ["D", "G", "C"])
        self.assertGreater(len(set(played)), 4, "the line barely moves")

    def test_a_dominant_to_tonic_walks_without_a_scale(self):
        chords = [("G", "7", "G7"), ("C", "maj7", "Cmaj7")]
        played = names(chords, [(1, 1.0), (2, 1.0)])
        self.assertEqual(played[0], "G")
        self.assertEqual(played[4], "C")

    def test_the_guide_line_movement_is_extensions_not_scale_degrees(self):
        """
        G-A-Eb over a G7 is the guide's own line, and its two upper notes are the 9th
        and the b13 of the chord they sit under - extensions, not scale degrees. That
        is the whole argument for reaching for the extension table in one assertion.

        The design document spells this line's third note as `Bb` and calls it the
        b13; Bb over G7 is the b5, and Eb is the b13, so the table's `7b13` row is
        keyed on the degree that actually produces it. The library follows the table
        rather than the prose, which is the same "never guess a chord" rule the
        notation tables follow.
        """
        permitted = permitted_for("G", "7")
        self.assertIn(PITCH_CLASS_NAMES.index("A"), permitted)   # the 9th
        self.assertIn(PITCH_CLASS_NAMES.index("Eb"), permitted)  # the b13


class TestGridAndHarmonyEdges(unittest.TestCase):
    """The cases the design says must be reported rather than guessed."""

    def test_no_timings_degrades_to_one_anchor_per_slot(self):
        """
        `timings=None` is the path every hand-written progression takes, so the
        degradation is asserted rather than left to be discovered.
        """
        chords = [("D", "m7", "Dm7"), ("G", "7", "G7"), ("C", "maj7", "Cmaj7")]
        played = line(chords, None)
        self.assertEqual(
            [(entry[2], entry[3]) for entry in played],
            [("D", BASS_ROLE_ANCHOR), ("G", BASS_ROLE_ANCHOR), ("C", BASS_ROLE_ANCHOR)],
        )
        self.assertEqual([entry[0] for entry in played], [None, None, None])

    def test_one_whole_note_in_a_bar_yields_four_walked_beats(self):
        """
        Decision B. The pass is keyed on onsets, not on melody slots, so a bar whose
        melody is a single whole note still yields four notes - which is the whole
        reason a held melody can sound once over a moving bass.
        """
        walked = line([("G", "7", "G7")], [(1, 1.0)])
        self.assertEqual([entry[1] for entry in walked], [1.0, 2.0, 3.0, 4.0])

    def test_an_nc_bar_continues_the_last_known_harmony(self):
        """Never a guessed one - the same rule the loaders follow."""
        chords = [("C", "maj7", "Cmaj7"), (None, None, NO_CHORD), ("G", "7", "G7")]
        walked = line(chords, [(1, 1.0), (2, 1.0), (3, 1.0)])
        bar_two = [entry for entry in walked if entry[0] == 2]
        self.assertTrue(bar_two)
        anchors = [entry for entry in bar_two if entry[3] == BASS_ROLE_ANCHOR]
        self.assertEqual([entry[2] for entry in anchors], ["C"])

    def test_an_unspeakable_quality_yields_no_notes_and_is_never_guessed(self):
        """
        A quality the library cannot voice is left out of the tables rather than
        folded into a near neighbour, and a walk that invented a harmony under the
        thumb would be worse than no walk at all.
        """
        chords = [("D", "wobble", "Dwobble"), ("G", "7", "G7")]
        played = line(chords, [(1, 1.0), (2, 1.0)])
        self.assertEqual({entry[0] for entry in played}, {2})
        self.assertIsNone(_bass_harmony("D", "wobble"))

    def test_an_empty_progression_yields_no_notes(self):
        self.assertEqual(_walking_bass_line([], None), [])

    def test_signed_bars_are_ordered_correctly(self):
        """A pickup bar is negative, and must sort before bar 1, not after it."""
        walked = line([("D", "m7", "Dm7"), ("G", "7", "G7")], [(-1, 1.0), (1, 1.0)])
        self.assertEqual([entry[0] for entry in walked[:4]], [-1, -1, -1, -1])
        self.assertEqual([entry[0] for entry in walked[4:]], [1, 1, 1, 1])


class TestBassCost(unittest.TestCase):
    """
    The cost is role-conditional, and the role is the point: being outside the chord
    is a hard filter for an anchor and a tie-break for a connective note.
    """

    def test_the_anchor_filter_is_the_root(self):
        permitted = permitted_for("D", "m7")
        root = PITCH_CLASS_NAMES.index("D")
        third = PITCH_CLASS_NAMES.index("F")
        on_root = bass_cost(root, BASS_ROLE_ANCHOR, None, 7, root, permitted)
        off_root = bass_cost(third, BASS_ROLE_ANCHOR, None, 7, root, permitted)
        self.assertLess(on_root, off_root)

    def test_a_connective_note_may_leave_the_chord(self):
        """
        Being outside the permitted set is a **tie-break**, not a veto. A 9th (E over
        Dm7) and a chromatic approach (Ab, a half step below the next root G) are
        both outside the chord's own tones, and both are reachable - a purity-first
        cost would reject them and return the arpeggio.
        """
        permitted = permitted_for("D", "m7")
        in_chord = bass_cost(5, BASS_ROLE_CONNECT, 2, 7, 2, permitted)   # F, a 3rd
        extension = bass_cost(4, BASS_ROLE_CONNECT, 2, 7, 2, permitted)  # E, the 9th
        chromatic = bass_cost(8, BASS_ROLE_CONNECT, 2, 7, 2, permitted)  # Ab
        # Both out-of-chord candidates are admissible: the criterion that separates
        # them from a chord tone is a later element, not a rejection.
        for name, cost in (("the 9th", extension), ("a chromatic approach", chromatic)):
            self.assertEqual(
                cost[0], in_chord[0], f"{name} was filtered out rather than ranked"
            )
        # And they are not *all* worse: a nearer out-of-chord note beats a more
        # distant chord tone, which is the whole point of admitting them.
        self.assertEqual(extension[2], 2)  # two semitones from D
        self.assertEqual(in_chord[2], 3)    # three
        self.assertLess(extension, in_chord, "the nearer 9th lost to the farther 3rd")
        self.assertGreater(chromatic[2], extension[2])

    def test_the_cost_prefers_motion_to_a_repeated_note(self):
        permitted = permitted_for("G", "7")
        root = PITCH_CLASS_NAMES.index("G")
        third = PITCH_CLASS_NAMES.index("F")
        repeated = bass_cost(root, BASS_ROLE_CONNECT, root, root, root, permitted)
        moving = bass_cost(third, BASS_ROLE_CONNECT, root, root, root, permitted)
        self.assertLess(moving, repeated)

    def test_a_held_note_is_always_last(self):
        permitted = permitted_for("G", "7")
        root = PITCH_CLASS_NAMES.index("G")
        third = PITCH_CLASS_NAMES.index("F")
        held = bass_cost(root, BASS_ROLE_HOLD, root, root, root, permitted)
        for role in (BASS_ROLE_CONNECT, BASS_ROLE_APPROACH, BASS_ROLE_ENCLOSURE):
            other = bass_cost(third, role, root, root, root, permitted)
            self.assertLess(other, held, f"a {role} lost to a hold")

    def test_an_approach_prefers_a_half_step_to_a_fourth(self):
        permitted = permitted_for("G", "7")
        half_step = bass_cost(6, BASS_ROLE_APPROACH, 7, 7, 7, permitted)  # F#
        fourth = bass_cost(0, BASS_ROLE_APPROACH, 7, 7, 7, permitted)   # C, a 4th below G
        self.assertLess(half_step, fourth)

    def test_the_cost_is_deterministic_and_physical_term_free(self):
        """
        The tuple is built per role and contains no physical term, because the octave,
        the string and `hand_fret` cannot be known here - an earlier draft carried an
        octave term and re-decided the octave in the wrong place.
        """
        permitted = permitted_for("G", "7")
        first = bass_cost(5, BASS_ROLE_CONNECT, 7, 7, 7, permitted)
        second = bass_cost(5, BASS_ROLE_CONNECT, 7, 7, 7, permitted)
        self.assertEqual(first, second)
        self.assertTrue(all(isinstance(value, int) for value in first))


if __name__ == "__main__":
    unittest.main()


class TestTheBassPolicyRegistry(unittest.TestCase):
    """`bass=` is a policy with a name, and the set of policies is open.

    The point of the registry is that a **new bass pattern is a row in a table**, not
    another branch at each of the call sites that decide whether a thumb line exists.
    These tests are mostly about that staying true - the two tables agreeing, and no
    policy being nameable without a rule - because a registry that can be named past
    its own rules is worse than the branches it replaced.
    """

    def test_every_policy_has_a_rule_and_every_rule_has_a_policy(self):
        """`BASS_STYLES` and `BASS_POLICY_ROLES` describe the same set.

        The two differ in exactly one entry by design - `BASS_AUTO` is a default and not
        a policy - so `BASS_STYLES` minus `none` is the key set of the rule table.
        """
        self.assertEqual(
            sorted(p for p in BASS_STYLES if p != "none"),
            sorted(BASS_POLICY_ROLES),
            "a policy is nameable without a rule, or has a rule without a name",
        )

    def test_auto_is_not_a_policy(self):
        """`auto` is resolved before it reaches any of this.

        It is a default for an argument, not a pattern a caller can ask for, and keeping
        it out of `BASS_STYLES` is what lets `arrange_progression` validate `bass`
        against the policies without special-casing a sentinel.
        """
        self.assertNotIn("auto", BASS_STYLES)
        self.assertNotIn("auto", BASS_POLICY_ROLES)

    def test_walk_keeps_every_role_and_anchors_keeps_only_the_root(self):
        """`anchors` is `walk` with the connective roles dropped, not a second opinion.

        Asserted against the same generator's output so the two cannot drift: if a role
        is added to the walk, `anchors` either keeps it or it does not - but it is
        computed from the same line either way.
        """
        # Annotated rather than inferred: `List` is invariant, so a list of
        # `Tuple[str, str, str]` is not a `List[Tuple[Optional[str], str, str]]` and
        # pyright rejects it - the same trap, and the same spelling, as every other
        # timing list in this suite.
        chords: List[Tuple[Optional[str], str, str]] = [("C", "maj7", "Cmaj7")] * 8
        onsets: List[Tuple[int, float]] = [(1, 1.0 + 0.5 * i) for i in range(8)]
        walked = bass_line_for("walk", chords, onsets, 4)
        anchored = bass_line_for("anchors", chords, onsets, 4)
        self.assertGreater(len(walked), len(anchored))
        self.assertEqual({n.role for n in anchored}, {BASS_ROLE_ANCHOR})
        self.assertTrue(
            all(n.role == BASS_ROLE_ANCHOR for n in anchored),
            "anchors kept a connective role",
        )
        # Every anchored note is one the walk actually wrote, in order.
        walked_anchors = [n for n in walked if n.role == BASS_ROLE_ANCHOR]
        self.assertEqual(
            [(n.bar, n.beat, n.pitch_class) for n in anchored],
            [(n.bar, n.beat, n.pitch_class) for n in walked_anchors],
            "anchors is not a subset of walk",
        )

    def test_none_writes_no_line(self):
        self.assertEqual(bass_line_for("none", [("C", "maj7", "Cmaj7")], None, 4), [])

    def test_an_unknown_policy_raises_rather_than_defaulting(self):
        """A spelling nobody recognises is a question, not a walk.

        Defaulting here would put a bass line under an arrangement that did not ask for
        one, which is the failure mode the house rule exists to prevent everywhere else.
        """
        with self.assertRaises(KeyError):
            bass_line_for("stride", [("C", "maj7", "Cmaj7")], None, 4)


class TestThumbCapacityAndRefusal(unittest.TestCase):
    """A thumb line needs a string, and the capacity is derived not listed."""

    def test_capacity_is_read_from_the_grip_tables(self):
        """`uniform` is the one texture that can occupy every thumb string at once."""
        self.assertEqual(thumb_capacity("uniform", "target"), 0)
        targets_capacity = thumb_capacity("targets", "target")
        assert targets_capacity is not None, "a grip palette cannot be unbounded"
        self.assertGreaterEqual(targets_capacity, 1)
        # An empty palette means the left hand plays nothing: every string is free.
        self.assertIsNone(thumb_capacity("walking_bass", "fill"))
        # A melody-only *selection* is not in the grip tables at all: its upper
        # shapes are single frets, so all three thumb strings are free whatever
        # the texture's palette says, and the capacity is answered where the
        # route is known - `bass_allowed`'s `melody_only`, unbounded by
        # construction rather than measured.
        allowed, _why = bass_allowed("uniform", "walk", melody_only=True)
        self.assertTrue(allowed, "a single-fret upper shape leaves every string free")

    def test_uniform_is_refused_for_every_policy_and_the_reason_names_a_texture(self):
        for policy in (p for p in BASS_STYLES if p != "none"):
            allowed, reason = bass_allowed("uniform", policy)
            self.assertFalse(allowed, policy)
            self.assertIn("no bass string free", reason)
            self.assertIn("texture=", reason, "the refusal must say what to use instead")

    def test_the_textures_that_leave_a_string_are_allowed(self):
        for texture in TEXTURE_STYLES:
            if texture == "uniform":
                continue
            for policy in BASS_STYLES:
                allowed, _why = bass_allowed(texture, policy)
                self.assertTrue(allowed, f"{texture} + {policy}")

    def test_none_is_always_allowed(self):
        for texture in TEXTURE_STYLES:
            allowed, _why = bass_allowed(texture, "none")
            self.assertTrue(allowed, texture)


class TestCompingCapacity(unittest.TestCase):
    """The comping route's thumb capacity, which `thumb_capacity` cannot answer.

    **The defect this class exists for.** `bass_allowed` derives capacity from
    `TEXTURE_GRIPS`, which describes the shapes the *melody-bearing* route generates.
    On the comping route the shapes come from `get_comping_voicings` and the texture is
    inert, so passing a texture there refused a playable combination - and produced a
    warning telling the player to change a setting that could not affect the result.

    Measured on `tests/data/but_not_for_me.mxl` before the fix, with
    `melody="alto,tenor", bass="walk"`:

        texture=uniform    80 steps, **0 thumb notes**, warning "uniform leaves no
                           bass string free for a target"
        texture=targets   166 steps, 127 thumb notes, no warning

    The warning was false on the facts too: those 80 comping shapes sound on strings
    `(2, 3, 4, 5)` and never once on the low E or the A, so the thumb had the whole
    bottom of the neck.
    """

    def test_the_capacity_is_measured_at_every_arity(self):
        """Derived from `_comping_string_sets`, so a new arity is covered by this.

        The numbers rather than a bare `>= 1`, because "never zero" is the finding and
        a regression should say *which* arity changed rather than fail on a boolean.
        """
        self.assertEqual(comping_capacity(1), 3)
        self.assertEqual(comping_capacity(2), 2)
        self.assertEqual(comping_capacity(3), 1)
        self.assertEqual(comping_capacity(4), 1)

    def test_a_lone_bass_voice_reaches_lower_and_leaves_fewer_strings(self):
        """`bass_voice` is the one arity-1 case that occupies the thumb's own strings.

        `BASS_VOICE_STRING_SETS` is `(0, 1, 2)` - low E, A and D - because a bass stated
        alone is the bottom of the band rather than a guide tone. One note still cannot
        occupy all three, so two remain free.
        """
        self.assertEqual(comping_capacity(1, bass_voice=True), 2)

    def test_the_capacity_is_never_zero_so_the_route_cannot_be_refused(self):
        """The property the refusal rests on, stated once rather than per arity.

        Asserted over a range rather than only the arities the tests above name, so a
        fourth voice name or a future arity cannot slip past a hand-maintained list.
        """
        for notes in range(1, 8):
            for bass_voice in (False, True):
                self.assertGreaterEqual(
                    comping_capacity(notes, bass_voice), 1,
                    f"{notes} notes, bass_voice={bass_voice}",
                )

    def test_every_texture_is_allowed_on_the_comping_route(self):
        """The bug in one assertion: no texture may refuse, because none is consulted.

        This is the inverted form of `test_uniform_is_refused_for_every_policy_and_the
        _reason_names_a_texture` above. That test is **not** deleted and its premise is
        still true - `uniform` really does occupy all three thumb strings on the route it
        describes. What was wrong was asking it about a route where `uniform` is a
        meaningless name.
        """
        for texture in TEXTURE_STYLES:
            for policy in (p for p in BASS_STYLES if p != "none"):
                allowed, reason = bass_allowed(texture, policy, notes=2)
                self.assertTrue(
                    allowed,
                    f"texture={texture} + {policy} refused the comping route: {reason}",
                )

    def test_a_refusal_on_this_route_would_not_name_a_texture(self):
        """There is no texture to try instead, so the sentence must not offer one.

        `_no_room_reason` names a texture because a palette is what failed. On the comping
        route the route itself was chosen by the voice selection, and the original bug
        produced a warning that pointed at `texture=` - a setting that could not change
        the outcome. Since no arity currently refuses, this asserts the sentence's shape
        directly against the function rather than through `bass_allowed`.
        """
        reason = _comping_no_room_reason(2, False)
        self.assertNotIn("texture=", reason)
        self.assertIn("voices", reason)
