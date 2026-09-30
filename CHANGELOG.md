# Changelog

Entries are added, never rewritten. Dates are the dates of the work; every number names its source.

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
