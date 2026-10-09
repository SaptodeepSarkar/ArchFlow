import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "build_v6_icsi_stt_sqlite.py"
SPEC = importlib.util.spec_from_file_location("build_v6_icsi_stt_sqlite", MODULE_PATH)
icsi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(icsi)


def word(text, category="W"):
    element = ET.Element("w", {"c": category})
    element.text = text
    return element


class ICSIImportTests(unittest.TestCase):
    def test_nonlexical_disfluency_marker_is_dropped_without_deleting_adjacent_words(self):
        transcript, count = icsi.transcript([
            word("I"), word("I"), ET.Element("disfmarker"), word("think"), word(".", ".")
        ])

        self.assertEqual(transcript, "I I think.")
        self.assertEqual(count, 3)

    def test_apostrophe_attaches_to_the_preceding_lexical_token(self):
        transcript, count = icsi.transcript([word("we"), word("'re", "APOSS")])

        self.assertEqual(transcript, "we're")
        self.assertEqual(count, 2)

    def test_participant_split_matches_pinned_seed_assignment(self):
        self.assertEqual(icsi.participant_split("participant-a", "fixed-seed"), "train")

    def test_invalid_or_incomplete_word_timestamps_are_rejected(self):
        self.assertIsNone(icsi.timestamp(ET.Element("w", {"starttime": "", "endtime": "1.0"})))
        self.assertIsNone(icsi.timestamp(ET.Element("w", {"starttime": "2.0", "endtime": "1.0"})))
        self.assertEqual(icsi.timestamp(ET.Element("w", {"starttime": "0.2", "endtime": "0.7"})),
                         (0.2, 0.7))


if __name__ == "__main__":
    unittest.main()
