# Changelog

Entries are added, never rewritten. Dates are the dates of the work; every number names its source.

## The manifest step stops at its first failure on Windows too - 2026-10-02

* `.github/workflows/ci.yml`, step "Files on disk are the files of the manifest and of the freeze list": it now runs
  in `bash` on both systems. In run 37033190588 (2026-10-02) the manifest check failed on both systems, but on
  `windows-latest` the default shell (PowerShell) took only the exit code of the last command, the freeze check,
  so the step passed and the job went on to the tests. With `shell: bash` the runner adds `-e`, and the step fails
  at the first command that fails, as it already did on `ubuntu-latest`. The manifest is regenerated; no frozen file
  and no tag changes.

## Profile hash and manifest follow the README reviewed in pull request #1 - 2026-10-02

* Pull request #1 (week-1 review of 2026-09-30, merge commit `6970d8e`) corrected the profile text of `README.md`
  (the thesis title, in the list of contributions and in the diploma). Pull request #2 (merge commit `3860010`) brought in the
  pack, whose `MANIFEST.sha256` and `ORIGINAL_README_SHA256` in `tests/test_docs.py` had been computed on the README
  before that review. On `main` (run 37033190588, 2026-10-02, both systems) `python tools/manifest.py --check`
  answered `FAILED - README.md: changed`; on `windows-latest`, where that step went on to the freeze check and the
  tests, two tests failed: `test_the_manifest_is_the_disk` and `test_the_profile_is_byte_for_byte_the_page_before_the_pack`.
* `tests/test_docs.py`: `ORIGINAL_README_SHA256` is now the hash of the reviewed profile text, sha256
  `3288f8b200c6f5397581fa42453b2819a43d8948ac8888e91068d73bb3fcb0ae` (the page at commit `6970d8e`), with a comment that names pull request #1 as the source of
  the change. `CLAIMS.md` section 4 gains a paragraph that says the same; its earlier text and the entries below,
  which give the hash before the review, stay as written.
* No frozen file changed (`python tools/freeze.py --check` answers `OK`; `eval/FREEZE.sha256` is unchanged). The
  README text is unchanged. The manifest is regenerated. No tag is placed or moved: `v2.0.0-freeze` to
  `v2.0.2-freeze` stay where they are.

## README states the recorded blind runs and the publication - 2026-10-02

* `README.md`, proof-pack section only: the italic line, the "Blind run" row of the numbers table (now three rows,
  one per run) and the line "An independent number" of "What is NOT demonstrated" said that the blind run had not
  been done. They now state what `eval/history.json` records for runs 6, 7 and 8: the evaluator (Claude Opus 5.5),
  not the builder; the tag `v2.0.0-freeze`; seed 20261011; the times in UTC; stories, commits and objects; the
  `TO_CONFIRM` answers; wrong assertions and never-events; and what part B did not exercise. The profile below the
  section is unchanged (sha256 `158e4c9bf21b476becce1eb844cc75511c5b84eff1e313130d6d49a60df1cc59`).
* `CLAIMS.md`: the row "An independent number" and requirement E1 say the same. The tag `v2.0.0` is still not
  placed; whether to place it is [TO CONFIRM].
* Published on 2026-10-02 as pull request #2 of this repository; the workflow runs on GitHub-hosted runners and
  its results are on the pull request. The statements written before that, that the workflow had never been
  executed (`README.md`, `CLAIMS.md` row "A green CI run" and requirement E4, the comment of
  `.github/workflows/ci.yml`), now say so; no result is copied here. `tests/test_docs.py` checked the section for
  the words "never been executed" and now checks for "pull request #2". `CLAIMS.md` "One machine": every run
  recorded here was on Windows 11. Older entries of this file that say "never executed" described their version
  and stay as written.
* Documents and one test module only: no frozen file changed (`python tools/freeze.py --check` answers `OK`),
  `eval/history.json` and `eval/blind/` are unchanged, `eval/BLIND_PROTOCOL.md` still points to `v2.0.1-freeze`.
  The manifest is regenerated. The commit of this entry is tagged `v2.0.2-freeze`.

## Blind runs recorded - 2026-09-30

* `eval/history.json`: runs 6, 7 and 8 are the blind runs of 2026-09-30 made by an evaluator who is not the builder
  (seed 20261011, profiles standard and stress, then the hand-written repository of part B), copied verbatim from the
  evaluator's own files, with their three result files in `eval/blind/`. They were run at `v2.0.0-freeze`; the protocol
  explains why that run stays valid at `v2.0.1-freeze`. Part B found 13 of 15 objects exact and two handoffs derived
  as MISMATCH: the evaluator's handoff and receipt files lacked fields that the protocol names but does not describe
  [TO CONFIRM whether this is a gap of the protocol or of the hand-written files].
* `tests/test_docs.py`: `test_the_history_holds_no_blind_result` is replaced by
  `test_the_author_runs_stay_and_every_blind_run_names_its_runner` - the author's five runs and seeds are still
  checked as before; every later run must be blind, name a runner who is not the builder and use a seed the author
  never saw. Recorded by the D25 coordinator session (Claude Opus 5.5) - not the builder and not the evaluator. No frozen file changed; the manifest is regenerated.

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
