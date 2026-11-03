"""One place that decides which font the PDFs use.

ReportLab's built-in Helvetica has no Tamil, Devanagari or other Indic glyphs, so a witness statement in Tamil
printed as empty boxes. This module registers a Unicode TrueType font that covers Latin and Indic scripts when the
machine has one (CW_PDF_FONT to choose explicitly; otherwise Nirmala UI / Latha on Windows, Noto or DejaVu on
Linux). If none is found, text falls back to Helvetica with characters it cannot draw replaced by "?" (never boxes),
and `UNICODE` is False so callers and tests can tell.
"""
from __future__ import annotations

import os
from typing import Any

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
UNICODE = False

_CANDIDATES = [
    (os.environ.get("CW_PDF_FONT") or "", 0),
    (r"C:\Windows\Fonts\Nirmala.ttc", 0),
    (r"C:\Windows\Fonts\latha.ttf", 0),
    ("/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf", 0),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    (r"C:\Windows\Fonts\arial.ttf", 0),
    ("/Library/Fonts/Arial Unicode.ttf", 0),
]


def _register() -> None:
    global FONT, FONT_BOLD, UNICODE
    for path, index in _CANDIDATES:
        if not path or not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("CWUnicode", path, subfontIndex=index))
            bold = path
            for cand in (path.replace(".ttf", "b.ttf"), path.replace("Regular", "Bold")):
                if cand != path and os.path.exists(cand):
                    bold = cand
                    break
            pdfmetrics.registerFont(TTFont("CWUnicode-Bold", bold, subfontIndex=index))
            registerFontFamily("CWUnicode", normal="CWUnicode", bold="CWUnicode-Bold", italic="CWUnicode", boldItalic="CWUnicode-Bold")
            FONT, FONT_BOLD, UNICODE = "CWUnicode", "CWUnicode-Bold", True
            return
        except Exception:  # noqa: BLE001 - try the next candidate
            continue


_register()


def fit(value: Any) -> str:
    """Text safe to draw in the chosen font."""
    s = "" if value is None else str(value)
    return s if UNICODE else s.encode("latin-1", "replace").decode("latin-1")
