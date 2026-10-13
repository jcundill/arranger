# Parts: melody, bass, chord — redesign of the harmonisation axes

**Status: partly built. Step 1 (§7) has landed** — `bass_style` as a note-rule table,
replacing the `walk`/`anchors` policies, byte-identical over the committed heads. Steps 2
onwards are still proposal, and the parts model itself (`parts=`) is not built. Counts live
in the documents named here, not restated.

## 1. Why

Six flags. Four questions. Each flag answers one to three of them.

| flag | when a part sounds | which degrees | which parts are mine | how realised |
|---|---|---|---|---|
| `texture=` | yes | yes | **yes** | yes |
| `bass=` | yes | yes | no | no |
| `voices=` | no | yes | **yes** | yes |
| `harmony=` | no | yes | no | no |
| `grid=` | yes | no | no | no |
| `grips=` | no | no | no | yes |

Five consequences on record:

- `texture=`'s empty palette and `voices=` **both** used to mean "the guitar does not sing",
  which is the overlap [comping-styles.md](comping-styles.md) §2 records. [one-fact.md](one-fact.md)
  Stage 2 moved the claim onto `voices=`, so what remains is one fact on each side rather than
  two spellings of one: an empty **palette** says the left hand plays nothing here (a thickness
  fact), and only a soprano-less **selection** says the tune is somebody else's.
- `texture=` is a 2-D space enumerated as a list — §3 of that document.
- `--voices soprano,alto` arranges the same as `auto` — [voices-axis.md](voices-axis.md)
  §7 item 6.
- `harmony=full` is accepted and answered with a different family —
  [open-issues.md](open-issues.md) item 3.
- **Unexplained**: on the comping route `--grips` yields four arrangements and the
  cause is not established — [comping-styles.md](comping-styles.md) §2 item 3.
  Explain it before deleting the flag that carries it.

## 2. Three parts, not four

Four strings sound at once. The reason is physical: the right hand is thumb, index,
middle and ring — `p-i-m-a`, four digits (`grips.RIGHT_HAND_STRINGS`). Four strings is
not four parts. Three parts:

- **melody** — 0 or 1 note. The tune, on the top string. Its rhythm is data, not choice.
- **bass** — 0 or 1 note. The bottom of the band. The note that names the chord.
- **chord** — 0 or more. The harmonisation between them.

The fourth string is **capacity, not a part**.

The bass part is not the thumb, and the thumb is not the bass part.
[fingering.md](fingering.md) §2.5: the thumb takes the lowest sounding string, then
index, middle, ring upward. A shape whose lowest note sits above the thumb's reach has
**no** thumb in it. A shape with no bass line still has its bottom note taken by the
thumb. The parts model says what music is there. The digits stay derived in
realisation. One fact, one source.

## 3. The arithmetic, and the table it makes

```
melody (0 or 1) + bass (0 or 1) + chord (0..n)  <=  RIGHT_HAND_STRINGS (4)
```

Not a new rule. The engine enforces it in three places: `grips.thumb_safe_grips` is the
melody+bass case; `supported_string_sets()` is the four-string half; the defect behind
`AGENTS.md` trap 13 was melody+bass+a four-note chord part, which is five. As
arithmetic it is a precondition rather than a repair — refused before generation, not
narrowed afterwards by a texture's palette.

| guitar takes | strings | today's nearest spelling |
|---|---|---|
| melody | 1 | `voices=soprano` |
| bass | 1 | `voices=bass` |
| melody + chord (1) | 2 | `voices=auto` with `grips=duo` |
| melody + chord (2) | 3 | `grips=shell`, no thumb |
| melody + chord (3) | 4 | `voices=auto` with `grips=drop2` |
| melody + bass | 2 | `voices=soprano,bass` |
| melody + bass + chord (2) | 4 | `texture=walking_bass` target |
| bass + chord (3) | 4 | `harmony=shell_root` with the thumb |
| chord (1) | 1 | `voices=alto` or `voices=tenor` |
| chord (2) | 2 | `voices=alto,tenor` |
| chord (3) | 3 | comping with `harmony=shell_root` |
| chord (4) | 4 | [comping-styles.md](comping-styles.md) §9.4, unbuilt |

