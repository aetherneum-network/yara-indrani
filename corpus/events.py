"""Coordination stories as lists of events (one event = one commit).

An event says *what happened* ("bruno acknowledges ines-1, committed by bruno at 08:31Z"); it holds no
markdown and no git. Two independent things are derived from the same list:

* `corpus/render.py` turns it into a `COORD.md` history (a git fast-import stream);
* `corpus/reference_reducer.py` computes the gold state and the gold violations from the events alone.

The tooling under test (`coord/`) only ever sees the rendered git history.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ENTRY_TYPES = ("PROPOSE", "ACK", "DISSENT", "BLOCK", "UNBLOCK", "FREEZE", "LIFT", "DECIDE", "HANDOFF", "RECEIPT",
               "ARBITRATE")


def parse_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def fmt_utc(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tz_delta(tz: str) -> timedelta:
    sign = -1 if tz.startswith("-") else 1
    hh, mm = tz[1:].split(":")
    return sign * timedelta(hours=int(hh), minutes=int(mm))


def local_iso(d: datetime, tz: str) -> str:
    """The instant `d` written on the wall clock of an agent whose offset is `tz` (e.g. +01:00)."""
    return (d.astimezone(timezone.utc) + tz_delta(tz)).strftime("%Y-%m-%dT%H:%M:%S") + tz


class StoryBuilder:
    """Append events in log order. Times always move forward, so list order is log order."""

    def __init__(self, team: dict, agents: list[dict], start_utc: str, step_minutes: int = 17):
        self.team = dict(team)
        self.agents = {a["id"]: dict(a) for a in agents}
        self.clock = parse_utc(start_utc)
        self.step = step_minutes
        self.counters: dict[str, int] = {}
        self.events: list[dict] = []
        self.tip = 0
        self._add({"op": "init", "team": self.team, "agents": [dict(a) for a in agents]}, agents[0]["id"], None, None)

    # -- plumbing -----------------------------------------------------------------------------------
    def _add(self, ev: dict, commit_by: str, parent: int | None, minutes: int | None, parents: list[int] | None = None):
        if self.events:
            self.clock += timedelta(minutes=self.step if minutes is None else minutes)
        n = len(self.events) + 1
        ev = {"n": n, "parents": parents if parents is not None else ([] if n == 1 else [parent or self.tip]),
              "commit_by": commit_by, "utc": fmt_utc(self.clock), **ev}
        self.events.append(ev)
        self.tip = n
        return n

    def next_id(self, agent: str) -> str:
        self.counters[agent] = self.counters.get(agent, 0) + 1
        return f"{agent}-{self.counters[agent]}"

    def _entry(self, etype: str, by: str, fields: dict, *, commit_as: str | None = None, insert_before: str | None = None,
               mojibake: bool = False, minutes: int | None = None, parent: int | None = None, style: dict | None = None,
               as_of: str | None = None) -> str:
        eid = self.next_id(by)
        when = self.clock + timedelta(minutes=self.step if minutes is None else minutes)
        entry = {"type": etype, "id": eid, "by": by,
                 "as_of": as_of or local_iso(when - timedelta(minutes=2), self.agents[by]["tz"])}
        entry.update({k: v for k, v in fields.items() if v is not None})
        ev = {"op": "entry", "entry": entry}
        if insert_before:
            ev["insert_before"] = insert_before
        if mojibake:
            ev["mojibake"] = True
        if style:
            ev["style"] = style
        self._add(ev, commit_as or by, parent, minutes)
        return eid

    @property
    def last(self) -> int:
        return len(self.events)

    # -- entries ------------------------------------------------------------------------------------
    def propose(self, by, to, text, *, supersedes=None, resource=None, klass=None, due=None, **kw) -> str:
        return self._entry("PROPOSE", by, {"to": list(to), "text": text, "supersedes": supersedes, "resource": resource,
                                           "class": klass, "due": due}, **kw)

    def ack(self, by, refs, note=None, **kw) -> str:
        return self._entry("ACK", by, {"refs": [refs] if isinstance(refs, str) else list(refs), "note": note}, **kw)

    def dissent(self, by, ref, text, **kw) -> str:
        return self._entry("DISSENT", by, {"refs": [ref], "text": text}, **kw)

    def block(self, by, ref, on=None, to=None, text=None, **kw) -> str:
        return self._entry("BLOCK", by, {"refs": [ref], "on": on, "to": list(to) if to else None, "text": text}, **kw)

    def unblock(self, by, ref, text=None, **kw) -> str:
        return self._entry("UNBLOCK", by, {"refs": [ref], "text": text}, **kw)

    def freeze(self, by, scope, to, text=None, **kw) -> str:
        return self._entry("FREEZE", by, {"scope": scope, "to": list(to), "text": text}, **kw)

    def lift(self, by, ref, text=None, **kw) -> str:
        return self._entry("LIFT", by, {"refs": [ref], "text": text}, **kw)

    def decide(self, by, ref, text=None, **kw) -> str:
        return self._entry("DECIDE", by, {"refs": [ref], "text": text}, **kw)

    def handoff(self, by, to, anchors, text=None, **kw) -> str:
        return self._entry("HANDOFF", by, {"to": [to], "anchors": dict(anchors), "text": text}, **kw)

    def receipt(self, by, ref, anchors, text=None, **kw) -> str:
        return self._entry("RECEIPT", by, {"refs": [ref], "anchors": dict(anchors), "text": text}, **kw)

    def arbitrate(self, by, refs, rule, outcome, text=None, **kw) -> str:
        return self._entry("ARBITRATE", by, {"refs": list(refs), "rule": rule, "outcome": outcome, "text": text}, **kw)

    # -- things that are not entries ----------------------------------------------------------------
    def tamper(self, by, target, change, *, minutes=None, parent=None) -> int:
        """Rewrite something already in the repository, in place (V01)."""
        return self._add({"op": "tamper", "target": target, "change": dict(change)}, by, parent, minutes)

    def dup_agent(self, by, agent: dict, *, minutes=None, parent=None) -> int:
        """Add a second `## Agents` line with an id already in use (V08)."""
        return self._add({"op": "dup_agent", "agent": dict(agent)}, by, parent, minutes)

    def join(self, by, agent: dict, *, minutes=None, parent=None) -> int:
        """A new agent joins: a new `## Agents` line (legitimate)."""
        self.agents[agent["id"]] = dict(agent)
        return self._add({"op": "join", "agent": dict(agent)}, by, parent, minutes)

    def merge(self, by, parents: list[int], *, minutes=None) -> int:
        return self._add({"op": "merge"}, by, None, minutes, parents=list(parents))
