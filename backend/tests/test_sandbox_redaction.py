"""PII redaction: nothing identifying leaves the machine, and replies are restored locally."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import redaction as rd  # noqa: E402

ENTITIES = [
    {"entity_type": "person", "canonical_name": "Ramesh Kumaran", "aliases": "R. Kumaran,Kumaran,Ramesh"},
    {"entity_type": "person", "canonical_name": "Priya Nair", "aliases": ""},
    {"entity_type": "location", "canonical_name": "MedVantage Pharmacy", "aliases": ""},
]


def test_person_names_and_aliases_are_replaced_consistently():
    r = rd.build_redactor(ENTITIES)
    out = r.redact("R. Kumaran told Priya Nair that Ramesh locked up at MedVantage Pharmacy. Kumaran left.")
    assert "Kumaran" not in out and "Priya" not in out and "Ramesh" not in out
    assert "MedVantage Pharmacy" in out, "places are scene facts and are kept"
    assert out.count("PERSON_1") == 3 and out.count("PERSON_2") == 1


def test_no_partial_word_damage():
    r = rd.build_redactor(ENTITIES)
    assert "Ramesha" in r.redact("the shop Ramesha opens at nine"), "only whole words are matched"


def test_identifiers_are_replaced():
    r = rd.build_redactor([])
    text = "Call +91 98765 43210 or mail raj.k@example.com. Aadhaar 1234 5678 9012, PAN ABCDE1234F, car TN 09 AB 1234, IMEI 356938035643809, a/c 1234567890123456."
    out = r.redact(text)
    for secret in ("98765", "raj.k@example.com", "1234 5678 9012", "ABCDE1234F", "TN 09 AB 1234", "356938035643809", "1234567890123456"):
        assert secret not in out, secret
    assert {"PHONE", "EMAIL", "AADHAAR", "PAN", "PLATE", "IMEI", "NUMBER"} <= set(r.counts)


def test_ordinary_numbers_and_times_survive():
    r = rd.build_redactor([])
    out = r.redact("At 02:24 a 3.5 m shutter, 12 boxes, room 204, 2026-03-05.")
    assert out == "At 02:24 a 3.5 m shutter, 12 boxes, room 204, 2026-03-05."


def test_roundtrip_restores_nested_json_and_ignores_foreign_placeholders():
    r = rd.build_redactor(ENTITIES)
    red = r.redact("Priya Nair phoned 9876543210")
    reply = {"title": f"{red.split()[0]} and PERSON_99", "facts": [{"text": red}], "n": 3}
    back = r.restore_json(reply)
    assert back["facts"][0]["text"] == "Priya Nair phoned 9876543210" and back["title"].startswith("Priya Nair") and "PERSON_99" in back["title"] and back["n"] == 3


def test_same_value_gets_the_same_placeholder_across_calls():
    r = rd.build_redactor([])
    a = r.redact("call 9876543210")
    b = r.redact("again 9876543210 please")
    assert a.split()[-1] == b.split()[1]


def test_switched_off_is_explicit(monkeypatch):
    monkeypatch.setenv("SANDBOX_REDACT_PII", "0")
    assert rd.redaction_enabled() is False
    r = rd.build_redactor(ENTITIES, enabled=False)
    assert r.redact("Priya Nair") == "Priya Nair" and r.summary()["enabled"] is False
    monkeypatch.setenv("SANDBOX_REDACT_PII", "1")
    assert rd.redaction_enabled() is True


def test_summary_states_what_is_not_covered():
    r = rd.build_redactor(ENTITIES)
    r.redact("Priya Nair")
    s = r.summary()
    assert s["enabled"] and s["replacements"]["PERSON"] == 1 and any("place" in x for x in s["not_covered"])