Every grip family and every `voices` selection lands in a cell of this table. The
generative space already is this table. Today three flags address it, with aliases and
collisions between them.

## 4. The axes that remain

| axis | owns | replaces |
|---|---|---|
| `parts=` | which of melody / bass / chord the guitar takes | `voices=`, and the empty-palette route to "the left hand plays nothing" |
| `grid=` | when each part sounds — positions crossed with parts | `grid=`, and the bass rhythm half of `bass=` |
| `texture=` | the **chord part's arity**, by metric weight | `texture=`, and the arity half of `TEXTURE_GRIPS` |
| `harmony=` | the chord part's **degree order**: which degrees fill the arity asked for | `harmony=`, and `harmony=root` |
| `bass_style=` | the bass part's **note rules**, ordered | `bass=`, `BASS_STYLES`, `BASS_POLICY_ROLES` |

Values: `parts=melody,bass,chord`, with the order canonicalised because it carries no
meaning. `texture=uniform|targets|chord1|chord2|chord3`, `harmony=auto|full|guide|shell_root`,
and `bass_style` an ordered list of `root`, `5th`, `nearest` and `approach` in which the
first reachable note wins.

`harmony=auto` is the default and it resolves from `parts`: the **full order** when the
melody is the guitar's, the **guide pair** when it is not. The two shipped defaults are
different shapes — the first three of the full order on the singing route, the guide pair on
the comping one — so one value cannot be both, and this is the one sentinel that **decides**
rather than naming its own default. That is why it survives where `grid`'s was withdrawn.

`uniform` is **derived, not listed**: it is the most notes the arithmetic allows at that
position. With the tune on top and no thumb that is three — the four-note shape the engine
has always built. With a thumb under it the budget gives two, which is the shell.
`targets` reads `_metric_weight`, `TARGET_BEATS` and the conditions behind decisions E and
F, so those stay **rules the policy reads** rather than becoming data.

So `texture=` is the half of `TEXTURE_GRIPS` that is not a grip list. The target-versus-fill
role is a claim about thickness, and a grip tuple was only ever how thickness was
implemented. That implementation dies with `grips=`. The claim survives, and so does the
axis — which is why the count here is **6 to 5** and not 6 to 4. The complaint was never the
number of flags; it was that a flag answered two questions, and each survivor answers one.

`grid=` is positions crossed with parts, because the bass rhythm is its business:
`joe_pass` is a chord on every upbeat and a bass note on every beat, and the two parts do
not move together. Its rows are not all bar-relative: a row may derive its positions from the
harmony **timeline** instead, which is how `anchors` says "the root, where the chord changes"
(§9). `harmony=` names the order and `texture=` names how many of it sound, so the two cannot
disagree about arity the way `full` and a voice count did.

The order `harmony=` names is **`TONE_PRIORITY`'s row for the quality**, read at the chord
part's own degrees, so the arity `texture=` takes is a *prefix* of that row and a reduced shape
gives up its *tail*. For `Cmaj7` (`3rd, 7th, root, 5th`) that is: at three voices drop the
**5th**, at two the shape is the guide pair, at one the 3rd alone. Two facts sit beside the
row, and both are already in the tables rather than new here. A tone the **melody** states is
not a candidate for dropping — the tune is one of the chord's voices, which is what
`stated_tones` already does by excluding the melody's degree — so the melody's presence can
change *which other* tone is given up. And an **altered 5th** — `Bbm7b5`'s `b5`, a `#11`, a
`b13` — is kept over the root rather than dropped beside the natural 5th, so a reduced shape
gives the **root** up before it.

