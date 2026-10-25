# Open issues

**One is open.** Every other issue this project filed is closed, and the ledger holds the one open item
below; the record of the first six — each with its measurement and the recipe that re-measures it — is
[docs/history/open-issues.md](history/open-issues.md), which holds the full text of every item.

This path still exists because the tree cites it: the frozen documents in `docs/history/` link to
`open-issues.md` by relative path, and the engine, the importer and the tests cite an item **by
number**. A citation of `open-issues item N` resolves through the index below, which is the one
place the numbers are listed.

## The six, as they closed

Each line is the item's own title; the measurement behind it is in the record.

1. **The library facade takes its harmony per melody note** — closed by the rhythm-first request.
2. **A refused thumb note is usually not the shape being unplayable** — closed by the palette
   narrow: a requested bass note moves the harmony instead of being dropped.
3. **`harmony=full` is accepted on the comping route and answered with a different family** —
   closed by the axis being removed.
4. **A `bass:` grid row is accepted and changes nothing** — closed by the request, and then made
   unreachable: the row itself went with the `grid` axis.
5. **A lone note the hand holds can leave the walk below the shape's reach** — closed by the
   hand's reach being bounded and the palette making room for the note.
6. **A position falling on a note's release is read as held** — closed by reading the note as
   sounding over `[onset, end)`, so the union states the chord where the tune has just stopped.

## 7. Open — one defect in the comping selector that the comp-line plan did not fix silently

- **`cost.py:218`'s hardcoded 9.** `position = abs(voicing.avg_fret - 9)` when there is no
  previous voicing pins the comp's rest position to fret 9 instead of reading the neck window.
  The comp line's own opening (`comp_line.opening_no_melody`) now decides a comping step's
  first shape by the home band's middle, so the constant only reaches a caller with no
  previous shape outside the comping route — it is still the wrong rule there.
  Recipe: `grep -n "avg_fret - 9" arranger/cost.py`.

The item's **other half is closed**: the collapse's `(span, avg_fret)` key now keeps one shape
per **top tone** ranked by `(outside the window, outside the band, |avg − band middle|, span)`
(`grips._comping_collapse_key`), which is what let a line reach a low shape at all. The
measurement that closed it — the palette's reach per tone, and the plateau's 322 zero moves of
474 falling to 0 — is in [history/comp-line.md](history/comp-line.md) §"The measurement".

## Filing a new one

An issue is filed here, in the form the retired ledger used and the tree's citations assume:

- the **issue**, the **problem it produces**, and **why it exists**, with the measurement behind
  it — a figure with no measurement is a complaint, and **a stated figure gets a recipe** that
  takes it by hand, because nothing in the gate is keyed to these numbers;
- each figure stated **once**, in its own item, so a second document restating it cannot rot
  silently beside it;
- **numbering continues from the record** (item 6 is its last), so a bare `open-issues item N` —
  which is how nine sites in `headxml.py` and `tests/` cite these items — stays unambiguous
  across the record and this ledger.

A fixed issue is **removed** from this file rather than kept: its record lives in the commit that
fixed it and in the document that owns the subject. When the ledger holds nothing open it is
retired into [docs/history/](history/) and this path becomes an index of what it recorded — which
is what has happened once already.
