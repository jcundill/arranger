# Renderers: tab, MusicXML, Guitar Pro

`tabstaff`, `tabxml`, `tabgp` and `headxml`: the modules that turn an arrangement
into something a musician reads, and the one that reads a written head back in.
They are top-level modules rather than part of the `arranger` package because
`tabxml` and `tabgp` need optional dependencies the engine must not have.

Read this before touching any of them. Nearly every decision below was forced by a
real file, so the reasoning is the point: a "simplification" that drops one of them
reintroduces a bug that was found the hard way.
## The staff renderers live in `tabstaff.py`

`format_tab_staff`, `format_tab_html` and `write_tab_html` are the renderers that
lay an arrangement along **one staff in reading order**, and they live outside the
`arranger` package so the engine can be read without them. `format_progression`
(one line or one block *per chord*) and the vertical `tab_block()` stay in
`arranger/render.py` and `arranger/tuning.py`: they are a different shape of output,
and `Voicing.tab_block()` is called from the dataclass itself.

**They are split together, never separately**, because the two renderings share
`_staff_columns` — which places each step on an absolute beat and decides what is a
strike and what is a hold. That sharing is not incidental duplication to be tidied
away: it is *why* the two grids agree on where a chord sits and what counts as a
hold. Splitting the HTML half alone would have forced that shared core to be
duplicated or imported across the boundary.
`TestTabstaffModuleBoundary::test_tabstaff_shares_the_layout_core` guards it.

| name | role |
|---|---|
| `tabstaff.format_tab_staff` | the ASCII staff, for a terminal |
| `tabstaff.format_tab_html` | a self-contained HTML page for a browser |
| `tabstaff.write_tab_html` | the only function in the module that touches the filesystem |
| `_staff_columns` / `_staff_breaks` | the shared layout core, both renderers call these |
| `_carries_melody` | which strings carry the melody, for the `*` marker |