Five axes against the four questions in §1, and that is not a regression: what the chord
part states is **two** facts, an order and a count. `harmony=` gives the order, `texture=`
takes the first n of it, and a count longer than the order is refused rather than padded. So
`guide` and `full` differ in the length of the list they offer, not in how many notes are
wanted — `full` is not "more notes", it is a longer order to slice. A single flag answering
both is what `harmony=full` used to be, and item 3 of the open issues is where that ended.

Unchanged, because they were never part of the confusion: `top_strings`, `fret_min`,
`fret_max` (the neck window); `non_chord_tone`, `fallback` (strategies); the renderers.

`grips=` becomes an internal search space rather than a flag. The caveat is honest: its
families share cells of the parts table and differ in degrees and strings, which
`TONE_PRIORITY` and the window decide. The claim is "not choices we expose", not "the
distinctions do not exist". §1's measurement must become a function of parts, texture and
window, or be recorded as a defect.

The refusals are derived, never listed: the arithmetic refuses an impossible selection, so
`parts=melody,bass` with `texture=chord3` is five strings; a degree order too short for the
arity asked is refused from the row's own length; a content policy for a part the selection
does not name is refused, naming the part that would work; `grid_allowed` keeps its
one-directional test.

An `NC` bar has no chord, so the **chord part has no event** and the **bass part has none
either**: a part whose notes are chosen from a chord cannot state anything where there is no
chord, and that is a derivation rather than a rule about chordless bars. The melody part is
unaffected, so such a bar sounds the tune alone. It is deliberately **not** the claim an
off-grid rest makes — there the thumb still walks, because a grid thins the chords and not
the bass line. "No chord here" and "silent here" are different facts, and only the second is
a rest.

## 5. What it fixes

1. `harmony=full` stops lying, because `full` stops being an arity word at all. It is the
   whole tone set in `TONE_PRIORITY` order, and the texture's arity takes the first n of
   it. [open-issues.md](open-issues.md) item 3 goes for good.
2. `texture=walking_bass` dissolves into the two things it always was: a bass part with
   note rules (`parts` and `bass_style`) and a thick-on-the-strong-beat arity (the policy).
3. `shell_root` is no longer a conjunction of two degree tables welded inside
   `_shell_voicing`. It is one degree order with a bass-register note at the bottom.
4. The lone-bass branch in [voices-axis.md](voices-axis.md) §8a goes. That register fact
   was about a part, not a name.
5. §7 item 6 of that document goes. A part is taken or not taken, `voices=none` has no
   equivalent, and there is no inner voice to name.
6. The overlap in [comping-styles.md](comping-styles.md) §2 goes. "Does the guitar sing?"
   is one part's presence.
7. `harmony_allowed`'s "room for three" refusal goes, and the arithmetic does not inherit it:
   `shell_root` is the guide pair plus a register note, so at arity two it **is** the guide
   pair rather than a combination to refuse — the refusal had no work left to do. The one
   refusal that does move is `harmony=root`'s, into the rule that a content policy for a part
   the selection does not name is refused.
8. `resolve_texture_grips`' five arguments become the selection's own budget, and trap
   13's class of defect becomes unrepresentable rather than repaired.
9. **The chord-tone invariant gains a named exception.** The bass part may state a note
   outside the chord: `bass.py` already adds a chromatic approach
   (`(anchor_pc + 1) % 12`), and `tests/test_walking_bass.py` already says "the thumb is no
   longer uniformly chord tones". Today that is hidden by scope, because the merge happens
   after the shape check. Here it is a fact about a part, and the invariant in `AGENTS.md`
   states it instead of implying it.
10. The step model does not change. `melody_voiced`, `bass_only`, `bass_role`,
    `chord_unvoiced` and `silence` are already part facts — see
    [one-fact.md](one-fact.md).
