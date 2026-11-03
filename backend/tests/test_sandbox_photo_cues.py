"""Photo readings from Meta's vision model: off by default, qualitative, checked, capped, and kept with the run. The model is faked."""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from pipeline import sandbox  # noqa: E402

EV = {"evidence_items": [{"evidence_id": f"EV-{i}", "filename": f"photo{i}.jpg", "evidence_type": "image"} for i in range(6)] + [{"evidence_id": "EV-DOC", "filename": "a.txt", "evidence_type": "text_document"}],
      "observations": [], "entities": [], "conflicts": [], "relationships": [], "timeline": []}
CALLS = []

GOOD = {"scene": "A rear alley outside a shop.", "items": [
    {"what": "roller shutter", "kind": "shutter", "state": "forced", "note": "bottom lock prised"},
    {"what": "padlock", "kind": "NONSENSE", "state": "weird", "note": "n" * 300},
    {"what": "", "kind": "door", "state": "open", "note": "empty names are dropped"}] + [{"what": f"thing {i}", "kind": "other", "state": "unknown", "note": ""} for i in range(12)],
    "scale_cues": ["a standard padlock"], "cannot_tell": ["the interior"]}


def fake_vision(system, prompt, image_path, max_tokens=2048):
    CALLS.append(str(image_path))
    if "photo3" in str(image_path):
        raise RuntimeError("model hiccup")
    if "photo2" in str(image_path):
        return "meta", "not json at all"
    return "meta", json.dumps(GOOD)


@pytest.fixture()
def vision(monkeypatch):
    CALLS.clear()
    monkeypatch.setattr(sandbox, "chat_vision", fake_vision)
    monkeypatch.setattr("storage.get_object_path", lambda case, eid, fn: Path("fake") / fn)
    monkeypatch.setenv("SANDBOX_VISION_CUES", "1")


def test_off_by_default_and_sends_nothing(monkeypatch):
    CALLS.clear()
    monkeypatch.setattr(sandbox, "chat_vision", fake_vision)
    monkeypatch.delenv("SANDBOX_VISION_CUES", raising=False)
    meta = {}
    assert sandbox._visual_notes("C", EV, meta) == "" and CALLS == [] and "vision_cues" not in meta


def test_at_most_four_photos_are_read_and_only_images(vision):
    meta = {}
    sandbox._visual_notes("C", EV, meta)
    assert len(CALLS) == sandbox.MAX_VISION_PHOTOS == 4 and not any("a.txt" in c for c in CALLS)
    assert meta["vision_cues"]["images_sent"] == 4


def test_a_failed_or_unreadable_photo_is_skipped_and_counted_not_fatal(vision):
    meta = {}
    notes = sandbox._visual_notes("C", EV, meta)
    vc = meta["vision_cues"]
    assert vc["images_sent"] == 4 and vc["photos_read"] == 2          # photo3 raised, photo2 was not JSON
    assert {p["evidence_id"] for p in vc["photos"]} == {"EV-0", "EV-1"} and "EV-3" not in notes and "EV-2" not in notes


def test_the_readings_are_cleaned_capped_and_never_carry_numbers_the_model_invented(vision):
    meta = {}
    sandbox._visual_notes("C", EV, meta)
    p = meta["vision_cues"]["photos"][0]
    assert len(p["items"]) <= 8 and all(i["what"] for i in p["items"])               # empty names dropped, at most 8 kept
    odd = next(i for i in p["items"] if i["what"] == "padlock")
    assert odd["kind"] == "other" and odd["state"] == "unknown" and len(odd["note"]) <= 100
    assert p["scale_cues"] == ["a standard padlock"] and p["cannot_tell"] == ["the interior"]
    assert "Do not give measurements" in sandbox.VISION_SYSTEM_PROMPT and "Do not identify people" in sandbox.VISION_SYSTEM_PROMPT


def test_the_layout_model_is_told_to_treat_them_as_inferred_and_to_cite_the_photo(vision):
    notes = sandbox._visual_notes("C", EV, {})
    assert notes.startswith("<visual_layout_notes>") and notes.rstrip().endswith("</visual_layout_notes>")
    assert "inferred" in notes and "cite the photo id (EV-...)" in notes and "Never take a size from them" in notes
    assert "[EV-0] photo0.jpg" in notes and "roller shutter (forced: bottom lock prised)" in notes and "Cannot tell: the interior" in notes


def test_when_every_photo_fails_nothing_is_added_and_generation_goes_on(monkeypatch):
    monkeypatch.setenv("SANDBOX_VISION_CUES", "1")
    monkeypatch.setattr(sandbox, "chat_vision", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr("storage.get_object_path", lambda case, eid, fn: Path("fake") / fn)
    meta = {}
    assert sandbox._visual_notes("C", EV, meta) == "" and meta["vision_cues"]["photos_read"] == 0
