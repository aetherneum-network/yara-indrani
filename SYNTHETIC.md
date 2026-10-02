# What is synthetic here: everything

**Yara Indrani is a synthetic alumna (an AI agent) of Aetherneum University. She is not a person and not a
certified project manager.** Every team, agent, company, build number and
decision in this repository is fictitious. This file says what the data in this repository is, where it comes from,
and what it cannot show.

## The data

| What | Where it comes from | Real? |
|---|---|---|
| The three companies: Cantiere Portoluna S.r.l., Editrice Meridiana S.r.l., Laboratorio Ottico Fiordaliso | invented for this repository, listed in `corpus/world.py` | no |
| Their agents (names, roles, time zones, email addresses) | invented, same file; every address is under a `.example` domain | no |
| Proposals, consents, dissents, blocks, freezes, hand-offs, build numbers, due dates, decisions | written by `scenarios/stories.py` (ten stories, by hand) and by `corpus/generate.py` (120 stories per seed, from a seeded random generator) | no |
| The git histories the tooling reads | built on the spot from fast-import streams, with fixed dates and the invented identities above; they exist only in a build folder | no |
| The "gold" the tooling is scored against | computed by `corpus/reference_reducer.py` from the list of events that generated each story | not applicable |

The coordination cycles were **written for this repository**. They are not excerpts of any real
project's documents, in any form: not copied, not paraphrased, not anonymised, not "sanitised". No real
coordination document was opened, searched or used to build this pack.

## What this means for the numbers

Every number in this repository measures **internal consistency on synthetic data**: the state the
tooling derives from a generated git history, compared with the state an independent piece of code
computes from the events that generated that history. No number here says anything about a real team,
a real project or a real deadline.

Seeds the author of the pack generated and looked at: `20260930` (dev) and `20261002` (stress
diagnosis). Any other seed belongs to the blind run (`eval/BLIND_PROTOCOL.md`), which is done by a
different hand.

## Known limits of the fiction

* The invented stories are tidy in ways real work is not: every entry is about one thing, nobody
  answers outside the document, and the defects are the eleven kinds the generator knows how to plant.
* The names of the three companies were invented without consulting any register: whether a real
  company carries one of these names is `[TO CONFIRM]`. The `.example` domains cannot be registered
  by anyone.
* What happens outside the document leaves no trace in the log. The pack shows the discipline of the
  document; it cannot show that no other channel was used.
