"""Sections suggested by the model get their empty legal details from the bundled corpus, never invented."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.legal_advisor import _fill_from_corpus  # noqa: E402

BNS = "Bharatiya Nyaya Sanhita, 2023"


def test_empty_details_are_filled_from_the_corpus_by_base_section():
    out = _fill_from_corpus({"act": BNS, "section": "305(a)", "bailable": None, "cognizable": None, "punishment": None, "triable_by": ""})
    assert out["punishment"] == "Imprisonment up to 7 years and fine" and out["bailable"] is False and out["cognizable"] is True
    assert out["triable_by"] == "Any Magistrate" and "unverified" in out["details_source"]


def test_a_value_the_model_gave_is_kept():
    out = _fill_from_corpus({"act": BNS, "section": "305", "punishment": "model text", "bailable": True})
    assert out["punishment"] == "model text" and out["bailable"] is True


def test_a_section_not_in_the_corpus_is_left_empty_and_unsourced():
    sec = {"act": "Some Other Act, 1999", "section": "9", "punishment": None}
    assert _fill_from_corpus(sec) == sec and "details_source" not in _fill_from_corpus(sec)
