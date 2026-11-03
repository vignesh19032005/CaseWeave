"""
CaseWeave AI — Cross-Case Modus Operandi (M.O.) & Pattern Intelligence Engine.
Identifies recurring crime patterns, tool signatures and entry mechanics across cases using dense vector
embeddings (all-MiniLM-L6-v2) and an LLM comparative synthesis.

Honesty rules this module follows:
- the M.O. of a case is written ONLY from that case's own observations. If the model cannot be reached, or the
  case has no observations, the result says so ("unavailable"); a plausible-looking signature is never invented
  and never stored;
- the reference cases it compares against (CW-HIST-*) are SYNTHETIC demonstration records, clearly labelled as
  such in every result. They are kept out of the real `cases` table, so they never appear in anyone's case list;
- matches and synthesis are computed once and cached; the cache is reset whenever the signature is recomputed.
"""
import json
import logging
from typing import Any, Dict, List, Optional

import chromadb
from db import get_conn, utcnow
from llm_client import LLMUnavailableError
from pipeline import llm_schema as sch
from pipeline.legal import CHROMA_DIR, _get_model
from pipeline.llm_guard import safe_chat_json

logger = logging.getLogger("caseweave.patterns")

DEMO_PREFIX = "CW-HIST-"
MAX_OBSERVATIONS = 60

_client = None
_patterns_collection = None
_seeded = False


def _get_patterns_collection():
    global _client, _patterns_collection
    if _patterns_collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _patterns_collection = _client.get_or_create_collection(
            "case_patterns", metadata={"hnsw:space": "cosine"}
        )
    return _patterns_collection


MO_EXTRACTION_PROMPT = """You are a forensic analyst profiling criminal modus operandi (M.O.).
From ONLY the observations of the case below, extract its M.O. fingerprint. Use what the evidence says; where the evidence does not say, write "not established" (and use 0 for suspect_count) rather than guessing.

Return ONLY a valid JSON object with EXACTLY these keys (no markdown, no extra commentary):
{{
  "crime_category": "<snake_case category the evidence supports, or not_established>",
  "point_of_entry": "<how the premises were entered, or not established>",
  "tools_used": "<tools the evidence mentions, or not established>",
  "target_goods": "<what was taken or targeted, or not established>",
  "timing_window": "<time window the evidence gives, or not established>",
  "suspect_count": <integer number of offenders the evidence supports, 0 if unknown>,
  "signature_traits": ["<short distinctive behaviours that appear in the evidence>"],
  "mo_summary": "<two or three sentences using only facts from the observations>"
}}

CASE TITLE: {title}
CASE OBSERVATIONS:
{context}
"""

COMPARATIVE_SYNTHESIS_PROMPT = """You are a senior criminal intelligence analyst evaluating a potential link between two cases.
Compare the ACTIVE CASE against the REFERENCE CASE below, using only what is written here.

ACTIVE CASE M.O.:
- Title: {active_title}
- Summary: {active_summary}
- Entry: {active_entry}
- Tools: {active_tools}
- Target: {active_target}
- Timing: {active_timing}
- Signatures: {active_signatures}

REFERENCE CASE M.O.{reference_note}:
- Title: {hist_title}
- Jurisdiction: {hist_jurisdiction}
- Date: {hist_date}
- Summary: {hist_summary}
- Entry: {hist_entry}
- Tools: {hist_tools}
- Target: {hist_target}
- Timing: {hist_timing}
- Signatures: {hist_signatures}

Return ONLY a valid JSON object with this structure:
{{
  "verdict": "STRONG PATTERN SIMILARITY" or "MODERATE PATTERN SIMILARITY" or "DISTINCT UNRELATED CRIME",
  "matching_traits": ["<trait both cases share, quoted from the two M.O.s>"],
  "divergent_factors": ["<way the two differ>"],
  "inter_station_leads": ["<a concrete follow-up an investigator could make, based on the comparison>"]
}}
A similarity of M.O. is an investigative lead, never proof that the same person committed both."""


