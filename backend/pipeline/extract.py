"""
Stage 1 — Media Extraction Pipeline. Real implementations:
- PDF: PyMuPDF text extraction, falls back to OCR per-page if no extractable text (scanned PDF)
- Image: Tesseract OCR via pytesseract (for text-bearing images; photos without text return empty)
- Video: ffmpeg frame extraction at a fixed interval, timestamps preserved in filename
- Audio: Groq's hosted Whisper transcription endpoint (multipart upload), real API call

Plain .txt/.json evidence (used by case CW-001 today) bypasses this module —
ingest.py reads them directly, since there's nothing to "extract" from text
that's already text. This module activates the moment a PDF/image/video/audio
file is added to a case.
"""
import functools
import json
import os
import shutil
import subprocess
import urllib.request
import uuid
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from llm_client import LLMUnavailableError

# Windows Tesseract install location found on this machine — override via
# TESSERACT_CMD env var if deployed elsewhere.
_TESSERACT_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_TESSERACT_DEFAULT):
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_DEFAULT

# ffmpeg: FFMPEG_CMD if set, otherwise whatever is on PATH. (There is deliberately no machine-specific default.)
FFMPEG_CMD = os.environ.get("FFMPEG_CMD") or shutil.which("ffmpeg") or "ffmpeg"

MAX_PDF_PAGES = 300          # pages read from one PDF
MAX_OCR_PAGES = 30           # scanned pages OCR'd from one PDF (OCR is slow; the rest are listed as skipped)
MAX_EXTRACT_FRAMES = 24      # frames written to disk for one video before sampling down for the vision model
MAX_AUDIO_SECONDS = 780      # the hosted speech model rejects uploads over 25 MB; 13 minutes of 16 kHz mono WAV fits
FFMPEG_TIMEOUT_S = 300


@functools.lru_cache(maxsize=1)
def _ocr_languages() -> str:
    """English always; Tamil and Hindi too when their Tesseract language packs are installed (TESSERACT_LANGS overrides)."""
    explicit = os.environ.get("TESSERACT_LANGS", "").strip()
    if explicit:
        return explicit
    try:
        have = set(pytesseract.get_languages(config=""))
    except Exception:  # noqa: BLE001 - Tesseract missing or unreadable: the OCR call itself will report it
        return "eng"
    return "+".join(["eng"] + [lang for lang in ("tam", "hin") if lang in have])


def extract_pdf(path: Path) -> list[dict]:
    """Returns one record per page: {page_number, text, method}. OCR fallback per page."""
    import io

    records = []
    ocr_done = 0
    doc = fitz.open(path)
    try:
        for page_num, page in enumerate(doc, start=1):
            if page_num > MAX_PDF_PAGES:
                records.append({"page_number": page_num, "text": f"(pages beyond {MAX_PDF_PAGES} were not read)", "method": "page_limit"})
                break
            text = page.get_text().strip()
            method = "text_layer"
            if not text:
                if ocr_done >= MAX_OCR_PAGES:
                    records.append({"page_number": page_num, "text": "", "method": "ocr_skipped_limit"})
                    continue
                # scanned page with no extractable text layer — render to image and OCR it
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang=_ocr_languages()).strip()
                method = "ocr_fallback"
                ocr_done += 1
            records.append({"page_number": page_num, "text": text, "method": method})
    finally:
        doc.close()
    return records


def extract_image_ocr(path: Path) -> dict:
    """OCR an image file. Returns {} text if the image has no legible text (expected for most photos)."""
    with Image.open(path) as img:
        text = pytesseract.image_to_string(img, lang=_ocr_languages()).strip()
    return {"text": text, "method": "ocr"}


