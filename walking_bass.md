# Walking Bass Texture — Implementation Plan

This document is a design plan only. It does not implement any new behavior yet.

It supersedes the earlier draft of this file, which proposed a separate
`walking_bass=True` flag and a parallel bass pipeline. Both were revised after
reading the engine: the decisions and the reasons for them are recorded below,
so the rejected alternatives are not re-proposed later.

## Goal

Add `texture="walking_bass"` — a thumb line on the bass strings under a **light**
left hand: a shell (3rd & 7th) struck on a target beat, the **melody alone** between
(decision C), and a four-quarter walk underneath.

The existing emphasis is preserved:
- playable guitar voicings
- melody pinned to the soprano string
- hand position stability
- backward compatibility for `uniform` and `targets`

## The three design decisions that shape everything else

These were each forced by reading the code rather than chosen up front, and each
one removes work rather than adding it.

### 1. Shells and the melody alone, not full voicings

The upper structure is restricted to a shell (target) and the melody alone (fill).
Four consequences:

- **It removes the string collision.** `drop2_6432` is the only *four-note* grip
  that reaches the low E, and it is never offered. Checking
  `GRIP_STRING_SETS["shell"]` against soprano string, only the **6-4-3** shell
  touches index 0, and only for a G-string soprano — where 5-4-3 and 5-3-2 are
  always available. No parameter, no A-string fallback, and no post-filtering
  of candidates that could escape `supported_string_sets()`.
- **It sidesteps the completeness problem.** `voicing_cost` ranks
  `missing = 4 - len(active)` *above* neck position. That is exactly why
  `targets` needed `TEXTURE_GRIPS` to restrain the candidate set; restricting the
  grip tuple does the same work through the mechanism that already exists.
- **It is the music.** A shell is 3rd + 7th, so the **root is absent from the
  upper structure**. A walk landing on the root supplies the note the shell
  deliberately omits — the guide's "Root + 3rd + 7th … or just 3rd & 7th under
  the melody note" and its "Chord-Bass Alternation (Walking Bass)". The duo's own
  safety rule — `DUO_DEGREES = (0, 7)`, a root or 5th in the melody over a 3rd — is
  noted and then **not needed**: decision C drops the duo from the fill tuple, so
  which melody degrees may take one never arises in this texture.
- **It is one texture, not a second axis.** `TEXTURE_GRIPS` is already
  `texture → role → permitted grips`, passed straight into `prepare_step`.
  Shell-or-melody-alone *is* a texture choice, and it inherits the target/fill machinery.

An earlier draft proposed a separate `bass=` keyword. That was solving the
wrong problem and is dropped.

### 2. Target = strong beat **and** harmony changed since the last target

This is the off-beat chord change rule, and it is the heart of the design.

**Two independent axes.** Only one is a design choice:

- **Which chord** a step is voiced against comes from the harmony *timeline* —
  the same forward fill `wjazzd._forward_fill` and `headxml` apply. A change on
  beat 4-and means every step from 4-and onward is harmonised against the
  **new** chord, full stop. This is unaffected by role.
- **How many notes** is the role: shell (target) vs melody alone (fill).

So on an off-beat change nothing sounds *wrong*. The only question is whether
the left hand states the new harmony **there** or **at the next target beat**.

**Why this case is the common one, not the edge case.** Off-beat chord changes are
the mechanism a walking bass is built from: if the harmony only moved on 1 and 3,
the thumb would have four notes and nowhere to walk through. A rule tuned only
for on-beat changes is tuned for the exception.

**The hazard that decides it.** If an off-beat change were promoted to a
`target`, it would get a shell. But off-beat slots are exactly where the melody
is most often a *non-chord tone* — that is what makes it a passing slot. And a
shell under a non-chord tone goes through the non-chord-tone strategies in
`prepare_step`: `extension` may rewrite the harmony to `Cmaj9`, `diminished`
may substitute `Bdim7`. On a weak beat, under a note that was only passing
through, a substituted chord is mud, not colour. The texture would get busier
exactly where it was meant to get lighter.

**The rule.** A slot is a `target` when it is metrically strong **and** its
normalised harmony differs from that of the previous `target`. A strong beat
with no change since the last target is a `fill`, and so is every off-beat slot.

**The off-beat answer.** A chord change on beat 4-and is voiced as a **fill** under the
**new** chord — the melody alone, plus the thumb's note for that beat (decision C). The
harmony is correct but deliberately thin, and stated fully at the next target beat.

**One dependency, stated because it is easy to miss.** This rule only reaches the
example's result because a fill is the melody alone: while a fill was a duo or an
interval, a change on the 4-and put notes under a passing tone, and a passing tone is
precisely where the non-chord-tone strategies rewrite the harmony. Decision C is what
keeps the texture light exactly where the off-beat change happens.

**What this buys.** The role rule is a conjunction of the *existing*
`weight > 0` test and one harmony comparison, so `_roles_for_slot` needs no new
metric logic. It also fixes the two-bar chord for free: a chord spanning two bars
yields **one** shell rather than one per bar, which is the "lightest texture"
intent. The earlier chord-change-only rule needed lookahead machinery to achieve
the same thing.

**Non-chord tones on off-beat fills, narrowed by decision C.** The 4-and is a `fill`,
and the first draft worried that a non-chord-tone melody there could still trigger a
substitution under the existing strategies. Decision C mostly removes the question: a
fill is the melody alone, with no chord of its own for a strategy to rewrite. The
residue is a slot carrying a *target's* harmonisation under a note the new chord does not
contain, and there the fix, if the output is noisy, is to suppress substitution on
`walking_bass` fills (`non_chord_tone="legacy"` for fills): cheap, and still better
decided from output than pre-emptively.

### 3. The bass lives in `Voicing.frets`, not a parallel field

`Voicing.frets` is already a six-slot vector with a documented per-string model,
and `tab_string`, `tab_block`, `tabstaff`, `tabxml._build_part` and
`tabgp._sounding_frets` **all** read it. A walking bass is not a new kind of
object — it is *a slot among the bass strings being filled in*, with the string
chosen per note (see the next section).

The earlier draft proposed `bass_note` / `has_bass` / `bass_pattern` fields plus
renderer changes. That would create a parallel representation four renderers must
each learn about, and push GP5 to "follow-up work" for no structural reason.

Two ordering rules make this safe, and they are the concrete answer to "don't mix
bass logic into the cost function":

- **Select first, merge after.** `voicing_cost`'s `missing = 4 - len(active)`
  would be corrupted by a merged fifth voice. The bass is written into `frets`
  only once `_best_voicing` has returned, so it cannot enter the cost tuple by
  construction rather than by discipline.
- **Never overwrite a voice.** The bass takes a string in `BASS_STRING_INDICES` that
  is unoccupied, can reach the pitch, and would sound below the upper structure —
  and among those it takes the one **nearest the hand**, not the lowest-numbered.
  With no candidate, the step gets no bass and the omission is reported: the same
  "penalty, never a filter" argument the neck window already uses. (An earlier
  draft of this bullet said "lowest-indexed", which contradicted the proximity
  rule below and would have reinstated the low-E-first ordering.)

### Which strings: three candidates, chosen by where the hand already is

`BASS_STRING_INDICES = (0, 1, 2)` — the low E, the A string and the 4th string
(D). All three are in play, and the choice is made per note, from the fret the
hand is *already* at.

**The hand is one hand.** The thumb and the fingers are not two independent
players: a walking bass line under a comping left hand is played by the same
person in the same position, and the thumb note belongs at the fret the fingers
are already on. This is not a stylistic preference, it is the physical premise of
the texture, and it is what decides the string.

**The arithmetic makes it unambiguous.** Adjacent strings are five semitones
apart, so the *same pitch* sits five frets lower on each string you move up:

| pitch | 6th | 5th | 4th |
|---|---|---|---|
| D3 | 10 | **5** | 0 |
| F3 | 13 | 8 | 3 |
| G3 | 15 | 10 | 5 |
| A2 | 5 | 0 | — |
| C3 | 8 | 3 | — |

So "prefer the lowest string" and "prefer the string nearest the hand" are in
direct opposition, always, by exactly five frets. A hand sitting at fret 5 plays
D3 on the A string *under the position it is already in*; on the low E that same
D3 is fret 10, five frets of travel for an identical pitch. The hand moves, the
line does not — which is the whole opposite of what this library is for.

**So the ordering is by fret proximity, not string index**:

> For each index in `BASS_STRING_INDICES`, skip it if it already sounds, if the
> pitch is unreachable in `0..18`, or if its note would not sound below the upper
> structure. Of the survivors, take the one whose **fret is nearest the upper
> voicing's position**; break a tie toward the lower sounding pitch.

`hand_fret` is the upper voicing's `avg_fret` (or `top_fret` — the plan should
settle which, and measure it; the B section's bars are the only evidence either way
and they point at a third candidate, the shell's **lowest** active fret). This is
the same economy `voicing_cost` already
applies to the upper voices as its neck-position term, extended to the thumb: the
bass joins the hand rather than forming a second, independent position.

**The 4th string wins rarely, and that is expected.** It is occupied by three of
the five shells: 2-3-4 `(4,3,2)`, 5-4-3 `(1,2,3)` and 6-4-3 `(0,2,3)` all include
it. It is free only under 1-2-3 `(5,4,3)` and 5-3-2 `(1,3,4)`, and under 5-3-2
the A-string note is that shape's *lowest sounding voice*, so a thumb note on the
D string would sit above it and be rejected by the sounding-order filter. It is
worth carrying anyway, because proximity ordering makes it self-limiting: the A
string is always five frets higher than the D for the same pitch, so the 4th wins
**only** when the hand is genuinely low. The filters guard it; the search order
does the rest.