def _load_traits(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def _signature_from_row(row: dict) -> Dict[str, Any]:
    return {
        "case_id": row["case_id"],
        "crime_category": row.get("crime_category") or "not_established",
        "point_of_entry": row.get("point_of_entry") or "not established",
        "tools_used": row.get("tools_used") or "not established",
        "target_goods": row.get("target_goods") or "not established",
        "timing_window": row.get("timing_window") or "not established",
        "suspect_count": row.get("suspect_count") or 0,
        "signature_traits": _load_traits(row.get("signature_traits")),
        "mo_summary": row.get("mo_summary") or "",
        "created_at": row.get("created_at") or "",
    }


class PatternsUnavailable(RuntimeError):
    """The M.O. could not be built from this case's evidence; the message says why."""


def extract_case_signature(case_id: str, force: bool = False) -> Dict[str, Any]:
    """Extracts or retrieves the structured M.O. fingerprint for a case. Raises PatternsUnavailable (never invents one)."""
    with get_conn() as conn:
        if not force:
            existing = conn.execute("SELECT * FROM case_signatures WHERE case_id = ?", (case_id,)).fetchone()
            if existing:
                return _signature_from_row(existing)
        case_row = conn.execute("SELECT title FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        title = case_row["title"] if case_row else f"Case {case_id}"
        obs = conn.execute(
            "SELECT description, extracted_time, subject, action, location FROM observations WHERE case_id = ? LIMIT ?",
            (case_id, MAX_OBSERVATIONS),
        ).fetchall()

    if not obs:
        raise PatternsUnavailable("This case has no analysed observations yet. Run the analysis first.")

    context_text = "\n".join(
        f"- [{o.get('extracted_time') or 'time unknown'}] ({o.get('location') or 'place unknown'}) "
        f"{o.get('subject') or ''} {o.get('action') or ''}: {o.get('description') or ''}"
        for o in obs
    )
    prompt = MO_EXTRACTION_PROMPT.format(title=title, context=context_text)
    try:
        _, raw = safe_chat_json(case_id, "You profile criminal modus operandi from evidence only. Output valid JSON.", prompt)
    except LLMUnavailableError as e:
        raise PatternsUnavailable(f"The language model could not be reached, so no M.O. was produced. Nothing was guessed. ({str(e)[:120]})")
    data = raw if isinstance(raw, dict) else {}
    traits = sch.string_list(data.get("signature_traits"), limit=12, item_limit=200)
    try:
        suspects = max(0, int(data.get("suspect_count") or 0))
    except (TypeError, ValueError):
        suspects = 0
    sig = {
        "crime_category": sch.text(data.get("crime_category"), 60) or "not_established",
        "point_of_entry": sch.text(data.get("point_of_entry"), 120) or "not established",
        "tools_used": sch.text(data.get("tools_used"), 250) or "not established",
        "target_goods": sch.text(data.get("target_goods"), 250) or "not established",
        "timing_window": sch.text(data.get("timing_window"), 60) or "not established",
        "suspect_count": suspects,
        "signature_traits": traits,
        "mo_summary": sch.text(data.get("mo_summary"), 2000) or "",
    }

    now = utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "REPLACE INTO case_signatures (case_id, crime_category, point_of_entry, tools_used, target_goods, timing_window, suspect_count, "
            "signature_traits, mo_summary, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (case_id, sig["crime_category"], sig["point_of_entry"], sig["tools_used"], sig["target_goods"], sig["timing_window"],
             sig["suspect_count"], json.dumps(traits), sig["mo_summary"], now),
        )
        conn.commit()

    try:
        embed_text = _embed_text(title, sig)
        _get_patterns_collection().upsert(
            ids=[case_id], embeddings=_get_model().encode([embed_text], convert_to_numpy=True).tolist(), documents=[embed_text],
            metadatas=[{"case_id": case_id, "title": title, "crime_category": sig["crime_category"]}],
        )
    except Exception as e:  # noqa: BLE001 - the signature is saved; only similarity search is affected
        logger.warning("Could not index signature in ChromaDB: %s", e)

    return {"case_id": case_id, **sig, "created_at": now}