def extract_video_frames(path: Path, out_dir: Path, interval_seconds: float = 2.0) -> list[dict]:
    """
    Extracts frames at a fixed interval via ffmpeg, preserving elapsed-time
    offsets (NOT wall-clock timestamps — those come from the camera overlay,
    read separately by vision analysis in Stage 2, since ffmpeg has no way to
    know what a CCTV camera's on-screen clock said).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%04d.png"
    cmd = [
        FFMPEG_CMD, "-y", "-nostdin", "-i", str(path),
        "-vf", f"fps=1/{interval_seconds}", "-frames:v", str(MAX_EXTRACT_FRAMES),
        str(pattern),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg frame extraction timed out after {FFMPEG_TIMEOUT_S}s")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed: {result.stderr[:500]}")

    frames = sorted(out_dir.glob("frame_*.png"))
    records = []
    for idx, frame_path in enumerate(frames):
        records.append(
            {
                "frame_index": idx,
                "elapsed_seconds": idx * interval_seconds,
                "path": str(frame_path),
            }
        )
    return records


def extract_audio_track(video_path: Path, out_path: Path) -> Path:
    """Pulls the audio track out of a video file as a standalone .wav, via ffmpeg."""
    cmd = [FFMPEG_CMD, "-y", "-nostdin", "-i", str(video_path), "-vn", "-t", str(MAX_AUDIO_SECONDS), "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(out_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg audio extraction timed out after {FFMPEG_TIMEOUT_S}s")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr[:500]}")
    return out_path


MIN_OCR_CHARS = 20  # below this, an image's OCR output is noise, not a document
MAX_VIDEO_FRAMES = 4  # bound vision-call cost per video

VIDEO_FRAME_PROMPT = """You are describing one frame from evidence video for
CaseWeave, an investigation support tool. State only what is visibly present:
people (clothing, position, action), doors/objects and their state, any
on-screen timestamp text exactly as shown. Do not guess identities or
intent. 1-3 sentences."""

PHOTO_DESCRIPTION_PROMPT = """You are describing an evidence photograph for
CaseWeave, an investigation support tool. State only what is visibly
present: the room/location type, every distinct object and its state or
position (e.g. "a chair lying on its side", "a cardboard box with its flaps
torn open and contents missing", "papers scattered across the floor"), any
visible damage, and any visible text (signage, labels, timestamps) exactly
as shown. Do not guess what happened or who was involved — describe only
what the image shows. 2-4 sentences."""


def _fmt_offset(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def evidence_to_text(path: Path, evidence_type: str, work_dir: Path) -> tuple[str | None, str]:
    """
    Turns any stored evidence file into text the observation engine can read.
    Returns (text, method). text is None when the file has nothing extractable
    (e.g. a photo with no legible text) — the caller skips it, it isn't an error.

    PDF and image parsing run in a sandboxed subprocess (Stage 14) so a
    malformed file can't crash the worker process.
    """
    from upload_validation import run_extraction_sandboxed

    if evidence_type in ("text_document", "structured_log"):
        return path.read_text(encoding="utf-8", errors="replace"), "plain_text"

    if evidence_type == "pdf":
        pages = json.loads(run_extraction_sandboxed("pipeline.extract_worker", "pdf", str(path), timeout_seconds=600))
        text = "\n\n".join(f"[page {p['page_number']} · {p['method']}]\n{p['text']}" for p in pages if p["text"])
        skipped = [p["page_number"] for p in pages if p["method"] in ("ocr_skipped_limit", "page_limit")]
        if skipped:
            text += f"\n\n(note: {len(skipped)} page(s) were not read because of size limits, starting at page {skipped[0]})"
        return (text or None), "pdf_" + ",".join(sorted({p["method"] for p in pages if p["method"] not in ("page_limit",)}))

    if evidence_type == "image":
        # Two passes, combined: OCR for any legible on-screen text (signage,
        # timestamps), and a vision description for the actual scene content
        # — most evidence photos (a toppled chair, a torn-open box) have no
        # text at all, so OCR alone silently dropped them from analysis
        # entirely. Every photo now contributes real content.
        from llm_client import chat_vision

        ocr_result = json.loads(run_extraction_sandboxed("pipeline.extract_worker", "image", str(path)))
        ocr_text = ocr_result.get("text", "").strip()

        _, description = chat_vision(PHOTO_DESCRIPTION_PROMPT, "Describe this evidence photograph.", path, max_tokens=400)
        description = description.strip()

        parts = [f"[photo description] {description}"] if description else []
        if len(ocr_text) >= MIN_OCR_CHARS:
            parts.append(f"[on-screen text, OCR] {ocr_text}")
        text = "\n".join(parts)
        method = "image_vision" + ("+ocr" if len(ocr_text) >= MIN_OCR_CHARS else "")
        return (text or None), method

    if evidence_type == "audio":
        t = transcribe_audio(path)
        return _transcript_text(t, "Audio transcript"), "audio_whisper"

    if evidence_type == "video":
        from llm_client import chat_vision

        parts = []
        audio_path = work_dir / f"{path.stem}_audio.wav"
        try:
            extract_audio_track(path, audio_path)
            parts.append(_transcript_text(transcribe_audio(audio_path), "Video audio transcript"))
        except Exception as e:  # silent videos have no audio track — not fatal
            parts.append(f"(no usable audio track: {str(e)[:120]})")

        frames = extract_video_frames(path, work_dir / f"{path.stem}_frames", interval_seconds=5.0)
        if len(frames) > MAX_VIDEO_FRAMES:
            step = len(frames) / MAX_VIDEO_FRAMES
            frames = [frames[int(i * step)] for i in range(MAX_VIDEO_FRAMES)]
        for fr in frames:
            _, desc = chat_vision(VIDEO_FRAME_PROMPT, "Describe this frame.", fr["path"], max_tokens=400)
            parts.append(f"[video frame at +{_fmt_offset(fr['elapsed_seconds'])} elapsed] {desc.strip()}")
        text = "\n".join(p for p in parts if p)
        return (text or None), "video_audio+frames"

    return None, "unsupported"


def _transcript_text(t: dict, label: str) -> str | None:
    if t.get("segments"):
        lines = [f"[+{_fmt_offset(s.get('start'))} elapsed] {s['text']}" for s in t["segments"] if s.get("text")]
        return f"{label} (offsets are elapsed time from start of recording, not wall-clock):\n" + "\n".join(lines)
    return f"{label}:\n{t['text']}" if t.get("text") else None


def transcribe_audio(path: Path) -> dict:
    """
    Real transcription via Groq's hosted Whisper endpoint (multipart upload).
    This is the MMS/Whisper secondary-tier fallback from PLAN.md's Model
    Fallback Matrix — there's no Meta-hosted ASR API to call as primary yet,
    so Groq-hosted Whisper is used directly as documented there.
    """
    from secrets_store import get_secret

    api_key = (os.environ.get("GROQ_API_KEY") or get_secret("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise LLMUnavailableError("GROQ_API_KEY not set — cannot transcribe audio")
    from llm_client import provider_mode
    if provider_mode() != "auto":
        raise LLMUnavailableError(f"audio transcription needs the hosted speech service, which is not allowed in {provider_mode()} mode")

    size = Path(path).stat().st_size
    if size > 24 * 1024 * 1024:
        raise LLMUnavailableError(f"audio file is {size // (1024 * 1024)} MB; the speech service accepts at most 25 MB. Split or compress it.")
    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        audio_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n'
        f"whisper-large-v3\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        f"verbose_json\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + audio_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0 (CaseWeave/1.0)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - network and HTTP errors become one clear message
        raise LLMUnavailableError(f"audio transcription failed: {type(e).__name__}") from e

    return {
        "text": result.get("text", ""),
        "segments": [
            {"start": s.get("start"), "end": s.get("end"), "text": s.get("text", "").strip()}
            for s in result.get("segments", [])
        ],
    }