**The 6th string still earns its place**, for the two cases the upper strings
cannot cover:

- **A and 4th are both occupied.** 5-4-3 or 5-3-2 takes the A, while 2-3-4 or
  6-4-3 takes the D. The collision sets are *disjoint*, so between the three
  strings every shell in the table leaves at least one free.
- **The note is below the A string's floor.** A2 is the 5th string's open pitch;
  E2 and F2 are only on the low E. A walk descending into a dominant wants those.

This is the same five-semitone relationship the library already reasons about for
`HIGH_FRET_LIMIT`, where the B string sits five frets *higher* than the high E for
the same written pitch. Here it is the mirror image, and it points the other way:
the lower string is the one that costs travel.

**What this does not claim.** Reach is not the deciding factor — the low E covers
E2–Bb3 on its own and the A string covers A2–Eb4, so neither range forces the
choice. Nor is tone. Both are downstream of a simpler fact: the thumb is part of
the hand, and the hand is already somewhere.

## Types

```python
TEXTURE_STYLES: Tuple[str, ...] = ("uniform", "targets", "walking_bass")

TEXTURE_GRIPS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "uniform":      {"target": GRIP_PREFERENCE,   "fill": GRIP_PREFERENCE},
    "targets":      {"target": ("drop2", "drop3"), "fill": ("shell", "interval", "melody")},
    "walking_bass": {"target": ("shell",),         "fill": ()},
}
```

`"fill": ()` is deliberate and means **the left hand plays nothing** (decision C): the
fill is the melody alone, resolved through `get_melody_only_voicing` rather than through
grip lookup, so the integration step needs one explicit branch for the empty tuple.
`"melody"` is dropped from the `walking_bass` tuples because it is a **token that yields
nothing** — `_string_sets_for` returns `[]` for any grip absent from `GRIP_STRING_SETS`,
so it neither helps nor hurts — and the path it was reaching for is now the fill rule
itself. The same inert token in the `targets` fill tuple is left exactly as it is:
removing it is a tidy-up with no behaviour change, and it is not this feature's business.

The B section's last finding is why the wiring is not optional: a `walking_bass` target
has one grip and **no fallback**, so a melody no shell can sound (`D` over `Bbm7`) would
otherwise *disappear* with only a warning. The melody-alone path is the target's fallback
too, which is the second half of decision C.

`ArrangementStep`, three defaulted fields after `metric_weight`:

- `bass: Optional[int] = None` — MIDI pitch of the thumb note, `None` when absent.
- `bass_role: Optional[str] = None` — `anchor` / `connect` / `approach` /
  `enclosure` / `hold`, for annotation and tests. A plain string, not an enum, for
  the same reason `grip` is: the module has no `enum` import and pyright must stay
  clean. Renamed from the first draft's `root` / `chord` / `passing` / `approach`
  so that "target" is not used for both the left hand's role and the bass's.
- `bass_only: bool = False` — the step exists for the thumb and **nothing above it
  strikes** (decision B). This is the opposite of `repeated`, not a variant of it:
  `repeated` marks a melody that *is* re-articulated (the soprano strikes, the inner
  voices are held), where `bass_only` marks a slot the melody grid did not have, so
  the upper voices are held across it. Setting one never sets the other, and an `NC`
  step is never marked either.

`Voicing`, two defaulted fields after `role`:

- `bass_midi: Optional[int] = None` — set **only after** `_best_voicing` runs. Its
  presence is what tells `tabstaff` to exclude the bass string from the `collapse`
  comparison.
- `bass_string: Optional[int] = None` — which string actually carries it, since
  that is per note and not a constant. The `collapse` fix reads this rather than
  assuming index 0, so it stays correct when the thumb moves to the 5th string.

`BASS_STRING_INDICES: Tuple[int, ...] = (0, 1, 2)` and the bass role constants,
module level.

`BassNote` — the pass's own record, one per **walked beat**: `(bar, beat, pitch_class,
role)`. It carries no octave and no string, deliberately: neither can be decided before
the upper voicing exists, which is the reason the pass returns a pitch *class* at all.
It is what decision B's extra steps are built from.

No new grip family, so `GRIP_STRING_SETS`, `supported_string_sets()` and
`GRIP_MAX_SPAN` are untouched, and the existing grip sweep does not need extending.

## The invariant amendment (must be explicit)

*"The sounding strings are exactly one `supported_string_sets()` entry"*
**cannot hold** for a bass step: merging a thumb turns a 5-4-3 shell `(1,2,3)`
into `{0,1,2,3}`, or a 6-4-3 shell `(0,2,3)` into `{0,1,2,3}` — neither of which
is a supported set. `TestStringSetTable` and the `test_wjazzd.py` sweep would fail.

Precedent already exists: melody-only `NC` steps are explicitly not harmonised
voicings and are exempt (see CORPUS_PLAN.md). So, in the same spirit:

> For a step carrying a bass, the invariant applies to the **upper voices**: they
> must be exactly one `supported_string_sets()` entry with the melody on its
> soprano, **and** exactly one string in `BASS_STRING_INDICES` outside that set
> carries the bass. The combined set is deliberately not itself a supported set.

Two further conditions the bass must satisfy, both consequences of letting it
change strings:

- **The bass note must sound below the upper structure.** This is a **filter, not
  a tie-break**, and it exists because the tuning is not monotonic in the useful
  direction: the A string is five semitones *above* the D string it may neighbour,
  and a 5-3-2 shell's A-string note can sound below its G-string note. So a bass
  candidate that would place the thumb *above* a voice it is meant to support is
  rejected outright, on either string. An earlier draft made this the primary sort
  key, which was wrong — string index and sounding order disagree, and sounding
  order is the one that has to win.
- **Reach and sounding order are separate tests, and both are required.**
  `note_to_fret` returning a valid fret says the pitch is playable; it says
  nothing about whether the resulting note is under the chord.
- **A fill is exempt in the upper voices**, exactly as an `NC` step is: under
  decision C a fill is the melody alone, so there is no `supported_string_sets()`
  entry to be a member of, and the bass rule above (one `BASS_STRING_INDICES` string
  below the melody) is the only part that applies. Same for a target that fell back
  to melody-alone because no shell could sound it.

`fret_span()` is unaffected — the thumb shares the shell's position budget, which
is the point of the texture, and placing it by proximity to `hand_fret` is what
keeps that true. `partial` must count **upper voices only**, so a shell plus a
thumb is still annotated `(shell - 3rd & 7th, partial)`.

## The bass line: beat 1 is the anchor, beat 4 is the target

One pure, phrase-level pass. It cannot be per-step, because a walking line is
defined *between* two anchors:

```python
def _walking_bass_line(
    chords: List[Tuple[Optional[str], str, str]],          # (root, quality, name) per slot
    onsets: Optional[List[Optional[Tuple[int, float]]]],  # each slot's (bar, beat), or None
    beats_per_bar: int,
) -> List[BassNote]:   # (bar, beat, pitch CLASS, role) - one entry per WALKED BEAT
```

**One entry per walked beat, not one per slot** (decision B). The line is keyed on
onsets, so a bar whose melody is a single whole note still yields four bass notes, and
`arrange_progression` unions those onsets with the melody slots *before* the melody loop
runs. The pass still reads harmony only: it needs the onsets to know which beats exist,
never the melody pitches to know what they are. With `onsets=None` — `timings=None`, or a
`chords` skeleton — there is no beat grid, so it degrades to one note per slot.

**It returns a pitch class, not a pitch, and that is load-bearing.** The octave
cannot be chosen here, because this pass runs *before* the melody loop and so
before `hand_fret` exists. A descending `C4-B3-A3-G3` over a held Dm7 is a
beautiful walk and completely unplayable under a shell at fret 5, because C4 on
the 5th string is fret 15 — ten frets above the fingers. The same line an octave
down is not. Only the placement step knows the hand position, so **octave and
string are resolved together there**, and this pass decides *what note*, purely
from the harmony. This is the split the library already draws for the melody: the
pitch is musical, the string and position are physical, and they are not decided
in the same place.

**The governing rule: beat 1 is the anchor, beat 4 is the target.** A walking
line does two jobs — it marks time and it bridges one chord to the next — and
those fall on predictable beats:

- **Beat 1 of every bar is the anchor**, and it is the current chord's **root**.
  Not a chord tone that happens to be convenient: the root. This is the same rule
  the library already states for a single note in `BASS_DEGREES_6432`, where the
  lowest voice may take only a root or a 5th because "the lowest voice is what
  *defines* the chord". Here it is generalised from one note to the whole downbeat.

  **A mid-bar change anchors too** (decided: **decision E**). Bar 10 of the B section
  moves `Bbm7 -> Eb7` on beat 3 and the guide's thumb states the new root `Eb` there.
  The rule therefore reads "the first slot of any harmony group that begins on a strong
  beat" — the same predicate `_roles_for_slot` already applies to the left hand, reused
  rather than reinvented, so the thumb and the left hand fire on the same slot by
  construction. See **Break 5** for the evidence.
- **Beat 4 is the target**: a note chosen to lead into the next bar's anchor.
- **Beats 2 and 3 connect** — chord tones, extensions, or passing motion.

**Beat 4 is chosen backwards from the next anchor, not forwards.** Pick the next
root, then work back to a note that reaches it by a half step above, a half step
below, or a fourth below / fifth above. This is why the pass is phrase-level and
why the generator cannot be per-step: beat 4 is *defined* by a note that has not
happened yet. It is the strongest argument for the whole pure-pass design, and
the plan should say so rather than leaving the lookahead incidental.

**Consequences for the anchor rule.** A chord lasting two bars is re-anchored on
each downbeat, because the anchor is a *metric* event, not a harmonic one. That is
the opposite of the left hand, which states a held chord once (see the role rule
above) — and the two run on different rhythms, which is the texture. It also means
the earlier note in this file, that a two-bar chord must not re-anchor the thumb,
was **wrong**: re-striking the root is what marks the bar, and suppressing it
would leave the second bar unmarked.

### Bass roles

Renamed from the first draft's `root` / `chord` / `passing` / `approach` / `hold`,
because "target" now means two different things in this document — the *left*
hand's `ROLE_TARGET` and the *bass*'s beat 4 — and one word cannot carry both:

| role | beat | what it is |
|---|---|---|
| `anchor` | 1, or a strong beat where the harmony changes | the current chord's root, always |
| `connect` | 2, 3 | a chord tone, an extension, or passing motion |
| `approach` | 4 | a half step from the next anchor |
| `enclosure` | 3 or 4 | half step above, then half step below the next anchor |
| `hold` | any | the previous note repeated, when nothing better is reachable |

### The cost is role-conditional, and this is the substantive rule

An earlier draft made `out-of-chord tones` the **first** criterion of `bass_cost`,
unconditionally. Checked against a canonical line, that is wrong: **two thirds of
the notes in a textbook walk are not chord tones of the chord they sit under.**

| line | note | under | a chord tone? |
|---|---|---|---|
| D E F A♭ | E | Dm7 `(0,3,7,10)` | no — the 9th |
| D E F A♭ | A♭ | Dm7 | no — the ♭9, a chromatic approach |
| G A B♭ B | A | 7 `(0,4,7,10)` | no — the 9th |
| G A B♭ B | B♭ | 7 | no — the ♭13 |
| C B A G | A | maj7 `(0,4,7,11)` | no — the 13th |

A purity-first cost would rank every one of those last and return the arpeggio the
guide explicitly warns against ("pure arpeggios can sound like exercise drills").
Being outside the chord is, for a connective note, frequently the point.

So purity is a **hard filter for `anchor` and a tie-break for everything else**:

```
anchor:    (not the root, ...)                          # hard filter
connect:   (out-of-chord, semitones from previous,       # tie-break only
            pitch-class motion, role preference)
