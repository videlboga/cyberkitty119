import os
import json

from transcribe_client import TranscribeClient
from transcribe_client.stub import StubAdapter


def test_stub_adapter_returns_expected_structure(tmp_path):
    adapter = StubAdapter(text="hello world")
    client = TranscribeClient(adapter=adapter)
    res = client.transcribe(str(tmp_path / "dummy.wav"), mode="stub")
    assert res["status"] == "ok"
    assert "text" in res and res["text"] == "hello world"
    assert isinstance(res.get("segments"), list)


def test_client_default_mode_and_override(tmp_path):
    adapter = StubAdapter(text="abc")
    client = TranscribeClient(default_mode="stub", adapter=adapter)
    res = client.transcribe("/tmp/f.wav")
    assert res["status"] == "ok"
    assert res["text"] == "abc"
