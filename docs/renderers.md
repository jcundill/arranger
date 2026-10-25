# Renderers: tab, MusicXML, Guitar Pro

`tabstaff`, `tabxml`, `tabgp` and `headxml`: the modules that turn an arrangement
into something a musician reads, and the one that reads a written head back in.
They are top-level modules rather than part of the `arranger` package because
`tabxml` and `tabgp` need optional dependencies the engine must not have.

Read this before touching any of them. Nearly every decision below is forced by a
real file, so the reasoning is the point: a "simplification" that drops one of them
reintroduces a bug the measurement below records.
## The staff renderers live in `tabstaff.py`

`format_tab_staff`, `format_tab_html` and `write_tab_html` are the renderers that
lay an arrangement along **one staff in reading order**, and they live outside the
`arranger` package so the engine can be read without them. `format_progression`
(one block *per chord*) stays in `arranger/render.py`, and the vertical
`tab_block()` in `arranger/tuning.py`: they are a different shape of output, and
`Voicing.tab_block()` is called from the dataclass itself.

`format_progression` prints the four columns on the step's own line and lays the
**explanation** out over as many lines as it needs, each indented to the column the
explanation starts in (`render._PROGRESSION_WIDTH`, and `width=None` for one line per
step). A staff with the chords on their real beats is what a player reads, and this
module renders one; a six-line block per chord is `format_tab_staff`'s, and the vertical
form of a single voicing is `Voicing.tab_block()`.

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
| `_staff_bars` / `_staff_barlines` | the bar number of every column, and the columns that open a bar |
| `_staff_rhythm` / `_note_value` / `_meter_label` | the timing core: note values, rests and ties, the metre |
| `_carries_melody` | which strings carry the melody, for the `*` marker |

**A barline and a system break are two different questions, and the split is load-bearing.**
`_staff_barlines` marks **every** bar — that is the mark saying where the metre falls —
while `_staff_breaks` marks every `measures_per_line` bars, which is only where a printed
line *ends*. One setting for both would rule one bar in four
and never wrap at all, with `measures_per_line` deciding where the barlines went.
TuxGuitar's ASCII export closes every measure and wraps at a fixed width, which is the
shape the split has to follow. Both sets come
from one `_staff_bars` list, so a barline and a wrap can never disagree about where a bar
ends.

The consequence for the tests is that **"every row is the same width" is an invariant of a
system, not of the whole staff** — the last system is short by definition, and a staff that
never wrapped could be compared as a whole. `_systems` in `tests/test_tab_rendering.py`
splits on the blank line so the assertion can be stated per system, which is what the
alignment check was for in the first place.