11. **An `NC` bar sounds the melody and nothing else, on every route.** Today the bass part
    is settled by the route instead: a chordless bar between two chords is walked when the
    guitar sings, and every beat of it is refused when it comps, because the walk anchors on
    the previous chord's root and only the singing route has an upper shape to merge it into.
    Measured over the committed heads this change moves **0 steps** — `NC` occurs in one
    head, as a first bar, where there is nothing to anchor on — so its acceptance gate is a
    **new** test for a chordless bar between two chords, not a moved count.

## 6. What it costs

- `harmony=` becomes load-bearing where the guitar sings, which it is not today. The
  `--grips shell` chord-melody must be expressible in the same pass: an arity from the
  texture plus a degree order from `harmony`. That is the deferred option (A) in
  [comping-styles.md](comping-styles.md) §6 Q2.
- `bass.py`'s `_walking_bass_line` and its `BASS_ROLE_*` set become the `bass_style` table,
  so the walk's own pitch — the lever [open-issues.md](open-issues.md) item 2 measures —
  becomes something a caller can name.
- The generator's core rule is touched. `TONE_PRIORITY` and `_drop2_template_for` are the
  drop-2 rule ([generated-grips.md](generated-grips.md)). Re-express it, do not wrap it.
- The gate. Fingerprints are re-baselined by construction equivalence
  (`tests/test_step_loop_equivalence.py`, `AGENTS.md` trap 8). Never regenerate snapshots.

## 7. The order it lands in

1. ~~`bass_style` as a note-rule table~~ — **built**. `BASS_RULE_ROLES` maps each note
   rule (`root`, `5th`, `approach`, `nearest`) to the `BASS_ROLE_*` values it admits, and
   `parse_bass_style` owns the flag's vocabulary. It replaced `BASS_POLICY_ROLES` (the
   policy→role filter) and the shipped `walk`/`anchors` spellings; the root-then-5th
   preference in `_shell_voicing` is named by the `5th` rule but that half is still the
   `_shell_voicing` code. The shipped resolution order is `root, 5th, approach, nearest`
   (not §4's literal order — see §9), and it is byte-identical to the old `walk` and
   `anchors` over all 3,696 committed-head steps. The *rhythm* half of `bass=` still waits
   for step 5, so the shipped styles keep it for now.
2. A chord timeline at beat level ([open-issues.md](open-issues.md) item 1's remainder).
   Needed before `grid=` can own "when": today a grid can only filter melody slots inside a
   bar the tune occupies. It is also what makes a chordless bar *between* two chords
   expressible, which is where the `NC` rule in §4 bites.
3. `parts=`, replacing `voices=` and the empty-palette route to "the left hand plays nothing".
4. `texture=` reshaped as the arity policy, which is where `TEXTURE_GRIPS` loses its grip
   lists and `walking_bass` leaves `TEXTURE_STYLES`.
5. `grid=` becomes positions crossed with parts, taking the bass rhythm with it.
6. Deletions: `grips=`, `HARMONY_ROOT`, and the `voices=none` and `voices=auto` spellings.

Steps 3 to 5 are one logical change and land as **one commit**. They cannot be three: the
house rule is one green `make check` per commit, and a rename that removes a spelling cannot
be split into green steps — an intermediate state has `parts=` half-wired and `voices=`
half-gone. §8 rules out the other split (accept both spellings first, drop the old one
later), because a surviving alias keeps the collision addressable.

## 8. Deliberately not built

No per-finger cost criterion ([fingering.md](fingering.md) §5 step 3). No sixth axis. The
digits stay derived and unexposed. `voices=` does not survive as an alias: this is pre-1.0,
and an alias keeps the collision addressable. Two `*_AUTO` sentinels survive: `harmony`'s,
which resolves from `parts` because the two shipped defaults are different shapes, and
`bass_style`'s, so naming no style uses the shipped note rules — `root`, then `5th` — rather
than `none`: naming the part is a request for it to sound.

## 9. Decisions taken

- **`bass_style` names note rules, not degrees alone** — root, 5th, nearest to previous,
  approach next chord. `targets` is not one of them: that is the texture's word.
- **The shipped resolution order is `root, 5th, approach, nearest`, not §4's literal
  `root, 5th, nearest, approach`.** The listing in §4 is the vocabulary; the order is a
  separate fact, and `approach` must sit before `nearest` because on the last beat the
  approach outranks the connective note. That ordering is what makes the full list
  byte-identical to the old `walk`. An amendment taken when step 1 landed, not a
  contradiction: §4 enumerates, this fixes the sequence.
- **`grid=` names positions and `texture=` owns arity.** `targets` keeps its measured
  metric-weight behaviour, so arity is a policy rather than a per-position literal.
- **`parts=` is one comma-separated list**, parsed by the module that owns the vocabulary
  and canonicalised, because its order carries no meaning.
- **`grips=` is not a choice.** Its families are a search space over the chord part's
  degrees and the neck window.
- **A named bass part with no style resolves to the shipped *note rules* — `root`, then `5th`,
  the `BASS_DEGREES_6432` order — and its *density* is `grid=`'s.** That is the reading that
  makes §3's `bass` cell true: a bare `parts=bass` under the default grid (the melody's own
  slots) reproduces today's `voices=bass`, the per-slot one-note shape (`_shell_voicing`'s
  `bass_voice` branch), because the note rule is the shipped one and the grid fires once per
  slot. The *thumb line* is a combination rather than the default: those note rules plus a
  per-beat grid. `bass_style` names note rules, so "no style named" can only mean "no note
  rule named", which is the shipped one — **not** `none`. A style named for a part the
  selection leaves out is still refused, naming the part that would work.