`format_musicxml` and `write_musicxml` are the same rendering decision in a different
medium, and they live in `tabxml.py` rather than here — see
[MusicXML export](#musicxml-export). `format_gp5` and `write_gp5` are the same again
in a third medium and live in `tabgp.py` — see
[Guitar Pro 5 export](#guitar-pro-5-export). `tabstaff` re-exports all four, so
there is still one spelling for the whole staff-rendering surface.

**The dependency is one-way: `tabstaff` imports `arranger`, never the reverse.** It
takes `STRING_NAMES`, `ArrangementStep` and `_MUTED_CELL` from here; the last of
those stays put because `Voicing.tab_block()` and `format_progression` use it too.

### The re-export is lazy, and has to be

`from arranger import format_tab_html` still works — the README, the tests and
`wjazzd` all spell it that way — but `arranger` does **not** import `tabstaff` at
the top. A top-level (or even bottom-of-file) import would be a genuine cycle:
importing `tabstaff` first would re-enter a half-initialised `arranger` and fail to
find the names. So `arranger` exposes them through a **module-level `__getattr__`**
(PEP 562), which resolves each name on first access.

Two consequences worth knowing:

- **A `TYPE_CHECKING` import** in `arranger/__init__.py` gives the type checker and
  IDEs the real declarations, since a checker cannot follow `__getattr__`. Without it
  pyright reports the names as "not present in module". The same import was in
  `tabstaff.py` for the two `tabxml` names, and without it pyright flagged their
  `__all__` entries; Phase 6 removed that one along with the `__getattr__` it fed.
- **`__all__` is an explicit list**, not computed from `globals()`. It had to be
  added: the module never had one, so `from arranger import *` used to export every
  public name, and the lazy `__getattr__` hides the re-exported ones from a star
  import. `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface`
  fails if the list and the module's public names diverge, in either direction. It is
  spelled as one literal in both modules rather than with `+=`, which a checker
  cannot follow either.

## MusicXML import

`headxml` is the counterpart to `tabxml`: it reads a written head — a melody plus
chord symbols — out of a MusicXML file and arranges it. `arranger head FILE`
is its front end (also `make demo`'s sibling: `python -m arranger head FILE`).

**It needs no optional dependency.** `zipfile` and `xml.etree` are enough for both
forms of the format, so a plain `pip install jazz-arranger` can import a head and
`tests/test_headxml.py` needs no `skipUnless` guard at all. That asymmetry with
the exporter is deliberate and is the reason the two are separate modules rather
than two halves of one.

**Its four test scores are committed in `tests/data/`, and are not guarded.** A
hand-built fixture proves the parser agrees with itself; only a file written by
music21, MuseScore or this library's own exporter proves it reads what a notation
program actually writes. They are excepted from the `*.musicxml` / `*.mxl` rules
in `.gitignore` — which exist for *export output* — and a missing fixture is a
broken checkout, not a reason to pass quietly. `tenor_madness.musicxml` is 528 KB
and the largest of them; it earns its place by being the only two-part score,
which is what makes the TAB-staff part-selection test possible.

| name | role |
|---|---|
| `MUSICXML_KIND_QUALITIES` | `kind-value` → library quality; the inverse of `tabxml._READABLE_KINDS` |
| `_DEGREE_REFINEMENTS` | `(quality, degree, alter) → quality`, for the alterations a kind cannot name |
| `parse_musicxml_chord(harmony)` | → `(root, quality, bass)`; `None` for a chord that cannot be voiced |
| `Head` / `HeadNote` | the loaded melody, its timing, and each note's chord |
| `load_musicxml(path, part=None)` | `.mxl` or `.musicxml` → `Head` |
| `head_skeleton(head, strategy, section, pick)` | slots of `(triple, bar, beat, duration)` |
| `arrange_xml_head(path, …)` | the whole pipeline → steps, the `Head`, and diagnostics |
| `head_cli(argv)` | the `head` command |

Six decisions are load-bearing, and each was forced by a real file:

- **The harmony is a timeline, not a per-note attribute.** A `<harmony>` precedes
  the note it governs, several can share a bar, and a bar can carry none at all —
  But Not For Me bars 3 and 5 carry no harmony, and Rainy Day bar 1 changes twice
  inside the bar. So a chord is **held** from the note it is declared before until
  the next replaces it, the same forward fill `wjazzd` applies to the `beats`
  table. Reading the chord off the following note would drop the harmony from
  every bar that does not change.
- **A `.mxl` is read through `META-INF/container.xml`,** which names the root
  file. "The first `.xml` in the archive" looks equivalent and is not: a container
  may carry a `score.xml` beside a stylesheet or a thumbnail, and picking the
  wrong one is a *silent* failure. The largest XML member is the fallback when the
  container is missing; a non-zip is read as a bare document.
- **The metre is the notated one.** `beat` is the beat within the bar in notated
  beats, so `1 + onset/divisions * beats_per_bar / 4`. Dividing by four is what
  makes a 2/2 bar two beats wide — a quarter note in cut time is on beat 1.5, not
  beat 3 — and three of the four scores in the repository are in cut time. The
  `<time>` read is the **last** one stated, since a score may change metre.

### A beat is not a quarter note

Cut time is where every metre assumption in this library comes apart, and it did so
three separate times in one review of `but_not_for_me.mxl` — a music21-written
**2/2** head whose `<time symbol="cut">` is the only signature in the file. The
tune *sounds* like common time and is written with a quarter-note pulse, which is
exactly why it is easy to assume 4/4 and wrong to: the file says 2/2, and the
loader is right to read it that way. The bar is four quarters long either way; only
the *counting* differs.

**A beat is `4 / beat_type` quarters long, and a bar is `beats_per_bar` of them.**
The divisor is the load-bearing part: a 2/2 beat is a **half** note, so two
quarters, not `2/4` of one. Every renderer needs both numbers, and reading the
beat count as a quarter count is what each of the four bugs below was:

| where | was | cost |
|---|---|---|
| `headxml._slot_key` | clamped a slot to `beats_per_bar` | **13 of 80 notes lost.** A 2/2 bar's eighths run 1.0 … **2.5**; clamping to 2.0 folded the last eighth of every bar onto beat 2, where it collided and was dropped by `pick` |
| `head_cli` → the file writers | passed no metre at all | both writers used their own `beats_per_bar=4`, so a 2/2 head was written as 4/4 on the wrong grid |
| `tabxml._events`, `tabgp._measures` | `4.0 / beats_per_bar`, `bar_length = beats_per_bar` | a cut-time beat measured as half a quarter, so every bar came out half length — 32 measures written as 64 |
| the same two, *after* the fix above | `beat_type / 4` instead of `4 / beat_type` | **every bar a quarter note long.** The measure *count* stayed right, because onsets are placed in beats and that part was correct — so 32 short bars under a 2/2 signature, each holding a quarter of the music it claimed |

That last one is the instructive one, and it is worth stating as a rule of thumb:
**4/4 cannot catch it.** Both readings of the fraction give 1 quarter to the beat
in 4/4, so the whole suite passed with the file unusable for every other metre.
A test that asserts the measure *count* cannot catch it either, for the same
reason - the count was right. The check that catches it is summing each
measure's durations back to a bar length, which is what
`GuitarProTestCase.bar_quarters` and
`test_every_measure_of_a_written_head_fills_its_bar` do.

So `beat_type` is now a parameter of `format_musicxml` and `format_gp5` (and of
`_events`, `_measures`, `_build_part`, `_build_song`), it is what makes a 2/2 head
read as **2/2 rather than 2/4** in the file, and `head_cli` passes
`head.beats_per_bar` and `head.beat_type` to every renderer. `tabstaff` needs
neither: it works in *beats* throughout and never converts to a length.

### A rest is not a note, but it is time

The same review turned up a bug that has nothing to do with the metre, and it is
worth stating separately because it is the one a musician hears first.

Bar 1 of `but_not_for_me.mxl` is **a quarter rest followed by three quarter
notes**. `_read_notes` skipped the rest — correctly, it is not melody — but
skipped it with a bare `continue`, so **the cursor never moved past it**. Every
note in the file after that rest was read a beat early: the F4 landed on beat 1.0
instead of 1.5, the head appeared to begin on a downbeat, and the GP5 bar was
written as three chords filling a bar the score says is a rest and three.

The general rule is that *every* element the loader steps over has to be asked
whether it occupies time, and a rest does:

| element | advances the cursor? |
|---|---|
| a rest | **yes** — it is a `<duration>` like any other |
| a cue note | **yes** — it sounds in another part, and time passes |
| a grace note | **no** — it borrows the length of the note it decorates, so adding it would count that note twice |
| a lower voice of a `<chord>` group | no — the group's unmarked member carries the length |

This is a different failure from the metre one and a nastier one to spot, because
every bar is still exactly full afterwards: the music is simply a beat out, and
the error survives any test that only checks bar lengths. The test that catches it
is reading the *first note's own beat* off the committed file, which is
`test_a_cut_time_head_opens_on_the_beat_its_first_note_is_written_on`.

Fixing it exposed a second one, in the renderer rather than the loader. GP5 has
no anacrusis, and `tabgp._measures` represented a pickup by opening an **empty**
first measure and dropping it again at the end - which is not a representation of a
pickup, it is its deletion, and the music after it slid forward by the length of
the rest to fill the gap. It is now a **rest beat** at the head of the first
measure, with the cursor offset to follow it, so the bar is full *and* the music
sits where the score puts it. A knock-on effect worth knowing: a note that used to
be split across a bar line is often no longer split, because the rest is time
rather than a hole. `test_a_step_crossing_a_bar_line_is_split_not_stretched` pins
the new placement, and `test_a_long_step_is_split_across_a_bar_line_rather_than_stretched`
covers the split itself without a pickup in the way.

`_slot_key`'s clamp is now `beats_per_bar + 1 - grid` — the last grid position
**inside** the bar — rather than `beats_per_bar`. It still catches what it was
written to catch (a note that rounds onto the bar line is pulled back), which is
what `test_a_bar_line_overflow_is_still_pulled_back_inside` pins, because a fix
that kept those notes must not lose the protection.

The general lesson, and the one to apply to the next importer: **a count without a
denominator is not a metre.** 2/2 and 2/4 are both two beats to the bar, so
`beats_per_bar` alone cannot say which - which is why `Head` carries `beat_type`
and why it is now plumbed all the way to the file headers.

- **A `<chord>` group reduces to its highest note.** MusicXML does not order a
  group by pitch: only the first member is unmarked, and in a chord-melody part
  that member is the *lowest* note of the shape. Taking the maximum is what makes
  the reduction independent of how the writer ordered the notes, and it is what
  lets this library read back its own two-part export with the TAB staff skipped.
- **`<degree>` is how a chord its `kind` cannot name is spelled** — a `dominant`
  with a flat 5th is a 7b5, which is exactly how MuseScore writes one, and "Here's
  That Rainy Day" is a third of an E7b5 under an F melody line. The degrees are
  applied **in document order, each refining the last**, so the table keys off the
  *result* of the previous degree as well as the base kind. The `text` attribute
  is the final fallback and the inverse of `tabxml._downgrade_kinds`: that pass
  writes an unclassifiable chord as `<kind text="Bb7sus4">other</kind>`, so
  without reading `text` back a round trip of this library's own export would lose
  every chord it could not spell.
- **A tuplet's `<duration>` is unreduced** and must be divided by
  `time-modification`, or every bar after the first drifts a third long.
  "I Was Doing All Right" is written in triplets at 10080 divisions and is the
  test for it.

**Never guess a chord.** A kind the library cannot voice is absent from
`MUSICXML_KIND_QUALITIES` rather than folded into a near neighbour —
`Neapolitan`, `Italian`, `French`, `German`, `pedal`, `power`, `Tristan` and
`none` are all real MusicXML kinds and all absent — and it is counted in
`Head.unmapped` and printed, on the same principle as
`WEIMAR_QUALITY_ALIASES`. A quality naming a chord the voicing tables do not hold
is reported as untranslatable rather than failing silently later.

**The voicings are not re-implemented here.** `arrange_xml_head` hands its slots
to `wjazzd.arrange_slots`, the step loop promoted out of `wjazzd.arrange_head` for
exactly this. An imported head therefore gets the same non-chord-tone strategies,
the same opt-in dim7 retry, the same `repeated` hold and the same slash-bass rule
as one read from the database. A second implementation of the step loop is how
the corpus path came to disagree with the library once already; the whole point of
the extraction is that it cannot happen again.

**Imports are lazy where they keep the module cheap** — `argparse` inside
`head_cli`, and the renderers inside it too, so `load_musicxml` costs nothing.
`main()` imports `headxml` inside the `head` branch, as it does `wjazzd`.



## MusicXML export

`format_musicxml` / `write_musicxml` in `tabxml.py` render an arrangement as a
`score-partwise` document for a notation program. It is a **third renderer family**,
not a third column: it is the only one that needs a dependency, and the only one that
has to be post-processed before it is correct.

| name | role |
|---|---|
| `tabxml.format_musicxml` | the document, as a string. Pure, like every other renderer |
| `tabxml.write_musicxml` | the only function in the module that touches the filesystem |
| `_events` / `_is_hold` | placement, durations and the pickup; the rhythmic core |
| `_build_part` | the staff: measures, notes, ties, chord symbols |
| `_chord_symbol` | a symbol, or a text-only one for a name music21 rejects |
| `_drop_empty_inversions` | removes the meaningless `<inversion>-1</inversion>` |
| `_downgrade_kinds` | rewrites a `<kind>` value MusicXML 3.1 does not have |

**There is no TAB staff, deliberately.** This was a measured decision, not a
simplification. music21 cannot write a TAB staff a notation program renders
correctly: it emits neither the `<staff-lines>6</staff-lines>` a tab staff needs nor a
fret and string for each note *inside* a chord - it puts them all on the chord's first
note (cuthbertLab/music21#1534). Both were patched back in afterwards, and the patched
document **still did not display correctly in MuseScore 3**. A workaround that does not
work costs more than not shipping it, so `tabxml` writes a **notation staff only** and
`tabgp` writes the fretting, as a Guitar Pro 5 file. The two are divided by what each
format can do: GP5 stores a fret and a string per note natively, MusicXML reaches
Sibelius, MuseScore and Final. Everything that is genuinely *shared* - `_events`,
`_is_hold`, `_substitute_steps` - is still shared, so a head lands on the same beats in
both files.

Four decisions in here were each forced by a failure, not chosen:

- **The document is post-processed with `ElementTree` after music21 writes it** - for
  `_drop_empty_inversions` and `_downgrade_kinds`, and `_unique_instrument_ids`. The
  two passes that used to repair a tab staff are gone with it.
- **Steps are placed by `tabxml`, not by `tabstaff._staff_columns`.** The column grid
  is deliberately lossy - two steps on one onset collapse into one column, "the first
  step in a column owns that column" - which is right for a fixed-width ASCII staff
  and wrong for a score. The eighth-note skeleton puts two steps on the last beat of
  most bars, so sharing the grid would drop a chord from every bar of a head. What is
  shared is the *semantics*: absolute onsets with signed bars, and collapse on
  unchanged sounding pitches.
- **Steps sharing an onset divide their span equally**, and the transcribed
  `duration` is not used as a weight. It is the length of the *melody note* the step
  came from, which runs past the onset, and the corpus's values are arbitrary
  fractions of a whole note; scaling by them yields note values music21 refuses to
  write, and it refuses the **whole export** rather than rounding one. Two eighths on
  the last beat of a bar are two eighths.
- **Only the first measure carries the time signature.** MusicXML says a signature
  holds until it changes, so repeating it in every bar is legal but reads as a new one
  at each: MuseScore 3 draws a 4/4 over every bar of the head. This replaced a
  deliberate per-measure repetition, whose stated reason was that music21 needs a
  signature in each measure to pad and tie the bar. **That reason was measured and is
  false** - music21 resolves each measure against the signature already in force, and
  the export does not touch `makeRests` without one. Eight corpus heads, plus pickups,
  bar-line crossings and rests, all re-parse with every bar the right length.
  `tests/test_musicxml.py::test_the_time_signature_is_written_once` is the regression.

Two more are worth stating because they look like bugs otherwise:

- `Measure.padAsAnacrusis` is a **method**, not a flag. Assigning to it silently does
  nothing, and a pickup written as a full bar is a bar of wrong music.
- An event that runs across a bar line is **tied**, not stretched. A note cannot cross
  a bar line in MusicXML, and a measure holding more than its time signature is not a
  measure, so the renderer cuts it and ties the halves. The written rhythm survives
  even where the transcription's phrasing disagrees with the metre.

**Dependencies and the optional extra.** `music21` is the single exception to the
musthe-only rule, and it is opt-in: `pip install 'jazz-arranger[xml]'`. `_music21()`
imports it inside the functions and rewrites the `ImportError` into a message naming
that install command, so `import arranger`, the ASCII staff and the HTML page all work
without it, and `corpus_cli` reports the missing extra as a usage message rather than a
traceback.

**A chord name music21 cannot classify is written, not dropped.** `mMaj7`, `maj9` and
`7alt` are among the ones it rejects, and the Weimar notation produces more
(`Bb7sus4`). `_chord_symbol` falls back to `<kind text="...">other</kind>` with the
root still parsed out by `ChordParser`, which is how MusicXML spells a symbol whose
type the writer does not recognise.

**The output is valid MusicXML 3.1, not just 4.0.**

`kind-value` is a **closed enumeration**, and music21 writes MusicXML 4.0, which
extended it. `suspended-fourth-seventh` is the value that actually bites: MuseScore 3
refuses to open the file at all, with

```
Content of element kind does not match its type definition:
String content is not listed in the enumeration facet.
```

One chord costs the whole document, because the reader rejects the file rather than
the symbol.

`converter.parse()` **cannot see this** - music21 both writes the 4.0 value and reads
it back - and neither could any test asserting on the music21 objects. It is the second
consecutive defect of that shape, the first being the duplicate part-list instrument
id, so `tests/test_musicxml.py::TestMusicXML31Kinds` asserts on the **document**: every
`<kind>` value in it is in `_READABLE_KINDS`. A 3.1-legal file is also 4.0-legal, so
this costs nothing against the DOCTYPE and maximises what imports.

`_downgrade_kinds` runs last, as a compatibility filter over the finished document,
and rewrites in two steps:

- **the spec's own spelling** - `suspended-fourth-seventh` becomes `suspended-fourth`
  plus a `<degree>` adding the 7th. 3.1 has no kind for the combination, but it does
  have the `add`-degree idiom for a harmony expressed as a base kind plus alterations,
  so the chord still arrives as a classified symbol. `_SUS_KINDS` holds the mapping;
- **`other` with the analyst's text**, the same fallback `_chord_symbol` uses. This is
  the backstop for any value not in the table, and it is why the pass generalises to
  kinds nobody has hit yet.

The `<root>` is never touched, and on a document that only uses 3.1 kinds the pass is
a no-op - `test_an_ordinary_progression_is_untouched` asserts the document is
byte-identical afterwards, because a filter that degrades a working file is worse than
the bug.

**Open, and worth doing next: validate against the actual XSD.** `xmlschema` as a
**dev-only** tool (like pyright, never a runtime dependency and not in the `xml` extra)
would catch this whole class - MusicXML-level errors invisible to a round trip. It
means vendoring the 3.1 XSD into `tests/` and skipping when absent, in the same
`skipUnless` spirit as the `wjazzd.db` tests.

**Known limitations.** Durations are floored at a sixteenth, because MusicXML cannot
write less and music21 aborts rather than rounding; nothing this library generates is
shorter than an eighth. A triplet onset that does not divide the bar evenly would hit
the same wall - untested. The provenance notes the HTML page carries (`notes=`) are
not written into the score.
- **`__all__` is an explicit list**, not computed from `globals()`. It had to be
  added: the module never had one, so `from arranger import *` used to export every
  public name, and the lazy `__getattr__` hides the re-exported ones from a star
  import. `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface`
  fails if the list and the module's public names diverge, in either direction.
## Guitar Pro 5 export

`format_gp5` / `write_gp5` in `tabgp.py` render an arrangement as a **Guitar Pro 5
file**. It is a **third renderer family**, beside the ASCII/HTML staff and the
MusicXML score, and it is **not a replacement for MusicXML** — see below.

| name | role |
|---|---|
| `tabgp.format_gp5` | the file, as bytes. Pure, like every other renderer |
| `tabgp.write_gp5` | the only function in the module that touches the filesystem |
| `tabgp._guitarpro` | the lazy import, mirroring `tabxml._music21` |
| `_measures` | events to measures of beats; where GP5 and MusicXML differ |
| `_build_song` | the guitarpro `Song` |
| `_duration_split` | a quarter-length to the `Duration` + `Tuplet` that sum to it |
| `_sounding_frets` | which strings a step plays; a repeated melody is one note |
| `GP_VERSION` / `GP_SIGNATURE` | `(5, 1, 0)` and the file header it writes |

**Why a third renderer rather than a replacement.** GP5 is a *tab* format, so it
stores a fret and a string per note natively and a shape survives the round trip
exactly — which is why the mapping here is a few lines with no post-processing at
all. That is not merely tidier than the MusicXML tab staff used to be: it is the
**only** one that works, since music21 cannot write a tab staff a notation program
renders correctly (see [MusicXML export](#musicxml-export)). So the division is now
by capability, not by preference: GP5 carries the fingering, MusicXML carries the
notation, and neither renderer tries to do the other's job. But GP5 opens in Guitar
Pro and nowhere else, has no notation staff, and is a closed format. MusicXML remains
the way into Sibelius, MuseScore and Final. Both are shipped, and both are one flag
on `corpus_cli` (`--musicxml`, `--gp5`).

**What is shared, deliberately.** `tabgp` calls `tabxml._events` and
`tabxml._substitute_steps` rather than reimplementing either, so a head lands on the
same beats in both files and a substituted chord is named the same way in both.
That is the *semantics*; the bar grid is separate, for the reason below.

### Where GP5 genuinely differs from MusicXML
`tabxml._build_part` writes a **short first measure** for a head with an anacrusis,
because MusicXML has an anacrusis. A GP5 measure is a fixed-length container and the
format cannot say "this bar is only two beats long", so `_measures` writes a **full
first measure with the leading beats empty** and the music begins on the following
downbeat. That moves every onset later rather than reshaping the metre — the lesser
of the two distortions, since the notes and their order are untouched.

Two more consequences of a fixed-length measure:

- **An event crossing a bar line is split**, written as two notes in consecutive
  measures. The second half is written with `NoteType.tie`, so the two are one held
  note rather than the shape struck twice. This was wrong until it was measured:
  the code believed a GP tie was "a slur the player has to interpret" and wrote both
  halves as plain notes, which re-struck the shape at the head of every bar a step
  crossed - **14 of the 32 bars** of "But Not For Me", whose score genuinely ties
  Eb4 across the bar line in bars 2-3. `NoteType.tie` is a real GP5 tie and
  round-trips through PyGuitarPro 0.11.
  `test_a_held_shape_is_tied_across_a_bar_line_not_re_struck` and
  `test_every_split_step_in_a_written_head_is_tied` are the regressions; the second
  measures it over the real head, because a hand-built fixture finds the mechanism
  while an export can still be full of instances.
- **A measure opens when the cursor *reaches* a bar line**, not only when a step
  *crosses* one. Testing only for a crossing was a real bug found by the eighth-note
  case: beats landing exactly on the boundary all piled into the first bar, so a
  two-bar head came out as one eight-beat bar.
- **A beat with no notes must say `BeatStatus.rest`.** `gp3.writeBeat` only emits
  the status byte when the status is not `normal` (`if beat.status !=
  gp.BeatStatus.normal: flags |= 0x40`), so a note-less beat marked `normal` goes
  out as an *ordinary* beat whose string-flags byte is empty — indistinguishable
  from a chord on no strings rather than a rest. MuseScore 3 reads that as a rest
  in the right place; **TuxGuitar does not**, and puts the pickup rest on the 4th
  quarter rather than the 1st. This is the one defect so far that two readers
  disagree about, which is what made it findable: the file is self-consistent, so
  the round trip through PyGuitarPro passes while a notation program misplaces the
  rest. `BeatStatus.rest` is the third member of the enum (`empty`/`normal`/`rest`)
  and was simply never used.
  `test_a_rest_beat_is_marked_as_a_rest_not_as_an_empty_chord` and
  `test_every_note_less_beat_in_a_written_head_is_a_rest` are the regressions. The
  first asserts on the **parsed-back status** rather than on the beat having no
  notes, which is what the earlier test did and which this defect passes.

### Two things the format cannot express, found by TuxGuitar

TuxGuitar rejected a written head with `voice 1 is too long` on three measures of
*Blue Train* and one each of two *All the Things You Are* transcriptions. Both causes
are in `_duration_split`, and **both are silent** — the file writes cleanly and is
only wrong on read, so nothing in the round-trip test caught them until a real
notation program was run against the output.

- **A duration is a power of two, and there is no dotted note.** The value is
  written as `value.bit_length() - 3` and read back as `1 << (n + 2)`, so a length
  that is not a power of two has to be *split*, not rounded. A dotted half (3
  quarters) rounded to the nearest legal value is a **whole note** — a quarter too
  long, and a bar summing to more than its 4/4 signature. It is now written as a
  half plus a quarter.
- **A triplet is a `Tuplet`, not a `Duration` of 12.** `12.bit_length() - 3` is 1,
  so a bare `Duration(12)` is written as an **eighth** and reads back as one. Every
  triplet in a head silently became an eighth, and the bar went a quarter long. A
  triplet eighth is `Duration(8)` with `Tuplet(3, 2)`.

The rule is the one `test_no_written_bar_is_longer_than_its_time_signature` states:
**the parts must sum to the length asked for.** A split may leave a bar slightly
short, which a reader tolerates; it must never be long, which a reader rejects.
`_duration_split` therefore only ever takes parts that *fit*, and reaches for a
triplet only once no plain note does — so a dotted half stays a half and a quarter
rather than becoming three triplet eighths.

**A sliver the format cannot express is dropped, not padded.** The code once closed a
leftover remainder by appending the shortest legal note, reasoning that a short bar
"silently loses music". That is backwards: the music is not lost, the bar is merely
a hair long, and a bar that overruns its signature is **rejected**. It was reached
by the gap-as-rest work in the next section — a `1/6`-quarter rest, which is a
triplet-eighth divided by the onset, leaves a remainder no single note covers, and
the appended sixteenth made bar 2 of the Weimar head 4.92 quarters of 4.
`test_a_length_the_format_cannot_exact_is_written_short_never_long` is the direct
regression, asserting the ceiling over the exact and the inexpressible alike.

### A gap between two notes is a rest, not a held chord

The harmony is a timeline, not a per-note attribute. **The rhythm is
one too, and a rest is time.** Bar 4 of "But Not For Me" is a single whole note and
bar 5 opens with a quarter rest, so the gap from the note to the next onset is five
quarters while the note is written for four. The span a step is given is the gap to
the *next sound*, which is not the same as how long it *sounds* — so the note was
held over the silence into the next bar, and since a step crossing a bar line is
tied, the bar opened with a tied chord where the score says a rest. The eighth-note
skeleton puts a rest at the head of every second bar, so this was not one bar but
half the head.

`tabxml._events` therefore **caps** the span at the melody note's own `duration` and
writes the remainder as an explicit rest — a `(None, False, length)` event, which is
already what all three renderers read as "nothing here" (`tabxml` writes a
`<rest>`, `tabstaff` blanks the cell and clears the ring, `tabgp` writes
`BeatStatus.rest`). Three properties of the fix are load-bearing, and each was a
real failure:

- **It is a cap, never a substitute.** A `duration` longer than the gap is ignored,
  so no step is ever *stretched*, and a step with no `duration` at all keeps the
  whole-gap behaviour — which is what the renderers' uniform-grid fallback relies
  on. This is why the gap rule exists in the first place: `duration` is a fraction
  of a whole note that music21 cannot always write.
- **The last group is exempt.** It runs to the end of its own bar by definition, so
  there is no gap to represent and a cap would only invent a rest at the end.
- **The rest is measured after the sixteenth floor**, from what the group *wrote*
  rather than from the cap. The floor can make a group longer than the cap, and
  taking the rest from the cap would then add the two and overrun the bar.

`test_a_gap_between_notes_is_a_rest_not_a_held_chord` and its two companions — one
for the no-gap direction, one for a step with no timing — are the regressions.

### Six undocumented traps, each found by a failed round trip

None is in PyGuitarPro's documentation, all of them look innocent, and **every one
is a silent corruption rather than an exception** — the file writes without
complaint and is unreadable. They are recorded in `tabgp`'s module docstring, and
repeated here because the test that catches them is the one thing not to weaken:

- **`Song()` already contains one `MeasureHeader` and one `Track`.** Appending
  another yields a file that reads back as an extra track. Use `tracks[0]` and
  `measureHeaders[0]`.
- **`Measure.maxVoices` is 2 and the writer emits every voice.** A one-voice measure
  desyncs the byte stream; the reader fails much later with an unrelated-looking
  `count must be less than or equal than 255`.
- **`Beat.status` defaults to `BeatStatus.empty`,** which occupies *zero* duration.
  A beat that is meant to sound must say `BeatStatus.normal`.
- **Strings are numbered 1–6 with 1 = high E.** This library indexes 0 = low E, so
  the conversion is `6 - index` — the same flip `tabxml` makes.
- **`Chord` is a chord *diagram*, not a shape.** It holds a name, a root and a fret
  vector for the little box above the staff. A played shape is several `Note`s on one
  `Beat`, `Note.value` being the fret. Using `Chord` for the shape is the obvious
  mistake and writes a box rather than a chord.

### Why the test suite round-trips

`tests/test_guitarpro.py` writes the file, parses it back with `guitarpro.parse`, and
compares the notes against `step.voicing.frets`. That is the whole point: a GP file's
only contract is that Guitar Pro can open it, and every trap above produces a file
that passes any assertion on the builder's own output while being unusable. A parse
is the closest proxy available without Guitar Pro itself. `test_every_shape_survives_the_round_trip`
is the one that matters.

**Known limitation.** `PyGuitarPro` 0.11 writes GP3/GP4/GP5/TGP; GP5 is the newest it
supports. Guitar Pro 7+ `.gp` is a different, zip-based format that nothing here can
write, so a file from this renderer targets Guitar Pro 5 and 6 as well as anything
later that still reads GP5.




## Known limitations

- **MusicXML import (`headxml.py`):**
  - A score that changes metre is laid out in its **prevailing** metre — the last
    `<time>` stated — rather than per bar. A head that moves from 4/4 to 3/4
    mid-way will have the wrong bar lines in its first half.
  - A `<chord>` group is reduced to its highest note, so a **piano** part read as
    a melody is the top line of the right hand with the left hand discarded. That
    is the right reading for a chord-melody part and the wrong one for a
    two-hand piano reduction; there is no staccato/hand inference.
  - A melody below the library's `G3` floor is still unvoiceable, so a very low
    lead sheet needs `--bars` or a transposition, as the corpus path does.
  - No 11th chord is voiced: a dominant 11th is read as the 9th shape and a major
    11th as `maj7#11`, which is the shape it would be played as rather than a
    refusal. A `<degree>` the table does not know is ignored rather than guessed
    at, so an unfamiliar alteration leaves the base kind standing.
  - Repeat barlines and `<ending>` markers are read as text, not expanded: a head
    written with a repeat is played once, not twice.

- **MusicXML export** floors durations at a sixteenth, because MusicXML cannot
  write less and music21 aborts rather than rounding; nothing this library
  generates is shorter than an eighth. A triplet onset that does not divide the bar
  evenly would hit the same wall - untested.
- **Guitar Pro 5** is the newest format PyGuitarPro writes. Guitar Pro 7+ `.gp` is
  a different, zip-based format that nothing here can write, so a file from this
  renderer targets Guitar Pro 5 and 6 as well as anything later that still reads
  GP5.
