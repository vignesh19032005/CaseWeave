"""
Stage 14 — Input validation & upload sandboxing. Real magic-byte
verification (not just trusting the filename extension), size limits, content
checks for the text types, and a subprocess-isolation helper for running
untrusted-file parsing (PyMuPDF/OCR) out of the main API process so a malicious
file can crash a worker, not the server.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50MB — generous for evidence photos/docs, blocks abuse
TEXT_CHECK_BYTES = 2 * 1024 * 1024  # text/JSON uploads this small are fully validated; larger ones are checked on their first part

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
        b"\x00\x00\x00\x18ftyp",  # M4A
        b"\x00\x00\x00\x20ftyp",
    ],
}

# What the API accepts. "unknown" is deliberately not here: a file the pipeline cannot read is refused up front
# instead of being stored and silently skipped later.
EXTENSION_TYPES = {
    ".json": "structured_log",
    ".txt": "text_document", ".md": "text_document",
    ".pdf": "pdf",
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".mp4": "video", ".mov": "video", ".avi": "video",
    ".wav": "audio", ".mp3": "audio", ".m4a": "audio",
}


class UploadValidationError(ValueError):
    pass


def classify_evidence_type(filename: str) -> str:
    """The evidence type for a filename, or raises UploadValidationError for a file type we cannot process."""
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSION_TYPES:
        allowed = ", ".join(sorted(EXTENSION_TYPES))
        raise UploadValidationError(f"'{filename}': file type '{suffix or 'none'}' is not supported. Supported: {allowed}")
    return EXTENSION_TYPES[suffix]


def validate_magic_bytes(header: bytes, evidence_type: str, filename: str):
    """Raises UploadValidationError if the file's actual content doesn't
    match what its extension claims."""
    if evidence_type not in MAGIC_SIGNATURES:
        return
    # MP4/MOV/M4A: the first box's size (bytes 0-3) varies by encoder; the real
    # signature is "ftyp" at offset 4.
    if evidence_type in ("video", "audio") and header[4:8] == b"ftyp":
        return
    signatures = MAGIC_SIGNATURES[evidence_type]
    if not any(header.startswith(sig) for sig in signatures):
        raise UploadValidationError(
            f"'{filename}' claims to be {evidence_type} but its content doesn't match "
            f"known {evidence_type} file signatures — rejected (spoofed extension?)"
        )


def validate_text_content(path: Path, evidence_type: str, filename: str):
    """Text and JSON evidence: must be real text (no NUL bytes, valid UTF-8) and JSON must parse."""
    if evidence_type not in ("text_document", "structured_log"):
        return
    with open(path, "rb") as f:
        data = f.read(TEXT_CHECK_BYTES + 1)
    complete = len(data) <= TEXT_CHECK_BYTES
    data = data[:TEXT_CHECK_BYTES]
    if b"\x00" in data:
        raise UploadValidationError(f"'{filename}' contains binary data and is not a text file")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        if complete or e.start < len(data) - 4:  # an incomplete character at the cut is fine, anything else is not
            raise UploadValidationError(f"'{filename}' is not valid UTF-8 text")
        text = data[: e.start].decode("utf-8-sig")
    if evidence_type == "structured_log" and complete:
        try:
            json.loads(text)
        except ValueError:
            raise UploadValidationError(f"'{filename}' is not valid JSON")


def validate_size(size_bytes: int, filename: str):
    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
        raise UploadValidationError(
            f"'{filename}' is {size_bytes} bytes, exceeds the {MAX_UPLOAD_SIZE_BYTES} byte limit"
        )
    if size_bytes == 0:
        raise UploadValidationError(f"'{filename}' is empty")


def _child_env() -> dict:
    """The environment an untrusted-file parser gets: the bare minimum to run, never the API keys, database
    password or signing secrets that the parent process holds."""
    keep = ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
            "TESSERACT_CMD", "TESSDATA_PREFIX", "TESSERACT_LANGS", "FFMPEG_CMD", "LANG", "LC_ALL", "PROGRAMFILES", "PROGRAMDATA", "OMP_NUM_THREADS")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONUTF8"] = "1"
    return env


def run_extraction_sandboxed(worker_module: str, *args, timeout_seconds: int = 60) -> str:
    """Runs a pipeline/extract.py-style function in an isolated subprocess
    instead of in-process, so a malicious/malformed file that crashes
    PyMuPDF/OCR takes down a throwaway worker process, not the API
    server. The child gets a stripped environment (no secrets). worker_module is a
    `python -m`-style module path that reads args and prints JSON to stdout."""
    result = subprocess.run(
        [sys.executable, "-m", worker_module, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
        cwd=str(Path(__file__).parent),  # so `-m pipeline.extract_worker` resolves
        env=_child_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"sandboxed extraction failed (exit {result.returncode}): {result.stderr[:500]}")
    return result.stdout
