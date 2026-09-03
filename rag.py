"""
RAG retrieval layer. Loads the FAISS index built by build_index.py and
exposes a simple retrieve(query, k) function.
"""

import pickle
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent
INDEX_DIR = BASE_DIR / "faiss_index"
MODEL_NAME = "all-MiniLM-L6-v2"

_model = None
_index = None
_metadata = None


def _load():
    global _model, _index, _metadata
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
        _index = faiss.read_index(str(INDEX_DIR / "index.faiss"))
        with open(INDEX_DIR / "metadata.pkl", "rb") as f:
            _metadata = pickle.load(f)


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Return the top-k most relevant chunks for a query, with distance scores."""
    _load()
    query_vec = _model.encode([query], convert_to_numpy=True)
    distances, indices = _index.search(query_vec, k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:
            continue
        chunk = _metadata[idx]
        results.append({
            "source": chunk["source"],
            "title": chunk["title"],
            "text": chunk["text"],
            "distance": float(dist),
        })
    return results


if __name__ == "__main__":
    # quick manual test
    for q in ["card expired what should we do", "how many times to retry insufficient funds"]:
        print(f"\nQuery: {q}")
        for r in retrieve(q, k=2):
            print(f"  [{r['source']}/{r['title']}] (dist={r['distance']:.3f})")
            print(f"    {r['text'][:120]}...")
