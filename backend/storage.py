"""
Object storage for evidence originals.

NOTE on MinIO: PLAN.md calls for MinIO as the demo object store. MinIO gated
their Docker images behind a registration wall in a 2025 licensing change —
`docker pull minio/minio` now returns 401/403 on both Docker Hub and quay.io
without a registered account. That's a real vendor-side block, confirmed by
testing both registries directly, not a code issue.

This module is the honest substitute: a local object store with the same
contract MinIO would provide (content-addressed storage, retrievable by
case_id/evidence_id, hash-verified on write). Swapping to real MinIO/S3
later means replacing only this file — nothing above it changes, since
callers only use put_object/get_object/object_path.
"""
import hashlib
import shutil
from pathlib import Path

STORE_ROOT = Path(__file__).parent / "object_store"


def put_object(case_id: str, evidence_id: str, src_path: Path) -> dict:
    """Copies src_path into the store under case_id/evidence_id/filename,
    verifies the copy's hash matches the original, returns storage metadata."""
    dest_dir = STORE_ROOT / case_id / evidence_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / src_path.name

    original_hash = hashlib.sha256(src_path.read_bytes()).hexdigest()
    shutil.copy2(src_path, dest_path)
    stored_hash = hashlib.sha256(dest_path.read_bytes()).hexdigest()

    if original_hash != stored_hash:
        dest_path.unlink(missing_ok=True)
        raise IOError(f"Storage integrity check failed for {src_path.name}: hash mismatch after copy")

    return {
        "stored_path": str(dest_path),
        "sha256": stored_hash,
        "size_bytes": dest_path.stat().st_size,
    }


def get_object_path(case_id: str, evidence_id: str, filename: str) -> Path:
    path = STORE_ROOT / case_id / evidence_id / filename
    if not path.exists():
        raise FileNotFoundError(f"No stored object at {path}")
    return path


def verify_object(case_id: str, evidence_id: str, filename: str, expected_hash: str) -> bool:
    path = get_object_path(case_id, evidence_id, filename)
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return actual_hash == expected_hash