def _embed_text(title: str, sig: Dict[str, Any]) -> str:
    return (f"{title}. Category: {sig.get('crime_category')}. Entry: {sig.get('point_of_entry')}. Tools: {sig.get('tools_used')}. "
            f"Target: {sig.get('target_goods')}. Summary: {sig.get('mo_summary')}")


HISTORICAL_SEED_CASES = [
    {
        "case_id": "CW-HIST-01",
        "title": "Night break-in of a 24-hour pharmacy (rear shutter)",
        "jurisdiction": "Reference record A",
        "fir_number": "demo reference, not a real FIR",
        "fir_date": "2025-10-08",
        "crime_category": "commercial_burglary",
        "point_of_entry": "rear rolling shutter / alleyway gate",
        "tools_used": "18-inch hexagonal crowbar, manual lever",
        "target_goods": "Schedule H1 syrup and tablets, cash counter register",
        "timing_window": "02:15 - 02:40 AM",
        "suspect_count": 1,
        "signature_traits": [
            "fractured centre lock bracket on rolling shutter",
            "single intruder in a hooded dark raincoat and blue nitrile gloves",
            "selective looting of the controlled-drugs cabinet",
            "escape on foot toward a service lane",
        ],
        "mo_summary": (
            "Single hooded intruder breached the rear shutter of a 24-hour pharmacy at 02:15 AM using an 18-inch "
            "hex crowbar to snap the centre lock clasp. Wore blue nitrile gloves. Ignored cosmetics and selectively "
            "took cash and controlled formulations."
        ),
    },
    {
        "case_id": "CW-HIST-02",
        "title": "Pharmacy rooftop entry (cut roof sheeting)",
        "jurisdiction": "Reference record B",
        "fir_number": "demo reference, not a real FIR",
        "fir_date": "2025-08-19",
        "crime_category": "commercial_burglary",
        "point_of_entry": "rooftop asbestos sheet cut and ceiling hatch",
        "tools_used": "tin snips, nylon climbing rope, battery grinder",
        "target_goods": "oncology medications, insulin stock, desktop computer",
        "timing_window": "03:10 - 04:00 AM",
        "suspect_count": 2,
        "signature_traits": [
            "vertical entry from adjacent building terrace",
            "cut CCTV coaxial cables inside premises",
            "cloth surgical gloves worn",
        ],
        "mo_summary": (
            "Two suspects scaled an adjacent under-construction building, cut rooftop sheeting with tin snips, "
            "and dropped into a pharmacy storeroom at 03:10 AM. Severed recorder cables and took oncology drugs."
        ),
    },
    {
        "case_id": "CW-HIST-03",
        "title": "Jewellery showroom glass-front smash",
        "jurisdiction": "Reference record C",
        "fir_number": "demo reference, not a real FIR",
        "fir_date": "2025-07-02",
        "crime_category": "armed_robbery_heist",
        "point_of_entry": "front toughened glass facade smashed",
        "tools_used": "10-pound sledgehammer, oxy-acetylene torch, iron levers",
        "target_goods": "gold jewellery ornaments, display trays",
        "timing_window": "05:15 - 05:25 AM",
        "suspect_count": 4,
        "signature_traits": [
            "dawn smash-and-grab",
            "getaway on two motorcycles",
            "full-face helmets and woollen caps worn",
        ],
        "mo_summary": (
            "Four helmeted assailants shattered the front glass door with a sledgehammer at 05:15 AM, "
            "threatened an unarmed guard, scooped gold display trays into sacks and fled on motorbikes."
        ),
    },
    {
        "case_id": "CW-HIST-04",
        "title": "Diagnostic centre storeroom theft (window)",
        "jurisdiction": "Reference record D",
        "fir_number": "demo reference, not a real FIR",
        "fir_date": "2025-09-14",
        "crime_category": "commercial_burglary",
        "point_of_entry": "side sliding aluminium window",
        "tools_used": "screwdriver, small pry bar",
        "target_goods": "petty cash box, laser printer",
        "timing_window": "01:30 - 02:00 AM",
        "suspect_count": 1,
        "signature_traits": [
            "forced window latch open with a flathead screwdriver",
            "untargeted ransacking of office desks",
            "bare-handed fingerprints left on glass pane",
        ],
        "mo_summary": (
            "Opportunistic burglary through a ground-floor sliding window pried open with a flathead screwdriver. "
            "Left latent fingerprints on the glass and took a small amount of cash from an unlocked box."
        ),
    },
]


