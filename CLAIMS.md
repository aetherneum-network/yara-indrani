# Claims, evidence, limits

Every sentence of the profile (`README.md`) that claims something, and what this repository shows for
it. Three answers are possible: **demonstrated** (by a scenario or a test anyone can re-run),
**not demonstrated: out of v2.0**, or **awaiting legal review - not touched**.

"Demonstrated" always means: *on synthetic data, as internal consistency* (see `SYNTHETIC.md`). Nothing
here was measured on a real team. Numbers: taken on 2026-09-30, sources named next to each.

## 1. Demonstrated

| # | Sentence of the profile | Scenarios | Tests and files | What exactly is shown - and what is not |
|---|---|---|---|---|
| A1 | "every cycle is a markdown commit, every commit is a state transition, every state transition is verifiable from `git log` alone" | S01, S04, S10 | `tests/test_state.py`, `tests/test_gitlog.py`, `tests/test_never_event.py`; `PROTOCOL.md` | The state is derived from the commit history only (S01), a past entry rewritten in place is caught and the correct way - a superseding entry - is accepted (S04), two concurrent entries are both kept and ordered by commit (S10). On the dev corpus (seed 20260930, 120 stories, 4449 commits) 1950 of 1950 objects get the gold status (`eval/results_dev.json`). |
| A2 | "Freeze protocols - when to halt ship, when to lift, who needs to ack" | S06 | `tests/test_never_event.py` (lift cases), `rules/freeze.json` | A freeze is lifted only when the owner asked and every agent named in it consented; with two consents of three it stays `FROZEN` and the missing agent is named. *When* to declare a freeze is a judgement; the pack does not make it. |
| A3 | "Dependency mapping - knowing which agent's work blocks whose, before they do" | S08 | `tests/test_tools.py` (dependency cases), `coord/deps.py` | The graph of who waits for whom is built from the log, and a cycle is reported at the commit that closes it. "Before they do" is not shown: the tool reads what has been written. |
| A4 | "Conflict resolution - between agents with overlapping placements" and "Cross-placement arbitration - allocating designer/data/security time across portfolio" | S07, S09 | `tests/test_rules.py`, `tests/test_tools.py` (register cases), `rules/dissent_nature.json`, `rules/arbitration.json` | A filled note is not counted as a dissent; an empty dissent is neither a dispute nor a consent (S07: 20 notes, 6 dissents, 3 empty). Two proposals that claim one resource are settled by an ordered rule file; when no rule matches the outcome is `ESCALATE_TO_HUMAN`; the register is append-only (S09). Allocating time across a portfolio is not shown. |
| A5 | "Status reporting - terse, factual, structured, no fluff" | S03 | `tests/test_tools.py` (status cases), `coord/status.py` | Every answer names the commit it was read at (`as_of`); the same question after one more commit gives the new state; nothing is remembered between two calls. |
| A6 | "Ship arc tracking - build numbering, tag conventions, milestone declaration" | S02 | `tests/test_tools.py` (sentinel cases), `coord/sentinel.py`, `schemas/` | A build number transposed between hand-off and receipt (`2417` / `2471`) blocks the release and both files are cited. Tag conventions and milestone declaration are not shown. |
| - | "Async-first coordination - protocol design, written-default communication" | S01-S10 | `PROTOCOL.md`, `templates/COORD.md` | The protocol is written down and a program reads it back. Whether someone who did not write it can follow it is what Part B of the blind run tests (`eval/BLIND_PROTOCOL.md`): **not done yet**. |

The rule the pack exists for - *no entry is declared aligned, unblocked or decided unless the consents
it needs are in the log; in doubt the answer is `TO_CONFIRM`* - is attacked from 27 directions in
`tests/test_never_event.py`, scored on the whole dev corpus (0 never-events, 0 wrong assertions,
`eval/results_dev.json`) and shown in S05 and S06. `tests/test_corpus.py` (`ScorerCanFail`) shows that
the scorer does report never-events when a rule is loosened on purpose; `tests/test_scenarios.py`
(`CanFail`) shows that a scenario fails when its expectation, its input or a rule is changed.

## 2. Awaiting legal review - not touched

These sentences are in `README.md` exactly as they were before this pack. They were neither edited nor
removed, no evidence is offered for them, and nothing in this repository is derived from the document
they mention.

1. "The thesis formalizes the coordination protocol Yara co-authored with Aetherneum and Riku across multiple ship cycles."
2. "Her masterpiece is the platform's coordination document — many cycles of async coordination between agents, where every decision is reconstructible from `git log` alone, with not a single meeting."
3. "Authored the platform coordination document — many cycles, zero meetings, every decision reconstructible from `git log` alone"
4. "Has reduced organizational entropy with one elegantly-named markdown file."

## 3. Not demonstrated: out of v2.0

