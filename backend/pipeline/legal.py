"""
Stage 5 — Legal Retrieval Engine. Real embeddings (sentence-transformers,
all-MiniLM-L6-v2) + real local vector store (ChromaDB, persisted to disk).
Replaces the earlier keyword-overlap placeholder.

The index follows the files in legal_corpus/: a fingerprint of their contents is stored with the collection,
so editing a statute's text (not only adding or removing one) triggers a re-index on the next search.
"""
import hashlib
import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CORPUS_DIR = Path(__file__).parent.parent / "legal_corpus"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_store"
FINGERPRINT_FILE = CHROMA_DIR / "legal_corpus.fingerprint"

_model = None
_client = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            "legal_corpus", metadata={"hnsw:space": "cosine"}
        )
    return _collection


def corpus_fingerprint() -> str:
    h = hashlib.sha256()
    for path in sorted(CORPUS_DIR.glob("*.json")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _load_docs() -> list:
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        docs.append(json.loads(path.read_text(encoding="utf-8")))
    return docs


def index_corpus():
    """(Re)embeds every document in legal_corpus/ and upserts into the local
    Chroma store. Idempotent — safe to call every run; upsert overwrites by id, and entries whose file was
    removed are deleted."""
    model = _get_model()
    collection = _get_collection()

    docs = _load_docs()
    ids = [d["id"] for d in docs]
    stale = sorted(set(collection.get(include=[])["ids"]) - set(ids))
    if stale:
        collection.delete(ids=stale)
    texts = [f"{d['title']}. {d['topic']}. {d['text']}" for d in docs]
    embeddings = model.encode(texts, convert_to_numpy=True).tolist()
    metadatas = [
        {"title": d["title"], "source_url": d.get("source_url") or "", "type": d["type"]}
        for d in docs
    ]

    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    FINGERPRINT_FILE.parent.mkdir(exist_ok=True)
    FINGERPRINT_FILE.write_text(corpus_fingerprint(), encoding="utf-8")
    return len(docs)


def ensure_index_current():
    collection = _get_collection()
    stored = FINGERPRINT_FILE.read_text(encoding="utf-8") if FINGERPRINT_FILE.exists() else ""
    if collection.count() == 0 or stored != corpus_fingerprint():
        index_corpus()


def search_legal_corpus(query: str, top_k: int = 3):
    model = _get_model()
    ensure_index_current()
    collection = _get_collection()

    query_embedding = model.encode([query], convert_to_numpy=True).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=min(top_k, collection.count()))

    output = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        similarity = 1 - distance  # chroma returns cosine distance by default config here
        output.append(
            {
                "id": doc_id,
                "title": metadata["title"],
                "source_url": metadata["source_url"] or None,
                "similarity_score": round(similarity, 4),
                "passage": document,
            }
        )
    return output
