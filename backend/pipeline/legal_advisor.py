"""
CaseWeave AI — Legal Advisory, Universal Legal Search & Statutory FIR Co-pilot.
Provides:
1. Universal legal search across BNS, BNSS, BSA, NDPS, POCSO, JJ Act, and Supreme Court Precedents.
2. Case evidentiary compliance checks (BSA Sec 63, BNSS Sec 105, juvenile safeguards).
3. A statutory FIR section suggestion, written by a language model from THIS case's recorded facts.

Honesty rules (this module feeds documents police may rely on):
- every suggestion is labelled as an AI suggestion that counsel must verify against the official text of the Act;
- the facts given to the model come only from the case record. Nothing about the accused (age, number, clothing)
  is assumed; where the evidence is silent the prompt says "not established" and the model is told not to
  assume. If the model cannot be reached, the advisory is empty with a notice, never a canned set of sections;
- the compliance checks only claim what the system can actually know. It cannot know that a certificate was
  signed or that a search was video-recorded, so those items say "not verified", not "compliant".
"""
import hashlib
import json
import logging
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from db import get_conn
from llm_client import LLMUnavailableError
from pipeline import llm_schema as sch
from pipeline.legal import _get_model, _get_collection, ensure_index_current, CORPUS_DIR
from pipeline.llm_guard import safe_chat_json

logger = logging.getLogger("caseweave.legal_advisor")

NOT_ESTABLISHED = "not established in the evidence"
VERIFY_NOTICE = ("AI-drafted suggestion based on this case's recorded facts. This is not legal advice and not a charging decision. A qualified legal "
                 "professional must confirm every section number, sub-clause, punishment and procedure against the official text of the Act, and the facts "
                 "against the source evidence, before anything here is relied on.")

FIR_ADVISORY_PROMPT = """You assist a Police Prosecutor in India. From ONLY the case facts below, suggest which sections of the Bharatiya Nyaya Sanhita (BNS, 2023) and relevant Special Acts (NDPS, POCSO, JJ Act, Arms Act) an FIR may need to consider. This is a suggestion for a human to verify, not a decision.

FACTUAL CASE CONTEXT:
Case ID: {case_id}
Title: {title}
Point of entry: {point_of_entry}
Tools: {tools_used}
Target goods / loss: {target_goods}
Timing window: {timing_window}
Number of offenders: {suspect_count}
Accused: age and identity {accused_note}
Observations:
{observations}

RULES:
1. Suggest a section only if the observations above support each of its ingredients; list the ingredients you matched in "statutory_ingredients_met" and cite what in the observations supports them. If an ingredient is not supported, do not suggest the section.
2. Forced entry into a building by night with preparation may fit BNS house-breaking by night provisions; theft in a building may fit the BNS theft-in-a-building provision. Verify the exact section and sub-clause numbers.
3. NDPS applies only if the substance taken is actually controlled under the NDPS Act's schedules. "Schedule H1" is a classification under the Drugs and Cosmetics Rules, NOT the NDPS Act, so it does not by itself bring the NDPS Act into play. If the observations name a substance, say that counsel must check whether it is a notified narcotic or psychotropic substance and in what quantity; do not assume.
4. If the accused's age is not established, say so in "age_assessed" and set "is_juvenile" to null. Never assume an age, a sex or a description of the accused.
5. If the accused may be under 18, the Juvenile Justice (Care and Protection of Children) Act, 2015 procedure applies instead of adult custody.
6. If five or more persons committed robbery together, dacoity (BNS) may apply. Only say so if the observations give that number.
7. Where punishment, cognizability, bailability or the court that tries the offence is uncertain, put null rather than guessing.

Return ONLY a JSON object with this structure:
{{
  "accused_demographic_assessment": {{"is_juvenile": null, "age_assessed": "<what the evidence says about age, or 'not established'>", "applicable_regime": "<procedure that applies, or 'depends on the accused's age, which is not established'>"}},
  "recommended_sections": [
    {{"act": "", "section": "", "title": "", "cognizable": null, "bailable": null, "punishment": null, "triable_by": null,
      "justification": "<which observations support it>", "statutory_ingredients_met": ["<ingredient matched, with the supporting fact>"]}}
  ],
  "evidentiary_safeguards": [
    {{"mandate": "", "status": "ACTION REQUIRED or NOT VERIFIED", "severity": "CRITICAL or HIGH or INFO", "detail": ""}}
  ]
}}
Use an empty "recommended_sections" list if the observations do not support any section."""

