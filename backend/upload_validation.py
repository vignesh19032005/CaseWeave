"""
Stage 14 — Input validation & upload sandboxing. Real magic-byte
verification (not just trusting the filename extension), size limits, and
a subprocess-isolation helper for running untrusted-file parsing (PyMuPDF/
OCR/ffmpeg) out of the main API process so a malicious file can crash a
worker, not the server.
"""
import subprocess
import sys
from pathlib import Path

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50MB — generous for evidence photos/docs, blocks abuse

# Real file-signature (magic byte) checks, not extension-based trust.
# Maps our evidence_type -> list of acceptable byte signatures at offset 0
# (JSON/text have no reliable magic bytes, checked separately below).
MAGIC_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "image": [
        b"\xff\xd8\xff",  # JPEG
        b"\x89PNG\r\n\x1a\n",  # PNG
    ],
    "video": [
        b"\x00\x00\x00\x18ftyp",  # MP4 (common variant)
        b"\x00\x00\x00\x1cftyp",
        b"\x00\x00\x00\x20ftyp",
        b"RIFF",  # AVI
    ],
    "audio": [
        b"RIFF",  # WAV
        b"ID3",  # MP3 with ID3 tag
        b"\xff\xfb",  # MP3 without ID3
        b"\xff\xf3",
        b"\xff\xf2",
    ],
}


class UploadValidationError(ValueError):
    pass


def validate_magic_bytes(header: bytes, evidence_type: str, filename: str):
    """Raises UploadValidationError if the file's actual content doesn't
    match what its extension claims. text_document/structured_log/unknown
    types have no reliable magic bytes and are allowed through here —
    they're low-risk (parsed as plain text, not by PyMuPDF/ffmpeg/OCR)."""
    if evidence_type not in MAGIC_SIGNATURES:
        return
    # MP4/MOV: the first box's size (bytes 0-3) varies by encoder; the real
    # signature is "ftyp" at offset 4.
    if evidence_type == "video" and header[4:8] == b"ftyp":
        return
    signatures = MAGIC_SIGNATURES[evidence_type]
    if not any(header.startswith(sig) for sig in signatures):
        raise UploadValidationError(
            f"'{filename}' claims to be {evidence_type} but its content doesn't match "
            f"known {evidence_type} file signatures — rejected (spoofed extension?)"
        )


def validate_size(size_bytes: int, filename: str):
    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
        raise UploadValidationError(
            f"'{filename}' is {size_bytes} bytes, exceeds the {MAX_UPLOAD_SIZE_BYTES} byte limit"
        )
    if size_bytes == 0:
        raise UploadValidationError(f"'{filename}' is empty")


def run_extraction_sandboxed(worker_module: str, *args, timeout_seconds: int = 60) -> str:
    """Runs a pipeline/extract.py-style function in an isolated subprocess
    instead of in-process, so a malicious/malformed file that crashes
    PyMuPDF/OCR/ffmpeg takes down a throwaway worker process, not the API
    server. worker_module is a `python -m`-style module path that reads
    args and prints JSON to stdout; caller parses that output."""
    import os

    result = subprocess.run(
        [sys.executable, "-m", worker_module, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
        cwd=str(Path(__file__).parent),  # so `-m pipeline.extract_worker` resolves
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"sandboxed extraction failed (exit {result.returncode}): {result.stderr[:500]}")
    return result.stdout
