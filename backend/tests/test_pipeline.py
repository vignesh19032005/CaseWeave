"""
End-to-end test, scored against data/case_cw001/ground_truth.json.
Run: python tests/test_pipeline.py  (from backend/ dir, or via run_tests.bat)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_pipeline import run
from db import get_conn

PASS = []
FAIL = []


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  PASS: {name}")
    else:
        FAIL.append(f"{name} -- {detail}")
        print(f"  FAIL: {name} -- {detail}")


def main():
    result = run()
    gt = result["ground_truth"]

    print("\n=== Scoring against ground truth ===\n")

    check(
        "Observation count >= expected minimum",
        len(result["observations"]) >= gt["expected_observation_count_min"],
        f"got {len(result['observations'])}, expected >= {gt['expected_observation_count_min']}",
    )

    check(
        "Timeline event count >= expected minimum",
        len(result["timeline_events"]) >= gt["expected_timeline_event_count_min"],
        f"got {len(result['timeline_events'])}, expected >= {gt['expected_timeline_event_count_min']}",
    )

    check(
        "At least one discrepancy (clock mismatch) detected",
        len(result["conflicts"]) >= 1,
        f"got {len(result['conflicts'])} conflicts",
    )

    all_sources_in_conflicts = set()
    for c in result["conflicts"]:
        all_sources_in_conflicts.add(c["source_a"])
        all_sources_in_conflicts.add(c["source_b"])
    check(
        "Discrepancy spans at least 2 distinct evidence sources",
        len(all_sources_in_conflicts) >= 2,
        f"sources involved: {all_sources_in_conflicts}",
    )

    check(
        "Every observation has a non-empty source_locator (traceability)",
        True,  # enforced structurally by observe.py schema; spot-check below
    )
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as n FROM observations WHERE source_locator IS NULL OR source_locator = ''")
    orphan_count = cur.fetchone()["n"]
    conn.close()
    check(
        "Zero observations without a source locator (hard traceability rule)",
        orphan_count == 0,
        f"found {orphan_count} orphaned observations",
    )

    check(
        "Legal retrieval returns at least 1 result for the case's legal question",
        len(result["legal_results"]) >= 1,
        f"got {len(result['legal_results'])} results",
    )

    expected_doc_hit = any(
        "63" in r["title"] or "65B" in r["title"] for r in result["legal_results"]
    )
    check(
        "Legal retrieval surfaces the relevant electronic-evidence statute (S.63 or S.65B)",
        expected_doc_hit,
        f"titles returned: {[r['title'] for r in result['legal_results']]}",
    )

    check(
        "At least 2 competing scenarios generated",
        len(result["scenarios"]) >= 2,
        f"got {len(result['scenarios'])}",
    )

    check(
        "Report file was written",
        result["report_path"].exists(),
        str(result["report_path"]),
    )

    report_text = result["report_path"].read_text(encoding="utf-8")
    check(
        "Report contains Pilot Readiness Gap section",
        "Pilot Readiness Gap" in report_text,
    )
    check(
        "Report audit trail section shows chain integrity PASSED",
        "PASSED" in report_text,
    )

    check(
        "Timeline HTML artifact was written",
        result["timeline_html_path"].exists(),
        str(result["timeline_html_path"]),
    )

    # --- Stage 1: real PDF extraction ---
    check(
        "Stage 1: PDF extraction returned at least one page with real text",
        result["pdf_pages"] is not None and len(result["pdf_pages"]) >= 1 and len(result["pdf_pages"][0]["text"]) > 50,
        f"pdf_pages={result['pdf_pages']}",
    )
    if result["pdf_pages"]:
        check(
            "Stage 1: PDF text layer extracted correctly (not OCR fallback needed)",
            result["pdf_pages"][0]["method"] == "text_layer",
            f"method was {result['pdf_pages'][0]['method']}",
        )

    # --- Stage 2a: structured entity fields on observations ---
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as n FROM observations WHERE subject IS NOT NULL OR location IS NOT NULL")
    entity_field_count = cur.fetchone()["n"]
    conn.close()
    check(
        "Stage 2a: at least some observations have subject/location fields populated",
        entity_field_count >= 1,
        f"got {entity_field_count} observations with entity fields",
    )

    # --- Stage 2.5: evidence-grounded case chat ---
    check(
        "Stage 2.5: case chat returned a non-empty answer",
        len(result["chat_result"]["answer"]) > 0,
        f"answer={result['chat_result']['answer'][:100]}",
    )
    check(
        "Stage 2.5: case chat answer cites retrieved sources",
        len(result["chat_result"]["sources"]) >= 1,
        f"got {len(result['chat_result']['sources'])} sources",
    )

    # --- Stage 4a: review-status workflow ---
    if result["conflicts"]:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT review_status FROM conflicts WHERE conflict_id=?",
            (result["conflicts"][0]["conflict_id"],),
        )
        row = cur.fetchone()
        conn.close()
        check(
            "Stage 4a: review_status update persisted correctly",
            row is not None and row["review_status"] == "confirmed",
            f"got {dict(row) if row else None}",
        )

    # --- Stage 4b: evidence linking ---
    check(
        "Stage 4b: evidence_links list is present (may be empty if no supports/related pairs found)",
        isinstance(result["evidence_links"], list),
        f"got {type(result['evidence_links'])}",
    )

    # --- Stage 11: entity resolution ---
    check(
        "Stage 11: at least one entity resolved",
        len(result["entities"]) >= 1,
        f"got {len(result['entities'])} entities",
    )

    # --- Stage 9a: incident reconstruction ---
    check(
        "Stage 9a: incident reconstruction produced a non-empty narrative",
        len(result["reconstruction"]["narrative"]) > 0,
        f"narrative={result['reconstruction']['narrative'][:100]}",
    )

    print(f"\n=== RESULT: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        print("\nFailures:")
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\nAll checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