approach:  (distance to the next anchor, semitones from previous, ...)
```

**Extensions come from the table that already exists.** Every non-chord tone above
is an extension the library can already name, via
`VoiceLeadingEngine.NON_CHORD_TONE_EXTENSIONS`: `m7 → m9` for E over Dm7,
`7 → 9` for A over G7, `7 → 7b13` for B♭ over G7. The vocabulary is there and
reachable; the bass was simply never wired to it. The `anchor` role is the only
one that may not use an extension, because the anchor is the root by definition.

**This is what keeps the no-key-model claim true.** The "diatonic scale movement"
in a real line — G→A→B♭, A→B♭→B — looks like it needs a key. It does not: those
notes are extensions of the *current* chord (A is the 9th of G7, B♭ its ♭13), and
the one genuinely chromatic note, B→C, is exactly the root-relative approach
already generated. Strip extensions out, as the purity-first cost did, and
diatonic movement becomes unreachable — at which point a key model really would be
necessary. **The two claims are linked, and admitting extensions is what keeps the
key out.** An earlier draft also warned against `_interval_offsets`' hardcoded
major-scale fallback; that warning stands, and it is the reason to reach for
`NON_CHORD_TONE_EXTENSIONS` rather than for a scale.

Three properties, each forced by something:

- **The bass and the left hand run on different rhythms.** The thumb marks every
  downbeat; the left hand states a chord only where its own role rule says. That
  is the texture, and it is why the two-bar case is *not* a shared decision (see
  the anchor rule above: the thumb re-anchors, the left hand does not).
- **No key model, by construction** — for the reason given above: extensions and
  root-relative approaches cover the vocabulary, and reaching for
  `NON_CHORD_TONE_EXTENSIONS` rather than a scale is what keeps it that way.
- **Rhythm needs no new timing model, but it does change the step list.** Beats 1-4
  are already in the grid, so the bass attaches to the onset whose beat matches — and
  where the beat grid has an onset the melody grid does not, that onset becomes a
  **bass-only step** (decision B). The union is built *before* the melody loop, each
  extra slot carrying the previous melody pitch, so the loop's index still matches the
  skeleton `arrange_head` handed it and the guarded attach keeps meaning what it
  meant. `arrange_progression` can therefore return more steps than the progression it
  was given; that is the one contract this texture changes, and it is what the
  renderers must be checked against.

**Which harmony the bass reads.** Every role is chosen against the harmony that
*actually sounds* — `harmonized_as` when a strategy substituted, not the written
`chord` — so the anchor under a substituted chord is the substituted chord's root.
An unparseable quality returns `None` and is counted, never guessed (the rule
`WEIMAR_QUALITY_ALIASES` and `MUSICXML_KIND_QUALITIES` already follow). An `NC`
bar continues the last known harmony or rests; it is never given a guessed one.

**Selection** is a lexicographic tuple, never a weighted sum, matching the house
rule that `voicing_cost` states why it must be. It is **role-conditional** — the
form is given in the cost section above, and the point that matters here is that
the tuple is *built per role* rather than shared. `min` over a stable list, so the
walk is deterministic like the rest of the engine.

Note what is **not** in this tuple: anything about the hand, the octave or the
string. All three are physical and are decided in the placement step, because this
pass runs before the upper voicing exists and cannot know any of them. An earlier
draft carried a "distance from the ideal octave of the previous note" term here,
which quietly re-decided the octave in the wrong place — a descending line would
have committed to C4 before anything knew the hand was at fret 5.

## The `collapse` fix is mandatory

`tabstaff._staff_columns` decides hold-vs-strike from
`tuple(sorted(step.voicing.midi_notes()))`. A walking bass changes the lowest
pitch every quarter, so the `held` chain breaks permanently and the 0.7.0
"held shape, not a chord list" behaviour is destroyed for the whole arrangement.

One line in the shared core: exclude `step.voicing.bass_string` from that
comparison when `bass_midi is not None`. Reading the **recorded string** rather
than a constant is what keeps this correct once the thumb is allowed onto the 5th
string. Because ASCII and HTML both go through `_staff_columns`, they cannot
drift, and `TestTabstaffModuleBoundary` already guards that sharing.

**Two rendering rules, and they are opposites.** A `repeated` step blanks the **upper
inner voices** but **still strikes the bass** — the bass is a moving voice, not a held
one. A `bass_only` step (decision B) strikes **only** the bass and leaves every string
above it alone: the upper voices are held from the previous strike, and the melody is not
re-attacked. It is the second rule that makes the example's bar 1 legible — one melody
strike, four bass notes — and it is why `bass_only` is a separate field rather than a
reuse of `repeated`.

The earlier draft's test "no bass movement when the melody is repeated and the
chord is unchanged" is **dropped**: a walking line moves regardless, and there is
no such case.

## Integration order in `arrange_progression`

1. Validate `texture` against `TEXTURE_STYLES` and raise `ValueError` **before
   any voicing work** — the existing check, extended.
2. Precompute the bass line when `texture == "walking_bass"`, over the **walked
   beats** rather than over the slots (decision B). It yields a **pitch class**, not
   a pitch and not a string: the octave and the string both depend on the upper
   voicing, which does not exist yet.
3. **Union the onsets before the loop.** Every walked beat with no melody slot
   becomes an extra slot carrying the *previous* melody pitch, to be marked
   `bass_only`. The loop then runs over the union, so its index still matches the
   skeleton it was given and the guarded attach below stays index-aligned. This is
   the only place the step list grows.
4. Run the melody loop **unchanged** — no edit to candidate generation,
   `prepare_step`, `_best_voicing`, the non-chord-tone strategies, the
   octave-down rescue, or `repeated`.
5. **The empty fill tuple is a branch, not a failure** (decision C). A
   `walking_bass` **fill** is voiced through the melody-alone path
   (`get_melody_only_voicing`) rather than through grip lookup, and the generic
   "a fill that cannot be filled becomes a target" fallback is skipped for this
   texture. A **target** whose `("shell",)` yields nothing takes the same
   melody-alone route rather than disappearing with a warning.
6. Attach `bass` / `bass_role` / `bass_only` by guarded index (never trusting it, as
   `arrange_head` already guards timings).
7. **After** selection, resolve octave and string together. For each candidate
   octave of the pitch class (the one the previous bass note implies, and the one
   an octave away) crossed with each index in `BASS_STRING_INDICES`, skip it if
   the string already sounds, if the pitch is unreachable in `0..18`, or if its
   note would not sound below the upper structure. Of the survivors take the
   **`min` by `abs(fret - hand_fret)`**, breaking a tie toward the previous bass
   note's octave and then toward the lower sounding pitch. Write that fret, and
   set `bass_midi` and `bass_string`. With no survivor, leave the step without a
   bass and report it.

   Two consequences worth stating. The bass is placed by a rule that *reads* the
   upper voicing rather than following a string order, which is what lets one line
   move between strings as the left hand moves up the neck. And because the
   octave is a choice made here, **it has failure modes** — a descending line can
   run out of board below the A string's open A2, and the tie-break decides
   whether it climbs or drops. That is a decision with consequences, not a
   derivation, and Phase 3 should say what the tie-break does.
8. Fix `partial` to count upper voices only, and leave it off a melody-alone fill
   (there are no upper voices to be partial).

`wjazzd.arrange_slots` and `headxml.arrange_xml_head` keep the default texture,
so the corpus and head CLIs are unchanged. `--texture walking_bass` is a one-line
addition in the style of `--texture targets`.

## Rendering

- **ASCII / HTML:** the `_staff_columns` fix only, plus the `repeated`-plus-bass and
  `bass_only` cell behaviours. Because the bass is excluded from the hold comparison,
  a run of `bass_only` steps draws as *one held upper shape with a moving thumb* — the
  example's bar 1 — with no further change to the shared core.
- **Annotation:** extend the shared `_step_annotation()` with the bass role and the
  motion — `(bass: Ab > G, approach)` alongside the existing `partial` text, so
  `format_progression` and the staff cannot disagree. The role is worth printing
  because the thumb line is no longer uniformly chord tones, and a reader counting
  strings would otherwise wonder why the bass is not playing the chord.
  `format_tab_staff` has no
  annotation channel — its guarantee remains "it draws what sounds", exactly as
  today.
- **GP5: free.** `_sounding_frets` reads `frets`, and `Voice` already carries a
  string per note. This is the concrete payoff of keeping the bass in the fret
  vector.
- **MusicXML: its own later phase.** A five-note chord needs a second staff or
  voice and `_build_part` assumes one. Named explicitly, not "follow-up".

## Worked example (schematic)

Bar 4/4, `Dm7` for beats 1-4, `G7` from the 4-and. Pitch classes and roles only —
exact fingerings get pinned by Phase 3 tests rather than asserted here.

| beat | slot | chord | left hand | thumb | why |
|---|---|---|---|---|---|
| 1 | 1 | Dm7 | **shell** (F, C) | D | `anchor` — the root |
| 2 | 2 | Dm7 | duo / interval | E | `connect` — 9th of Dm7, an extension |
| 3 | 3 | Dm7 | *fill* (no change since the last target) | F | `connect` — 3rd |
| 4 | 4 | Dm7 | duo / interval | A♭ | `approach` — half step down to G |
| 4& | 5 | **G7** | duo / interval under **G7** | B | `connect` — 3rd, leads to C |
| next 1 | 6 | G7 | **shell** (B, F) | G | `anchor` — the root |

Note how many thumb notes are **not** chord tones: E is the 9th of Dm7 and A♭ is
its ♭9. Under the purity-first cost this document previously described, both would
have been rejected in favour of an arpeggio. The left hand states a held Dm7 once,
at beat 1; the thumb re-anchors and re-targets — the two rhythms are independent,
which is the texture.

### Why the octave has to be a decision: Dm7's four tones over four beats

The obvious idea is to walk the chord tones — D, F, A, C — one per beat. On the
5th string alone that is **fret 5, 8, 12, 15**: a ten-fret span, and one hand
position is about five. So the line cannot be one position, and this is a *span*
problem rather than a string problem. The tones across all three candidate
strings:

| tone | 6th | 5th | 4th |
|---|---|---|---|
| C3 | 8 | 3 | — |
| D3 | 10 | **5** | 0 |
| F3 | 13 | 8 | 3 |
| A2 | 5 | 0 | — |
| A3 | 17 | 12 | 7 |
| C4 | 20 ✗ | 15 | 10 |

Three things follow, and each is a case the code has to get right:

- **The octave is the whole game.** `C4` is fret 15 and `C3` is fret 3 on the
  5th string — twelve frets apart for one note. Under a shell at fret 5, C4 puts
  the thumb ten frets above the fingers, which is not one hand. C3 does not. The
  generator cannot know which, which is why it returns a pitch class.
- **The 4th string plays G3 at fret 5 where the 5th needs fret 10** — the same
  pitch, five frets closer to the nut. That is the whole argument for carrying it
  as a candidate, and it is why proximity ordering rather than string order is the
  rule.
- **A descending line can run out of board.** `C4-B3-A3-G3` is a lovely descent at
  frets 15-14-12-10 on the 5th, but dropped an octave it wants B2 and A2, and A2
  is the 5th string's open pitch — below it there is nothing. The tie-break has to
  decide whether the line climbs back or drops to the low E, and either answer is
  defensible, which is exactly why it should be measured rather than assumed.

## Does the plan survive the applied example?

The guide's worked arrangement — the first 8 bars of "But Not For Me" in F, split
into melody / inner shell / walking bass — is the plan's real test. It confirms
most of the design, and it breaks three things. One is now resolved and two remain
as **open decisions**, stated here rather than as settled design, because they
change the shape of the work and should be answered before Phase 1.

The same tune's second eight bars were supplied afterwards and are the harder test,
because the melody stops being a held note and becomes a line. They are assessed at
*The B section (bars 9-16)* below; they confirm the same texture and add three more
decisions (D, E and F).

### What it confirms

**The fret-proximity rule reproduces its exact string choices.** Bar 1 has the
hand at frets 7-9, and the bass is F, E, F, C♯:

| note | 6th string | 5th string | proximity picks |
|---|---|---|---|
| F | 1 | 8 | **5th @ 8** — distance 0 |
| E | — | 7 | **5th @ 7** — distance 0 |
| C♯ | 9 | 14 | **6th @ 9** — distance 0 |

That is F→E→F on the 5th string then a jump to the 6th for C♯, which is exactly
the published tab, and exactly for the reason the proximity rule argues. Under
the low-E-first ordering this bar would have read `1-?-?-9` with the hand
travelling five frets for notes the 5th string plays in place. **The rule earns
its keep on the one worked example available.**

**The anchor rule holds throughout.** Beat 1 is the root in all eight bars:
F, F, G, C, F, D, G, C.

**The shell is genuinely 3rd + 7th.** Bar 1 gives A and E under Fmaj7, bar 4
gives B♭ and E under C7 — matching the guide's own performance notes.

**`hold` earns its slot.** Bar 6's bass is D, D, C, B♭: a repeated note on beats
1 and 2, which is exactly the `hold` role.

### Break 1: the shell string set did not exist in this library

Bar 1 sounds on **high E, G and D** — the B string is skipped entirely, i.e.
`{5, 3, 2}` in string indices.

`GRIP_STRING_SETS["shell"]` currently holds `(5,4,3)`, `(4,3,2)`, `(1,2,3)`,
`(0,2,3)` and `(1,3,4)`. **`{5,3,2}` is not among them**, so the engine cannot
generate this shape at all.

That is not a cosmetic gap. `{5,3,2}` is the set that leaves **both the 5th and
6th strings free** — it is the three-layer split the guide describes, and it is
the only shell in the neighbourhood that hands both bass strings to the thumb
without contest. Add it and the texture has a native home; leave it out and the
example is approximated with a different shell whose bass strings are then
argued over by the placement step.

### Resolved: the shell string set is added, as a general gap

> **Open decision A — decided: add `(5,3,2)` to `GRIP_STRING_SETS["shell"]`, with
> soprano 5.** It is a general improvement to the shell family, not a
> walking-bass workaround, and it is wanted for the same reason the guide's example
> happens to want it.

**The general argument is an asymmetry in the table.** Counting the shell sets by
soprano:

| soprano | sets today | count |
|---|---|---|
| 5 (high E) | `(5,4,3)` | **1** |
| 4 (B) | `(4,3,2)`, `(1,3,4)` | 2 |
| 3 (G) | `(1,2,3)`, `(0,2,3)` | 2 |

The high E is the *most* used soprano — `MELODY_STRING_CHOICES_FULL = (5, 4, 3)`
puts it first, and every arrangement tries it before the others — and it is the
*least* served, with a single shape. `(5,3,2)` removes that asymmetry, and the
selector gains the second option for the commonest case rather than for the
hardest.

**The implementation is a one-line table change, which was not obvious.** The plan
assumed a new set would need a `_place_shell` search written for it. It does not:
`_place_shell` already takes `strings` and searches generically, and
`_string_sets_for` rotates each set so the melody lands on its own soprano
regardless of the order the table lists it in. So:

- `_place_shell` — **no change**. It is generic over the set.
- `supported_string_sets()` — **no change**. It derives from `GRIP_STRING_SETS`.
- `GRIP_MAX_SPAN` — **no change**. `shell` is already 5, and the span is checked on
  the frets actually placed.
- `GRIP_STRING_SETS["shell"]` — **one entry added**: `((5, 3, 2), 5)`.

It is the third non-contiguous set, joining `6-4-3` and `5-3-2`, and it skips the
B string *going up* — like `6-4-3` but at the top of the neck rather than the
bottom. `_place_shell`'s docstring already explains why a non-contiguous set needs
the search rather than stacking, so the reasoning is written down.

**But this is a behaviour change, and cannot ride along with the "provably inert"
Phase 1.** Adding a shell set adds a *candidate* to every `uniform` and `targets`
arrangement, because `shell` is in `GRIP_PREFERENCE` and in the `targets` fill
tuple. All shells cost the same on `missing` (3 notes, so `4 - 3 = 1`), so the new
candidate is decided by the window penalty, position and movement terms — any of
which it can win. Many existing tests assert exact tab strings, so **some of them
may legitimately change**, and the honest thing is to measure that rather than
assert it either way. It therefore gets its own phase, between the types and the
integration, with the compatibility sweep as its deliverable.

**Expect relocation, not coverage.** The comment on `5-3-2` records that it "adds no
coverage at all — never the only shape for a melody — but relocates 1.3% of
steps, always onto a better melodic position". `(5,3,2)` may behave the same way.
That is a fine outcome, but it should be **measured and reported**, not assumed in
either direction.


### Break 2: the model is melody-primary, and this texture is bass-primary

Bar 1's melody is a **whole note**, struck once and held. The bass plays **four
notes** underneath it.

Our slots are melody-driven, and this plan's first draft stated that the bass does
**not** invent extra steps. So under a sparse skeleton — `chords`, or `timings=None` —
there is one slot for the bar and therefore one place to put four bass notes: the
stated degradation ("one bass note per anchor") removes the texture from exactly the
bars this example is made of.

The `eighths` skeleton appears to hide it, by subdividing a whole note into eight slots
— but it does not, quite. Those seven extra slots are slots where the melody does not
change, and under the draft's own rules each of them still *struck*: `repeated` forced a
soprano attack, and the fill tuple put a duo under it. The skeleton has the onsets the
walk needs; what it lacks is any way to say "this slot exists for the thumb". Decision B
is that way, which is why the eighth-note case is not a solution by itself.

> **Open decision B — decided: bass-only steps.** A step may carry a bass and no
> melody change, so the bass grid is allowed to be finer than the melody grid.
> Stated once, the consequence is: **the step list is the union of the melody slots
> and the walked beats**, so `arrange_progression` returns more steps than the
> progression it was given whenever the beat grid has an onset the melody does not.
>
> Three things follow, and they are the work this decision creates:
>
> - **The union is built before the melody loop**, not spliced in afterwards. Each
>   extra slot carries the *previous* melody pitch, so the loop stays index-aligned
>   with the skeleton it was given and `arrange_head`'s guard — and `arrange_slots`'
>   `retry` index — still mean what they mean. Returning a longer list *from* the
>   loop would break the one invariant the corpus path depends on.
> - **The extra slots need their own marker, because `repeated` means the opposite.**
>   `repeated` says the melody is genuinely re-articulated: the soprano strikes and
>   the inner voices are held. A bass-only step says nothing above the thumb strikes
>   at all, so it is its own defaulted field (`bass_only: bool = False`, Phase 1) and
>   the renderers branch on it.
> - **It is why the `collapse` fix is mandatory rather than tidy.** Excluding the
>   bass from the hold comparison makes consecutive bass-only steps *held* for the
>   upper voices, which is what the example shows: bar 1's whole note is struck once
>   while the thumb walks under it. That is also the answer to the `repeated` wart
>   noted below — in this texture the melody is no longer attacked on every slot.
>
> The `chords` skeleton still has no beat grid to union with, so the degradation
> there ("one bass note per anchor") stands. What changes is that it is now only the
> *gridless* case, not the sparse one.

### Break 3: the left hand goes silent between targets

The example strikes the shell **once per chord and stops** — beats 2, 3 and 4 are
thumb alone. This plan's first draft gave the fill tuple `("duo", "interval", "melody")`,
which puts notes under the passing melody, and `collapse` will not suppress them because
a duo's pitches differ from the shell's: every fill strikes.

> **Open decision C — decided: a fill is the melody alone.** The left hand plays *no*
> notes on a fill; the melody note sounds by itself, which is what the guide's own
> example does (beats 2, 3 and 4 of bar 1 are the thumb and nothing else).
>
> Two mechanical consequences, small but neither optional:
>
> - **The fill tuple is empty (`()`), and the role rule resolves it through
>   `get_melody_only_voicing`** rather than through grip lookup. An empty tuple in
>   `TEXTURE_GRIPS` therefore needs one explicit branch in `arrange_progression` —
>   the path an `NC` step already takes — because the generic code would read "no
>   candidates" as a failure and fall back, which is the opposite of the intent.
> - **"A fill that cannot be filled becomes a target" is disabled for this texture,
>   and inverted.** A *target* that cannot be a shell — the bar-10 `D` over `Bbm7` —
>   falls back to melody-alone instead. "Nothing under the passing note" is the
>   intent here, so a fallback that promotes a fill to a target would undo the
>   texture one step at a time.
>
> The `"melody"` token is therefore dropped from the `walking_bass` tuples rather
> than wired: the mechanism it was reaching for is now the fill rule itself.

### One correction, and one divergence

**Corrected: `SHELL_DEGREES` is a minimum, not a fixed pair.** An earlier draft of
this section claimed bar 5 (Fmaj7, melody A) would be voiced with an `A` doubled
under the melody, because the table is `(4, 11)` for `maj7`. That was a misreading
of `_place_shell`. The table's pair is a **subset requirement** (`needed <= pcs`) and
`pcs` is computed from the three placed strings *including the melody*. When the
melody is already one of the guide tones, only the other one is additionally
required, and the third voice is any chord tone the search's ranking prefers. So
Fmaj7 under `A4` gives `x-x-2-5-x-5` — `C4` and `E3`, the 5th and the 7th, the
example's own shape — with no new code and no per-melody table. The claim that
varying the shell pair needs an extension is withdrawn; the search already does it.

**The altered non-chord tones are not in the extension table.** `maj7` routes only
degrees 2, 6 and 9 (9th, #11, 6/9) and `m7` only degree 2 (the 9th), so C♯ over Fmaj7
(degree 8 — its ♯5/♭13, not a ♭9, and the `8` in the earlier draft of this bullet was
the wrong reason for the right conclusion) and G♯ over Gm7 (degree 1, the ♭9) have no
route, and under the plan's own rule they are unreachable. Separately, bar 1-2's C♯ sits
under a chord that **does not change** (Fmaj7 → Fmaj7), so unlike every other bar
it approaches nothing and has no harmonic function; that reads as a slip in the
example, and it means bar 1's line cannot be reproduced as written.

### The B section (bars 9-16): the same texture, three new breaks

The second half of the same tune is the harder half, because the melody stops being
a held note and becomes a **line**: `D-Db-C-Bb`, then `A-G-F-E`, then back up, over
`Bbmaj7 | Bbm7-Eb7 | Fmaj7 | Dm7 | G7 | G7 | Gm7 | C7`.

**Read the source with care.** The excerpt's tab is loose in a way that matters, and
three of its bars disagree with themselves:

| bar | what it says |
|---|---|
| 9 | the prose describes the shell as "A (3rd) and D/F" — the 3rd and 7th; the tab shows `F4` and `Bb3`, the 5th and the root |
| 10 | the note-name row reads `Bb Bb Eb Eb`; the fret row is four identical `Bb2`s at fret 6 of the low E |
| 12, 16 | the fret rows omit the beat-1 root the note-name row states (`D` and `C`) |

So this analysis reads the **note-name rows as authoritative for the bass**, treats
the fret columns as approximate, and where the prose and the tab disagree it follows
the prose — which in bar 9 is what the engine's own invariant would force anyway.

#### What the B section confirms

1. **The `(5,3,2)` split is the tune's texture, not bar 1's.** Every one of the B
   section's eight bars puts the melody on the high E and the guide tones on the G and
   D strings — the same split the A section's bar 1 uses — so decision A is supported
   by the tune's second half as well as by its first bar. The B section is also the
   stronger test of it: bars 15 and 16 put the melody on `F4` (high-E fret 1) and `E4`
   (fret 0), the floor of the string, and the shells still land at a spread of 2 and 3.
2. **The anchor rule holds in all eight of its bars** — `Bbmaj7->Bb`, `Bbm7->Bb`,
   `Fmaj7->F`, `Dm7->D`, `G7->G`, `G7->G`, `Gm7->G`, `C7->C` — on top of the A
   section's 8 of 8: sixteen downbeats, sixteen roots.
3. **The D string carries no bass note in any of the B section's eight bars.** Under a
   `(5,3,2)` shell it *is* the shell's lowest voice, so "skip a string that already
   sounds" is what keeps the thumb off it. `BASS_STRING_INDICES`'s third entry is
   therefore dead in this texture; it is the `(5,4,3)` and `(1,3,4)` shells that keep
   it worth carrying at all.
4. **The placement rule reproduces the published string choices.** Bar 9, whose upper
   voicing sits at `avg_fret` 8, recomputed from the tuning:

   | note | chosen site | distance | the tab |
   |---|---|---|---|
   | `Bb2` | 6th @ 6 | 2 | 6th @ 6 ✓ (`Bb3` on the 4th is nearer, but the 4th sounds and it is not below the shell's `A3`) |
   | `F3` | 5th @ 8 | 0 | 5th @ 8 ✓ |
   | `G3` | 5th @ 10 | 2 | 5th @ 10 ✓ (`G3` on the 4th would be distance 3, and the 4th sounds) |
   | `C#3` | 6th @ 9 | 1 | 6th @ 9 ✓ |

   All four match, with each of the amendment's three filters doing real work on the
   way. Bar 11's `E` is the cleanest illustration of the sounding-order rule: `E3` on
   the 5th at fret 7 is nearer the hand than `E2` on the 6th at fret 0 and is rejected
   because the shell's lowest note *is* an `E3`, so the thumb drops to the low E and
   matches the tab.
