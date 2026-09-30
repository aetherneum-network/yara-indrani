"""The never-event: an item declared aligned, unblocked, lifted or decided without the required consents
being present in the log. Each test tries to make it happen; the tooling must refuse every time."""
import unittest

from coord import fixture, gitlog, state as state_mod
from corpus import render
from corpus.reference_reducer import Unsupported, reduce_events
from tests.helpers import RULES, RepoCase, story


class NeverEvent(RepoCase):
    def check(self, b, kind: str, oid: str, *, expect: str | None = None, cls: str | None = None,
              consents_are_in_the_log: bool = False):
        st = self.state(b)
        if consents_are_in_the_log:        # ALIGNED is then true; what must not be asserted is the decision
            self.assertNotEqual(st.status[kind][oid], "DECIDED")
        else:
            self.assert_never_asserted(st, kind, oid)
        if expect is not None:
            self.assertEqual(st.status[kind][oid], expect)
        if cls is not None:
            self.assertIn(cls, [f.cls for f in st.findings])
        try:
            gold = reduce_events(b.events)
        except Unsupported:
            return st                      # the reference reducer refuses the story: only the tool is checked
        self.assertEqual(st.as_dict()["state"], gold["state"])
        self.assertEqual(st.violations, gold["violations"])
        return st

    def test_decide_without_any_consent(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.decide("ines", p)
        st = self.check(b, "proposals", p, expect="PROPOSED", cls="V05")
        self.assertEqual(st.details["proposals"][p]["missing"], ["bruno", "carla"])

    def test_decide_with_two_consents_out_of_three(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla", "dario"], "Pour slab B2.")
        b.ack("bruno", p)
        b.ack("carla", p)
        b.decide("ines", p)
        st = self.check(b, "proposals", p, expect="PROPOSED", cls="V05")
        self.assertEqual(st.details["proposals"][p]["missing"], ["dario"])

    def test_consent_written_by_someone_else(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        forged = b.ack("carla", p, commit_as="ines")
        b.decide("ines", p)
        st = self.check(b, "proposals", p, expect="TO_CONFIRM", cls="V02")
        self.assertEqual(st.doubtful, {forged: ["author"]})

    def test_dissent_rewritten_into_a_consent(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("carla", p)
        d = b.dissent("bruno", p, "the cure time is too short")
        b.tamper("ines", d, {"kind": "retype", "type": "ACK"})
        b.decide("ines", p)
        log, st = self.derive(b)
        self.assert_never_asserted(st, "proposals", p)
        self.assertIn("V01", self.classes(st))
        self.assertIn("V05", self.classes(st))
        # the latest text of the document, read alone, would have been fooled
        self.assertEqual(state_mod.from_document(log.head_files["COORD.md"], RULES).status["proposals"][p], "DECIDED")

    def test_consent_rewritten_after_the_decision(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        a = b.ack("bruno", p)
        b.decide("ines", p)
        b.tamper("ines", a, {"kind": "field", "field": "note", "value": "agreed, and also to pier cap 4"})
        self.check(b, "proposals", p, expect="TO_CONFIRM", cls="V01")

    def test_unblock_without_the_consent_of_everyone_named(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        blk = b.block("bruno", p, to=["carla", "dario"], text="formwork not inspected")
        u = b.unblock("bruno", blk, text="inspected now")
        b.ack("carla", u)
        b.decide("ines", p)
        st = self.check(b, "blocks", blk, expect="ACTIVE", cls="V05")
        self.assert_never_asserted(st, "proposals", p)
        self.assertEqual(st.status["proposals"][p], "BLOCKED")
        self.assertEqual(st.details["blocks"][blk]["missing"], ["dario"])

    def test_unblock_requested_by_someone_else_needs_the_blocker(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        blk = b.block("bruno", p, text="formwork not inspected")
        b.unblock("ines", blk, text="I say it is fine")
        st = self.check(b, "blocks", blk, expect="ACTIVE")
        self.assertEqual(st.details["blocks"][blk]["missing"], ["bruno"])

    def test_lift_with_two_consents_out_of_three(self):
        b = story()
        f = b.freeze("ines", "release", ["bruno", "carla"], text="crack in pier cap 4")
        lift = b.lift("ines", f)
        b.ack("bruno", lift)
        st = self.check(b, "freezes", f, expect="FROZEN")
        self.assertEqual(st.release_gate, "BLOCKED")
        self.assertEqual(st.details["freezes"][f]["missing"], ["carla"])

    def test_lift_consent_by_an_agent_not_named_in_the_freeze(self):
        b = story()
        f = b.freeze("ines", "release", ["bruno", "carla"], text="crack in pier cap 4")
        lift = b.lift("ines", f)
        b.ack("bruno", lift)
        b.ack("dario", lift)                       # dario is not one of the required agents
        st = self.check(b, "freezes", f, expect="FROZEN")
        self.assertEqual(st.release_gate, "BLOCKED")

    def test_lift_refused_by_a_required_agent(self):
        b = story()
        f = b.freeze("ines", "release", ["bruno", "carla"], text="crack in pier cap 4")
        lift = b.lift("ines", f)
        b.ack("bruno", lift)
        b.dissent("carla", lift, "the crack is still there")
        st = self.check(b, "freezes", f, expect="FROZEN")
        self.assertEqual(st.release_gate, "BLOCKED")

    def test_consent_withdrawn_by_a_later_dissent(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        b.ack("carla", p)
        b.dissent("bruno", p, "the forecast changed: frost on Thursday")
        b.decide("ines", p)
        self.check(b, "proposals", p, expect="DISPUTED", cls="V05")

    def test_consent_by_an_agent_who_was_not_asked(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        b.ack("dario", p)
        st = self.check(b, "proposals", p, expect="PROPOSED")
        self.assertIn("no_effect", [f.cls for f in st.findings])

    def test_owner_consents_to_its_own_proposal(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("ines", p)
        self.check(b, "proposals", p, expect="PROPOSED")

    def test_consent_given_to_another_proposal(self):
        b = story()
        p1 = b.propose("ines", ["bruno"], "Pour slab B2.")
        p2 = b.propose("ines", ["bruno"], "Strip formwork set 7.")
        b.ack("bruno", p2)
        b.decide("ines", p1)
        st = self.check(b, "proposals", p1, expect="PROPOSED", cls="V05")
        self.assertEqual(st.status["proposals"][p2], "ALIGNED")

    def test_consent_to_something_that_does_not_exist(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", "ines-9")
        st = self.check(b, "proposals", p, expect="PROPOSED")
        self.assertIn("invalid", [f.cls for f in st.findings])

    def test_empty_dissent_is_not_a_consent(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.dissent("bruno", p, "no objection")
        b.decide("ines", p)
        st = self.check(b, "proposals", p, expect="PROPOSED", cls="V05")
        self.assertEqual(st.status["disputes"], {})

    def test_answered_dissent_is_not_a_consent(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        d = b.dissent("bruno", p, "the cure time is too short")
        b.ack("ines", d, note="two more days added")
        b.decide("ines", p)
        st = self.check(b, "proposals", p, expect="DISPUTED", cls="V05")
        self.assertEqual(st.status["disputes"][d], "ANSWERED")

    def test_consents_do_not_carry_over_to_the_superseding_proposal(self):
        b = story()
        p1 = b.propose("ines", ["bruno", "carla"], "Pour slab B2 on Thursday.")
        b.ack("bruno", p1)
        b.ack("carla", p1)
        p2 = b.propose("ines", ["bruno", "carla"], "Pour slab B2 and B3 on Thursday.", supersedes=p1)
        b.decide("ines", p2)
        self.check(b, "proposals", p2, expect="PROPOSED", cls="V05")

    def test_decide_by_someone_who_is_not_the_owner(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        b.ack("carla", p)
        b.decide("bruno", p)
        st = self.check(b, "proposals", p, expect="ALIGNED", consents_are_in_the_log=True)
        self.assertIn("invalid", [f.cls for f in st.findings])

    def test_decide_with_an_active_block(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        b.block("carla", p, text="the pump is booked elsewhere")
        b.decide("ines", p)
        self.check(b, "proposals", p, expect="BLOCKED", cls="V05")

    def test_two_agent_lines_with_the_same_id(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        second = dict(b.agents["bruno"], name="Bruno (second account)", email="bruno.second@portoluna.example")
        b.dup_agent("ines", second)
        b.ack("bruno", p, commit_as="bruno")
        b.decide("ines", p)
        self.check(b, "proposals", p, expect="TO_CONFIRM", cls="V08")

    def test_decide_written_on_a_branch_that_had_not_seen_the_last_consent(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        base = b.tip
        b.ack("carla", p, parent=base)
        n_carla = b.tip
        b.decide("ines", p, parent=base)           # ines decides without carla's consent in her history
        n_ines = b.tip
        b.merge("ines", [n_ines, n_carla])
        self.check(b, "proposals", p, expect="ALIGNED", cls="V05", consents_are_in_the_log=True)

    def test_opposite_answers_from_two_branches_are_not_resolved_by_the_tool(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        base = b.tip
        b.ack("bruno", p, parent=base)
        n1 = b.tip
        b.dissent("bruno", p, "not before the inspection", parent=base)
        n2 = b.tip
        b.merge("bruno", [n2, n1])
        st = self.state(b)
        self.assert_never_asserted(st, "proposals", p)
        self.assertIn("ambiguous", [f.cls for f in st.findings])
        self.assertTrue(all("ambiguous" in why for why in st.doubtful.values()))
        self.assertEqual(len(st.doubtful), 2)

    def test_receipt_written_by_someone_who_is_not_the_recipient(self):
        b = story()
        h = b.handoff("ines", "bruno", {"build": "412"})
        b.receipt("carla", h, {"build": "412"})
        st = self.check(b, "handoffs", h)
        self.assertEqual(st.status["handoffs"][h], "AWAITING_RECEIPT")
        self.assertEqual(st.release_gate, "BLOCKED")

    def test_invalid_restraining_entry_degrades_every_assertion(self):
        b = story()
        p1 = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p1)
        b.decide("ines", p1)
        p2 = b.propose("ines", ["bruno"], "Strip formwork set 7.")
        b.dissent("ines", p2, "I changed my mind")        # an owner cannot dissent on its own proposal
        st = self.state(b)
        self.assertEqual(st.status["proposals"][p1], "TO_CONFIRM")
        self.assertEqual(st.face["proposals"][p1], "DECIDED")
        self.assertEqual(st.release_gate, "BLOCKED")
        self.assertTrue(st.degraded)

    def test_a_block_of_the_log_that_cannot_be_read_degrades_every_assertion(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        b.ack("carla", p)
        b.decide("ines", p)
        stream = render.stream(b.events)
        broken = stream.replace(b"### ACK carla-1", b"### AKC carla-1")     # same length, no longer an entry type
        self.assertNotEqual(stream, broken)
        log = gitlog.read(fixture.build_repo(broken, self.tmp / "broken.git"))
        st = state_mod.derive(log, RULES)
        self.assert_never_asserted(st, "proposals", p)
        self.assertEqual(st.release_gate, "BLOCKED")
        self.assertTrue({"unparsed", "malformed"} & {f.cls for f in st.findings})

    def test_the_same_story_without_the_attack_is_decided(self):
        """Control: the refusals above are not a tool that never says DECIDED."""
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        b.ack("bruno", p)
        b.ack("carla", p)
        b.decide("ines", p)
        st = self.assert_gold(b)
        self.assertEqual(st.status["proposals"][p], "DECIDED")
        self.assertEqual(st.violations, [])


if __name__ == "__main__":
    unittest.main()
