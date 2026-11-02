"""
Evidence handling for the sandbox: what the model is shown, how its claims
are checked against the real case record, how steps are tied to real clock
times, and how scenarios are scored.

Nothing in here calls a model. The score is a transparent, documented rubric
over things that can be checked (citations that exist and are relevant, steps
that cite evidence, contradictions, dropped steps, physics, time anchors). It
is a heuristic for ranking, not a probability, and the interface says so.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from db import get_conn
from pipeline.timeline import get_timeline
from pipeline.sandbox_geometry import clean_text, clamp

MAX_PROMPT_OBSERVATIONS = 240
MAX_PROMPT_ENTITIES = 90
OBS_TEXT_LIMIT = 230

_CITE_RE = re.compile(r"\[([^\[\]\s]{3,64})\]")
_CLOCK_RE = re.compile(r"(?<![\d.:])(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]\.?m\.?)?(?![\d:])", re.IGNORECASE)
_AMPM_RE = re.compile(r"(?<![\d:])(\d{1,2})\s*([ap]\.?m\.?)(?!\w)", re.IGNORECASE)
_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATE_DMY = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)")
_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_DATE_TEXT = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})")

WORD_STOP = set("""the and for with that this from have were was are but not you your they them their there here what when where which who
would could should about into over after before then than also been being had has did does done just only some such very more most other
person people said says told stated report reports reported time""".split())

SCENE_TERMS = set("""door gate shutter entrance exit window counter shelf shelves cabinet locker safe room store stock office hall floor aisle corridor
stair stairs alley yard lock locked forced broke broken pried cut opened closed entered enters left leaves fled walked ran took taken stole
stolen cash till drawer bag camera cctv footage witness saw seen heard vault back rear front side roof wall gap damage tool crowbar glove
bedroom kitchen bathroom garage street road car vehicle van bike""".split())

CAUTION_WEIGHTS: Dict[str, Tuple[int, int]] = {
    "door_state": (5, 15), "cross_source_time": (2, 6), "unsupported_time_mentions": (3, 9), "disputed_sources": (2, 8), "weak_citations": (1, 6),
    "cross_person_clock": (2, 4), "officer_time_differs": (3, 6),
}

SCORE_FORMULA = (
    "score = 100 x (0.45 x share of steps citing relevant real evidence + 0.35 x distinct relevant observations cited (capped at 6) / 6 "
    "+ 0.20 x share of steps that were placed in the scene) - 8 per fact that contradicts the account with a real citation (3 without), or 2 per open question the "
    "evidence leaves unsettled (1 without); contradictions and open questions together capped at 30 "
    "- small fixed penalties for cautions (a door recorded as intact or locked that is used, times from different recordings, times in the text "
    "that no cited evidence gives, citations from disputed sources, citations that do not seem to concern the step; each capped). "
    "Capped at 25 if any hard physical or timing violation exists. "
    "This is a ranking heuristic over checkable facts, not a probability that the scenario is true."
)


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Gathering
# --------------------------------------------------------------------------

def gather_evidence(case_id: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        evidence_items = [dict(r) for r in conn.execute("SELECT * FROM evidence_items WHERE case_id=?", (case_id,)).fetchall()]
        observations = [dict(r) for r in conn.execute("SELECT * FROM observations WHERE case_id=?", (case_id,)).fetchall()]
        entities = [dict(r) for r in conn.execute("SELECT * FROM entities WHERE case_id=?", (case_id,)).fetchall()]
        relationships = [dict(r) for r in conn.execute("SELECT * FROM relationships WHERE case_id=?", (case_id,)).fetchall()]
        conflicts = [dict(r) for r in conn.execute("SELECT * FROM conflicts WHERE case_id=?", (case_id,)).fetchall()]
    finally:
        conn.close()
    return {"evidence_items": evidence_items, "observations": observations, "entities": entities, "relationships": relationships,
            "conflicts": conflicts, "timeline": get_timeline(case_id)}


def fingerprint_parts(ev: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Per-item hashes, kept with each run so a later change can be explained, not just detected."""
    return {
        "evidence": {e["evidence_id"]: e.get("file_hash") or "" for e in ev["evidence_items"]},
        "observations": {o["observation_id"]: text_hash(f"{o.get('description') or ''}|{o.get('extracted_time') or ''}")[:16] for o in ev["observations"]},
        "entities": {e["entity_id"]: "" for e in ev["entities"]},
        "conflicts": {c["conflict_id"]: c.get("review_status") or "" for c in ev["conflicts"]},
    }


