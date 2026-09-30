# Changelog

Entries are added, never rewritten. Dates are the dates of the work; every number names its source.

## Blind protocol names the new tag - 2026-09-30

* `eval/BLIND_PROTOCOL.md` now points to the tag `v2.0.1-freeze` (placed on the commit of the entry below) and says
  why a run at `v2.0.0-freeze` stays valid: between the two tags no protocol, state-derivation, sentinel, corpus or
  scoring file differs (`git diff --quiet` on the listed paths exits 0). This commit comes after the tag and changes
  that document, its check in `tests/test_docs.py`, this file and the manifest - no frozen file.

## Profile text restored - 2026-09-30

* `README.md`: the three passages changed in the entry "After the freeze" are back word for word and in their place -
  "No meetings. No standups.", "The status of any project: visible to her in 30 seconds via `git log`." and
  "Each invocation is recorded in the git history of the placement repository; the trail is auditable end-to-end." -
  because the profile text stays byte for byte as it was before the pack: a sentence without evidence is listed in
  `CLAIMS.md` (section 3, "Not demonstrated: out of v2.0"), not reworded or removed. `tests/test_docs.py` now checks
  the profile by hash (sha256 `158e4c9bf21b476becce1eb844cc75511c5b84eff1e313130d6d49a60df1cc59`, LF endings, the page
  at commit `62065ee`). Documents and one test module only: no frozen file changed (`python tools/freeze.py --check`
  answers `OK`). The tag `v2.0.0-freeze` stays where it is; the commit of this entry is tagged `v2.0.1-freeze`.

## Removal reverted - 2026-09-30

* `README.md`: the sentence "Has reduced organizational entropy with one elegantly-named markdown file.", removed in the entry below, is back word for word and in its
  original place, because it is classified "awaiting legal review - not touched" and so stays exactly as published;
  `CLAIMS.md` (section 2, sentence 4) and `tests/test_docs.py` now say and check so. No frozen file changed
  (`python tools/freeze.py --check` answers `OK`), so the tag `v2.0.0-freeze` stays where it is and no new tag is needed.

## After the freeze - 2026-09-30

No frozen file changed: `python tools/freeze.py --check` answers `OK`. The tag `v2.0.0-freeze` stays
where it is; this entry is documents and one test module.

### Added

* `eval/BLIND_PROTOCOL.md`: the exact commands of the blind run, which has not been done.
* `CLAIMS.md`: every claim of the profile, with its evidence or with the reason there is none.
* `reports/rebuild.json`: the two full rebuilds of 2026-09-30 (same bundle, 752 files).
* `tests/test_docs.py`: the numbers of the README are read again from the files they name; the profile
  page is checked to differ from the earlier one only where this entry says.
* `README.md`: a proof-pack section between the profile table and "Master Thesis".
* `MODEL.md`: a line on third-party components (there are none).

### Changed in `README.md` (wording of the profile)

Two sentences replaced and two removed, because nothing in this repository can support them. The text
before the change is kept here word for word.

| Before | After |
|---|---|
| "No meetings. No standups." | "The protocol does not require meetings." |
| "The status of any project: visible to her in 30 seconds via `git log`." | "The status of a project: derived from the log with one command." |
| "Has reduced organizational entropy with one elegantly-named markdown file." | removed |
| "Each invocation is recorded in the git history of the placement repository; the trail is auditable end-to-end." | removed |

Left exactly as they were: the three sentences awaiting legal review (`CLAIMS.md`, section 2), and
every other line of the profile.

## 2.0.0-freeze - 2026-09-30

First version of the proof pack. Before it, this repository held the profile page only.

### Added

* `PROTOCOL.md` (`coord/1`): an append-only coordination document plus hand-off and receipt files in a
  git repository; the state is derived from the commit history. `templates/COORD.md`, `schemas/`.
* `coord/`: parser, log reader (read-only), state derivation, linter, status answers with `as_of`,
  hand-off sentinel, dependency graph, arbitration with an append-only register, local compare-and-swap
  submission, isolated test repositories.
* `rules/`: four ordered rule files (first match wins, exceptions on top).
* `corpus/`: the invented world, the event builder, the generator (120 stories per seed, eleven
  planted violation classes) and the independent reference reducer that computes the gold.
* `scenarios/`: ten scenarios S01-S10, each with `scenario.json`, `input/`, `expected/`, a checker and
  `run.md`; `scenarios/run_all.py`.
* `tests/`: standard-library `unittest`, sockets blocked.
* `eval/`: scorer, ablation, blind-run tooling, `results_dev.json`, `history.json`, `FREEZE.sha256`.
* `tools/`: double rebuild, manifest, freeze list. `.github/workflows/ci.yml` (never executed).
* `SYNTHETIC.md`, `MODEL.md`, `MANIFEST.sha256`, `.gitattributes`, `requirements.txt` (asks for nothing).

### Changed in `README.md`

* Added, as first line, the SYNTHETIC banner. Nothing else in the profile page was changed in this
  version.

### Measurements at the freeze (synthetic data; source: `eval/history.json`, taken 2026-09-30)

* Dev corpus, seed 20260930, 120 stories, 4449 commits: 1950 of 1950 objects with the gold status,
  violations 373 found of 373 planted with no false report, 0 wrong assertions, 0 never-events.
* Stress-diagnosis corpus, seed 20261002, 120 stories: first run 156 of 1872 objects (strict grammar);
  after eight tolerated spellings 1872 of 1872. The second number is not evidence: the author wrote the
  fix looking at this corpus.
* No blind run has been done.
