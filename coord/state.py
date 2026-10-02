"""State of a coordination, derived from the commit history (PROTOCOL.md sections 4-5).

The entries are replayed in log order through a small machine whose decisions come from the rule files
(`rules/*.json`). Three things keep it from ever asserting more than the log holds:

* a `DECIDE` is judged on the history its commit descends from, not on what arrived later or elsewhere;
* a status that asserts something becomes `TO_CONFIRM` when any entry it rests on is doubtful;
* if part of the log cannot be read, or a restraining entry is invalid, every asserting status becomes
  `TO_CONFIRM` and the release gate is `BLOCKED`.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from coord import arbitrate, gitlog, sentinel
from coord.deps import closing_cycle
from coord.parse import ESCALATE, RESTRAINING, Entry, Finding, parse_doc
from coord.rules import RuleError, RuleSet, load

KINDS = ("proposals", "blocks", "freezes", "handoffs", "disputes", "conflicts")
ASSERTING = {
    "proposals": ("ALIGNED", "DECIDED", "SUPERSEDED"),
    "blocks": ("REMOVED",),
    "freezes": ("LIFTED",),
    "handoffs": ("RECEIVED",),
    "disputes": ("ANSWERED", "CLOSED"),
    "conflicts": ("ARBITRATED", "ESCALATED", "WITHDRAWN"),
}
TO_CONFIRM = "TO_CONFIRM"
CLOSED = ("DECIDED", "SUPERSEDED")


@dataclass
class _Proposal:
    id: str
    by: str
    required: list[str]
    order: int
    text: str
    resource: str | None
    klass: str | None
    due: str | None
    responses: dict[str, bool] = field(default_factory=dict)
    decided_by: str | None = None
    superseders: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    disputes: list[str] = field(default_factory=list)
    basis: set[str] = field(default_factory=set)

    def claim(self) -> dict:
        return {"id": self.id, "by": self.by, "class": self.klass, "due": self.due}


@dataclass
class _Gate:                      # a block or a freeze: something that stays closed until every consent is in
    id: str
    kind: str
    by: str
    required: list[str]
    target: str                   # block: the blocked proposal; freeze: the scope
    on: str | None = None
    requests: list[str] = field(default_factory=list)
    consent: dict[str, bool] = field(default_factory=dict)
    open: bool = False
    basis: set[str] = field(default_factory=set)


@dataclass
class _Handoff:
    id: str
    by: str
    to: str
    anchors: dict[str, str]
    receipts: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)     # (id, by, anchors)
    basis: set[str] = field(default_factory=set)


@dataclass
class _Dispute:
    id: str
    proposal: str
    by: str
    text: str
    answered: bool = False
    closed: bool = False
    basis: set[str] = field(default_factory=set)


@dataclass
class _Conflict:
    id: str
    p: str
    q: str
    arbitrations: list[tuple[str, bool, str, str]] = field(default_factory=list)      # (entry, effective, rule, outcome)
    dissents: list[str] = field(default_factory=list)
    basis: set[str] = field(default_factory=set)


@dataclass
class Verdict:
    """What the history an entry descends from says about it."""
    valid: bool
    reason: str = ""
    effective: bool | None = None     # DECIDE, ARBITRATE
    stale: bool = False               # BLOCK waiting for something already closed


class Machine:
    _TARGETS = {"proposal": "proposal", "dispute": "dissent", "unblock": "unblock", "lift": "lift", "arbitrate": "arbitrate"}

    def __init__(self, rules: RuleSet):
        self.rules = rules
        self.kind: dict[str, str] = {}
        self.proposals: dict[str, _Proposal] = {}
        self.gates: dict[str, _Gate] = {}
        self.handoffs: dict[str, _Handoff] = {}
        self.disputes: dict[str, _Dispute] = {}
        self.conflicts: dict[str, _Conflict] = {}
        self.request_of: dict[str, str] = {}
        self.arbitration_of: dict[str, str] = {}
        self.natures: dict[str, tuple[str, str, str]] = {}      # response id -> (type, nature, rule id)

    # -- face-value statuses ----------------------------------------------------------------------------
    def proposal_status(self, pid: str) -> str:
        p = self.proposals[pid]
        if p.superseders:
            return "SUPERSEDED"
        if p.decided_by:
            return "DECIDED"
        if any(not self.gates[b].open for b in p.blocks):
            return "BLOCKED"
        if any(not self.disputes[d].closed for d in p.disputes):
            return "DISPUTED"
        return "ALIGNED" if all(p.responses.get(a) for a in p.required) else "PROPOSED"

    def gate_status(self, gid: str) -> str:
        g = self.gates[gid]
        if g.kind == "block":
            return "REMOVED" if g.open else "ACTIVE"
        return "LIFTED" if g.open else "FROZEN"

    def handoff_status(self, hid: str) -> str:
        h = self.handoffs[hid]
        if not h.receipts:
            return "AWAITING_RECEIPT"
        return "RECEIVED" if h.receipts[-1][2] == h.anchors else "MISMATCH"

    def dispute_status(self, did: str) -> str:
        d = self.disputes[did]
        return "CLOSED" if d.closed else "ANSWERED" if d.answered else "OPEN"

    def conflict_status(self, cid: str) -> str:
        c = self.conflicts[cid]
        won = [a for a in c.arbitrations if a[1]]
        if won:
            return "ESCALATED" if won[0][3] == ESCALATE else "ARBITRATED"
        if "SUPERSEDED" in (self.proposal_status(c.p), self.proposal_status(c.q)):
            return "WITHDRAWN"
        return "OPEN"

    def missing(self, gid: str) -> list[str]:
        g = self.gates[gid]
        return [a for a in g.required if not g.consent.get(a)]

    def missing_consents(self, pid: str) -> list[str]:
        p = self.proposals[pid]
        return [a for a in p.required if not p.responses.get(a)]

    def why_not_aligned(self, pid: str) -> str:
        p = self.proposals[pid]
        parts = []
        if self.missing_consents(pid):
            parts.append("missing consent of " + ", ".join(self.missing_consents(pid)))
        open_blocks = [b for b in p.blocks if not self.gates[b].open]
        if open_blocks:
            parts.append("active block " + ", ".join(open_blocks))
        open_disputes = [d for d in p.disputes if not self.disputes[d].closed]
        if open_disputes:
            parts.append("dispute not closed " + ", ".join(open_disputes))
        return f"{pid} is {self.proposal_status(pid)}: " + "; ".join(parts)

    def active_edges(self) -> list[tuple[str, str, str]]:
        return [(g.id, g.on, g.target) for g in self.gates.values() if g.kind == "block" and g.on and not g.open]

    # -- responses ------------------------------------------------------------------------------------------
    def _facts(self, e: Entry, ref: str) -> tuple[str, set[str]]:
        kind = self.kind.get(ref)
        roles: set[str] = set()
        if kind is None:
            return "unknown", roles
        if kind == "proposal":
            p = self.proposals[ref]
            if p.by == e.by:
                roles.add("owner")
            if e.by in p.required:
                roles.add("required")
            if any(self.disputes[d].by == e.by for d in p.disputes):
                roles.add("dissenter")
        elif kind == "dispute":
            d = self.disputes[ref]
            if d.by == e.by:
                roles.add("author")
            if self.proposals[d.proposal].by == e.by:
                roles.add("proposal_owner")
        elif kind in ("unblock", "lift"):
            if e.by in self.gates[self.request_of[ref]].required:
                roles.add("required")
        return self._TARGETS.get(kind, "entry"), roles

    def effects(self, e: Entry) -> list[tuple[str, list[str], str]]:
        """(reference, effects, rule id) for each reference of an ACK or a DISSENT."""
        nature, _ = self.rules.nature(e.type, e.text)
        out = []
        for ref in e.refs:
            target, roles = self._facts(e, ref)
            then, rid = self.rules.effect(e.type, target, roles, nature)
            out.append((ref, then, rid))
        return out

    # -- judging an entry on the history it descends from -----------------------------------------------------
    def judge(self, e: Entry, known) -> Verdict:
        def bad(reason: str) -> Verdict:
            return Verdict(False, reason)

        if not known(e.by):
            return bad(f"'{e.by}' is not an agent of this document")
        t = e.type
        strangers = [a for a in e.to if not known(a)]
        if strangers:
            return bad(f"'to' names {', '.join(strangers)}: not an agent of this document")
        if t in ("ACK", "DISSENT"):
            for ref, then, rid in self.effects(e):
                if "invalid" in then:
                    return bad(f"{t} on {ref} is refused (rule {rid})")
            return Verdict(True)
        if t == "PROPOSE":
            if e.by in e.to:
                return bad("the author of a proposal cannot be in its 'to'")
            old = e.get("supersedes")
            if old is not None:
                if old not in self.proposals:
                    return bad(f"supersedes {old}, which is not a proposal this commit has seen")
                if self.proposals[old].by != e.by:
                    return bad(f"only the owner of {old} can supersede it")
                if self.proposal_status(old) == "SUPERSEDED":
                    return bad(f"{old} is already superseded")
            return Verdict(True)
        if t == "FREEZE":
            return Verdict(True)
        if t == "HANDOFF":
            return bad("a handoff to oneself") if e.to[0] == e.by else Verdict(True)
        ref = e.refs[0]
        if t == "BLOCK":
            if ref not in self.proposals:
                return bad(f"{ref} is not a proposal this commit has seen")
            if self.proposal_status(ref) in CLOSED:
                return bad(f"{ref} is already {self.proposal_status(ref)}")
            on = e.get("on")
            if on is None:
                return Verdict(True)
            if on not in self.proposals or on == ref:
                return bad(f"'on: {on}' is not another proposal this commit has seen")
            return Verdict(True, stale=self.proposal_status(on) in CLOSED)
        if t in ("UNBLOCK", "LIFT"):
            want = "block" if t == "UNBLOCK" else "freeze"
            if ref not in self.gates or self.gates[ref].kind != want:
                return bad(f"{ref} is not a {want} this commit has seen")
            return Verdict(True)
        if t == "DECIDE":
            if ref not in self.proposals:
                return bad(f"{ref} is not a proposal this commit has seen")
            if self.proposals[ref].by != e.by:
                return bad(f"only the owner of {ref} ({self.proposals[ref].by}) can decide it")
            status = self.proposal_status(ref)
            if status in CLOSED:
                return bad(f"{ref} is already {status}")
            if status == "ALIGNED":
                return Verdict(True, effective=True)
            return Verdict(True, self.why_not_aligned(ref), effective=False)
        if t == "RECEIPT":
            if ref not in self.handoffs:
                return bad(f"{ref} is not a handoff this commit has seen")
            if self.handoffs[ref].to != e.by:
                return bad(f"the receipt of {ref} must be written by its recipient ({self.handoffs[ref].to})")
            return Verdict(True)
        if t == "ARBITRATE":
            if any(r not in self.proposals for r in e.refs):
                return bad("both references must be proposals this commit has seen")
            p, q = sorted((self.proposals[r] for r in e.refs), key=lambda x: x.order)
            cid = f"{p.id}~{q.id}"
            if cid not in self.conflicts:
                return bad(f"{p.id} and {q.id} do not claim the same resource from different owners")
            if e.by in (p.by, q.by):
                return bad("an arbitration is written by an agent who owns neither proposal")
            if any(a[1] for a in self.conflicts[cid].arbitrations):
                return bad(f"{cid} is already arbitrated")
            if "SUPERSEDED" in (self.proposal_status(p.id), self.proposal_status(q.id)):
                return bad(f"{cid} is withdrawn: one of the proposals was superseded")
            rule, outcome = arbitrate.decide(self.rules.arbitration, p.claim(), q.claim())
            if (e.get("rule"), e.get("outcome")) == (rule, outcome):
                return Verdict(True, effective=True)
            return Verdict(True, f"cites rule {e.get('rule')} -> {e.get('outcome')}; the rule file gives {rule} -> {outcome}",
                           effective=False)
        raise RuleError(f"no judgement for entry type {t}")

    # -- applying an entry ----------------------------------------------------------------------------------
    def _settle(self, g: _Gate) -> None:
        if not g.open and g.requests and all(g.consent.get(a) for a in g.required):
            g.open = True

    def apply(self, e: Entry, v: Verdict) -> list[tuple[str, str, str, tuple[str, ...]]]:
        """Apply an entry with the verdict of its own history. Returns (class, target, detail, cites) notes."""
        notes: list[tuple[str, str, str, tuple[str, ...]]] = []
        t = e.type
        # what an object rests on is recorded even when the entry is refused
        if t in ("ACK", "DISSENT", "DECIDE"):
            for ref in e.refs:
                if ref in self.proposals:
                    self.proposals[ref].basis.add(e.id)
                if ref in self.request_of and t != "DECIDE":
                    self.gates[self.request_of[ref]].basis.add(e.id)
        if t == "ACK":
            for ref in e.refs:
                if ref in self.disputes:
                    self.disputes[ref].basis.add(e.id)
                if ref in self.proposals:
                    for d in self.proposals[ref].disputes:
                        if self.disputes[d].by == e.by:
                            self.disputes[d].basis.add(e.id)
        if not v.valid:
            return notes

        if t in ("ACK", "DISSENT"):
            nature, nrule = self.rules.nature(t, e.text)
            self.natures[e.id] = (t, nature, nrule)
            opened = False
            for ref, then, rid in self.effects(e):
                for eff in then:
                    if eff in ("consent_yes", "consent_no"):
                        if ref in self.proposals:
                            self.proposals[ref].responses[e.by] = eff == "consent_yes"
                        else:
                            g = self.gates[self.request_of[ref]]
                            g.consent[e.by] = eff == "consent_yes"
                            self._settle(g)
                    elif eff == "close_own_disputes":
                        for d in self.proposals[ref].disputes:
                            if self.disputes[d].by == e.by:
                                self.disputes[d].closed = True
                    elif eff == "close_dispute":
                        self.disputes[ref].closed = True
                    elif eff == "answer":
                        self.disputes[ref].answered = True
                    elif eff == "open_dispute":
                        self.disputes[e.id] = _Dispute(e.id, ref, e.by, e.text, basis={e.id})
                        self.proposals[ref].disputes.append(e.id)
                        opened = True
                    elif eff == "record_dissent":
                        self.conflicts[self.arbitration_of[ref]].dissents.append(e.id)
                    elif eff == "no_effect":
                        notes.append(("no_effect", e.id, f"{t} on {ref} changes nothing (rule {rid})", ()))
                    elif eff == "empty_dissent":
                        notes.append(("empty_dissent", e.id, f"a DISSENT with no substance is not a dispute, and not a "
                                                             f"consent either (rules {nrule}, {rid})", ()))
                    elif eff != "invalid":
                        raise RuleError(f"rule {rid}: unknown effect '{eff}'")
            self.kind[e.id] = "dispute" if opened else "entry"
        elif t == "PROPOSE":
            p = _Proposal(e.id, e.by, self.rules.required("decide", e.by, e.to), len(self.proposals), e.text,
                          e.get("resource"), e.get("class"), e.get("due"), basis={e.id})
            for q in self.proposals.values():
                if p.resource and q.resource == p.resource and q.by != p.by:
                    cid = f"{q.id}~{p.id}"
                    self.conflicts[cid] = _Conflict(cid, q.id, p.id, basis={q.id, p.id})
            old = e.get("supersedes")
            if old is not None:
                self.proposals[old].superseders.append(e.id)
                self.proposals[old].basis.add(e.id)
            self.proposals[e.id] = p
            self.kind[e.id] = "proposal"
        elif t in ("BLOCK", "FREEZE"):
            if t == "BLOCK":
                g = _Gate(e.id, "block", e.by, self.rules.required("unblock", e.by, e.to), e.refs[0], e.get("on"), basis={e.id})
                self.proposals[e.refs[0]].blocks.append(e.id)
            else:
                g = _Gate(e.id, "freeze", e.by, self.rules.required("lift", e.by, e.to), e.get("scope") or "", basis={e.id})
            self.gates[e.id] = g
            self.kind[e.id] = g.kind
        elif t in ("UNBLOCK", "LIFT"):
            g = self.gates[e.refs[0]]
            g.requests.append(e.id)
            g.basis.add(e.id)
            self.request_of[e.id] = g.id
            self.kind[e.id] = t.lower()
            if e.by in g.required:
                g.consent[e.by] = True
            self._settle(g)
        elif t == "DECIDE":
            self.kind[e.id] = "decide"
            p = self.proposals[e.refs[0]]
            if v.effective and not p.decided_by:
                p.decided_by = e.id
        elif t == "HANDOFF":
            self.handoffs[e.id] = _Handoff(e.id, e.by, e.to[0], dict(e.anchors), basis={e.id})
            self.kind[e.id] = "handoff"
        elif t == "RECEIPT":
            h = self.handoffs[e.refs[0]]
            h.receipts.append((e.id, e.by, dict(e.anchors)))
            h.basis.add(e.id)
            self.kind[e.id] = "receipt"
            d = sentinel.diff(h.anchors, e.anchors)
            if d:
                notes.append(("V04", h.id, f"receipt {e.id} does not match: {sentinel.describe(d)}",
                              (f"handoffs/{h.id}.json", f"receipts/{e.id}.json")))
        elif t == "ARBITRATE":
            p, q = sorted((self.proposals[r] for r in e.refs), key=lambda x: x.order)
            c = self.conflicts[f"{p.id}~{q.id}"]
            c.arbitrations.append((e.id, bool(v.effective), e.get("rule") or "", e.get("outcome") or ""))
            c.basis.add(e.id)
            self.arbitration_of[e.id] = c.id
            self.kind[e.id] = "arbitrate"
        return notes


# -- the derived state ------------------------------------------------------------------------------------------

@dataclass
class State:
    source: str                                  # 'log' or 'document'
    commits: int
    as_of: dict
    head_sha: str
    status: dict[str, dict[str, str]]
    face: dict[str, dict[str, str]]              # statuses before doubt is applied
    release_gate: str
    release_reasons: list[str]
    findings: list[Finding]
    edges: list[dict]
    arbitrations: list[dict]
    degraded: list[str]
    doubtful: dict[str, list[str]]
    details: dict
    rules_sha256: dict
    rules_version: dict

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def violations(self) -> list[dict]:
        """The V01..V11 findings as (class, commit_index, target), the identity used to score them."""
        keys = sorted({(f.commit_index, f.cls, f.target) for f in self.findings if f.cls.startswith("V")})
        return [{"class": c, "commit_index": n, "target": t} for n, c, t in keys]

    def as_dict(self) -> dict:
        """Everything the state says, with commits cited by index so that the output has no hash in it."""
        return {
            "protocol": "coord/1", "source": self.source, "commits": self.commits, "as_of": self.as_of,
            "state": self.status, "release_gate": self.release_gate, "release_reasons": self.release_reasons,
            "degraded": self.degraded, "doubtful": self.doubtful, "violations": self.violations,
            "findings": [f.as_dict() for f in self.findings], "edges": self.edges, "arbitrations": self.arbitrations,
            "details": self.details, "rules_sha256": self.rules_sha256,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sort_key(f: Finding):
    return (f.commit_index, f.cls, f.target, f.detail)


def derive(log: gitlog.Log, rules: RuleSet | None = None, *, source: str = "log", check_files: bool = True) -> State:
    rules = rules or load()
    m = Machine(rules)
    verdicts: dict[str, Verdict] = {}
    findings: list[Finding] = list(log.findings)
    degraded: list[str] = list(log.degraded)
    applied: list[Entry] = []
    where = {e.id: e for e in log.entries}

    for e in log.entries:
        ci = e.commit_index
        anc = log.ancestors[ci]

        def known(agent: str, _ci=ci, _anc=anc) -> bool:
            since = log.roster_since.get(agent)
            return since is not None and (since == _ci or since in _anc or since == 0)

        if len(anc) == ci - 1:
            view = m                               # linear history: everything before is an ancestor
        else:
            view = Machine(rules)
            for x in applied:
                if x.commit_index in anc or x.commit_index == ci:
                    view.apply(x, verdicts[x.id])
        v = verdicts[e.id] = view.judge(e, known)
        cite = (f"{gitlog.DOC}:{e.line}",)
        if not v.valid:
            findings.append(Finding("invalid", ci, e.id, v.reason, cite))
            if e.type in RESTRAINING:
                degraded.append(f"c{ci}: {e.type} {e.id} is invalid ({v.reason})")
        elif e.type == "DECIDE" and not v.effective:
            findings.append(Finding("V05", ci, e.id, f"DECIDE without the required consents: {v.reason}", cite))
        elif e.type == "ARBITRATE" and not v.effective:
            findings.append(Finding("V11", ci, e.id, v.reason, cite))
        elif e.type == "BLOCK" and e.get("on"):
            if v.stale:
                findings.append(Finding("V07", ci, e.id, f"waits for {e.get('on')}, which is already closed", cite))
            chain = closing_cycle(m.active_edges(), e.refs[0], e.get("on"))
            if chain:
                ids = sorted(chain + [e.id], key=lambda i: (where[i].commit_index, where[i].seq))
                findings.append(Finding("V06", ci, "+".join(ids), "dependency cycle: " + " -> ".join(ids), cite))
        for cls, target, detail, cites in m.apply(e, v):
            findings.append(Finding(cls, ci, target, detail, cites))
        applied.append(e)

    # two opposite answers by one agent, written on branches that had not seen each other
    answers: dict[tuple[str, str], list[Entry]] = {}
    for e in applied:
        if e.type in ("ACK", "DISSENT") and verdicts[e.id].valid:
            for ref in e.refs:
                answers.setdefault((e.by, ref), []).append(e)
    for (agent, ref), mine in answers.items():
        for i, a in enumerate(mine):
            for b in mine[i + 1:]:
                if a.type != b.type and a.commit_index != b.commit_index \
                        and a.commit_index not in log.ancestors[b.commit_index]:
                    a.doubt.add("ambiguous")
                    b.doubt.add("ambiguous")
                    findings.append(Finding("ambiguous", b.commit_index, b.id,
                                            f"{a.id} ({a.type}) and {b.id} ({b.type}) answer {ref} from branches that had not "
                                            f"seen each other: the log does not say which one stands"))

    # handoffs at head: missing receipts, files that disagree with their entries
    file_problems: dict[str, list[str]] = {}
    for hid, h in m.handoffs.items():
        if not h.receipts:
            findings.append(Finding("V03", where[hid].commit_index, hid, f"no receipt from {h.to}", (f"handoffs/{hid}.json",)))
        problems: list[str] = []
        if check_files:
            sides = [("handoff", hid, {"id": hid, "by": h.by, "to": h.to, "anchors": h.anchors})]
            sides += [("receipt", rid, {"id": rid, "handoff": hid, "by": rby, "anchors": ranch}) for rid, rby, ranch in h.receipts]
            for kind, eid, expected in sides:
                path = f"{kind}s/{eid}.json"
                first = log.first_files.get(path)
                for problem in sentinel.check_file(kind, expected, first[1] if first else None):
                    problems.append(f"{path}: {problem}")
                    findings.append(Finding("V04", where[eid].commit_index, hid, f"{path}: {problem}",
                                            (f"handoffs/{hid}.json", path)))
        file_problems[hid] = problems

    doubtful = {e.id: sorted(e.doubt) for e in log.entries if e.doubt}
    face: dict[str, dict[str, str]] = {k: {} for k in KINDS}
    basis: dict[str, dict[str, set[str]]] = {k: {} for k in KINDS}
    for gid, g in m.gates.items():
        kind = "blocks" if g.kind == "block" else "freezes"
        face[kind][gid], basis[kind][gid] = m.gate_status(gid), set(g.basis)
    for hid, h in m.handoffs.items():
        face["handoffs"][hid] = "MISMATCH" if file_problems[hid] else m.handoff_status(hid)
        basis["handoffs"][hid] = set(h.basis)
    for did, d in m.disputes.items():
        face["disputes"][did], basis["disputes"][did] = m.dispute_status(did), set(d.basis)
    for pid, p in m.proposals.items():
        face["proposals"][pid] = m.proposal_status(pid)
        rests = set(p.basis)
        for b in p.blocks:
            rests |= m.gates[b].basis
        for d in p.disputes:
            rests |= m.disputes[d].basis
        basis["proposals"][pid] = rests
    for cid, c in m.conflicts.items():
        face["conflicts"][cid] = m.conflict_status(cid)
        rests = set(c.basis)
        if face["conflicts"][cid] == "WITHDRAWN":
            rests |= set(m.proposals[c.p].superseders) | set(m.proposals[c.q].superseders)
        basis["conflicts"][cid] = rests

    is_degraded = bool(degraded)
    status: dict[str, dict[str, str]] = {k: {} for k in KINDS}
    for kind in KINDS:
        for oid, s in face[kind].items():
            doubt = is_degraded or bool(basis[kind][oid] & set(doubtful))
            status[kind][oid] = TO_CONFIRM if s in ASSERTING[kind] and doubt else s

    # release gate, by rule
    reasons: list[str] = []
    checks = [("state", "the state", {"kind": "state", "degraded": is_degraded})]
    checks += [("freeze", f"freeze {i}", {"kind": "freeze", "status": s}) for i, s in status["freezes"].items()]
    checks += [("handoff", f"handoff {i}", {"kind": "handoff", "status": s}) for i, s in status["handoffs"].items()]
    for _, label, facts in checks:
        verdict, rid = rules.release(facts)
        if verdict == "BLOCKED":
            reasons.append(f"{label} is {'degraded' if facts['kind'] == 'state' else facts['status']} (rule {rid})")
    release_gate = "BLOCKED" if reasons else "OPEN"

    edges = [{"block": g.id, "on": g.on, "refs": g.target, "active": status["blocks"][g.id] != "REMOVED"}
             for g in m.gates.values() if g.kind == "block" and g.on]
    arbitrations, conflict_details = [], {}
    for c in sorted(m.conflicts.values(), key=lambda c: (m.proposals[c.p].order, m.proposals[c.q].order)):
        p, q = m.proposals[c.p], m.proposals[c.q]
        rule, outcome = arbitrate.decide(rules.arbitration, p.claim(), q.claim())
        arbitrations.append({"conflict": c.id, "rule": rule, "outcome": outcome})
        conflict_details[c.id] = {
            "resource": p.resource, "claims": [p.claim(), q.claim()], "expected": {"rule": rule, "outcome": outcome},
            "recorded": [{"entry": a, "effective": ok, "rule": r, "outcome": o} for a, ok, r, o in c.arbitrations],
            "dissents": list(c.dissents)}

    def answer(p: _Proposal, a: str) -> str:
        return "none" if a not in p.responses else "ACK" if p.responses[a] else "DISSENT"

    tally = {"note": 0, "dissent": 0, "none": 0}
    for _, nature, _ in m.natures.values():
        tally[nature] += 1
    details = {
        "proposals": {pid: {"by": p.by, "to": p.required, "text": p.text, "commit_index": where[pid].commit_index,
                            "consents": {a: answer(p, a) for a in p.required}, "missing": m.missing_consents(pid),
                            "blocks": list(p.blocks), "disputes": list(p.disputes), "decided_by": p.decided_by,
                            "superseded_by": list(p.superseders)} for pid, p in m.proposals.items()},
        "blocks": {g.id: {"by": g.by, "refs": g.target, "on": g.on, "required": g.required, "missing": m.missing(g.id),
                          "requests": list(g.requests), "commit_index": where[g.id].commit_index}
                   for g in m.gates.values() if g.kind == "block"},
        "freezes": {g.id: {"by": g.by, "scope": g.target, "required": g.required, "missing": m.missing(g.id),
                           "requests": list(g.requests), "commit_index": where[g.id].commit_index}
                    for g in m.gates.values() if g.kind == "freeze"},
        "handoffs": {h.id: {"by": h.by, "to": h.to, "anchors": h.anchors, "commit_index": where[h.id].commit_index,
                            "receipts": [{"id": r, "anchors": a} for r, _, a in h.receipts],
                            "diff": sentinel.diff(h.anchors, h.receipts[-1][2]) if h.receipts else [],
                            "files": [f"handoffs/{h.id}.json"] + ([f"receipts/{h.receipts[-1][0]}.json"] if h.receipts else []),
                            "file_problems": file_problems[h.id]} for h in m.handoffs.values()},
        "disputes": {d.id: {"proposal": d.proposal, "by": d.by, "text": d.text, "commit_index": where[d.id].commit_index}
                     for d in m.disputes.values()},
        "conflicts": conflict_details,
        "responses": {"by_nature": tally,
                      "entries": {rid: {"type": t, "nature": n, "rule": r} for rid, (t, n, r) in m.natures.items()}},
    }
    head = log.head
    if source == "log":
        as_of = {"commit_index": head.index if head else 0, "committed_utc": _utc(head.committed) if head else None}
    else:
        as_of = {"entries": len(log.entries)}
    return State(source=source, commits=len(log.commits), as_of=as_of, head_sha=head.sha if head else "",
                 status=status, face=face, release_gate=release_gate, release_reasons=reasons,
                 findings=sorted(dict.fromkeys(findings), key=_sort_key), edges=edges, arbitrations=arbitrations,
                 degraded=degraded, doubtful=doubtful, details=details, rules_sha256=dict(rules.sha256),
                 rules_version=dict(rules.version))


def from_log(repo, rules: RuleSet | None = None, ref: str = "main") -> State:
    return derive(gitlog.read(repo, ref), rules)


def from_document(data: bytes, rules: RuleSet | None = None) -> State:
    """The state as the latest text of `COORD.md` alone would give it: entries in document order, no commits,
    no authors. It cannot see a rewrite, a forged author or a branch - which is why the log is the source."""
    doc = parse_doc(data)
    findings: list[Finding] = []
    degraded: list[str] = []
    roster, roster_since, entries = {}, {}, []
    duplicated = set()
    for a in doc.agents:
        if a.id in roster:
            duplicated.add(a.id)
            findings.append(Finding("V08", 0, f"agent:{a.id}", "two agent lines with the same id"))
        else:
            roster[a.id], roster_since[a.id] = a, 0
    for u in doc.unparsed:
        findings.append(Finding("unparsed", 0, f"line:{u.line}", u.reason))
        degraded.append(f"line {u.line}: {u.reason}")
    ancestors: dict[int, frozenset[int]] = {}
    n = 0
    for e in doc.entries:
        if e.problems:
            findings.append(Finding("malformed", 0, e.id, "; ".join(e.problems), (f"{gitlog.DOC}:{e.line}",)))
            degraded.append(f"entry {e.id} is malformed")
            continue
        n += 1
        e.commit_index, e.seq = n, 1
        ancestors[n] = frozenset(range(1, n))
        if e.by in duplicated:
            e.doubt.add("duplicate_agent")
        entries.append(e)
    log = gitlog.Log(commits=[], entries=entries, roster=roster, roster_since=roster_since, findings=findings,
                     ancestors=ancestors, degraded=degraded, head_files={}, first_files={})
    return derive(log, rules, source="document", check_files=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coord.state", description="Derive the state of a coordination from its git log.")
    ap.add_argument("--repo", help="a git repository holding COORD.md")
    ap.add_argument("--doc", help="a COORD.md file alone (no history): for comparison only")
    ap.add_argument("--rules", help="directory with the rule files (default: rules/)")
    ap.add_argument("--out", help="write the state as JSON to this file")
    a = ap.parse_args(argv)
    if bool(a.repo) == bool(a.doc):
        ap.error("give --repo or --doc")
    rules = load(a.rules)
    if a.repo:
        st = from_log(a.repo, rules)
    else:
        with open(a.doc, "rb") as fh:
            st = from_document(fh.read(), rules)
    text = st.to_json()
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
