"""The commands a reader runs: lint, status, sentinel, deps, arbitrate, submit - their exit codes, their
first lines, and what they refuse to say."""
import hashlib
import json
import unittest

from coord import arbitrate, deps, fixture, gitlog, sentinel, state as state_mod, submit
from corpus import render
from tests.helpers import RULES, RepoCase, run, story


def cli(module: str, *args) -> tuple[int, str]:
    return run(["-m", module, *args])


class LintAndStatus(RepoCase):
    def test_lint_ok_and_failed(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        code, out = cli("coord.lint", "--repo", self.repo(b))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("lint: OK - 0 error(s), 0 warning(s) in 3 commit(s), as of commit 3"), out)
        b.decide("bruno", p)                                   # not the owner
        repo = self.repo(b)
        code, out = cli("coord.lint", "--repo", repo)
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("lint: FAILED - 1 error(s)"), out)
        self.assertIn("fix:", out)
        sha = fixture.head_sha(repo)[:12]
        self.assertIn(sha, out)                                # the offending commit is cited by hash too ...
        code, out = cli("coord.lint", "--repo", repo, "--no-sha")
        self.assertNotIn(sha, out)                             # ... unless asked for an output that is the same everywhere
        code, out = cli("coord.lint", "--repo", repo, "--json")
        self.assertEqual(json.loads(out)["findings"][0]["class"], "invalid")

    def test_warnings_do_not_fail_the_lint(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("carla", p)                                       # not asked: no effect
        code, out = cli("coord.lint", "--repo", self.repo(b))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("lint: OK - 0 error(s), 1 warning(s)"), out)

    def test_a_repository_that_cannot_be_read_is_a_failure_in_the_first_line(self):
        for module in ("coord.lint", "coord.status"):
            code, out = cli(module, "--repo", self.tmp / "nothing-here")
            self.assertEqual(code, 2, module)
            self.assertIn("FAILED - the repository could not be read", out.splitlines()[0])

    def test_status_names_who_is_waited_for_and_its_as_of(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        h = b.handoff("ines", "dario", {"build": "412"})
        repo = self.repo(b)
        code, out = cli("coord.status", "--repo", repo, "--json", "--no-sha")
        sm = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(sm["as_of"], {"commit_index": 4, "committed_utc": "2026-02-02T08:51:00Z"})
        self.assertEqual(sm["pending_by_agent"], {"carla": [f"ACK {p}"], "dario": [f"RECEIPT {h}"]})
        self.assertEqual(sm["release_gate"], "BLOCKED")
        self.assertNotIn("head", sm)
        code, text = cli("coord.status", "--repo", repo)
        self.assertTrue(text.startswith("status as of commit 4 (2026-02-02T08:51:00Z), head " + fixture.head_sha(repo)[:12]), text)
        self.assertLessEqual(len(text.splitlines()), 12)        # terse: a handful of lines

    def test_state_command_writes_the_same_state_as_the_library(self):
        b = story()
        b.propose("ines", ["bruno"], "Pour slab B2.")
        repo = self.repo(b)
        out_file = self.tmp / "state.json"
        code, _ = cli("coord.state", "--repo", repo, "--out", out_file)
        self.assertEqual(code, 0)
        self.assertEqual(out_file.read_text(encoding="utf-8"), state_mod.derive(gitlog.read(repo), RULES).to_json())
        self.assertNotIn(b"\r\n", out_file.read_bytes())


class Sentinel(RepoCase):
    def test_diff_names_each_anchor(self):
        self.assertEqual(sentinel.diff({"build": "2417", "tag": "v3"}, {"build": "2471", "tag": "v3"}),
                         [{"anchor": "build", "handoff": "2417", "receipt": "2471"}])
        self.assertEqual(sentinel.diff({"build": "1"}, {"build": "1", "tag": "v3"}), [{"anchor": "tag", "handoff": None, "receipt": "v3"}])
        self.assertEqual(sentinel.diff({"build": "1"}, {"build": "1"}), [])
        self.assertEqual(sentinel.diff({"build": "0412"}, {"build": "412"})[0]["anchor"], "build")     # compared as written

    def test_schema_validator(self):
        schema = sentinel.load_schema("handoff")
        good = {"schema": "coord/handoff/1", "id": "ines-1", "by": "ines", "to": "bruno", "as_of": "2026-02-02T09:00:00+01:00",
                "anchors": {"build": "412"}}
        self.assertEqual(sentinel.validate(good, schema), [])
        self.assertTrue(sentinel.validate({k: v for k, v in good.items() if k != "anchors"}, schema))
        self.assertTrue(sentinel.validate(dict(good, anchors={}), schema))
        self.assertTrue(sentinel.validate(dict(good, anchors={"build": 412}), schema))
        self.assertTrue(sentinel.validate(dict(good, extra="x"), schema))
        self.assertTrue(sentinel.validate([], schema))

    def test_check_file(self):
        expected = {"id": "ines-1", "by": "ines", "to": "bruno", "anchors": {"build": "412"}}
        good = dict(expected, schema="coord/handoff/1", as_of="2026-02-02T09:00:00+01:00")
        self.assertEqual(sentinel.check_file("handoff", expected, json.dumps(good).encode()), [])
        self.assertEqual(sentinel.check_file("handoff", expected, None), ["file is missing"])
        self.assertEqual(sentinel.check_file("handoff", expected, b"\xff\xfe"), ["file is not UTF-8 JSON"])
        bad = dict(good, anchors={"build": "413"})
        self.assertEqual(sentinel.check_file("handoff", expected, json.dumps(bad).encode()), ["'anchors' in the file differs from the entry"])

    def test_the_files_written_with_the_entries_are_valid(self):
        b = story()
        h = b.handoff("ines", "bruno", {"build": "412", "tag": "v1.4.0"})
        r = b.receipt("bruno", h, {"build": "412", "tag": "v1.4.0"})
        log, st = self.derive(b)
        self.assertEqual(sentinel.validate(json.loads(log.head_files[f"handoffs/{h}.json"]), sentinel.load_schema("handoff")), [])
        self.assertEqual(sentinel.validate(json.loads(log.head_files[f"receipts/{r}.json"]), sentinel.load_schema("receipt")), [])
        self.assertEqual(st.details["handoffs"][h]["file_problems"], [])
        code, out = cli("coord.sentinel", "--repo", self.repo(b))
        self.assertEqual((code, out.splitlines()[-1]), (0, "release gate: OPEN"))

    def test_an_entry_whose_file_says_something_else_is_a_mismatch(self):
        b = story()
        h = b.handoff("ines", "bruno", {"build": "412"})
        b.receipt("bruno", h, {"build": "412"})
        stream = render.stream(b.events)
        broken = stream.replace(b'"build": "412"', b'"build": "421"', 1)       # the hand-off file, not the entry
        self.assertNotEqual(stream, broken)
        st = state_mod.derive(gitlog.read(fixture.build_repo(broken, self.tmp / "file-mismatch.git")), RULES)
        self.assertEqual(st.status["handoffs"][h], "MISMATCH")
        self.assertEqual(st.release_gate, "BLOCKED")
        self.assertIn("V04", self.classes(st))


class Dependencies(RepoCase):
    def test_closing_cycle_and_head_cycles(self):
        active = [("b1", "p1", "p2"), ("b2", "p2", "p3")]
        self.assertEqual(deps.closing_cycle(active, "p1", "p3"), ["b1", "b2"])
        self.assertEqual(deps.closing_cycle(active, "p4", "p3"), [])
        edges = [{"block": "b1", "on": "p1", "refs": "p2", "active": True}, {"block": "b2", "on": "p2", "refs": "p1", "active": True},
                 {"block": "b3", "on": "p3", "refs": "p1", "active": False}]
        self.assertEqual(deps.head_cycles(edges), [["b1", "b2"]])
        self.assertEqual(deps.head_cycles(edges[:1] + [dict(edges[1], active=False)]), [])

    def test_a_chain_is_not_a_cycle_and_a_removed_block_breaks_one(self):
        b = story()
        a = b.propose("ines", ["dario"], "Inspect slab B2.")
        c = b.propose("bruno", ["dario"], "Strip formwork set 7.")
        d = b.propose("carla", ["dario"], "Pour pier cap 4.")
        b1 = b.block("ines", c, on=a)
        b.block("bruno", d, on=c)
        st = self.assert_gold(b)
        self.assertEqual(deps.graph(st)["cycles"], [])
        code, _ = cli("coord.deps", "--repo", self.repo(b))
        self.assertEqual(code, 0)
        b.unblock("ines", b1)
        b3 = b.block("carla", a, on=d)                           # would close the circle if b1 were still active
        st = self.assert_gold(b)
        self.assertEqual(deps.graph(st)["cycles"], [])
        self.assertNotIn("V06", self.classes(st))
        active = [i for i, status in st.status["blocks"].items() if status == "ACTIVE"]
        self.assertEqual([w["block"] for w in deps.graph(st)["who_blocks_whom"]], active)
        self.assertIn(b3, active)
        self.assertNotIn(b1, active)


class Register(RepoCase):
    def story(self):
        b = story()
        p = b.propose("ines", ["carla"], "Inspect slab B2.", resource="crane/2026-W08", klass="deadline", due="2026-02-20")
        q = b.propose("bruno", ["carla"], "Lift formwork set 7.", resource="crane/2026-W08", klass="deadline", due="2026-02-18")
        return b, p, q

    def test_register_is_append_only_and_idempotent(self):
        b, p, q = self.story()
        st = self.state(b)
        reg = self.tmp / "register"
        first = arbitrate.append(arbitrate.records(st), reg)
        self.assertEqual([(r["id"], r["rule"], r["outcome"], r["supersedes"]) for r in first], [("ARB-0001", "R-DUE", q, None)])
        before = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in reg.glob("*.json")}
        self.assertEqual(arbitrate.append(arbitrate.records(st), reg), [])            # nothing new: nothing written
        self.assertEqual({f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in reg.glob("*.json")}, before)
        rec = arbitrate.read_register(reg)[0]
        self.assertEqual((rec["schema"], rec["rules_version"], rec["rules_sha256"]), ("coord/arbitration/1", 1, RULES.sha256["arbitration"]))
        self.assertEqual(rec["as_of"], st.as_of)

    def test_a_record_is_never_overwritten(self):
        b, p, q = self.story()
        recs = arbitrate.records(self.state(b))
        reg = self.tmp / "register-with-a-gap"
        reg.mkdir()
        other = {"conflict": "u-1~v-1", "rule": "none", "outcome": "ESCALATE_TO_HUMAN", "id": "ARB-0002"}
        (reg / "ARB-0002.json").write_text(json.dumps(other), encoding="utf-8")       # ARB-0001 is gone: the next number is taken
        with self.assertRaises(FileExistsError):
            arbitrate.append(recs, reg)
        self.assertEqual(json.loads((reg / "ARB-0002.json").read_text(encoding="utf-8")), other)
        self.assertEqual(sorted(f.name for f in reg.iterdir()), ["ARB-0002.json"])

    def test_dissent_on_an_arbitration_is_kept_and_changes_nothing(self):
        b, p, q = self.story()
        a = b.arbitrate("carla", [p, q], "R-DUE", q)
        d = b.dissent("ines", a, "the inspection cannot wait")
        st = self.assert_gold(b)
        (rec,) = arbitrate.records(st)
        self.assertEqual((rec["outcome"], rec["dissents"]), (q, [d]))
        self.assertEqual(st.status["conflicts"], {f"{p}~{q}": "ARBITRATED"})
        self.assertEqual(st.status["disputes"], {})


