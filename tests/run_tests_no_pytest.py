import os
import sys
import math
import importlib
from pathlib import Path
import asyncio


def assert_ok(cond, msg="assertion failed"):
    if not cond:
        print(msg)
        raise AssertionError(msg)


def test_openrouter_client():
    os.environ.pop("OPENROUTER_API_KEY", None)
    mod = importlib.import_module("knowledge.openrouter_client")
    importlib.reload(mod)
    texts = ["hello world", "another text"]
    embs = mod.embed(texts)
    assert_ok(isinstance(embs, list) and len(embs) == 2, "embed returned wrong shape")
    for v in embs:
        assert_ok(len(v) > 0, "empty embedding")
        norm = math.sqrt(sum(x * x for x in v))
        assert_ok(abs(norm - 1.0) < 1e-6, f"embedding not normalized: {norm}")
    ans = mod.generate("Test prompt")
    assert_ok(isinstance(ans, str) and ans.startswith("[mock answer]"), "generate mock failed")
    print("test_openrouter_client: OK")


def test_store(tmpdir: Path):
    mod = importlib.import_module("knowledge.store")
    idx = tmpdir / "idx.json"
    store = mod.SimpleVectorStore(idx)
    e1 = [1.0, 0.0, 0.0]
    e2 = [0.0, 1.0, 0.0]
    store.add("a", "doc A", e1)
    store.add("b", "doc B", e2)
    store.save()
    s2 = mod.SimpleVectorStore(idx)
    assert_ok(len(s2.entries) == 2, "store load failed")
    hits = s2.query([1.0, 0.0, 0.0], top_k=1)
    assert_ok(len(hits) == 1 and hits[0][1]["id"] == "a", "query returned wrong best hit")
    print("test_store: OK")


def test_ingest_query(tmpdir: Path):
    os.environ.pop("OPENROUTER_API_KEY", None)
    importlib.reload(importlib.import_module("knowledge.openrouter_client"))
    ing = importlib.import_module("knowledge.ingest_service")
    qry = importlib.import_module("knowledge.query_service")
    from knowledge.store import SimpleVectorStore
    tmp_index = tmpdir / "index.json"
    tmp_store = SimpleVectorStore(tmp_index)
    # monkeypatch module-level stores
    ing.store = tmp_store
    qry.store = tmp_store

    async def run_flow():
        req = type("R", (), {"text": "FastAPI is a Python framework.", "id": None})
        res = await ing.ingest(req)
        assert_ok(res.get("status") == "stored", "ingest did not store")
        qreq = type("Q", (), {"question": "What is FastAPI?", "top_k": 2, "use_llm": False})
        resp = await qry.query(qreq)
        assert_ok("contexts" in resp and len(resp["contexts"]) >= 1, "query returned no contexts")

    asyncio.run(run_flow())
    print("test_ingest_query: OK")


def main():
    root = Path(__file__).parent
    tmp = Path("/tmp/py_tests_knowledge")
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    test_openrouter_client()
    test_store(tmp)
    test_ingest_query(tmp)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("TESTS FAILED:", e)
        sys.exit(1)
    sys.exit(0)
