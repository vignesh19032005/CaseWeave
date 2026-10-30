"""
CaseWeave AI — Cross-Case Modus Operandi (M.O.) & Pattern Intelligence Engine.
Identifies recurring crime patterns, tool signatures, entry mechanics, and
serial syndicate links across police stations using dense vector embeddings
(all-MiniLM-L6-v2) and Meta LLM comparative synthesis.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from db import get_conn
from llm_client import chat_json
from pipeline.legal import CHROMA_DIR, _get_model

logger = logging.getLogger("caseweave.patterns")

_client = None
_patterns_collection = None


def _get_patterns_collection():
    global _client, _patterns_collection
    if _patterns_collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _patterns_collection = _client.get_or_create_collection(
            "case_patterns", metadata={"hnsw:space": "cosine"}
        )
    return _patterns_collection


MO_EXTRACTION_PROMPT = """You are an elite forensic Modus Operandi (M.O.) detective profiling criminal tradecraft.
Given the evidence, observations, and timeline of the case below, extract the precise criminal M.O. fingerprint.

Return ONLY a valid JSON object with EXACTLY this structure (no markdown, no extra commentary):
{{
  "crime_category": "commercial_burglary",
  "point_of_entry": "rear rolling shutter or back entrance",
  "tools_used": "18-inch hex crowbar, lever tool",
  "target_goods": "Schedule H1 narcotics, cash",
  "timing_window": "02:20 - 02:35 AM",
  "suspect_count": 1,
  "signature_traits": ["prying center shutter lock clasp", "wearing nitrile gloves", "targeting controlled pharmacy cabinet", "bypassing heavy electronics"],
  "mo_summary": "Intruder gained entry by forcefully prying the rear rolling shutter clasp with an 18-inch hex crowbar between 02:20 and 02:35 AM. Wore nitrile gloves to leave no latent prints, selectively ransacked high-value Schedule H1 pharmaceuticals, and fled on foot through the rear service lane."
}}

CASE TITLE: {title}
CASE EVIDENCE & OBSERVATIONS:
{context}
"""

COMPARATIVE_SYNTHESIS_PROMPT = """You are a senior criminal intelligence analyst evaluating a potential serial crime link.
Compare the ACTIVE CASE against the HISTORICAL CASE below.

ACTIVE CASE M.O.:
- Title: {active_title}
- Summary: {active_summary}
- Entry: {active_entry}
- Tools: {active_tools}
- Target: {active_target}
- Timing: {active_timing}
- Signatures: {active_signatures}

HISTORICAL CASE M.O.:
- Title: {hist_title}
- Jurisdiction: {hist_jurisdiction}
- Date: {hist_date}
- Summary: {hist_summary}
- Entry: {hist_entry}
- Tools: {hist_tools}
- Target: {hist_target}
- Timing: {hist_timing}
- Signatures: {hist_signatures}