_AGE_RE = re.compile(r"\b(?:aged?\s*(\d{1,2})|(\d{1,2})[- ]?(?:years?|yrs?)[- ]?old)\b", re.I)
_JUVENILE_RE = re.compile(r"\b(juvenile|minor|child|schoolboy|school boy|school girl|schoolgirl)\b", re.I)

_ADVISORY_CACHE: Dict[tuple, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _read_corpus_docs() -> List[Dict[str, Any]]:
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001 - one unreadable file must not hide the others
            logger.warning("Error reading %s: %s", path, e)
    return docs


def get_all_legal_corpus_documents() -> List[Dict[str, Any]]:
    """Loads all structured legal documents from legal_corpus/."""
    return _read_corpus_docs()


def _result(d: Dict[str, Any], similarity: float, match_type: str) -> Dict[str, Any]:
    return {
        "id": d["id"], "act": d.get("act", "Statute"), "section": d.get("section", ""), "title": d["title"], "topic": d.get("topic", ""),
        "cognizable": d.get("cognizable"), "bailable": d.get("bailable"), "punishment": d.get("punishment", ""),
        "triable_by": d.get("triable_by", ""), "ingredients": d.get("ingredients", []), "similarity_score": similarity,
        "text": d.get("text", ""), "match_type": match_type, "source_url": d.get("source_url") or None,
        "verification_status": d.get("verification_status", "unverified"),
    }


def universal_legal_search(query: str, top_k: int = 5, act_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Universal semantic & keyword search across the entire Indian legal corpus."""
    top_k = max(1, min(int(top_k or 5), 25))
    all_docs = _read_corpus_docs()
    query_lower = (query or "").strip().lower()
    if not query_lower:
        return []

    exact_matches = []
    for d in all_docs:
        act = str(d.get("act", "")).lower()
        if act_filter and act_filter.lower() not in act:
            continue
        hay = (str(d.get("section", "")), str(d.get("title", "")), str(d.get("topic", "")))
        if any(query_lower in h.lower() for h in hay):
            exact_matches.append(_result(d, 1.0, "exact_keyword"))

    try:
        model = _get_model()
        ensure_index_current()
        collection = _get_collection()
        q_emb = model.encode([query], convert_to_numpy=True).tolist()
        results = collection.query(query_embeddings=q_emb, n_results=min(top_k + len(exact_matches), collection.count()))
        ids = results["ids"][0] if results["ids"] else []
        distances = results["distances"][0] if results["distances"] else []
        doc_map = {d["id"]: d for d in all_docs}
        have = {m["id"] for m in exact_matches}
        vector_matches = []
        for d_id, dist in zip(ids, distances):
            d = doc_map.get(d_id)
            if d_id in have or not d:
                continue
            if act_filter and act_filter.lower() not in str(d.get("act", "")).lower():
                continue
            vector_matches.append(_result(d, round(max(0.0, min(1.0, 1.0 - dist)), 4), "semantic_vector"))
        return (exact_matches + vector_matches)[:top_k]
    except Exception as e:  # noqa: BLE001 - keyword matches are still correct without the vector index
        logger.warning("Semantic search fallback: %s", e)
        return exact_matches[:top_k]


# --------------------------------------------------------------- compliance checks ----

def _case_facts(case_id: str) -> Dict[str, Any]:
    with get_conn() as conn:
        evidence = [dict(r) for r in conn.execute("SELECT * FROM evidence_items WHERE case_id = ?", (case_id,)).fetchall()]
        observations = [dict(r) for r in conn.execute("SELECT * FROM observations WHERE case_id = ?", (case_id,)).fetchall()]
        conflicts = [dict(r) for r in conn.execute("SELECT * FROM conflicts WHERE case_id = ?", (case_id,)).fetchall()]
        entities = [dict(r) for r in conn.execute("SELECT * FROM entities WHERE case_id = ?", (case_id,)).fetchall()]
    return {"evidence": evidence, "observations": observations, "conflicts": conflicts, "entities": entities}


def _age_evidence(facts: Dict[str, Any]) -> Dict[str, Any]:
    """What the record says about the accused's age: ages mentioned near 'suspect/accused/offender' and juvenile words."""
    ages, juvenile_hits = [], []
    for o in facts["observations"]:
        t = o.get("description") or ""
        if not re.search(r"\b(suspect|accused|offender|intruder|culprit|boy|youth)\b", t, re.I):
            continue
        for m in _AGE_RE.finditer(t):
            ages.append(int(m.group(1) or m.group(2)))
        if _JUVENILE_RE.search(t):
            juvenile_hits.append(t[:120])
    return {"ages": ages, "juvenile_mentions": juvenile_hits}


def audit_case_legal_compliance(case_id: str) -> Dict[str, Any]:
    """Evaluates case facts against mandatory Indian procedural & evidentiary rules, claiming only what the system can know."""
    facts = _case_facts(case_id)
    evidence, conflicts = facts["evidence"], facts["conflicts"]
    items: List[Dict[str, Any]] = []

    # Every stored file is an electronic record (a log, a video, a PDF, a digital photograph).
    if evidence:
        items.append({
            "rule": "BSA Section 63 electronic evidence certificate",
            "statute": "Bharatiya Sakshya Adhiniyam, 2023 (Sec 63); Arjun Panditrao (2020)",
            "status": "CERTIFICATE_REQUIRED",
            "verdict": "Action required: CaseWeave holds no signed Section 63 certificate for these records",
            "details": f"{len(evidence)} electronic record(s) are stored. A certificate from the person responsible for each device or system is needed before they are relied on in court. A draft can be generated for each item.",
            "severity": "HIGH",
            "statutory_form": "Section 63 certificate (Schedule to the BSA)",
        })

    clock = [c for c in conflicts if re.search(r"drift|clock|offset|timestamp|time stamp|out of sync", f"{c.get('nature_of_conflict') or ''} {c.get('question') or ''} {c.get('claim_a') or ''} {c.get('claim_b') or ''}", re.I)]
    if clock:
        items.append({
            "rule": "Device clock offset must be stated in the certificate",
            "statute": "BSA 2023 Section 63; IEA 1872 Section 65B(2) (earlier law)",
            "status": "DISCLOSURE_RECOMMENDED",
            "verdict": f"{len(clock)} conflict(s) between sources involve device clocks or time stamps",
            "details": "Where two systems' clocks disagree, the certificate should state each device's known offset so the disagreement is explained rather than discovered by the other side.",
            "severity": "HIGH",
            "statutory_form": "Technical note on system clock accuracy",
        })

    photos = [e for e in evidence if e.get("evidence_type") == "image"]
    items.append({
        "rule": "BNSS Section 105 audio-video recording of search and seizure",
        "statute": "Bharatiya Nagarik Suraksha Sanhita, 2023 (Sec 105)",
        "status": "NOT_VERIFIED",
        "verdict": "Not verified: CaseWeave cannot tell whether the search or seizure was audio-video recorded",
        "details": f"{len(photos)} photograph(s) are catalogued with SHA-256 hashes. Photographs are not the audio-video recording the section asks for; confirm that a recording exists and add it as evidence.",
        "severity": "HIGH" if not any(e.get("evidence_type") == "video" for e in evidence) else "INFO",
        "statutory_form": "Seizure memo with recording reference",
    })

    age = _age_evidence(facts)
    entity_hits = [e for e in facts["entities"] if _JUVENILE_RE.search(f"{e.get('canonical_name') or ''} {e.get('aliases') or ''}")]
    if age["juvenile_mentions"] or entity_hits or any(a < 18 for a in age["ages"]):
        items.append({
            "rule": "Juvenile Justice Act safeguards",
            "statute": "Juvenile Justice (Care and Protection of Children) Act, 2015",
            "status": "SPECIAL_PROCEDURE_MAY_APPLY",
            "verdict": "The record mentions a juvenile or minor in connection with the accused; confirm the age before any custody decision",
            "details": "If the accused is under 18, adult police custody is barred: the child must be referred to the Juvenile Justice Board and the Special Juvenile Police Unit, and identity must not be disclosed.",
            "severity": "CRITICAL",
            "statutory_form": "Age determination record; Social Investigation Report",
        })
    else:
        items.append({
            "rule": "Accused's age",
            "statute": "BNSS 2023 Sec 35; Juvenile Justice Act 2015",
            "status": "AGE_NOT_ESTABLISHED",
            "verdict": "The accused's age is not established by the evidence recorded so far",
            "details": "Nothing in the case record states the accused's age, so CaseWeave cannot confirm the adult procedure applies. Establish and record the age before any arrest or custody decision.",
            "severity": "INFO",
            "statutory_form": "Age determination record",
        })

    return {"case_id": case_id, "total_exhibits_audited": len(evidence), "compliance_items": items, "audited_at": datetime.now().isoformat(),
            "notice": "Checks are limited to what the case record can show. They are prompts for the investigating officer, not a legal opinion."}


# ----------------------------------------------------------------------- FIR advisory ----

_CORPUS_CACHE: Dict[str, Any] = {}


def _corpus_index() -> Dict[tuple, Dict[str, Any]]:
    """The bundled legal summaries by (act's first two words, section number), loaded once."""
    if not _CORPUS_CACHE:
        for path in sorted(CORPUS_DIR.glob("*.json")):
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            key = (" ".join(str(d.get("act") or "").lower().split()[:2]), str(d.get("section") or "").lower())
            _CORPUS_CACHE[key] = d
    return _CORPUS_CACHE


def _fill_from_corpus(sec: Dict[str, Any]) -> Dict[str, Any]:
    """The model often leaves cognizable, bailable, punishment and triable-by empty. Where the section is in the bundled corpus (matched on act and
    base section number, so "305(a)" finds 305), the empty fields are filled from it and the source is named. A value the model did give is kept.
    Nothing is invented: a section not in the corpus keeps its empty fields, and the screen says "not stated"."""
    act = " ".join(str(sec.get("act") or "").lower().split()[:2])
    m = re.match(r"\s*(\d+[a-z]?)", str(sec.get("section") or "").lower())
    doc = _corpus_index().get((act, m.group(1))) if m else None
    if not doc:
        return sec
    out, filled = dict(sec), False
    for k in ("cognizable", "bailable", "punishment", "triable_by"):
        if out.get(k) in (None, "") and doc.get(k) not in (None, ""):
            out[k] = doc[k]
            filled = True
    if filled:
        out["details_source"] = "legal corpus summary (unverified, check the official text)"
    return out


def _facts_fingerprint(case_id: str, facts: Dict[str, Any], sig: Dict[str, Any]) -> tuple:
    h = hashlib.sha256()
    for o in sorted(facts["observations"], key=lambda o: o["observation_id"]):
        h.update(f"{o['observation_id']}|{o.get('description')}".encode())
    h.update(json.dumps(sig, sort_keys=True, default=str).encode())
    return (case_id, h.hexdigest())


def get_fir_legal_advisory(case_id: str) -> Dict[str, Any]:
    """The FIR section suggestion plus the compliance audit. Computed once per state of the case's observations."""
    facts = _case_facts(case_id)
    with get_conn() as conn:
        case_row = conn.execute("SELECT title FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        sig = conn.execute("SELECT * FROM case_signatures WHERE case_id = ?", (case_id,)).fetchone() or {}
    title = case_row["title"] if case_row else f"Case {case_id}"
    compliance = audit_case_legal_compliance(case_id)
    base = {"case_id": case_id, "title": title, "compliance_audit": compliance, "notice": VERIFY_NOTICE}

    if not facts["observations"]:
        return {**base, "status": "unavailable", "advisory": {"recommended_sections": [], "evidentiary_safeguards": [], "accused_demographic_assessment": {
            "is_juvenile": None, "age_assessed": NOT_ESTABLISHED, "applicable_regime": "cannot be determined without evidence"}},
            "reason": "This case has no analysed observations yet, so no sections can be suggested."}

    fp = _facts_fingerprint(case_id, facts, {k: sig.get(k) for k in ("point_of_entry", "tools_used", "target_goods", "timing_window", "suspect_count")})
    with _cache_lock:
        if fp in _ADVISORY_CACHE:
            return {**base, **_ADVISORY_CACHE[fp], "cached": True}

    age = _age_evidence(facts)
    accused_note = (f"mentioned in the record: {sorted(set(age['ages']))}" if age["ages"] else NOT_ESTABLISHED)
    obs = sorted(facts["observations"], key=lambda o: (o.get("extracted_time") or "99:99"))[:40]
    obs_text = "\n".join(f"- [{o.get('extracted_time') or 'time unknown'}] {o.get('subject') or ''} {o.get('action') or ''}: {o.get('description')}" for o in obs)
    prompt = FIR_ADVISORY_PROMPT.format(
        case_id=case_id, title=title, point_of_entry=sig.get("point_of_entry") or NOT_ESTABLISHED, tools_used=sig.get("tools_used") or NOT_ESTABLISHED,
        target_goods=sig.get("target_goods") or NOT_ESTABLISHED, timing_window=sig.get("timing_window") or NOT_ESTABLISHED,
        suspect_count=sig.get("suspect_count") or NOT_ESTABLISHED, accused_note=accused_note, observations=obs_text)
    try:
        _, raw = safe_chat_json(case_id, "You assist a Police Prosecutor. Output valid JSON only; never assume facts that are not given.", prompt, max_tokens=3072)
    except LLMUnavailableError as e:
        logger.warning("FIR advisory unavailable: %s", e)
        return {**base, "status": "unavailable", "reason": "The language model could not be reached, so no sections were suggested. Nothing was assumed.",
                "advisory": {"recommended_sections": [], "evidentiary_safeguards": [], "accused_demographic_assessment": {
                    "is_juvenile": None, "age_assessed": NOT_ESTABLISHED, "applicable_regime": "cannot be determined"}}}

    data = raw if isinstance(raw, dict) else {}
    demo = data.get("accused_demographic_assessment") if isinstance(data.get("accused_demographic_assessment"), dict) else {}
    sections = []
    for s in sch.records(data.get("recommended_sections")):
        s = _fill_from_corpus(s)
        sections.append({
            "act": sch.text(s.get("act"), 200) or "", "section": sch.text(s.get("section"), 40) or "", "title": sch.text(s.get("title"), 300) or "",
            "cognizable": s.get("cognizable") if isinstance(s.get("cognizable"), bool) else None,
            "bailable": s.get("bailable") if isinstance(s.get("bailable"), bool) else None,
            "punishment": sch.text(s.get("punishment"), 300), "triable_by": sch.text(s.get("triable_by"), 200),
            "justification": sch.text(s.get("justification"), 800) or "",
            "statutory_ingredients_met": sch.string_list(s.get("statutory_ingredients_met"), limit=10, item_limit=300),
            "details_source": s.get("details_source"),
        })
    safeguards = []
    for g in sch.records(data.get("evidentiary_safeguards")):
        safeguards.append({"mandate": sch.text(g.get("mandate"), 200) or "", "status": sch.text(g.get("status"), 40) or "NOT VERIFIED",
                           "severity": sch.choice(str(g.get("severity") or "").upper(), ("critical", "high", "info"), "info").upper(), "detail": sch.text(g.get("detail"), 600) or ""})
    payload = {
        "status": "ok",
        "advisory": {
            "accused_demographic_assessment": {
                "is_juvenile": demo.get("is_juvenile") if isinstance(demo.get("is_juvenile"), bool) else None,
                "age_assessed": sch.text(demo.get("age_assessed"), 300) or NOT_ESTABLISHED,
                "applicable_regime": sch.text(demo.get("applicable_regime"), 300) or "depends on the accused's age, which is not established",
            },
            "recommended_sections": sections, "evidentiary_safeguards": safeguards, "source": "language model, from this case's recorded observations",
        },
    }
    with _cache_lock:
        _ADVISORY_CACHE[fp] = payload
    return {**base, **payload, "cached": False}