5. **`_place_shell` already returns the published shells, unchanged.** G7 under `D5`
   comes out `x-x-9-10-x-10` (`D5`, `F4`, `B3`) at a spread of 1 — exactly bars 13
   and 14. Dm7 under `A4` comes out `x-x-3-5-x-5` — exactly bar 12. Fmaj7 under `A4`
   comes out `x-x-2-5-x-5` — exactly bar 11. Gm7 under `F4` and C7 under `E4` match
   bars 15 and 16 as well, so six of the eight B-section shells need no new code.
6. **Bar 9's tab is not generatable, and the guide's prose is.** A shell requires
   *both* guide tones to sound (`needed <= pcs`, the melody's own pitch class
   included). Under `Bbmaj7` with `D5` on top, `(4, 11)` needs a `D` and an `A`; the
   melody is the `D`, so an `A` must sound underneath. The tab's `F4 + Bb3` contains
   no `A` and fails outright; the prose's `A` and `D` pass. The engine returns
   `x-x-7-7-x-10` — the 3rd doubled, the 7th present — which is the guide's own
   description of its own bar.

#### Break 4: beat 4 does not consistently approach the next *root*

This is the first place the B section contradicts the plan, and the guide's own words
are the evidence. Its performance note on bar 16 says the line "leads straight into
the **A2 section target note** (C on beat 1 of bar 17)" — a bass `B2` resolving a
semitone up to the next bar's **melody**, not to its root. Under our rule
(`approach` = a half step above, a half step below, or a fourth below / fifth above
**the next anchor**) that `B2` is wrong unless bar 17's root happens to sit beside it.

