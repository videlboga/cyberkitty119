"""Test that DiWorkerAdapter delegates to LocalAdapter when mode='local'."""
from __future__ import annotations

import types

from transcribe_client.di_worker import DiWorkerAdapter


def test_di_worker_local_delegates(monkeypatch, tmp_path):
    called = {}

    class FakeLocal:
        def __init__(self, service_url=None):
            self.service_url = service_url

        def transcribe(self, file_uri, mode=None):
            called['file_uri'] = file_uri
            called['mode'] = mode
            return {'status': 'ok', 'text': 'from-local', 'meta': {'file_uri': file_uri}}

    # Patch LocalAdapter in the local module (this is what DiWorkerAdapter imports)
    import transcribe_client.local as local_mod
    monkeypatch.setattr(local_mod, 'LocalAdapter', FakeLocal, raising=False)

    adapter = DiWorkerAdapter()
    sample = tmp_path / "in.mp3"
    sample.write_bytes(b"dummy")
    res = adapter.transcribe(str(sample), mode='local')

    assert res['status'] == 'ok'
    assert res['text'] == 'from-local'
    assert called['file_uri'].endswith('in.mp3')
    assert called['mode'] == 'local'
