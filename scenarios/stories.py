"""The ten scenario stories, written for this repository. Every team, agent and company is invented.

Each function returns the events of a story and what its author declares the outcome must be. The
declarations are literals written by hand: they are neither computed by the tooling nor by the reference
reducer, so a scenario passes only when three independent things agree.

`scenarios/make_inputs.py` turns these stories into the `input/` and `expected/` folders.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus import world                       # noqa: E402
from corpus.events import StoryBuilder         # noqa: E402


def _builder(company: str, ids: list[str], start: str, step: int = 17) -> StoryBuilder:
    team, agents = world.team(company, ids)
    return StoryBuilder(team, agents, start, step_minutes=step)


def s01():
    """Portoluna: three clean cycles."""
    b = _builder("portoluna", ["ines", "bruno", "carla", "dario"], "2026-03-02T08:00:00Z")
    p1 = b.propose("ines", ["bruno", "carla"], "Pour slab B2 on Thursday.")
    b.ack("bruno", p1, note="formwork inspected")
    b.ack("carla", p1)
    b.decide("ines", p1)
    p2 = b.propose("bruno", ["ines", "dario"], "Load-test crane pad C before the pour.")
    b.ack("ines", p2)
    d = b.dissent("dario", p2, "the test needs the safety review first")
    b.ack("bruno", d, note="review booked before the test")
    b.ack("dario", p2, note="fine with the review in place")
    b.decide("bruno", p2)
    h = b.handoff("ines", "bruno", {"build": "412", "tag": "v1.4.0"}, text="pour sequence, revision 4")
    b.receipt("bruno", h, {"build": "412", "tag": "v1.4.0"})
    declared = {
        "proposals": {p1: "DECIDED", p2: "DECIDED"}, "disputes": {d: "CLOSED"}, "handoffs": {h: "RECEIVED"},
        "release_gate": "OPEN", "violations": [], "lint_ok": True,
    }
    return b.events, declared


def s02():
    """Meridiana: a build number arrives with two digits transposed."""
    b = _builder("meridiana", ["livia", "oscar", "nadia"], "2026-03-09T08:30:00Z")
    p = b.propose("livia", ["oscar", "nadia"], "Send to proof the ebook build.")
    b.ack("oscar", p)
    b.ack("nadia", p, note="cover file is the final one")
    b.decide("livia", p)
    h = b.handoff("livia", "oscar", {"build": "2417", "tag": "v3.2.0"}, text="ebook build for the store")
    r = b.receipt("oscar", h, {"build": "2471", "tag": "v3.2.0"})
    declared = {
        "proposals": {p: "DECIDED"}, "handoffs": {h: "MISMATCH"}, "release_gate": "BLOCKED",
        "violations": [{"class": "V04", "commit_index": 7, "target": h}],
        "cites": [f"handoffs/{h}.json", f"receipts/{r}.json"],
        "diff": [{"anchor": "build", "handoff": "2417", "receipt": "2471"}], "lint_ok": False,
    }
    return b.events, declared


def s03():
    """Fiordaliso: the same question asked twice, with a commit in between."""
    b = _builder("fiordaliso", ["teo", "uma", "vera"], "2026-03-16T09:00:00Z")
    p = b.propose("teo", ["uma", "vera"], "Recalibrate lens bench 3.")
    b.ack("uma", p, note="counts match mine")
    first = b.last                              # the first question is asked here
    b.ack("vera", p)
    declared = {
        "first": {"as_of": {"commit_index": 3, "committed_utc": "2026-03-16T09:34:00Z"}, "proposals": {p: "PROPOSED"},
                  "waiting_for": {"vera": [f"ACK {p}"]}},
        "second": {"as_of": {"commit_index": 4, "committed_utc": "2026-03-16T09:51:00Z"}, "proposals": {p: "ALIGNED"},
                   "waiting_for": {"teo": [f"DECIDE {p}"]}},
        "split_after": first,
    }
    return b.events, declared


def s04():
    """Portoluna: a decision rewritten in place - and the correct way to change it."""
    def base():
        b = _builder("portoluna", ["ines", "bruno", "carla"], "2026-03-23T07:45:00Z")
        p = b.propose("ines", ["bruno", "carla"], "Close access to the east ramp on Thursday.")
        b.ack("bruno", p)
        b.ack("carla", p, note="deliveries moved to the site gate")
        b.decide("ines", p)
        return b, p

    wrong, p = base()
    wrong.tamper("ines", p, {"kind": "field", "field": "text", "value": "Close access to the east ramp on Friday."})
    right, p = base()
    p2 = right.propose("ines", ["bruno", "carla"], "Close access to the east ramp on Friday.", supersedes=p)
    right.ack("bruno", p2)
    right.ack("carla", p2, note="deliveries moved again")
    right.decide("ines", p2)
    declared = {
        "rewritten": {"proposals": {p: "TO_CONFIRM"}, "violations": [{"class": "V01", "commit_index": 6, "target": p}],
                      "lint_ok": False},
        "superseded": {"proposals": {p: "SUPERSEDED", p2: "DECIDED"}, "violations": [], "lint_ok": True},
    }
    return {"rewritten": wrong.events, "superseded": right.events}, declared


def s05():
    """Meridiana: an entry says 'by: nadia' but the commit is livia's."""
    b = _builder("meridiana", ["livia", "marco", "nadia"], "2026-03-30T08:10:00Z")
    p = b.propose("livia", ["marco", "nadia"], "Lock the cover of title 12.")
    b.ack("marco", p)
    forged = b.ack("nadia", p, commit_as="livia")
    b.decide("livia", p)
    declared = {
        "proposals": {p: "TO_CONFIRM"}, "violations": [{"class": "V02", "commit_index": 4, "target": forged}],
        "doubtful": [forged], "named_in_by": "nadia", "commit_author": "livia@meridiana.example", "lint_ok": False,
        "document_alone_says": {p: "DECIDED"},
    }
    return b.events, declared


