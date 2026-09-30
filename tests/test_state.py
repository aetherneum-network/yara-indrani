"""Transitions: every status of PROTOCOL.md section 4 is reached by a story, and on every story the tool
agrees with the independent reference reducer."""
import unittest

from coord import state as state_mod
from corpus import render
from tests.helpers import RULES, RepoCase, story


class Proposals(RepoCase):
    def test_proposed_aligned_decided(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        self.assertEqual(self.assert_gold(b).status["proposals"][p], "PROPOSED")
        b.ack("bruno", p)
        self.assertEqual(self.assert_gold(b).status["proposals"][p], "PROPOSED")
        b.ack("carla", p, note="pump booked")
        self.assertEqual(self.assert_gold(b).status["proposals"][p], "ALIGNED")
        b.decide("ines", p)
        st = self.assert_gold(b)
        self.assertEqual(st.status["proposals"][p], "DECIDED")
        self.assertEqual(st.details["proposals"][p]["consents"], {"bruno": "ACK", "carla": "ACK"})

    def test_dispute_open_answered_closed(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        d = b.dissent("bruno", p, "the cure time is too short")
        st = self.assert_gold(b)
        self.assertEqual((st.status["proposals"][p], st.status["disputes"][d]), ("DISPUTED", "OPEN"))
        b.ack("ines", d, note="two more days added")
        st = self.assert_gold(b)
        self.assertEqual((st.status["proposals"][p], st.status["disputes"][d]), ("DISPUTED", "ANSWERED"))
        b.ack("bruno", p)
        st = self.assert_gold(b)
        self.assertEqual((st.status["proposals"][p], st.status["disputes"][d]), ("ALIGNED", "CLOSED"))

    def test_dissenter_can_withdraw_its_own_dissent(self):
        b = story()
        p = b.propose("ines", ["bruno", "carla"], "Pour slab B2.")
        d = b.dissent("dario", p, "the east ramp is closed that day")          # dario was not asked: a dispute all the same
        b.ack("bruno", p)
        b.ack("carla", p)
        self.assertEqual(self.assert_gold(b).status["proposals"][p], "DISPUTED")
        b.ack("dario", d)
        st = self.assert_gold(b)
        self.assertEqual((st.status["proposals"][p], st.status["disputes"][d]), ("ALIGNED", "CLOSED"))

    def test_supersede(self):
        b = story()
        p1 = b.propose("ines", ["bruno"], "Pour slab B2 on Thursday.")
        b.ack("bruno", p1)
        p2 = b.propose("ines", ["bruno"], "Pour slab B2 on Friday.", supersedes=p1)
        st = self.assert_gold(b)
        self.assertEqual(st.status["proposals"], {p1: "SUPERSEDED", p2: "PROPOSED"})
        self.assertEqual(st.details["proposals"][p1]["superseded_by"], [p2])

    def test_only_the_owner_supersedes(self):
        b = story()
        p1 = b.propose("ines", ["bruno"], "Pour slab B2 on Thursday.")
        b.propose("bruno", ["ines"], "Pour slab B2 on Friday.", supersedes=p1)
        st = self.state(b)
        self.assertEqual(st.status["proposals"][p1], "PROPOSED")
        self.assertIn("invalid", [f.cls for f in st.findings])


class BlocksAndFreezes(RepoCase):
    def test_block_active_then_removed(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        blk = b.block("carla", p, to=["dario"], text="the pump is booked elsewhere")
        st = self.assert_gold(b)
        self.assertEqual((st.status["proposals"][p], st.status["blocks"][blk]), ("BLOCKED", "ACTIVE"))
        u = b.unblock("carla", blk, text="pump freed")
        self.assertEqual(self.assert_gold(b).status["blocks"][blk], "ACTIVE")
        b.ack("dario", u)
        st = self.assert_gold(b)
        self.assertEqual((st.status["proposals"][p], st.status["blocks"][blk]), ("ALIGNED", "REMOVED"))

    def test_block_with_only_its_author_is_removed_by_its_author(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        blk = b.block("bruno", p, text="formwork not inspected")
        b.unblock("bruno", blk)
        self.assertEqual(self.assert_gold(b).status["blocks"][blk], "REMOVED")

    def test_stale_block_is_reported(self):
        b = story()
        p1 = b.propose("ines", ["bruno"], "Inspect formwork set 7.")
        b.ack("bruno", p1)
        b.decide("ines", p1)
        p2 = b.propose("ines", ["bruno"], "Pour slab B2.")
        blk = b.block("carla", p2, on=p1, text="waits for the inspection")
        st = self.assert_gold(b)
        self.assertEqual(st.violations, [{"class": "V07", "commit_index": 6, "target": blk}])

    def test_freeze_frozen_then_lifted_and_the_release_gate(self):
        b = story()
        f = b.freeze("ines", "release", ["bruno"], text="crack in pier cap 4")
        st = self.assert_gold(b)
        self.assertEqual((st.status["freezes"][f], st.release_gate), ("FROZEN", "BLOCKED"))
        self.assertIn("REL-FREEZE", st.release_reasons[0])
        lift = b.lift("ines", f)
        self.assertEqual(self.assert_gold(b).status["freezes"][f], "FROZEN")
        b.ack("bruno", lift)
        st = self.assert_gold(b)
        self.assertEqual((st.status["freezes"][f], st.release_gate, st.release_reasons), ("LIFTED", "OPEN", []))


class Handoffs(RepoCase):
    def test_awaiting_mismatch_received(self):
        b = story()
        h = b.handoff("ines", "bruno", {"build": "412", "tag": "v1.4.0"})
        st = self.assert_gold(b)
        self.assertEqual((st.status["handoffs"][h], st.release_gate), ("AWAITING_RECEIPT", "BLOCKED"))
        self.assertEqual(self.classes(st), ["V03"])
        b.receipt("bruno", h, {"build": "421", "tag": "v1.4.0"})
        st = self.assert_gold(b)
        self.assertEqual((st.status["handoffs"][h], st.release_gate, self.classes(st)), ("MISMATCH", "BLOCKED", ["V04"]))
        b.receipt("bruno", h, {"build": "412", "tag": "v1.4.0"})                  # a new receipt, the old one stays
        st = self.assert_gold(b)
        self.assertEqual((st.status["handoffs"][h], st.release_gate), ("RECEIVED", "OPEN"))
        self.assertEqual(self.classes(st), ["V04"])                                # the mismatch stays in the record
        self.assertEqual(len(st.details["handoffs"][h]["receipts"]), 2)

    def test_missing_anchor_is_a_mismatch(self):
        b = story()
        h = b.handoff("ines", "bruno", {"build": "412", "tag": "v1.4.0"})
        b.receipt("bruno", h, {"build": "412"})
        st = self.assert_gold(b)
        self.assertEqual(st.status["handoffs"][h], "MISMATCH")
        self.assertEqual(st.details["handoffs"][h]["diff"], [{"anchor": "tag", "handoff": "v1.4.0", "receipt": None}])

    def test_file_changed_after_the_hand_off_is_caught(self):
        b = story()
        h = b.handoff("ines", "bruno", {"build": "412"})
        b.receipt("bruno", h, {"build": "412"})
        b.tamper("ines", h, {"kind": "file", "anchors": {"build": "413"}})
        st = self.assert_gold(b)
        self.assertIn("V01", self.classes(st))
        self.assertEqual(st.status["handoffs"][h], "TO_CONFIRM")


class Conflicts(RepoCase):
    def build(self):
        b = story()
        p = b.propose("ines", ["carla"], "Inspect slab B2.", resource="crane/2026-W08", klass="deadline", due="2026-02-20")
        q = b.propose("bruno", ["carla"], "Lift formwork set 7.", resource="crane/2026-W08", klass="deadline", due="2026-02-18")
        return b, p, q

    def test_open_arbitrated_and_the_rule_is_cited(self):
        b, p, q = self.build()
        cid = f"{p}~{q}"
        st = self.assert_gold(b)
        self.assertEqual(st.status["conflicts"], {cid: "OPEN"})
        self.assertEqual(st.arbitrations, [{"conflict": cid, "rule": "R-DUE", "outcome": q}])
        b.arbitrate("carla", [p, q], "R-DUE", q)
        self.assertEqual(self.assert_gold(b).status["conflicts"], {cid: "ARBITRATED"})

    def test_arbitration_citing_the_wrong_rule_or_winner_is_not_effective(self):
        for rule, winner in (("R-FIRST", "p"), ("R-DUE", "p"), ("R-SAFETY", "q"), ("none", "q")):
            b, p, q = self.build()
            a = b.arbitrate("carla", [p, q], rule, p if winner == "p" else q)     # the rule file gives R-DUE -> q
            st = self.assert_gold(b)
            self.assertEqual(st.status["conflicts"], {f"{p}~{q}": "OPEN"}, rule)
            self.assertEqual(st.violations, [{"class": "V11", "commit_index": 4, "target": a}], rule)

    def test_an_owner_cannot_arbitrate_its_own_conflict(self):
        b, p, q = self.build()
        b.arbitrate("ines", [p, q], "R-DUE", q)
        st = self.state(b)
        self.assertEqual(st.status["conflicts"], {f"{p}~{q}": "OPEN"})
        self.assertIn("invalid", [f.cls for f in st.findings])

    def test_uncovered_case_is_escalated_never_decided(self):
        b = story()
        p = b.propose("ines", ["carla"], "Quarantine batch 27.", resource="review/2026-W08", klass="safety")
        q = b.propose("bruno", ["carla"], "Quarantine polisher 4.", resource="review/2026-W08", klass="safety")
        st = self.assert_gold(b)
        self.assertEqual(st.arbitrations, [{"conflict": f"{p}~{q}", "rule": "none", "outcome": "ESCALATE_TO_HUMAN"}])
        b.arbitrate("carla", [p, q], "none", "ESCALATE_TO_HUMAN")
        self.assertEqual(self.assert_gold(b).status["conflicts"], {f"{p}~{q}": "ESCALATED"})

    def test_conflict_withdrawn_when_a_claim_is_superseded(self):
        b, p, q = self.build()
        b.propose("bruno", ["carla"], "Lift formwork set 7 next week.", supersedes=q)
        self.assertEqual(self.assert_gold(b).status["conflicts"], {f"{p}~{q}": "WITHDRAWN"})

    def test_same_owner_or_different_resource_is_no_conflict(self):
        b = story()
        b.propose("ines", ["carla"], "Inspect slab B2.", resource="crane/2026-W08")
        b.propose("ines", ["carla"], "Inspect pier cap 4.", resource="crane/2026-W08")
        b.propose("bruno", ["carla"], "Lift formwork set 7.", resource="crane/2026-W09")
        self.assertEqual(self.assert_gold(b).status["conflicts"], {})


class OrderAndDocument(RepoCase):
    def test_log_and_document_agree_on_a_clean_story(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p)
        b.decide("ines", p)
        log, st = self.derive(b)
        doc = state_mod.from_document(log.head_files["COORD.md"], RULES)
        self.assertEqual((doc.status, doc.release_gate, doc.source), (st.status, st.release_gate, "document"))
        self.assertEqual(doc.as_of, {"entries": 3})

    def test_entry_inserted_above_is_ordered_by_its_commit_not_by_its_place(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        d = b.decide("ines", p)
        a = b.ack("bruno", p, insert_before=d)                   # written after the DECIDE, placed above it
        log, st = self.derive(b)
        self.assert_gold(b, st)
        self.assertEqual([e.id for e in log.entries], [p, d, a])
        self.assertEqual(sorted(self.classes(st)), ["V05", "V09"])
        self.assertEqual(st.status["proposals"][p], "ALIGNED")    # the consent is in the log; the decision was not valid
        doc = state_mod.from_document(log.head_files["COORD.md"], RULES)
        self.assertEqual(doc.status["proposals"][p], "DECIDED")   # the document alone is fooled

    def test_as_of_field_never_orders_anything(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.decide("ines", p, as_of="2026-02-02T23:00:00+01:00")
        b.ack("bruno", p, as_of="2026-02-02T06:00:00+01:00")     # claims to be earlier than the DECIDE
        st = self.assert_gold(b)
        self.assertEqual(st.status["proposals"][p], "ALIGNED")
        self.assertEqual(self.classes(st), ["V05"])

    def test_line_endings_do_not_change_the_state(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Pour slab B2.")
        b.ack("bruno", p, note="già fatto")
        b.decide("ines", p)
        lf = self.state(b).as_dict()
        b.events[0]["style"] = {"eol": "crlf"}
        self.assertIn(b"\r\n", render.stream(b.events))
        crlf = self.state(b).as_dict()
        self.assertEqual((crlf["state"], crlf["violations"], crlf["findings"]), (lf["state"], lf["violations"], lf["findings"]))

    def test_accents_survive_and_corrupted_ones_are_reported(self):
        b = story()
        p = b.propose("ines", ["bruno"], "Verificare la quota già rilevata: è così.")
        log, st = self.derive(b)
        self.assertEqual(st.details["proposals"][p]["text"], "Verificare la quota già rilevata: è così.")
        self.assertEqual(st.violations, [])
        self.assertTrue(any(not a.name.isascii() for a in log.roster.values()), "the synthetic world has accented names")
        bad = b.ack("bruno", p, note="già fatto", mojibake=True)
        st = self.assert_gold(b)
        self.assertEqual(st.violations, [{"class": "V10", "commit_index": 3, "target": bad}])

    def test_state_json_has_no_commit_hash_in_it(self):
        b = story()
        b.propose("ines", ["bruno"], "Pour slab B2.")
        log, st = self.derive(b)
        text = st.to_json()
        self.assertTrue(all(c.sha not in text and c.sha[:12] not in text for c in log.commits))
        self.assertEqual(st.as_of["commit_index"], 2)


if __name__ == "__main__":
    unittest.main()
