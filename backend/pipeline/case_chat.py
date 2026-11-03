"""
Stage 2.5 — Evidence-grounded case chat. Separate from Stage 5's legal RAG:
this indexes the CASE's own observations (not the legal corpus) in their own
per-case Chroma collection, then answers investigator questions grounded
only in retrieved case evidence. Reuses legal.py's embedding model singleton
instead of loading MiniLM twice.

Identifiers are redacted before the question and retrieved text are sent to a model, and the answer is
restored locally (see llm_guard). The index is refreshed in place (new rows upserted, rows for observations
that no longer exist removed) so a chat asked while a re-index runs never sees an empty collection.
"""
import chromadb

from pipeline.legal import _get_model, CHROMA_DIR
from pipeline.evidence_guard import screen_text
from pipeline.llm_guard import case_redactor, safe_chat
from db import get_conn
from llm_client import LLMUnavailableError

_client = None

ANSWER_SYSTEM_PROMPT = """You are an evidence-grounded case assistant for
CaseWeave. Answer the investigator's question using ONLY the provided case
observations. If the evidence doesn't support an answer, say so explicitly
— do not guess or fill gaps. Cite which observation(s) support your answer
by their source_evidence_id. Keep the answer to 2-4 sentences plus
citations.

You may be given prior turns from this same conversation. Use them only to
resolve references like "it", "that time", "the other witness" — never
treat something said earlier as evidence; only the retrieved case
observations below are evidence."""


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def collection_name(case_id: str) -> str:
    return f"case_evidence_{case_id}"


def index_case_evidence(case_id: str):
    model = _get_model()
    client = _get_client()
    collection = client.get_or_create_collection(collection_name(case_id), metadata={"hnsw:space": "cosine"})

    conn = get_conn()
    rows = conn.execute(
        "SELECT observation_id, description, source_evidence_id, classification, extracted_time FROM observations WHERE case_id=?",
        (case_id,),
    ).fetchall()
    conn.close()

    # A pipeline re-run replaces every observation with new IDs, so rows for observations that no longer exist
    # must go, or the chat could still cite them.
    current = {r["observation_id"] for r in rows}
    existing = set(collection.get(include=[])["ids"])
    stale = sorted(existing - current)
    if stale:
        collection.delete(ids=stale)

    if not rows:
        return 0

    ids = [r["observation_id"] for r in rows]
    texts = [r["description"] for r in rows]
    embeddings = model.encode(texts, convert_to_numpy=True).tolist()
    metadatas = [
        {
            "source_evidence_id": r["source_evidence_id"] or "",
            "classification": r["classification"] or "unknown",
            "extracted_time": r["extracted_time"] or "",
        }
        for r in rows
    ]

    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(rows)


def drop_case_index(case_id: str) -> None:
    try:
        _get_client().delete_collection(collection_name(case_id))
    except Exception:  # noqa: BLE001 - never indexed, or already gone
        pass


def ask_case(case_id: str, question: str, history: list[dict] | None = None, top_k: int = 5):
    model = _get_model()
    client = _get_client()
    collection = client.get_or_create_collection(collection_name(case_id), metadata={"hnsw:space": "cosine"})

    if collection.count() == 0:
        index_case_evidence(case_id)
        collection = client.get_or_create_collection(collection_name(case_id), metadata={"hnsw:space": "cosine"})

    if collection.count() == 0:
        return {"answer": "No evidence has been processed for this case yet.", "sources": []}

    query_embedding = model.encode([question], convert_to_numpy=True).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=min(top_k, collection.count()))

    retrieved = []
    for doc_id, document, metadata in zip(
        results["ids"][0], results["documents"][0], results["metadatas"][0]
    ):
        retrieved.append({"observation_id": doc_id, "text": document, **metadata})

    context = "\n".join(
        f"- [{r['observation_id']}] ({r['source_evidence_id']}, time={r['extracted_time']}): {screen_text(r['text'])[0]}"
        for r in retrieved
    )
    history_text = ""
    if history:
        turns = "\n".join(f"Investigator: {h['question']}\nAssistant: {h['answer']}" for h in history[-6:])
        history_text = f"Earlier in this conversation:\n{turns}\n\n"

    prompt = f"{history_text}Question: {question}\n\nRetrieved case observations:\n{context}"

    try:
        provider, answer = safe_chat(case_id, ANSWER_SYSTEM_PROMPT, prompt, max_tokens=1024, redactor=case_redactor(case_id))
    except LLMUnavailableError as e:
        raise LLMUnavailableError(f"Case chat answer generation failed: {e}") from e

    return {"answer": answer, "sources": retrieved, "provider": provider}
