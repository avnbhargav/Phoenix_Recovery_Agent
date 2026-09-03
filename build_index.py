"""
Builds the FAISS index Phoenix's RAG layer retrieves from.

Two sources get embedded:
  1. best_practices.md — chunked by section (## headers), prose reasoning
  2. decline_codes.json — each code's category + notes, turned into short
     retrievable text so the agent can also retrieve "what this specific
     code means" alongside general best-practice reasoning

Run this once (and again any time the source docs change):
    python build_index.py
"""

import json
import pickle
import re
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent
BEST_PRACTICES_PATH = BASE_DIR / "best_practices.md"
DECLINE_CODES_PATH = BASE_DIR / "decline_codes.json"
INDEX_DIR = BASE_DIR / "faiss_index"

MODEL_NAME = "all-MiniLM-L6-v2"  # small, local, no API key needed


def chunk_best_practices(path: Path) -> list[dict]:
    """Split best_practices.md into one chunk per ## section."""
    text = path.read_text()
    sections = re.split(r"\n(?=## )", text)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or section.startswith("#") and "##" not in section[:3]:
            # skip the top-level H1 intro block, keep ## sections
            if not section.startswith("## "):
                continue
        title_match = re.match(r"## (.+)", section)
        title = title_match.group(1) if title_match else "intro"
        chunks.append({
            "source": "best_practices",
            "title": title,
            "text": section,
        })
    return chunks


def chunk_decline_codes(path: Path) -> list[dict]:
    """Turn each decline code entry into a short retrievable text chunk."""
    data = json.loads(path.read_text())
    category_desc = data["_meta"]["categories"]
    chunks = []
    for entry in data["decline_codes"]:
        code = entry["code"]
        category = entry["category"]
        notes = entry.get("notes", "")
        retry_delay = entry.get("retry_delay_hours")
        text = (
            f"Decline code '{code}' falls into category '{category}': "
            f"{category_desc.get(category, '')} "
            f"{'Retry delay: ' + str(retry_delay) + ' hours.' if retry_delay is not None else 'No retry — do not attempt again automatically.'} "
            f"{notes}"
        ).strip()
        chunks.append({
            "source": "decline_codes",
            "title": code,
            "text": text,
        })
    return chunks


def main():
    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    chunks = chunk_best_practices(BEST_PRACTICES_PATH) + chunk_decline_codes(DECLINE_CODES_PATH)
    print(f"Total chunks to embed: {len(chunks)}")

    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    INDEX_DIR.mkdir(exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "index.faiss"))
    with open(INDEX_DIR / "metadata.pkl", "wb") as f:
        pickle.dump(chunks, f)

    print(f"Index built: {index.ntotal} vectors, dim={dim}")
    print(f"Saved to {INDEX_DIR}/")


if __name__ == "__main__":
    main()
