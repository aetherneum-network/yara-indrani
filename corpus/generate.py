"""Generate a corpus of synthetic coordination stories.

    python corpus/generate.py --seed 20260930 --out corpus/out/dev

Each story is a team of 3-6 invented agents of one of three invented companies, writing 20-60 commits of
coordination cycles. Some cycles plant one of the eleven violation classes of PROTOCOL.md section 6.
For every story three files are written:

    events.json   what happened, one event per commit (the source of truth of the story)
    stream.fi     the same story as a git fast-import stream (what the tooling reads, once imported)
    gold.json     the expected state and violations, computed from the events by the reference reducer

The generator is deterministic: the same seed, profile and size give the same bytes. The `stress`
profile tells the same kind of stories but lets each agent write the entries in its own style (other
bullets, bold keys, other heading forms, CRLF, ...): the meaning is unchanged, only the rendering.

Everything is fictitious. Nothing here is derived from any real project or document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus import render, world                                              # noqa: E402
from corpus.events import StoryBuilder, fmt_utc, parse_utc                    # noqa: E402
from corpus.reference_reducer import ESCALATE, expected_arbitration, reduce_events   # noqa: E402

PROFILES = ("standard", "stress")
AUTHOR_SEEDS = {"dev": 20260930, "stress-diag": 20261002}     # the only seeds the author of the pack ever generated
DEFAULT_N = 120
MIN_COMMITS, MAX_COMMITS = 20, 60


class Story:
    def __init__(self, seed: int, index: int, profile: str):
        self.rng = random.Random(f"{seed}:{index}:story")
        self.style_rng = random.Random(f"{seed}:{index}:style")
        self.index, self.profile = index, profile
        self.clean = index % 4 == 3                        # one story in four plants nothing
        self.key = list(world.COMPANIES)[index % len(world.COMPANIES)]
        self.c = world.COMPANIES[self.key]
        everyone = [row[0] for row in self.c["agents"]]
        self.ids = self.rng.sample(everyone, self.rng.randint(3, 6))
        self.bench = [a for a in everyone if a not in self.ids]
        self.styles = {a: self._agent_style() for a in everyone} if profile == "stress" else {}
        team, agents = world.team(self.key, self.ids)
        start = parse_utc("2026-03-02T07:00:00Z") + timedelta(days=index, minutes=self.rng.randrange(240))
        self.b = StoryBuilder(team, agents, fmt_utc(start), step_minutes=self.rng.choice([7, 11, 13, 17, 23]))
        if profile == "stress" and self.style_rng.random() < 0.25:
            self.b.events[0]["style"] = {"eol": "crlf"}
        self.planted: list[tuple[str, int, str]] = []
        self.live: list[str] = []                          # entries still in the document, never tampered with
        self.type_of: dict[str, str] = {}
        self.anchors_of: dict[str, dict] = {}
        self.resources_used: set[str] = set()
        self.dup_done = False

    # -- helpers ------------------------------------------------------------------------------------------
    def _agent_style(self) -> dict:
        r, s = self.style_rng, {}
        if r.random() < 0.30:
            s["bullet"] = "*"
        if r.random() < 0.20:
            s["bold"] = True
        if r.random() < 0.20:
            s["keys"] = "cap"
        h = r.random()
        if h < 0.32:
            s["heading"] = ("id_first", "colon", "h4", "lower")[int(h / 0.08)]
        if r.random() < 0.15:
            s["sep"] = "; "
        if r.random() < 0.20:
            s["as_of"] = "local"
        if r.random() < 0.30:
            s["swap"] = [[1, 2]]
        return s

    def add(self, kind: str, by: str, *args, **kw) -> str:
        if self.styles.get(by):
            kw["style"] = self.styles[by]
        eid = getattr(self.b, kind)(by, *args, **kw)
        self.live.append(eid)
        self.type_of[eid] = self.b.events[-1]["entry"]["type"]
        return eid

    @property
    def n(self) -> int:
        return self.b.last

    def plant(self, cls: str, target: str, n: int | None = None) -> None:
        self.planted.append((cls, n or self.n, target))

    def text(self) -> str:
        return f"{self.rng.choice(self.c['actions'])} {self.rng.choice(self.c['things'])}."

    def note(self) -> str | None:
        return self.rng.choice(world.NOTES) if self.rng.random() < 0.4 else None

    def owner_and(self, lo: int, hi: int) -> tuple[str, list[str]]:
        owner = self.rng.choice(self.ids)
        rest = [a for a in self.ids if a != owner]
        return owner, self.rng.sample(rest, min(len(rest), self.rng.randint(lo, hi)))

    def other(self, *exclude: str) -> str:
        return self.rng.choice([a for a in self.ids if a not in exclude])

    def ack_all(self, ref: str, agents: list[str]) -> None:
        for a in agents:
            self.add("ack", a, ref, note=self.note())

    def chance(self, p: float) -> bool:
        """A planted variant: never in a clean story."""
        return self.rng.random() < p and not self.clean

    def resource(self) -> str:
        while True:
            r = f"{self.rng.choice(self.c['resources'])}/{self.rng.choice(world.WEEKS)}"
            if r not in self.resources_used:
                self.resources_used.add(r)
                return r

    # -- cycles ---------------------------------------------------------------------------------------------
    def c_clean(self) -> None:
        o, to = self.owner_and(1, 3)
        p = self.add("propose", o, to, self.text())
        self.ack_all(p, to)
        if self.rng.random() < 0.8:
            self.add("decide", o, p)

    def c_pending(self) -> None:
        o, to = self.owner_and(2, 3)
        p = self.add("propose", o, to, self.text())
        self.ack_all(p, to[:-1])
        if self.chance(0.35):
            self.plant("V05", self.add("decide", o, p))

    def c_dispute(self) -> None:
        o, to = self.owner_and(1, 3)
        p = self.add("propose", o, to, self.text())
        who = self.rng.choice(to)
        self.ack_all(p, [a for a in to if a != who])
        d = self.add("dissent", who, p, self.rng.choice(world.DISSENTS))
        variant = self.rng.choice(["open", "answered", "closed", "closed_own", "decide_anyway"])
        if variant == "decide_anyway":
            if self.clean:
                variant = "answered"
            else:
                self.plant("V05", self.add("decide", o, p))
        if variant in ("answered", "closed", "closed_own"):
            self.add("ack", o, d, note=self.rng.choice(world.ANSWERS))
        if variant == "closed":
            self.add("ack", who, p)
            if self.rng.random() < 0.6:
                self.add("decide", o, p)
        elif variant == "closed_own":
            self.add("ack", who, d)

    def c_outsider_dispute(self) -> None:
        o, to = self.owner_and(1, 1)
        x = self.other(o, *to)
        p = self.add("propose", o, to, self.text())
        self.add("ack", to[0], p, note=self.note())
        d = self.add("dissent", x, p, self.rng.choice(world.DISSENTS))
        if self.rng.random() < 0.5:
            self.add("ack", o, d, note=self.rng.choice(world.ANSWERS))
            self.add("ack", x, p)
            if self.rng.random() < 0.6:
                self.add("decide", o, p)

    def c_empty_dissent(self) -> None:
        o, to = self.owner_and(1, 3)
        p = self.add("propose", o, to, self.text())
        who = self.rng.choice(to)
        self.ack_all(p, [a for a in to if a != who])
        self.add("dissent", who, p, self.rng.choice(world.EMPTY_DISSENTS))
        variant = self.rng.choice(["later_ack", "left", "decide_anyway"])
        if variant == "later_ack":
            self.add("ack", who, p)
            if self.rng.random() < 0.7:
                self.add("decide", o, p)
        elif variant == "decide_anyway" and not self.clean:
            self.plant("V05", self.add("decide", o, p))

    def c_block(self) -> None:
        o, to = self.owner_and(1, 2)
        p = self.add("propose", o, to, self.text())
        self.ack_all(p, to)
        blocker = self.other(o)
        extra = [self.other(blocker)] if self.rng.random() < 0.5 else []
        bl = self.add("block", blocker, p, to=extra or None, text="waiting for " + self.rng.choice(self.c["things"]))
        variant = self.rng.choice(["removed", "partial", "none", "decide_anyway"])
        if variant == "removed":
            u = self.add("unblock", blocker, bl)
            self.ack_all(u, extra)
            if self.rng.random() < 0.7:
                self.add("decide", o, p)
        elif variant == "partial" and extra:
            self.add("unblock", self.rng.choice([blocker, extra[0]]), bl)
        elif variant == "decide_anyway" and not self.clean:
            self.plant("V05", self.add("decide", o, p))

    def c_block_on(self) -> None:
        o1, to1 = self.owner_and(1, 2)
        a = self.add("propose", o1, to1, self.text())
        o2, to2 = self.owner_and(1, 2)
        b = self.add("propose", o2, to2, self.text())
        x = self.rng.choice(self.ids)
        bl = self.add("block", x, a, on=b)
        if self.rng.random() < 0.5:
            self.ack_all(b, to2)
            self.add("decide", o2, b)
            self.add("unblock", x, bl)
            self.ack_all(a, to1)
            self.add("decide", o1, a)

    def c_freeze(self) -> None:
        x = self.rng.choice(self.ids)
        rest = [a for a in self.ids if a != x]
        to = self.rng.sample(rest, min(len(rest), self.rng.randint(1, 2)))
        f = self.add("freeze", x, self.rng.choice(self.c["scopes"]), to)
        variant = self.rng.choice(["lifted", "lifted", "partial", "withdrawn", "none"])
        if variant == "none":
            return
        lifter = self.rng.choice([x] + to)
        others = [a for a in [x] + to if a != lifter]
        lift = self.add("lift", lifter, f)
        if variant == "lifted":
            self.ack_all(lift, others)
        elif variant == "withdrawn" and len(others) >= 2:
            self.add("ack", others[0], lift)
            self.add("dissent", others[0], lift, self.rng.choice(world.DISSENTS))
            self.ack_all(lift, others[1:])
        else:
            self.ack_all(lift, others[:-1])

    def c_handoff(self) -> None:
        x = self.rng.choice(self.ids)
        y = self.other(x)
        build = str(self.rng.randint(100, 999))
        while build[1] == build[2]:
            build = str(self.rng.randint(100, 999))
        anchors = {"build": build, "tag": f"v{self.rng.randint(1, 4)}.{self.rng.randint(0, 9)}.{self.rng.randint(0, 9)}"}
        if self.rng.random() < 0.4:
            anchors["rev"] = f"r{self.rng.randint(10, 99)}"
        h = self.add("handoff", x, y, anchors)
        self.anchors_of[h] = anchors
        roll = self.rng.random()
        if self.clean or roll < 0.55:
            r = self.add("receipt", y, h, anchors)
            self.anchors_of[r] = anchors
        elif roll < 0.75:
            self.plant("V03", h)
        else:
            wrong = dict(anchors, build=build[0] + build[2] + build[1])         # two digits transposed
            r = self.add("receipt", y, h, wrong)
            self.anchors_of[r] = wrong
            self.plant("V04", h)
            if roll > 0.90:
                r2 = self.add("receipt", y, h, anchors)
                self.anchors_of[r2] = anchors

    def c_conflict(self) -> None:
        o1, o2, arbiter = self.rng.sample(self.ids, 3)
        res = self.resource()
        kind = self.rng.choice(["safety", "due", "first", "both_safety", "due_tie"])
        d1, d2 = f"2026-0{self.rng.randint(4, 6)}-{self.rng.randint(10, 19)}", f"2026-0{self.rng.randint(4, 6)}-{self.rng.randint(20, 28)}"
        if kind == "safety":
            claims = [("safety", None), (self.rng.choice(["routine", "deadline", None]), None)]
            self.rng.shuffle(claims)
        elif kind == "due":
            claims = [("deadline", d1), (self.rng.choice(["deadline", "routine"]), d2)]
            self.rng.shuffle(claims)
        elif kind == "first":
            claims = [(self.rng.choice(["routine", None]), None), (None, None)]
        elif kind == "both_safety":
            claims = [("safety", None), ("safety", d1)]
        else:
            claims = [("deadline", d1), ("deadline", d1)]
        p = self.add("propose", o1, [self.other(o1)], self.text(), resource=res, klass=claims[0][0], due=claims[0][1])
        q = self.add("propose", o2, [self.other(o2)], self.text(), resource=res, klass=claims[1][0], due=claims[1][1])
        ep = {"id": p, "class": claims[0][0], "due": claims[0][1]}
        eq = {"id": q, "class": claims[1][0], "due": claims[1][1]}
        rule, outcome = expected_arbitration(ep, eq)
        refs = [p, q] if self.rng.random() < 0.7 else [q, p]
        variant = self.rng.choice(["arbitrated", "arbitrated", "arbitrated_dissent", "open", "withdrawn", "wrong",
                                   "wrong_then_right"])
        if variant.startswith("wrong") and self.clean:
            variant = "arbitrated"
        if variant.startswith("wrong"):
            if outcome == ESCALATE:
                cited = ("R-FIRST", p)
            else:
                cited = ("R-FIRST" if rule != "R-FIRST" else "R-DUE", q if outcome == p else p)
            self.plant("V11", self.add("arbitrate", arbiter, refs, cited[0], cited[1]))
        if variant in ("arbitrated", "arbitrated_dissent", "wrong_then_right"):
            arb = self.add("arbitrate", arbiter, refs, rule, outcome)
            if variant == "arbitrated_dissent":
                loser = o2 if outcome == p else o1
                self.add("dissent", loser, arb, self.rng.choice(world.DISSENTS))
        elif variant == "withdrawn":
            self.add("propose", o2, [self.other(o2)], self.text(), supersedes=q, resource=self.resource())

    def c_supersede(self) -> None:
        o, to = self.owner_and(1, 2)
        p = self.add("propose", o, to, self.text())
        if self.rng.random() < 0.5:
            self.add("ack", to[0], p, note=self.note())
        p2 = self.add("propose", o, to, self.text(), supersedes=p)
        self.ack_all(p2, to)
        if self.rng.random() < 0.6:
            self.add("decide", o, p2)

    def c_concurrent(self) -> None:
        o, to = self.owner_and(2, 2)
        p = self.add("propose", o, to, self.text())
        base = self.b.tip
        self.add("ack", to[0], p, note=self.note(), parent=base)
        early = self.chance(0.35)
        if early:
            self.plant("V05", self.add("decide", o, p))     # decided on a branch that has not seen the second consent
        left = self.b.tip
        self.add("ack", to[1], p, note=self.note(), parent=base)
        right = self.b.tip
        self.b.merge(o, [left, right])
        if self.profile == "stress" and self.style_rng.random() < 0.5:
            self.b.events[-1]["style"] = {"merge_order": "branch"}
        if not early and self.rng.random() < 0.8:
            self.add("decide", o, p)

    def c_join(self) -> None:
        if not self.bench:
            return self.c_clean()
        new = self.bench.pop(self.rng.randrange(len(self.bench)))
        row = next(r for r in self.c["agents"] if r[0] == new)
        self.b.join(self.rng.choice(self.ids), world.agent_record(self.key, row))
        o = self.rng.choice(self.ids)
        self.ids.append(new)
        p = self.add("propose", o, [new], self.text())
        self.add("ack", new, p, note=self.note())
        if self.rng.random() < 0.7:
            self.add("decide", o, p)

    # -- plants ---------------------------------------------------------------------------------------------
    def p_forged(self) -> None:
        o, to = self.owner_and(2, 3)
        p = self.add("propose", o, to, self.text())
        self.ack_all(p, to[:-1])
        self.plant("V02", self.add("ack", to[-1], p, commit_as=o))        # the owner writes the missing consent itself
        self.add("decide", o, p)

    def p_tamper(self) -> None:
        by = self.rng.choice(self.ids)
        options = ["role", "header"]
        texts = [i for i in self.live if self.type_of[i] in ("PROPOSE", "DISSENT")]
        dissents = [i for i in self.live if self.type_of[i] == "DISSENT"]
        answers = [i for i in self.live if self.type_of[i] in ("ACK", "DISSENT")]
        files = [i for i in self.live if i in self.anchors_of]
        options += ["text"] * 3 * bool(texts) + ["retype"] * 2 * bool(dissents) + ["delete"] * 2 * bool(answers) \
            + ["file"] * 2 * bool(files)
        kind = self.rng.choice(options)
        if kind == "role":
            target, change = f"agent:{self.rng.choice(self.ids)}", {"value": f"coordination (rev {self.n})"}
        elif kind == "header":
            target, change = "header", {"value": f"{self.c['title']} (revision {self.n})"}
        elif kind == "text":
            target, change = self.rng.choice(texts), {"kind": "field", "field": "text", "value": self.text()}
        elif kind == "retype":
            target, change = self.rng.choice(dissents), {"kind": "retype", "type": "ACK"}
        elif kind == "delete":
            target, change = self.rng.choice(answers), {"kind": "delete"}
        else:
            target = self.rng.choice(files)
            change = {"kind": "file", "anchors": dict(self.anchors_of[target], build=str(self.rng.randint(100, 999)) + "0")}
        n = self.b.tamper(by, target, change)
        if target in self.live:
            self.live.remove(target)
        self.plant("V01", target, n)

    def p_dup(self) -> None:
        if self.dup_done:
            return self.c_clean()
        self.dup_done = True
        victim = self.rng.choice(self.ids)
        original = self.b.agents[victim]
        second = dict(original, name=original["name"] + " (second account)",
                      email=f"{victim}.second@{self.c['domain']}")
        n = self.b.dup_agent(self.other(victim), second)
        self.plant("V08", f"agent:{victim}", n)

    def p_insert(self) -> None:
        o, to = self.owner_and(1, 2)
        p = self.add("propose", o, to, self.text())
        above = self.rng.choice(self.live)
        self.plant("V09", self.add("ack", to[0], p, note=self.note(), insert_before=above))
        self.ack_all(p, to[1:])

    def p_mojibake(self) -> None:
        o, to = self.owner_and(1, 2)
        accented = [a["name"] for a in self.b.agents.values() if not a["name"].isascii()]
        name = self.rng.choice(accented or ["Inès Carrà"])
        if self.rng.random() < 0.5:
            p = self.add("propose", o, to, f"{self.text()} Checked with {name}.", mojibake=True)
            self.plant("V10", p)
            self.ack_all(p, to)
        else:
            p = self.add("propose", o, to, self.text())
            self.plant("V10", self.add("ack", to[0], p, note=f"checked with {name}", mojibake=True))
            self.ack_all(p, to[1:])

    def p_cycle(self) -> None:
        k = self.rng.choice([2, 3])
        props = []
        for _ in range(k):
            o, to = self.owner_and(1, 1)
            props.append(self.add("propose", o, to, self.text()))
        blocks = [self.add("block", self.rng.choice(self.ids), props[i], on=props[(i + 1) % k]) for i in range(k)]
        self.plant("V06", "+".join(blocks))
        if self.rng.random() < 0.4:
            first = blocks[0]
            self.add("unblock", first.rsplit("-", 1)[0], first)

    def p_stale(self) -> None:
        o2, to2 = self.owner_and(1, 2)
        b = self.add("propose", o2, to2, self.text())
        self.ack_all(b, to2)
        self.add("decide", o2, b)
        o1, to1 = self.owner_and(1, 2)
        a = self.add("propose", o1, to1, self.text())
        x = self.rng.choice(self.ids)
        bl = self.add("block", x, a, on=b)
        self.plant("V07", bl)
        if self.rng.random() < 0.5:
            self.add("unblock", x, bl)

    CYCLES = (("c_clean", 10), ("c_pending", 4), ("c_dispute", 7), ("c_outsider_dispute", 3), ("c_empty_dissent", 4),
              ("c_block", 6), ("c_block_on", 3), ("c_freeze", 6), ("c_handoff", 7), ("c_conflict", 7), ("c_supersede", 3),
              ("c_concurrent", 4), ("c_join", 2))
    PLANTS = (("p_forged", 3), ("p_tamper", 4), ("p_dup", 1.5), ("p_insert", 3), ("p_mojibake", 3), ("p_cycle", 3),
              ("p_stale", 3))

    def build(self) -> dict:
        menu = self.CYCLES if self.clean else self.CYCLES + self.PLANTS
        names, weights = [m[0] for m in menu], [m[1] for m in menu]
        target = self.rng.randint(MIN_COMMITS, 50)
        while self.n < target:
            getattr(self, self.rng.choices(names, weights)[0])()
        if not MIN_COMMITS <= self.n <= MAX_COMMITS:
            raise AssertionError(f"story {self.index}: {self.n} commits")
        gold = reduce_events(self.b.events)
        got = {(v["class"], v["commit_index"], v["target"]) for v in gold["violations"]}
        if got != set(self.planted):
            raise AssertionError(f"story {self.index}: planted {sorted(set(self.planted) - got)} missing from the gold, "
                                 f"gold {sorted(got - set(self.planted))} not planted")
        gold["planted"] = [{"class": c, "commit_index": n, "target": t} for c, n, t in sorted(self.planted, key=lambda v: (v[1], v[0]))]
        return gold


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def story_files(seed: int, index: int, profile: str) -> tuple[dict, dict[str, bytes]]:
    """(index row, {file name: content}) for story number `index` (0-based)."""
    s = Story(seed, index, profile)
    gold = s.build()
    row = {"id": f"story-{index + 1:03d}", "company": s.c["company"], "agents": len(s.ids), "commits": s.n,
           "clean": s.clean, "planted": sorted({c for c, _, _ in s.planted}),
           "merges": sum(1 for ev in s.b.events if ev["op"] == "merge")}
    return row, {"events.json": dumps(s.b.events), "stream.fi": render.stream(s.b.events), "gold.json": dumps(gold)}


def generate(seed: int, out: Path, profile: str = "standard", n: int = DEFAULT_N) -> dict:
    """Write the corpus under `out` and return its index (which holds the SHA-256 of every file)."""
    out.mkdir(parents=True, exist_ok=True)
    rows, sums, by_class = [], {}, {}
    for i in range(n):
        row, files = story_files(seed, i, profile)
        d = out / row["id"]
        d.mkdir(exist_ok=True)
        for name, data in files.items():
            (d / name).write_bytes(data)
            sums[f"{row['id']}/{name}"] = hashlib.sha256(data).hexdigest()
        for c in row["planted"]:
            by_class[c] = by_class.get(c, 0) + 1
        rows.append(row)
    index = {"seed": seed, "profile": profile, "n": n, "stories": rows,
             "stories_planting_class": dict(sorted(by_class.items())), "clean_stories": sum(r["clean"] for r in rows),
             "sha256": sums}
    (out / "index.json").write_bytes(dumps(index))
    return index


def digest(index: dict) -> str:
    """One SHA-256 for the whole corpus: the hash of its sorted per-file hashes."""
    lines = "".join(f"{h}  {path}\n" for path, h in sorted(index["sha256"].items()))
    return hashlib.sha256(lines.encode("ascii")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a synthetic corpus of coordination stories.")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--profile", choices=PROFILES, default="standard")
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    index = generate(a.seed, Path(a.out), a.profile, a.n)
    print(f"corpus seed={a.seed} profile={a.profile} stories={a.n} clean={index['clean_stories']} "
          f"commits={sum(r['commits'] for r in index['stories'])} sha256={digest(index)}")
    print("stories planting each class: " + " ".join(f"{c}={k}" for c, k in index["stories_planting_class"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
