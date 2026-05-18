WireGuard support for di-worker container

Goal
- Allow the container to bring up a WireGuard interface inside itself so outbound requests
  to DeepInfra go over the VPN, avoiding the need to manage host netns routing.

How it works
- The image includes wireguard tools and a wrapper entrypoint `wg_entrypoint.sh`.
- If you set environment variable `USE_WG=1` and mount your WireGuard config to
  `/etc/wireguard/wg0.conf` the entrypoint will run `wg-quick up wg0` before running
  the usual worker command.

Security & requirements
- The container must be started with privileges to create network interfaces:
  - docker: `--cap-add=NET_ADMIN --device /dev/net/tun` (or `--privileged`)
  - podman: `--cap-add=NET_ADMIN --device /dev/net/tun` and (on some systems) extra security opts
- Kernel must support WireGuard (modern kernels do). The host must allow creating TUN devices.
- Your WG private key and config are sensitive. Mount only the minimal config into the container
  (read-only), or use secrets management. Do not bake private keys into images.

Example docker run

```bash
docker run --rm \
  --cap-add=NET_ADMIN --device /dev/net/tun \
  -v /local/path/wg0.conf:/etc/wireguard/wg0.conf:ro \
  -v /local/path/input.mp3:/data/input.mp3:ro \
  -v /local/path/out:/data/out \
  -e USE_WG=1 \
  -e DEEPINFRA_API_KEY="$DEEPINFRA_API_KEY" \
  cyberkitty/di-worker:local run_e2e /data/input.mp3
```

Notes
- If you prefer not to give the container NET_ADMIN, you can instead run the scripts
  directly under the host netns (what we used earlier) with `ip netns exec vpnspace ...`.
- Bringing up WG inside a container may interact with host networking and routing; test carefully.
