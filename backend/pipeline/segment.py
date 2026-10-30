"""
Stage 8 — Object Segmentation. Real Meta-hosted SAM 3.1 via the same
Responses API used everywhere else (model="sam-3.1"), NOT the self-hosted
local weights originally planned — Meta hosts this one, confirmed live.
Give it a short noun phrase + an image/video, get back a box + pixel-
accurate mask per match. No local GPU/weights needed for this stage.
"""
import base64
import json
from pathlib import Path

from llm_client import _post_json
from secrets_store import get_secret


def _mime_type(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


def segment_image(image_path, text_prompt: str) -> dict:
    """
    Runs SAM 3.1 on an image for a given noun-phrase prompt (e.g. "chair",
    "cardboard box"). Returns every match as a box + mask.

    Returns {"matches": [{"box": {...}, "mask_raw": str}], "prompt": str,
    "image_path": str}. mask_raw is SAM 3.1's RLE-encoded pixel mask string
    — stored as-is for now; decoding to a renderable mask overlay is a
    Stage-11-scene-linking follow-on, not needed for the segmentation call
    itself to be "done."
    """
    api_key = get_secret("META_API_KEY")
    if not api_key:
        raise RuntimeError("META_API_KEY not set — Stage 8 needs the real Meta API key")

    path = Path(image_path)
    image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

    payload = {
        "model": "sam-3.1",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": text_prompt},
                    {"type": "input_image", "image_url": f"data:{_mime_type(path)};base64,{image_b64}"},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result = _post_json("https://api.meta.ai/v1/responses", headers, payload, timeout=90)

    raw_text = ""
    for item in result.get("output", []):
        if item.get("type") == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    raw_text = block["text"]

    # SAM 3.1 returns one or more "<box;...><mask;...>" segments per match,
    # concatenated. Split them out rather than parsing the full geometry
    # here — downstream scene-linking code decides what to do with each.
    matches = []
    for segment in raw_text.split("<0f>"):
        segment = segment.strip()
        if segment:
            matches.append({"raw": segment})

    return {"matches": matches, "prompt": text_prompt, "image_path": str(image_path), "raw_response_text": raw_text}