def s06():
    """Fiordaliso: a freeze lifted with two consents out of three."""
    b = _builder("fiordaliso", ["teo", "uma", "vera"], "2026-04-06T08:00:00Z")
    f = b.freeze("teo", "lens-release", ["uma", "vera"], text="coating batch 27 is out of tolerance")
    lift = b.lift("teo", f, text="batch re-measured")
    b.ack("uma", lift)
    first = b.last
    b.ack("vera", lift, note="re-measured on my bench too")
    declared = {
        "two_of_three": {"freezes": {f: "FROZEN"}, "release_gate": "BLOCKED", "missing": ["vera"],
                         "waiting_for": {"vera": [f"ACK {lift} (to lift {f})"]}},
        "three_of_three": {"freezes": {f: "LIFTED"}, "release_gate": "OPEN", "missing": []},
        "split_after": first,
    }
    return b.events, declared


def s07():
    """Portoluna: twenty notes, six true dissents, two of them answered."""
    b = _builder("portoluna", ["ines", "bruno", "carla", "dario", "elio", "fiona"], "2026-04-13T07:00:00Z", step=9)
    four = ["bruno", "carla", "dario", "elio"]
    things = ["slab B2", "pier cap 4", "the east ramp", "crane pad C", "formwork set 7", "the drainage trench"]
    reasons = ["the sequence breaks the cure time", "the figure does not match my count", "this needs the safety review first",
               "the slot is already taken that day", "the tolerance is wrong for this batch", "two steps are swapped"]
    proposals, dissents, status = [], [], {}
    for i, thing in enumerate(things):
        p = b.propose("ines", four, f"Inspect {thing}.")
        proposals.append(p)
        against = four[i % 4]
        for a in four:
            if a == against:
                dissents.append(b.dissent(a, p, reasons[i]))
            else:
                b.ack(a, p, note=world.NOTES[(i + four.index(a)) % len(world.NOTES)])      # 6 x 3 = 18 notes
        status[p] = "DISPUTED"
    p7 = b.propose("ines", ["bruno", "carla"], "Survey retaining wall R3.")
    b.ack("bruno", p7, note="checked against the drawing")                                  # note 19
    b.ack("carla", p7, note="fine from my side")                                            # note 20
    p8 = b.propose("ines", ["dario", "elio", "fiona"], "Sign off scaffold tower 2.")
    b.dissent("dario", p8, "none")                  # three dissents with nothing in them: not disputes, not consents
    b.dissent("elio", p8, "n/a")
    b.dissent("fiona", p8, "no objection")
    b.ack("ines", dissents[0])                      # two answers, plain
    b.ack("ines", dissents[1])
    status.update({p7: "ALIGNED", p8: "PROPOSED"})
    disputes = {d: "OPEN" for d in dissents}
    disputes[dissents[0]] = disputes[dissents[1]] = "ANSWERED"
    declared = {
        "proposals": status, "disputes": disputes, "notes": 20, "true_dissents": 6, "answered": 2, "open_disputes": 4,
        "empty_dissents": 3, "violations": [],
    }
    return b.events, declared


