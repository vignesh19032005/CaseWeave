"""Defensive reading of model output.

A model is asked for JSON in a given shape and does not always comply: a list may arrive wrapped in an object,
a string where a list was asked for, null for text, a label outside the allowed set. Nothing downstream should
crash or store garbage because of that, so every stage reads model output through these helpers.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional


def records(value: Any) -> List[dict]:
    """The list of objects in a model reply: a bare list, or the first list found inside an object."""
    if isinstance(value, dict):
        lists = [v for v in value.values() if isinstance(v, list)]
        value = lists[0] if lists else [value]
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


def text(value: Any, limit: int = 2000) -> Optional[str]:
    """Trimmed string, or None for null/empty/non-text."""
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    s = " ".join(str(value).split())
    return s[:limit] or None


def string_list(value: Any, limit: int = 20, item_limit: int = 300) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        t = text(v, item_limit)
        if t:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def choice(value: Any, allowed: Iterable[str], default: str) -> str:
    s = str(value or "").strip().lower().replace(" ", "_")
    return s if s in set(allowed) else default
