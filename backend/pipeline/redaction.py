"""
PII redaction for text sent to third-party language models.

Before any case text leaves the machine, people's names (taken from the
case's resolved person entities and their aliases) and structured identifiers
(phone numbers, emails, Aadhaar, PAN, vehicle plates, IMEI, long account-like
numbers) are replaced with stable placeholders such as PERSON_1 or PHONE_2.
The model's reply is then restored locally, so officers see real names and the
provider never receives them.

What this does NOT cover, and the interface says so: places and organisation
names (the scene needs them), names that were never resolved as person
entities, free-text addresses, and any identifying detail inside images that
were already sent for description during the analysis pipeline.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Tuple

_STOP = {
    "the", "and", "for", "mr", "mrs", "ms", "dr", "sri", "shri", "smt", "kumar", "singh", "unknown", "person", "male", "female", "staff",
    "owner", "guard", "witness", "suspect", "victim", "officer", "manager", "customer",
}

_PATTERNS: List[Tuple[str, str]] = [
    ("EMAIL", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    ("AADHAAR", r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
    ("PAN", r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    ("PLATE", r"\b[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{3,4}\b"),
    ("PHONE", r"(?<!\d)(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)"),
    ("IMEI", r"(?<!\d)\d{15}(?!\d)"),
    ("NUMBER", r"(?<!\d)\d{9,18}(?!\d)"),
]
_PLACEHOLDER = re.compile(r"\b(PERSON|EMAIL|AADHAAR|PAN|PLATE|PHONE|IMEI|NUMBER)_(\d+)\b")


def redaction_enabled() -> bool:
    return os.environ.get("SANDBOX_REDACT_PII", "1").strip().lower() not in ("0", "false", "no", "off")


class Redactor:
    def __init__(self, person_names: Iterable[Iterable[str]] = ()):
        self._forward: Dict[str, str] = {}
        self._back: Dict[str, str] = {}
        self._counters: Dict[str, int] = {}
        self._name_res: List[Tuple[re.Pattern, str]] = []
        self.counts: Dict[str, int] = {}
        for group in person_names:
            names = sorted({n.strip() for n in group if n and len(n.strip()) >= 3}, key=len, reverse=True)
            if not names:
                continue
            ph = self._placeholder("PERSON", names[0])
            for n in names:
                self._add_name(n, ph)
                for part in re.split(r"[\s.,]+", n):
                    if len(part) >= 4 and part.lower() not in _STOP and part.isalpha():
                        self._add_name(part, ph)
        self._name_res.sort(key=lambda t: -len(t[0].pattern))

    def _placeholder(self, kind: str, original: str) -> str:
        key = f"{kind}:{original.lower()}"
        if key in self._forward:
            return self._forward[key]
        self._counters[kind] = self._counters.get(kind, 0) + 1
        ph = f"{kind}_{self._counters[kind]}"
        self._forward[key] = ph
        self._back[ph] = original
        return ph

    def _add_name(self, name: str, ph: str) -> None:
        self._name_res.append((re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE), ph))

    def redact(self, text: str) -> str:
        if not text:
            return text
        out = text
        for pat, ph in self._name_res:
            out, n = pat.subn(ph, out)
            if n:
                self.counts["PERSON"] = self.counts.get("PERSON", 0) + n
        for kind, rx in _PATTERNS:
            def sub(m, kind=kind):
                self.counts[kind] = self.counts.get(kind, 0) + 1
                return self._placeholder(kind, m.group(0))
            out = re.sub(rx, sub, out)
        return out

    def restore(self, text: str) -> str:
        if not text or "_" not in text:
            return text
        return _PLACEHOLDER.sub(lambda m: self._back.get(m.group(0), m.group(0)), text)

    def restore_json(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.restore(value)
        if isinstance(value, list):
            return [self.restore_json(v) for v in value]
        if isinstance(value, dict):
            return {k: self.restore_json(v) for k, v in value.items()}
        return value

    def summary(self) -> Dict[str, Any]:
        return {"enabled": True, "replacements": dict(self.counts), "distinct_placeholders": len(self._back),
                "not_covered": ["place and organisation names", "unresolved names in free text", "free-text addresses", "details inside images already analysed"]}


class NoRedaction(Redactor):
    def redact(self, text: str) -> str:
        return text

    def restore(self, text: str) -> str:
        return text

    def restore_json(self, value: Any) -> Any:
        return value

    def summary(self) -> Dict[str, Any]:
        return {"enabled": False, "replacements": {}, "distinct_placeholders": 0, "not_covered": ["everything: redaction is switched off"]}


def build_redactor(entities: List[dict], enabled: bool = True) -> Redactor:
    if not enabled:
        return NoRedaction()
    groups = []
    for e in entities:
        if str(e.get("entity_type") or "").lower() != "person":
            continue
        names = [e.get("canonical_name") or ""] + [a for a in str(e.get("aliases") or "").split(",")]
        groups.append(names)
    return Redactor(groups)
