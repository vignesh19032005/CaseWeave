"""
Downloads SAM 3 and SAM 3D Objects weights locally, once HF gated access is
granted for each. Run: python scripts/download_models.py [sam3] [sam3d]
(no args = try both; each is skipped individually if still gated/pending).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from huggingface_hub import snapshot_download
from huggingface_hub.errors import GatedRepoError

BACKEND_DIR = Path(__file__).parent.parent


def _load_hf_token() -> str:
    env_path = BACKEND_DIR / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("HUGGINGFACE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("HUGGINGFACE_API_KEY not set in backend/.env")


def download(repo_id: str, local_dir: Path, ignore_patterns: list[str], label: str):
    token = _load_hf_token()
    print(f"[{label}] downloading {repo_id} -> {local_dir} ...")
    try:
        path = snapshot_download(
            repo_id=repo_id, local_dir=str(local_dir), token=token, ignore_patterns=ignore_patterns
        )
        print(f"[{label}] done: {path}")
        return True
    except GatedRepoError as e:
        print(f"[{label}] still blocked: {e}")
        print(f"[{label}] accept the license at https://huggingface.co/{repo_id} and re-run this script.")
        return False


def main():
    targets = sys.argv[1:] or ["sam3", "sam3d"]
    if "sam3" in targets:
        download("facebook/sam3", BACKEND_DIR / "models" / "sam3", ["sam3.pt"], "SAM 3")
    if "sam3d" in targets:
        download("facebook/sam-3d-objects", BACKEND_DIR / "models" / "sam-3d-objects", ["*.pt"], "SAM 3D Objects")


if __name__ == "__main__":
    main()
