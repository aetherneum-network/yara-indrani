"""Grammar of COORD.md: what is read, what is tolerated and why, what is refused instead of guessed."""
import unittest

from coord import parse
from tests import ROOT

HEAD = ["# COORD - Portoluna quay works", "", "protocol: coord/1", "", "## Agents", "",
        "- ines | Inès Quaranta | ines@portoluna.example | site lead",
        "- bruno | Bruno Alfieri | bruno@portoluna.example | formwork", "", "## Log", ""]
PROPOSE = ["### PROPOSE ines-1", "- by: ines", "- to: bruno, carla", "- as_of: 2026-02-02T09:00:00+01:00", "- text: Pour slab B2."]


def doc(*blocks: list[str], eol: str = "\n") -> parse.Doc:
    lines = list(HEAD)
    for blk in blocks:
        lines += blk + [""]
    return parse.parse_doc((eol.join(lines) + eol).encode("utf-8"))


class Canonical(unittest.TestCase):
    def test_header_agents_and_entry(self):
        d = doc(PROPOSE)
        self.assertEqual(d.protocol, "coord/1")
        self.assertEqual([a.id for a in d.agents], ["ines", "bruno"])
        self.assertEqual(d.agents[0].name, "Inès Quaranta")
        self.assertEqual(d.agents[0].email, "ines@portoluna.example")
        (e,) = d.entries
        self.assertEqual((e.type, e.id, e.by, e.to, e.text, e.problems), ("PROPOSE", "ines-1", "ines", ["bruno", "carla"],
                                                                         "Pour slab B2.", []))
        self.assertEqual(d.unparsed, [])

    def test_the_template_parses_once_filled_and_is_refused_while_empty(self):
        template = (ROOT / "templates" / "COORD.md").read_text(encoding="utf-8")
        empty = parse.parse_doc(template.encode("utf-8"))
        self.assertEqual(empty.protocol, "coord/1")
        self.assertEqual((empty.entries, empty.agents), ([], []))          # placeholders are not guessed
        self.assertTrue(empty.unparsed)
        filled = template.replace("- <id> |", "- ines |", 1).replace("- <id> |", "- bruno |", 1)
        filled = filled.replace("<email the agent commits with>", "ines@portoluna.example", 1)
        filled = filled.replace("<email the agent commits with>", "bruno@portoluna.example", 1)
        filled = filled.replace("PROPOSE <id>-1", "PROPOSE ines-1").replace("by: <id>", "by: ines")
        filled = filled.replace("to: <id>, <id>", "to: bruno").replace("<YYYY-MM-DDTHH:MM:SS+HH:MM>", "2026-02-02T09:00:00+01:00")
        d = parse.parse_doc(filled.encode("utf-8"))
        self.assertEqual(d.unparsed, [])
        self.assertEqual([a.id for a in d.agents], ["ines", "bruno"])
        self.assertEqual([(e.type, e.id, e.problems, e.warnings) for e in d.entries], [("PROPOSE", "ines-1", [], [])])

    def test_anchors(self):
        self.assertEqual(parse.parse_anchors("build=412; tag=v1.4.0"), {"build": "412", "tag": "v1.4.0"})
        self.assertIsNone(parse.parse_anchors("build 412"))
        self.assertIsNone(parse.parse_anchors("build=412; build=413"))

    def test_crlf_and_lf_give_the_same_entries(self):
        a, b = doc(PROPOSE), doc(PROPOSE, eol="\r\n")
        self.assertEqual([(e.type, e.id, e.fields, e.raw) for e in a.entries], [(e.type, e.id, e.fields, e.raw) for e in b.entries])

    def test_ack_note_is_its_text(self):
        (e,) = doc(["### ACK bruno-1", "- by: bruno", "- refs: ines-1", "- as_of: 2026-02-02T09:10:00Z", "- note: fine"]).entries
        self.assertEqual((e.refs, e.text), (["ines-1"], "fine"))