class Submit(RepoCase):
    def setup_repo(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        base = b.tip
        b.ack("bruno", p, parent=base)
        nb = b.tip
        b.ack("carla", p, parent=base)
        nc = b.tip
        repo = fixture.build_repo(render.stream(b.events[:base]), self.tmp / f"submit{self._count}.git")
        type(self)._count += 1
        for n, who in ((nb, "bruno"), (nc, "carla")):
            fixture.append_stream(render.stream(b.events, select={n}, ref=f"refs/heads/cand-{who}",
                                                external={base: "refs/heads/main^0"}), repo)
        return repo

    def test_first_wins_second_is_refused_and_says_so(self):
        repo = self.setup_repo()
        before = fixture.head_sha(repo)
        ok, line = submit.submit(repo, "cand-bruno")
        self.assertTrue(ok)
        self.assertTrue(line.startswith("submit: OK"))
        moved = fixture.head_sha(repo)
        self.assertNotEqual(moved, before)
        ok, line = submit.submit(repo, "cand-carla")
        self.assertFalse(ok)
        self.assertTrue(line.startswith("submit: FAILED - rejected"))
        self.assertIn("NOT in the shared log", line)
        self.assertEqual(fixture.head_sha(repo), moved)           # a refused write leaves the log where it was
        self.assertEqual([e.id for e in gitlog.read(repo).entries], ["ines-1", "bruno-1"])

    def test_missing_candidate_and_command_exit_codes(self):
        repo = self.setup_repo()
        ok, line = submit.submit(repo, "cand-nobody")
        self.assertEqual((ok, line.startswith("submit: FAILED")), (False, True))
        self.assertEqual(cli("coord.submit", "--repo", repo, "--candidate", "cand-nobody")[0], 3)
        code, out = cli("coord.submit", "--repo", repo, "--candidate", "cand-bruno")
        self.assertEqual((code, out.startswith("submit: OK")), (0, True))
        code, out = cli("coord.submit", "--repo", repo, "--candidate", "cand-bruno")     # submitting the tip again moves nothing
        self.assertEqual(code, 0)
        code, out = cli("coord.submit", "--repo", repo, "--candidate", "cand-carla")
        self.assertEqual((code, out.splitlines()[0].startswith("submit: FAILED")), (3, True))


if __name__ == "__main__":
    unittest.main()