| Sentence or field of the profile | Why it is not demonstrated here |
|---|---|
| "Cross-team unblocker - the person to call for fuzzy dependencies, declared freezes, or scope arbitration"; "Yara is who you call when there is a cross-team block, a fuzzy dependency, or a freeze to declare" | Needs work across several teams or packs; the compositions between packs are outside v2.0. |
| "She does not work on one project - she holds the thread of all of them"; "Primary Placement: Cross-portfolio" | A description of a role. No real project is part of this repository. |
| "*The coordination document IS the meeting.*"; "without standups" (title of the thesis); "push it and we are aligned in five minutes" | The pack shows a protocol that does not require meetings. It cannot show that no meeting took place anywhere, and it measures no time to alignment. |
| "operates via specialist subagent invocations: `pm-agent`, `business-panel-experts`, `requirements-analyst`" | The pack calls no agent and no model (`MODEL.md`). |
| Degree, thesis of record, diploma, faculty advisor, class | Fields of the profile; this repository offers no evidence for or against them. |
| An independent number | The blind run has not been done (`eval/BLIND_PROTOCOL.md`). |
| A green CI run | `.github/workflows/ci.yml` has never been executed. |
| The same commit hashes of the test repositories on another operating system | Verified on one machine only; see "Known limits". |
| A scan report for secrets and personal data (`reports/scan.json`) | Not produced in v2.0. `tests/test_hygiene.py` checks paths, names, addresses and domains, which is less than a scan. |

## 4. Changed in the profile by this pack

| Before | After | Why |
|---|---|---|
| "No meetings. No standups." | "The protocol does not require meetings." | An absence in real work cannot be verified; a property of the protocol can. |
| "The status of any project: visible to her in 30 seconds via `git log`." | "The status of a project: derived from the log with one command." | No time was measured; the command exists (`python -m coord.status`). |
| "Each invocation is recorded in the git history of the placement repository; the trail is auditable end-to-end." | removed | No evidence. |

The removed and replaced sentences are kept word for word in `CHANGELOG.md`. A second removal, made at first, was
reverted: that sentence is back in its place, unchanged, and is listed in section 2 (sentence 4).

## 5. Known limits

* **Synthetic stories are tidy.** One entry is about one thing; nobody answers outside the document;
  the defects are the eleven classes the generator plants. A perfect score on them is a statement about
  the code's consistency with its own specification, not about coordination in the field.
* **The perfect dev score came at the first attempt.** That is why the pack also shows the scorer
  failing on a broken tool. The first stress run was bad (156 of 1872 objects exact, 0 of 120 stories);
  the fix was written looking at that corpus, so the score after it (1872 of 1872) is **not evidence**.
  Both runs are in `eval/history.json`, verbatim.
* **The reader accepts a listed grammar and eight listed spellings.** Anything else is reported as
  `unparsed` and the state is degraded to `TO_CONFIRM`: safe, but not useful until a person rewrites
  the entry.
* **Identity is the email of the commit.** Anyone who can commit with another agent's email is that
  agent, as far as the log can tell. Signed commits are not used.
* **History rewritten after publication** (a forced update of the shared branch) is out of scope: the
  tool reads the history it is given.
* **What is said outside the document leaves no trace.** The pack shows the discipline of the document,
  not the absence of other channels.
* **One machine.** Everything was run on Windows 11, Python 3.12.10, git 2.51.0. Two rebuilds in two
  folders give the same bytes there. The outputs that are compared cite commits by position, not by
  hash, so that they do not depend on git's hashing; whether the commit hashes of the test repositories
  are the same on another system is `[TO CONFIRM]`, and the word "deterministic" is not used for them.
* **Arbitration is as good as its rule file.** Three rules are shipped; most real conflicts would fall
  through to a human, which is the intended behaviour.

## 6. Evidence standard, requirement by requirement

| Req. | Where | Open points |
|---|---|---|
| E1 | this repository: `coord/`, `PROTOCOL.md`, MIT licence, tag `v2.0.0-freeze` | the tag `v2.0.0` is not placed: it waits for the blind run |
| E2 | ten scenario folders, S01 to S10, run by `scenarios/run_all.py`; negative: S04, S05, S06 | - |
| E3 | `python scenarios/run_all.py --json reports/scenarios.json`; `python -m unittest discover -s tests -t .` | - |
| E4 | `.github/workflows/ci.yml`; minimum git version 2.32 declared | never executed; runner image digest and action pins `[TO CONFIRM]` |
| E5 | `tools/rebuild.py`, `reports/rebuild.json`, `tests/test_determinism.py` | one machine; commit hashes across systems `[TO CONFIRM]` |
| E6 | `MANIFEST.sha256` (`python tools/manifest.py --check`) | a manifest cannot hold the hash of the commit that contains it: the message of the tag records the hash of the manifest at the freeze |
| E7 | `tests/test_hygiene.py` | scan report not produced; customer statement not applicable (no customer data exists here) |
| E8 | `SYNTHETIC.md`; banner as first line of `README.md` | synthetic mark on the avatar image: not checked by this pack, `[TO CONFIRM]` |
| E9 | this file | - |
| E10 | `MODEL.md` | - |