class Refused(unittest.TestCase):
    """Nothing here is guessed: the block is reported as it is."""

    def problems(self, *lines: str) -> list[str]:
        d = doc(list(lines))
        return [p for e in d.entries for p in e.problems] + [u.reason for u in d.unparsed]

    def test_unknown_type(self):
        d = doc(["### AGREE bruno-1", "- by: bruno", "- refs: ines-1"])
        self.assertEqual(d.entries, [])
        self.assertEqual(len(d.unparsed), 1)

    def test_free_text_in_the_log_is_not_an_entry(self):
        d = doc(["We agreed on the phone that bruno is fine with it."])
        self.assertEqual(d.entries, [])
        self.assertEqual(len(d.unparsed), 1)

    def test_id_must_belong_to_its_author(self):
        self.assertTrue(self.problems("### ACK bruno-1", "- by: ines", "- refs: ines-1", "- as_of: 2026-02-02T09:10:00Z"))

    def test_missing_required_field(self):
        self.assertTrue(self.problems("### PROPOSE ines-1", "- by: ines", "- as_of: 2026-02-02T09:00:00Z", "- text: Pour."))
        self.assertTrue(self.problems("### ACK bruno-1", "- by: bruno", "- as_of: 2026-02-02T09:00:00Z"))
        self.assertTrue(self.problems("### HANDOFF ines-1", "- by: ines", "- to: bruno", "- as_of: 2026-02-02T09:00:00Z"))

    def test_wrong_number_of_references(self):
        self.assertTrue(self.problems("### DECIDE ines-2", "- by: ines", "- refs: ines-1, ines-3", "- as_of: 2026-02-02T09:00:00Z"))
        self.assertTrue(self.problems("### ARBITRATE ines-2", "- by: ines", "- refs: bruno-1", "- rule: R-DUE", "- outcome: bruno-1",
                                      "- as_of: 2026-02-02T09:00:00Z"))

    def test_bad_anchors(self):
        self.assertTrue(self.problems("### HANDOFF ines-1", "- by: ines", "- to: bruno", "- anchors: build 412",
                                      "- as_of: 2026-02-02T09:00:00Z"))

    def test_a_timestamp_without_offset_is_a_warning_because_as_of_orders_nothing(self):
        (e,) = doc(["### ACK bruno-1", "- by: bruno", "- refs: ines-1", "- as_of: 2026-02-02 09:10"]).entries
        self.assertEqual(e.problems, [])
        self.assertEqual([w[0] for w in e.warnings], ["as_of_unanchored"])

    def test_duplicate_field(self):
        self.assertTrue(self.problems("### ACK bruno-1", "- by: bruno", "- by: ines", "- refs: ines-1", "- as_of: 2026-02-02T09:00:00Z"))

    def test_heading_with_two_types_or_no_id(self):
        for heading in ("### ACK DISSENT bruno-1", "### ACK", "### bruno-1", "## ACK bruno-1"):
            d = doc([heading, "- by: bruno", "- refs: ines-1", "- as_of: 2026-02-02T09:00:00Z"])
            self.assertEqual([e for e in d.entries if not e.problems], [], heading)


class Tolerated(unittest.TestCase):
    """Each tolerated spelling is accepted while it is active and refused when it is switched off."""
    CASES = {
        "bullet_star": ["### PROPOSE ines-1", "* by: ines", "* to: bruno, carla", "* as_of: 2026-02-02T09:00:00Z", "* text: Pour."],
        "bold_key": ["### PROPOSE ines-1", "- **by**: ines", "- **to**: bruno, carla", "- **as_of**: 2026-02-02T09:00:00Z",
                     "- **text**: Pour."],
        "capital_key": ["### PROPOSE ines-1", "- By: ines", "- To: bruno, carla", "- As_of: 2026-02-02T09:00:00Z", "- Text: Pour."],
        "type_lowercase": ["### propose ines-1"] + PROPOSE[1:],
        "heading_colon": ["### PROPOSE: ines-1"] + PROPOSE[1:],
        "heading_id_first": ["### ines-1 PROPOSE"] + PROPOSE[1:],
        "heading_h4": ["#### PROPOSE ines-1"] + PROPOSE[1:],
        "list_semicolon": ["### PROPOSE ines-1", "- by: ines", "- to: bruno; carla", "- as_of: 2026-02-02T09:00:00Z", "- text: Pour."],
    }

    def tearDown(self):
        parse.ACTIVE.clear()
        parse.ACTIVE.update(parse.TOLERATED)

    def good(self, d: parse.Doc) -> bool:
        return (len(d.entries) == 1 and not d.entries[0].problems and not d.unparsed
                and (d.entries[0].type, d.entries[0].id, d.entries[0].by, d.entries[0].to) == ("PROPOSE", "ines-1", "ines", ["bruno", "carla"]))

    def test_every_tolerance_has_a_case_and_a_reason(self):
        self.assertEqual(sorted(self.CASES), sorted(parse.TOLERATED))
        self.assertTrue(all(reason for reason in parse.TOLERATED.values()))

    def test_accepted_when_active_refused_when_off(self):
        for key, block in self.CASES.items():
            with self.subTest(tolerance=key):
                self.assertTrue(self.good(doc(block)), "accepted while active")
                parse.ACTIVE.discard(key)
                self.assertFalse(self.good(doc(block)), "refused when switched off")
                parse.ACTIVE.add(key)

    def test_canonical_grammar_needs_no_tolerance(self):
        parse.ACTIVE.clear()
        self.assertTrue(self.good(doc(PROPOSE)))


class Accents(unittest.TestCase):
    def test_real_accents_are_not_corruption(self):
        for text in ("Inès Quaranta", "Zoë Günther", "già fatto, così com'è", "naïve façade", "plain ascii"):
            self.assertFalse(parse.looks_corrupted(text), text)

    def test_mojibake_is_detected(self):
        for text in ("Inès Quaranta", "già fatto", "Zoë"):
            broken = text.encode("utf-8").decode("latin-1")
            self.assertTrue(parse.looks_corrupted(broken), broken)
        self.assertTrue(parse.looks_corrupted("In\ufffds"))

    def test_no_break_space_at_the_end_of_a_value_is_content(self):
        (e,) = doc(["### ACK bruno-1", "- by: bruno", "- refs: ines-1", "- as_of: 2026-02-02T09:10:00Z", "- note: giÃ "]).entries
        self.assertTrue(parse.looks_corrupted(e.text))


if __name__ == "__main__":
    unittest.main()
