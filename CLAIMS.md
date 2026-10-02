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
| "No meetings. No standups." | An absence in real work cannot be verified. What the pack shows is a protocol that does not require meetings, on synthetic stories. |
| "The status of any project: visible to her in 30 seconds via `git log`." | No time was measured and no real project is part of this repository. What exists is a command that derives the status of a synthetic story from its log (`coord/status.py`, S03). |
| "Each invocation is recorded in the git history of the placement repository; the trail is auditable end-to-end." | The pack calls no agent and no model (`MODEL.md`), so it holds no invocation and no trail of one. |
| "*The coordination document IS the meeting.*"; "without standups" (title of the thesis); "push it and we are aligned in five minutes" | The pack shows a protocol that does not require meetings. It cannot show that no meeting took place anywhere, and it measures no time to alignment. |
| "operates via specialist subagent invocations: `pm-agent`, `business-panel-experts`, `requirements-analyst`" | The pack calls no agent and no model (`MODEL.md`). |
| Degree, thesis of record, diploma, faculty advisor, class | Fields of the profile; this repository offers no evidence for or against them. |
| An independent number | The blind run was made once by a different hand on 2026-09-30 (`eval/BLIND_PROTOCOL.md`; `eval/history.json`, runs 6 to 8), but the gold of part A comes from the pack's own generator and reference: internal consistency on synthetic data. Part B, written by hand, exercised V04, V05 and the release gate only. |
| A green CI run | Published on 2026-10-02 as pull request #2; `.github/workflows/ci.yml` runs on GitHub-hosted runners and its results are on the pull request, not copied here. |
| The same commit hashes of the test repositories on another operating system | Verified on one machine only; see "Known limits". |
| A scan report for secrets and personal data (`reports/scan.json`) | Not produced in v2.0. `tests/test_hygiene.py` checks paths, names, addresses and domains, which is less than a scan. |

## 4. Profile text: not changed by this pack

The profile part of `README.md` - everything except the SYNTHETIC banner (its first line) and the section
between the two `proof-pack` markers - is byte for byte the page as it was before the pack: sha256
`158e4c9bf21b476becce1eb844cc75511c5b84eff1e313130d6d49a60df1cc59` with LF line endings, the page at commit `62065ee`,
checked by `tests/test_docs.py`.

An earlier commit of this branch (`5297a87`) had reworded two passages and removed two sentences. All four are
back word for word and in their place; the record is in `CHANGELOG.md`. Rewording the public profile is not a
decision of this pack: a sentence without evidence is listed in section 3 (or in section 2), and left as it is.

After the merge of the pack, the profile text on `main` is the one corrected by pull request #1 (week-1 review
of 2026-09-30, merge commit `6970d8e`): the thesis title, in the list of contributions and in the diploma. The
pack did not change it. Byte for byte it is now the page at commit `6970d8e`, sha256
`3288f8b200c6f5397581fa42453b2819a43d8948ac8888e91068d73bb3fcb0ae` with LF line endings, checked by `tests/test_docs.py`.

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
* **One machine.** Every run recorded here was on Windows 11, Python 3.12.10, git 2.51.0. Two rebuilds in two
  folders give the same bytes there. The outputs that are compared cite commits by position, not by
  hash, so that they do not depend on git's hashing; whether the commit hashes of the test repositories
  are the same on another system is `[TO CONFIRM]`, and the word "deterministic" is not used for them.
* **Arbitration is as good as its rule file.** Three rules are shipped; most real conflicts would fall
  through to a human, which is the intended behaviour.

## 6. Evidence standard, requirement by requirement

| Req. | Where | Open points |
|---|---|---|
| E1 | this repository: `coord/`, `PROTOCOL.md`, MIT licence, tag `v2.0.0-freeze` | the tag `v2.0.0` is not placed: the blind run was made (`eval/history.json`, runs 6 to 8); the decision to place it is [TO CONFIRM] |
| E2 | ten scenario folders, S01 to S10, run by `scenarios/run_all.py`; negative: S04, S05, S06 | - |
| E3 | `python scenarios/run_all.py --json reports/scenarios.json`; `python -m unittest discover -s tests -t .` | - |
| E4 | `.github/workflows/ci.yml`; minimum git version 2.32 declared | runs on GitHub-hosted runners since the publication of 2026-10-02 (pull request #2), results on the pull request; runner image digest and action pins `[TO CONFIRM]` |
| E5 | `tools/rebuild.py`, `reports/rebuild.json`, `tests/test_determinism.py` | one machine; commit hashes across systems `[TO CONFIRM]` |
| E6 | `MANIFEST.sha256` (`python tools/manifest.py --check`) | a manifest cannot hold the hash of the commit that contains it: the message of the tag records the hash of the manifest at the freeze |
| E7 | `tests/test_hygiene.py` | scan report not produced; customer statement not applicable (no customer data exists here) |
| E8 | `SYNTHETIC.md`; banner as first line of `README.md` | synthetic mark on the avatar image: not checked by this pack, `[TO CONFIRM]` |
| E9 | this file | - |
| E10 | `MODEL.md` | - |
