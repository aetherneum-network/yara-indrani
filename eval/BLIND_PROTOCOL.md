# Blind run - protocol

**Status on 2026-09-30: not done.** The author of the pack (a synthetic AI agent, via Claude Opus 5.5)
froze the code at the tag `v2.0.0-freeze`, never generated a blind seed and never looked at one. This
file says exactly what a **different hand** runs, once. Until that is done, the pack has no independent
number and must not be tagged `v2.0.0`.

**Which tag.** Run it at `v2.0.1-freeze`. That tag holds the code of `v2.0.0-freeze`, unchanged, with
corrected documents and one documentation test module. Between the two tags

```
git diff --quiet v2.0.0-freeze v2.0.1-freeze -- coord corpus rules schemas templates scenarios tools eval/score.py eval/blind_hand.py eval/ablation.py PROTOCOL.md
```

exits 0: no protocol, state-derivation, sentinel, corpus or scoring file differs. A blind run made at
`v2.0.0-freeze` is a run on the same code and stays valid; its result names the commit it was run at.

Everything measured here is internal consistency on synthetic data (see `SYNTHETIC.md`).

## 0. Before starting

* Who runs it: anyone who is not the author of the pack. The name goes into every result (`--runner`).
* Where: the repository at the tag `v2.0.1-freeze` (same code as `v2.0.0-freeze`), or any later commit for which the command below
  answers `OK` (later commits may add documents; they may not change the frozen files).
* With: Python 3.12 and git 2.32 or later. Nothing to install. No network is needed.

```
python tools/freeze.py --check
```

Expected: `freeze: OK - the code is the frozen one`. If it says `FAILED`, stop: the blind run is not
valid on changed code. Both blind commands below repeat this check themselves and refuse to run.

## 1. Part A - a corpus from a seed the author never saw

1. Choose a whole number `N` **before** running anything, and write down how it was chosen (for example
   the date of the run as `YYYYMMDD`). `20260930` and `20261002` are refused: the author used them.
2. Run, once each:

```
python eval/score.py --suite blind --seed N --profile standard --runner "NAME"
python eval/score.py --suite blind --seed N --profile stress --runner "NAME"
```

Each command generates 120 stories from the seed, builds their git histories, derives the state with the
frozen code, compares it with the gold of the reference reducer, prints one summary line and writes
`eval/blind/blind-N-standard.json` (or `-stress.json`). A result file is never overwritten: the same
seed and profile cannot be run twice.

What the two profiles can and cannot show:

* `standard` plays the part of the holdout set: new stories, canonical spelling.
* `stress` writes the same kind of stories with the eight tolerated spellings of `PROTOCOL.md`
  section 2. It shows that the tolerances hold on stories the author never saw. It does **not** show
  that the reader copes with spellings nobody listed: that is what Part B is for.

## 2. Part B - five cycles written by hand

The runner writes at least five coordination cycles by hand with **only** `PROTOCOL.md` and
`templates/COORD.md` in front of them - not the code, not the scenarios, not the corpus - on an invented
team (invented names, `.example` addresses; nothing taken from real work). The command of step 4 is run
afterwards, when the cycles and `declared.json` are written and will not be changed.

1. Create the repository and the document:

```
git init --initial-branch=main blind-hand
cd blind-hand
```

   Copy `templates/COORD.md` to `COORD.md`, fill the title and the agents, and commit it.

2. Append one entry per commit. Each commit is made with the email of the agent named in `by`:

```
git add COORD.md
git -c user.name="AGENT NAME" -c user.email="AGENT@TEAM.example" commit -m "ENTRY-ID"
```

   (add `handoffs/ENTRY-ID.json` or `receipts/ENTRY-ID.json` to the same commit when the entry is a
   `HANDOFF` or a `RECEIPT`).

3. **Before** running anything, write in `declared.json`, next to the repository, the state intended:

```
{"proposals": {"anna-1": "DECIDED"}, "blocks": {}, "freezes": {}, "handoffs": {}, "disputes": {},
 "conflicts": {}, "release_gate": "OPEN", "violations": []}
```

   Any of the keys may be left out; `violations` lists classes (`["V05"]`), `[]` means none intended.

4. Run, once:

```
python eval/blind_hand.py --repo blind-hand --declared declared.json --runner "NAME"
```

   It prints one line (`objects exact X/Y, release gate ..., violations ..., structural findings Z`),
   then every object whose derived status differs from the declared one, and writes
   `eval/blind/hand-NAME.json`. It fixes nothing and is never overwritten.

## 3. Recording

* Add one item per result to `eval/history.json` (at the end of `runs`; nothing above is edited) with
  `suite` (`blind` or `blind-hand`), `seed` and `profile` where they apply, `runner`, `recorded_at`,
  `command`, `output` (the name of the file in `eval/blind/`) and the result verbatim.
  `tests/test_corpus.py` fails if a file in `eval/blind/` is not recorded there.
* The numbers are reported as they are, with the name of who ran them - also when they are bad.
* A wrong assertion or a never-event greater than zero is a failure of the pack, whatever the other
  numbers say. In Part B, every difference between the declared and the derived state is either a
  defect of the code or a place where `PROTOCOL.md` was not clear enough for someone who did not write
  it: both are findings, and both are written down.

## 4. After the blind run

Nothing is fixed and re-run on the same seed. If the code or the protocol changes, that is a new
version (`v2.0.1`): new freeze list, new tag, a new seed chosen by the runner, and the old result
stays in `eval/history.json`.
