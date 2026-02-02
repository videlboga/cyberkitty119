"""Integration-style test for transcribe_client.local.LocalAdapter.

This test does not start a real HTTP server. Instead it monkeypatches the
`requests` object inside the adapter to a tiny fake that records the call and
returns a predictable JSON payload. This verifies the adapter builds the
request properly and returns parsed JSON.
"""
from __future__ import annotations

import os
import types

from transcribe_client.local import LocalAdapter


def test_local_adapter_posts_and_parses(monkeypatch, tmp_path):
    # Prepare a fake response object
    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            return None

    recorded = {}

    # Create a fake requests module with a post() that records args
    def fake_post(url, json=None, timeout=None):
        recorded['url'] = url
        recorded['json'] = json
        recorded['timeout'] = timeout
        # return a response that .json() => expected dict
        return FakeResponse({
            'status': 'ok',
            'text': 'fake transcription',
            'segments': [],
            'model': 'whisper-mock',
            'meta': {'received': True},
        })

    fake_requests = types.SimpleNamespace(post=fake_post)

    # Ensure the adapter uses our fake requests (no external dependency)
    import transcribe_client.local as local_mod

    monkeypatch.setattr(local_mod, "requests", fake_requests)

    # Use a sample file path. Adapter sends file_uri in JSON payload.
    sample = tmp_path / "input.wav"
    sample.write_bytes(b"RIFF....")

    adapter = LocalAdapter(service_url="http://127.0.0.1:9999")
    result = adapter.transcribe(str(sample), mode="local")

    # Assert we called the expected endpoint and returned parsed JSON
    assert recorded['url'].endswith('/transcribe')
    assert recorded['json']['file_uri'].endswith('input.wav')
    assert recorded['json']['options']['mode'] == 'local'
    assert result['status'] == 'ok'
    assert result['text'] == 'fake transcription'