def evidence_fingerprint(ev: Dict[str, Any]) -> str:
    return canonical_hash(fingerprint_parts(ev))


def diff_parts(old: Dict[str, Dict[str, str]], new: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for kind in ("evidence", "observations", "entities", "conflicts"):
        o, n = old.get(kind, {}), new.get(kind, {})
        out[kind] = {"added": len(set(n) - set(o)), "removed": len(set(o) - set(n)), "changed": sum(1 for k in set(o) & set(n) if o[k] != n[k])}
    out["any"] = any(v["added"] or v["removed"] or v["changed"] for v in out.values())
    return out


def describe_diff(diff: Dict[str, Any]) -> str:
    names = {"evidence": "evidence file", "observations": "observation", "entities": "entity", "conflicts": "conflict review"}
    parts = []
    for kind, label in names.items():
        d = diff.get(kind, {})
        for verb in ("added", "changed", "removed"):
            if d.get(verb):
                parts.append(f"{d[verb]} {label}{'s' if d[verb] != 1 else ''} {verb}")
    return ", ".join(parts) or "evidence changed"


def known_refs(ev: Dict[str, Any]) -> set:
    refs = {o["observation_id"] for o in ev["observations"]}
    refs |= {e["entity_id"] for e in ev["entities"]}
    refs |= {e["evidence_id"] for e in ev["evidence_items"]}
    refs |= {c["conflict_id"] for c in ev["conflicts"]}
    return refs


# --------------------------------------------------------------------------
# Clock times (HH:MM[:SS], am/pm, optional dates)
# --------------------------------------------------------------------------

def _to_sod(h: int, m: int, s: int, ampm: Optional[str]) -> Optional[int]:
    if ampm:
        a = ampm.lower().replace(".", "")
        if not (1 <= h <= 12):
            return None
        h = (h % 12) + (12 if a == "pm" else 0)
    if h > 23 or m > 59 or s > 59:
        return None
    return h * 3600 + m * 60 + s


def parse_clock(extracted_time: Any, time_claim: Any = None) -> Optional[Dict[str, Any]]:
    """Seconds into the day (and a date ordinal when the source gives one).
    Returns None when no usable clock time exists."""
    for src in (extracted_time, time_claim):
        text = str(src or "")
        m = _CLOCK_RE.search(text)
        sod: Optional[int] = None
        if m:
            sod = _to_sod(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), m.group(4))
        else:
            m2 = _AMPM_RE.search(text)
            if m2:
                sod = _to_sod(int(m2.group(1)), 0, 0, m2.group(2))
        if sod is None:
            continue
        day = None
        full = f"{extracted_time or ''} {time_claim or ''}"
        try:
            d = _DATE_ISO.search(full)
            if d:
                day = datetime.date(int(d.group(1)), int(d.group(2)), int(d.group(3))).toordinal()
            else:
                d = _DATE_DMY.search(full)
                if d:
                    day = datetime.date(int(d.group(3)), int(d.group(2)), int(d.group(1))).toordinal()
                else:
                    d = _DATE_TEXT.search(full)
                    if d and d.group(2)[:3].lower() in _MONTHS:
                        day = datetime.date(int(d.group(3)), _MONTHS[d.group(2)[:3].lower()], int(d.group(1))).toordinal()
        except ValueError:
            day = None
        return {"sod": sod, "day": day, "text": text.strip()[:40]}
    return None


def clock_mentions(text: str) -> List[int]:
    """All clock times (seconds into the day) written in free text."""
    out = []
    for m in _CLOCK_RE.finditer(text or ""):
        v = _to_sod(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), m.group(4))
        if v is not None:
            out.append(v)
    for m in _AMPM_RE.finditer(text or ""):
        v = _to_sod(int(m.group(1)), 0, 0, m.group(2))
        if v is not None:
            out.append(v)
    return out


def _fmt_clock(sod: int) -> str:
    return f"{(sod // 3600) % 24:02d}:{(sod % 3600) // 60:02d}"


# --------------------------------------------------------------------------
# What the model is shown
# --------------------------------------------------------------------------

def _obs_sort_key(o: dict):
    c = parse_clock(o.get("extracted_time"), o.get("time_claim"))
    return (c is None, c["sod"] if c else 0, o["observation_id"])