def seed_historical_patterns() -> int:
    """Loads the four SYNTHETIC reference records into case_signatures and the vector index (not into `cases`).
    Idempotent and cheap: it does nothing once they are present."""
    global _seeded
    collection = _get_patterns_collection()
    with get_conn() as conn:
        have = {r["case_id"] for r in conn.execute("SELECT case_id FROM case_signatures WHERE case_id LIKE ?", (DEMO_PREFIX + "%",)).fetchall()}
    in_index = set(collection.get(ids=[c["case_id"] for c in HISTORICAL_SEED_CASES], include=[])["ids"])
    missing = [c for c in HISTORICAL_SEED_CASES if c["case_id"] not in have or c["case_id"] not in in_index]
    if not missing:
        _seeded = True
        return 0
    model = _get_model()
    with get_conn() as conn:
        for case in missing:
            conn.execute(
                "REPLACE INTO case_signatures (case_id, crime_category, point_of_entry, tools_used, target_goods, timing_window, suspect_count, "
                "signature_traits, mo_summary, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (case["case_id"], case["crime_category"], case["point_of_entry"], case["tools_used"], case["target_goods"], case["timing_window"],
                 case["suspect_count"], json.dumps(case["signature_traits"]), case["mo_summary"], case["fir_date"]),
            )
            embed_text = _embed_text(case["title"], case)
            collection.upsert(
                ids=[case["case_id"]], embeddings=model.encode([embed_text], convert_to_numpy=True).tolist(), documents=[embed_text],
                metadatas=[{"case_id": case["case_id"], "title": case["title"], "jurisdiction": case["jurisdiction"],
                            "fir_number": case["fir_number"], "fir_date": case["fir_date"], "crime_category": case["crime_category"]}],
            )
        conn.commit()
    _seeded = True
    return len(missing)


def _ensure_seeded():
    if not _seeded:
        seed_historical_patterns()