def s08():
    """Meridiana: A blocks B, B blocks C, C blocks A."""
    b = _builder("meridiana", ["livia", "marco", "nadia"], "2026-04-20T08:20:00Z")
    a = b.propose("livia", ["marco"], "Approve the spring catalogue.")
    bb = b.propose("marco", ["nadia"], "Re-set chapter 4.")
    c = b.propose("nadia", ["livia"], "Release the back-cover copy.")
    b1 = b.block("livia", bb, on=a, text="chapter 4 must wait for the catalogue")
    b2 = b.block("marco", c, on=bb, text="the copy quotes chapter 4")
    b3 = b.block("nadia", a, on=c, text="the catalogue prints the copy")
    declared = {
        "proposals": {a: "BLOCKED", bb: "BLOCKED", c: "BLOCKED"},
        "blocks": {b1: "ACTIVE", b2: "ACTIVE", b3: "ACTIVE"},
        "violations": [{"class": "V06", "commit_index": 7, "target": f"{b1}+{b2}+{b3}"}],
        "cycle": [b1, b2, b3],
        "who_blocks_whom": [["livia", "marco"], ["marco", "nadia"], ["nadia", "livia"]],
        "edges": [[a, bb], [bb, c], [c, a]],
    }
    return b.events, declared


def s09():
    """Fiordaliso: three conflicts on shared resources, then one rule is added."""
    b = _builder("fiordaliso", ["teo", "uma", "vera", "walt", "xenia", "yuri"], "2026-04-27T08:00:00Z")
    a1 = b.propose("teo", ["vera"], "Calibrate the interferometer.", resource="calibration-rig/2026-W18", klass="deadline",
                   due="2026-05-05")
    a2 = b.propose("uma", ["vera"], "Re-measure filter lot F2.", resource="calibration-rig/2026-W18", klass="deadline",
                   due="2026-05-12")
    t1 = b.propose("vera", ["teo"], "Re-measure prism order 88.", resource="data-analyst/2026-W18", klass="deadline",
                   due="2026-05-08")
    t2 = b.propose("walt", ["teo"], "Accept mould set M5.", resource="data-analyst/2026-W18", klass="deadline",
                   due="2026-05-08")
    s1 = b.propose("xenia", ["teo"], "Quarantine coating batch 27.", resource="security-review/2026-W18", klass="safety")
    s2 = b.propose("yuri", ["teo"], "Quarantine polisher 4.", resource="security-review/2026-W18", klass="safety")
    arb = b.arbitrate("vera", [a1, a2], "R-DUE", a1, text="earlier due date")
    objection = b.dissent("uma", arb, "the lot expires before the 12th")
    ca, ct, cs = f"{a1}~{a2}", f"{t1}~{t2}", f"{s1}~{s2}"
    declared = {
        "conflicts": {ca: "ARBITRATED", ct: "OPEN", cs: "OPEN"},
        "rules_v1": {ca: ["R-DUE", a1], ct: ["none", "ESCALATE_TO_HUMAN"], cs: ["none", "ESCALATE_TO_HUMAN"]},
        "rules_v2": {ca: ["R-DUE", a1], ct: ["R-TIE-FIRST", t1], cs: ["none", "ESCALATE_TO_HUMAN"]},
        "only_change": ct, "recorded_dissent": objection, "violations": [],
    }
    return b.events, declared


def s10():
    """Portoluna: two agents answer at the same time; the second write is refused, then merged."""
    b = _builder("portoluna", ["ines", "bruno", "carla"], "2026-05-04T08:00:00Z")
    p = b.propose("ines", ["bruno", "carla"], "Issue drawings for pier cap 4.")
    base = b.tip
    ack_bruno = b.ack("bruno", p, note="checked against the drawing", parent=base)
    n_bruno = b.tip
    ack_carla = b.ack("carla", p, note="counts match mine", parent=base)
    n_carla = b.tip
    n_merge = b.merge("carla", [n_carla, n_bruno])
    b.events[-1]["style"] = {"merge_order": "branch"}       # carla's document keeps her entry above bruno's
    declared = {
        "base": base, "bruno": n_bruno, "carla": n_carla, "merge": n_merge,
        "after_bruno": {"proposals": {p: "PROPOSED"}, "entries": [p, ack_bruno]},
        "after_rejection": {"proposals": {p: "PROPOSED"}, "entries": [p, ack_bruno], "not_in_log": ack_carla},
        "after_merge": {"proposals": {p: "ALIGNED"}, "entries": [p, ack_bruno, ack_carla],
                        "document_order": [p, ack_carla, ack_bruno]},
    }
    return b.events, declared


STORIES = {
    "S01_state_from_log": s01, "S02_transposed_anchor": s02, "S03_as_of_moves": s03, "S04_rewrite_in_place": s04,
    "S05_author_mismatch": s05, "S06_lift_two_of_three": s06, "S07_notes_are_not_dissents": s07,
    "S08_dependency_cycle": s08, "S09_arbitration_rules": s09, "S10_concurrent_entries": s10,
}
