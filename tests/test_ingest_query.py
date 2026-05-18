import importlib
import asyncio
from pathlib import Path


def test_ingest_and_query_integration(tmp_path, monkeypatch):
    # Ensure mock embeddings
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    openmod = importlib.import_module("knowledge.openrouter_client")
    importlib.reload(openmod)

    ing = importlib.import_module("knowledge.ingest_service")
    qry = importlib.import_module("knowledge.query_service")

    # Replace module-level stores with temp ones
    tmp_index = Path(tmp_path / "index.json")
    from knowledge.store import SimpleVectorStore
    tmp_store = SimpleVectorStore(tmp_index)
    ing.store = tmp_store
    qry.store = tmp_store

    async def run_flow():
        # Ingest a document
        req = type("R", (), {"text": "FastAPI is a Python web framework.", "id": None})
        res = await ing.ingest(req)
        assert res.get("status") == "stored"

        # Query
        qreq = type("Q", (), {"question": "What is FastAPI?", "top_k": 2, "use_llm": False})
        resp = await qry.query(qreq)
        assert "contexts" in resp
        assert len(resp["contexts"]) >= 1

    asyncio.run(run_flow())
