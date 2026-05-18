#!/usr/bin/env python3
"""Minimal mock Whisper HTTP service.

Listens on 0.0.0.0:8000 and accepts POST /transcribe with JSON payload
{"file_uri": "...", "options": {...}} and returns a deterministic
transcription JSON. No external dependencies required.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/transcribe":
            self._send_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            self._send_json({"error": "invalid json"}, status=400)
            return

        file_uri = payload.get("file_uri") or payload.get("file") or ""
        mode = (payload.get("options") or {}).get("mode")

        text = f"[mock] transcription for {file_uri}"
        resp = {
            "status": "ok",
            "text": text,
            "segments": [{"start": 0.0, "end": 1.0, "text": text, "confidence": 0.95}],
            "model": "mock-whisper",
            "meta": {"file_uri": file_uri, "mode": mode},
        }
        self._send_json(resp)

    def log_message(self, format, *args):
        # keep logs short
        print("[mock_whisper] " + (format % args))


def run(host: str = "0.0.0.0", port: int = 8000):
    srv = HTTPServer((host, port), Handler)
    print(f"Mock whisper server listening on http://{host}:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down mock server")
        srv.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    run(args.host, args.port)