def _obs_relevance(o: dict) -> float:
    text = f"{o.get('description') or ''} {o.get('location') or ''} {o.get('action') or ''}".lower()
    words = set(re.findall(r"[a-z]+", text))
    score = 2.0 * len(words & SCENE_TERMS)
    if parse_clock(o.get("extracted_time"), o.get("time_claim")):
        score += 1.5
    if o.get("classification") == "observed":
        score += 1.0
    if len(text) > 40:
        score += 0.5
    return score


def select_observations(ev: Dict[str, Any]) -> Tuple[List[dict], int]:
    """Everything if it fits; otherwise the observations most about places and
    movement, in time order. Returns (selected, omitted) so omission is disclosed."""
    obs = ev["observations"]
    if len(obs) <= MAX_PROMPT_OBSERVATIONS:
        return sorted(obs, key=_obs_sort_key), 0
    ranked = sorted(obs, key=lambda o: (-_obs_relevance(o), o["observation_id"]))[:MAX_PROMPT_OBSERVATIONS]
    return sorted(ranked, key=_obs_sort_key), len(obs) - MAX_PROMPT_OBSERVATIONS


def evidence_context(ev: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Prompt text for the model. Evidence is wrapped in tags and the model is
    told to treat it as data, so text inside a witness statement cannot act as
    an instruction."""
    files = {e["evidence_id"]: e for e in ev["evidence_items"]}
    selected, omitted = select_observations(ev)
    lines = ["<evidence_data>", "EVIDENCE FILES:"]
    for e in ev["evidence_items"]:
        lines.append(f"- [{e['evidence_id']}] {clean_text(e['filename'], 120)} ({e['evidence_type']})")
    lines.append("\nOBSERVATIONS (id | clock time | kind | source) description:")
    for o in selected:
        src = files.get(o.get("source_evidence_id") or "", {}).get("filename", o.get("source_evidence_id") or "?")
        loc = clean_text(o.get("source_locator"), 40)
        lines.append(
            f"- [{o['observation_id']}] {o.get('extracted_time') or 'untimed'} | {o.get('classification') or '?'} | "
            f"{clean_text(src, 60)}{' ' + loc if loc else ''}: {clean_text(o.get('description'), OBS_TEXT_LIMIT)}"
        )
    if omitted:
        lines.append(f"(NOTE: {omitted} lower-relevance observations were not included because of size limits.)")
    lines.append("\nENTITIES (people, places, objects):")
    ents = ev["entities"]
    for e in ents[:MAX_PROMPT_ENTITIES]:
        lines.append(f"- [{e['entity_id']}] {clean_text(e['canonical_name'], 80)} ({e['entity_type']})")
    ent_omitted = max(0, len(ents) - MAX_PROMPT_ENTITIES)
    if ent_omitted:
        lines.append(f"(NOTE: {ent_omitted} further entities not shown.)")
    if ev["conflicts"]:
        lines.append("\nCONFLICTS BETWEEN SOURCES (officer review status in brackets; 'resolved' means the officer settled it):")
        for c in ev["conflicts"]:
            lines.append(f"- [{c.get('review_status') or 'unresolved'}] {clean_text(c['claim_a'], 200)} VERSUS {clean_text(c['claim_b'], 200)}")
    from pipeline.evidence_guard import screen_lines
    body, guard = screen_lines(lines[1:])
    lines = [lines[0]] + body
    lines.append("</evidence_data>")
    stats = {
        "guard": guard,
        "observations_total": len(ev["observations"]), "observations_shown": len(selected), "observations_omitted": omitted,
        "entities_total": len(ents), "entities_omitted": ent_omitted, "evidence_files": len(ev["evidence_items"]),
        "timed_observations": sum(1 for o in ev["observations"] if parse_clock(o.get("extracted_time"), o.get("time_claim"))),
    }
    return "\n".join(lines), stats


def build_evidence_index(ev: Dict[str, Any], ids: set) -> Dict[str, Dict[str, Any]]:
    """Snapshot of what every cited id actually says, frozen at generation time."""
    files = {e["evidence_id"]: e for e in ev["evidence_items"]}
    obs = {o["observation_id"]: o for o in ev["observations"]}
    ents = {e["entity_id"]: e for e in ev["entities"]}
    out: Dict[str, Dict[str, Any]] = {}
    for i in sorted(ids):
        if i in obs:
            o = obs[i]
            f = files.get(o.get("source_evidence_id") or "", {})
            out[i] = {"id": i, "kind": "observation", "text": clean_text(o.get("description"), 500), "time": o.get("extracted_time"),
                      "classification": o.get("classification"), "source_evidence_id": o.get("source_evidence_id"), "filename": f.get("filename"),
                      "locator": clean_text(o.get("source_locator"), 120), "limitations": clean_text(o.get("limitations"), 240)}
        elif i in ents:
            e = ents[i]
            out[i] = {"id": i, "kind": "entity", "text": f"{clean_text(e['canonical_name'], 120)} ({e['entity_type']})"}
        elif i in files:
            out[i] = {"id": i, "kind": "evidence", "text": clean_text(files[i]["filename"], 160), "filename": files[i]["filename"]}
    return out


# --------------------------------------------------------------------------
# Checking model claims
# --------------------------------------------------------------------------

def clean_refs(raw: Any, known: set) -> Tuple[List[str], List[str]]:
    valid, invalid, seen = [], [], set()
    for r in raw if isinstance(raw, list) else []:
        s = str(r).strip().strip("[]")
        if not s or s in seen:
            continue
        seen.add(s)
        (valid if s in known else invalid).append(s)
    return valid[:10], invalid[:10]


def clean_facts(raw: Any, known: set, limit: int = 12) -> List[Dict[str, Any]]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            text = clean_text(item.get("text") or item.get("fact"), 320)
            r = item.get("refs") or item.get("evidence_refs") or []
            refs_raw = list(r) if isinstance(r, list) else []
        else:
            text = clean_text(item, 320)
            refs_raw = []
        if not text:
            continue
        refs_raw += _CITE_RE.findall(text)
        valid, invalid = clean_refs(refs_raw, known)
        kind = str(item.get("kind") or "").lower() if isinstance(item, dict) else ""
        out.append({"text": text, "refs": valid, "invalid_refs": invalid, "supported": bool(valid), "kind": "open_question" if kind == "open_question" else "contradicts"})
        if len(out) >= limit:
            break
    return out


def content_words(text: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in WORD_STOP}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def citation_strength(claim_text: str, refs: List[str], index: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """Splits cited ids into (relevant, weak). A citation is weak when the claim
    has enough words to judge and shares none of them with what the cited
    observation says. Entities and files are accepted when named in the claim."""
    cw = {_stem(w) for w in content_words(claim_text)}
    strong, weak = [], []
    for r in refs:
        ent = index.get(r)
        if ent is None or len(cw) < 2:
            strong.append(r)
            continue
        ow = {_stem(w) for w in content_words(ent.get("text", ""))}
        (strong if cw & ow else weak).append(r)
    return strong, weak


def time_mentions_unsupported(text: str, cited_secs: List[int], tolerance_s: int = 150) -> List[str]:
    """Clock times written in free text that no cited observation gives."""
    out = []
    for sod in clock_mentions(text):
        if not any(min(abs(sod - c), 86400 - abs(sod - c)) <= tolerance_s for c in cited_secs):
            out.append(_fmt_clock(sod))
    return out


def disputed_observation_ids(ev: Dict[str, Any]) -> Dict[str, str]:
    """Observations that are one side of an unresolved conflict between sources."""
    out: Dict[str, str] = {}
    for c in ev["conflicts"]:
        if (c.get("review_status") or "unresolved") not in ("unresolved", "confirmed"):
            continue
        for src, t in ((c.get("source_a"), c.get("time_a")), (c.get("source_b"), c.get("time_b"))):
            for o in ev["observations"]:
                if o.get("source_evidence_id") == src and (o.get("extracted_time") or "") == (t or ""):
                    out[o["observation_id"]] = (c.get("nature_of_conflict") or c.get("question") or "a disputed fact")[:140]
    return out


# --------------------------------------------------------------------------
# Real clock time anchors (any number of people)
# --------------------------------------------------------------------------

def _delta(a: Dict[str, Any], b: Dict[str, Any]) -> int:
    if a["day"] is not None and b["day"] is not None:
        return (b["day"] - a["day"]) * 86400 + (b["sod"] - a["sod"])
    d = b["sod"] - a["sod"]
    return d + 86400 if d < -12 * 3600 else d


def compute_time_anchors(actors: List[dict], ev: Dict[str, Any], officer_times: Optional[List[int]] = None) -> Dict[str, Any]:
    """Ties steps to real clock times using the timed observations they cite.
    The model never supplies a clock time; it cites evidence, and the time comes
    from the case record. Times have minute precision at best, so comparisons
    allow a minute of slack. Disagreement between two different recordings is a
    caution (their clocks can differ), not a failure."""
    obs = {o["observation_id"]: o for o in ev["observations"]}
    names = {e["evidence_id"]: e.get("filename") for e in ev["evidence_items"]}
    anchors: List[Dict[str, Any]] = []
    for actor in actors:
        for st in actor.get("steps", []):
            cands = []
            for r in st.get("evidence_refs", []):
                o = obs.get(r)
                c = parse_clock(o.get("extracted_time"), o.get("time_claim")) if o else None
                if c:
                    cands.append((c["sod"], r, c, o))
            if cands:
                _, ref, c, o = min(cands, key=lambda x: x[0])
                anchors.append({"actor": actor["id"], "actor_label": actor.get("label", actor["id"]), "step": st["k"], "t_model": st["arrive_s"],
                                "sod": c["sod"], "day": c["day"], "observation_id": ref, "label": st["label"], "clock_text": o.get("extracted_time") or c["text"],
                                "source_evidence_id": o.get("source_evidence_id")})
    violations: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    cross_source: List[str] = []
    cross_person: List[str] = []
    for actor in actors:
        mine = sorted((a for a in anchors if a["actor"] == actor["id"]), key=lambda a: a["step"])
        for a, b in zip(mine, mine[1:]):
            real = _delta(a, b)
            model = b["t_model"] - a["t_model"]
            conflicting = real < -60 or real + 60 < model
            if conflicting and a["source_evidence_id"] != b["source_evidence_id"]:
                cross_source.append(
                    f"{actor['label']}: steps {a['step'] + 1} and {b['step'] + 1} rest on times from different recordings "
                    f"({names.get(a['source_evidence_id']) or a['source_evidence_id']} and {names.get(b['source_evidence_id']) or b['source_evidence_id']}). "
                    f"Their clocks may be offset from each other, so the apparent disagreement ({a['clock_text']} vs {b['clock_text']}) is not treated as a hard conflict.")
                continue
            if real < -60:
                violations.append({"code": "anchor_order_conflict", "step": b["step"], "actor": actor["id"],
                                   "message": f"{actor['label']}: evidence times put step {b['step'] + 1} ({b['clock_text']}) before step {a['step'] + 1} ({a['clock_text']}), but the scenario has them the other way round"})
            elif real + 60 < model:
                apart = (f"{real / 60:.0f} min apart" if real >= 0 else f"in the opposite order by about {abs(real) / 60:.0f} min ({a['clock_text']} then {b['clock_text']})")
                violations.append({"code": "anchor_time_conflict", "step": b["step"], "actor": actor["id"],
                                   "message": f"{actor['label']}: evidence puts steps {a['step'] + 1} and {b['step'] + 1} {apart}, but the movement between them needs at least {model / 60:.1f} min"})
            elif real - model > 60:
                notes.append({"actor": actor["id"], "from_step": a["step"], "to_step": b["step"], "unmodelled_s": int(real - model),
                              "message": f"{actor['label']}: {(real - model) / 60:.0f} min between steps {a['step'] + 1} and {b['step'] + 1} are not accounted for by the movement shown"})
    # one shared clock for the picture: origin = clock at model time 0
    origins = [a["sod"] - a["t_model"] for a in anchors]
    if origins and max(origins) - min(origins) > 120 and len({a["actor"] for a in anchors}) > 1:
        cross_person.append("Different people's cited times imply different start times for the same scenario; the clock shown follows the nearest cited step.")
    clock_anchors = sorted(({"t_model": a["t_model"], "sod": a["sod"], "observation_id": a["observation_id"], "actor": a["actor"]} for a in anchors), key=lambda x: x["t_model"])
    basis = "anchored" if anchors else "none"
    officer_note = ""
    officer_differs = 0
    first_step_t = min((st["arrive_s"] for a in actors for st in a.get("steps", [])), default=0.0)
    if not anchors and officer_times:
        clock_anchors = [{"t_model": first_step_t, "sod": officer_times[0], "observation_id": "", "actor": ""}]
        basis = "officer"
        officer_note = f"No step cites a timed observation; the clock starts at {_fmt_clock(officer_times[0])}, the time the officer gave."
    elif anchors and officer_times:
        implied = anchors[0]["sod"] - (anchors[0]["t_model"] - first_step_t)
        if min(abs(implied - o) for o in officer_times) > 1800:
            officer_differs = 1
            officer_note = f"The time the officer gave ({_fmt_clock(officer_times[0])}) differs by more than 30 minutes from the times in the cited evidence ({_fmt_clock(implied % 86400)})."
    note = {
        "anchored": "Evidence times have minute precision at best; the clock between cited steps is an estimate.",
        "officer": officer_note,
        "none": "No step cites a timed observation, so no real clock time is shown; elapsed time is relative.",
    }[basis]
    if officer_note and basis == "anchored":
        note += " " + officer_note
    return {
        "anchors": anchors, "violations": violations, "unmodelled_gaps": notes, "cross_source_notes": cross_source, "cross_person_notes": cross_person,
        "basis": basis, "note": note, "clock_anchors": clock_anchors, "officer_differs": officer_differs,
    }


# --------------------------------------------------------------------------
# Consistency with the saved case narrative
# --------------------------------------------------------------------------

def narrative_consistency(narrative: Optional[Dict[str, Any]], scenario_text: str) -> Dict[str, Any]:
    if not narrative:
        return {"available": False, "note": "No case narrative has been generated, so there is nothing to compare with."}
    sw = {_stem(w) for w in content_words(scenario_text)}
    missing = []
    facts = [f for f in narrative.get("supported_facts", []) if isinstance(f, str)]
    for f in facts:
        fw = {_stem(w) for w in content_words(f)}
        if len(fw) >= 3 and not (fw & sw):
            missing.append(f[:200])
    return {"available": True, "facts_total": len(facts), "facts_not_reflected": missing[:8],
            "note": "A rough word-overlap comparison with the case narrative's supported facts; it flags facts this scenario never mentions, not contradictions."}


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score_scenario(*, llm_estimate: int, steps: List[dict], dropped: int, supporting: List[dict], contradicted: List[dict],
                   hard_violations: int, observation_ids: set, cautions: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    n = max(len(steps), 1)
    cited = sum(1 for s in steps if s.get("strong_refs", s.get("evidence_refs")))
    coverage = cited / n
    distinct = set()
    for s in steps:
        distinct |= set(s.get("strong_refs", s.get("evidence_refs", [])))
    for f in supporting:
        distinct |= set(f["refs"])
    distinct_real = {r for r in distinct if r in observation_ids}
    support_term = min(1.0, len(distinct_real) / 6.0)
    placed = n / (n + dropped) if (n + dropped) else 0.0
    base = 100.0 * (0.45 * coverage + 0.35 * support_term + 0.20 * placed)
    # a fact that contradicts the account costs more than an open question the evidence simply leaves unsettled; anything not marked is treated as a contradiction
    pen_contra = min(30, sum((2 if f.get("kind") == "open_question" else 8) if f["refs"] else (1 if f.get("kind") == "open_question" else 3) for f in contradicted))
    caution_detail: Dict[str, int] = {}
    pen_caution = 0
    for name, count in (cautions or {}).items():
        w, cap = CAUTION_WEIGHTS.get(name, (1, 5))
        p = min(cap, w * count)
        caution_detail[name] = p
        pen_caution += p
    score = clamp(base - pen_contra - pen_caution, 0, 100)
    cap_reason = None
    if hard_violations:
        if score > 25:
            cap_reason = f"capped at 25 because {hard_violations} hard physical or timing violation(s) were found"
        score = min(score, 25)
    return {
        "verifiable_score": int(round(score)), "llm_estimate": int(clamp(llm_estimate, 0, 100)),
        "components": {
            "steps_total": n, "steps_citing_evidence": cited, "step_coverage": round(coverage, 3),
            "distinct_real_observations_cited": len(distinct_real), "support_term": round(support_term, 3),
            "steps_dropped_not_in_scene": dropped, "placed_share": round(placed, 3),
            "contradictions": sum(1 for f in contradicted if f.get("kind") != "open_question"), "open_questions": sum(1 for f in contradicted if f.get("kind") == "open_question"), "contradictions_with_citation": sum(1 for f in contradicted if f["refs"]),
            "caution_penalty_points": pen_caution, "caution_breakdown": caution_detail, "hard_violations": hard_violations,
            "base_before_penalties": round(base, 1), "penalty_points": pen_contra + pen_caution,
        },
        "cap_reason": cap_reason, "formula": SCORE_FORMULA,
    }
