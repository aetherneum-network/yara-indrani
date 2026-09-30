"""Gold state from events alone - no markdown, no git, no rule files.

This is the independent side of the evaluation. It reads the event list of a story (`corpus/events.py`)
and recomputes, by scanning the list, what PROTOCOL.md says the state is. It is written in a plain
recompute-from-scratch style on purpose: the tooling under test (`coord/state.py`) is an incremental
machine driven by rule files and fed from `git log`, so the two share no code and no data path.

It is strict: an event that PROTOCOL.md does not give a meaning to (a reference to an unknown entry, a
RECEIPT by the wrong agent, ...) raises `Unsupported` instead of being guessed. The generator and the
scenario stories therefore contain only the eleven planted violation classes.
"""
from __future__ import annotations

from collections import deque

NO_SUBSTANCE = {"", "-", "none", "n/a", "na", "no objection", "nothing"}
ASSERTING = {
    "proposals": {"ALIGNED", "DECIDED", "SUPERSEDED"},
    "blocks": {"REMOVED"},
    "freezes": {"LIFTED"},
    "handoffs": {"RECEIVED"},
    "disputes": {"ANSWERED", "CLOSED"},
    "conflicts": {"ARBITRATED", "ESCALATED", "WITHDRAWN"},
}
TO_CONFIRM = "TO_CONFIRM"
ESCALATE = "ESCALATE_TO_HUMAN"


class Unsupported(ValueError):
    """The event list contains something the reference reducer refuses to interpret."""


def has_substance(text: str | None) -> bool:
    return (text or "").strip().rstrip(".").strip().lower() not in NO_SUBSTANCE


def expected_arbitration(p: dict, q: dict) -> tuple[str, str]:
    """(rule id or 'none', winner id or ESCALATE_TO_HUMAN) for two claims, `p` being the earlier one."""
    cp, cq = p.get("class") or "routine", q.get("class") or "routine"
    if (cp == "safety") != (cq == "safety"):
        return "R-SAFETY", (p if cp == "safety" else q)["id"]
    if cp != "safety" and cq != "safety" and p.get("due") and q.get("due") and p["due"] != q["due"]:
        return "R-DUE", (p if p["due"] < q["due"] else q)["id"]
    if cp == "routine" and cq == "routine":
        return "R-FIRST", p["id"]
    return "none", ESCALATE