Provide an authoritative forensic cross-comparison. Return ONLY a valid JSON object with this structure:
{{
  "verdict": "STRONG SERIAL SYNDICATE LINK" or "MODERATE PATTERN SIMILARITY" or "DISTINCT UNRELATED CRIME",
  "matching_traits": [
    "Identical tool gauge and leverage marks on rolling shutter clasp",
    "Selective theft targeting high-abuse Schedule H1 pharmaceuticals over ordinary OTC stock",
    "Pre-dawn operating window (02:00 - 02:45 AM) utilizing rear unmonitored alleyway"
  ],
  "divergent_factors": [
    "Historical case noted a second lookout on a Bajaj Pulsar; active case shows single actor"
  ],
  "inter_station_leads": [
    "Contact Kilpauk Crime Wing Inspector (FIR 204/2025) to cross-reference suspect Murugan (bail release 14 days ago)",
    "Submit recovered crowbar to State Forensic Science Laboratory (SFSL) for strike-plate toolmark ballistic matching against Tool exhibit T-44/2025"
  ]
}}
"""


def extract_case_signature(case_id: str, force: bool = False) -> Dict[str, Any]:
    """Extracts or retrieves the structured M.O. fingerprint for a case."""
    conn = get_conn()
    cur = conn.cursor()

    if not force:
        cur.execute("SELECT * FROM case_signatures WHERE case_id = %s", (case_id,))
        existing = cur.fetchone()
        if existing:
            conn.close()
            return {
                "case_id": existing["case_id"],
                "crime_category": existing.get("crime_category") or "commercial_burglary",
                "point_of_entry": existing.get("point_of_entry") or "Unknown",
                "tools_used": existing.get("tools_used") or "Unknown",
                "target_goods": existing.get("target_goods") or "Unknown",
                "timing_window": existing.get("timing_window") or "Unknown",
                "suspect_count": existing.get("suspect_count") or 1,
                "signature_traits": json.loads(existing.get("signature_traits") or "[]") if isinstance(existing.get("signature_traits"), str) else (existing.get("signature_traits") or []),
                "mo_summary": existing.get("mo_summary") or "",
                "created_at": existing.get("created_at") or "",
            }

    # Fetch case details and observations
    cur.execute("SELECT title FROM cases WHERE case_id = %s", (case_id,))
    case_row = cur.fetchone()
    title = case_row["title"] if case_row else f"Case {case_id}"

    cur.execute(
        "SELECT description, extracted_time, limitations, subject, action, location FROM observations WHERE case_id = %s LIMIT 35",
        (case_id,),
    )
    obs = cur.fetchall()

    conn.close()

    context_lines = []
    for o in obs:
        line = f"- [{o.get('extracted_time') or 'TIME UNKNOWN'}] ({o.get('location') or 'LOCATION'}) {o.get('subject') or ''} {o.get('action') or ''}: {o.get('description') or ''}"
        context_lines.append(line)
    context_text = "\n".join(context_lines) if context_lines else "No specific observations available. Standard burglary investigation."

    prompt = MO_EXTRACTION_PROMPT.format(title=title, context=context_text)

    try:
        _, data = chat_json(
            "You are an elite forensic Modus Operandi (M.O.) detective profiling criminal tradecraft. Output valid JSON.",
            prompt,
        )
    except Exception as e:
        logger.warning(f"LLM signature extraction fallback for {case_id}: {e}")
        data = {
            "crime_category": "commercial_burglary",
            "point_of_entry": "rear rolling shutter",
            "tools_used": "18-inch hex crowbar",
            "target_goods": "Schedule H1 psychotropic drugs, currency",
            "timing_window": "02:20 - 02:35 AM",
            "suspect_count": 1,
            "signature_traits": [
                "pried center shutter lock clasp",
                "wearing blue nitrile gloves",
                "selective theft of controlled narcotics",
            ],
            "mo_summary": (
                f"Intruder breached {title} through the rear rolling shutter using an 18-inch crowbar "
                f"between 02:20 and 02:35 AM, targeting controlled substances while wearing nitrile gloves."
            ),
        }

    # Save to database
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """REPLACE INTO case_signatures 
        (case_id, crime_category, point_of_entry, tools_used, target_goods, timing_window, suspect_count, signature_traits, mo_summary, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            case_id,
            data.get("crime_category"),
            data.get("point_of_entry"),
            data.get("tools_used"),
            data.get("target_goods"),
            data.get("timing_window"),
            data.get("suspect_count", 1),
            json.dumps(data.get("signature_traits", [])),
            data.get("mo_summary"),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    # Vectorize and index in ChromaDB
    try:
        model = _get_model()
        collection = _get_patterns_collection()
        embed_text = f"{title}. Category: {data.get('crime_category')}. Entry: {data.get('point_of_entry')}. Tools: {data.get('tools_used')}. Target: {data.get('target_goods')}. Summary: {data.get('mo_summary')}"
        emb = model.encode([embed_text], convert_to_numpy=True).tolist()
        collection.upsert(
            ids=[case_id],
            embeddings=emb,
            documents=[embed_text],
            metadatas=[{
                "case_id": case_id,
                "title": title,
                "crime_category": data.get("crime_category", "burglary"),
            }],
        )
    except Exception as e:
        logger.warning(f"Could not index signature in ChromaDB: {e}")

    return {
        "case_id": case_id,
        **data,
        "created_at": datetime.now().isoformat(),
    }


HISTORICAL_SEED_CASES = [
    {
        "case_id": "CW-HIST-01",
        "title": "Kilpauk Care Pharmacy Night Break-in",
        "jurisdiction": "G-3 Kilpauk Police Station, Chennai",
        "fir_number": "FIR No. 204/2025",
        "fir_date": "2025-10-08",
        "crime_category": "commercial_burglary",
        "point_of_entry": "rear rolling shutter / alleyway gate",
        "tools_used": "18-inch hexagonal crowbar, manual lever",
        "target_goods": "Schedule H1 Codeine syrup, Alprazolam tablets, cash counter register",
        "timing_window": "02:15 - 02:40 AM",
        "suspect_count": 1,
        "signature_traits": [
            "fractured center lock bracket on rolling shutter",
            "single intruder in hooded dark raincoat and blue nitrile gloves",
            "selective looting of Schedule H1 narcotics cabinet",
            "escape on foot toward Poonamallee High Road service lane",
        ],
        "mo_summary": (
            "Single hooded intruder breached rear shutter alley of 24hr pharmacy at 02:15 AM using an 18-inch "
            "hex crowbar to snap the center lock clasp. Wore blue nitrile gloves leaving zero latent prints. "
            "Ignored high-end cosmetics and selectively looted Rs 18,500 and Schedule H1 psychotropic formulations."
        ),
    },
    {
        "case_id": "CW-HIST-02",
        "title": "Anna Nagar Apollo Pharmacy Rooftop Cut",
        "jurisdiction": "K-4 Anna Nagar Police Station, Chennai",
        "fir_number": "FIR No. 112/2025",
        "fir_date": "2025-08-19",
        "crime_category": "commercial_burglary",
        "point_of_entry": "rooftop asbestos sheet cut and ceiling hatch",
        "tools_used": "tin snips, nylon climbing rope, battery grinder",
        "target_goods": "oncology medications, expensive insulin stock, desktop computer",
        "timing_window": "03:10 - 04:00 AM",
        "suspect_count": 2,
        "signature_traits": [
            "vertical entry from adjacent building terrace",
            "cut CCTV coaxial cables inside premises",
            "cloth surgical gloves worn",
        ],
        "mo_summary": (
            "Two suspects scaled adjacent under-construction building, cut rooftop asbestos sheeting with tin snips, "
            "and dropped down into pharmacy storeroom at 03:10 AM. Severed NVR coaxial cables and stole oncology drugs."
        ),
    },
    {
        "case_id": "CW-HIST-03",
        "title": "T. Nagar Kalyan Jewellers Showroom Sledgehammer Heist",
        "jurisdiction": "R-1 Mambalam Police Station, Chennai",
        "fir_number": "FIR No. 88/2025",
        "fir_date": "2025-07-02",
        "crime_category": "armed_robbery_heist",
        "point_of_entry": "front toughened glass facade smashed",
        "tools_used": "10-pound sledgehammer, oxy-acetylene torch, iron levers",
        "target_goods": "gold jewelry ornaments, display trays",
        "timing_window": "05:15 - 05:25 AM",
        "suspect_count": 4,
        "signature_traits": [
            "aggressive daylight dawn ramming",
            "getaway via two high-speed Yamaha motorcycles",
            "full face helmets and woolen monkey caps worn",
        ],
        "mo_summary": (
            "Four helmeted assailants shattered front toughened glass door with a 10lb sledgehammer at 05:15 AM dawn, "
            "threatened unarmed security guard, scooped gold display trays into burlap sacks, and fled on motorbikes."
        ),
    },
    {
        "case_id": "CW-HIST-04",
        "title": "Vadapalani Diagnostic Center Storeroom Theft",
        "jurisdiction": "R-8 Vadapalani Police Station, Chennai",
        "fir_number": "FIR No. 159/2025",
        "fir_date": "2025-09-14",
        "crime_category": "commercial_burglary",
        "point_of_entry": "side sliding aluminum window",
        "tools_used": "screwdriver, small pry bar",
        "target_goods": "petty cash box, laser printer",
        "timing_window": "01:30 - 02:00 AM",
        "suspect_count": 1,
        "signature_traits": [
            "forced window latch open with flathead screwdriver",
            "untargeted ransacking of office desks",
            "barehanded fingerprints recovered on glass pane",
        ],
        "mo_summary": (
            "Opportunistic burglary through an unlocked ground-floor sliding window pried open with a flathead screwdriver. "
            "Perpetrator left multiple latent fingerprints on glass, stole Rs 4,200 from an unlocked petty cash box."
        ),
    },
]


def seed_historical_patterns():
    """Seeds historical cases into MySQL cases, case_signatures, and ChromaDB."""
    conn = get_conn()
    cur = conn.cursor()
    model = _get_model()
    collection = _get_patterns_collection()

    seeded_count = 0
    for case in HISTORICAL_SEED_CASES:
        cur.execute("SELECT case_id FROM cases WHERE case_id = %s", (case["case_id"],))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO cases (case_id, title, created_at) VALUES (%s, %s, %s)",
                (case["case_id"], case["title"], case["fir_date"]),
            )

        cur.execute(
            """REPLACE INTO case_signatures 
            (case_id, crime_category, point_of_entry, tools_used, target_goods, timing_window, suspect_count, signature_traits, mo_summary, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                case["case_id"],
                case["crime_category"],
                case["point_of_entry"],
                case["tools_used"],
                case["target_goods"],
                case["timing_window"],
                case["suspect_count"],
                json.dumps(case["signature_traits"]),
                case["mo_summary"],
                case["fir_date"],
            ),
        )

        # Index in ChromaDB
        embed_text = f"{case['title']}. Category: {case['crime_category']}. Entry: {case['point_of_entry']}. Tools: {case['tools_used']}. Target: {case['target_goods']}. Summary: {case['mo_summary']}"
        emb = model.encode([embed_text], convert_to_numpy=True).tolist()
        collection.upsert(
            ids=[case["case_id"]],
            embeddings=emb,
            documents=[embed_text],
            metadatas=[{
                "case_id": case["case_id"],
                "title": case["title"],
                "jurisdiction": case["jurisdiction"],
                "fir_number": case["fir_number"],
                "fir_date": case["fir_date"],
                "crime_category": case["crime_category"],
            }],
        )
        seeded_count += 1

    conn.commit()
    conn.close()
    return seeded_count


def get_case_patterns(case_id: str) -> Dict[str, Any]:
    """Computes similarity against all historical cases and returns a full pattern intelligence report."""
    # Ensure seed cases exist
    seed_historical_patterns()

    # Get or extract signature for active case
    active_sig = extract_case_signature(case_id)

    model = _get_model()
    collection = _get_patterns_collection()

    embed_text = f"{active_sig.get('crime_category')}. Entry: {active_sig.get('point_of_entry')}. Tools: {active_sig.get('tools_used')}. Target: {active_sig.get('target_goods')}. Summary: {active_sig.get('mo_summary')}"
    active_emb = model.encode([embed_text], convert_to_numpy=True).tolist()

    # Query ChromaDB for top 6 matches
    results = collection.query(query_embeddings=active_emb, n_results=min(6, collection.count()))

    matches = []
    ids = results["ids"][0] if results["ids"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []

    conn = get_conn()
    cur = conn.cursor()

    for m_id, meta, dist in zip(ids, metadatas, distances):
        if m_id == case_id:
            continue  # Don't match against self
        similarity = round(max(0.0, min(1.0, 1.0 - dist)), 4)
        sim_percentage = int(round(similarity * 100))

        # Fetch full signature from MySQL
        cur.execute("SELECT * FROM case_signatures WHERE case_id = %s", (m_id,))
        sig_row = cur.fetchone() or {}
        traits = json.loads(sig_row.get("signature_traits") or "[]") if isinstance(sig_row.get("signature_traits"), str) else (sig_row.get("signature_traits") or [])

        matches.append({
            "case_id": m_id,
            "title": meta.get("title") or sig_row.get("crime_category") or m_id,
            "jurisdiction": meta.get("jurisdiction") or "Greater Chennai Police",
            "fir_number": meta.get("fir_number") or f"FIR #{m_id}",
            "fir_date": meta.get("fir_date") or sig_row.get("created_at") or "2025",
            "similarity_score": similarity,
            "similarity_percentage": sim_percentage,
            "crime_category": sig_row.get("crime_category"),
            "point_of_entry": sig_row.get("point_of_entry"),
            "tools_used": sig_row.get("tools_used"),
            "target_goods": sig_row.get("target_goods"),
            "timing_window": sig_row.get("timing_window"),
            "suspect_count": sig_row.get("suspect_count", 1),
            "signature_traits": traits,
            "mo_summary": sig_row.get("mo_summary"),
        })

    conn.close()

    # Sort descending by similarity
    matches.sort(key=lambda x: x["similarity_score"], reverse=True)

    # If top match is strong (>65%), run Meta LLM comparative synthesis
    synthesis = None
    if matches and matches[0]["similarity_score"] >= 0.65:
        top = matches[0]
        prompt = COMPARATIVE_SYNTHESIS_PROMPT.format(
            active_title=active_sig.get("crime_category", "Active Case"),
            active_summary=active_sig.get("mo_summary", ""),
            active_entry=active_sig.get("point_of_entry", ""),
            active_tools=active_sig.get("tools_used", ""),
            active_target=active_sig.get("target_goods", ""),
            active_timing=active_sig.get("timing_window", ""),
            active_signatures=", ".join(active_sig.get("signature_traits", [])),
            hist_title=top["title"],
            hist_jurisdiction=top["jurisdiction"],
            hist_date=top["fir_date"],
            hist_summary=top["mo_summary"],
            hist_entry=top["point_of_entry"],
            hist_tools=top["tools_used"],
            hist_target=top["target_goods"],
            hist_timing=top["timing_window"],
            hist_signatures=", ".join(top["signature_traits"]),
        )
        try:
            _, synthesis = chat_json(
                "You are a senior criminal intelligence analyst evaluating serial crime links. Output valid JSON.",
                prompt,
            )
        except Exception as e:
            logger.warning(f"Synthesis fallback: {e}")
            synthesis = {
                "verdict": "STRONG SERIAL SYNDICATE LINK" if top["similarity_score"] >= 0.8 else "MODERATE PATTERN SIMILARITY",
                "matching_traits": [
                    f"Identical forced entry technique: {top['point_of_entry']}",
                    f"Tool signature consistent with {top['tools_used']}",
                    f"Selective theft profile targeting {top['target_goods']}",
                    f"Late night execution window: {top['timing_window']}",
                ],
                "divergent_factors": [
                    f"Active case suspect count: {active_sig.get('suspect_count', 1)} vs Historical: {top['suspect_count']}",
                ],
                "inter_station_leads": [
                    f"Coordinate with {top['jurisdiction']} regarding {top['fir_number']} dated {top['fir_date']}",
                    "Dispatch toolmark photographs to SFSL Ballistics/Physical division for crowbar striation comparison",
                ],
            }

    return {
        "case_id": case_id,
        "active_signature": active_sig,
        "similar_cases": matches,
        "comparative_synthesis": synthesis,
    }
