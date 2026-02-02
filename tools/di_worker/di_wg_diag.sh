#!/bin/bash
set -euo pipefail
WG_IF=wg0
WG_CONF="/etc/wireguard/${WG_IF}.conf"
if [ ! -f "$WG_CONF" ]; then echo 'WG conf missing' >&2; exit 2; fi
mkdir -p /dev/net
[ -c /dev/net/tun ] || mknod /dev/net/tun c 10 200 || true
WG_TMP_CONF=$(mktemp)
awk '/^[[:space:]]*Address/ {print; next} /^[[:space:]]*DNS/ {next} /^[[:space:]]*MTU/ {next} /^[[:space:]]*Table/ {next} /^[[:space:]]*PreUp/ {next} /^[[:space:]]*PostUp/ {next} /^[[:space:]]*PreDown/ {next} /^[[:space:]]*PostDown/ {next} {print}' "$WG_CONF" > "$WG_TMP_CONF"
ip link delete $WG_IF 2>/dev/null || true
wg setconf $WG_IF $WG_TMP_CONF 2>/dev/null || echo 'wg setconf failed (ok)'
addresses=$(awk -F'=' '/^Address/ {gsub(/ /, "", $2); gsub(/,/, " ", $2); print $2}' "$WG_CONF") || true
for addr in $addresses; do ip addr add "$addr" dev $WG_IF 2>/dev/null || true; done
ip link set $WG_IF up 2>/dev/null || true

echo '--- ip addr show for' $WG_IF '---'
ip addr show $WG_IF || echo 'no interface present'

echo '--- wg show ---'
wg show || echo 'wg show failed'

echo '--- ip route (first 200 lines) ---'
ip route show | sed -n '1,200p'

echo '--- resolve api.openai.com ---'
OPENAI_IP=$(getent hosts api.openai.com | awk '{print $1}' | head -n1 || true)
echo "api.openai.com -> $OPENAI_IP"
if [ -n "$OPENAI_IP" ]; then ip route get $OPENAI_IP || true; fi

echo '--- external IP via ifconfig.co (10s) ---'
curl -sS --max-time 10 https://ifconfig.co/ip || echo 'curl failed or timed out'

echo 'done'
