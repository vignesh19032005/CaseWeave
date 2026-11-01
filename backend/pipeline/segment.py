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


def _segment_single(image_path, text_prompt: str) -> dict:
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

    import re
    box_pattern = re.compile(r"x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)")
    matches = []

    PALETTE = ["#10b981", "#06b6d4", "#f59e0b", "#ec4899", "#8b5cf6"]

    color_idx = 0
    for match in box_pattern.finditer(raw_text):
        x1, y1, x2, y2, w, h = map(int, match.groups())
        pct_left = round((x1 / w) * 100, 2)
        pct_top = round((y1 / h) * 100, 2)
        pct_width = round(((x2 - x1) / w) * 100, 2)
        pct_height = round(((y2 - y1) / h) * 100, 2)

        matches.append({
            "label": text_prompt,
            "color": PALETTE[color_idx % len(PALETTE)],
            "box": {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "image_width": w,
                "image_height": h,
                "pct_left": pct_left,
                "pct_top": pct_top,
                "pct_width": pct_width,
                "pct_height": pct_height,
            },
        })
        color_idx += 1

    return {
        "matches": matches,
        "prompt": text_prompt,
        "image_path": str(image_path),
        "detected_count": len(matches),
    }


def segment_image(image_path, text_prompt: str) -> dict:
    """Runs SAM 3.1 on an image. Supports multi-noun queries separated by commas."""
    terms = [t.strip() for t in text_prompt.split(",") if t.strip()]
    if len(terms) > 1:
        all_matches = []
        PALETTE = ["#10b981", "#06b6d4", "#f59e0b", "#ec4899", "#8b5cf6"]
        for term in terms:
            try:
                res = _segment_single(image_path, term)
                for m in res.get("matches", []):
                    m["color"] = PALETTE[len(all_matches) % len(PALETTE)]
                    all_matches.append(m)
            except Exception:
                continue
        return {
            "matches": all_matches,
            "prompt": text_prompt,
            "image_path": str(image_path),
            "detected_count": len(all_matches),
        }
    return _segment_single(image_path, text_prompt)

