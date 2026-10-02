# coord/1 - a coordination document as protocol

*Version 1 (pack v2.0). Written for this repository by a synthetic AI agent. Every example team, agent
and company is fictitious.*

One markdown file, `COORD.md`, in a git repository. Every entry is appended in its own commit by the
agent who writes it. The state of the coordination is **derived from the commit history**, never from
what somebody remembers and never from the latest text of the file alone.

This file is the whole contract: a reader who has only `PROTOCOL.md` and `templates/COORD.md` must be
able to write cycles that the tooling reads back correctly.

## 1. Files of a coordination repository

| path | content |
|---|---|
| `COORD.md` | header, agents, append-only log of entries |
| `handoffs/<handoff entry id>.json` | what the sender hands over (schema `schemas/handoff.schema.json`) |
| `receipts/<receipt entry id>.json` | what the recipient actually received (schema `schemas/receipt.schema.json`) |

The shared log is the branch `main` of the repository. An entry is "in the log" when its commit can be
reached from `main`, and not before.

## 2. `COORD.md`

```
# COORD - <team title>

protocol: coord/1

## Agents

- ines | Inès Carrà | ines@portoluna.example | site lead
- bruno | Bruno Šťastný | bruno@portoluna.example | structures

## Log

### PROPOSE ines-1
- by: ines
- to: bruno
- as_of: 2026-03-02T09:10:00+01:00
- text: Pour slab B2 on Thursday.

### ACK bruno-1
- by: bruno
- refs: ines-1
- as_of: 2026-03-02T09:31:00+01:00
- note: formwork inspected
```

* **Agents.** One line per agent: `- id | full name | email | role`. The id is lowercase ASCII
  (`[a-z][a-z0-9]*`). The email is the one the agent commits with. A new agent is a new line at the end
  of the section. A second line with an id already in use is a violation (V08).
* **Entries.** A heading `### <TYPE> <id>` followed by field lines `- key: value`. The id is
  `<agent id>-<n>` with `n` a positive integer chosen by that agent (its own counter); the agent part
  must be the `by` of the entry. An entry ends at the next heading or at the end of the file.
* **Lists** (`to`, `refs`) are comma-separated. **Anchors** are `key=value` pairs separated by `;`.
* **`as_of`** is the author's clock, ISO 8601 with a UTC offset (`2026-03-02T09:10:00+01:00`). It is
  information for readers. It never orders anything: order comes from commits (section 5).
* **Encoding.** UTF-8, LF line endings. Names keep their accents.
* **Tolerated spellings.** The grammar above is the canonical one. The reader also accepts, because
  each is unambiguous: field lines that start with `*`; keys in bold (`- **by**: ines`); keys with
  capital letters (`- By: ines`); the type in lower case (`### propose ines-1`); a colon after the type
  (`### PROPOSE: ines-1`); the id before the type (`### ines-1 PROPOSE`); a level-4 heading
  (`#### PROPOSE ines-1`); lists separated by `;`. Anything else in the log is *not read and not
  guessed*: it is reported as `unparsed` and the state is degraded (section 5).
* **Append-only.** A commit adds entries at the end of the file and changes nothing else. To change
  something said before, write a new entry that refers to it (`supersedes`, a new `RECEIPT`, a `DISSENT`).

## 3. Entry types

Fields common to every entry: `by` (author), `as_of`. "Required" below lists the other mandatory fields.

| type | required | optional | meaning |
|---|---|---|---|
| `PROPOSE` | `to`, `text` | `supersedes`, `resource`, `class`, `due` | opens a proposal; `to` = agents whose consent is required (not the author) |
| `ACK` | `refs` | `note` | consent to / acknowledgement of the referenced entries |
| `DISSENT` | `refs` (one) | `text` (the reason) | disagreement with the referenced entry; without a reason it has no substance (section 4.2) |
| `BLOCK` | `refs` (one: the blocked proposal) | `on` (the proposal it waits for), `to`, `text` | the proposal cannot be decided until the block is removed |
| `UNBLOCK` | `refs` (one: the block) | `text` | asks to remove the block |
| `FREEZE` | `scope`, `to` | `text` | halts the release of `scope` |
| `LIFT` | `refs` (one: the freeze) | `text` | asks to lift the freeze |
| `DECIDE` | `refs` (one: the proposal) | `text` | the owner declares the proposal decided |
| `HANDOFF` | `to` (one), `anchors` | `text` | hands work over, with fixed points (`build=412; tag=v1.4.0`) |
| `RECEIPT` | `refs` (one: the handoff), `anchors` | `text` | the recipient states what it received |
| `ARBITRATE` | `refs` (two proposals), `rule`, `outcome` | `text` | a third agent records the arbitration of a resource conflict |

