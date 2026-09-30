"""The synthetic world: three invented companies, their invented agents, and the phrases they use.

Everything here is fictitious and was written for this repository. Domains are `.example`.
Names carry accents on purpose: the tooling must keep them intact (see V10 in PROTOCOL.md).
"""
from __future__ import annotations

COMPANIES = {
    "portoluna": {
        "company": "Cantiere Portoluna S.r.l.",
        "domain": "portoluna.example",
        "title": "Portoluna quay works",
        "agents": [
            ("ines", "Inès Carrà", "site lead", "+01:00"),
            ("bruno", "Bruno Šťastný", "structures", "+01:00"),
            ("carla", "Carla Muñoz Peña", "procurement", "+00:00"),
            ("dario", "Dário Åkesson", "safety", "+02:00"),
            ("elio", "Elio Đorđević", "surveying", "+01:00"),
            ("fiona", "Fíona Ó Briain", "design", "+00:00"),
            ("gaia", "Gaïa Lührs", "data", "+02:00"),
            ("hugo", "Hugo Żuławski", "security", "-03:00"),
        ],
        "things": ["slab B2", "pier cap 4", "the east ramp", "crane pad C", "formwork set 7", "the drainage trench",
                   "retaining wall R3", "the site gate", "scaffold tower 2", "rebar cage 11"],
        "actions": ["Pour", "Inspect", "Survey", "Re-order steel for", "Close access to", "Issue drawings for",
                    "Load-test", "Sign off"],
        "scopes": ["quay-release", "drawings-rev", "site-access"],
        "resources": ["designer", "surveyor", "crane", "security-review"],
    },
    "meridiana": {
        "company": "Editrice Meridiana S.r.l.",
        "domain": "meridiana.example",
        "title": "Meridiana autumn list",
        "agents": [
            ("livia", "Lívia Sàez-Brontë", "managing editor", "+02:00"),
            ("marco", "Marco D'Anjò", "copy desk", "+01:00"),
            ("nadia", "Nadia Øvrebø", "design", "+01:00"),
            ("oscar", "Óscar Çelik", "production", "+03:00"),
            ("paola", "Paola Nguyễn", "rights", "+07:00"),
            ("quinn", "Quinn Müller-Łoś", "data", "+00:00"),
            ("rosa", "Rosa Štěpánková", "proofreading", "+01:00"),
            ("sami", "Sámi Ünal", "security", "+03:00"),
        ],
        "things": ["chapter 4", "the cover of title 12", "the index", "the spring catalogue", "galley 3",
                   "the rights sheet", "the ebook build", "the back-cover copy", "plate section B", "the errata slip"],
        "actions": ["Send to proof", "Lock", "Re-set", "Approve", "Hold", "Reprint", "Translate", "Release"],
        "scopes": ["print-release", "catalogue", "ebook-store"],
        "resources": ["designer", "proofreader", "press-slot", "data-analyst"],
    },
    "fiordaliso": {
        "company": "Laboratorio Ottico Fiordaliso",
        "domain": "fiordaliso.example",
        "title": "Fiordaliso lens line",
        "agents": [
            ("teo", "Teó Bălănescu", "lab lead", "+02:00"),
            ("uma", "Uma Kjærsgård", "optics", "+01:00"),
            ("vera", "Vera Ångström-Ruiz", "calibration", "+01:00"),
            ("walt", "Walt Grzybowski", "data", "-05:00"),
            ("xenia", "Xénia Pașca", "quality", "+02:00"),
            ("yuri", "Yuri Håland", "security", "+01:00"),
            ("zita", "Zita Ördög", "design", "+01:00"),
            ("abel", "Ábel Fröding", "supply", "+00:00"),
        ],
        "things": ["lens bench 3", "coating batch 27", "the interferometer", "mould set M5", "the clean room log",
                   "prism order 88", "the alignment jig", "filter lot F2", "the test chart", "polisher 4"],
        "actions": ["Calibrate", "Re-coat", "Quarantine", "Ship", "Re-measure", "Recalibrate", "Accept", "Scrap"],
        "scopes": ["lens-release", "calibration-table", "lab-access"],
        "resources": ["designer", "calibration-rig", "data-analyst", "security-review"],
    },
}

NOTES = ["checked against the drawing", "fine from my side", "seen, no change needed", "agreed with the sequence",
         "counts match mine", "ok after the second reading", "done on my list too", "as discussed in the entry above"]
DISSENTS = ["the sequence breaks the cure time", "the figure does not match my count", "this needs the safety review first",
            "the slot is already taken that day", "the source file is one revision behind", "the supplier has not confirmed",
            "two steps are swapped", "the tolerance is wrong for this batch"]
ANSWERS = ["sequence corrected in the text below the proposal", "count re-done, figure confirmed", "review booked before the step",
           "moved by one day", "rebuilt from the current revision", "confirmation attached to the order"]
EMPTY_DISSENTS = ["none", "n/a", "no objection", "-"]
WEEKS = ["2026-W10", "2026-W11", "2026-W12", "2026-W14", "2026-W15", "2026-W17", "2026-W18", "2026-W20"]


def agent_record(company_key: str, row: tuple[str, str, str, str]) -> dict:
    aid, name, role, tz = row
    return {"id": aid, "name": name, "email": f"{aid}@{COMPANIES[company_key]['domain']}", "role": role, "tz": tz}


def team(company_key: str, ids: list[str] | None = None) -> tuple[dict, list[dict]]:
    """Team header and agent records for a company (all agents, or the given ids in the given order)."""
    c = COMPANIES[company_key]
    rows = {r[0]: r for r in c["agents"]}
    chosen = ids or list(rows)
    header = {"title": c["title"], "company": c["company"], "domain": c["domain"], "key": company_key}
    return header, [agent_record(company_key, rows[i]) for i in chosen]
