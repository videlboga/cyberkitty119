import importlib
from pathlib import Path


def test_store_add_save_load(tmp_path):
    mod = importlib.import_module("knowledge.store")
    Path(tmp_path / "idx.json")  # ensure path exists
    store = mod.SimpleVectorStore(Path(tmp_path / "idx.json"))

    # minimal embeddings
    e1 = [1.0, 0.0, 0.0]
    e2 = [0.0, 1.0, 0.0]
    store.add("a", "doc A", e1)
    store.add("b", "doc B", e2)
    store.save()

    s2 = mod.SimpleVectorStore(Path(tmp_path / "idx.json"))
    assert len(s2.entries) == 2

    # Query near e1
    hits = s2.query([1.0, 0.0, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0][1]["id"] == "a"
