# di_worker (containerized DeepInfra worker)

This directory contains a lightweight worker image and helper scripts to POST audio to DeepInfra (openai/whisper-large-v3-turbo) and extract per-segment timestamps.

What is included
- `Dockerfile` — Debian-slim image with `wireguard-tools`, `openresolv`, `procps`, `iptables`, and small scripts.
- `wg_entrypoint.sh` — wrapper entrypoint that will `wg-quick up wg0` when `USE_WG=1` and `/etc/wireguard/wg0.conf` is mounted.
- `entrypoint.sh`, `run_e2e.sh`, `run_chunk_scan.sh` — runner scripts to call DeepInfra and save results.
- `extract_segments.py` — converts DeepInfra `result_whole.json` into `<stem>_segments.csv` and `<stem>_transcript_with_timestamps.txt`.

Usage (recommended for tests)

1) Prepare hosts resources (do not embed secrets into images):

 - WireGuard config (mounted read-only): `/path/to/wg0.conf`
 - Input audio file: `/path/to/input.mp3`
 - Output directory: `/path/to/results/di_e2e`
 - Export DEEPINFRA_API_KEY in your shell session (do not pass it on the command line):

```bash
export DEEPINFRA_API_KEY="<your_api_key_here>"
mkdir -p /path/to/results/di_e2e
```

2) Run the container (test run)

The container can optionally bring up WireGuard if you mount `wg0.conf` and set `USE_WG=1`.

Privileged (works reliably for local testing):

```bash
sudo docker run --rm --privileged \
  -e USE_WG=1 \
  -e DEEPINFRA_API_KEY="$DEEPINFRA_API_KEY" \
  -v /path/to/wg0.conf:/etc/wireguard/wg0.conf:ro \
  -v /path/to/input.mp3:/data/input.mp3:ro \
  -v /path/to/results/di_e2e:/data/out/di_e2e \
  cyberkitty/di-worker:wg run_e2e /data/input.mp3
```

Safer alternatives
- Use host netns: run the script from the host inside `vpnspace` (no special container privileges):

```bash
ip netns exec vpnspace docker run --rm -e DEEPINFRA_API_KEY="$DEEPINFRA_API_KEY" -v /path/to/input.mp3:/data/input.mp3:ro -v /path/to/results/di_e2e:/data/out/di_e2e cyberkitty/di-worker:wg run_e2e /data/input.mp3
```

- Or run the container with minimal caps (may require tuning):

```bash
sudo docker run --rm --cap-add=NET_ADMIN --device /dev/net/tun \
  -e USE_WG=1 -e DEEPINFRA_API_KEY="$DEEPINFRA_API_KEY" \
  -v /path/to/wg0.conf:/etc/wireguard/wg0.conf:ro \
  -v /path/to/input.mp3:/data/input.mp3:ro \
  -v /path/to/results/di_e2e:/data/out/di_e2e \
  cyberkitty/di-worker:wg run_e2e /data/input.mp3
```

Files produced
- `/data/out/di_e2e/result_whole.json` — raw DeepInfra JSON response
- `/data/out/di_e2e/<stem>_segments.csv` — CSV with columns: id,start_s,end_s,text
- `/data/out/di_e2e/<stem>_transcript_with_timestamps.txt` — readable transcript with timestamps

Notes & safety
- Do not bake `wg0.conf` with private keys into the image. Always mount it at runtime.
- `--privileged` is convenient for testing but grants broad host access. For production, prefer `--cap-add=NET_ADMIN --device=/dev/net/tun` and tune host policies.
- If podman `--network ns:/var/run/netns/vpnspace` is used, be aware some hosts enforce sysctl restrictions and the run may fail; test it first.

If you want, I can also add a small systemd unit template and a short runbook in this directory.

---
README generated 2026-01-27 — contains run instructions and security notes.
