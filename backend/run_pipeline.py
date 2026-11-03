"""End-to-end orchestrator: Stage 0 -> Stage 12, for case CW-001. Run: python run_pipeline.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db import reset_db
from pipeline.ingest import ingest_case
from pipeline.observe import run_observation_engine
from pipeline.timeline import build_timeline
from pipeline.discrepancy import detect_discrepancies, update_review_status
from pipeline.legal import search_legal_corpus
from pipeline.scenarios import generate_scenarios
from pipeline.report import generate_report
from pipeline.report_pdf import generate_report_pdf
from pipeline.timeline_html import render_timeline_html
from pipeline.entities import resolve_entities
from pipeline.case_chat import index_case_evidence, ask_case
from pipeline.incident_reconstruction import reconstruct_incident
from pipeline.extract import extract_pdf

CASE_ID = "CW-001"
DATA_DIR = Path(__file__).parent / "data" / "case_cw001"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.json"


def run():
    # This demo rebuilds CW-001 from scratch. It resets the whole database first, which reset_db() only allows on a
    # database whose name contains "test" and with CASEWEAVE_ALLOW_DB_RESET=1 (see db.reset_db).
    reset_db()
    print(f"=== CaseWeave Pipeline — {CASE_ID} ===\n")

    print("[Stage 0] Ingesting case + evidence...")
    evidence_items = ingest_case(CASE_ID, "Warehouse Incident", DATA_DIR)
    print(f"  -> {len(evidence_items)} evidence items ingested, hashed, logged.\n")

    print("[Stage 1] Testing PDF extraction on a real PDF (forensic_report.pdf)...")
    pdf_path = DATA_DIR / "forensic_report.pdf"
    pdf_pages = None
    if pdf_path.exists():
        pdf_pages = extract_pdf(pdf_path)
        for p in pdf_pages:
            print(f"     page {p['page_number']} [{p['method']}]: {p['text'][:80]}")
    else:
        print("     (forensic_report.pdf not found, skipping)")
    print()

    print("[Stage 1-2] Extracting observations (live LLM call: Meta -> Groq -> Gemini fallback)...")
    observations = run_observation_engine(CASE_ID, evidence_items)
    print(f"  -> {len(observations)} observations extracted.\n")

    print("[Stage 3] Building timeline...")
    timeline_events = build_timeline(CASE_ID)
    print(f"  -> {len(timeline_events)} timed events placed on timeline.\n")
    for e in timeline_events:
        print(f"     {e['time']} [{e['classification']}] {e['description'][:70]}")
    print()

    print("[Stage 11] Resolving entities + relationships (now runs before Stage 4 — its output grounds the debate)...")
    entity_result = resolve_entities(CASE_ID)
    print(f"  -> {len(entity_result['entities'])} entities, {len(entity_result['relationships'])} relationships.\n")
    for e in entity_result["entities"]:
        print(f"     {e['canonical_name']} ({e['entity_type']}) aliases={e['aliases']}")
    print()

    print("[Stage 4 / 4a / 4b] Detecting discrepancies via 3-agent debate (Prosecutor/Defender/Judge) + evidence links...")
    conflicts, evidence_links = detect_discrepancies(CASE_ID, timeline_events, live=True)
    print(f"  -> {len(conflicts)} conflict(s), {len(evidence_links)} evidence link(s).\n")
    for c in conflicts:
        print(f"     CONFLICT: {c['time_a']} vs {c['time_b']} — {c.get('nature_of_conflict', '')[:80]}")
    for l in evidence_links:
        print(f"     {l['link_type'].upper()}: {l['claim_a'][:40]} <-> {l['claim_b'][:40]}")

    if conflicts:
        print(f"  [4a] Marking conflict {conflicts[0]['conflict_id']} as 'confirmed'...")
        update_review_status(
            CASE_ID,
            conflicts[0]["conflict_id"],
            "confirmed",
            reason="Verified against physical log disparity during testing",
            actor_username="test_runner",
            actor_role="reviewer",
        )
    print()

    print("[Stage 5] Legal retrieval...")
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    legal_query = ground_truth["legal_question_for_rag_test"]
    print(f"  Query: {legal_query}")
    legal_results = search_legal_corpus(legal_query)
    print(f"  -> {len(legal_results)} result(s).\n")
    for r in legal_results:
        print(f"     {r['title']} (similarity={r['similarity_score']})")
    print()

    print("[Stage 2.5] Indexing + querying case evidence chat...")
    index_case_evidence(CASE_ID)
    chat_result = ask_case(CASE_ID, "What time did the side door open, according to the access log?")
    print(f"  Q: What time did the side door open, according to the access log?")
    print(f"  A: {chat_result['answer'][:200]}\n")

    print("[Stage 9] Generating scenarios...")
    scenarios = generate_scenarios(conflicts)
    print(f"  -> {len(scenarios)} scenario(s) generated.\n")

    print("[Stage 9a] Synthesizing incident reconstruction...")
    reconstruction = reconstruct_incident(
        CASE_ID, timeline_events, entity_result["entities"], entity_result["relationships"], conflicts, evidence_links
    )
    print(f"  Narrative: {reconstruction['narrative'][:300]}")
    print(f"  Unresolved gaps: {reconstruction['unresolved_gaps']}\n")

    print("[Stage 10] Exporting report...")
    out_path = Path(__file__).parent / "output_report_CW-001.md"
    generate_report(CASE_ID, timeline_events, conflicts, scenarios, legal_results, out_path, reconstruction)
    print(f"  -> Report written to {out_path}\n")

    pdf_path = Path(__file__).parent / "output_report_CW-001.pdf"
    generate_report_pdf(CASE_ID, timeline_events, conflicts, scenarios, legal_results, pdf_path, reconstruction)
    print(f"  -> PDF report written to {pdf_path}\n")

    print("[Stage 3] Rendering viewable timeline artifact...")
    html_path = Path(__file__).parent / "timeline_CW-001.html"
    render_timeline_html(CASE_ID, "Warehouse Incident", timeline_events, conflicts, html_path)
    print(f"  -> Timeline page written to {html_path}\n")

    return {
        "evidence_items": evidence_items,
        "pdf_pages": pdf_pages,
        "observations": observations,
        "timeline_events": timeline_events,
        "conflicts": conflicts,
        "evidence_links": evidence_links,
        "legal_results": legal_results,
        "scenarios": scenarios,
        "entities": entity_result["entities"],
        "relationships": entity_result["relationships"],
        "reconstruction": reconstruction,
        "chat_result": chat_result,
        "ground_truth": ground_truth,
        "report_path": out_path,
        "timeline_html_path": html_path,
    }


if __name__ == "__main__":
    run()
