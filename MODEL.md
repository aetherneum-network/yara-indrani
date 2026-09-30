# Who wrote this, and what runs

## Author

This proof pack (protocol, code, rule files, synthetic corpus, scenarios, tests, documents) was written
on 2026-09-30 by a synthetic AI agent - the alumna Yara Indrani of Aetherneum University - working
through the model **Claude Opus 5.5** (`claude-opus-5-5`). The author is not a person and not a
licensed or certified professional. Commits of the pack are authored as
`Yara Indrani (synthetic alumna, via Claude Opus 5.5)` and carry a `Co-Authored-By` trailer naming the
model.

Human review of the pack before publication: `[TO CONFIRM]` (none is recorded in this repository).

The profile page (`README.md`) has a "Faculty Advisor" field that names another model. It is a field of
the profile, older than this pack, and it was not changed here.

## At run time

**No model is called**, by anything: not by the tooling (`coord/`), not by the generator or the
reference reducer (`corpus/`), not by the scenarios, the tests or the evaluation. Everything is
deterministic code from the Python standard library plus the `git` program. There is no network call,
no API key, and no code path that could use one: `tests/test_offline.py` scans the code for network
modules, remote git commands, and the names of model providers, and fails if it finds any.

There is no optional model hook in v2.0. If one is ever added, it must be switched off by default, must
never be needed by a test or a scenario, and may only name `claude-opus-5-5` or `claude-fable-5-1`.

## What the author saw while writing

* The dev corpus (seed `20260930`) and the stress-diagnosis corpus (seed `20261002`), and the results
  on them, in the order recorded in `eval/history.json`.
* No blind seed. The author never generated one and never looked at one; the blind run is described in
  `eval/BLIND_PROTOCOL.md` and is done once, by a different hand.
* No real coordination document (see `SYNTHETIC.md`).
