# Engine reference

The voicing engine: what shapes exist, how one is chosen, and what the tables
behind them mean. Read this before touching anything under `arranger/` except
`options.py`.

The module map and the dependency order that holds it are in
[../AGENTS.md](../AGENTS.md), and [dependency-dag.md](dependency-dag.md) draws
that order as a graph; this document is the reasoning behind the decisions,
not the map. Where a rule was measured, the measurement is kept - it is what tells
you whether a change is an improvement or a different library.

## Architecture and key types

- `STANDARD_TUNING` — six open-string `Note`s, index `0` = low E (string 6)
  through index `5` = high E (string 1). `STRING_NAMES` mirrors these.
- `MELODY_STRING_CHOICES` — `(5, 4)`: the soprano string indices the *drop-2* path may
  be pinned to (`5` → D-G-B-E, `4` → A-D-G-B). Kept as the default of
  `get_drop2_voicings` so its published output is unchanged. Index `0` = low E ...
  `5` = high E, so the conventional guitar string number is `6 - index` (index
  `5` = string 1).
- `MELODY_STRING_CHOICES_FULL = (5, 4, 3)` — the default soprano set: the high E, the
  B **and the G** string. Adding the G string is what lets a melodic position be held
  by *changing strings* rather than by moving the hand. The A string and the low E are
  inner voices only; no grip puts the soprano on either, so the melody floor is `G3`
  while the chord range extends down to `E2` as a bass voice.
- `GRIP_PREFERENCE = ("drop2", "closed", "drop3", "drop24", "drop2_6432", "shell", "duo")`
  — the grip families, in the order they are generated in. **One order with one job**: no
  criterion in `voicing_cost` names a family, so a candidate tie that runs off the end of
  the cost tuple is broken by this order alone (see `best_voicing` below). It is *not*
  what decides how many notes a step sounds — that is criterion 2,
  `missing = 4 - len(active)` — so a shell never beats a four-note shape by sitting early
  here, and a family's place only orders shapes of the same arity against each other.
  `drop2` is first so the idiomatic reading of the name is the default one. `closed`
  (close position) is **second**, and it holds that place on the tie-break rather than on
  reachability: it is the tightest four-note shape there is, so where a melody *can* fret it
  it beats every other four-note family it ties with, while most melodies cannot fret it at
  all (see Known Limitations). `drop2_6432` (6-4-3-2) is listed after the contiguous blocks
  because it is the *alternative* to the contiguous drop-2, not a third string set for it:
  `grips=("drop2",)` still means the four contiguous strings, which is the idiom that
  reproduces the original output exactly. `drop3` and `drop24` sit between the two, each a
  derived reading of the close stack rather than a block.
- `GRIP_STRING_SETS` — for each grip, its supported `(active string indices, soprano
  index)` pairs: the 4-3-2-1 and 5-4-3-2 four-string blocks, **6-4-3-2**, the six
  shell shapes (1-2-3, 2-3-4, 5-4-3, **6-4-3**, and the two 5-3-2s — `(1,3,4)`
  skipping the D going down and `(5,3,2)` skipping the B going up). The **duos** are the
  three adjacent pairs 1-2, 2-3 and 3-4 plus **one** skipped pair, `(3,1)`, which exists
  to voice the 9ths a displaced 2nd needs — see the decisions below. An `interval` uses
  the three adjacent pairs only: a 3rd or a 6th has tuning to spare and gains nothing
  from a wider set.
  `6-4-3`, both `5-3-2`s and `6-4-3-2` are the four non-contiguous sets, each skipping
  one string; `6-4-3-2` and `(5,3,2)` skip one going *up* (the A to reach the B as
  soprano, and the B to reach the high E respectively).
  The second `(5,3,2)` — the one skipping the B — adds no coverage over 120 transcriptions,
  because it is never the only shape for a melody, but it relocates **1.3%** of steps onto a
  better melodic position: F7 with a `Db4` soprano moves from `x-6-7-6-x-x` to `x-6-x-2-2-x`,
  the same three pitches with the melody at B-string fret 2 instead of G-string fret 6. That
  is the whole point of letting the melody hold its place by changing strings.
  **No set skips an *inner* string any more except the `(5,3,2)` shell**: the four
  `drop24` sets that did - four of that family's eight, two of them its measured winners -
  were removed because the right hand had to reach over an unplucked string to fret them.
  [fingering.md](history/fingering.md) §4.4 holds the measurement and what the removal cost.
  `supported_string_sets()` is the playability invariant stated in
  one place, and adds the drop-2 blocks for all three sopranos (drop-2 is defined
  generically, so a caller passing their own `top_string` still works).
- `BASS_DEGREES_6432 = (0, 7)` — the degrees the low E may take in a 6-4-3-2 shape, and
  the analogue of `DUO_DEGREES` for the bass rather than the melody. The lowest voice is
  what *defines* the chord, so a 3rd or a 7th there sounds like a different harmony.