- **`anchors` is a grid row, not a `bass_style`.** Its note rule is `root` and its rhythm is
  "where the harmony changes" — a position set the **timeline** derives, not a bar-relative one
  — so it belongs with `grid=`, which is what §4 means by "the bass rhythm half of `bass=`", and
  it needs §7 step 2's beat-level timeline to be expressible. `walk` is the other half of the
  same split: every beat of every bar the melody touches, a metre-relative set. So `bass=` (the
  flag) dissolves into one `bass_style` and one grid row, and no note rule is lost: `root`,
  `5th`, `nearest` and `approach` are all `bass_style`'s.
- **`harmony` keeps an `auto` sentinel** that resolves from `parts`: the full order when the
  melody is the guitar's, the guide pair when it is comping. One value cannot be both, and
  the sentinel decides rather than naming its own default.
- **The chord part's order is `TONE_PRIORITY`'s row, sliced.** `harmony=` names the row and
  `texture=` takes a prefix of it, so a reduced shape gives up the tail. For `Cmaj7`
  (`3rd, 7th, root, 5th`): three voices drops the **5th**, two the guide pair, one the 3rd.
  A tone the **melody** states is excluded from the candidates, so the melody's presence can
  change *which other* tone is given up.
- **An altered 5th is kept over the root.** `Bbm7b5` gives up its **root** before its `b5`,
  and the same holds for `dim7`, `7b5`, `7#5`, `7#11`, `7b13` and `maj7#11`. The rows say so;
  the change is inert over the 119 witnessed templates — the only shapes that move are the
  unwitnessed natural-5th melodies of `7#11`, `7b13` and `maj7#11` — and it is what lets a
  reduced chord part keep the tone that names the altered chord.
- **`shell_root` is the guide pair plus a register note.** So `chord1` and `chord2` under it
  equal `guide`'s and only `chord3` differs — a **new** reading, not today's: today
  `shell_root` below three voices is refused, which is why §5 item 7 deletes the refusal
  rather than relocating it.
- **An `NC` bar has no chord part and no bass part**, on every route, and the melody is
  unaffected. The rule is derived: a part whose notes come from a chord cannot sound where
  there is no chord, and the thumb refusal the comping route reports today is retired with
  it. An off-grid rest keeps its thumb, so the two kinds of silence stay separate.
