"""Ordered rule files: first match wins, exceptions on top.

Decisions live in `rules/*.json`, not in code. To change a decision, change a rule (and its order);
never an output. Every rule has an `id`, and every decision the tooling takes can name the rule it came from.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "rules"
FILES = ("transitions", "freeze", "dissent_nature", "arbitration")


class RuleError(ValueError):
    pass


def matches(when: dict, facts: dict) -> bool:
    """Every key of `when` must hold in `facts`. A list means 'one of'."""
    for key, want in when.items():
        have = facts.get(key)
        if isinstance(want, list):
            if isinstance(have, (list, set, frozenset, tuple)):
                if not set(want) & set(have):
                    return False
            elif have not in want:
                return False
        elif isinstance(have, (list, set, frozenset, tuple)):
            if want not in have:
                return False
        elif have != want:
            return False
    return True


def first_match(rules: list[dict], facts: dict) -> dict | None:
    for rule in rules:
        if matches(rule.get("when", {}), facts):
            return rule
    return None


@dataclass(frozen=True)
class RuleSet:
    transitions: dict
    freeze: dict
    dissent_nature: dict
    arbitration: dict
    sha256: dict
    version: dict

    # -- nature of a response (PROTOCOL.md 4.2) -------------------------------------------------------
    def substance(self, text: str | None) -> bool:
        t = (text or "").strip().rstrip(".").strip().lower()
        return t not in set(self.dissent_nature["no_substance"])

    def nature(self, etype: str, text: str | None) -> tuple[str, str]:
        rule = first_match(self.dissent_nature["rules"], {"type": etype, "substance": self.substance(text)})
        if rule is None:
            raise RuleError(f"no nature rule for {etype}")
        return rule["then"], rule["id"]

    # -- effect of a response on its target (4.1-4.4, 4.7) ----------------------------------------------
    def effect(self, etype: str, target: str, roles: set[str], nature: str) -> tuple[list[str], str]:
        rule = first_match(self.transitions["rules"], {"type": etype, "target": target, "role": roles, "nature": nature})
        if rule is None:
            raise RuleError(f"no transition rule for {etype} on {target}")
        return list(rule["then"]), rule["id"]

    # -- who must consent (4.1, 4.3, 4.4) ---------------------------------------------------------------
    def required(self, gate: str, by: str, to: list[str]) -> list[str]:
        rule = first_match(self.freeze["consents"], {"gate": gate})
        if rule is None:
            raise RuleError(f"no consent rule for gate {gate}")
        out: list[str] = []
        for part in rule["then"]["required"]:
            for a in ([by] if part == "by" else to):
                if a not in out:
                    out.append(a)
        return out

    # -- release gate (4.6) ---------------------------------------------------------------------------------
    def release(self, facts: dict) -> tuple[str, str]:
        rule = first_match(self.freeze["release"], facts)
        if rule is None:
            raise RuleError("no release rule")
        return rule["then"], rule["id"]


def load(directory: str | Path | None = None) -> RuleSet:
    d = Path(directory) if directory else DEFAULT_DIR
    data, sha, version = {}, {}, {}
    for name in FILES:
        raw = (d / f"{name}.json").read_bytes()
        data[name] = json.loads(raw.decode("utf-8"))
        sha[name] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        version[name] = data[name].get("version")
        ids = [r["id"] for key in ("rules", "consents", "release") for r in data[name].get(key, [])]
        if len(ids) != len(set(ids)):
            raise RuleError(f"{name}.json: duplicate rule id")
    return RuleSet(data["transitions"], data["freeze"], data["dissent_nature"], data["arbitration"], sha, version)