`PROPOSE` fields for arbitration: `resource` (what is claimed, e.g. `designer/2026-W14`), `class`
(`safety`, `deadline` or `routine`; default `routine`), `due` (`YYYY-MM-DD`).

## 4. What each entry does

**Consents are counted per agent, latest response wins.** The owner of an object is the `by` of the
entry that created it.

### 4.1 Proposals

* Required consents: every agent in `to`.
* `ACK` with the proposal in `refs`, by a required agent: that agent consents.
* `DISSENT` on the proposal by a required agent: that agent does not consent. A `DISSENT` by any agent
  other than the owner whose `text` has substance opens a **dispute** (section 4.2).
* Status, first match wins:
  `SUPERSEDED` (the owner wrote a `PROPOSE` with `supersedes: <this id>`) ·
  `DECIDED` (an effective `DECIDE`) ·
  `BLOCKED` (a block on it is not removed) ·
  `DISPUTED` (a dispute on it is not closed) ·
  `ALIGNED` (every required agent's latest response is an `ACK`) ·
  `PROPOSED`.
* `DECIDE` is **effective only if**, in the history the deciding commit descends from, the proposal is
  `ALIGNED`. Otherwise the proposal is *not* decided and the entry is a violation (V05). A later `ACK`
  does not repair an earlier `DECIDE`: the owner writes a new one.
* `supersedes` starts a new proposal with its own consents. Nothing carries over.

### 4.2 Disputes and the nature of a response

Before anything is counted, each response is classified (`rules/dissent_nature.json`, first match wins):

| response | nature |
|---|---|
| `DISSENT` whose `text` is empty or one of `none`, `n/a`, `no objection`, `-` | `none` - not a dispute, and **not a consent** either |
| any other `DISSENT` | `dissent` |
| `ACK` with a `note` that has substance | `note` - a consent with a remark, not a dispute |
| `ACK` | `none` |

A dispute is `OPEN` until the owner of the proposal answers it (`ACK` with the dissent id in `refs`):
`ANSWERED`. It is `CLOSED` when the dissenting agent writes an `ACK` with the proposal id or its own
dissent id in `refs`. Only an `ACK` on the proposal itself is a consent.

### 4.3 Blocks

* Consents required to remove a block: its author and every agent in its `to`.
* `UNBLOCK` by a required agent counts as that agent's consent. The others consent with an `ACK` whose
  `refs` holds the `UNBLOCK` id; a `DISSENT` on the `UNBLOCK` withdraws a consent.
* Status: `ACTIVE` until an `UNBLOCK` exists and every required consent is present; then `REMOVED`
  (final). To block again, write a new `BLOCK`.
* `on` draws a dependency edge *blocking proposal -> blocked proposal*. A cycle of active edges is a
  violation (V06). A `BLOCK` whose `on` proposal is already decided in the history it descends from is a
  stale claim (V07); the block still stands until it is removed with its consents.

### 4.4 Freezes

* Consents required to lift: the author of the `FREEZE` and every agent in its `to`.
* `LIFT` by a required agent counts as that agent's consent; the others `ACK` the `LIFT`.
* Status: `FROZEN` until a `LIFT` exists and every required consent is present; then `LIFTED` (final).

### 4.5 Handoffs and receipts

* `HANDOFF` adds `handoffs/<its id>.json` in the same commit; `RECEIPT`, written by the recipient, adds
  `receipts/<its id>.json`. Each file repeats the anchors of its entry.
* Status: `AWAITING_RECEIPT` · `MISMATCH` (the anchors of the latest receipt differ from the handoff,
  or a file is missing or disagrees with its entry) · `RECEIVED`.
* A receipt that does not match is a violation (V04) and cites both files. The correction is a new
  `RECEIPT`, never an edit.

### 4.6 Release gate

`BLOCKED` while any freeze is not `LIFTED` or any handoff is not `RECEIVED`; otherwise `OPEN`
(`rules/freeze.json`).

### 4.7 Arbitration

Two proposals by different owners with the same `resource` are in **conflict**. `rules/arbitration.json`
is an ordered list of rules; the first that matches gives the outcome, and if none matches the outcome
is `ESCALATE_TO_HUMAN`. An `ARBITRATE` entry is written by an agent who owns neither proposal and cites
the rule and the outcome (`rule: none`, `outcome: ESCALATE_TO_HUMAN` when no rule applies). If the cited
rule and outcome are not what the rule file gives, the entry has no effect and is a violation (V11).
Conflict status: `OPEN` · `ARBITRATED` · `ESCALATED` · `WITHDRAWN` (one of the two was superseded
before any arbitration). A `DISSENT` on an `ARBITRATE` entry is kept in the arbitration record; it does
not change the outcome.

## 5. Order, authorship, doubt

* **Order** is the order of commits: parents before children; among commits with no order between them
  (two branches later merged), the earlier committer time in UTC first. The position of an entry in
  the file and its `as_of` never decide order.
* **Authorship.** An entry is authentic when the email of the commit that added it is the email of its
  `by` agent in the first `## Agents` line for that id. Otherwise it is *doubtful* (V02). Entries by
  an id that has two agent lines (V08) and entries later modified in place (V01) are doubtful too.
* **What the history saw.** Every entry is evaluated on the commits its own commit descends from (plus
  the entries above it in the same commit), not on commits of a branch it had not seen. So a `DECIDE`
  written on a branch that did not hold the last consent is not effective, even after the merge.
* **Opposite answers from two branches.** If one agent wrote an `ACK` and a `DISSENT` on the same entry
  in two commits that had not seen each other, the log does not say which one stands: both are
  *doubtful* (finding `ambiguous`) until the agent appends one answer after the merge.
* **Writing to the shared log.** `main` only moves forward: a commit is accepted when it descends from
  the current tip. A writer whose commit was made on an older tip is refused, merges, and submits
  again (`python -m coord.submit`, a local compare-and-swap; no remote is involved). Until the write is
  accepted and read back, the entry is not "sent".
* **Doubt is reported, never resolved by the tool.** A status that asserts something
  (`ALIGNED`, `DECIDED`, `SUPERSEDED`, `REMOVED`, `LIFTED`, `RECEIVED`, `ANSWERED`, `CLOSED`,
  `ARBITRATED`, `ESCALATED`, `WITHDRAWN`) is replaced by `TO_CONFIRM` when any entry it rests on is
  doubtful. If a block of the log cannot be read, or an entry that restrains others (`DISSENT`, `BLOCK`,
  `FREEZE`, `HANDOFF`) is invalid, the state is *degraded*: every asserting status becomes `TO_CONFIRM`
  and the release gate is `BLOCKED`.

## 6. Violations reported by the linter

| id | name | pinned to |
|---|---|---|
| V01 | `modified_in_place` - a past entry, agent line, header or handoff/receipt file changed or removed | the changing commit, the entry id (`agent:<id>`, `header`) |
| V02 | `author_mismatch` - the commit author is not the `by` agent | the commit, the entry id |
| V03 | `handoff_without_receipt` | the handoff commit, the handoff id |
| V04 | `anchor_mismatch` - handoff and receipt disagree on a fixed point | the receipt commit, the handoff id |
| V05 | `gate_without_consents` - `DECIDE` on a proposal that is not aligned (missing consent, open dispute, active block) | the commit, the `DECIDE` id |
| V06 | `dependency_cycle` | the commit of the block that closes the cycle, the block ids joined by `+` |
| V07 | `stale_pending` - a block waits for something already decided | the commit, the block id |
| V08 | `duplicate_agent_id` | the commit, `agent:<id>` |
| V09 | `order_by_local_time` - an entry inserted above existing entries instead of appended | the commit, the entry id |
| V10 | `corrupted_accents` - text that was UTF-8 read as a single-byte encoding | the commit, the entry id |
| V11 | `arbitration_without_rule` - cited rule or outcome is not what the rule file gives | the commit, the `ARBITRATE` id |

Structural findings with the same severity: `unparsed` (a block of the log that is not an entry),
`malformed` (an entry that breaks the grammar of sections 2-3), `invalid` (a well-formed entry that the
rules refuse, for example a `DECIDE` by someone who is not the owner), `ambiguous` (opposite answers by
one agent from two branches, section 5). Warnings, which do not fail the lint: `no_effect`,
`empty_dissent`, `as_of_unanchored`, `unknown_field`.

## 7. What the protocol does not do

* It sees only what is in the repository. A decision taken elsewhere leaves no trace here.
* It does not judge the content of a `text` or a `note`: a disagreement written inside an `ACK` note is
  a note. Disagreement is a `DISSENT`.
* History rewritten after publication (force-push, rebase of published commits) is out of scope for
  version 1: the tooling reads the history it is given.
* An `ARBITRATE` entry is checked against the rule file in use when the tool runs.
* Arbitration outcomes are recorded; they do not by themselves stop a later `DECIDE`.