`format_musicxml` and `write_musicxml` are the same rendering decision in a different
medium, and they live in `tabxml.py` rather than here — see
[MusicXML export](#musicxml-export). `format_gp5` and `write_gp5` are the same again
in a third medium and live in `tabgp.py` — see
[Guitar Pro 5 export](#guitar-pro-5-export). `tabstaff` re-exports all four, so
there is still one spelling for the whole staff-rendering surface.

**The dependency is one-way: `tabstaff` imports `arranger.tuning`, never the
reverse.** It takes `STRING_NAMES`, `ArrangementStep` and `MUTED_CELL` from there -
the leaf the whole package is built on, which imports nothing - and the last of those
stays put because `Voicing.tab_block()` and `format_progression` use it too.

### The re-export is lazy, and why

`from arranger import format_tab_html` still works — the README and the tests
spell it that way — but `arranger` does **not** import `tabstaff` at the top. So
`arranger` exposes the seven names through a **module-level `__getattr__`**
(PEP 562), which resolves each on first access.

The reason is cost, plus one hard failure. Measured on the tree:

- a module-scope `from tabstaff import format_tab_staff` in `arranger/__init__.py`
  **imports cleanly** — Python resolves `arranger.tuning` through the partially
  initialised package — but it also loads `tabstaff`, `tabxml`, `tabgp` and
  `tabscore` on every `import arranger`. With the lazy seam, `import arranger`
  loads **none** of the six front ends;
- a module-scope `import headxml` **fails**, with
  `ImportError: cannot import name 'CHORD_FILLS_COMP'`: `headxml` names the facade's
  own public surface, so it meets a facade that has not defined those names yet.

So "the dependency is one-way" is the rule for the four rendering modules, and "no
package module imports a front end at module scope" is the rule for the two that
name the facade (`headxml`, `grip_chart`). `demo.main()`'s and `cli`'s imports are
function-local for both reasons at once, and the two directions still do not
deadlock: the front ends need only `tuning`, so neither side waits for the other.
[docs/dependency-dag.md](dependency-dag.md) has the full table, and
`tests/meta_front_end_dag.py::TestTheRuntimeCycle` holds it.

Two consequences worth knowing:

- **A `TYPE_CHECKING` import** in `arranger/__init__.py` gives the type checker and
  IDEs the real declarations, since a checker cannot follow `__getattr__`. Without it
  pyright reports the names as "not present in module". `tabstaff.py` needs no such
  import: it re-exports the two `tabxml` names directly.
- **`__all__` is an explicit list**, not computed from `globals()`. The lazy
  `__getattr__` hides the re-exported names from a star import, so a computed list
  would export less than the module has.
  `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface`
  fails if the list and the module's public names diverge, in either direction. It is
  spelled as one literal in both modules rather than with `+=`, which a checker
  cannot follow either.

## What the four renderers must agree about

An arrangement is data; four renderers read it. **They must agree about which notes are new
attacks**, because a note drawn twice is a wrong rhythm and a note drawn nowhere is a note
the arrangement does not really contain. These facts drive that agreement, and each has one
owner.

| fact | the field | what a renderer does with it |
|---|---|---|
| the shape is the same as the previous one | compared in `_staff_columns` / `_is_hold` | a hold column draws nothing: the previous shape is still ringing |
| the chord is **struck again** though the shape is unchanged | `ArrangementStep.chord_attack` | the column is a strike and the shape is drawn again |
| the thumb has **moved** under a held shape | `_moved_thumb` compares `(bass_midi, bass_string)` | the hold column draws **the bass string only** |
| the thumb is **sounding and not plucked** | `ArrangementStep.bass_held` | the tab mutes that string, the staff leaves it blank, the score ties it, GP5 writes a tie note |
| the step exists for the thumb: **nothing above it is struck** | `ArrangementStep.bass_only` | the tab and the staff draw the bass string only; the score re-states the ringing pitches **as ties**; GP5 writes the thumb as a new note and those pitches as ties |
| the tune's note was **released** by a chord attack | `ArrangementStep.melody_released` | the melody row is blank (`tabstaff._melody_label`), the compact line prints no note and no degree, and the writers need nothing: the note is not in the shape, so it is neither written nor tied |

**The last row is the melody row's one exception.** That row labels *every* step - the tune
moves on while the shape under it is held, so a held column is exactly where the name is
wanted - and the cell it must not label is a note a stab ended. The note is not sounding, so
its name would claim the tune is still in; the line is told which note it was by
`annotation._comping_tail` (`the stab ends the tied Eb4`) rather than by the column. The
writers agree for free, because a released note is absent from the shape: MusicXML has
nothing to tie, and GP5 nothing to restate.

**The first row cannot decide on its own, and the second is why.** A comp on
`--chord-on every-beat` states the *same shape* on every beat, and so does a slot the
tune merely sustains through - the pitches are identical whether the player strikes the
chord again or lets it ring. On the comping route that ambiguity is load-bearing, because
`melody_voiced=False` removes the soprano a `repeated` step would re-articulate, so the
engine deliberately holds the whole shape there (`render._step_cells`). The chord's own
rhythm is the fact that separates the two, and `slot_plan._chord_attacks` is its one home:
a position the request **named** - a `--chord-on` position, the tune's own onsets on a
comping selection, a stab under a held note - or a slot the chord layer invented where the
tune is silent is a new attack; a slot the eighth-note skeleton invented under a sustaining
note is a hold, and stays one.

**The last row is the one the score cannot express otherwise.** GP5 has no way to write a
string that sounds without being plucked, so a held shape is written as `NoteType.tie`
notes; MusicXML does, and it is still a **tie** rather than a fresh note - a note written
again is a note re-attacked. Both writers therefore re-state the *ringing* pitches and tie
them (`tabgp._sounding_frets` draws the thumb, `tabxml._sounding` takes the pitches the part
has already written), and `decisions.is_bass_only` is what says when: a position the
chord's rhythm did not name, over a harmony and a melody that are already sounding. Without
that, a tied melody under a walking line was re-plucked on every beat the walk invented, in
the tab and in both files.


**The hold comparison is of the upper voices**, and it has to be: a walking bass moves the
lowest pitch on every beat, so including it would mark every column a strike and turn the
arrangement back into the chord list the collapse exists to prevent. The cost of that choice
is a column whose shape is held and whose thumb moves — a hold for the shape and a new attack
for the bass — and drawing nothing at all would leave the note in the one-line tab and in
the score while the ASCII staff and the HTML showed silence. `_moved_thumb` is that fact and
`_draws` is the one predicate both renderers ask. The comparison is by `(midi, string)`
rather than by role, because a thumb can move to another octave of the same pitch class and
that is a note being plucked.

**A carried thumb is the mirror image.** `bass_merge.carry_bass` writes a struck note into
the steps that follow it, so a `--bass-on 1` line is one note ringing through the bar rather
than a stab per melody note. The fret is in the vector because the string really is
sounding, so each renderer has to say "not plucked" in its own way:

- `render._step_cells` draws a mute on that string — the one-line tab answers *what is
  plucked*;
- `tabstaff._strikes_here` returns False, so the cell is empty — the note is drawn where it
  is struck;
- `tabxml._build_note` writes a **per-note `<tie>`**: the earlier `Note` is patched to
  `start`/`continue` and this one is written with `stop`. It has to be at the note inside the
  chord, not on the chord, because the other voices are new. An event cut at a bar line
  carries no such tie — the cut writes one chord-level tie, and a note cannot carry two;
- `tabgp._strike_notes` writes the note as `NoteType.tie`, which is that format's only way
  to say "still sounding"; the tie is only trusted where the last note written on that
  string is the same fret, because a GP5 tie carries no fret of its own.

A **rest column** is drawn by all four as silence: a blank cell, an `x` under `--mutes`, an
explicit `<rest>` in the score. Two things about it are stated rather than left to a reader:

- **a rest is cut at a bar line and not tied.** A measure cannot overfill, so a rest longer
  than the room in its bar is split like any other event — but `<tie>` inside a `<rest>` is
  not legal MusicXML, and the claim it would make is false: a tie says *this pitch
  continues*, and a silence makes no such claim. `tabxml.write_event` sets the tie on a
  sounding event only, so the two pieces are the two silences they are.
- **a rest step is a rest beat in GP5.** The status is read off the beat's own notes rather
  than off `step is not None`: a rest *step* is still a step — the engine emits one for a
  position the guitar declines — and written `normal` it goes out as an ordinary beat with an
  empty string-flags byte, which MuseScore reads as a rest in the right place and TuxGuitar
  puts at the end of the bar instead of the head.

A **fill** is not a rest — it is a step with no melody — so
it draws the chord it states and its line says *the tune is silent here*, which is what stops
a chord with no melody above it from reading as a mistake.

## MusicXML import

`headxml` is the counterpart to `tabxml`: it reads a written head — a melody plus
chord symbols — out of a MusicXML file and arranges it. `arranger head FILE`
is its front end (also `make demo`'s sibling: `python -m arranger head FILE`).

**It needs no optional dependency.** `zipfile` and `xml.etree` are enough for both
forms of the format, so a plain `pip install jazz-arranger` can import a head and
`tests/test_headxml.py` needs no `skipUnless` guard at all. That asymmetry with
the exporter is deliberate and is the reason the two are separate modules rather
than two halves of one.

**The committed scores are in `tests/data/`, and are not guarded.** A hand-built
fixture proves the parser agrees with itself; the committed corpus proves it reads
the structures real exporters write — a container, a cross-barline tie, a TAB part,
slash basses, degrees and 10080-division triplets. They are excepted from the
`*.musicxml` / `*.mxl` rules in `.gitignore` — which exist for *export output* — and
a missing fixture is a broken checkout, not a reason to pass quietly. Every file
except `Trouble_in_Mind_Blues.musicxml` is generated by `tests/fixture_scores.py`;
`synthetic_tab_export.musicxml` is the only two-part score, which is what makes the
TAB-staff part-selection test possible.

| name | role |
|---|---|
| `MUSICXML_KIND_QUALITIES` | `kind-value` → library quality; the inverse of `tabxml._READABLE_KINDS` |
| `_DEGREE_REFINEMENTS` | `(quality, degree, alter) → quality`, for the alterations a kind cannot name |
| `parse_musicxml_chord(harmony)` | → `(root, quality, bass)`; `None` for a chord that cannot be voiced |
| `Head` / `HeadNote` | the loaded melody, its timing, its key, and each note's chord |
| `load_musicxml(path, part=None)` | `.mxl` or `.musicxml` → `Head` |
| `head_skeleton(head, strategy, section, pick)` | slots of `(triple, bar, beat, duration)` |
| `arrange_xml_head(path, …)` | the whole pipeline → steps, the `Head`, and the loader's notes |
| `head_cli(argv)` | the `head` command |

Six decisions are load-bearing, and each is forced by a real file:

- **The harmony is a timeline, not a per-note attribute.** A `<harmony>` precedes
  the note it governs, several can share a bar, and a bar can carry none at all —
  `synthetic_common_8` bar 8 carries harmony and no tune, and
  `synthetic_repeat_slash` bar 1 changes twice inside the bar. So a chord is
  **held** from the note it is declared before until
  the next replaces it — the ordinary forward fill, which is also what the removed
  corpus loader applied to its `beats` table. Reading the chord off the following
  note would drop the harmony from every bar that does not change.
- **A `.mxl` is read through `META-INF/container.xml`,** which names the root
  file. "The first `.xml` in the archive" looks equivalent and is not: a container
  may carry a `score.xml` beside a stylesheet or a thumbnail, and picking the
  wrong one is a *silent* failure. The largest XML member is the fallback when the
  container is missing; a non-zip is read as a bare document.
- **The metre is the notated one.** `beat` is the beat within the bar in notated
  beats, so `1 + onset/divisions * beat_type / 4`: an onset is counted in **quarters**
  (`<divisions>` is defined per quarter note) and a beat is `4 / beat_type` of them.
  The *count* is not the factor — `beats_per_bar / 4` equals `beat_type / 4` only where
  the numerator and the denominator are equal, which is 4/4 and 2/2, and in 3/4 it put
  every note of the waltz a quarter of a beat early. Dividing by four is what makes a
  2/2 bar two beats wide — a quarter note in cut time is on beat 1.5, not beat 3 — and
  the committed corpus spans 2/2, 3/4 and 4/4. `headxml._beat_from_onset` is that one expression, and
  both callers (a note's `<chord>` group and a `<harmony>`) go through it. The `<time>`
  read is the **last** one stated, since a score may change metre.

### Repeats, endings and jumps are played, not just read

**A score's `<repeat>`, `<ending>` and navigation instructions are honoured: the head plays
the bars a performer plays, not the bars the file writes.** `synthetic_repeat_slash` writes
8 bars — 1-4, a 1st ending at 5-6 with the backward repeat, a 2nd ending at 7-8 —
and a player hears `1-4, 5-6, 1-4, 7-8`: **12** bars, the 1st ending taken once and
skipped on the repeat. Three committed scores carry a repeat (`synthetic_repeat_slash`,
`synthetic_waltz` and `synthetic_triplets`, which has an explicit forward
repeat); the others load exactly as they always did.

`headxml._parse_barline` reads each `<barline>`; `_parse_direction` / `_parse_sound` read
MusicXML's navigation channel — `<sound dacapo>`, `dalsegno`, `segno`, `coda`, `tocoda`,
`fine`, `forward-repeat`, and a `<direction-type><segno/>` or `<coda/>` with no `<sound>`.
`expand_repeats` then calls `_expand_play_order`, which builds the play order (a backward
repeat jumps to the matching forward repeat, or to the start when the score marks none,
and a volta numbered N plays only on pass N) and renumbers `bar` to the **absolute**
play-order position, duplicating the notes and `<harmony>` of every section played again.
That renumbering is forced by the engine: every consumer — `chord_at`, `melody_at`, the
walking bass, the renderers' bar grouping — keys on `(bar, beat)`, and a repeat puts two
physical bars on the same written number. The score's own number stays on
`HeadNote.written_bar` / `HeadChange.written_bar`, and `Head.markers` records the
instructions on their absolute bars. **`--bars LO-HI` therefore selects on the expanded
(absolute) bars** — on a repeated head `--bars 31-32` is the 1st ending as played, not
written bar 31.

**A jump is a second traversal, not a new kind of bar.** A D.C. / D.S. returns to the
start or the Segno and the head plays on; a To Coda met after the jump diverts to the
Coda, and a Fine met after it stops the return. Four rules make that a form rather than
four decorations, and each is a decision:

- **a jump fires once.** Every later D.C. / D.S. is ignored — otherwise the instruction
  just obeyed would fire again as the return path reached it;
- **a Fine or To Coda is a destination only after the jump.** On the way out they are
  passed through; a player who stopped at the Fine on the way to the D.C. would never
  reach it. A Fine with **no** jump at all is the end of the piece, and ends it;
- **repeats are not re-taken after a jump.** A D.C. that re-entered a backward repeat at
  bar 1 would reach the same instruction and loop; a performer reading "D.C." plays the
  written section straight through, and so does this;
- **volta passes reset to 1 on the jump**, for the same reason: the return is a fresh read
  of the written page.

`expand_repeats` returns the **resolved** kind of each jump that fired — `da_capo_al_fine`,
`da_segno_al_coda` and the rest — so a writer spells a decision the expansion made rather
than re-deriving it from where the signs happen to sit. `Head.markers` carries it beside
the repeat and ending signs.

**What is read, and what is not.** The `<sound>` attribute is the format's semantic
channel and the one the importer reads; a `<words>D.C. al Fine</words>` with no `<sound>`
is prose and is ignored, because recognising it would mean parsing every exporter's
spelling of the same instruction. A file that states only words therefore loads linearly
rather than guessing. `times` / `time-only` on a jump, and a second *named* Segno, are not
modelled: MusicXML could carry them, but Guitar Pro 5 stores **one bar per sign name**, so
a second Segno is lost in that writer while the MusicXML one keeps it.

**The writers draw them back - on the written bars.** Each takes a `markers=` argument
(threaded from `head_cli` as `head.markers`), and each is handed the **written** score
rather than the played bars: `arranger.cli._as_written` folds the 12 played bars back onto
the 8 the file writes, using `Head.written_bars`, and moves the markers onto those bars.
A file that wrote the played bars out *and* carried repeat signs would make a reader take
the repeated section twice more, so the signs replace the written-out repeat rather than
sitting on top of it. `tabxml` writes `<barline>` `<repeat>` and `<ending>` elements, and
for navigation a `<direction>` carrying **both** the visual sign (`<segno/>`, `<coda/>` or
the words) and the `<sound>` attribute the importer reads. `tabgp` sets `isRepeatOpen` /
`repeatClose` / `repeatAlternative` on the measure headers, and puts a destination
(`Segno`, `Coda`, `Fine`) in `direction` and a jump in `fromDirection` — the split the
format's own reader makes. `tabstaff` draws `|:` / `:|` on the barline and a label row
above the staff: the volta numbers, `Segno`, `Coda`, `Fine`, `To Coda`, and the short
`D.C.` / `D.S.` (a full "D.C. al Fine" would set the width of every column in the system).
With no markers - every non-head caller and every non-repeating score - each writer is
byte-identical to what it produced before.

**GP5 navigation is only as portable as the importer.** The signs live in the song-level
19-entry direction table, which Guitar Pro and MuseScore 4 read. **TuxGuitar 2.0 does not
read the table at all** — its GP5 importer skips the 42 bytes after the MIDI channels,
which is exactly the 19 `short`s plus the master reverb — and its measure header has no
field for a jump (only repeats, the alternative-ending mask and a text marker), so no GP5
encoding could make it play one. **MuseScore 3 predates the feature**: GP jump import
landed in MuseScore 4 in 2022, and 3.2.3 converted a file carrying these signs into a
score containing none of them (only the tempo direction survived). The GP5 is correct
where the table is read; for either of those tools the **MusicXML** is the output that
carries the form — MuseScore 3 imports it as a real `<Jump>` plus `<Marker>`s, measured
on `examples/navigation/ds_al_coda.musicxml`.

A GP5 **measure marker** is the one thing both readers show. It is a text label, not a
jump: `examples/navigation/*_text.gp5` carry one marker per sign so the signs are visible
in TuxGuitar and MuseScore 3, but playback still runs straight through. The library does
not write those markers — they would duplicate the real symbol in Guitar Pro — so the
demo variant is generated by hand from the same file.

The plain `--tab line` listing is the exception: it prints the played arrangement, so a
repeated or jumped head still shows every bar a player plays there.

### A beat is not a quarter note

Cut time is where every metre assumption in this library comes apart, in three separate
places at once in `synthetic_cut_time.mxl` — the synthetic
**2/2** head whose `<time>` is the only signature in the file. The
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
| `tabscore.score_events`, `tabgp._measures` | `4.0 / beats_per_bar`, `bar_length = beats_per_bar` | a cut-time beat measured as half a quarter, so every bar came out half length — 32 measures written as 64 |
| the same two, with `beat_type / 4` instead of `4 / beat_type` | **every bar a quarter note long.** The measure *count* stayed right, because onsets are placed in beats and that part was correct — so 32 short bars under a 2/2 signature, each holding a quarter of the music it claimed |
| `headxml._beat_from_onset` (both callers) and `chord_slots` | `beats_per_bar / 4` per onset, `/ beats_per_bar` for a length | **a 3/4 bar of music in 2.25 of its 3 beats.** The waltz's six written eighths read 1.0 … 2.875, so the staff drew a hole of music before every barline, 21 of its 35 interior measures exported short of a full 3/4 bar, and `--musicxml` scaled every onset by a further 0.75 on each round trip |
| `arranger.bass._melody_timeline` | `duration * beats_per_bar` | a quarter short in 3/4 (`duration * beat_type` is the span). **Measured at 0 of 186 steps** on the waltz: the walk's chord timeline is onset-driven, so only a melody-in-force span reads a duration. Fixed with the rest rather than inherited by the next metre-sensitive rule |

That last one is the instructive one, and it is worth stating as a rule of thumb:
**4/4 cannot catch it.** Both readings of the fraction give 1 quarter to the beat
in 4/4, so the whole suite passed with the file unusable for every other metre.
A test that asserts the measure *count* cannot catch it either, for the same
reason - the count was right. The check that catches it is summing each
measure's durations back to a bar length, which is what
`GuitarProTestCase.bar_quarters` and
`test_every_measure_of_a_written_head_fills_its_bar` do - and the waltz is **in**
that test's fixture list for exactly this reason, because it is the one committed
head whose numerator and denominator differ.

**The rule of thumb has a corollary: a
`<time>` read is not a metre until the *denominator* reaches the arithmetic that
uses it.** `headxml` reads `beats_per_bar` and `beat_type`, and onsets convert with
both: converting with `beats_per_bar` alone is
right in 4/4 and 2/2, and 25% early in the 3/4 one. Every assertion in
`tests/test_headxml_arrangement.py::TestTheMetreHasADenominator` fails on that
denominator-free arithmetic: a test for a metre bug that cannot fail on it is not a
test, and all five of them fail on it.

So `beat_type` is a parameter of `format_musicxml` and `format_gp5` (and of
`tabscore.score_events`, `_measures`, `_build_part`, `_build_song`), it is what makes a 2/2 head
read as **2/2 rather than 2/4** in the file, and `head_cli` passes
`head.beats_per_bar` and `head.beat_type` to every renderer.

**`tabstaff` needs it too.** It works in
*beats* throughout and converts to a length only where a length is drawn: a chord is
placed on a beat with a fret under it, and a whole note and a quarter are one column of
frets on that grid. The **metre row** and the **note-value row** (`show_timing`) are what
need the length: a length is measured in quarters, and quarters come from
`4 / beat_type`. So `beat_type` is a parameter of `format_tab_staff` and
`format_tab_html` too, and `head_cli` passes it to all four renderers.

### Grouping is read from the score, but not written back

The importer reads `<beats>` and `<beat-type>`, and then the **grouping** — which
denominator units are felt as one beat — from the score's own channels: an `N+N` mark in
a direction, the primary beaming, or a metronome pulse (see
[engine.md](engine.md#grouping-the-metres-third-fact)). A score that states none of them
falls back to `auto` (threes for a compound metre, one per beat otherwise).

The **writers do not put the source's channel back verbatim**. `tabxml` writes no `N+N`
direction and only the navigation `<words>` it draws, but music21 *does* compose
`<beam>` elements from the exported rhythm, so a MusicXML round trip re-derives a grouping
from those beams. That grouping is music21's conventional beaming, not necessarily the
source's: a 12/8 score beamed 4+4+4 comes back beamed 3+3+3+3 and is read as four
dotted-quarter beats, and a 5/4 marked `3+2` comes back with no mark (its quarter-note
melody has no beams) and falls back to `auto`. GP5's time signature carries the count and
the denominator and nothing else. A caller's explicit non-standard grouping is therefore a
property of the run rather than of the file, and the exact grouping is lost when the
arrangement is written out and read back. The importer can read the fact; the writers do
not preserve the channel that stated it.

A generated comping bar does read it, though: `headxml._bar_resolution`
offers a **group-length** candidate ahead of the beat, so a 12/8 bar written in four
dotted quarters generates four positions rather than twelve. The beat remains the
fallback for a bar mixing subdivisions that no single finer resolution holds, so a busy
bar is still generated on its beats rather than on an arbitrary one of them.

### What the staff's timing rows are, and what they are not

`show_timing` (on by default) adds two rows above the chord names:

```
  |4/4                    |
  |w     r     r     r    |
  |Dm7                    |
  |D5                     |
e*|10---------------------|
B |10---------------------|
G |10---------------------|
D |10---------------------|
A |-----------------------|
E |-----------------------|
```

- the **metre** over the first bar, and nowhere else — a signature holds until it
  changes, which is the same reason `tabxml` writes `<time>` into the first measure
  only;
- a **note value** per column: `w h q e s`, dotted (`q.`), triplet (`3q`), `~` for a
  shape still held from an earlier column, and `r` for a rest.

Three things about the six string rows below them, all of them forced by comparing the
output with TuxGuitar's ASCII export of the same GP5 file:

- **Each string is a continuous line of dashes**, with the frets sitting *in* it. The
  cell that would otherwise be a space is a `-`, which costs nothing and is the whole
  difference between a staff that reads as tab and one that reads as a chord list.
- **The rows above are *not* filled.** The chord name, the melody note and the note
  value are text, and a dash through a chord name is a line through the word. So the
  `-` lives in `string_line` and not in the shared `line()` builder, and the two
  separators are both exactly one character — which is what keeps the columns of the
  two kinds of row aligned.
- **Every bar is ruled**, and `measures_per_line` now means bars per *line* of music,
  which is what the flag has always been called. A barline is the one mark saying
  where the metre falls, and `_staff_breaks` (where a line ends) is deliberately a
  different question from `_staff_barlines` (where a bar ends). Both come from one
  `_staff_bars` list, so the two renderers cannot disagree about it.

### Width is duration, and that is what the rhythm row was standing in for

**A column is as wide as the note is worth**, so a quarter and a
half note are not identical and the ASCII staff says how long anything
sounds. A note occupies as many *slots* as it is worth, one slot
being one fret cell.

Three things the grid has to get right, each measured
against `jon6.tab`:

- **The units are whole notes.** `ArrangementStep.duration` is in whole notes
  (`tuning.py`), so a slot count is not `duration` read as beats: a quarter note —
  `duration=0.25` — is **two** slots wide, not one, and reading it as a beat draws
  *every bar in the piece at the same width*, so no two notes are
  distinguishable by length at all. `_staff_rhythm` does this right
  (`duration * 4.0` → quarters).
- **`beat_type` is a conversion, not a scale factor.** The grid is per *whole note*, so a
  4/4 bar and a 2/2 bar are the same sixteen slots, and `beat_type` only converts beats to
  whole notes on the way in.
- **Holds and rests get their real span.** They were pinned to one slot, which is what
  made a pickup's leading rest too short to see and left a half-note hold as narrow as a
  sixteenth. The rule is the one `_staff_rhythm` already uses: a column runs to the next
  *sounding* column, capped at its own barline.

**The floor is eight slots to a whole note, and that is measured.** `jon6.tab` bar 1 — a
quarter rest and three quarter notes in 2/2 — is seventeen characters: one lead-in dash
plus sixteen of grid, which is eight slots of two characters, one to the quarter.
`_slots_per_whole` raises that floor only for music finer than an eighth, so the shortest
note never rounds away to nothing.

With that, our bar 1 and bar 11 come out **byte-identical** to TuxGuitar's — which is the
check that the lead-in, the cell width and the slot count are all landing where they
should, independently of each other. TuxGuitar never puts a fret hard against a `|`:
every one of `jon6.tab`'s 26 bars carries exactly one lead-in dash, which is why the row
written for a barline puts one separator there too.

### Sub-beat rests, and the column grid that dropped them

`_staff_columns` advanced the fill cursor a whole beat at a time and always set
`current = onset + 1.0`, assuming a step was a beat long. It is not: `duration` is in whole
notes and the default `eighths` skeleton puts steps half a beat apart, so **every gap
shorter than a beat was stepped over**. Bar 11 of the synthetic cut-time head lost its downbeat column
entirely that way, and with it the tie into the bar's early beat. `_rest_grain` is the
shortest thing the progression actually writes, bounded to a beat, so an untimed
progression keeps the one-column-per-beat grid.

The defect is **not** in the ASCII renderer alone: `_staff_columns` is
shared with `format_tab_html` and `_staff_rhythm`, so a missing rest reaches the page too.

Three further grid facts, measured the same way:

- **A leading rest inside the first bar is kept.** `_staff_columns` started at the first
  *onset*, which would silently drop a rest inside that bar: a pickup comes out with its
  first fret hard against the opening barline and reads as a downbeat. The synthetic cut-time
  head's bar 1 is written that way — a quarter rest and then three notes. The start is
  rounded down to the **bar** containing the first onset, which keeps the rest without
  inventing whole empty bars ahead of it. Rounding to the bar rather than to zero is
  the whole of that rule; rounding to zero would pad out a head selected from bar 12.
- **The last bar is padded out to its own length.** The grid fills the holes *between*
  onsets, so a head whose final note ends early would close its
  barline mid-bar: the rest after the last note is still time. Only the *last* bar is
  padded: every earlier one is closed by the next onset or the next bar's first column,
  and padding those would invent silence the score does not write.
- **An untimed progression is not subdivided.** No written rhythm means no durations to
  show, so every column stays one slot wide and the uniform fallback grid is unchanged.

The staff **wraps**, separated by a blank line, and each system is ruled to its own
width — a long chord name widens the bar it is in and no other, so one `Cmaj7` cannot
stretch a whole arrangement. So "every row is the same width" is an invariant of a
*system*, not of the whole output; the tests read it per system for that reason.

Two decisions in that row were measured rather than chosen:

- **A note runs to the next *sounding* column, not to the next column.** The `None`
  columns are rests `_staff_columns` invented to fill a gap, and stopping at the
  first of them printed a quarter note where `tabxml` writes a whole one. The length
  is then capped at the end of its own bar, because sounding past the barline is a
  tie and this grid has no tie to draw. Measured on melid 451, whose head has a
  four-beat hole in it: without the cap a six-quarter "note" went into one cell and
  widened the whole staff to fit it.
- **A length nothing names prints its quarter count** (`0.67q`), not the nearest legal
  note. A transcribed head does contain onsets that are not a clean power of two, and
  rounding one to a neighbouring value would print a note that is not being played.
  It also widens the grid, which is the `width` computation doing its job.

`_staff_rhythm` is computed from the **column grid**, not from `tabscore.score_events`,
because the two grids are deliberately different: `score_events` keeps every step sharing
an onset and divides the span between them, while `_staff_columns` gives the column
to the first and drops the rest. What is shared is the *rule* — a note lasts until
the next sound, capped by its written `duration`. Where two steps share one onset the
two renderers therefore disagree about the length, and that is the column grid's own
documented lossiness rather than a third convention;
`TestStaffRhythmAgreesWithTheScore` checks the cases where the grids line up.

### A rest is not a note, but it is time

This fault has nothing to do with the metre, and it is
worth stating separately because it is the one a musician hears first.

Bar 1 of `synthetic_cut_time.mxl` is **a quarter rest followed by three quarter
notes**. `_read_notes` skips the rest — correctly, it is not melody — and it must
advance the cursor past it. A bare `continue` leaves the cursor where it was, so every
note in the file after that rest is read a beat early: the F4 lands on beat 1.0
instead of 1.5, the head begins on a downbeat, and the GP5 bar is
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
every bar is still exactly full: the music is simply a beat out, and
the error survives any test that only checks bar lengths. The test that catches it
is reading the *first note's own beat* off the committed file, which is
`test_a_cut_time_head_opens_on_the_beat_its_first_note_is_written_on`.

A second one is in the renderer rather than the loader. GP5 has
no anacrusis, so `tabgp._measures` opens an **empty** first measure to hold the
pickup - which is not a representation of a pickup but its deletion, with the music
after it slid forward by the length of the rest to fill the gap. A pickup is a
**rest beat** at the head of the first
measure, with the cursor offset to follow it, so the bar is full *and* the music
sits where the score puts it. A knock-on effect worth knowing: the rest is time rather
than a hole, so a note crossing a bar line is split where the score splits it.
`test_a_step_crossing_a_bar_line_is_split_not_stretched` pins
the placement, and `test_a_long_step_is_split_across_a_bar_line_rather_than_stretched`
covers the split itself without a pickup in the way.

`_slot_key`'s clamp is `beats_per_bar + 1 - grid` — the last grid position
**inside** the bar — rather than `beats_per_bar`. It catches the note that rounds
onto the bar line and pulls it back, which is
what `test_a_bar_line_overflow_is_still_pulled_back_inside` pins.

The general lesson, and the one to apply to the next importer: **a count without a
denominator is not a metre.** 2/2 and 2/4 are both two beats to the bar, so
`beats_per_bar` alone cannot say which - which is why `Head` carries `beat_type`
and why it is plumbed all the way to the file headers.

- **A `<chord>` group reduces to its highest note.** MusicXML does not order a
  group by pitch: only the first member is unmarked, and in a chord-melody part
  that member is the *lowest* note of the shape. Taking the maximum is what makes
  the reduction independent of how the writer ordered the notes, and it is what
  lets this library read back its own two-part export with the TAB staff skipped.
- **`<degree>` is how a chord its `kind` cannot name is spelled** — a `dominant`
  with a flat 5th is a 7b5, which is exactly how MuseScore writes one, and "Here's
  That Synthetic Repeat Slash" is a third of an E7b5 under an F melody line. The degrees are
  applied **in document order, each refining the last**, so the table keys off the
  *result* of the previous degree as well as the base kind. The `text` attribute
  is the final fallback and the inverse of `tabxml._downgrade_kinds`: that pass
  writes an unclassifiable chord as `<kind text="Bb7sus4">other</kind>`, so
  without reading `text` back a round trip of this library's own export would lose
  every chord it could not spell.
- **A tuplet's `<duration>` is unreduced** and must be divided by
  `time-modification`, or every bar after the first drifts a third long.
  "Synthetic Triplets" is written in triplets at 10080 divisions and is the
  test for it.

**Never guess a chord.** A kind the library cannot voice is absent from
`MUSICXML_KIND_QUALITIES` rather than folded into a near neighbour —
`Neapolitan`, `Italian`, `French`, `German`, `pedal`, `power`, `Tristan` and
`none` are all real MusicXML kinds and all absent — and it is counted in
`Head.unmapped` and printed, on the same principle `ChordParser` follows: a spelling
the library cannot read resolves to `None` and is counted rather than guessed at. A
quality naming a chord the voicing tables do not hold
is reported as untranslatable rather than failing silently later.

**The voicings are not re-implemented here.** `arrange_xml_head` hands its slots to
`arranger.slots.arrange_slots`, the engine's own slot layer, which lives in the
package. An imported head therefore gets the same non-chord-tone strategies, the
same opt-in dim7 retry, the same `repeated` hold and the same slash-bass rule as any
other caller. A second implementation of the step loop is how this importer came to
disagree with the library once already; the whole point of the extraction is that it
cannot happen again.

That function is `arrange_slots`, named for what it does: it is the one step loop, and
MusicXML is most of its callers.

**Imports are lazy where they keep the module cheap** — `argparse` inside
`head_cli`, and the renderers inside it too, so `load_musicxml` costs nothing.
`demo.main()` imports `headxml` inside the `head` branch.



## MusicXML export

`format_musicxml` / `write_musicxml` in `tabxml.py` render an arrangement as a
`score-partwise` document for a notation program. It is a **third renderer family**,
not a third column: it is the only one that needs a dependency, and the only one that
has to be post-processed before it is correct.

| name | role |
|---|---|
| `tabxml.format_musicxml` | the document, as a string. Pure, like every other renderer |
| `tabxml.write_musicxml` | the only function in the module that touches the filesystem |
| `tabscore.score_events` / `tabscore._is_hold` | placement, durations and the pickup; the rhythmic core, shared with `tabgp` |
| `_build_part` | the staff: measures, notes, ties, chord symbols |
| `_chord_symbol` | a symbol, or a text-only one for a name music21 rejects |
| `_drop_empty_inversions` | removes the meaningless `<inversion>-1</inversion>` |
| `_downgrade_kinds` | rewrites a `<kind>` value MusicXML 3.1 does not have |

**An empty arrangement is answered at the definition.** `tabscore.score_events` returns no events and a
pickup of 0 when it is handed no steps: the pickup is measured from the first onset of the
steps placed, and an arrangement with none has no first onset. This is the seam both score
renderers place through (`tabxml.format_musicxml` and `tabgp.format_gp5`), so the empty case
belongs to it rather than to a guard at each caller — the renderers' own `if not steps`
guards are their documented contracts (an empty document for no steps), not what keeps
`score_events` safe to call. What that case *means* is a separate question: a **chords-only lead
sheet** produced zero steps while a part was built from melody notes alone, so its music was
declined by every export path rather than rendered — [open-issues](history/open-issues.md) item 1's
extreme case, and the union that closed it is why such a sheet now arranges. A **melody-only
selection** is still empty, which is a different claim: it plays the tune, and there is none.

**There is no TAB staff, deliberately.** This was a measured decision, not a
simplification. music21 cannot write a TAB staff a notation program renders
correctly: it emits neither the `<staff-lines>6</staff-lines>` a tab staff needs nor a
fret and string for each note *inside* a chord - it puts them all on the chord's first
note (cuthbertLab/music21#1534). Patching both back in leaves a document that
**still does not display correctly in MuseScore 3**, and a workaround that does not
work costs more than not shipping it, so `tabxml` writes a **notation staff only** and
`tabgp` writes the fretting, as a Guitar Pro 5 file. The two are divided by what each
format can do: GP5 stores a fret and a string per note natively, MusicXML reaches
Sibelius, MuseScore and Final. Everything that is genuinely *shared* - `score_events`,
`_is_hold`, `substitute_steps` - lives in `tabscore`, so a head lands on the same beats in
both files.

Six decisions in here were each forced by a failure or by the instrument's own
convention, not chosen:

- **The guitar's part is written an octave above its sound, and the transposition is
  declared rather than merely implied.** Guitar sounds an octave below its written
  pitch - the convention that keeps the staff off the ledger lines - so `_build_note`
  writes every pitch raised by `_WRITTEN_OCTAVE_SHIFT`, and `format_musicxml` makes the
  part `instrument.Guitar()` transposing by `interval.Interval('P-8')`, which music21
  emits as `<transpose><octave-change>-1</octave-change></transpose>` in the first
  measure. **Both halves are required**: raised pitches alone notate the staff correctly
  and *play* an octave too high, and the transposition alone notates concert pitch. The
  clef stays a plain treble clef - the form most lead sheets use - rather than an 8vb
  glyph, so the octave is never marked twice. `headxml._transposition` reads the value
  back, summing `<chromatic>` with twelve per `<octave-change>`, so the exporter's own
  round trip returns the melody at concert pitch and a head written for *any*
  transposing instrument - a Bb part, say - is arranged at concert pitch rather than
  shifted.
- **The document is post-processed with `ElementTree` after music21 writes it** - for
  `_drop_empty_inversions` and `_downgrade_kinds`, and `_unique_instrument_ids`.
- **Steps are placed by `tabxml`, not by `tabstaff._staff_columns`.** The column grid
  is deliberately lossy - two steps on one onset collapse into one column, "the first
  step in a column owns that column" - which is right for a fixed-width ASCII staff
  and wrong for a score. The eighth-note skeleton puts two steps on the last beat of
  most bars, so sharing the grid would drop a chord from every bar of a head. What is
  shared is the *semantics*: absolute onsets with signed bars, and collapse on
  unchanged sounding pitches.
- **Steps sharing an onset divide their span equally**, and the transcribed
  `duration` is not used as a weight. It is the length of the *melody note* the step
  came from, which runs past the onset, and its values are arbitrary
  fractions of a whole note; scaling by them yields note values music21 refuses to
  write, and it refuses the **whole export** rather than rounding one. Two eighths on
  the last beat of a bar are two eighths.
- **Only the first measure carries the time signature.** MusicXML says a signature
  holds until it changes, so repeating it in every bar is legal but reads as a new one
  at each: MuseScore 3 draws a 4/4 over every bar of the head. music21 needs no
  per-measure signature to pad and tie the bar: it resolves each measure against the
  signature already in force, and the export does not touch `makeRests` without one.
  Eight corpus heads, plus pickups,
  bar-line crossings and rests, all re-parse with every bar the right length.
  `tests/test_musicxml.py::test_the_time_signature_is_written_once` is the regression.
- **GP5 states the key on *every* bar, where MusicXML states it once.** The two formats
  disagree structurally here. The exporter writes one `MeasureHeader` per bar, so
  `keySignature` has to be set on each: a fresh `MeasureHeader` defaults that field to
  `KeySignature.CMajor` and **does not inherit from the previous one**, so setting it on
  the first bar alone exports a 32-bar Eb head as "Eb major, then C major" for 31 bars.

  A test reading `measureHeaders[0]` cannot see that — bar 1 is always right — and the
  **one-bar** fixture in `tests/test_guitarpro.py` is the one shape that cannot catch it
  either, which is why `test_every_bar_carries_the_key_not_only_the_first` builds its own
  three-bar arrangement and asserts over every header.

  `PyGuitarPro`'s writer dereferences `keySignature` unconditionally, so a `None` there
  raises `AttributeError` on **bar 2** and the file is never written. `_key_signature`
  returns `None` for a key GP5 cannot name (`fifths` outside ±7), so both bars use one
  rule, `key_signature or KeySignature.CMajor`, which is also what an absent signature
  means to every reader.
- **The key signature is written, in the first measure, on the same terms.** `fifths`
  counts sharps (positive) or flats (negative) and `mode` says which of the
  signature's two keys it is; both reach `_build_part` from `Head.key_fifths` /
  `Head.key_mode`, and a `fifths` outside -7..7 is rejected rather than clamped.

  It matters because music21 writes an explicit `<accidental>` for any note the
  signature does not already account for. A 32-bar Eb-major head needs **27** — every one
  of them a note genuinely outside Eb or a cautionary repeat within a bar — and without
  the signature it needs **201**, 137 of them flats the key had already said.

  **A chord symbol's pitches mark notes the signature accounts for**, which is a second
  cause of the same noise. music21 writes a `ChordSymbol` as `<harmony>` alone —
  `writeAsChord` is False — so its pitches never reach the document, but they stay in the
  stream and are still counted when music21 decides which notes need an accidental: 139
  with symbols against 27 without, for the same music. `_chord_symbol` clears them on both
  the parsed and the fallback path, because a pitch the document does not contain has no
  business deciding what the document contains.

**An accidental count is read against the key, not compared with a target.** "I Was
  Doing All Right" is in G, and its export carries F naturals — the F of a `G#dim7`
  resolving to `G7b9`. In a file with no `<key>`, a reader assumes F♯, and **12 of
  those Fs go out with no accidental at all** — silently F♯ to a reader. Stating
  the key raises that file's accidental count from 48 to 66, and the 18 more are
  almost exactly those notes finally marked. So a falling count is the *expected*
  consequence of stating the key and a rising one is not automatically a regression: both
  have to be read against the key, which is why the check here is not "fewer accidentals"
  but "every accidental is either required or a cautionary repeat within its bar".

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
without it, and `head_cli` reports the missing extra as a usage message rather than a
traceback.

**A chord name music21 cannot classify is written, not dropped.** `mMaj7`, `maj9` and
`7alt` are among the ones it rejects, and published notation produces more
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
the fault it repairs.

**Open, and worth doing next: validate against the actual XSD.** `xmlschema` as a
**dev-only** tool (like pyright, never a runtime dependency and not in the `xml` extra)
would catch this whole class - MusicXML-level errors invisible to a round trip. It
means vendoring the 3.1 XSD into `tests/` and skipping when absent, in the same
`skipUnless` spirit as the optional-extra tests.

**Known limitations.** Durations are floored at a sixteenth, because MusicXML cannot
write less and music21 aborts rather than rounding; nothing this library generates is
shorter than an eighth. A triplet onset that does not divide the bar evenly would hit
the same wall - untested. The provenance notes the HTML page carries (`notes=`) are
not written into the score.
- **`__all__` is an explicit list**, not computed from `globals()`. The lazy
  `__getattr__` hides the re-exported names from a star import, so a computed list
  would export less than the module has.
  `TestTabstaffModuleBoundary::test_dunder_all_matches_the_public_surface`
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
all. That is not merely tidier than a MusicXML tab staff: it is the
**only** one that works, since music21 cannot write a tab staff a notation program
renders correctly (see [MusicXML export](#musicxml-export)). So the division is
by capability, not by preference: GP5 carries the fingering, MusicXML carries the
notation, and neither renderer tries to do the other's job. But GP5 has no notation
staff and is a closed (undocumented) format, so what reads it is the family of *tab*
programs: Guitar Pro 5 and later that still read GP5, TuxGuitar, and the browser and
mobile readers built on engines such as AlphaTab. MusicXML remains the way into
Sibelius, MuseScore and Final. Both are shipped, and both are one flag
on `corpus_cli` (`--musicxml`, `--gp5`).

**What is shared, deliberately.** `tabgp` calls `tabscore.score_events` and
`tabscore.substitute_steps` rather than reimplementing either, so a head lands on the
same beats in both files and a substituted chord is named the same way in both.
The **chord names** are shared too, by rule: `_build_song` keeps an `in_force` and
writes a name only where the chord changes, which is the same walk
`tabxml._build_part` does for its `<harmony>` symbols — so a chord is named once, at
the attack that changes it, in both files, and a continuation part (the rest of a
length split, a hold crossing a bar line) never carries a label of its own. That is
the *semantics*; the bar grid is separate, for the reason below.

### Where GP5 genuinely differs from MusicXML
An **incomplete first bar is an anacrusis**, and `tabscore.score_events` recognises it
from the music alone: a first bar whose events stop before the bar line has a pickup
equal to the silence that is missing. A head whose bar 1 is one quarter note of a 2/2
bar therefore reports a pickup of three quarters and drops the trailing rest that would
have filled the bar. A source `<bar-style>` is not needed - the incompleteness is the
cause - and the three renderers spell the same decision differently:

**An imported head also carries the source's own statement.** `Head.first_bar_implicit`
is true when the score marks measure 1 `implicit="yes"` (or numbers it 0), and
`headxml._merge_chord_slots` withholds the positions its union generates in that bar. A
comping chord in the short bar would fill it, `score_events` would read a full first
bar, and the pickup would be erased - which is why the accompaniment starts in bar 2
while the written melody keeps the anacrusis.

- `tabxml._build_part` writes a **short first measure** - the pickup's music is the
  whole of it - marks it `implicit="yes"`, and `_apply_pickup_barline` closes it with
  the `light-light` bar line an engraver puts after an anacrusis.
- A GP5 measure is a fixed-length container and the format cannot say "this bar is
  only two beats long", so `_measures` writes a **full first measure with the pickup
  as a leading rest** and the music follows it. That pads *before* the pickup notes,
  which keeps them immediately ahead of the next bar's downbeat.
- The ASCII staff leaves the bar short and draws `||` where it stops:
  `_first_bar_content_end` is the recognition, `_fill_rests` leaves the trailing
  silence unwritten, `_slot_counts` stops the bar's columns at the same point, and
  `_mark_pickup_barline` closes it.

The notes and their order are untouched in all three; only where the missing time is
drawn differs.

Two more consequences of a fixed-length measure:

- **An event crossing a bar line is split**, written as two notes in consecutive
  measures. The second half is written with `NoteType.tie`, so the two are one held
  note rather than the shape struck twice. A GP tie is not "a slur the player has to
  interpret": writing both
  halves as plain notes re-strikes the shape at the head of every bar a step
  crossed - **14 of the 32 bars** of "the synthetic cut-time head", whose score genuinely ties
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
*Blue Train* and one each of two *synthetic common time* transcriptions. Both causes
are in `_duration_split`, and **both are silent** — the file writes cleanly and is
only wrong on read, so nothing in the round-trip test caught them until a real
notation program was run against the output.

- **A duration is a power of two, and there is no dotted note.** The value is
  written as `value.bit_length() - 3` and read back as `1 << (n + 2)`, so a length
  that is not a power of two has to be *split*, not rounded. A dotted half (3
  quarters) rounded to the nearest legal value is a **whole note** — a quarter too
  long, and a bar summing to more than its 4/4 signature. It is written as a
  half plus a quarter.
  **And the parts are tied, which is what makes them one note rather than two.**
  The note type is decided by `tie` from `_measures`, which marks a
  note continuing an *earlier bar* — so the parts of an intra-bar split would go out
  as ordinary notes, and a dotted half would play as a half and then a **re-struck**
  quarter in the middle of its own hold. Measured over every head
  `arrange_xml_head` arranges: every continuation beat is tied, and
  `tests/test_guitarpro.py` walks the writer's own model against the parsed bytes
  for each one. The chord name was duplicated with the note:
  it is written only where the chord changes (see "What is shared" above), so
  bar 2 of "synthetic common time" — a dotted half over a quarter, three written
  beats — shows **one** `Bbm7` where it showed three, and plays two attacks rather
  than three. `test_a_dotted_length_is_tied_within_a_bar_not_re_struck` is the
  mechanism, `test_no_split_continuation_in_a_written_head_is_re_struck` walks the
  writer's own model against the parsed bytes over the real export, and
  `test_a_chord_is_named_where_it_changes_in_a_written_head` is the label rule.
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
one too, and a rest is time.** Bar 4 of "the synthetic cut-time head" is a single whole note and
bar 5 opens with a quarter rest, so the gap from the note to the next onset is five
quarters while the note is written for four. The span a step is given is the gap to
the *next sound*, which is not the same as how long it *sounds* — so the note was
held over the silence into the next bar, and since a step crossing a bar line is
tied, the bar opens with a tied chord where the score says a rest. The eighth-note
skeleton puts a rest at the head of every second bar, so that is not one bar but
half the head.

`tabscore.score_events` therefore **caps** the span at the melody note's own `duration` and
writes the remainder as an explicit rest — a `(None, False, length)` event, which is
already what all three renderers read as "nothing here" (`tabxml` writes a
`<rest>`, `tabstaff` blanks the cell and clears the ring, `tabgp` writes
`BeatStatus.rest`). Three properties of the cap are load-bearing:

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
  GP5 — which includes TuxGuitar and the browser and mobile tab readers built on
  engines such as AlphaTab.
