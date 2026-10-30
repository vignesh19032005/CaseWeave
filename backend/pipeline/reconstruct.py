"""
Stage 7 — Object Reconstruction. Two paths, honestly distinguished:

1. SAM 3D Objects (self-hosted) — real reconstruction, actual depth/shape
   inferred from the photo. No Meta-hosted equivalent exists (checked
   against Meta's full models table). Stays the self-hosted path if you
   want true reconstruction fidelity; weights mid-download, paused.

2. Procedural approximation (THIS module, default/active now) — same
   method as the buildgen reference project analyzed earlier: a vision
   model describes the object's shape/proportions/color from the photo,
   then writes primitive Three.js geometry (boxes/cylinders) approximating
   it. Not a true mesh, not real reconstruction — an honest approximation,
   same disclosure as Stage 6's room-shell codegen. Zero downloads, uses
   the already-confirmed-working Meta vision API.
"""
import base64
import re
from pathlib import Path

from llm_client import chat_vision, LLMUnavailableError

SYSTEM_PROMPT = """You are an object-geometry describer for CaseWeave, an
investigation support tool. Look at the photographed object and write
React Three Fiber JSX approximating its shape using only primitive
geometry: <boxGeometry>, <cylinderGeometry>, <sphereGeometry>, with
<meshStandardMaterial> colors matched to what you see. Compose multiple
primitives if the object has distinct parts (e.g. a chair = seat box +
back box + four thin cylinder legs). Scale proportions realistically
relative to a 1-meter-wide reference. Output ONLY the JSX (what would go
inside a <group>...</group>), no explanation, no markdown fences, under
30 lines. This is an approximation for scene visualization, not a
precision reconstruction — state nothing beyond the geometry."""

OUTPUT_DIR = Path(__file__).parent.parent / "reconstructed_objects"


def reconstruct_object_procedural(image_path, object_label: str = "") -> dict:
    """
    Vision-describes the object in image_path, generates approximate
    primitive-geometry JSX for it. Returns {"jsx": str, "provider": str,
    "source_image": str, "method": "procedural_approximation"}.
    """
    prompt = f"Object in photo: {object_label or 'the main object'}. Describe its geometry as JSX primitives."
    try:
        provider, jsx = chat_vision(SYSTEM_PROMPT, prompt, image_path, max_tokens=1024)
    except LLMUnavailableError as e:
        raise LLMUnavailableError(f"Procedural object reconstruction failed: {e}") from e

    jsx = jsx.strip()
    if jsx.startswith("```"):
        jsx = re.sub(r"^```[a-zA-Z]*\n?", "", jsx)
        jsx = re.sub(r"```$", "", jsx).strip()
    # The model sometimes prepends boilerplate import/export lines despite
    # the prompt asking for bare JSX — those break the frontend's runtime
    # Babel compile (new Function can't parse ESM import statements), so
    # strip any such lines defensively rather than trust the prompt alone.
    jsx = "\n".join(
        line for line in jsx.splitlines()
        if not re.match(r"^\s*(import|export)\b", line)
    ).strip()

    return {
        "jsx": jsx,
        "provider": provider,
        "source_image": str(image_path),
        "method": "procedural_approximation",
    }


# --- Path 2: SAM 3D Objects (self-hosted, real reconstruction) ---
MODEL_DIR = Path(__file__).parent.parent / "models" / "sam-3d-objects"


def _sam3d_available() -> bool:
    return (MODEL_DIR / "checkpoints" / "pipeline.yaml").exists()


def reconstruct_object_sam3d(image_path, mask_path=None) -> dict:
    """Real reconstruction via self-hosted SAM 3D Objects. Requires the
    weights to finish downloading — see scripts/download_models.py."""
    if not _sam3d_available():
        raise RuntimeError(
            f"SAM 3D Objects weights not found at {MODEL_DIR}. Resume the paused "
            f"download: python scripts/download_models.py sam3d"
        )
    raise NotImplementedError(
        "Wire against sam-3d-objects' own inference library once weights finish downloading."
    )


def reconstruct_object(image_path, object_label: str = "", prefer: str = "auto") -> dict:
    """
    Main entry point. prefer: "procedural" (default/active), "sam3d"
    (real reconstruction, requires weights), or "auto" (tries sam3d if
    weights present, else falls back to procedural).
    """
    if prefer == "sam3d" or (prefer == "auto" and _sam3d_available()):
        return reconstruct_object_sam3d(image_path)
    return reconstruct_object_procedural(image_path, object_label)