Note by note, the B section's beat-4 notes are not a consistent approach to the next
root at all:

| bar | beat 4 | next root | interval |
|---|---|---|---|
| 9 | `C#3` | `Bb2` | a major 2nd |
| 11 | `E2` | `D3` | a major 2nd |
| 12 | `A2` | `G2` | a major 2nd |
| 13 | `E2` | `G2` | a minor 3rd |
| 14 | `F#3` | `G2` | **a semitone ✓** |
| 15 | `G#2` | `C3` | a major 3rd |
| 16 | `B2` | — | a semitone to bar 17's *melody* `C` |

One of seven, and the A section is no better — bar 1's `C#` approaches nothing at all
under an unchanged `Fmaj7`, which this file already records. So the examples
illustrate the *shape* of the rule (a note at the end of the bar chosen to lead into
the next) and obey it only where it suits the line.

It is worse than "a different note gets chosen". The plan's contract for a connective
note is that it is a chord tone, an extension `NON_CHORD_TONE_EXTENSIONS` can name, or
a root-relative approach — and checked against that vocabulary only four of the seven
are reachable at all: the 7th of `Fmaj7`, the 5th of `Dm7`, the 13th of `G7` (degree 9,
and the `7` row has it), and `F#` as a half step below the next root. The other three
— `C#` over `Bbmaj7` (degree 3), `G#` over `Gm7` (degree 1) and `B` over `C7` (degree
11) — have no table route and no root-relative approach to be read as, so they are
outside the vocabulary entirely. The fixture therefore cannot assert the published
line even if decision D widened the role rule; it asserts the rule, and those notes are
recorded as expected divergences.