- `SHELL_DEGREES` — the (3rd, 7th) pair per quality, explicit rather than inferred:
  a quality not listed gets no shell rather than a guessed one. A **duo reads its second
  voice from this same table** — `[0]` first (the 3rd, or the 4th on a suspended chord),
  `[1]` when `[0]` is the melody itself — so a quality cannot gain a shell and lose its
  duo. `DUO_DEGREES = (0, 7)` is the degrees a duo's *second voice* may take, not the
  melody's: a duo is generated under **any** chord tone, because a guide tone beneath a
  3rd or a 7th is what states the chord's function. The `interval` grip is a separate
  family for a different reason — it is a texture rather than a harmony; see
  [Texture: chords on the beats, fills between](#texture-chords-on-the-beats-fills-between).
- `ROLE_TARGET` / `ROLE_FILL`, `TEXTURE_STYLES`, `TARGET_BEATS`, `TEXTURE_ARITY` —
  the metric layer's whole vocabulary. `TARGET_BEATS = (1, 3)` names **felt beats**,
  not absolute onsets: a group index into the bar's grouping, so the rule reads the
  metre it is given. With no grouping every denominator unit is its own felt beat,
  which is beats 1 and 3 of 4/4; in 12/8 the felt beats are 1, 4, 7 and 10 and the
  targets are 1 and 7. `metric_weight` and `roles_for_slot` are the two functions
  that apply it. `TEXTURE_ARITY` is the chord part's arity per texture — `None` for
  `uniform` and `targets`, which are the parts arithmetic (`texture.derived_arity`).
- `NECK_FRET_MIN` / `NECK_FRET_MAX` — `2` and `13`. A strong preference, never a
  filter; see the selector below.
- `HIGH_FRET_LIMIT` — `13`. A melody whose only available position sits above this
  fret is re-voiced an octave down on the B string. See
  [High melodies move down an octave](#high-melodies-move-down-an-octave).
- `Voicing` — a dataclass for one fretboard shape: `frets` (6 entries,
  `-1` = muted), `top_fret`, `avg_fret`. Helpers: `tab_string()` (one-line
  `x-x-12-13-13-13`, frozen: ~40 call sites in tests and docs depend on it),
  `tab_block()` (six-line vertical tab, high E first, two-char right-aligned
  cells, highest string labelled lowercase `e`), `tab()` (`tab_block()` joined
  with newlines), `active_frets()`, `fret_span()`, `midi_notes()`,
  `pitch_classes()`, `soprano_string()` (index of the highest sounding string;
  `-1` if all muted). Supports legacy dict-style access (`v["frets"]`).
- Tab rendering is **pure**: every renderer returns a string (or list of
  strings) and prints nothing, so callers control display. **Only `demo.main()` writes
  to stdout** — the engine has no warning channel, so every choice it makes is either on
  the tab line or a `ValueError` from the axis that could not honour the request.
- `ArrangementStep` — a dataclass of `chord`, `melody`, `voicing` plus the
  non-chord-tone bookkeeping `non_chord_tone` (bool), `strategy` (which strategy
  handled the step) and `harmonized_as` (the substitute chord name). Also
  `tab_line()` / `tab_block()`, which delegate to the `Voicing` renderers.
  Supports legacy dict-style access (`step["chord"]`).
  The optional `bar` / `beat` / `duration` (all default `None`) carry the timing the
  staff renderer needs; `has_timing` reports whether a step can be placed on a grid.
  `repeated` (default `False`) marks a step whose melody holds the previous step's
  pitch **on the same string, under an unchanged harmony**: the voicing is still
  generated in full, but the renderers show only the soprano and hold the inner voices.
  A repeat across a chord change is not a hold, and neither is one the selector voiced
  on another string; the candidates for a hold are narrowed to the held string before
  selection. See
  [Repeated melodies hold the shape](#repeated-melodies-hold-the-shape).
- `format_progression(steps)` — module-level renderer for a whole
  arrangement: one **block** per step, whose first line is four fixed columns — chord,
  melody, the melody's
  **degree above that chord** (`chords.melody_degree_name`, blank when there is no melody
  or no readable chord), and the tab — so every shape starts in the same column. Any
  annotation is **appended after the tab** rather than printed inline, which is what keeps
  the tab column fixed however long the text is; an explanation too long for the width
  (100 columns, or whatever `width=` asks for) continues on the lines below the step,
  indented to the column the explanation starts in, and `width=None` gives one line per
  step at any length. Every step is annotated through the
  shared `step_annotation()` helper, which `print_step()` also uses so the two
  renderings cannot drift: a chord tone names the degree it is (`(harmony under b7)`), a
  non-chord tone names its substitution, and a partial shape names what it leaves out.
  Where the shape sounds **two or more voices**, the annotation also names them and the
  degree each states (`sounding: Bb 5, Eb Root, G 3, C 6`) — the chord column describes the
  harmony, and the tab gives frets, so which notes make up the shape is the third fact the
  line has to carry. Read from the step's own pitches (`upper_midi_notes()`, so the thumb is
  not among them: it has its own `bass:` clause) and named through
  `chords.melody_degree_name`, the vocabulary the degree column already uses.
  Where the melody-bearing route *chose* the shape, the annotation carries a **shape
  clause** as well: how many voices the step states and, where a fuller shape existed,
  which criterion turned it away — `(shell - 3rd & 7th, partial - 3 voices: the 4-voice
  voicing 2-x-1-2-0-x lies outside the neck window)`. It is written from
  `ArrangementStep.palette`, the fact the selector records — the most voices the palette
  offered, the best candidate with more of them, and the element of `cost.voicing_cost`
  that ranked it lower — so the answer is the decision's own rather than a second opinion
  at render time. The criterion is named from `cost.VOICING_COST_CRITERIA`, the tuple's
  order spelled as words; its last entry is not a cost at all but a shape the caller's
  slash-bass partition removed before the tuple ran, which is what a slash chord reading
  `does not sound the written bass` means.

  Four more clauses answer the routes that choose no shape from a palette, each of which
  used to read as something it was not: a **silent** step (`the guitar rests here - the grid
  places no chord`, where the line previously claimed a harmony under a degree - and the
  reason after the dash is now `step.silence`'s own, of five: the grid, an `NC` bar with
  nothing to comp, no shape for the chord or the tune, no string reaching the melody, or a
  melody-only selection with no tune here), a **comping**
  step (`comping - B 3, D 5 & F# 7; the guitar does not play the tune` — each voice read off
  the shape as its note and its degree, because the old grip label called a single bass note
  "shell - 3rd & 7th"), a step that exists
  for the thumb (`the shape above is held`), and a shape that had to leave the preferred frets
  (`reaches outside the preferred frets 2-13`, with what was inside them from
  `Palette.inside_window`). A palette that is thin because the *texture* asked reads
  `the most a fill's palette offers` rather than `the most this palette offers`, and a chord
  symbol nothing can parse says so instead of printing a bare count.

  A fifth names a loss the tab cannot show: the slash bass the partition could not reach
  (`the written bass D is not sounded - the lowest voice (G3) is 5 semitones from it`). The
  symbol asks for that note and no part of the tab answers, so the line does — read from the
  chord symbol and the shape, through `chords.slash_bass` and `chords.slash_bass_cost`.

  A sixth names the other loss the tab cannot show, and it is the rule's own price: a
  four-voice shape on a chord with more tones than voices *gives one up* — the root first,
  then the natural 5th (`TONE_PRIORITY`, [generated-grips.md](history/generated-grips.md)) — and four
  strings that count as a complete shape read as a complete chord. So the line says which tone
  went (`the chord tone it leaves out is Root`), named through the same
  `chords.melody_degree_name` vocabulary `_comping_clause` names the voices it *states* with,
  against the chord the part **states** (`harmonized_as` where a substitute was found) and the
  pitches of the **whole** step, so a thumb that lands on the root counts as stating it. Only
  the four-voice shape is asked about: fewer voices is a different decision, already answered
  by the count or by `partial`'s `shell - 3rd & 7th`, and a hold was answered where the shape
  was chosen.

  Two outcomes that used to print the same words are told apart. A non-chord tone whose
  strategy found nothing reads `non-chord tone - the extension strategy found no voicing; the
  written chord stands`, where before it read only `non-chord tone` — the words a route that
  never attempted a substitution would also print (`step.harmonized_as` is what separates the
  two, and `step.strategy` now carries the strategy *in force* rather than only the one that
  succeeded). And a comping step reads `the tune is silent here` where the grid stabs at a
  position the tune has no note under, rather than claiming the guitar is declining a note
  that is not sounding.

  **The rule that decides where a fact goes.** A clause is either a *correction* or an
  *explanation*, and the two behave differently. A correction fixes a **column** — the melody
  column shows the pitch that sounds, the chord column shows the written symbol — so it is
  restated on **every** line that suffers it, holds included. An explanation accounts for a
  **choice** (why fewer voices, why that fret, why the thumb moves), and it belongs on the line
  where the choice was made: a hold does not repeat its shape's count. Both are *derived
  clauses* in `annotation._annotate`, never branches at a return site, because a fact written as a
  branch is a fact some route will not print — which is precisely how 22 transposed steps lost
  their substitute chord and 2 holds lost their octave. `tests/meta_explanations.py` holds the
  whole invariant as a table of (decision, when this step is one of those, what the line must
  say), swept over every committed head from the step's **fields** rather than from the
  wording; `AGENTS.md` states the rule an editor must follow when adding a choice.
  It used to take `vertical=True` for a six-line block per
  chord, and the `--vertical` flag existed only to reach it; both are removed, so
  this is the compact one-line form alone and `format_tab_staff` is the six-line
  rendering. `Voicing.tab_block()` still renders a single voicing vertically.
- `format_tab_staff`, `format_tab_html` and `write_tab_html` **live in
  `tabstaff.py`**, not here, and are re-exported below. See
  [The staff renderers live in `tabstaff.py`](renderers.md#the-staff-renderers-live-in-tabstaffpy).
- `format_tab_staff(steps, beats_per_bar=4, beat_type=4, rhythm=True,
  show_chords=False, show_melody=False, show_melody_string=True, show_mutes=False,
  collapse=True, measures_per_line=4, show_timing=False)` — renders the **whole
  progression along one six-line staff** in reading order (high E on top), which is
  the standard tab layout and unlike `format_progression` is not one block per chord.
  The defaults draw **the tab and nothing else** — six string rows, frets sitting in a
  line of dashes, every bar ruled. `show_chords`, `show_melody` and `show_timing` add
  the lead-sheet and score annotation on top, and all three were on by default once.
  With `show_chords`, the chord names go on a line above, each starting in the column
  where its shape is struck, and `show_timing` adds the **metre** and a **note value per
  column** above them — see [docs/renderers.md](renderers.md#what-the-staffs-timing-rows-are-and-what-they-are-not).
  Neither is on by default: **width already says how long a note sounds**, so that row
  is a second, explicit way of saying it rather than the only one.
  Three decisions are load-bearing and were each forced by looking at the output:
  - **Fret cells are left-aligned in a fixed-width column.** A right-aligned cell
    looks tidy on its own but puts the fret at the far end of the column, so the
    chord name and its frets no longer share a column. The column width widens to
    the longest chord name rather than letting the chord line drift out of step
    with the frets under it.
  - **`collapse` compares sounding pitches, not fret numbers.** The skeleton voices
    one step per eighth, so without it a held chord is restruck eight times a bar and
    the staff is a chord list rather than a held shape. A rest clears the held
    pitches, because a rest genuinely stops the ringing.
  - **Every bar is ruled, and `measures_per_line` is bars per *line*.** These were one
    setting once: barlines were drawn every `measures_per_line` bars, on the reasoning
    that a barline every bar cluttered a grid already dense with columns. Splitting them
    was forced by TuxGuitar's ASCII export, which closes every measure and wraps at a
    fixed number of bars. A barline is not clutter — it is the one mark saying where the
    metre falls, and without one on every bar a reader cannot tell a two-bar phrase from
    a four-bar one. So `_staff_barlines` marks every bar and `_staff_breaks` marks where a
    line ends, both derived from one `_staff_bars` list so the two cannot disagree. The
    grid starts at the first step's own onset so a head selected from bar 1 (or from a
    negative pickup bar) is not preceded by empty bars.
  - **A string is drawn as a continuous line of dashes**, with the fret numbers sitting
    *in* it, and the chord/melody/metre rows above are **not** filled. That asymmetry is
    deliberate and is the difference between a staff that reads as tab and one that reads
    as a chord list; a dash through a chord name would be a line through the word.
  Muted strings are blank by default (a ringing voice is not restruck);
  `show_mutes` spells them out, and a melody-only step always shows its `x`s.
  With no step timing, `rhythm=True` falls back to a uniform one-chord-per-beat
  grid rather than failing.
- `GuitarFretboard` — static helpers `note_to_fret(string_index, note)` and
  `fret_to_midi(string_index, fret)`. Out-of-range inputs return `-1`.
- `ChordParser` — `parse_chord_name(name) -> (root, quality)`,
  `get_melody_degree(root, melody_note) -> 0..11`, `canonical_quality(quality)`
  (case-sensitive alias resolution: `M7` -> `maj7`, `M` -> `maj`, `m7` stays `m7`)
  and
  `get_chord_tones(quality, chord_name=None)` -> every pitch class in the chord.
  `CHORD_TONES_FROM_ROOT` is the full tone set per quality, and is what
  `grips.drop2_template_for` reads, so the root of a rootless `7b9` still counts
  as a chord tone and every tone of the chord can carry the melody.
- `VoiceLeadingEngine` — the core engine:
  - `get_drop2_voicings(melody_note, chord_type, chord_name=None, top_string=5)`
    — one string block; `top_string=4` pins the melody to the B string.
  - `get_grip_voicings(melody_note, chord_type, chord_name=None, top_string=5,
    grips=GRIP_PREFERENCE)` — candidates for one soprano string across every grip
    family, the general form of `get_drop2_voicings`.
  - `get_all_grip_voicings(melody_note, chord_type, chord_name=None,
    top_strings=MELODY_STRING_CHOICES_FULL, grips=GRIP_PREFERENCE)` — candidates
    across every allowed soprano string, high-E first, applying the chord-tone match
    then the quality-only fallback. **Pure**: it neither filters by fret nor
    transposes. `get_all_drop2_voicings` is this pinned to `grips=("drop2",)`.
  - `voicing_cost(voicing, criteria)` — the whole selection rule as one comparable
    **7-field** `VoicingScore`: notes outside the chord, then
    frets outside the window, then missing voices, then **span** (with spans 0 and 1
    bucketed to the same value — see §"Span outranks neck position"), then neck
    position (the difference of average frets from the previous voicing), then pitch
    movement, then bass function. Lexicographic, not a weighted sum, because these
    priorities must not be traded against each other. **No field names a grip family**,
    so a tie that runs off the end of the score is broken by generation order:
    `top_strings` first, then `GRIP_PREFERENCE` within one string. The generators still
    take a `grips=` preference list - that is how the order is written down - but no
    arrangement route reaches it: the axis that let a caller give one is deleted, so the
    family a step is voiced with is `GRIP_PREFERENCE`'s order and nothing else.
    `best_voicing` is its argmin and is stable, so the engine is deterministic.
    **Every input arrives as one `SelectionCriteria` value** (`previous`, the window,
    the allowed tones, the melody's pitch class, the root, and the slash-bass pair the
    partition reads before the score), so the selection and the palette record cannot
    be scored against different arguments - and a new ranking input is a *field* on
    that value rather than an eighth parameter. The score is a `tuple` subclass with
    named fields, so `min` and `decisive_criterion` compare exactly what they always
    did; **its field order is the invariant** and is asserted once, in
    `TestVoicingCost::test_the_field_order_is_the_rule`.
  - **Adding a ranking criterion** touches three places, and only the first is code:
    a field on `VoicingScore` (named in the return), its phrase in
    `cost._CRITERION_LABELS` (keyed by field name, so it cannot drift out of order),
    and its value read from the criteria in `voicing_cost`. The label tuple, the span
    index and the partition index are all *derived* from the fields, so nothing else
    has to be found and updated - and a field with no label raises at import, which no
    run can miss. What is **not** free is the *position*: a new field is ranked above
    or below the existing ones, and moving one is a musical decision with a
    measurement, which is why the order has its own test.
  - **No element names a finger, and that is measured rather than omitted.** The right
    hand's own criterion was a candidate and it is settled: measured at every placement it
    changed **0** picks below `position` and **17** just after `span`, across 94 of 1,204
    pools — and it was answered by *tables* instead, since the four `drop24` sets that
    carried a finger skip were removed. The only finger questions the engine asks are
    **filters** (`RIGHT_HAND_STRINGS` / `thumb_safe_grips`, `fingers.can_fret`), never
    scores. `docs/history/fingering.md` §4.2 and §4.4 hold the measurements, and §5 step 3
    is the one still open.
  - `get_octave_down_candidates(melody_note, chord_type, chord_name=None,
    top_strings=MELODY_STRING_CHOICES)` — the same for the melody an octave lower,
    on the strings below the high E. Empty when the transposed melody is unvoiceable,
    so the caller keeps its original candidates.
  - `calculate_voice_leading_distance(voicing_a, voicing_b)` — per-string fret
    movement, kept for backward compatibility (only meaningful within one block).
  - `calculate_pitch_leading_distance(voicing_a, voicing_b)` — movement in
    semitones between sorted sounding pitches; identical to the fret metric within
    one block, and the metric `arrange_progression` uses across blocks.
  - `NON_CHORD_TONE_EXTENSIONS` — canonical quality → `{melody degree: extension
    quality}`, the routing used by the `extension` strategy.
  - `NON_CHORD_TONE_STRATEGIES` — the accepted `non_chord_tone` values.
  - `is_chord_tone(melody_note, chord_type, chord_name)` — chord-tone detection
    using `ChordParser.CHORD_TONES_FROM_ROOT`; `False` for unknown qualities.
  - `resolve_non_chord_tone(melody_note, chord_type, chord_name, strategy,
    next_melody=None)` -> `(quality, name)` for a substitute chord, or `None` when
    the strategy cannot help (the caller then keeps its fallback).
  - `sustain_inner_voices(previous_voicing, melody_note)` — holds the previous
    voicing's inner voices and moves only the soprano; `None` when unplayable.
  - `arrange_progression(progression, **knobs)` — the step loop, and the point every
    other entry point funnels through: it voices each step, applies the selected
    non-chord-tone strategy where needed, and chooses each shape with
    `select_step_voicing`. The knobs are **not** transcribed here - they are the
    signature, every one of them defaulted, and `ArrangeOptions` carries the same set
    as one value. (A copy used to live here and had already drifted: it still showed
    the nine knobs `arrange_progression` had before the axis layer existed, and
    named `_best_voicing`, which the loop no longer calls.) Two promises it does make:
    an unknown strategy or axis spelling raises `ValueError` before any voicing work,
    and `grips=("drop2",)` with `top_strings=MELODY_STRING_CHOICES` reproduces the
    library's original output exactly, which is what the renderer tests pin their
    fixture to. `timings` and `texture` are the metric layer; see
    [Texture: chords on the beats, fills between](#texture-chords-on-the-beats-fills-between).
    The loop's own shape is [below](#the-step-loop-and-the-five-routes).
  - `VoiceLeadingEngine.get_interval_voicings(melody_note, chord_type,
    chord_name=None, top_string=5)` — the two-note `interval` grip, a public entry
    point like `get_drop2_voicings` so every family is reachable on its own.
  - `__version__` — the library version string, the single source of truth that
    `pyproject.toml` reads as the dynamic project version. No document may state a
    different one.
- `NO_CHORD` — the string `"NC"`, a bar carrying melody with no harmony.
- `VoiceLeadingEngine.get_melody_only_voicings(melody_note, prefer=...)` — **the palette a
  lone note is placed from**: one **single-fret** `Voicing` per eligible string, at the
  written pitch, in preference order. A note no string in `prefer` can carry is rescued on
  the strings below it, and a note playable only above `HIGH_FRET_LIMIT` is retried an
  octave down; the first group that yields anything is the palette, so a caller's named
  strings are never widened while they can carry the note. These are explicitly *not*
  harmonised voicings and are exempt from the string-set invariant.
- `VoiceLeadingEngine.get_melody_only_voicing(melody_note, prefer=...)` — the first of that
  palette, or `None` if it is empty: the convenience a caller wants when it has no previous
  shape to weigh the alternatives against. Every lone-note route in the engine asks for the
  list instead and lets `cost.voicing_cost` choose, so a lone note is placed by the same
  neck-window and hand-travel criteria a chord is (see `melody_alone._melody_alone_shape`).
- `ArrangementStep.melody_only` — defaulted flag set on NC steps.
- `ArrangementStep.chord_unvoiced` — defaulted flag set when the palette could not
  voice the step's chord **at all**, so the melody sounds alone. Distinct from
  `melody_only` (which means the slot had *no* chord) and from the span demotion (where a
  complete shape existed and was too wide), so `annotation.step_annotation` can say
  `(melody alone - no voicing for this chord)` without claiming something false. See
  [Known limitations](#known-limitations).
- `demo.main()` — with no arguments, prints the built-in demonstrations; with `head`
  as the first argument, delegates to `headxml.head_cli` through a **lazy** import
  inside the branch, so `import arranger` never depends on the importer or, through
  it, on the renderers. It lives in `demo.py` and `arranger.main` re-exports it, which
  is the name `[project.scripts]` exposes as the `jazz-arranger` console script.

### The step loop, and the five routes

`arrange_progression` lives in **`movement.py`**, not in `steps.py`: `steps.py` is the
published facade and delegates to it. The loop has two halves, and the seam between them
is where most of this document's rules are decided.

**Once per arrangement**, `resolve_knobs` reconciles `options=` with the keywords and
validates the spellings, and `resolve_policies` resolves the six axes and builds the
walked-beat union when a thumb line is running. Both live in **`resolution.py`**, which
`movement.py` calls: the sentinels and spellings are answered there so the loop reads a
concrete value on every axis. Both run before any slot is looked at,
because the band does not change halfway through a tune and a spelling nobody recognises
has to be reported **once** rather than never.

**Once per slot**, `slot_state` returns a `SlotPlan` - the note, whether the guitar
*sings* this slot, the metric weight, the role, the permitted grips, the melody-alone
kind and, for a silent plan, *why* it is silent (`silence`, one of the `SILENCE_*`
constants). That decision, and the `Carried` / `SlotInputs` values it reads, live in
**`slot_plan.py`**; `movement.py` only walks the plans it returns. It no longer refuses a slot outright: a melody-only selection at a position
with no note gets a silent plan (`MELODY_ALONE_REST` + `tune_silent`) rather than `None`,
so the tab keeps the bar. The plan then goes to **one** of five dispatch entries:

| entry | emits | when |
|---|---|---|
| `no_upper_voices` | `bass_alone_step`, `rest_step` | nothing above the thumb sounds: the bass line's own note, or a guitar silent for the reason `step.silence` names - off the grid, an `NC` bar under a comping selection, a position nothing can voice, or a melody-only selection with no tune |
| `texture_fill` | `texture_fill_step` | the guitar sings the note and the texture thins the slot to it - a fill, a target no shell can sound, or an off-grid note |
| `no_chord` | `no_chord_step` | an `NC` bar the guitar *is* singing: the melody, and no harmony to state |
| `comping` | `comping_step` | the guitar does **not** sing this slot, so it comps under the horn |
| `melody_bearing` | `harmonised_step` | the guitar sings: pin the tune, and voice the chord beneath it |

The dispatch is **`route_dispatch.py`**: those five rows are its `ROUTES` table, each
an entry with a *claim* ("is this slot mine?") and an *emit* ("here is the step"),
asked in order. A route may claim a slot and then **decline** it - the texture fill
and the comp are the two that can - and the next entry is asked instead, so the
order is the contract rather than the set. The last entry claims every slot, which
is what makes "exactly one step per slot" structural rather than a property to check;
`tests/meta_route_dispatch.py` pins the order and drives each entry from a request a
caller can ask for.

The four handlers other than `harmonised_step` live in **`routes.py`**. That one -
prepare, select, demote, or rest - lives in **`harmonised_route.py`**, and the
candidates it selects among are built by `prepare_step` in **`step_prepare.py`**,
which is also what the facade reaches for a single step. That split is why the loop
reads as sequencing rather than as a 250-line handler: `movement.py` is the
sequencing - the knobs, the slot list, the loop, the bass merge.

**The order is load-bearing**, and `AGENTS.md`'s trap 12 is what reordering it costs: the
same slot can reach three of the five depending on its plan, and every ordering is right
for one route and wrong for the other, because both build different steps from one plan.
That is why `decisions.melody_alone_case` returns a *kind* rather than a flag - and why
`MELODY_ALONE_REST` exists at all: "nothing here to play" and "nothing to say here" are
different claims, and only the first is a rest.

Each route takes what it needs as named arguments rather than reaching into one shared
context. The exceptions are `arrangements`, which they append to, and the two values one
step tells the next, which live on a small `Carried` in `slot_plan.py`.

### Adding a new chord quality

**Two rows, and the shapes follow.** The drop-2 templates, the derived grips and the
point the quality becomes voiceable are all computed from these, so there is no template
list, degree list or interval number to write down.

1. Add the quality's full tone set to `ChordParser.CHORD_TONES_FROM_ROOT`. This is also
   what `drop3`, `closed`, `shell` and `duo` build themselves from, so it is required
   for every grip family to reach the quality at all.
2. Add the quality's tones to `TONE_PRIORITY`, most defining first — the same row a shell
   and a duo read. Its **first two entries are `SHELL_DEGREES`' pair**, and its tail is
   which tone a four-voice shape gives up when the chord has more tones than voices: the
   root goes first, then the natural 5th, and a name-given extension is never the one
   dropped. `drop2_template_for` then builds each shape from the row, and
   `_drop2_palette` offers them for a melody with no degree to match.
   `tests/test_generated_grips.py` holds the row to the hand-written witness for every
   quality, and `tests/test_voicings.py::TestQualityTableInvariants` checks the row is a
   permutation of the tone set — a tone missing from it would have no shape at all.
3. Add aliases to `ChordParser.QUALITY_ALIASES`.
4. To make the quality reachable by the `extension` strategy, add it to
   `NON_CHORD_TONE_EXTENSIONS`.
5. **If a MusicXML file should be able to spell it**, add the matching
   `kind-value` to `MUSICXML_KIND_QUALITIES` in `headxml.py`, and any `<degree>`
   alteration that reaches it to `_DEGREE_REFINEMENTS`. The same rule applies: an
   absent kind resolves to `None` and is counted in `Head.unmapped`, so a new
   quality MusicXML cannot spell stays silent until this step is done. Note the
   table is keyed on the *library* quality, so a `kind` that only a `<degree>`
   reaches (a 7b5, say) needs a degree entry rather than a kind entry.
6. Add tests to `tests/test_voicings.py` for the drop-2 fingerings and to
   `tests/test_grips.py` for the other grips: exact fingerings, pitch classes a subset
   of `ChordParser.get_chord_tones(...)`, `fret_span() <= 5`, and the sounding strings
   a member of `supported_string_sets()`.
   `tests/test_non_chord_tones.py` covers any new
   `NON_CHORD_TONE_EXTENSIONS` route, and
   `tests/test_headxml.py::TestChordParsing::test_every_kind_the_table_names_is_voiceable`
   asserts that every quality `MUSICXML_KIND_QUALITIES` names can be voiced, so a
   table entry naming an unvoiceable quality fails the suite.

A quality with a tone set but **no** `TONE_PRIORITY` row is offered no drop-2 shapes at
all — `[]` rather than a guess — which is what `drop2_template_for` returns for it, and
what `tests/test_generated_grips.py` asserts.

## Grips, and the position-aware selector

The engine generates several grip families and then chooses between them, rather than
generating one kind and voice-leading it. Generation and selection are deliberately
separate: `get_grip_voicings` and `get_all_grip_voicings` are *pure* (no position
filtering, no transposition) and `best_voicing` does all the deciding. That split is
what stops the grip families and the octave-down rescue from having to know about each
other, and it is asserted in `tests/test_grips.py`.

**Two ways to propose a shape, one way to accept one.** `candidate` is the only place a set
of frets becomes a `Voicing`: the melody sounds and is the highest note, every fret is on the
board and inside `GRIP_MAX_SPAN`, the family's tone claim (`required`) and bass claim
(`lowest_pc_allowed`) hold, nothing outside the chord sounds where the family makes that claim,
and the sounding strings are one `supported_string_sets()` entry. The proposers are the
**search** (`search_shape`, for the families whose frets have to be found) and the **layouts**
(`place_template`, which computes them from an interval template). Both the proposers and the
rules they share live in `arranger/grip_place.py`, which sits below `grips` in the package order:
a generator builds a `Placement` and the module answers it. `_LAYOUT_GRIPS` and
`_SEARCHED_GRIPS` name the two kinds and must **partition** the families - a family listed in
neither generates nothing at all, which is what makes adding one a decision rather than a
silent omission.

The searched families' one search is answered from a memo that builds a fresh shape per call,
so generation stays pure in the observable sense: it changes the time and nothing else.
`search_shape` enumerates, `_searched_shape` (an `lru_cache`) remembers one request's
answer, and `place_shape` - the name the generators call - rebuilds a fresh `Voicing` from
the snapshot. Three things make it safe rather than merely fast, and
`tests/test_placement.py` holds each to a witness:

- **The key is the whole request.** `Placement` is a frozen dataclass of strings, tuples,
  ints and frozensets, so equal requests share an entry and different ones cannot, and
  nothing needs invalidating. The tables it reads besides the request (`GRIP_MAX_SPAN`,
  `STANDARD_TUNING`, `supported_string_sets()`) are fixed when the module is imported, so
  **reassigning one at runtime is the single thing that would leave a stale answer behind.**
- **A caller cannot write through it.** The fret vector is stored as a tuple and a fresh
  `Voicing` is built per call, because `bass_merge._attach_bass` writes the walked thumb *into*
  the chosen shape. A memo handing out the stored object would let one step's thumb line
  rewrite the shape the next step is handed - silently, and only in the tab.
- **It is read.** A hit and a miss are counted, so a memo nothing reaches cannot pass by
  leaving the other checks green.

The **comping palette is the same memo for the same reason**
(`_search_comping_voicings`, `_comping_palette`, and `get_comping_voicings_for` rebuilding
fresh `Voicing`s), because `decisions.select_step_voicing` hands one of the palette's own
objects back and `_attach_bass` writes the thumb into it. The memo key is the
`CompingRequest` itself - the chord, window, arity and degree flags - so the seven values
cannot be reconstructed in a different order at the next call. `get_comping_voicings` is
the primitive spelling that builds the same request. It buys time only: the search is still
exhaustive over the span window, so `frets_in_span`'s cost is the floor for a request
nobody has asked before.

**Three levers the placement has made possible, all measured and none taken.** Each would
let the search find a shape no grip family names, and each was priced on its own: **admit
crossings** (47 of 794 melody-bearing steps would win, and the shape would need a name),
**offer 6-5-4-3** to a G-string melody (104 of 967 steps would gain two to four shapes, so
that exclusion is load-bearing rather than academic), and **one shape per set for a
non-chord melody** (268 of 1,103 steps take the whole-palette route today - the largest
lever and the least understood). [generated-grips.md](history/generated-grips.md) §4 holds the
measurements; none of the three changes `voicing_cost`.

**A shape sounding a foreign note is refused before any preference is consulted.**
`allowed_tones` is the caller's tone set, and criterion 0 of the cost tuple counts the
sounding notes outside it, the melody excepted. It is a *count* rather than a flag: as a
boolean, a shape adding one foreign note scored the same as one adding four, so the tie
fell through to fret span — and the wronger shape usually won there, since having more
wrong notes does not oblige a shape to be wider but tends to. The melody is excluded for a
second measured reason: when the melody itself lies outside the chord **every** candidate
is impure on it and the criterion cannot tell them apart, so a correct shape could never
reach zero. G7 under F#5 is the case — drop-2's fallback offers shapes carrying two to four
foreign notes while drop-2 & 4 derives one carrying none, and both scored `1.0`, so the
wrong one won on span. Counting instead of flagging, together with excluding the melody,
takes **134 wrong notes down to 9** over five qualities and every non-chord melody in the
register.

### Span outranks neck position

`voicing_cost` ranks **fret span above neck position**. This is the only place one
criterion is promoted across another, and the trade was measured rather than guessed.

**The two criteria disagree about the same thing.** Position measures how far the
*hand* moves; span measures how far the hand has to *stretch* once it is there. A
five-fret shape sitting one fret from where the hand already was wins on position and
loses on span — and with span ranked below position that shape was chosen, which is
how the engine came to select `8-x-8-8-13-x` (index at 8, pinky at 13) for a Cm7b5.
Keeping the hand still is worth less than being able to play the shape it is holding.

**Promoting span is free where tightening the cap is not.** The obvious alternative is
to lower `GRIP_MAX_SPAN` from 5, and it was implemented and measured first. It is a
*filter*, so it deletes a voicing wherever no tighter one exists, and that cost real
music:

| cap | voicings kept (of 1008) | what went missing |
|---|---|---|
| 5 | 960 | — |
| 4 | 960 | the only Gsus4 fingering, `x-x-5-5-3-8`; and the **6-4-3** shell |

6-4-3 is the one default shape that reaches the low E, and losing it is a far bigger
musical cost than a few wide shapes. Ranking instead only ever chooses *between shapes
already on the table*, so nothing stops being voiceable at all. Over the same 1008
(melody, quality) pairs, coverage is identical at 960 and the share of selected
five-fret shapes fell from **4.1% to 0.8%**, with span-1 shapes rising from 27.8% to
44.4%.

**What it does not promise.** A selected shape can still span five frets, because
where the only candidate is wide, span is consulted first, finds every candidate
equal, and the wide one is played. `GRIP_MAX_SPAN` remains the outer bound. The
promotion is also below the correctness criteria: a shape sounding a foreign note or
a partial harmonisation still loses to a correct one however tight it is, which
`tests/test_grip_selection.py::TestVoicingCost` asserts directly on the tuple rather
than only through a result.

**Span 0 and span 1 are bucketed together.** The span index reports `0.0` for both,
so a zero-span barre and a one-fret reach tie and the decision falls through to neck
position. One fret of stretch is not a stretch worth moving the hand for, and the
case that showed it was a player reading the tab rather than a corpus measurement:
`Bb7` under `F4 → G4 → F4` with a three-note palette (`texture="chord2"`)
was voiced `x-x-6-7-6-x`,
`x-x-x-3-3-3`, `x-x-6-7-6-x` — down to a fret-3 barre for one note and straight back,
because the barre spans zero and the natural shape at frets 7–8 spans one. The
bucket keeps the hand at 6–8 (`x-x-8-7-8-x`). The bucket is applied to the *value*
at the span index, not by reordering the tuple, so **every span of two or more still
outranks position exactly as before**: the `8-x-8-8-13-x` case below is untouched,
and so is the low-Dm7 trade measured below it. Measured over the suite, the change
moves exactly one pinned tab — the last fill of the `targets` texture, `x-x-x-5-5-5`
→ `x-x-10-9-10-x`, which is the same stay-in-place behaviour on a different chord.
A bucket of `0/1/2` was measured too and **rejected**: it costs 13 tests, including
the low-Dm7 trade reverting to `5-x-3-5-3-x` and two walking-bass anchor
refusals, because a four-fret reach competing with barres on position is a
different decision than a one-fret reach doing so.

**The one case it costs, and why it is not tuned away.** A low Dm7 under D4 is now
`x-3-3-2-3-x` (span 1, lowest voice C3) where it was `5-x-3-5-3-x` on 6-4-3-2 (span 2,
lowest voice A2). Both sound the same four pitch classes, both are inside the window,
both are complete, so span decides and the narrower one wins — and the cost is the
bass, since C is the 3rd where A was the 5th, and 6-4-3-2 is the only default set that
reaches the low E at all.

The obvious repair is to rank the bass-function term above span. That was implemented
and measured, and it **brings `8-x-8-8-13-x` straight back**: the same ordering that
rescues the low bass also lets a five-fret shape with a root bass beat a one-fret shape
without one. The two criteria cannot both come first, so the choice is which to
favour. Span is favoured because a five-fret stretch is a shape the hand may not be
able to play at all, while a 3rd in the bass is a musical detail the ear supplies
around. The regression is asserted explicitly in
`tests/test_progressions.py::test_low_register_cadence_voices_low_with_a_complete_chord_or_a_shell`
so it stays visible rather than being quietly re-tuned away.

**Span is a distance, not a count.** `fret_span()` is `max(frets) - min(frets)`, so a
shape on frets 6 and 10 spans *four*: the stretch from index to pinky is four frets
even though five fret positions are involved. Counting the touched frets
inclusively would describe a reach the hand does not make, and would make the limit of
5 mean a five-finger stretch.

| grip | voices | how it is built |
|---|---|---|
| `drop2` | 4 | `TONE_PRIORITY`'s rule at four voices — generated; the hand table it reproduces is the witness ([generated-grips.md](history/generated-grips.md)) |
| `drop2_6432` | 4 | 6-4-3-2, found by search — the one default set that reaches the low E |
| `drop3` | 4 | derived from a close stack; offered through the bass-skipping sets |
| `drop24` | 4 | **drop-2 & 4** — the second *and* fourth voices lowered an octave; offered through the bass-skipping sets |
| `closed` | 4 | derived from a close stack; offered **second** — it beats every four-note family but drop-2 on a tie |
| `shell` | 3 | `SHELL_DEGREES` plus one more note |
| `duo` | 2 | the chord's guide tone — the 3rd, or the 4th on a sus chord — under any chord tone |

**`drop3` and `drop24` exist for a second reason, which is the one that matters.** A
melody that is *not* a chord tone leaves drop-2 with no template and no shell, so its
quality-only fallback states notes the chord does not contain. Both derive from the close
stack under the melody, which keeps every *other* voice a chord tone: measured over every
quality and every melody in the register they carry **no** wrong notes where drop-2's
fallback carries hundreds, and with the bass permitted to skip a string both are as tight
as drop-2 — frequently span 0 to 2.

**Every four-note voicing sounds the chord's 3rd and 7th**, and so does every three-note
one — except a suspended chord, which has no 3rd and whose guide tone is therefore the
**4th**. `Dsus7` is 1 4 5 b7 and its pair is (4, b7); `sus2`'s is the 9th. `SHELL_DEGREES`
already said so, and `tests/test_grips.py::TestGuideTones` holds the three tables to
the same answer. Those two notes are what decide whether the ear hears a major or minor chord, and
a dominant or a minor 7th, so a shape without them is a different chord rather than a
thinner one. All 119 drop-2 templates — the rule's own output, and held to the hand table
they came from by `tests/test_generated_grips.py` — keep both in every inversion, and every
degree of every one of the 29 qualities does too; the hand table was the witness, and step 3
of [generated-grips.md](history/generated-grips.md) records what retiring it cost. An
empty result offers nothing rather than borrowing another degree's template.

**Drop-2 & 4** lowers the second and fourth voices of a close stack an octave each — the
widest four-note shape there is, twenty semitones from melody to bass for a Cmaj7. It
is unplayable on four neighbouring strings and becomes frettable only through the
skipping rule below: the bass voice takes a lower string. Four of its eight sets instead
made it frettable by skipping an **inner** string — 1-2-4-5 (the G), 2-3-5-6 (the B),
1-3-4-6 and 2-4-5-6 — and **those four are now removed**, because the digit that takes a
string above an unplucked one has to reach over it. That is not a tidy-up: 1-2-4-5 and
2-3-5-6 were this family's measured winners over sevenths, ninths and sixths, and over
the committed heads the removal moves 260 of 1,204 selections and takes 57 of the 1,087
four-note steps down to fewer voices — **41 of them to the melody alone**, 16 to a duo —
because the best shape left at that melody position then sits at the top of the span
budget and `should_demote_to_melody_alone` drops it, and two positions in the pinned
fixtures lose their chord the same way (F5 at fret 13 over an F7, and C#5 over an Am7).
The full measurement, including which of the lost shapes were span-0 barres that cost
the hand nothing, the alternative that keeps every chord, and the open question of
whether the rule should be per *set* or per *shape*, are in
[fingering.md](history/fingering.md) §4.4.

Note the local names, which cost a wrong answer here: in `_, v1, v2, v3 = stack`, `v1`
is the **second** voice. So drop-2 & 4 drops `v1` and `v3` and keeps `v2` beside the
melody — `[0, v2, v1 - 12, v3 - 12]`. The other order sounds four chord tones too, and
so passes a tone-purity check while being the wrong shape.

**A four-note shape need not occupy four neighbouring strings.** The lowest voice may
skip to a lower string — what `drop2_6432` does with the low E, generalised. The
strings are tuned higher than the one below, so a deep bass runs out of board on a
contiguous block long before the low E would; skipping moves the shape down the neck as
a unit instead of stretching it. `GRIP_STRING_SETS` carries the skipping set for each
four-string block, and `place_template` still assigns the voices soprano-first, so a
set is ordered descending with the gap at the bottom.

Five decisions in here were each forced by something measurable:

- **drop-2's shapes are generated, and the decision the tables encoded is a tone
  priority.** `TONE_PRIORITY` says which of a chord's tones a shape states, most defining
  first, and `drop2_template_for` builds the shape for one degree from it — there is no
  table left to read. The 119 hand-written templates are kept as the witness the rule is
  asserted against (`tests/support.py::WITNESS`, read by `tests/test_generated_grips.py`)
  rather than trusted. The extended qualities
  are voiced *rootless* on purpose, so a 9 or a 13 that fits in four voices without the
  root is a musical decision; it is now a rule rather than 119 numbers, which is what makes
  it auditable and worth one line to change. Deriving drop-3 and close position from the
  same chord tones instead gives a *fuller* chord — every tone the rule left out comes back
  — a legitimate but different voicing, which is why those families keep their own rule.
  The measurements, the order that was not taken and what is still open are in
  [generated-grips.md](history/generated-grips.md).
- **Duos sound the chord's guide tone, under any chord tone.** The second voice is read
  from `SHELL_DEGREES` — the 3rd, or the **4th** on a suspended chord, with the 7th as the
  fallback — rather than from a list written out separately. That table already encodes
  the arranging guide's rule, and sharing it means a quality cannot gain a shell and lose
  its duo. It replaced a hand-written `(4, 3, 0)` scan that had two faults: it listed no
  sus degree, so `sus4`, `sus2` and `7sus4` admitted **no duo anywhere**, and its root
  fallback was unreachable besides, filtered out by its own `d not in DUO_DEGREES` guard.
  The fallback to the 7th is load-bearing: when the melody *is* the 3rd, `[0]` would place
  a unison under it, and a measured 252 of these cases are exactly that.

  This used to be a **hard rule on the melody** — `DUO_DEGREES = (0, 7)`, generated only
  under a root or a 5th, on the reasoning that a 3rd or a 7th there *is* the chord's
  function and a bare duo under it sounds wrong. That reasoning does not survive the
  guide-tone rule the family is built from: a guide tone *beneath* a 3rd or a 7th is what
  states that function, and it is the clearest possible statement that the two notes are
  this chord. The gate is gone. A melody that is not a chord tone never reaches the duo
  at all, because the non-chord-tone strategies rewrite the chord before generation — so
  a b6 arrives as the 9th or 13th of a resolved chord rather than as a passing note with
  a duo under it. `TestDuoHardRule` asserted the old rule and is **inverted rather than
  deleted**, because a 3/7 duo consists of genuine chord tones and the "only chord tones"
  check would not catch it either way.

  - **A 2nd under the melody is dropped an octave.** When the guide tone lands within two
    semitones of the melody the shape is a 2nd, which in two voices is where they fight
    rather than agree; the same pitch class an octave lower is a 9th, which sits. This is
    why the duo owns a **skipped-string** pair. A 9th spans 14 semitones and two adjacent
    strings are tuned 4 or 5 apart, so the lower note needs a fret difference of 9 or 10
    against a span cap of 4 — and over the 812 cases where the guide tone is displaced,
    **none** is voiceable on the adjacent pairs. `(3,1)` (strings 3-5, 10 semitones of
    tuning between the open strings) recovers 810 of them; `(5,2)` ties it, `(5,3)`
    recovers 118 and `(4,2)` 31, so **one pair was added, not four**. The cap is not
    widened for it: the pair works because it is wide in *tuning* and narrow in *frets*.
    Two cases remain unreachable — a `sus4` and a `7sus4` with G3 in the melody — and they
    return no duo rather than sound a 2nd, pinned by name in `test_grips.py`.
- **A shell is searched for, never stacked.** A shell's notes are not in descending pitch
  order down the strings, because the tuning is not monotonic in the useful direction: the
  A string is tuned five semitones *above* the D string. A G7 shell under G3 is
  `2-3-0-x-x-x` — B2 on the A string, F3 on the D string, G3 on the G — where the A string
  carries the *lower* note while being the higher string; Gm7 in 6-4-3 is `3-x-3-3-x-x`,
  with G3 on the D string below A2 on the low E. A model that stacks voices by pitch gets
  both backwards and finds nothing, so `place_shape` holds the melody and searches every
  combination of frets inside the span limit. That makes the search *exhaustive within the
  playability invariant*: if a playable shell exists in that position, it is found.
- **No four-note voicing on 6-5-4-3.** A G-string soprano has no four-note block, because
  the only one available is all of the four lowest strings and that does not sound good —
  four voices in the bottom fourth of the compass. A low melody is harmonised with a
  three-note shell (5-4-3 or 6-4-3) instead, dropping the 5th degree. Stated in one
  place, `_BOTTOM_FOUR`, and asserted by `TestStringSetTable`. **6-4-3-2 is not an
  exception to this rule**, which is why the two must not be conflated: it swaps the A
  string out for the B, so its lowest note is the low E while its soprano is the B, not
  the G. It is the answer to a different question — a *bass* — and it is the only default
  set that can reach one.
- **6-4-3-2 is searched for, and it needed a cost term to be chosen at all.** The same
  reason as 6-4-3: the set skips a string, so it is not in descending pitch order down
  the strings, so an interval-laid table cannot express it — the D string is a fifth above
  the low E, and the low E's note is frequently *not* the lowest sounding pitch.
  `_drop2_6432_request` therefore states that claim as a request to the shared search rather
  than inventing a second way to
  place notes, and the search ranks the survivors by `(fret_span, avg_fret)`. Two
  measurements forced the rest. Ranking is not cosmetic: an unranked
  search returns the first shape it meets, which puts the low E at fret 0–1, below
  `NECK_FRET_MIN`, and an earlier "0 of 22, never selected" reading was that bug. And
  ranked correctly it still lost — `voicing_cost` reached the neck-position term first
  and declined the better bass, so it wins only where the two shapes tie outright. Hence
  the root-or-5th bass term at index 6, a *tie-break* below every correctness criterion,
  which is what finally lets `5-x-5-5-5-x` (A2 G3 C4 E4) beat `x-3-5-2-5-x` (A2 E3 C4 E4).
- **A partial harmonisation is a fallback, not a style.** `missing` voices outranks neck
  position in the cost, so a complete chord wins even when a shell would have held the
  position better. The term counts the voices: a four-note shape scores 0, a shell 1 and a
  duo 2, so **a duo loses to a shell** wherever both are playable. That ordering is the
  arranging guide's — a shell sounds the 3rd *and* the 7th and a duo only one of them, so
  the shell is the fuller statement and the duo is the fallback beneath it.

  This paragraph used to claim a permitted root-or-5th duo "scores zero there and
  competes on equal terms". It never did: `missing` is `4 - len(active)` and nothing
  exempts a duo. Measured, adopting that claim would move 33 of 463 corpus steps (7.1%)
  and take **7 of them from shells** — inverting the very ranking the guide-tone argument
  requires. The code was right and the sentence was wrong, so the sentence is corrected
  and the cost tuple is untouched.

The window is a **penalty, not a filter**: a step with no voicing inside frets 2–13 is
still played, just outside it. A filter would silently drop every step whose melody
has no in-window shape, and losing a chord of the tune is worse than being a fret out
of position. `tests/test_grip_tables.py::TestFretWindow` pins that.

## The request, and the six axes under it

A caller asks six questions, and the six are one value (`options.Request`) spelled twice:
by `head`'s flags and by `Request(...)` on the library's own front door,
`arrange_progression(progression, request=Request(...))`. This document describes the
axes, because they are the implementation: **a request is resolved into them once, and
nothing below this section reads the request again.** `cli.REQUEST_DESTS` is the one list
holding the two spellings together, and `tests/test_request.py` asserts it.

| the question | the flag | `Request(...)` | the axis it resolves to |
|---|---|---|---|
| who plays the tune? | `--no-melody` | `melody=False` | `parts=` — the melody part is dropped from the selection |
| when does the chord attack? | `--chord-on POSITIONS` | `chord_on="1and"` | the chord layer's rhythm (`grid`, rewritten around `Rhythm`) |
| what does the chord state? | `--chord-notes full\|3\|2\|1` | `chord_notes="2"` | `texture=uniform\|chord3\|chord2\|chord1` |
| what does it do in a melody rest? | `--chord-fills none\|hold\|comp` | `chord_fills="hold"` | chord slots in the tune's rests, plus `parts=` including the chord |
| when does the thumb attack? | `--bass-on POSITIONS` | `bass_on="every-beat"` | the bass layer's rhythm, and `bass=` when it is not `none` |
| what does each thumb note state? | `--bass-notes root\|root-5th\|walk` | `bass_notes="walk"` | `bass=root`, `bass=root,5th`, or the full four rules |

The values are the flags' own strings, so a request read off a run header is one a caller
can paste into Python. The axis keywords (`texture=`, `bass=`, `parts=`, `harmony=`,
`grid=`, `time_signature=`) still ride beside the request and win where they are spelled,
which is how the axis tests hold a texture or a bass policy to its own behaviour.

`harmony=` is not on that list: it is the one axis with no request spelling, because it
is read only on the comping route and the request that route answers is `melody=False`,
whose chord content is `chord_notes`'s. The metre is read from the score (`grouping`,
below) rather than from a flag.

**The resolution is a derivation with refusals, not a set of defaults**, and it happens
before any voicing work (`options.resolve_request` → `resolution`). A content question
about a layer the request leaves silent is refused with the reason; a position the metre
does not have is refused by the parser; and `--no-melody` derives the chord's rhythm to
the metre's felt beats rather than refusing, because its default names a melody this
guitar does not have. A **spelled axis** still wins over the derivation in the Python
API, which is what lets this document's measurements be taken on one axis at a time.

## Texture: chords on the beats, fills between

`voicing_cost` ranks **completeness above position** and knows nothing about where in
the bar a note falls, so the `eighths` skeleton — one slot per eighth — produces eight
re-struck four-note chords per bar. That is a chord list. `tabstaff`'s `collapse`
hides it in the *drawing*; the selection never made the decision.

`texture="targets"` is that decision. It is the arranging guide's method — full chords
on the principal melody notes, something lighter in the gaps — expressed as **a change
to what may be played**, never as a change to what is preferred.

`uniform` is **derived, not listed**: it is the most notes the arithmetic allows at that
position — with the tune on top and no thumb that is three, the four-note shape this library
has always built, and with a thumb under it the budget gives two, which is the shell.
`TARGET_BEATS` and `metric_weight` stay **rules the policy reads** rather than data, which
is what makes `targets` a texture rather than a per-position literal.

Five decisions are load-bearing:

- **Timing narrows the candidate set; it does not touch the cost tuple.** "Play fewer
  notes here" is not a preference competing against "stay in position" — it is a
  change of what is on the table. A term in the cost would let a four-fret position
  outbid an entire texture, and it would make the "priorities must not be traded
  against each other" property of `voicing_cost` untrue. `TEXTURE_ARITY` maps
  texture → the chord part's arity, `texture_palette` turns that into the families a
  role may use at this position, and `arrange_progression` passes the role's tuple to
  the generator. Generation and selection stay separate exactly as they already were.
- **"No timing" is not "a weak note".** `metric_weight` returns **-1** when `bar` or
  `beat` is `None`, and `roles_for_slot` treats anything below zero as a target. This
  is the single line that makes the feature opt-in: with `timings=None` every slot is a
  target and the output is byte-identical to what it always was.
  `tests/test_texture.py::TestBackwardCompatibility` pins that against the exact tab
  of the library's own demo cadences, and it was written *before* any behaviour
  changed so every later step is checked against pre-existing output.
- **A beat is a counting position, not a quarter note.** `TARGET_BEATS = (1, 3)` names
  felt beats, and `beats_per_bar` and `grouping` decide which exist: a 3/4 head targets
  1 and 3, a 2/2 head has only the downbeat, and a 12/8 bar's grouping `(3,3,3,3)` puts
  its targets on beats 1 and 7. The comparison uses `BEAT_EPSILON` because a notated
  beat is a float — a 3/4 bar's second beat is 1.666… — and the earlier draft of
  `metric_weight` compared the *tuple index* against `beats_per_bar`, which let a
  2/2 bar inherit 4/4's second target. `headxml.arrange_xml_head` passes
  `head.beats_per_bar` through for this reason, and the committed corpus spans cut,
  common and waltz time — `synthetic_waltz.musicxml` is the 3/4 one, and it is the reason
  a rule stated only in quarters would pass on 4/4 and fail on a waltz.
- **A fill that cannot be filled becomes a target.** If a weak beat has no shell,
  interval or melody-alone voicing, the step is re-prepared as a principal note and
  its `role` is corrected to match. The texture is a lighter *texture*, never a missing
  harmony — the same argument that makes the neck window a penalty rather than a filter.
  Measured over melid 218, 2 of 30 weak slots take this path, so the reported role and
  the sounding shape must be allowed to disagree with `metric_weight` but never with
  each other.
- **A target that cannot be *played* becomes the melody alone.** The mirror of the rule
  above, and it exists because `targets` offers a target only `("drop2", "drop3")` — so a
  narrow shell is not merely outranked on such a step, it is **never generated**, and the
  cost tuple would not have chosen it anyway (`missing` is index 2, above span). Ebmaj
  under G4 in "the synthetic cut-time head" is the real case: the engine can sound `x-x-8-8-8-x`
  (span 0) there, but the only complete option a target is offered is `x-6-5-3-8-x`, a
  five-fret stretch. The step falls back to the melody alone, and `render`'s shape clause
  says so on the line.

  It is a **fallback, not a re-ranking**, and deliberately the last thing tried. Lowering
  `GRIP_MAX_SPAN` is a filter that deletes the voicing everywhere; promoting span above
  `missing` would dissolve the shell and duo families across the whole library. Here a
  complete chord is still what you get whenever it is playable, and only a shape at the
  very top of the budget is demoted. The demotion target is the melody alone rather than
  a shell because a shell is only reachable when the role's palette contains one, and
  where it does not — a `targets` target — there is nothing to demote *to*.
  `melody_only` stays **False**: the step does have a harmony, it is simply not spelled
  out, so the flag would make the annotation claim "no chord". `chord_unvoiced` stays
  false for the same reason from the other side: a complete shape **did** exist here and
  was refused for its reach, so "no voicing for this chord" would be claiming something
  that is not true.
- **The role's palette is the texture's business: there is no grip axis.** A caller
  cannot name a grip family. `texture=` states the chord part's arity and
  `texture_palette` builds the families that arity admits from `GRIP_PREFERENCE`, so a
  family the texture never uses cannot be asked for, and a tie that runs off the end of
  the cost tuple falls to the engine's own order rather than a caller's.

  Both entry points need this — `arrange_progression` and
  `arranger.slots.arrange_slots` — because a head read from a file takes the second
  and a hand-built progression the first. They are no longer two loops, so this is
  a request built in two places rather than a policy applied twice: fixing only one
  would leave the same request behaving two different ways depending on the entry point.
- **An `interval` is a texture; a duo is a harmony.** Both are two notes under the melody,
  and they are now offered under any melody degree, so the degree no longer distinguishes
  them. What does is the rule that builds them. An interval is not claiming the chord, so
  its second voice is whichever of a 3rd, 6th or 10th it can reach — falling back to the
  **major scale's** pitch classes when the melody is not in the chord, because a diatonic
  note is accompaniment and a chromatic one would be reharmonising. A duo *is* claiming
  the chord, so its second voice is the chord's guide tone and nothing else. Confining an
  interval to fill slots is what makes its looser rule safe.

`step_annotation` names the interval it actually is ("6th"), not the grip, and it
takes the existing precedence for free: a non-chord tone's substitution is annotated
instead, which is the more important fact about the step. `format_tab_staff` has **no**
annotation channel at all — the line above the staff carries chord names only — so
there the guarantee is simply that it draws the shape that sounds.

### Measured, over six corpus heads

| texture | mean sounding notes per melody note | share of steps in four voices |
|---|---|---|
| `uniform` (before) | 3.86 | 86.7% |
| `targets` | 3.39 | 50.8% |

Every head moved the same way, and none of them lost a step: melid 218 (Blue Train)
goes 4.00 → 3.42 notes per note and 100% → 55% four-voice steps, melid 266 3.97 → 3.34
and 96.6% → 48.3%. The ~50% ceiling is `TARGET_BEATS` itself — two of four beats — plus
the small number of fills that fall back. That is the trade the guide describes: the
chord is stated where it counts and the rest of the bar moves, instead of every note
carrying four voices.

## Grouping: the metre's third fact

A count says how many denominator units a bar has, the denominator says how long one
lasts, and neither says how the player **feels** them. 12/8 is twelve eighths wide and
four felt beats; 12/4 is twelve quarters wide and twelve felt beats. `grouping` is that
third fact. A loaded head takes it from the score, and `auto` falls back to the metre's
convention: an eighth-or-finer denominator whose bar divides by three is grouped in
threes (6/8, 9/8, 12/8 read as two, three and four beats), and every other metre is one
group per unit. 5/8 and 7/8 are **not guessed** from their count; the score has to state
them.

A hand-built progression declares the whole metre as one value:

```python
from arranger import TimeSignature

steps = engine.arrange_progression(
    progression,
    time_signature=TimeSignature(5, 4, grouping="3+2"),
)
```

`TimeSignature(beats_per_bar, beat_type, grouping)` validates the grouping against the
bar when it is built, so a `3+2` on a 4/4 signature is refused before any voicing work.
Omitting it means `COMMON_TIME` (`TimeSignature(4, 4)`), the metre every bare call had.
The three facts are one field rather than three keywords so they cannot disagree:
`beats_per_bar=12` alone is 12/4, not 12/8.

The three metre-driven rules read the grouping and nothing else:

- `metric_weight` treats `TARGET_BEATS` as **group indices**, so a 12/8 bar's targets
  are beats 1 and 7 rather than 1 and 3; a bar with two groups (6/8, 2/2) has only a
  downbeat target.
- the walking bass invents one note per **felt beat** and takes its approach on the last
  one — four notes in 12/8, not twelve.
- the named grid figures are group-relative. `freddie` is one stab per felt beat;
  `joe_pass` and `final_and` answer on a group's **last unit** (the third eighth of a
  dotted quarter, the `and` of a simple beat), so the simple-metre table is unchanged
  and the compound one is musically placed. A group index the bar does not have is
  dropped, never clamped.

**The score states the grouping, in three channels, and the importer reads them in this
order:**

1. a written `N+N` mark in a `<direction>`'s `<words>` or `<rehearsal>` — how a 5/4 that
   leans on a dotted quarter is actually annotated;
2. the **primary beaming**: a beam group begins at a `begin`, and the group lengths are
   the distances between starts, with the last running to the bar line;
3. a `<metronome>` pulse, dots included — a dotted quarter in 12/8 is the score saying
   "feel this in four".

Each candidate is used only if it partitions the bar; an unreadable one falls through.
The source is recorded on `Head.grouping_source` (`text`, `beams`, `metronome`, or empty
for "the score said nothing") and printed by the CLI, because "3+2 from a direction" and
"3+2 from the metre's convention" are different claims about the file.

**A conventional simple metre ignores its beaming.** 2/4, 3/4, 4/4 and 2/2 are already
grouped by their count, and notation programs beam eighths in whatever pairs or fours fit
the beat; reading that as a grouping would turn a half-bar beam in 4/4 into two felt
beats. Compound and asymmetric metres are where beaming carries information the count
cannot, so it is read there. A caller's explicit `TimeSignature(..., grouping=...)` still
overrides the score's statement.

`auto` is one group per beat on every metre the library shipped with, which is why the
**pre-existing** committed corpus is byte-identical with the axis present (the grouped
fixtures are new). `tests/test_grouping.py` owns
the algebra; `tests/test_headxml_arrangement.py` the end-to-end 5/4, 7/4 and 12/8 claims
and the precedence between the channels.

## Repeated melodies hold the shape

When a step's melody sounds the same pitch as the step before it **and the harmony
under it is unchanged**, the step is played as a **single note**: the soprano string is
struck alone and every other string is left blank. Restriking the whole chord is harder
than the music needs, and it is how a player actually reads a held melody.

The Weimar transcription of "synthetic common time" is the motivating case: at bars
61–63 it holds C4 across three chord changes (F-7, Bb-7, Eb7). The repeated Eb7 is a
genuine hold — one strike, then the note alone. The two *changes* underneath it are not.

The decision has two halves, and only one of them is presentational.

**Which shape is played is narrowed when the melody did not move.** A hold means the
finger already sounding the note stays where it is and only the chord under it changes,
so the candidates are filtered to the string the melody is on *before* the selector sees
them — `decisions.hold_the_melody_string`. That is a filter over a list rather than a new
cost criterion, for the reason the walking bass's finger budget is: ranking a hold above
a jump cannot stop the jump, because both are legal shapes, and `span` deliberately
outranks neck position in the tuple. Measured when this landed, over the heads
then in the tree and the three textures then shipped: **21** of 2,399 steps change, every
one of them under `targets` — 18 a different shape and 3 only the flag — while
`uniform` and a walking thumb line (`bass="root,5th,approach,nearest"`) are untouched. The
narrowing **cannot starve a step**: a thin palette with nothing on the
held string keeps its candidates unchanged, and such a step is then simply not marked
`repeated`.

**The flag itself is presentational.** `arrange_progression` still generates a full
`Voicing` for every step. The engine voice-leads from it, `midi_notes()` reports it, and
a caller wanting the literal shape still has it via `step.tab_line()`. What changes is
that `ArrangementStep.repeated` is set, and the renderers honour it.

- The flag is set by comparing **sounding pitches** (`max(midi_notes())`), not written
  note names, because either step may itself have been transposed down an octave by
  the `HIGH_FRET_LIMIT` rule. A run of four identical notes under one chord yields
  `[False, True, True, True]`.
- **The melody must still be on that string.** `decisions.is_repeated_step` requires the
  step's soprano string to equal the previous step's, because the renderers act on the
  flag by striking the soprano alone and collapsing the chord to that note: on another
  string no finger is holding the note, so a marked step would mute the chord it had just
  voiced and sound a note the hand is not on. `decisions.holds_the_shape` is the half that the
  narrowing and the flag share. Measured: **22 of 202** marked steps re-struck the melody
  on another string before the fix — every one of them under `targets`, where a fill's
  compact 6-4-3 shell beats a same-string alternative on `span` — and **0 of 199** now.
  The report that found it was bar 3 of the committed "synthetic common time", four G4s
  over `Eb7`: the two targets held the note on the B string and the two fills moved it to
  the G string, four frets away, while the steps still claimed to be holds.
- **The harmony must also be unchanged.** A note repeating across a *chord change* is
  not a hold: the ringing inner voices belong to the chord the hold began on, so
  printing the new chord's name over a single struck note claims a harmony that is not
  sounding. Those steps are harmonised against the new chord and struck in full, which
  is what the engine already does — only the rendering used to discard it.
  `normalised_harmony()` supplies the comparison: `harmonized_as` when a strategy
  substituted a chord, otherwise the written name, canonicalised to `(root, quality)`
  so `D-7` and `Dm7` are one chord rather than two. The `-7` suffix is an alias of
  `m7` for exactly this reason.
- A **melody-only (`NC`) step is never marked repeated**: it has one active fret and
  no inner voices to hold, so the flag would mean nothing.
- `collapse` in the staff renderer compares sounding pitches, so an unchanged shape
  is normally suppressed entirely as a *hold*. A repeated step overrides that and still
  strikes, because the melody is genuinely re-articulated.
- `step_annotation()` adds `(melody repeated - single note)`, because the
  chord name printed above a single note would otherwise imply a full voicing. The
  annotation is shared with `format_progression`, so the two cannot disagree.

**The hole that is left, named rather than assumed away.** The narrowing happens on the
melody-bearing route. The four melody-alone helpers (`melody_alone._rescue_melody_alone`,
`melody_alone._demoted_to_melody_alone`, `routes._texture_fill_step`,
`routes._no_chord_step`) still choose their
string from the caller's `top_strings`, so a repeat reaching one of them keeps the old
behaviour — re-stated rather than held, and never marked `repeated`, because
`is_repeated_step` refuses a step whose predecessor sounds a single note. Counted over the
committed heads: **67** steps that sound one note re-state the previous step's pitch under
an unchanged harmony, and **one** of them records a different string — a fill under the
walk, whose one-note upper shape is bookkeeping rather than a strike, since a fill under a
walk is `bass_only` and the previous shape is what is still ringing.

Every string the step does not play is marked muted (**`x`**), so the line states
exactly which strings are plucked and nothing else - including a `bass_only` slot,
whose upper voices are held rather than restruck: a string the player must not attack
reads the same as a mute here. Leaving them blank made the line look truncated, and a
blank is indistinguishable from a voice that went missing. (`~`, "let ring", was an
earlier draft and is still wrong: it says the opposite of what a collapse does.)

The HTML marks the whole column with `_CLASS_REPEAT` (`td.repeat`) and tints it. The
cells are otherwise empty, so without the tint a repeated note reads as a gap in the
music rather than as a deliberate single note. The ASCII staff needed no equivalent,
because a gap in a fixed-width cell is already legible.

### The other hold: a beat the thumb invented

Under a thumb line the bass grid is finer than the melody's, so a bar whose tune is a
whole note still gets a thumb note on each of its beats. The steps at those invented
positions are marked **`bass_only`**, and the flag means what it says: nothing above the
thumb is struck, and the shape in the tab is the previous step's, still ringing.

`decisions.is_bass_only` is the one owner of that answer, and it reads **two facts**, not
the step's role:

- **the chord's rhythm did not name the position** (`chord_attack`). A position the
  request named — `--chord-on every-beat`, a stab under a held note — is a fresh attack
  whatever the shape is, so a comp of four attacks a bar stays four attacks;
- **nothing above the thumb has changed** (`decisions.melody_is_ringing`): the harmony is
  the one already ringing and the melody is the note still sounding. A note repeating
  across a *chord change* is not a hold — printing the new name over the old voices would
  claim a harmony that is not sounding — so such a step is voiced afresh and struck.

The role is deliberately not consulted. A slot the walk invented on a strong beat is a
`target`, and reading that as "a target states its harmony, so it cannot be a hold"
silenced nine downbeats of "But Not For Me" whose harmony had not changed at all; the
same reading then re-plucked every tied melody note in the tab, the score and the GP5
file on the beats the walk had invented. A `bass_only` step also **clears `repeated`**:
the two flags name opposite halves of one column, and the renderers take their union.

The four renderers agree by construction, and each says "nothing above the thumb is
struck" in its own notation: the one-line tab and the staff draw the thumb and mute the
rest, `tabgp` writes the thumb as a new note and the ringing shape as ties, and `tabxml`
re-states those pitches and ties them — a score has no other way to say *still sounding*.

**One measured caveat, stated rather than left to be discovered.** The shape a held step
records (`step.voicing`) is the one the selector preferred; the shape that *sounds* is the
one already down. They are the same shape in all but a handful of cases — over the
committed heads under `--bass-on 1,2,1and,2and`, **3 of its 293** held shapes differ in
*what sounds* (the same chord, the same melody, another voicing of it); under
`--bass-on every-beat`, **0 of 112**. Another **40** and **14** move a voice to a different
string with the same pitches, which no renderer can show. A held step whose recorded
voicing is the thumb alone (`grip == "bass"`, a comping step's hold — 8 in the melody row)
is in neither count: it has no upper shape to compare. What a hold means is that the hand
does not move, so the ringing shape is what the tab, the score and the GP5 file draw, and
the annotation says `the shape above is held` rather than naming a voice nobody plays. The
selector's preference is simply not acted on there, exactly as a repeated melody's is not.

## High melodies move down an octave

The user requirement was "anything over the 13th fret, play the soprano on the B
string and move the harmonisation down". The trap is that this is **not** a
re-stringing: the B string is five semitones below the high E, so the same written
pitch sits five frets *higher* on it (`D5` is fret 10 on the high E, fret 15 on the
B). Simply choosing the B string would move the voicing *up* the neck, and for
anything above `F5` the B string cannot reach the pitch at all (`B3` + 18 frets =
`F5`). Dropping the melody an octave is the only thing that actually lowers the
position — it lands a major tenth below where the note sat on the high E.

| name | role |
|---|---|
| `HIGH_FRET_LIMIT = 13` | the neck position above which the move happens |
| `get_octave_down_candidates(...)` | candidates for the melody an octave down, B string only |
| `lower_soprano_strings(top_strings)` | the soprano strings below the high E, so the transposed note is not put straight back on the high E |
| `ArrangementStep.original_melody` | the written pitch, when the step was transposed |
| `_note_name(midi)` | spells a MIDI number (`Bb5`); `musthe.Note` parses strings only, so a transposed pitch must be spelled before it can be rebuilt as a `Note` |

Three decisions are load-bearing:

- **`get_all_drop2_voicings` stays pure.** It neither filters by fret nor
  transposes, so it and `get_octave_down_candidates` cannot recurse into each other.
  Filtering it was tried first and broke the documented "both families are offered"
  contract that `tests/test_voicings.py::TestMelodyStringChoices` asserts.
- **The guard requires candidates to exist.** This repositions a voicing that is
  playable but too high; a melody unreachable at the written pitch (`B5` is fret 19,
  `C6` is fret 20 — past the end of the board) is still emitted as a rest, with
  `silence="out_of_reach"` on the step and `_silence_clause` naming the reason.
  Silently respelling it would hide a real problem behind a plausible-looking tab.
- **The transposition is reported from the sounding pitch, not the fret.** The
  octave-down note lands at a *lower* fret, so a fret comparison would read it as
  untransposed. `max(voicing.midi_notes())` is the reliable test.

**Known limitation.** The decision is per step and applies to the melody only, so a
melody leaping across the limit can arrive an octave apart from its neighbour. A
transposition applied to a whole head at once could not tear the line apart, and this
can. The trade is deliberate: no step is ever left unplayable, at the cost of one
melodic interval.


## Known limitations

- Voicings use two to four strings, never all six. The melody may be on the high E, B
  or G string; the A string and low E are inner voices only, so no grip puts the
  soprano on either. No grip is a barré chord; a repeated fret is written as frets, and
  `fingers.py` does mark a barre where two strings share one, though no renderer prints a
  fingering. Fret `0` does appear when a voice happens to
  land on an open string (e.g. `x-2-3-0-3-x`). 6-4-3, 5-3-2 and 6-4-3-2 are the
  non-contiguous sets.
- Melodies are still confined to `G3`–`Bb5`: `G3` is the lowest pitch reachable on the
  G string, `Bb5` the highest on the high E string. The *chord* range reaches further
  down, to `E2` as a bass voice on the low E string in a 6-4-3 shell.
- **A fixed max fret span of 5 rules out close position for most melodies, and drop-3 on
  the contiguous block.** A close-position four-note chord under a melody spans a seventh
  or more, and the four strings below the high E are only five semitones apart in tuning,
  so the frets come out more than five apart (Cmaj7 close under C5 wants frets 8, 12, 12,
  14); drop-3 spans a twelfth by construction. `drop3` and `drop24` are offered anyway,
  because the bass may skip to a lower string and that is enough to bring both inside the
  span limit — see `GRIP_STRING_SETS`. `closed` shares those same bass-skipping sets and is
  offered **second** in `GRIP_PREFERENCE`, so it takes a tie against every four-note family
  but drop-2: measured at `GRIP_MAX_SPAN["closed"] == 5` it returns **27** shapes over
  ten melody notes × five qualities (spans 2 and 5) — 1 under a C5 melody for `Cm7`, 0 for
  `Cmaj7` — so it is reachable per melody rather than never, and generating it lets those
  steps use it without handing the selector a family most melodies cannot fret. Over the
  committed heads the family moves **66 of 799** steps (1, 0, 5, 11, 0 and 49 across the
  six). The **tie-break itself** decides **2 of 120** single-step cases, both `Cmaj` on the
  B string (melody `C4` or `G4`), where the two shapes differ only in whether the root or
  the 5th is in the bass — which criterion 6 deliberately scores the same, so the order is
  what decides: `x-3-2-0-1-x` and `x-10-10-9-8-x` against the drop-2 & 4 readings
  `3-x-2-0-1-x` and `8-x-10-9-8-x`. Raising the span to admit the rest is a real change to
  the library's playability contract, not a tuning knob.
- **A chord tone with no matching inversion used to fall through to the quality-only
  fallback**, which can sound a note the chord does not contain — a 9th in the melody of a
  13 chord, for example. That gap is **closed**, and closed for every chord tone: the rule
  answers for all 125 degrees of the 29 qualities, each pure and stating both guide tones,
  so `get_drop2_voicings` has a shape of its own for every chord tone a melody can be.
  `tests/test_grip_tables.py::TestKnownTableGaps` pins the closure, so a regression re-opens it
  visibly rather than silently.
- **A *non-chord* melody is still offered borrowed shapes.** No degree matches it, so the
  palette (`_drop2_palette`) hands the selector the rule's shape for each chord tone,
  placed under the caller's own note — and a shape built for one degree can spell a note
  outside the chord under another. `voicing_cost`'s first criterion rejects such a shape
  whenever a pure one exists, so an *arrangement* hears one only when nothing else is
  playable, but `get_drop2_voicings` still offers it.
  Measured over 25 transcriptions after the head-path fix, **26.0%** of head steps still
  carry an inner voice outside the sounding chord, against **23.0%** for the same
  progressions through the library. The two are close, which is the point: the head
  path is no longer a second, weaker implementation of the same rule.
- A melody that can only be voiced above `HIGH_FRET_LIMIT` is moved down an octave,
  so `step.melody` can be an octave below the written note. The decision is per step
  and applies to the melody alone, so a leap across the limit can leave one melodic
  interval an octave wide. See
  [High melodies move down an octave](#high-melodies-move-down-an-octave).
- A fixed max fret span of 5 and fret range 0–18 is assumed.
- Non-chord melody notes are only covered for the mappings in
  `NON_CHORD_TONE_EXTENSIONS` (9ths, 6/9s, 11ths, #11s, b13s, 13ths, the
  half-diminished 9th and the 9th over a plain triad) plus the dim7 substitution. An
  unmapped non-chord tone keeps the quality-only fallback, which can sound the melody
  over a different chord's shape — and the step's non-chord-tone clause says that is
  what happened.
- **A palette that cannot voice a chord leaves the tune alone** rather than dropping it.
  `shell`, `duo` and `interval` are built from the chord's own degrees, so they have no
  quality-only fallback to thin to — where the four-note families always have something.
  Under a shell-only palette a note with no mapping and no shell therefore had **no**
  candidate
  and the step was dropped with the melody in it: measured over the committed heads,
  the dropped notes were overwhelmingly non-chord tones the table cannot route, with a
  smaller number of chord tones the shell's geometry cannot place. Every one now sounds,
  alone, and the step says so. Two things bound the rescue: `top_strings` is still
  honoured — a note the named strings cannot carry is refused, which is what
  `tests/test_progressions.py` pins, the position emitted silent — and a melody no string
  reaches at all is likewise emitted silent rather than voiced, with `silence="out_of_reach"`
  on the step and `_silence_clause` naming the palette.
- A handful of low melodies (around `G3`–`C4`) reach no chord-tone-matched inversion
  and therefore use the quality-only fallback. Triad shapes double the root, so their
  second voice can sit up to 10 semitones below the melody — the same span limit, not a
  new failure mode.
- **A partial harmonisation means the printed chord name is not every note sounding.**
  Where a shell or a duo is used, the chord describes the harmony rather than the full
  voicing, and `step_annotation` says so and says why (`(shell - 3rd & 7th, partial -
  3 voices: the 4-voice voicing 2-x-1-2-0-x lies outside the neck window)`). The reason
  comes from the recorded `ArrangementStep.palette` rather than a re-derivation, so a thin
  shape is explicable rather than mysterious: a palette that never held four voices reads
  differently from one that did. The full shape is still in `step.voicing`. This is a
  consequence of the user's own brief — "just harmonising with the 3rd and 7th is fine" —
  not a defect, but it is a real thing to know before reading a tab.
- The `sustain` strategy is structural, not rhythmic: `arrange_progression` takes
  only `(note, quality, name)` triples, so it cannot tell a brief passing note from
  an accented tension. Holding the inner voices is applied whenever the shape can
  physically stay put.
- `7b9`/`7alt` are voiced rootless apart from their new root-in-top inversion;
  other omitted tones (e.g. a root-on-top `13`) have no template yet.
- If no voicing matches a melody/chord, `arrange_progression` **emits a rest step** with
  `silence="no_shape"` — the bar stays on the tab and `_silence_clause` says why — rather
  than raising or dropping the position.
- **Texture (`texture="targets"`):**
  - **The target-note rule is a fixed `(1, 3)`.** There is no way to say "chords on
    beat 1 only", or "fills on beat 2 as well", or to mark a bar that is all target
    notes — a cadenza or a shout chorus, say. The rule lives in one function
    (`roles_for_slot`) and one table (`TARGET_BEATS`), which is where a change would
    go, but neither is configurable per call.
  - **A fill that cannot be filled becomes a target.** Measured over melid 218, 2 of
    30 weak slots take this path, so a `targets` arrangement is not uniformly thin: a
    reader looking for "chord on the beat, nothing between" will still find a few
    full chords between. That is deliberate — see the section above — but it means
    the texture is a *tendency*, not a guarantee.
  - **Strong-beat fingerings differ from a `uniform` arrangement.** A target is
    voice-led from the shape before it, which is now thinner, so it does not keep the
    same position. Correct, but it means the two textures are not comparable
    fret-for-fret.
  - **The `interval` grip's diatonic fallback assumes a major key.** `_interval_offsets`
    reaches for major-scale pitch classes when the melody is outside the chord, which
    is right in most standards and wrong in a genuinely modal passage, where a
    non-diatonic note may be the *point*. The `key` argument the plan anticipated was
    not added: nothing in the pipeline supplies a key, and inferring one from the
    chord progression would be a guess.

### Melody alone: `parts="melody"` and `parts="melody,bass"`

Two selections that answer "lead sheet in, the tune out". `parts="melody"` plays the
melody and nothing else, and `parts="melody,bass"` plays the same line with a walking
thumb under it and still nothing harmonising it. Neither is a *grip*, for the reason
above: what they change is which parts sound at all, and a grip would have to win a cost
comparison it should not be in. `parts="melody,bass"` is one selection plus a `bass=`
answer rather than a second mode: the thumb line is the bass part's own axis.

A melody-only selection reaches `melody_alone_case` through the selection itself
(`parts.parts_has_melody_only`), which is the fact that says the chord part is not the
guitar's - not through a palette, because the empty palette that used to declare this is
gone with the grip axis: no texture, selection or thumb line yields one now
(`tests/test_texture.py` sweeps them all and requires a non-empty palette). The route is
`get_melody_only_voicings`, whose palette is one position per
eligible string, and the selection among them is `cost.voicing_cost`'s - so the note a
melody-only selection states lands by the same window and hand-travel criteria a chord
does. The step it builds keeps
`melody_only=False` — the harmony still exists and the chord name is still printed as
context, so the flag that would annotate "(no chord - melody alone)" would be claiming
something false.

Three decisions are load-bearing:

- **One predicate names the selections, derived from the parts.** Any site that decides
  "does this slot become a single note" reads `parts_has_melody_only(parts)` — the
  melody part present and the chord part absent, the bass part deliberately not — and
  never a texture named as a literal. A literal is how a spelling joins the melody-alone
  route in one place and misses it in another.
- **No texture carries an empty palette any more, and that is asserted.**
  `tests/test_texture.py` sweeps every texture, selection and thumb line and requires a
  non-empty palette from each, because an empty one means "the left hand plays nothing"
  and that claim belongs to the selection rather than to a row.
- **A solo note is one string, and that is inside the playability invariant.**
  `supported_string_sets()` lists the six singletons; a melody-alone step has one
  active fret. That has always been true of an `NC` bar and a walking-bass fill; a
  selection that builds an entire output on it makes it a headline, so it is stated
  and pinned in `TestMelodyOnlySelections` rather than left implied by a test that
  happens not to look at it.

The two selections differ in exactly one thing — the thumb line — which is what makes
them one selection plus a `bass=` answer rather than two spellings: `parts="melody,bass"`
is `parts="melody"` with a thumb line under it, and `bass=auto` reads the selection (the
table below).

### The bass style: `bass=` as its own axis

The thumb line used to be part of a texture's *name*, so one word meant both "a shell on
the strong beats" and "a note on every beat below". Two separable decisions
wearing one identifier. It is now `texture=` (the left hand) crossed with `bass=` (the
thumb), and `bass=auto` — the default — means **no line at all**: a caller who wants one
names the note rules or a `bass:walk` grid row. The sentinel still writes a line in one
case, and it is a selection rather than a texture:

| selection | default bass | equivalent to |
|---|---|---|
| `parts="melody,bass"` | `root,5th,approach,nearest` | `parts="melody,bass", bass="root,5th,approach,nearest"` |
| everything else | `none` | `bass="none"` |

`parts="melody"` alone keeps no thumb, and the two spellings are one arrangement:
`parts="melody", bass="root,5th,approach,nearest"` is the tune with a thumb line under it.
A lone `parts="bass"` selection keeps none either: that part already is the bass line, and a
thumb under it would double it.

All the equivalences are asserted byte-for-byte against the rendered tab, so nothing moved
when the axis was separated out.

The **vocabulary** lives in `arranger/bass_rules.py`: `BASS_RULES`, the `BASS_ROLE_*` and
`BASS_STYLE_*` names, `parse_bass_style`, and the questions asked of the hands
(`thumb_capacity`, `comping_capacity`, `bass_allowed`). `arranger/bass.py` owns the line
itself - its slots and its walk - while `arranger/bass_place.py` owns the thumb's
placement and `bass_cost`.

**The style names note rules, and the set of rules is a registry, not a flag**, because
it is open and is meant to stay that way. `BASS_RULE_ROLES` maps each rule to the
`BASS_ROLE_*` values it admits, and `bass_line_for` resolves a style's rule list into
the roles it keeps and applies that as *a filter over the roles `_walking_bass_line`
already assigns*. So:

- `root,5th,approach,nearest` (the whole vocabulary) keeps every role — a note on every
  beat. This is the walk.
- `root` keeps only `BASS_ROLE_ANCHOR` — a root where the harmony anchors. This is what
  `anchors` became.

The four rules are `root` (the chord's root, on anchor beats), `5th` (root then 5th, the
`BASS_DEGREES_6432` order — the walking anchor is always the root, so it shares `root`'s
beats), `approach` (a note reaching the next anchor — the last-beat approach and the
penultimate enclosure, one rule at two beats), and `nearest` (the connective vocabulary
— a chord tone, an extension, or passing motion). `hold` is deliberately **not** a rule:
it is the fallback of "first reachable wins", ranked last whatever the style says.

The shipped resolution order is `root, 5th, approach, nearest`. `approach` sits before
`nearest` because on the last beat the approach outranks the connective note — that
ordering is what makes the full list byte-identical to the old `walk`
([parts.md](history/parts.md) §9 records why it is not §4's literal order).

**A style is a set of note rules, so it cannot state anything where there is no chord.**
The harmony the walk reads is a forward fill, and an `NC` slot **ends** that fill rather
than continuing the previous chord across it — a part whose notes are chosen from a chord
has no event where there is no chord ([parts.md](history/parts.md) §4). The emission already
skipped a beat with no harmony in force, so this is the whole of the rule. Two
consequences a caller meets: a chordless bar between two chords contributes **no** thumb
notes at all, and the walk's approach into it now targets the next chord that *sounds*
rather than the phantom root the gap used to carry. Note that "no chord here" is not "a
chord this library cannot voice" — an untranslatable symbol leaves the harmony in force,
because the chord is still the music's and only its spelling is past this library.

`anchors`-style sparseness is deliberately **not a second generator**. The harmonic
reasoning about what a bass note is *for* is written once, and every style inherits it;
they cannot drift apart because one is a subset of another by construction. A rule that
needs new reasoning gets its own generator beside `_walking_bass_line` and a row in the
table; a rule that is a different reading of an existing note is a row.

`BASS_STYLE_AUTO` is deliberately **not** a rule. It is a default for an argument, not a
note a caller can ask for, so keeping it out means `arrange_progression` validates a
style against the rules and never has to special-case a sentinel. `parse_bass_style`
refuses `auto` and `none` as rule names, and an unknown rule raises rather than
defaulting to a walk.

**One refusal rule, derived rather than listed: a thumb line needs one free bass
string.** `thumb_capacity` computes it from `texture.texture_palette` and
`GRIP_STRING_SETS` — the left hand's palette is the whole question — so a texture added
later cannot reach the thumb-line route without its capacity being measured too. Measured
here:

```
targets, a fill                            all three free
targets, a target under a thumb line       one
uniform                                     one, and **zero** until the four
                                           inner-skip `drop24` sets were removed
```

A melody-only **selection** is not in the table at all: its upper shapes are single
frets, so all three thumb strings are free whatever the texture's palette says, and
`bass_allowed` answers its capacity unbounded when the route is known.

**Nothing in the tree is refused any more, and that is a consequence of the grip tables
rather than of this rule.** `uniform` used to be the one that failed: its palette held
`drop24`'s `(4,2,1,0)`, the one reachable set that spanned all three thumb strings, so
`bass="root,5th,approach,nearest"` under the default texture was refused, naming a texture that
would work. Removing the four inner-skip `drop24` sets for the right-hand reason in
[fingering.md](history/fingering.md) §4.4 removed that set with them, so the worst case anywhere
is now one free string — the rule's threshold — and `uniform` carries every policy. The
refusal and its reason string stay, because the question is still the right one: the
comping route is answered by `comping_capacity`, and a palette added later that reaches
the whole thumb range is caught here without this function being taught about it.

Two honest caveats, both measured rather than assumed:

- This is the **worst case across the sets a grip may use**, and in practice the
  selector rarely picks the worst one. On "the synthetic cut-time head" every `uniform` step still
  left a string, even under the old tables that made the refusal fire. The rule is
  deliberately conservative: it refuses a combination that would usually work rather than
  shipping a line that is occasionally holed.
- **A thumb line is lossy under a chord-stating texture, and always was.** Measured on
  "the synthetic cut-time head" bars 1-2: `targets` loses 11 of 151 thumb notes (7.3%) under a
  `bass:walk` row and 7 of 88 (8.0%) under `bass:anchors`, while a melody-only selection
  loses **none**, because a single left-hand note leaves every thumb string free. So the
  rule was aimed at the one combination that can *never* work and let the
  others through, each dropped note reported on its own step by `bass_refused`, rather than
  refusing a texture whose loss
  rate is the same order as the flagship's — and the one it did refuse lost the set that
  made it fail, so the rule now has nothing to fire on.

**The other half of the budget: four fingers on the right hand.** A thumb line needs a
free bass *string*; it also needs a free *finger*, and those are different questions.
The right hand plucks with thumb, index, middle and ring — `p-i-m-a` — so a step may
sound four strings and never five. `thumb_capacity` only ever answered the first: a
`targets` target has a free thumb string, so `bass_allowed` let the axis through, and
then a **four-note** target had a bass note merged under it — five plucks at once.

The rule is `grips.thumb_safe_grips`, derived from `GRIP_STRING_SETS`: while a bass note
is being placed under a slot, a **target** may sound at most three strings, and a palette
with none is narrowed to the widest statement that leaves a finger free
(`("drop2", "drop3")` → `("shell",)`). It narrows *this slot's* palette rather than the
arrangement's, because a target with nothing underneath it may use all four strings.

`AGENTS.md` trap 13 holds the measurement — the step counts, and why a shape-level
invariant could not see the defect — and
`tests/test_walking_bass.py::TestTheInvariant` is the standing count. What the rule costs:
a target whose quality has no shell — `Bmaj` under a `D5` melody, say — is a melody alone
over the thumb rather than a four-note shape nobody can play.

### `parts=` as the third axis: which of melody, bass and chord the guitar takes

`texture=` answers *how thick the chord part is*. `parts=` answers *which parts this
instrument plays at all*, and it is an axis of the same kind rather than a mode — a band
setting is a **combination**, not one name.

Three parts, because four strings sound at once and four strings is not four parts:

- **melody** — 0 or 1 note. The tune, on the top string. Its rhythm is data, not choice.
- **bass** — 0 or 1 note. The bottom of the band. The note that names the chord.
- **chord** — 0 or more, the arity `texture=` states.

The fourth string is **capacity, not a part**. `melody + bass + chord <= 4`
(`grips.RIGHT_HAND_STRINGS`) is arithmetic rather than a rule: a selection that does not
fit is refused before anything is generated, and `grips.thumb_safe_grips` and
`supported_string_sets()` are where the engine enforces it.

**The right hand is `p-i-m-a`, and it assigns *strings*, not voices.** Take the strings a
step plucks, sorted low to high, and hand them out in that order - thumb, index, middle,
ring - **provided the lowest of them lies on the low four strings (E A D G)**: a shape whose
bottom note sits on the B or the high E has **no thumb in it at all**, and the lowest pluck
is the index (`grips.THUMB_REACH_STRINGS` is that reach). The consequence worth stating is
that the thumb takes the bottom string whether or not a bass *part* is sounding - the merged
bass note is written into the fret vector only *after* selection, so no right-hand reading
ever sees it - which is why **the bass part is not the thumb**, and a shape with no bass
line still has its bottom note taken by the thumb.

Two gaps are not equal. A gap between the **thumb and the index** is free while the thumb is
the bottom digit: it strokes across a muted string, which is what the bass-skipping string
sets are built on. A gap crossed by the **middle or ring** finger is a real reach.
`grips.finger_skip_count` is that metric, and the string tables are held to it by test
rather than by the selector - the four `drop24` sets that carried a skip were removed.

The left hand's budget is **four fingers and five frets**, and unlike the four-string rule it is
stated over a *step* rather than a shape: `fingers.can_fret` is the check, and it refuses both a
fifth fretted position (`fingers_needed`) and a reach wider than `fingers.MAX_HAND_SPAN`. Its
callers are `bass_place.place_bass`, which asks before it picks a string, and
`bass_merge._takes_the_ring`, which asks before it lets a struck note keep ringing under the next
shape. So a bass note that would need a fifth fret, or that would leave the hand spanning more
than five, is refused there rather than inside a shape - and `AGENTS.md`'s playability invariants
hold both.

**The note is not only refused; the shape is asked to make room.** A requested grid bass note is
part of the request, so `decisions.leaving_room_for_the_bass` narrows the palette to the
candidates `bass_placement` can put the note under, and the same cost tuple ranks what is left.
That is a **narrowing and never a criterion**: no candidate carries a thumb, `cost` still sits
below `bass_place` in the DAG and cannot ask the question, and a palette where nothing survives is
returned unchanged so the step keeps its shape and `bass_refused` names the note. The shape that
the ranking preferred before the narrow is recorded on `Palette.dropped_for_bass`, because a
reader counting strings otherwise cannot tell a shape that moved for the bass from one that was
simply ranked lower.

| axis | owns | values |
|---|---|---|
| `parts=` | which of melody / bass / chord the guitar takes | any subset of `melody`, `bass`, `chord`; `auto` *(default)* is all three |
| `texture=` | the **chord part's arity**, by metric weight | `uniform`, `targets`, `chord1`, `chord2`, `chord3` |
| `harmony=` | the chord part's **degree order** | `auto` *(default)*, `full`, `guide`, `shell_root` |
| `bass=` | the bass part's **note rules**, in the order they are tried | `auto` *(default)*, `none`, or an ordered list of `root`, `5th`, `approach`, `nearest` |
| `grid=` | **when each part sounds** | `PART:PATTERN` rows — see `` `grid=` `` below |

**Order carries no meaning, so the selection is canonicalised.** `parse_parts` returns
`PART_NAMES` order, so `parts="chord,bass"` and `parts="bass,chord"` are one request and
not two that happen to agree. `auto` names every part; `none` is refused rather than
expanded, because a selection that names no part has no line to state. An unknown name
raises: a spelling nobody recognises is a question, and answering it by dropping a part
would hand back an arrangement missing something nobody asked it to drop.

`parts="chord"` is the ensemble comping answer: the tune belongs to the horn, the root to
the bassist, and the guitar takes the harmony in between. That is not silence — silence is
not an arrangement — and `parts="melody"` is its opposite, the tune and nothing else.

**Naming a part is a request for it to sound, and a policy for a part the selection leaves
out is refused**, naming the part that would work. Two axes are inert rather than refused:
`harmony=` is read only by the comping route, and `texture=` says nothing on a melody-only
selection, whose shapes are single frets.

**An `NC` bar has no chord part and no bass part**, on every route, and the melody is
unaffected: a part whose notes are chosen from a chord cannot state anything where there is
no chord. That is a derivation rather than a rule about chordless bars, and it is deliberately
*not* what an off-grid rest says — there the thumb still walks, because a grid thins the
chords and not the bass line. "No chord here" and "silent here" are different facts, and only
the second is a rest.

### `harmony=`: which degrees the chord part states

`texture=` says **how many** notes the chord part states; `harmony=` says **which**. The
order is `TONE_PRIORITY`'s row for the quality, read at the chord part's own degrees, so the
arity `texture=` takes is a **prefix** of that row and a reduced shape gives up its **tail**.
For `Cmaj7` (`3rd, 7th, root, 5th`): at three voices the 5th goes, at two the shape is the
guide pair, and at one it is the 3rd alone.

Two facts sit beside the row, and both are already in the tables rather than new here:

- a tone the **melody** states is not a candidate for dropping — the tune is one of the
  chord's voices — so the melody's presence can change *which other* tone is given up
  (`stated_tones` excludes the melody's own degree);
- an **altered 5th** — `Bbm7b5`'s `b5`, a `#11`, a `b13` — is kept over the root, so a
  reduced shape gives the **root** up before it.

`HARMONY_STYLES` is `auto`, `full`, `guide` and `shell_root`, and `HARMONY_AUTO` is the one
sentinel on any axis that **decides** rather than naming its own default: it resolves to the
**full order** when the melody is the guitar's and to the **guide pair** when it is not,
because the two shipped defaults are different shapes and one value cannot be both.
`shell_root` is the guide pair **plus a register note**, so it is one degree order rather
than a conjunction of two tables welded together inside `_shell_voicing`.

The refusals are derived from the rows rather than listed: `HARMONY_LENGTH` names the two
families with a fixed arity — `guide` (2) and `shell_root` (3) — so a selection without room
for that many notes is refused from the row's own length, naming the part that would work.
`full` is absent from that table because its length is the chord's own tone set, and its
consequence is [open-issues.md](open-issues.md) item 3: on the comping route `full` is
accepted and answered with a different family.

**The axis is read only by the comping route.** A grip is a claim about a chord's 3rd and
7th and takes its arity from `texture=`, so `harmony=` cannot reach an arrangement the
guitar sings; a policy named for a part the selection leaves out is refused before anything
is generated.

### `get_comping_voicings`: a chord with no melody on top

The generator behind a `parts="chord"` selection. **It is the same exhaustive search with
nothing held at the top.** A shell is already a claim about the chord's 3rd and 7th rather
than about
the tune, so the search needed no new rule: `frets_in_span` already tries every fret
combination on the remaining strings and the candidate keeps the ones where both guide
tones sound and nothing outside
the chord does. The only difference is that the top fret is searched too rather than fixed
by a melody. Because the window is exactly `GRIP_MAX_SPAN["shell"]`, the search stays
*exhaustive within the playability invariant*.

The shared half is factored into `_shell_voicing` so the melody-bearing shell and the
melody-free one cannot drift apart on what counts as a shell.

**It takes no melody argument, and that is the invariant rather than an accident.** Asking
it for `D5` and for `G3` under the same chord returns the **identical candidate set** — a
generator that read the melody could not do that. `tests/test_comping.py` asserts exactly
this, over eight melody notes and three chords. What the tune *does* decide on this route is
whether the slot is **reharmonised**, and that needs three states rather than two:
`headxml.melody_state` returns **onset** (the tune articulates here — reharmonise: the
anticipation a comping player makes), **held** (a note already sounding — no: it was decided
at its onset) and **silent** (nothing sounding — the chord symbol stands). In the measurement
that produced the rule, **274 of 1,146** grid positions carry a held note rather than an
articulation — a quarter, so the middle state is not an edge case; `melody_at` keeps its
two-way answer for callers that only need "is a note sounding".

**A note that crosses a barline is held on the far side.** `melody_at` converts a note's
whole-note duration to beats with `beat_type` and compares it to the probe on one absolute
beat line (`grid.beat_offset`): `duration * 4` is right only in 4/4, and a `(bar, beat)` pair
cannot express a note that ends in a later bar. A 2/2 note written to the barline is therefore
still sounding at the next bar's downbeat, and the default grid does not re-strike it there.
The end instant is inclusive — the release is still held — and that boundary is the open
decision [docs/open-issues.md](open-issues.md) item 6 records, pinned by
`tests/test_headxml_timeline.py::TestMelodyState::test_the_release_instant_counts_as_held_until_the_next_position`.

**The arity is the length of the selection, and it is honoured.** `notes` says how many
voices the guitar was asked for, and a two-voice request is **two notes**. The first
version of this generator always built a three-note shell, so `texture="chord1"` and
`texture="chord2"` both came back with three — a part sounding a note nobody named,
which in a band setting is a voice another player was supposed to have.

**The arity picks the grip family rather than truncating one.** Truncating a `shell` set to
two strings looks free and is not: it yields pairs the library has never measured —
`(0, 2)` skips the A string, `(5, 3)` skips the B — and they would enter the tab as though
they had been designed for the job. A two-note shape is a `duo`, the family this library
has always offered for exactly that, so two voices take the `duo` sets and three take the
`shell` sets unchanged.

**On a position the guitar does not sing, the soprano's string is free.**
`texture.comping_arity` drops the melody part from the arithmetic for that one slot,
because nothing is sounding on the string the tune would use — on a walked beat the note is
held rather than re-struck, and on a comping slot it belongs to the horn. It is a fact about
the *position*, not a rewrite of the selection: `parts_have_melody` still says whether the
guitar sings at all.

**One voice is a weaker claim, and the rule says so rather than refusing.** Two notes can
sound both guide tones, which is what states the chord; one note cannot, so a single note
keeps the **first** guide tone (the 3rd, or the 4th on a sus chord) — the same preference
order `_duo_offsets` already applies. Refusing instead would have made `texture="chord1"`
fall through to the melody-bearing route: measured, it put the horn's line back on the
guitar on every step, the opposite of what asking for one note meant.

**With no melody to support, a fourth voice would be the root or the 5th** — the two notes
that carry no information about the chord's quality. That is why only the `shell` family is
offered at all.

**A quality with no readable root gets nothing**, on the same rule as every other
guide-tone generator here: a shell is a claim about *this* chord's 3rd and 7th, and guessing
them without a root is how a wrong note gets into the tab.

**The playability invariant, minus the melody clause.** Every candidate sounds only chord
tones, sounds exactly the number of notes asked for, occupies one string set from the
matching family, and holds a span within that family's `GRIP_MAX_SPAN`. The dropped clause
is "the melody is on the topmost string", and it is dropped for the only reason there is:
there is no melody.

Measured over 2,069 comping steps:

```
notes per step          2        (2069 of 2069)
melody_voiced           False    (2069 of 2069)
supported string set    yes      (2069 of 2069)
over GRIP_MAX_SPAN      0
wrong notes             0
guide tone missing      0
unreadable chord        610      (no tone set at all; the library's own rule is not to
                                  judge a chord it could not read - see cost.voicing_cost)
```

**What is *not* claimed, measured rather than assumed.** A comping step may well contain the
melody's own pitch: **409 of 2,069 steps do.** That is coincidence, not the guitar
singing — the melody's pitch class is often a chord tone the shell needs anyway. What the
axis guarantees is that the shape was *chosen from the chord alone*, and that
`step.melody_voiced` is `False`. An earlier version of this document and of the test suite
claimed the stronger, falsifiable version ("no step sounds the melody"), and the
measurement is what corrected it.

### The renderer rule: a repeated melody holds the whole shape

Normally `repeated` is a **soprano-only re-strike** — the melody re-articulates under an
unchanged harmony, so the inner voices are held. That presumes there *is* a soprano
carrying the tune. Under `parts="chord"` there is none, so "re-strike the soprano" would
re-strike a guide tone and the shape would change on a beat where nothing has. The rule
becomes **hold the whole shape**, which is what a guitarist comping behind a horn does while
the horn repeats the note.

**`chord_attack` is the other half of that rule, and the two are told apart by the request
rather than by the pitches.** A comp on `--chord-on every-beat` repeats one shape four
times a bar, and a slot the tune merely sustains through has the same pitches — so the
renderers, which compare shapes, could not tell a re-strike from a hold, and folded the
named position into the one before it: the arrangement said four attacks and the score,
the staff, the HTML and GP5 all wrote **one long chord**. `slot_plan._chord_attacks` sets
`ArrangementStep.chord_attack` where the chord part was *asked* for the attack — a position
`--chord-on` named (including the stab `--chord-on melody,1and` puts under a held note), or a
slot the chord layer invented because the tune is silent there — and a slot the
eighth-note skeleton invented under a sustaining note keeps its hold. Measured on the
committed heads under the default comping request: the flag restores **103 attacks** — 38%
of the 270 sounding steps, across 9 of the 13 heads — and changes **no** melody-bearing
step, because a written onset there already strikes through `repeated` or by carrying a
different soprano.

This is not a corner case. Measured over 2,243 corpus steps, **152 carry `repeated`**, and
keeping the old rule rendered every one as a single moving note — a melody line on the
guitar part, on exactly the beats where the arrangement had handed the tune away.

The rule is stated in **two** places, `render._step_cells` and `tabstaff._strikes_here`,
because those two are what keep the one-line renderer, the ASCII staff and the HTML from
disagreeing about what attacks. `tests/test_comping.py::TestRepeatedStepsHoldTheShape`
asserts they agree, string by string. `tests/test_chord_attack.py` holds the flag's half:
the rule, and the four renderers reading it.

### Two consequences, both derived rather than listed

**A texture that harmonises nothing cannot also give the melody away — and no texture
harmonises nothing any more.** The refusal `melody_allowed` used to make dissolved when
the melody-only claim moved onto the selection: a chord-only selection simply comps, on
every texture, and nothing is self-contradictory anywhere. The equivalent fact on the
selection axis is `parts_has_melody_only`, which is derived from the parts rather than
listed, so a spelling that cannot be voiced cannot miss it either.

**`melody_alone_case` gains a guard, because its routes all end at the melody alone.** Every
answer it gives reaches `get_melody_only_voicing`, so under `parts="chord"` it must not
answer `MELODY_ALONE_TEXTURE` — or a texture *fill* would put the tune straight back on the
guitar, and the axis would be honoured only on targets. Measured: before the guard, every
fill under `texture="targets", bass="root,5th,approach,nearest"` came back `x-7-x-x-x-8`, a bare melody note.

**An `NC` bar is emitted silent, with the reason on the step.** There is no chord, so
there are no guide tones, and the guitar is genuinely silent while the horn is not. The
position is a rest step carrying `silence="nc_comping"` - the tab keeps the bar, so a
reader lining the comp up against the tune is not one bar short - and one sentence
names the reason, rather than reaching the generator (which correctly refuses a chord
with no root) and then falling through to a melody-bearing route that would either state
it twice or hand the horn's line back to the guitarist.




## `grid=` — where a chord falls

`harmony=` answers *which degrees* a stab states; this answers *where one lands*. A
comping style needs both, and `bass=` supplies a third orthogonal question (what plays the
bottom). The vocabulary is `GRID_PART_PATTERNS` + `GRID_STYLES` + `GRID_PATTERNS` in
`grid.py`, with `parse_grid` / `resolve_grid` / `grid_allowed` /
`grid_defers_to_melody` beside the other axes' functions. A row is written **`part:pattern`**
— `chord:freddie`, `bass:walk` — so the axis is positions crossed with parts, and each part
may have a row of its own. There is **no `auto` grid value**: `GRID_DEFAULT` is
`melody:every_note`, so the tune's own slots govern every part, and `grid=auto` is refused
like any other unknown name (see [comping-styles.md](history/comping-styles.md) §9.3).

**Positions are `(beat, eighths)` pairs, and `beat` may be a sentinel.** `LAST` resolves
to the metre's final beat and `ALL` to every beat of the bar, so a pattern names *a
position* rather than a beat number — `final_and` is 2.5 in 2/2, 3.5 in 3/4 and 4.5 in
4/4 from one row. `eighths` is an **integer count of eighths**, not a float, because a
notated position is a float in practice (a 3/4 bar's second beat is 1.666...) and
comparing floats for equality is a comparison that will eventually be false for the wrong
reason — the same argument as `BEAT_EPSILON`. The subdivision is
`grid.TICKS_PER_BEAT = 24` — a beat in whole twenty-fourths, integer on purpose — so a
position is a tick number and never a rounding of one.

| pattern | positions | kind |
|---|---|---|
| `every_note` | **none** — the absence of a restriction | bar-relative |
| `freddie` | `(ALL, 0)` | bar-relative |
| `final_and` | `(LAST, SUB)` | bar-relative |
| `charleston` | `(1, 0), (2, SUB)` | metre-relative |
| `joe_pass` | `(ALL, SUB)` | metre-relative |
| `walk` | `(ALL, 0)` | bar-relative |
| `anchors` | the harmony **timeline**, not the metre | `GRID_TIMELINE_PATTERNS` |

Not every part may use every row: `melody` has `every_note` alone, `chord` has
`every_note`, `freddie`, `joe_pass`, `final_and` and `charleston`, and `bass` has
`every_note`, `walk` and `anchors`. `GRID_PART_PATTERNS` is that table, and the parser
refuses a row it does not hold.

**`bar_relative` is a property of the pattern, not a comment.** It says whether a *silence*
is the arranger's mistake: a bar-relative pattern resolves in any metre, while a
metre-relative one is a named figure of a particular metre and is either right or is a 4/4
figure asked of a 2/2 bar. That is the arranger's calling, not an engine defect, and
recording it as data is what stops "the pattern silently did nothing" reading as a bug.

**`every_note` is not a pattern with positions; it is the absence of one.** `grid_positions`
returns nothing for it, so `grid_allowed` must test it explicitly — deriving the check from
`grid_positions` made the *default* a mismatch in every metre, which is the false reading the
check exists to avoid. "Places nothing" and "has no positions to place" are different
claims and only the first is a mismatch.

**The refusal is unreachable through the shipped rows**, measured: every metre-relative
pattern fits every metre, because `charleston` keeps its beat 1 and `joe_pass` is built on
`ALL`. `grid_allowed` is therefore defensive, and the refusal and its reason are tested
against a temporary row. `tests/test_grid.py::test_no_shipped_row_is_a_mismatch_in_any_metre`
exists to keep that fact from being forgotten — a check no input can fail proves nothing.

**`beat=None` is on the grid.** A slot nobody located has no position to be off, the same
rule `metric_weight` follows with its `-1`. Without it a hand-written progression — which
carries no timings — would lose every chord the moment a grid was passed, which is the
opposite of an opt-in.

### What an off-grid slot does, and why it is a fourth kind

`decisions.melody_alone_case` returns a *kind*, and the grid added `MELODY_ALONE_REST`
alongside `MELODY_ALONE_NONE`, `MELODY_ALONE_TEXTURE` and `MELODY_ALONE_NO_CHORD`:

- **guitar singing** → `MELODY_ALONE_TEXTURE`: the note of the tune sounds alone. No note
  is dropped, ever.
- **guitar comping** → `MELODY_ALONE_REST`: the guitar is silent. There is no melody on
  this guitar to play alone, and the tune is the horn's. The step is still emitted, so the
  part keeps its bar and beat and lines up against the tune; all six strings are muted, so
  every renderer draws silence rather than a held shape.
- **`NC`** → unchanged per route. It has *no chord to place*, so "off the grid" is not a
  claim about it: the comping route emits a rest step carrying `silence="nc_comping"`, the
  singing route plays the note alone.

The **ordering of those guards is load-bearing and was got wrong twice** — see
[../AGENTS.md](../AGENTS.md) trap 12 for the three orderings and what each one breaks.

**The grid does not touch the bass line**, and that is orthogonality tested rather than
asserted: measured on `synthetic_cut_time` with `parts="chord", texture="targets",
grid="melody:every_note,bass:walk"`, the walked notes are `[51, None, 52, None]` at both the
`melody:every_note` and the `chord:freddie` chord row. A grid removes chords, never the thumb.

### What is not built

The **free-form** spelling (naming positions directly rather than choosing a row) and a
**held baseline** (`hold=`). **Both were withdrawn on 2026-10-04, on measurement** — a stab
already lasts as long as the melody note under it, because `step.duration` *is* that
note's duration and every renderer already honours it, so "a held baseline" as a flag
would add a second answer to a question the step model already answers. The real gap is
the inverse one: a stab *outlasting* its note.

A **four-note comping chord** is the third, and it is a decision about string sets rather than
about a longer degree order: `derived_arity` caps the chord part at `chord3`, and
`get_comping_voicings` offers the `shell` family alone, because with no melody to support a
fourth voice would be the root or the 5th — the two notes that say least about the quality.
Its consequence for `harmony=` is [open-issues.md](open-issues.md) item 3.

Both withdrawals are [comping-styles.md](history/comping-styles.md) §8 Stage D, and
[open-issues.md](open-issues.md) item 1 is the larger thing underneath them — a grid names
positions the tune does not occupy, and sounding them took a union of the grid's positions
with the melody's own slots.