def get_case_patterns(case_id: str, force: bool = False) -> Dict[str, Any]:
    """Similarity of this case's M.O. to the reference cases and to the other cases of this deployment.
    Cached after the first computation; never fabricated: if it cannot be computed the result has status
    "unavailable" and a reason."""
    _ensure_seeded()

    if not force:
        with get_conn() as conn:
            cached = conn.execute("SELECT * FROM case_signatures WHERE case_id = ?", (case_id,)).fetchone()
        if cached and cached.get("matches_json") and cached.get("synthesis_json"):
            try:
                return {
                    "status": "ok", "case_id": case_id, "active_signature": _signature_from_row(cached),
                    "similar_cases": json.loads(cached["matches_json"]), "comparative_synthesis": json.loads(cached["synthesis_json"]),
                    "cached": True, "computed_at": cached.get("computed_at") or cached.get("created_at"),
                }
            except (TypeError, ValueError) as e:
                logger.warning("Error parsing cached pattern intelligence for %s: %s", case_id, e)

    try:
        active_sig = extract_case_signature(case_id, force=force)
    except PatternsUnavailable as e:
        return {"status": "unavailable", "reason": str(e), "case_id": case_id, "active_signature": None, "similar_cases": [],
                "comparative_synthesis": None, "cached": False}

    with get_conn() as conn:
        title_row = conn.execute("SELECT title FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    title = title_row["title"] if title_row else case_id
    model = _get_model()
    collection = _get_patterns_collection()
    active_emb = model.encode([_embed_text(title, active_sig)], convert_to_numpy=True).tolist()
    results = collection.query(query_embeddings=active_emb, n_results=min(7, collection.count()))

    matches: List[Dict[str, Any]] = []
    ids = results["ids"][0] if results["ids"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []
    with get_conn() as conn:
        for m_id, meta, dist in zip(ids, metadatas, distances):
            if m_id == case_id:
                continue  # Don't match against self
            sig_row = conn.execute("SELECT * FROM case_signatures WHERE case_id = ?", (m_id,)).fetchone()
            if not sig_row:
                continue  # indexed but its record was removed (for example a deleted case)
            similarity = round(max(0.0, min(1.0, 1.0 - dist)), 4)
            demo = m_id.startswith(DEMO_PREFIX)
            sig = _signature_from_row(sig_row)
            matches.append({
                "case_id": m_id,
                "title": ("[SYNTHETIC REFERENCE] " if demo else "") + (meta.get("title") or m_id),
                "is_synthetic_reference": demo,
                "jurisdiction": meta.get("jurisdiction") or "This deployment",
                "fir_number": meta.get("fir_number") or "",
                "fir_date": meta.get("fir_date") or sig_row.get("created_at") or "",
                "similarity_score": similarity,
                "similarity_percentage": int(round(similarity * 100)),
                **{k: sig[k] for k in ("crime_category", "point_of_entry", "tools_used", "target_goods", "timing_window", "suspect_count", "signature_traits", "mo_summary")},
            })
    matches.sort(key=lambda x: x["similarity_score"], reverse=True)

    synthesis: Optional[dict] = None
    if matches and matches[0]["similarity_score"] >= 0.65:
        top = matches[0]
        prompt = COMPARATIVE_SYNTHESIS_PROMPT.format(
            active_title=title, active_summary=active_sig.get("mo_summary", ""), active_entry=active_sig.get("point_of_entry", ""),
            active_tools=active_sig.get("tools_used", ""), active_target=active_sig.get("target_goods", ""),
            active_timing=active_sig.get("timing_window", ""), active_signatures=", ".join(active_sig.get("signature_traits", [])),
            reference_note=" (a SYNTHETIC demonstration record, not a real case)" if top["is_synthetic_reference"] else "",
            hist_title=top["title"], hist_jurisdiction=top["jurisdiction"], hist_date=top["fir_date"], hist_summary=top["mo_summary"],
            hist_entry=top["point_of_entry"], hist_tools=top["tools_used"], hist_target=top["target_goods"], hist_timing=top["timing_window"],
            hist_signatures=", ".join(top["signature_traits"]),
        )
        try:
            _, parsed = safe_chat_json(case_id, "You compare two cases' modus operandi from the text given. Output valid JSON.", prompt)
            data = parsed if isinstance(parsed, dict) else {}
            synthesis = {
                "verdict": sch.text(data.get("verdict"), 80) or "NOT ASSESSED",
                "matching_traits": sch.string_list(data.get("matching_traits"), limit=10),
                "divergent_factors": sch.string_list(data.get("divergent_factors"), limit=10),
                "inter_station_leads": sch.string_list(data.get("inter_station_leads"), limit=10),
                "compared_with": top["case_id"],
            }
        except LLMUnavailableError as e:
            logger.warning("Comparative synthesis unavailable: %s", e)
            synthesis = {"verdict": "NOT ASSESSED", "matching_traits": [], "divergent_factors": [], "inter_station_leads": [],
                         "note": "The language model could not be reached, so the comparison was not written. Similarity scores above are still valid."}

    computed_at = utcnow().isoformat()
    # a synthesis that could not be written is not cached, so the next visit tries again
    cacheable = synthesis is None or not synthesis.get("note")
    with get_conn() as conn:
        conn.execute(
            "UPDATE case_signatures SET matches_json = ?, synthesis_json = ?, computed_at = ? WHERE case_id = ?",
            (json.dumps(matches), json.dumps(synthesis) if cacheable else None, computed_at, case_id),
        )
        conn.commit()

    return {"status": "ok", "case_id": case_id, "active_signature": active_sig, "similar_cases": matches,
            "comparative_synthesis": synthesis, "cached": False, "computed_at": computed_at}