> **Open decision D — decided: beat 4 approaches the next anchor, and the published
> lines are recorded as divergences.** The rule stays "a half step above, a half step
> below, or a fourth below / fifth above the next bar's **root**", because it is the
> only version that can be stated and tested in a line: bar N's beat 4 is a named
> interval from bar N+1's beat 1.
>
> The melody-target reading — the guide's own performance note on bar 16 — is **kept
> on record as the measured alternative** rather than dropped: it reproduces bars 16
> and bar 1 and is the guide's stated intent, but it is undefined wherever the melody
> does not move on the downbeat (a whole note across the bar line, which is the A
> section's bar 1), so it cannot be the rule. Three of the seven beat-4 notes in the
> B section are outside the vocabulary either way, so the fixture asserts the rule and
> those notes are expected divergences.

#### Break 5: a change on beat 3 needs an anchor, and the rule only speaks of beat 1

Bar 10 is **two chords in one bar**: `Bbm7` for two beats and `Eb7` from beat 3, under
the melody `D-Db-C-Bb`. The guide's bass row reads `Bb Bb Eb Eb` — the new chord's
**root stated on beat 3**.

Our rules have no slot for it. "Beat 1 of every bar is the anchor" says nothing about a
chord arriving mid-bar, and the role table's `connect` (beats 2 and 3) is a chord tone
with no obligation to be the root. Beat 3 is already a **left-hand** target
(`TARGET_BEATS = (1, 3)` includes it), so the left hand would state `Eb7` there while
the thumb, on the letter of the rule, was still walking through `Bbm7` — the two hands
disagreeing about which chord is sounding, which is the one thing this texture must
never do.

> **Open decision E — decided: the anchor generalises to the first slot of any harmony
> group that begins on a strong beat.** Beat 1 of every bar, plus any strong beat where
> the harmony changes — bar 10's beat 3, and any subdivided-metre change that lands on
> a strong beat. It is one comparison and it already exists: `_roles_for_slot` tests
> `_metric_weight > 0` and the normalised harmony differing from the previous target's,
> so reusing that predicate is what makes the thumb's anchor and the left hand's target
> fire on exactly the slot where the harmony moves, with no second mechanism to keep
> in step.
>
> The alternative — anchors on beat 1 only, the mid-bar root arriving as a `connect`
> that happens to be the root — is smaller but leaves the two hands' agreement a
> coincidence rather than a rule.

#### Break 6: the second bar of a held chord is where the plan and the example part

Bars 13 and 14 are two bars of one `G7`, and the guide **restates the shell on both
downbeats** (the same `x-x-9-10-x-10` twice). Our role rule deliberately does not: a
target needs a harmony *change*, so bar 14's downbeat is a `fill`. Two things make this
worth deciding rather than waving through.

- **The shape would be identical if the role allowed it.** `_place_shell` returns the
  same shell for bar 14 as for bar 13, so this is purely a role decision and no voicing
  question is hiding inside it.
- **The fill is thinner than the example, and loses the 7th.** Under this plan's first
  draft a fill was a duo or an interval: under a 5th melody the duo is the melody plus its
  3rd (`D5 + B4`), so with the thumb's `G2` the bar sounded `G`, `B`, `D` — a plain `G`
  major triad, the 7th absent. Decision C makes it thinner still: melody and thumb only,
  so no interval is stated above the root at all. Either way the 7th — the note that makes
  the chord a dominant and the whole point of a guide-tone shell — is missing from the bar,
  which is the argument for F.

> **Open decision F — ruled on, pending measurement: option (c), a target only where
> the melody moves.** Bars 13-14 support it exactly: bar 14's `D5` follows a `C#5`, so
> the melody re-articulates on that downbeat and the shell is restated — which (c)
> does and today's fill rule does not. Where the melody is genuinely *held* across the
> second bar the slot stays a fill, and under decision C a fill is the melody alone:
> thinner than a restated shell, and never claiming a harmony that is not sounding.
>
> It is recorded as the working rule rather than locked, because it is the one decision
> made on two bars and one criterion ("does the melody move *onto* this downbeat"), and
> because both readings are cheap to pin — the test below asserts them apart. Option
> (b), a target on every second bar regardless, is dropped: it would restate the shell
> under a melody that is simply ringing.

Note this does not touch the `repeated` hold: bar 14's `D5` follows `C#5`, not `D5`, so
the hold does not fire and the downbeat strikes either way.

#### Three smaller findings from the same bars

**`hand_fret` is not settled by the examples, and they lean away from both
candidates.** Checked note by note, `avg_fret` and `top_fret` choose the same string on
every readable bass note of the B section, so the examples do *not* decide that
question either way. What they do favour is a third candidate: measuring to the shell's
**lowest active fret** scores 26 of the 28 readable bass notes against 24 of 28 for
`avg_fret`, because bars 13 and 14 put their `E3` on the 5th string *behind* the
fingers, where proximity to the average picks the low E at fret 12. The misses that
survive every metric are two, both the same shape: bar 12's final `A2` (the tab takes
the open 5th string, proximity takes the low E at fret 5) and bar 13's drop to `E2` for
its last note. Candidate refinements — measure to the lowest active fret, treat an open
string as zero travel, break a sub-fret tie toward the lower fret — belong in Phase 3's
measurement, not in a rule chosen from two bars.

**The shell is chosen without knowing where the bass will go.** `voicing_cost` cannot
see the thumb, which is the price of "select first, merge after", so nothing prefers
`(5,3,2)` *because* it frees the 5th and 6th strings — even though that is exactly why
the example uses it in all eight bars. Under a high-E melody the selector weighs
`(5,4,3)` (which frees the 6th, 5th and 4th) against `(5,3,2)` (which frees the
6th and 5th) on upper-voice grounds alone, and either is playable. A stated risk, to
be measured — not something to fix by adding a bass term to `voicing_cost`.

**A target that cannot be a shell disappears, and the `"melody"` token does not catch
it.** Bar 10's beat 1 is `D` over `Bbm7` — the major 3rd over a minor chord, the
appoggiatura that resolves to `Db` on beat 2. It is not a chord tone and
`NON_CHORD_TONE_EXTENSIONS` has no "major 3rd over a minor 7th" route, so
`resolve_non_chord_tone` returns `None`, `prepare_step` keeps its fallback — which for
`grips=("shell",)` is an empty list, since a shell can never sound a note outside the
chord — and the step is **dropped with a warning**. That is existing behaviour, but
`walking_bass` is the first texture whose target is one grip and nothing else, so it has
no fallback at all. And the `"melody"` token already listed in the fill tuple does not
supply one: `_string_sets_for` returns `[]` for any grip absent from `GRIP_STRING_SETS`,
so `"melody"` is **inert** and the melody-alone path (`get_melody_only_voicing`) is
unreachable through `TEXTURE_GRIPS`. Two consequences: the extension and dim7 strategies
are **load-bearing** for this texture rather than optional, and `"melody"` must either
be wired to the melody-alone voicing or dropped from both tuples rather than left as a
token that does nothing.

### One pre-existing behaviour the example exposes

`repeated` forces a strike on every slot, so a held whole note becomes eight
soprano attacks where the example shows one. That is current behaviour rather than
something this plan introduces, but the example makes it visible, and under a
walking bass it starts to matter: the thumb is already marking time, so
re-articulating the melody on every eighth fights it.

**Decision B resolves it for this texture, without touching `repeated` elsewhere.**
The slots the melody grid invents under a held note become `bass_only` steps, whose
upper voices are held: the melody is struck where it is written and the thumb walks
under it. `repeated` keeps its present meaning everywhere, including in `uniform` and
`targets`, so no existing output moves — which is the whole reason the two are separate
fields rather than one overloaded flag. The measurement this needs is that a held
whole note in a walking-bass arrangement sounds **one** soprano note and four bass
notes, not eight of either.

## Phases

Each ends with the suite green, per the contributing workflow.

