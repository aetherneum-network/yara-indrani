"""Handoff sentinel: a handoff is received only when the receipt repeats every fixed point.

Compares the anchors of a `HANDOFF` with those of its `RECEIPT`, and each entry with the JSON file that
must accompany it (`handoffs/<id>.json`, `receipts/<id>.json`). It reports the differences and the two
files; it never picks a side.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def diff(handoff: dict[str, str], receipt: dict[str, str]) -> list[dict]:
    """Fixed points on which the two sides disagree, by anchor name."""
    out = []
    for key in sorted(set(handoff) | set(receipt)):
        if handoff.get(key) != receipt.get(key):
            out.append({"anchor": key, "handoff": handoff.get(key), "receipt": receipt.get(key)})
    return out


def describe(diffs: list[dict]) -> str:
    def side(v):
        return "missing" if v is None else f"'{v}'"
    return "; ".join(f"{d['anchor']}: handoff {side(d['handoff'])}, receipt {side(d['receipt'])}" for d in diffs)


def validate(obj, schema: dict, where: str = "$") -> list[str]:
    """The subset of JSON Schema used by schemas/*.json. Returns the problems found ([] = valid)."""
    out: list[str] = []
    t = schema.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            return [f"{where}: not an object"]
        for key in schema.get("required", []):
            if key not in obj:
                out.append(f"{where}: missing '{key}'")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        names = schema.get("propertyNames", {}).get("pattern")
        if len(obj) < schema.get("minProperties", 0):
            out.append(f"{where}: needs at least {schema['minProperties']} member(s)")
        for key, value in obj.items():
            if names and not re.search(names, key):
                out.append(f"{where}: bad member name '{key}'")
            if key in props:
                out += validate(value, props[key], f"{where}.{key}")
            elif extra is False:
                out.append(f"{where}: unexpected member '{key}'")
            elif isinstance(extra, dict):
                out += validate(value, extra, f"{where}.{key}")
    elif t == "string":
        if not isinstance(obj, str):
            return [f"{where}: not a string"]
        if len(obj) < schema.get("minLength", 0):
            out.append(f"{where}: empty")
        if "enum" in schema and obj not in schema["enum"]:
            out.append(f"{where}: must be one of {schema['enum']}")
        if "pattern" in schema and not re.search(schema["pattern"], obj):
            out.append(f"{where}: does not match {schema['pattern']}")
    elif t is not None:
        out.append(f"{where}: schema type '{t}' is not supported by this validator")
    return out


def load_schema(kind: str) -> dict:
    return json.loads((SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))


def check_file(kind: str, expected: dict, content: bytes | None) -> list[str]:
    """Problems of the file that accompanies an entry. `expected` holds what the entry says
    (id, by, to | handoff, anchors); `kind` is 'handoff' or 'receipt'."""
    if content is None:
        return ["file is missing"]
    try:
        obj = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ["file is not UTF-8 JSON"]
    problems = validate(obj, load_schema(kind))
    if problems:
        return problems
    for key, want in expected.items():
        if obj.get(key) != want:
            problems.append(f"'{key}' in the file differs from the entry")
    return problems


def main(argv: list[str] | None = None) -> int:
    from coord import gitlog, state as state_mod

    ap = argparse.ArgumentParser(prog="coord.sentinel", description="Compare every handoff with its receipt.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    st = state_mod.derive(gitlog.read(a.repo))
    rows = [{"handoff": hid, "status": st.status["handoffs"][hid], **h} for hid, h in st.details["handoffs"].items()]
    if a.json:
        text = json.dumps({"handoffs": rows, "release_gate": st.release_gate}, indent=2, sort_keys=True, ensure_ascii=False)
    else:
        lines = []
        for r in rows:
            lines.append(f"{r['handoff']} {r['by']} -> {r['to']}: {r['status']}")
            if r["diff"]:
                lines.append(f"  differs: {describe(r['diff'])}")
                lines.append(f"  files: {', '.join(r['files'])}")
            for p in r["file_problems"]:
                lines.append(f"  {p}")
        lines.append(f"release gate: {st.release_gate}")
        text = "\n".join(lines)
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 3 if any(r["status"] != "RECEIVED" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
