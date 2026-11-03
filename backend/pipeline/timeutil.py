"""Clock-time helpers shared by the timeline, the debate and the reports.

Evidence gives times of day ("02:23", "9:10 PM", "02:28:15") without a date. Two things go wrong if they are
treated as plain strings: "9:10 PM" sorts after "10:00", and an incident that straddles midnight (23:50 then
00:10) sorts backwards. This module normalises what a model returns to 24-hour HH:MM[:SS], and orders a set of
times so that the longest quiet stretch of the day is where the sequence starts.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

_CLOCK = re.compile(r"(?<![\d.:])(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap])?\.?\s*(m)?\.?(?![\d:])", re.IGNORECASE)
_HOUR_ONLY = re.compile(r"(?<![\d:.])(\d{1,2})\s*([ap])\.?m\.?(?!\w)", re.IGNORECASE)
DAY = 86400


def parse_seconds(value) -> Optional[int]:
    """Seconds into the day for the first clock time found in `value`, or None."""
    text = str(value or "")
    m = _CLOCK.search(text)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        meridiem = (m.group(4) or "").lower() if m.group(5) else ""
    else:
        m2 = _HOUR_ONLY.search(text)
        if not m2:
            return None
        h, mi, s, meridiem = int(m2.group(1)), 0, 0, m2.group(2).lower()
    if meridiem:
        if not 1 <= h <= 12:
            return None
        h = (h % 12) + (12 if meridiem == "p" else 0)
    if h > 23 or mi > 59 or s > 59:
        return None
    return h * 3600 + mi * 60 + s


def normalize_clock(value, keep_seconds: bool = True) -> Optional[str]:
    """'9:10 PM' -> '21:10', '02:28:15' -> '02:28:15', anything that is not a time -> None."""
    sec = parse_seconds(value)
    if sec is None:
        return None
    h, rem = divmod(sec, 3600)
    mi, s = divmod(rem, 60)
    return f"{h:02d}:{mi:02d}:{s:02d}" if (s and keep_seconds) else f"{h:02d}:{mi:02d}"


def chronological_offsets(times: Iterable[Optional[str]]) -> dict:
    """Maps each distinct time string to a sortable offset. The sequence starts after the longest empty gap on the
    24-hour circle, so 23:50 comes before 00:10 when the evidence spans midnight, and an ordinary daytime or
    night-time incident keeps its natural order."""
    secs = sorted({parse_seconds(t) for t in times if parse_seconds(t) is not None})
    if len(secs) < 2:
        return {t: parse_seconds(t) for t in times if parse_seconds(t) is not None}
    gaps = [(secs[i + 1] - secs[i], i + 1) for i in range(len(secs) - 1)]
    gaps.append((secs[0] + DAY - secs[-1], 0))  # the gap across midnight
    _, start_idx = max(gaps)
    start = secs[start_idx]
    return {t: (parse_seconds(t) - start) % DAY for t in times if parse_seconds(t) is not None}


def sort_chronologically(items: List[dict], key: str = "time") -> List[dict]:
    """Stable chronological sort of dicts by their clock-time field; items with no usable time go last."""
    offsets = chronological_offsets([i.get(key) for i in items])
    return sorted(items, key=lambda i: (offsets.get(i.get(key)) is None, offsets.get(i.get(key)) or 0))