**All six decisions are now made** — A (the `(5,3,2)` shell), B (bass-only steps), C (a
fill is the melody alone), D (beat 4 approaches the next anchor), E (the anchor
generalises to a mid-bar change) and F (a target where the melody moves, recorded rather
than locked). What the ordering below is about, then, is *when each becomes checkable*,
not which answer arrives first. Three are settled by a unit test rather than an
integration — D and E inside the pure pass (Phase 4), F inside the role rule (Phase 5) —
and B is the one that reaches furthest: it changes the step list, so its work lands in
Phase 5's union and Phase 6's renderers, and the texture is not finished until both are
done.

1. **Types only.** `BASS_STRING_INDICES`, the bass role constants, the three
   `ArrangementStep` fields — including `bass_only`, which decision B requires —
   `Voicing.bass_midi` and `Voicing.bass_string`,
   `__all__`, `__version__` →
   `0.9.0`. Nothing reads them; provably inert.
2. **Backward-compatibility test first**, before any behaviour: exact
   demo-cadence tabs pinned under `uniform` and `targets`. This is what makes
   every later step cheap.
3. **The `(5,3,2)` shell set**, as its own phase because it is a behaviour change
   rather than an addition. One table entry; then run the full suite and
   **measure** which pinned tabs move, which steps relocate onto the new set, and
   whether any melody becomes reachable that was not. Update the pinned
   expectations only where the new output is musically correct, and report the
   count either way — "0 of 120 transcriptions" and "14%" are both acceptable
   outcomes, but only one of them is knowable in advance and it is not this one.
4. **`_walking_bass_line` + `bass_cost`, pure and unintegrated.** The anchor rule
   on every downbeat including a held chord's second bar, plus the **generalised
   mid-bar anchor of decision E** — one predicate, the one `_roles_for_slot`
   already applies. Beat 4 chosen **backwards from the next anchor** (decision D),
   extensions reachable on connective notes, the guide's major and minor ii-V-I
   lines reproduced without a key model, `enclosure`, `NC`, and unknown quality →
   `None`. `onsets=None` is asserted here too: the gridless case degrades to one
   note per slot rather than failing. The three `hand_fret` candidates are measured
   here, not chosen.
5. **Integration.** The union of the melody slots with the walked beats (decision
   B), the melody-alone branch for an empty fill tuple *and* for a target with no
   shell (decision C), the conjunction role rule carrying F, the `TEXTURE_GRIPS`
   entry, the guarded attach, the post-selection merge, the `partial` fix, the
   invariant amendment. Assert `uniform` output is byte-identical above the bass.
6. **Rendering, in all three families.** The `_staff_columns` fix and its
   regression, the `bass_only` branch (held upper voices, striking thumb) and
   `_step_annotation`. Then `tabgp._measures`, where a `bass_only` step is a beat
   whose upper voices must be written **and tied** or the bar reads as silence above
   the bass — verified by round trip, because nothing else finds a corruption, and
   the tie machinery (`NoteType.tie`) already exists for the bar-line case.
   MusicXML stays its own later phase — a five-note chord needs a second voice and
   `_build_part` assumes one — but it is named here so it is not mistaken for a gap.
   Assert existing render output byte-identical when the texture is unchanged.
7. **Front ends and docs.** `--texture walking_bass`, an AGENTS.md section,
   README, `implementation_plan.md` closed, version bump.

## Tests

- **The `(5,3,2)` set is a real set, not just a table entry.** Mirroring the existing
  6-4-3 reachability assertion: it appears in `supported_string_sets()`, its
  soprano is 5 and is in the set, and it is genuinely produced for at least one
  melody under `grips=("shell",)`. A tabulated-but-unreachable set is the failure
  mode `5-3-2`'s own comment warns about.
- **Every shell it produces obeys the invariant** — three strings, the melody on
  the soprano and highest, `fret_span() <= 5`, and every pitch a chord tone. Swept
  over the qualities in `SHELL_DEGREES` the way `test_grips.py` already sweeps the
  grips, so a non-contiguous set is held to the same contract as a contiguous one.
- **It is offered for a high-E soprano and not for the others.** The set is keyed
  on soprano 5, so `_string_sets_for` must not offer it for `top_string=3` or `4`.
- **The walking-bass fixture uses it.** The applied example's bars are voiced on
  `{5,3,2}`, so the fixture asserts the three-layer split actually occurs rather
  than the arrangement being approximated with a different shell.
- `tests/test_bass.py` — the generator, the role-conditional cost, the anchor rule,
  the backwards beat-4 choice, `NC`, unknown qualities.
- `tests/test_texture.py::TestBackwardCompatibility` — pinned fixtures, plus
  "adding a bass does not change the melody or the upper voicing".
- **Off-beat chord change** — a change on the 4-and yields a *fill* under the **new**
  chord: the melody alone above the thumb, and therefore a step whose only pitches are
  the melody and the bass (decision C). The next target beat carries the shell. This
  is the test that fails if the empty fill tuple is left to the generic
  no-candidates path.
- **Beat 1 is always the root** of the harmony sounding there, on every bar,
  including the second bar of a two-bar chord. This is the anchor rule, and it is
  the regression for the earlier draft's claim that a held chord must not
  re-anchor — re-striking the root is what marks the bar.
- **Beat 4 reaches the next anchor** by a half step above, a half step below, or a
  fourth below / fifth above, and the choice is made *backwards* from the next
  root.
- **A mid-bar change re-anchors** — `Bbm7` on beats 1-2 and `Eb7` from beat 3 puts
  the thumb on `Bb` and then `Eb`, on the same slot where the left hand states
  `Eb7`. This is decision E's regression, and it is the B section's bar 10; without
  it the two hands name different chords on the same beat.
- **The second bar of a held chord** — asserted deliberately separately from the
  anchor test above, so the two readings of decision F are cheap to pin. Under the
  working rule, option (c): the thumb re-anchors on the root either way, and the left
  hand restates the shell **only where the melody moves onto that downbeat** (bar 14's
  `D5` after `C#5`), staying melody-alone where the melody is genuinely held. Both
  halves are asserted, so a later switch to option (a) is a one-line change to one
  test rather than a rewrite.
- **A target that cannot be a shell does not vanish.** `D` over `Bbm7` has no
  `NON_CHORD_TONE_EXTENSIONS` route and no shell can sound it, so the step takes the
  melody-alone fallback of decision C — the same route an empty fill tuple takes —
  and keeps its bass. A silently dropped step is the failure mode here, and the
  warning is the only sign of it, so the assertion is on the step's presence in the
  list, not on the warning.
- **A held melody over a walk is one soprano note and four bass notes** (decision B).
  A whole note in the melody against one chord for the bar yields four steps from one
  melody slot — the first with the shell, three `bass_only` — and only the first
  strikes a string above the bass. `arrange_progression` therefore returns more steps
  than the progression it was given, which is asserted as a fact of the contract
  rather than tolerated.
- **A `bass_only` step holds the upper voices and strikes the bass**, in
  `format_tab_staff` and in GP5's round trip. The ASCII half is the `collapse`
  assertion below; the GP5 half is that the upper strings are written and **tied**
  rather than omitted, because an omitted string reads as silence above a moving bass.
- **A fill carries no chord of its own** — its upper voices are the melody alone, its
  bass is the walked note, and the chord name above it describes the harmony rather
  than everything sounding. Asserted as "the sounding upper pitches are exactly
  `{melody}`", which is the assertion that would catch a fill silently reverting to a
  duo.
- **A walking-bass fill is never promoted to a target** — the generic "a fill that
  cannot be filled becomes a target" rule is disabled for this texture, so a fill
  whose melody cannot take the melody-alone route cannot acquire a shell either.
- **The walk's own lines, not the example's.** The guide's beat-4 notes are not
  approaches to the next root (Break 4), so the fixture asserts the *rule* — a
  semitone or a 4th/5th to the next anchor — and the published tab is recorded as an
  expected divergence rather than an expectation.
- **Extensions are reachable on a connective note** — E over Dm7, A over G7, B♭
  over G7 and A over Cmaj7 are all generated. Every one of these is a **failure
  under the purity-first cost this document previously described**, so this is the
  single most important test in the file alongside the anchor test.
- **No key model is required** — the ii-V-I and ii-V-i lines from the guide are
  reproduced from chord tones, `NON_CHORD_TONE_EXTENSIONS` and root-relative
  approaches alone. If a test needs a scale to pass, the extension set has a hole.
- **A pure arpeggio is not the default output.** Asserted as a property of the
  generated line rather than an exact string: a bar of four notes under one chord
  must contain at least one non-chord tone, or the cost is ranking purity first
  again.
- **One shell per chord** — the *left hand* states a two-bar chord once. The thumb
  still re-anchors on the second downbeat, so this and the anchor test above are
  deliberately different assertions about the same two bars.
- `tests/test_tab_rendering.py` — the `collapse` regression (a walking line must
  not break the hold chain), the `repeated`-plus-bass case, and the `bass_only`
  case (held above, striking below).
- `tests/test_grips.py` — the amended invariant: upper voices in
  `supported_string_sets()`, exactly one `BASS_STRING_INDICES` string outside it
  carries the bass, `fret_span()` still bounded.
- **Bass string choice** — the bass lands on the string whose fret is nearest the
  hand, not the lower string: a D3 under a hand at fret 5 is the 5th string at
  fret 5, **not** the 6th at fret 10. Asserted on the fret distance, because that
  is the actual rule.
- **All three bass strings are reachable** — a step whose upper structure is `5-4-3`
  or `5-3-2` has no free 5th string and must fall to the 4th or the 6th; one under
  `2-3-4` or `6-4-3` has no free 4th. Asserted in both directions, so no candidate
  is dead code.
- **The octave is chosen against the hand** — a Dm7 held under a shell at fret 5
  walks its `C` as `C3` on the 5th at fret 3, **not** `C4` at fret 15. This is the
  regression for the whole pitch-class split, and the single most valuable test in
  the file.
