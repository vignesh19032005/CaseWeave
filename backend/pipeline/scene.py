"""
Stage 6 — Procedural Scene Shell. Llama/Groq writes Three.js geometry code
from investigator-supplied measurements + evidence photo references
(buildgen-style, see PLAN.md §5) — not reconstruction, explicit LLM-assisted
procedural generation from human-supplied facts.
"""
import re

from llm_client import chat, LLMUnavailableError

SYSTEM_PROMPT = """You are a procedural scene generator for CaseWeave, an
investigation support tool. Given a room/building description and
measurements, write React Three Fiber JSX that depicts THIS SPECIFIC scene —
not a generic empty room.

HARD REQUIREMENT: every distinct object, fixture or evidence item named in
the description (door, shelving/racking, boxes, a fallen/toppled chair,
scattered papers, a counter, windows, etc.) must appear as its own visible
primitive at a plausible position, not be omitted or merged into the walls.
If the description names an object you don't have a perfect primitive for,
approximate it with boxes/cylinders rather than skipping it — an empty shell
with nothing described is a wrong answer.

Build with only <mesh>, <boxGeometry>, <cylinderGeometry>, <planeGeometry>,
<meshStandardMaterial> and plain hex colors. No external assets, no imports
beyond what's already in scope in a React Three Fiber Canvas. A toppled
chair should visibly differ from an upright one (rotated/tilted, e.g.
rotation={[0, 0, Math.PI/2.2]}). Scattered items should be several small
meshes at varied positions/rotations, not one placeholder box. Use distinct
colors per object type so they read clearly against the walls/floor.

Output ONLY the JSX for the scene contents (what goes inside
<Canvas>...</Canvas>), no explanation, no markdown fences. Up to 100 lines.
Use realistic proportions from the measurements."""


def generate_scene_jsx(description: str, measurements: dict) -> dict:
    """
    description: free text, e.g. "Warehouse side entrance, one door, two
      interior rooms, scattered evidence near entry".
    measurements: {"width_m": .., "length_m": .., "height_m": ..} — from the
      investigator, not inferred/guessed by the model.

    Returns {"jsx": str, "provider": str}.
    """
    prompt = (
        f"Room description: {description}\n"
        f"Measurements (meters): {measurements}\n\n"
        f"Generate the Three.js/React Three Fiber scene JSX for this room shell."
    )
    try:
        provider, jsx = chat(SYSTEM_PROMPT, prompt, max_tokens=3072)
    except LLMUnavailableError as e:
        raise LLMUnavailableError(f"Scene generation failed: {e}") from e

    jsx = jsx.strip()
    if jsx.startswith("```"):
        jsx = re.sub(r"^```[a-zA-Z]*\n?", "", jsx)
        jsx = re.sub(r"```$", "", jsx).strip()
    # Defensive: strip stray import/export lines the model occasionally
    # adds despite the prompt — they break the frontend's runtime Babel
    # compile (same fix as pipeline/reconstruct.py).
    jsx = "\n".join(
        line for line in jsx.splitlines()
        if not re.match(r"^\s*(import|export)\b", line)
    ).strip()

    return {"jsx": jsx, "provider": provider}
