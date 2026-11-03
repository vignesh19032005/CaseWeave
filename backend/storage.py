"""
Object storage for evidence originals.

NOTE on MinIO: PLAN.md calls for MinIO as the demo object store. MinIO gated
their Docker images behind a registration wall in a 2025 licensing change —
`docker pull minio/minio` now returns 401/403 on both Docker Hub and quay.io
without a registered account. That's a real vendor-side block, confirmed by
testing both registries directly, not a code issue.

This module is the honest substitute: a local object store with the same
contract MinIO would provide (retrievable by case_id/evidence_id, hash-verified
on write). Swapping to real MinIO/S3 later means replacing only this file —
nothing above it changes, since callers only use put_object/get_object_path/
verify_object.

Integrity: every original is hashed while it is copied in, the copy is hashed
again, and the file is made read-only. `verify_object` re-hashes the stored
file on demand; the API calls it before serving or processing an original, so
a file that was changed on disk after upload is reported instead of trusted.
"""
import hashlib
import os
import shutil
import stat
from pathlib import Path

STORE_ROOT = Path(os.environ.get("CASEWEAVE_OBJECT_STORE") or (Path(__file__).parent / "object_store"))
_CHUNK = 1024 * 1024


class IntegrityError(RuntimeError):
    """A stored original no longer matches the hash recorded when it was uploaded."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_part(value: str) -> str:
    """A single path component; anything that could climb out of the store is rejected."""
    if not value or value in (".", "..") or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe storage path component: {value!r}")
    return value


def put_object(case_id: str, evidence_id: str, src_path: Path) -> dict:
    """Copies src_path into the store under case_id/evidence_id/filename,
    verifies the copy's hash matches the original, makes it read-only, returns storage metadata."""
    dest_dir = STORE_ROOT / _safe_part(case_id) / _safe_part(evidence_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / _safe_part(src_path.name)

    original_hash = _sha256(src_path)
    shutil.copy2(src_path, dest_path)
    stored_hash = _sha256(dest_path)

    if original_hash != stored_hash:
        dest_path.unlink(missing_ok=True)
        raise IOError(f"Storage integrity check failed for {src_path.name}: hash mismatch after copy")

    try:
        os.chmod(dest_path, stat.S_IREAD)  # read-only: the original is never edited in place
    except OSError:
        pass

    return {
        "stored_path": str(dest_path),
        "sha256": stored_hash,
        "size_bytes": dest_path.stat().st_size,
    }


def get_object_path(case_id: str, evidence_id: str, filename: str) -> Path:
    path = STORE_ROOT / _safe_part(case_id) / _safe_part(evidence_id) / _safe_part(filename)
    if not path.is_file():
        raise FileNotFoundError(f"No stored object for {evidence_id}")
    return path


def verify_object(case_id: str, evidence_id: str, filename: str, expected_hash: str) -> bool:
    path = get_object_path(case_id, evidence_id, filename)
    return _sha256(path) == expected_hash


def require_intact(case_id: str, evidence_id: str, filename: str, expected_hash: str) -> Path:
    """The stored path, only if the file still matches its recorded hash. Raises IntegrityError otherwise."""
    path = get_object_path(case_id, evidence_id, filename)
    if _sha256(path) != expected_hash:
        raise IntegrityError(f"{filename} ({evidence_id}) no longer matches the hash recorded at upload")
    return path


def delete_case_objects(case_id: str) -> None:
    """Removes every stored file of a case (read-only files need their flag cleared on Windows first)."""
    root = STORE_ROOT / _safe_part(case_id)

    def _onerror(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    shutil.rmtree(root, onerror=_onerror)
