import os
from minimal_app.transcriber import transcribe_audio, transcribe_bytes


def test_transcribe_stub_from_path(tmp_path):
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF....")
    r = transcribe_audio(str(p))
    assert "text" in r
    assert "Transcript of audio.wav" in r["text"]


def test_transcribe_stub_from_bytes():
    data = b"\x00\x01\x02"
    r = transcribe_bytes(data)
    assert "text" in r
    assert "Transcript of" in r["text"]
