"""
Stage 5 — Legal Retrieval Engine. Real embeddings (sentence-transformers,
all-MiniLM-L6-v2) + real local vector store (ChromaDB, persisted to disk).
Replaces the earlier keyword-overlap placeholder.
"""
import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CORPUS_DIR = Path(__file__).parent.parent / "legal_corpus"
CHROMA_DIR = Path(__file__).parent.parent / "chroma_store"

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


def index_corpus():
    """(Re)embeds every document in legal_corpus/ and upserts into the local
    Chroma store. Idempotent — safe to call every run; upsert overwrites by id."""
    model = _get_model()
    collection = _get_collection()

    docs = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        docs.append(json.loads(path.read_text(encoding="utf-8")))

    ids = [d["id"] for d in docs]
    texts = [f"{d['title']}. {d['topic']}. {d['text']}" for d in docs]
    embeddings = model.encode(texts, convert_to_numpy=True).tolist()
    metadatas = [
        {"title": d["title"], "source_url": d.get("source_url") or "", "type": d["type"]}
        for d in docs
    ]

    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(docs)


def search_legal_corpus(query: str, top_k: int = 3):
    model = _get_model()
    collection = _get_collection()

    if collection.count() == 0:
        index_corpus()

    query_embedding = model.encode([query], convert_to_numpy=True).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)

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
