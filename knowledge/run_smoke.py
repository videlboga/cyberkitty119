"""Smoke runner: exercise ingest+query without needing a running server.

This script uses the implemented modules in-process and demonstrates the
ingest -> query flow using the mock embedding when OPENROUTER_API_KEY is not set.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from knowledge.openrouter_client import embed, generate
from knowledge.store import SimpleVectorStore


def main():
    idx = Path("/tmp/knowledge_index.json")
    if idx.exists():
        idx.unlink()
    store = SimpleVectorStore(idx)

    docs = [
        ("doc1", "Python: an interpreted, high-level programming language."),
        ("doc2", "FastAPI: a fast web framework for building APIs with Python."),
        ("doc3", "OpenRouter: proxy services for LLMs and embeddings."),
    ]
    for did, text in docs:
        emb = embed([text])[0]
        store.add(did, text, emb)
    store.save()
    print("Stored documents:", [d[0] for d in docs])

    question = "What is FastAPI?"
    q_emb = embed([question])[0]
    hits = store.query(q_emb, top_k=2)
    print("Top contexts:")
    for score, e in hits:
        print(f"score={score:.4f} id={e['id']} text={e['text']}")

    prompt = "Answer concisely using the contexts: \n" + "\n---\n".join([h[1]["text"] for h in hits]) + "\nQuestion: " + question
    answer = generate(prompt)
    print("Generated answer:", answer)


if __name__ == "__main__":
    main()