class _Story:
    def __init__(self, events: list[dict]):
        self.events = events
        self.roster: dict[str, dict] = {}
        self.dup_since: dict[str, int] = {}
        self.entries: list[dict] = []          # entry dicts + "n" (commit index) + "commit_by", in log order
        self.by_id: dict[str, dict] = {}
        self.anc: dict[int, set[int]] = {}
        self.doubtful: set[str] = set()
        self.violations: list[tuple[str, int, str]] = []
        self.effective: dict[str, bool] = {}   # DECIDE and ARBITRATE entries
        self._load()
        self._semantics()

    # -- pass 1: what the events say happened to the repository ---------------------------------------
    def _load(self) -> None:
        last_utc = ""
        for i, ev in enumerate(self.events, start=1):
            if ev["n"] != i:
                raise Unsupported(f"event {i}: n must be {i}")
            if i > 1 and not ev["parents"]:
                raise Unsupported(f"event {i}: no parent")
            if any(p >= i for p in ev["parents"]) or ev["utc"] <= last_utc:
                raise Unsupported(f"event {i}: events must be listed in log order with increasing UTC times")
            last_utc = ev["utc"]
            self.anc[i] = set()
            for p in ev["parents"]:
                self.anc[i] |= self.anc[p] | {p}
            op = ev["op"]
            if op == "init":
                for a in ev["agents"]:
                    if a["id"] in self.roster:
                        raise Unsupported("init with a duplicate agent id")
                    self.roster[a["id"]] = a
            elif op == "join":
                if ev["agent"]["id"] in self.roster:
                    raise Unsupported("join with an id in use (use dup_agent)")
                self.roster[ev["agent"]["id"]] = ev["agent"]
            elif op == "dup_agent":
                aid = ev["agent"]["id"]
                if aid not in self.roster:
                    raise Unsupported("dup_agent with an unknown id")
                self.dup_since.setdefault(aid, i)
                self.violations.append(("V08", i, f"agent:{aid}"))
            elif op == "tamper":
                target = ev["target"]
                self.violations.append(("V01", i, target))
                if target != "header" and not target.startswith("agent:"):
                    if target not in self.by_id:
                        raise Unsupported(f"tamper of unknown entry {target}")
                    self.doubtful.add(target)
            elif op == "merge":
                if len(ev["parents"]) < 2:
                    raise Unsupported("merge needs two parents")
            elif op == "entry":
                e = dict(ev["entry"], n=i, commit_by=ev["commit_by"])
                if e["id"] in self.by_id:
                    raise Unsupported(f"duplicate entry id {e['id']}")
                if e["by"] not in self.roster or e["id"].rsplit("-", 1)[0] != e["by"]:
                    raise Unsupported(f"entry {e['id']}: bad author")
                self.entries.append(e)
                self.by_id[e["id"]] = e
                if ev["commit_by"] != e["by"]:
                    self.violations.append(("V02", i, e["id"]))
                    self.doubtful.add(e["id"])
                if e["by"] in self.dup_since:
                    self.doubtful.add(e["id"])
                if ev.get("insert_before"):
                    self.violations.append(("V09", i, e["id"]))
                if ev.get("mojibake"):
                    self.violations.append(("V10", i, e["id"]))
            else:
                raise Unsupported(f"unknown op {op}")
        childless = set(range(1, len(self.events) + 1)) - {p for ev in self.events for p in ev["parents"]}
        if childless != {len(self.events)}:
            raise Unsupported("every branch must be merged before the end of the story")

    # -- views ----------------------------------------------------------------------------------------
    def view(self, n: int) -> list[dict]:
        """Entries in the commits that commit `n` descends from."""
        return [e for e in self.entries if e["n"] in self.anc[n]]

    def prefix(self, n: int) -> list[dict]:
        return [e for e in self.entries if e["n"] < n]

    def _refs(self, e: dict) -> list[str]:
        return e.get("refs") or []

    def _of_type(self, view, etype, ref=None):
        return [e for e in view if e["type"] == etype and (ref is None or self._refs(e) == [ref])]

    def _gate_open(self, view, author: str, extra: list[str], request_type: str, target_id: str) -> bool:
        """True from the first moment a request exists and every required agent's latest response consents."""
        required = {author, *extra}
        consent: dict[str, bool] = {}
        requests: set[str] = set()
        for e in view:
            if e["type"] == request_type and self._refs(e) == [target_id]:
                requests.add(e["id"])
                if e["by"] in required:
                    consent[e["by"]] = True
            elif e["type"] in ("ACK", "DISSENT") and e["by"] in required and requests & set(self._refs(e)):
                consent[e["by"]] = e["type"] == "ACK"
            if requests and all(consent.get(a) for a in required):
                return True
        return False

    def block_removed(self, view, b: dict) -> bool:
        return self._gate_open(view, b["by"], b.get("to") or [], "UNBLOCK", b["id"])

    def freeze_lifted(self, view, f: dict) -> bool:
        return self._gate_open(view, f["by"], f.get("to") or [], "LIFT", f["id"])

    def disputes_on(self, view, p: dict) -> list[dict]:
        return [e for e in view if e["type"] == "DISSENT" and self._refs(e) == [p["id"]] and e["by"] != p["by"]
                and has_substance(e.get("text"))]

    def dispute_status(self, view, d: dict) -> str:
        p = self.by_id[self._refs(d)[0]]
        later = [e for e in view if e["n"] > d["n"] and e["type"] == "ACK"]
        if any(e["by"] == d["by"] and ({p["id"], d["id"]} & set(self._refs(e))) for e in later):
            return "CLOSED"
        if any(e["by"] == p["by"] and d["id"] in self._refs(e) for e in later):
            return "ANSWERED"
        return "OPEN"

    def consents(self, view, p: dict) -> dict[str, bool]:
        out = {}
        for a in p["to"]:
            mine = [e for e in view if e["type"] in ("ACK", "DISSENT") and e["by"] == a and p["id"] in self._refs(e)]
            out[a] = bool(mine) and mine[-1]["type"] == "ACK"
        return out

    def proposal_status(self, view, p: dict) -> str:
        if any(e["type"] == "PROPOSE" and e.get("supersedes") == p["id"] for e in view):
            return "SUPERSEDED"
        if any(self.effective.get(e["id"]) for e in self._of_type(view, "DECIDE", p["id"])):
            return "DECIDED"
        if any(not self.block_removed(view, b) for b in self._of_type(view, "BLOCK", p["id"])):
            return "BLOCKED"
        if any(self.dispute_status(view, d) != "CLOSED" for d in self.disputes_on(view, p)):
            return "DISPUTED"
        return "ALIGNED" if all(self.consents(view, p).values()) else "PROPOSED"

    # -- pass 2: meaning --------------------------------------------------------------------------------
    def _need(self, e: dict, ref: str, types: tuple[str, ...], view_ids: set[str]) -> dict:
        t = self.by_id.get(ref)
        if t is None or ref not in view_ids or t["type"] not in types:
            raise Unsupported(f"{e['id']}: reference {ref} is not a visible {'/'.join(types)}")
        return t

    def _semantics(self) -> None:
        for e in self.entries:
            view = self.view(e["n"])
            ids = {x["id"] for x in view}
            t, refs = e["type"], self._refs(e)
            if t == "PROPOSE":
                if not e.get("to") or e["by"] in e["to"] or any(a not in self.roster for a in e["to"]):
                    raise Unsupported(f"{e['id']}: bad 'to'")
                if e.get("supersedes"):
                    old = self._need(e, e["supersedes"], ("PROPOSE",), ids)
                    if old["by"] != e["by"] or self.proposal_status(view, old) == "SUPERSEDED":
                        raise Unsupported(f"{e['id']}: cannot supersede {old['id']}")
            elif t == "ACK":
                for r in refs:
                    self._need(e, r, ("PROPOSE", "DISSENT", "UNBLOCK", "LIFT"), ids)
            elif t == "DISSENT":
                target = self._need(e, refs[0], ("PROPOSE", "UNBLOCK", "LIFT", "ARBITRATE"), ids)
                if len(refs) != 1 or (target["type"] == "PROPOSE" and target["by"] == e["by"]):
                    raise Unsupported(f"{e['id']}: bad dissent")
            elif t == "BLOCK":
                p = self._need(e, refs[0], ("PROPOSE",), ids)
                if self.proposal_status(view, p) in ("DECIDED", "SUPERSEDED"):
                    raise Unsupported(f"{e['id']}: blocks a closed proposal")
                if e.get("on"):
                    on = self._need(e, e["on"], ("PROPOSE",), ids)
                    if on["id"] == p["id"]:
                        raise Unsupported(f"{e['id']}: blocks a proposal on itself")
                    if self.proposal_status(view, on) in ("DECIDED", "SUPERSEDED"):
                        self.violations.append(("V07", e["n"], e["id"]))
                    cycle = self._cycle_closed_by(e)
                    if cycle:
                        self.violations.append(("V06", e["n"], "+".join(cycle)))
            elif t == "UNBLOCK":
                self._need(e, refs[0], ("BLOCK",), ids)
            elif t == "LIFT":
                self._need(e, refs[0], ("FREEZE",), ids)
            elif t == "FREEZE":
                if not e.get("to") or any(a not in self.roster for a in e["to"]):
                    raise Unsupported(f"{e['id']}: bad 'to'")
            elif t == "DECIDE":
                p = self._need(e, refs[0], ("PROPOSE",), ids)
                status = self.proposal_status(view, p)
                if p["by"] != e["by"] or status in ("DECIDED", "SUPERSEDED"):
                    raise Unsupported(f"{e['id']}: cannot decide {p['id']}")
                self.effective[e["id"]] = status == "ALIGNED"
                if status != "ALIGNED":
                    self.violations.append(("V05", e["n"], e["id"]))
            elif t == "HANDOFF":
                if len(e.get("to") or []) != 1 or e["to"][0] == e["by"] or e["to"][0] not in self.roster or not e.get("anchors"):
                    raise Unsupported(f"{e['id']}: bad handoff")
            elif t == "RECEIPT":
                h = self._need(e, refs[0], ("HANDOFF",), ids)
                if h["to"][0] != e["by"] or not e.get("anchors"):
                    raise Unsupported(f"{e['id']}: receipt by the wrong agent")
                if e["anchors"] != h["anchors"]:
                    self.violations.append(("V04", e["n"], h["id"]))
            elif t == "ARBITRATE":
                if len(refs) != 2:
                    raise Unsupported(f"{e['id']}: needs two proposals")
                p, q = sorted((self._need(e, r, ("PROPOSE",), ids) for r in refs), key=lambda x: x["n"])
                if not p.get("resource") or p.get("resource") != q.get("resource") or p["by"] == q["by"] \
                        or e["by"] in (p["by"], q["by"]):
                    raise Unsupported(f"{e['id']}: not an arbitrable conflict")
                if any(self.effective.get(a["id"]) for a in view if a["type"] == "ARBITRATE" and set(self._refs(a)) == set(refs)) \
                        or "SUPERSEDED" in (self.proposal_status(view, p), self.proposal_status(view, q)):
                    raise Unsupported(f"{e['id']}: conflict already closed")
                ok = (e["rule"], e["outcome"]) == expected_arbitration(p, q)
                self.effective[e["id"]] = ok
                if not ok:
                    self.violations.append(("V11", e["n"], e["id"]))
            else:
                raise Unsupported(f"unknown type {t}")

    def _cycle_closed_by(self, b: dict) -> list[str]:
        """Block ids of the dependency cycle that block `b` closes, in log order; [] if none."""
        before = self.prefix(b["n"])
        active = [x for x in before if x["type"] == "BLOCK" and x.get("on") and not self.block_removed(before, x)]
        start, goal = self._refs(b)[0], b["on"]
        queue, seen = deque([(start, [])]), {start}
        while queue:
            node, path = queue.popleft()
            for x in active:
                if x["on"] != node:
                    continue
                nxt = self._refs(x)[0]
                if nxt == goal:
                    ids = [y["id"] for y in path + [x]] + [b["id"]]
                    return sorted(ids, key=lambda i: self.by_id[i]["n"])
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, path + [x]))
        return []

    # -- head state -------------------------------------------------------------------------------------
    def gold(self) -> dict:
        head = self.entries
        state: dict[str, dict[str, str]] = {k: {} for k in ASSERTING}
        taint: dict[str, dict[str, set[str]]] = {k: {} for k in ASSERTING}

        for b in self._of_type(head, "BLOCK"):
            state["blocks"][b["id"]] = "REMOVED" if self.block_removed(head, b) else "ACTIVE"
            unblocks = {u["id"] for u in self._of_type(head, "UNBLOCK", b["id"])}
            taint["blocks"][b["id"]] = {b["id"]} | unblocks | {
                e["id"] for e in head if e["type"] in ("ACK", "DISSENT") and unblocks & set(self._refs(e))}
        for f in self._of_type(head, "FREEZE"):
            state["freezes"][f["id"]] = "LIFTED" if self.freeze_lifted(head, f) else "FROZEN"
            lifts = {x["id"] for x in self._of_type(head, "LIFT", f["id"])}
            taint["freezes"][f["id"]] = {f["id"]} | lifts | {
                e["id"] for e in head if e["type"] in ("ACK", "DISSENT") and lifts & set(self._refs(e))}
        for h in self._of_type(head, "HANDOFF"):
            receipts = self._of_type(head, "RECEIPT", h["id"])
            if not receipts:
                state["handoffs"][h["id"]] = "AWAITING_RECEIPT"
                self.violations.append(("V03", h["n"], h["id"]))
            else:
                state["handoffs"][h["id"]] = "RECEIVED" if receipts[-1]["anchors"] == h["anchors"] else "MISMATCH"
            taint["handoffs"][h["id"]] = {h["id"]} | {r["id"] for r in receipts}
        proposals = self._of_type(head, "PROPOSE")
        for p in proposals:
            for d in self.disputes_on(head, p):
                state["disputes"][d["id"]] = self.dispute_status(head, d)
                taint["disputes"][d["id"]] = {d["id"]} | {
                    e["id"] for e in head if e["type"] == "ACK" and e["n"] > d["n"] and (
                        d["id"] in self._refs(e) or (e["by"] == d["by"] and p["id"] in self._refs(e)))}
        for p in proposals:
            state["proposals"][p["id"]] = self.proposal_status(head, p)
            t = {p["id"]} | {e["id"] for e in head if e["type"] in ("ACK", "DISSENT", "DECIDE") and p["id"] in self._refs(e)}
            t |= {e["id"] for e in proposals if e.get("supersedes") == p["id"]}
            for b in self._of_type(head, "BLOCK", p["id"]):
                t |= taint["blocks"][b["id"]]
            for d in self.disputes_on(head, p):
                t |= taint["disputes"][d["id"]]
            taint["proposals"][p["id"]] = t
        arbitrations = []
        for i, p in enumerate(proposals):
            for q in proposals[i + 1:]:
                if not p.get("resource") or p.get("resource") != q.get("resource") or p["by"] == q["by"]:
                    continue
                cid = f"{p['id']}~{q['id']}"
                rule, outcome = expected_arbitration(p, q)
                arbitrations.append({"conflict": cid, "rule": rule, "outcome": outcome})
                arbs = [a for a in self._of_type(head, "ARBITRATE") if set(self._refs(a)) == {p["id"], q["id"]}]
                won = [a for a in arbs if self.effective.get(a["id"])]
                t = {p["id"], q["id"]} | {a["id"] for a in arbs}
                if won:
                    state["conflicts"][cid] = "ESCALATED" if won[0]["outcome"] == ESCALATE else "ARBITRATED"
                elif "SUPERSEDED" in (state["proposals"][p["id"]], state["proposals"][q["id"]]):
                    state["conflicts"][cid] = "WITHDRAWN"
                    t |= {e["id"] for e in proposals if e.get("supersedes") in (p["id"], q["id"])}
                else:
                    state["conflicts"][cid] = "OPEN"
                taint["conflicts"][cid] = t

        for kind, objs in state.items():
            for oid, status in objs.items():
                if status in ASSERTING[kind] and taint[kind][oid] & self.doubtful:
                    objs[oid] = TO_CONFIRM
        gate = "BLOCKED" if any(s != "LIFTED" for s in state["freezes"].values()) or any(
            s != "RECEIVED" for s in state["handoffs"].values()) else "OPEN"
        edges = [{"block": b["id"], "on": b["on"], "refs": self._refs(b)[0], "active": state["blocks"][b["id"]] != "REMOVED"}
                 for b in self._of_type(head, "BLOCK") if b.get("on")]
        return {
            "commits": len(self.events),
            "state": state,
            "release_gate": gate,
            "violations": [{"class": c, "commit_index": n, "target": t} for c, n, t in sorted(set(self.violations),
                                                                                           key=lambda v: (v[1], v[0], v[2]))],
            "edges": edges,
            "arbitrations": arbitrations,
        }


def reduce_events(events: list[dict]) -> dict:
    """Gold for one story: final status of every object, violations, dependency edges, arbitration outcomes."""
    return _Story(events).gold()