- **A four-tone walk over a held chord is playable** — every thumb note in it is
  within the shell's span budget of `hand_fret`, which is the span problem the
  Dm7 table above describes.
- **The bass sounds below the upper structure**, on every step, checked against
  `min(voicing.midi_notes())` rather than against string indices.
- **The applied example is a fixture.** The guide's 8 bars of "But Not For Me" in F
  are transcribed as a skeleton with timings and asserted against: the anchor on
  every downbeat, the 3rd + 7th shell, the bass string choices. This is the single
  test that would have caught all three breaks above, and it should exist before
  Phase 4 rather than after it. It does **not** need to match the published tab
  note-for-note — the shell set and the bar-1 C♯ are known divergences — so it
  asserts the parts the plan claims and leaves the rest open.
- `tests/test_wjazzd.py` — over melid 218, every **anchor** note is the root of the
  *effective* harmony, and every thumb note is either a chord tone, an extension
  `NON_CHORD_TONE_EXTENSIONS` can name, or a root-relative approach to the next
  anchor. `skipUnless(DEFAULT_DB.is_file())`.

The invariant tests already in the suite (`supported_string_sets`, `fret_span`,
"every sounding pitch is a chord tone") are the ones that would catch a bad
merge, so they are extended to a walking-bass arrangement rather than a new
invariant being invented.

## Risks

- **The `(5,3,2)` set changes existing output.** This is the one item here that is
  not opt-in: `shell` is in `GRIP_PREFERENCE`, so the new set is a candidate in
  every `uniform` arrangement and in every `targets` fill, and the selector may
  prefer it. Pinned tab strings across the suite may legitimately move. The phase
  exists to *measure* that rather than to prevent it, and the expectation is
  update-only-where-musically-correct.
- **Overfitting.** v1 targets functional harmony and says so; no claim of general
  jazz walking.
- **Coupling to the cost function.** Avoided structurally by selecting before
  merging, not by discipline.
- **Rhythm confusion.** No new timing model — the bass attaches to beats that already
  exist — but the step list grows (decision B), so the one thing that *is* new is that
  `arrange_progression` may return more steps than it was given. Contained by building
  the union before the melody loop, so the index alignment the corpus path relies on
  never breaks; the test is "a held whole note yields one soprano strike and four bass
  notes".
- **The step list stops being index-aligned with the progression.** Decision B's real
  cost, and the replacement for the "slot model may not fit a bass-primary texture" risk
  this document used to carry. A caller that zips its own progression against the
  returned steps, or indexes one by the other, is now wrong wherever the beat grid is
  finer than the melody grid. Two mitigations, both required rather than optional: the
  union is built **before** the melody loop (so `arrange_head`'s guard and
  `arrange_slots`' `retry` index keep meaning what they meant), and the growth is
  asserted in a test rather than discovered by a caller.
- **Renderer assumptions.** The `collapse` regression is the specific test; it is the
  one thing not to weaken. Decision B adds two further renderer concerns — the
  `bass_only` branch in `_staff_columns`, and tied upper voices in `tabgp._measures`
  where an omitted string would read as silence above a moving bass — so Phase 6 is
  deliberately *sequential*: the `collapse` fix lands first with its own regression, then
  the `bass_only` work, so a failure in one cannot be masked by the other.
- **Non-chord tones on off-beat fills** may substitute the written harmony. Named
  above as a measurement, with a cheap mitigation if it bites. Decision C makes it
  smaller rather than larger: a fill that is the melody alone has no chord of its own to
  substitute, so the question only survives where a fill slot carries a *target's*
  harmonisation.
- **The melody-alone route is load-bearing on both sides.** `grips=("shell",)` yields
  nothing for a melody no shell can sound, and an empty fill tuple yields nothing at
  all, so one branch of decision C carries the target's fallback *and* every fill. If it
  is not wired the failure is silent in two different ways at once — a dropped step with
  only a warning, and a fill that quietly reverts to a target. The test is "no step in a
  real head disappears", not "the warning is printed", because the warning is easy to
  miss in a long run.
- **The shell is picked blind to the bass.** "Select first, merge after" is the
  property that keeps the cost tuple honest, and this is its cost: nothing prefers
  the shell that leaves the bass strings free. Measure which shell wins under a
  high-E melody and report it; do not add a bass term to `voicing_cost` to steer it,
  which would put an invisible second objective into a tuple whose whole argument is
  that its criteria are independent.

## Acceptance criteria

- The feature exists as `texture="walking_bass"`, validated like the others.
- `uniform` and `targets` are byte-identical to today, with or without a bass.
- The melody and the upper voicing are provably unchanged by the addition of a
  bass.
- Output is musically coherent on ii–V–I and dominant-to-tonic, with the bass
  stated on anchors and the left hand light between.
- A fill is the melody alone, and a held melody over a walk sounds once above the
  bass rather than on every slot.
- The bass remains outside the upper-voicing cost tuple.
- The staff renderer holds its shape under a walking line, and a `bass_only` step
  draws as a held upper shape with a moving thumb in all three renderer families
  that v1 supports.
- Tests cover the new mode and guard the old ones.

## Non-goals

Deliberately not in v1: fully general contrapuntal writing, stylistic
improvisation choices, automatic reharmonization beyond bass-motion rules,
multi-voice orchestration beyond a thumb line plus the upper structure, a full
"Joe Pass" system, Coltrane changes, modal handling, and any bass string above
the 4th.

`enclosure` is named as a role because the lookahead makes it nearly free, but
only the simplest form is in scope: half step above, then half step below. Longer
enclosures, and pedal points as a sustained device rather than a role, are not.

## Known limitations, to be written down rather than discovered

- **`timings=None` degrades to one bass note per anchor.** There is no beat grid
  to place four quarters on, so there is nothing for decision B's union to add to
  either. Every other existing test passes `timings=None`, so this is the path a
  hand-written progression takes and it must be documented, not silent.
- **A `walking_bass` arrangement can have more steps than the progression it came
  from** (decision B). Callers that assume one step per input triple — a zip, an
  index, a bar count derived from `len(steps)` — are wrong for this texture only.
  The `uniform` and `targets` contracts are untouched.
- **A fill carries no chord of its own** (decision C). The chord name printed above
  a fill describes the harmony, and the only notes sounding are the melody and the
  thumb; the harmony is stated in full at the targets. That is the texture rather
  than a defect, but it means a `walking_bass` tab has more bars than not where the
  left hand is silent, and the reader needs to know that before counting strings.
- The bass uses the 6th, 5th and 4th strings only. A timbre preference is not
  implemented, and neither is a fixed-string preference: the string follows the
  hand, so a line that walks up the neck will change strings as it goes.
- **The 4th string will be used rarely**, since three of the five shells occupy
  it. That is a measured prediction, not a design goal, and Phase 3 should report
  the real distribution rather than assume it. Under the `(5,3,2)` shell — which is
  what this tune's high-E melodies use in every bar — "rarely" becomes "never": the
  string belongs to the shell's lowest voice, so the thumb has only the 6th and 5th.
  Once decision A lands, **four** of the six shells occupy it, not three of five.
- **`hand_fret` is a choice to be measured, not a derived constant.** `avg_fret`
  and `top_fret` disagree for a 6-4-3 or 5-3-2 shape, and the plan should settle it
  from output rather than by assertion. The B section's evidence is that the two
  agree on *every* readable bass note there, and that a third candidate — the shell's
  **lowest** active fret — matches two of their shared misses, 26 of 28 against 24 of
  28. So the measurement should carry all three rather than choosing between the
  original two.
- **The walk will not reproduce a published line.** `approach` is defined against the
  next *root*, and the guide's own examples approach the next bar's *melody* about as
  often as they approach anything at all (Break 4). A user wanting one specific line
  is asking for an override the texture does not have, and this should be documented
  rather than implied.
- **A fill states no chord of its own** (decision C), so between the targets the
  harmony is carried by the thumb's root — and the quality returns at the next target.
  The previous version of this bullet worried that a fill under a 5th melody would state
  a triad rather than a seventh chord (`G`, `B`, `D` under a `G7`); that is now
  impossible, because under decision F the second bar of a held chord is a *target*
  wherever the melody moves, and a fill sounds the melody alone. What remains worth
  documenting is the consequence for the ear rather than the fingers: at a fill there is
  one bass note and a melody, and nothing else.
- **The octave tie-break is unmeasured.** When a descending walk runs out of board
  below the A string's open A2, whether the line climbs or drops to the low E is
  a judgement call, and either answer is defensible.
- **The extension set is the ceiling on the line's vocabulary.** A connective note
  that is neither a chord tone nor a `NON_CHORD_TONE_EXTENSIONS` route nor a
  root-relative approach is unreachable, and unlike the melody there is no
  `diminished` fallback — substituting the harmony under the thumb would change
  the bass. Whether the current table covers the guide's lines is a Phase 3
  measurement, and it is the one most likely to need a new table entry.
- **Non-4/4 metres lose the beat-4 approach.** A 3/4 bar has three quarters to fill and
  no beat 4, so the `approach` role has nowhere to go; a 2/2 bar has two. The anchor rule
  is unaffected — decision E keys it on strong beats, and `_roles_for_slot` already reads
  the metre it was given (`TARGET_BEATS = (1, 3)` means beats 1 and 3 in a 3/4 bar) — but
  what replaces the approach role in a three-beat bar is undecided, and 3/4 will need its
  own thought.
- The left hand anchors on target beats only, so a long held chord gets no
  re-strike even where a player might punctuate it. The **thumb** does re-anchor,
  so the bar is still marked.
- `partial` stays `True` for every walking step, so the staff annotation is
  permanently verbose; the walk role is carried in `_step_annotation` instead.
