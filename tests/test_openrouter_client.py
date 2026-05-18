import os
import math
import importlib

import pytest


def test_embed_and_generate_mock(monkeypatch):
    # Ensure mock path: no API key
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Reload module to pick up env changes
    mod = importlib.import_module("knowledge.openrouter_client")
    importlib.reload(mod)

    texts = ["hello world", "another text"]
    embs = mod.embed(texts)
    assert isinstance(embs, list) and len(embs) == 2
    for v in embs:
        # embeddings should be non-empty vectors
        assert len(v) > 0
        # normalized approx 1.0
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-6

    ans = mod.generate("Test prompt")
    assert isinstance(ans, str) and ans.startswith("[mock answer]")
