"""Grammar of `COORD.md` (PROTOCOL.md sections 2-3).

The parser never guesses. A block that is not an entry is returned as *unparsed*; an entry that breaks
the grammar is returned with its `problems`. What to do about either is decided by the caller
(`coord/state.py` degrades the state; `coord/lint.py` fails).

Tolerated spellings are listed in one place, `TOLERATED`, with the reason each one is accepted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_WS = " \t\r"     # ASCII only: a no-break space at the end of a line is content, not layout
TYPES = ("PROPOSE", "ACK", "DISSENT", "BLOCK", "UNBLOCK", "FREEZE", "LIFT", "DECIDE", "HANDOFF", "RECEIPT", "ARBITRATE")
RESTRAINING = ("DISSENT", "BLOCK", "FREEZE", "HANDOFF")
CLASSES = ("safety", "deadline", "routine")
KNOWN_FIELDS = ("by", "to", "refs", "on", "scope", "supersedes", "resource", "class", "due", "rule", "outcome",
                "anchors", "as_of", "text", "note")
ESCALATE = "ESCALATE_TO_HUMAN"

AGENT_ID = re.compile(r"^[a-z][a-z0-9]*$")
ENTRY_ID = re.compile(r"^([a-z][a-z0-9]*)-([1-9][0-9]*)$")
HEADING = re.compile(r"^### ([A-Z]+) (\S+)$")
FIELD = re.compile(r"^- ([a-z_]+):(?: (.*))?$")
AS_OF = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})$")
DUE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ANCHOR_KEY = re.compile(r"^[a-z][a-z0-9_]*$")

# Spellings accepted beyond the canonical grammar. The first grammar accepted none; its measurement on the
# stress profile (eval/history.json, run "stress-diag first") is what justified each line below, and
# eval/ablation.py measures what each one is worth. All of them are unambiguous: a heading must still hold
# exactly one known type and one entry id. Anything else stays unparsed, and an unparsed block degrades the
# state instead of being guessed.
TOLERATED: dict[str, str] = {
    "bullet_star": "field lines written '* key: value'",
    "bold_key": "field keys written in bold, '- **key**: value'",
    "capital_key": "field keys with capital letters, '- By: ...'",
    "type_lowercase": "entry type in lower case, '### propose ines-1'",
    "heading_colon": "a colon after the type, '### PROPOSE: ines-1'",
    "heading_id_first": "id before the type, '### ines-1 PROPOSE'",
    "heading_h4": "a level-4 heading, '#### PROPOSE ines-1'",
    "list_semicolon": "lists separated by ';' instead of ','",
}
ACTIVE: set[str] = set(TOLERATED)       # eval/ablation.py switches them off one at a time to measure them
_LOOSE_HEADING = re.compile(r"^### (\S+?)(:?) (\S+)$")
_LOOSE_FIELD = re.compile(r"^([-*]) (\*\*)?([A-Za-z_]+)(\*\*)?:(?: (.*))?$")

REQUIRED = {
    "PROPOSE": ("to", "text"), "ACK": ("refs",), "DISSENT": ("refs",), "BLOCK": ("refs",), "UNBLOCK": ("refs",),
    "FREEZE": ("scope", "to"), "LIFT": ("refs",), "DECIDE": ("refs",), "HANDOFF": ("to", "anchors"),
    "RECEIPT": ("refs", "anchors"), "ARBITRATE": ("refs", "rule", "outcome"),
}
REF_COUNT = {"DISSENT": 1, "BLOCK": 1, "UNBLOCK": 1, "LIFT": 1, "DECIDE": 1, "RECEIPT": 1, "ARBITRATE": 2}


@dataclass
class Entry:
    type: str
    id: str
    line: int                              # 1-based line of the heading in the document
    raw: str                               # canonical text of the block (for change detection)
    fields: dict[str, str] = field(default_factory=dict)
    by: str = ""
    to: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    anchors: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)     # grammar violations: the entry is malformed
    warnings: list[tuple[str, str]] = field(default_factory=list)
    # set by coord/gitlog.py when the entry is read from a history
    commit_index: int = 0
    seq: int = 0
    author_email: str = ""
    doubt: set[str] = field(default_factory=set)

    def get(self, key: str) -> str | None:
        return self.fields.get(key)

    @property
    def text(self) -> str:
        return self.fields.get("note" if self.type == "ACK" else "text", "")


@dataclass
class AgentLine:
    id: str
    name: str
    email: str
    role: str
    raw: str
    line: int


@dataclass
class Unparsed:
    raw: str
    line: int
    reason: str


@dataclass
class Doc:
    header: str = ""
    protocol: str | None = None
    agents: list[AgentLine] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    unparsed: list[Unparsed] = field(default_factory=list)


def _canon(lines: list[str]) -> str:
    out = [ln.rstrip(_WS) for ln in lines]
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def split_list(value: str) -> list[str]:
    parts = re.split(r"[,;]", value) if "list_semicolon" in ACTIVE else value.split(",")
    return [x.strip(_WS) for x in parts if x.strip(_WS)]


def _heading(line: str) -> tuple[str, str] | None:
    """(type, id) of an entry heading, or None."""
    m = HEADING.match(line)
    if m:
        return m.group(1), m.group(2)
    if "heading_h4" in ACTIVE and line.startswith("#### "):
        line = line[1:]
    m = _LOOSE_HEADING.match(line)
    if not m:
        return None
    a, colon, b = m.groups()
    if colon and "heading_colon" not in ACTIVE:
        return None
    if "heading_id_first" in ACTIVE and not colon and ENTRY_ID.match(a) and not ENTRY_ID.match(b):
        a, b = b, a
    if "type_lowercase" in ACTIVE and a.islower():
        a = a.upper()
    return a, b


def _field(line: str) -> tuple[str, str | None] | None:
    """(key, value) of a field line, or None."""
    m = FIELD.match(line)
    if m:
        return m.group(1), m.group(2)
    m = _LOOSE_FIELD.match(line)
    if not m:
        return None
    bullet, b1, key, b2, value = m.groups()
    if bullet == "*" and "bullet_star" not in ACTIVE:
        return None
    if bool(b1) != bool(b2) or (b1 and "bold_key" not in ACTIVE):
        return None
    if key != key.lower():
        if "capital_key" not in ACTIVE:
            return None
        key = key.lower()
    return key, value


def parse_anchors(value: str) -> dict[str, str] | None:
    out: dict[str, str] = {}
    for part in value.split(";"):
        if not part.strip(_WS):
            continue
        key, sep, val = part.partition("=")
        key, val = key.strip(_WS), val.strip(_WS)
        if not sep or not ANCHOR_KEY.match(key) or not val or key in out:
            return None
        out[key] = val
    return out or None


def _validate(e: Entry) -> None:
    f = e.fields
    m = ENTRY_ID.match(e.id)
    e.by = f.get("by", "")
    if "by" not in f or not AGENT_ID.match(e.by):
        e.problems.append("missing or malformed 'by'")
    elif m.group(1) != e.by:
        e.problems.append(f"id {e.id} does not belong to 'by: {e.by}'")
    if "as_of" not in f:
        e.problems.append("missing 'as_of'")
    elif not AS_OF.match(f["as_of"]):
        e.warnings.append(("as_of_unanchored", f"as_of '{f['as_of']}' has no UTC offset"))
    for key in REQUIRED[e.type]:
        if not f.get(key):
            e.problems.append(f"missing '{key}'")
    e.to = split_list(f.get("to", ""))
    e.refs = split_list(f.get("refs", ""))
    if any(not AGENT_ID.match(a) for a in e.to) or len(set(e.to)) != len(e.to):
        e.problems.append("'to' must be a list of distinct agent ids")
    if any(not ENTRY_ID.match(r) for r in e.refs) or len(set(e.refs)) != len(e.refs):
        e.problems.append("'refs' must be a list of distinct entry ids")
    want = REF_COUNT.get(e.type)
    if want is not None and e.refs and len(e.refs) != want:
        e.problems.append(f"{e.type} needs exactly {want} reference(s)")
    if e.type == "HANDOFF" and e.to and len(e.to) != 1:
        e.problems.append("HANDOFF needs exactly one recipient")
    for key in ("on", "supersedes"):
        if key in f and not ENTRY_ID.match(f[key]):
            e.problems.append(f"'{key}' must be an entry id")
    if "anchors" in f:
        anchors = parse_anchors(f["anchors"])
        if anchors is None:
            e.problems.append("'anchors' must be 'key=value; key=value'")
        else:
            e.anchors = anchors
    if "class" in f and f["class"] not in CLASSES:
        e.problems.append(f"unknown class '{f['class']}'")
    if "due" in f and not DUE.match(f["due"]):
        e.problems.append("'due' must be YYYY-MM-DD")
    if e.type == "ARBITRATE" and f.get("outcome") and f["outcome"] != ESCALATE and not ENTRY_ID.match(f["outcome"]):
        e.problems.append("'outcome' must be a proposal id or ESCALATE_TO_HUMAN")
    for key in f:
        if key not in KNOWN_FIELDS:
            e.warnings.append(("unknown_field", f"field '{key}' is not part of coord/1"))


def _entry(block: list[str], line: int) -> Entry | Unparsed:
    head = _heading(block[0].rstrip(_WS))
    if not head or head[0] not in TYPES or not ENTRY_ID.match(head[1]):
        return Unparsed(_canon(block), line, "heading is not '### <TYPE> <id>'")
    e = Entry(type=head[0], id=head[1], line=line, raw=_canon(block))
    for ln in block[1:]:
        ln = ln.rstrip(_WS)
        if not ln:
            continue
        fm = _field(ln)
        if not fm:
            e.problems.append(f"unreadable line: {ln[:60]}")
            continue
        key, value = fm[0], (fm[1] or "").strip(_WS)
        if key in e.fields:
            e.problems.append(f"field '{key}' given twice")
            continue
        e.fields[key] = value
    _validate(e)
    return e


def parse_doc(data: bytes | str) -> Doc:
    """Parse one version of `COORD.md`."""
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    lines = text.split("\n")
    doc = Doc()
    stripped = [ln.rstrip(_WS) for ln in lines]
    try:
        a = stripped.index("## Agents")
    except ValueError:
        a = None
    try:
        g = stripped.index("## Log")
    except ValueError:
        g = None
    head_end = min(x for x in (a, g, len(lines)) if x is not None)
    doc.header = _canon(lines[:head_end])
    for ln in stripped[:head_end]:
        if ln.startswith("protocol:"):
            doc.protocol = ln.split(":", 1)[1].strip(_WS)
    if a is None:
        doc.unparsed.append(Unparsed("", 1, "no '## Agents' section"))
    if g is None:
        doc.unparsed.append(Unparsed("", 1, "no '## Log' section"))
        return doc
    if a is not None and a < g:
        for i in range(a + 1, g):
            ln = stripped[i]
            if not ln:
                continue
            parts = [p.strip(_WS) for p in ln[2:].split("|")] if ln.startswith("- ") else []
            if len(parts) == 4 and AGENT_ID.match(parts[0]) and "@" in parts[2] and parts[1]:
                doc.agents.append(AgentLine(parts[0], parts[1], parts[2], parts[3], ln, i + 1))
            else:
                doc.unparsed.append(Unparsed(ln, i + 1, "not an agent line '- id | name | email | role'"))
    elif a is not None:
        doc.unparsed.append(Unparsed("", a + 1, "'## Agents' must come before '## Log'"))
    # the log: blocks open at every heading line
    block: list[str] = []
    start = g + 2
    seen: set[str] = set()

    def close() -> None:
        if not block:
            return
        if not block[0].startswith("#"):
            if _canon(block):
                doc.unparsed.append(Unparsed(_canon(block), start, "text outside an entry"))
            return
        item = _entry(block, start)
        if isinstance(item, Unparsed):
            doc.unparsed.append(item)
            return
        if item.id in seen:
            item.problems.append(f"entry id {item.id} appears twice in the document")
        seen.add(item.id)
        doc.entries.append(item)

    for i in range(g + 1, len(lines)):
        if lines[i].startswith("#"):
            close()
            block, start = [lines[i]], i + 1
        else:
            if not block:
                start = i + 1
            block.append(lines[i])
    close()
    return doc


# -- findings and text checks shared by the readers -------------------------------------------------------

VIOLATIONS = {
    "V01": "modified_in_place", "V02": "author_mismatch", "V03": "handoff_without_receipt", "V04": "anchor_mismatch",
    "V05": "gate_without_consents", "V06": "dependency_cycle", "V07": "stale_pending", "V08": "duplicate_agent_id",
    "V09": "order_by_local_time", "V10": "corrupted_accents", "V11": "arbitration_without_rule",
}
STRUCTURAL = ("unparsed", "malformed", "invalid", "ambiguous")
WARNINGS = ("no_effect", "empty_dissent", "as_of_unanchored", "unknown_field")


@dataclass(frozen=True)
class Finding:
    cls: str                 # V01..V11, or one of STRUCTURAL, or one of WARNINGS
    commit_index: int
    target: str
    detail: str = ""
    cites: tuple[str, ...] = ()

    @property
    def severity(self) -> str:
        return "warn" if self.cls in WARNINGS else "error"

    @property
    def name(self) -> str:
        return VIOLATIONS.get(self.cls, self.cls)

    def as_dict(self) -> dict:
        d = {"class": self.cls, "name": self.name, "commit_index": self.commit_index, "target": self.target,
             "severity": self.severity, "detail": self.detail}
        if self.cites:
            d["cites"] = list(self.cites)
        return d


def looks_corrupted(text: str) -> bool:
    """True when some word is UTF-8 that was decoded with a single-byte encoding ('InÃ¨s'), or lost ('In?s' as U+FFFD)."""
    if "\ufffd" in text:
        return True
    for word in re.split(r"[ \t\r\n]+", text):
        if word.isascii():
            continue
        for codec in ("cp1252", "latin-1"):
            try:
                fixed = word.encode(codec).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if fixed != word:
                return True
    return False
