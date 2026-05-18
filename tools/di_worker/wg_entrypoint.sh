#!/usr/bin/env bash
set -e

# Di-worker WireGuard entrypoint — mirror the transcriber-style setup which uses
# selective routing for Google/Telegram IP ranges instead of replacing the
# default route. This avoids breaking DNS resolution when forcing all traffic
# through the tunnel and makes YouTube/Google accesses work via vpnspace.

WG_IF="wg0"
WG_CONF="/etc/wireguard/${WG_IF}.conf"
WG_TABLE=51820
WG_FWMARK=51820
WG_MTU=${WG_MTU:-1420}
WG_TMP_CONF=""
WG_FULL_TUNNEL=${WG_FULL_TUNNEL:-false}

cleanup() {
    ip link delete "${WG_IF}" 2>/dev/null || true
    ip rule delete not fwmark "${WG_FWMARK}" table "${WG_TABLE}" 2>/dev/null || true
  if [ "${WG_FULL_TUNNEL}" = "true" ]; then
    ip route delete default dev "${WG_IF}" table "${WG_TABLE}" 2>/dev/null || true
    ip rule delete fwmark "${WG_FWMARK}" table "${WG_TABLE}" 2>/dev/null || true
  fi
    ip rule delete table main suppress_prefixlength 0 2>/dev/null || true
    ip route delete 0.0.0.0/0 dev "${WG_IF}" table "${WG_TABLE}" 2>/dev/null || true
    [ -n "${WG_TMP_CONF}" ] && rm -f "${WG_TMP_CONF}"
}

trap cleanup EXIT

echo "🔧 Starting WireGuard..."

if [ ! -f "${WG_CONF}" ]; then
    echo "⚠️ ${WG_CONF} not found, starting without VPN"
    exec /opt/di/entrypoint.sh "$@"
fi

# Ensure /dev/net/tun exists
if [ ! -c /dev/net/tun ]; then
  mkdir -p /dev/net
  mknod /dev/net/tun c 10 200 || true
fi

# Delete existing interface if present and create new one
ip link delete "${WG_IF}" 2>/dev/null || true
ip link add "${WG_IF}" type wireguard

# Strip wg-quick specific directives (Address/DNS/etc.) for wg setconf
WG_TMP_CONF=$(mktemp)
awk '
    /^[[:space:]]*Address/ {next}
    /^[[:space:]]*DNS/ {next}
    /^[[:space:]]*MTU/ {next}
    /^[[:space:]]*Table/ {next}
    /^[[:space:]]*PreUp/ {next}
    /^[[:space:]]*PostUp/ {next}
    /^[[:space:]]*PreDown/ {next}
    /^[[:space:]]*PostDown/ {next}
    {print}
' "${WG_CONF}" > "${WG_TMP_CONF}"

wg setconf "${WG_IF}" "${WG_TMP_CONF}"

# Apply IP addresses from config (comma or space separated)
addresses=$(awk -F'=' '/^Address/ {gsub(/ /, "", $2); gsub(/,/, " ", $2); print $2}' "${WG_CONF}")
for addr in ${addresses}; do
    ip addr add "${addr}" dev "${WG_IF}"
done

wg set "${WG_IF}" fwmark "${WG_FWMARK}"
ip link set mtu "${WG_MTU}" up dev "${WG_IF}"

echo "✅ WireGuard interface ready"
ip addr show "${WG_IF}" || echo "Device ${WG_IF} not found"

WG_ROUTE_GOOGLE=${WG_ROUTE_GOOGLE:-true}
WG_ROUTE_TELEGRAM=${WG_ROUTE_TELEGRAM:-true}
WG_ROUTE_TG_MEDIA=${WG_ROUTE_TG_MEDIA:-false}

echo "🌐 Setting up selective routing..."
if [ "$WG_ROUTE_GOOGLE" = "true" ]; then
  # Google IP ranges (including YouTube)
  ip route add 34.64.0.0/10 dev wg0 2>/dev/null || true
  ip route add 35.184.0.0/13 dev wg0 2>/dev/null || true
  ip route add 64.233.160.0/19 dev wg0 2>/dev/null || true
  ip route add 66.102.0.0/20 dev wg0 2>/dev/null || true
  ip route add 66.249.64.0/19 dev wg0 2>/dev/null || true
  ip route add 72.14.192.0/18 dev wg0 2>/dev/null || true
  ip route add 74.125.0.0/16 dev wg0 2>/dev/null || true
  ip route add 108.177.0.0/17 dev wg0 2>/dev/null || true
  ip route add 172.217.0.0/16 dev wg0 2>/dev/null || true
  ip route add 172.253.0.0/16 dev wg0 2>/dev/null || true
  ip route add 173.194.0.0/16 dev wg0 2>/dev/null || true
  ip route add 209.85.128.0/17 dev wg0 2>/dev/null || true
  ip route add 216.58.192.0/19 dev wg0 2>/dev/null || true
  ip route add 216.239.32.0/19 dev wg0 2>/dev/null || true
  ip route add 142.250.0.0/15 dev wg0 2>/dev/null || true
fi

if [ "$WG_ROUTE_TELEGRAM" = "true" ]; then
  # Telegram IP ranges (to ensure local bot API fetches files)
  ip route add 91.108.4.0/22 dev wg0 2>/dev/null || true
  ip route add 91.108.8.0/22 dev wg0 2>/dev/null || true
  ip route add 91.108.12.0/22 dev wg0 2>/dev/null || true
  ip route add 91.108.16.0/22 dev wg0 2>/dev/null || true
  ip route add 91.108.56.0/22 dev wg0 2>/dev/null || true
  ip route add 149.154.160.0/20 dev wg0 2>/dev/null || true
fi

if [ "$WG_ROUTE_TG_MEDIA" = "true" ]; then
  # Narrow Telegram media/CDN ranges often used for large files
  ip route add 91.108.56.0/22 dev wg0 2>/dev/null || true
  ip route add 91.108.12.0/22 dev wg0 2>/dev/null || true
  ip route add 91.108.16.0/22 dev wg0 2>/dev/null || true
  ip route add 149.154.164.0/22 dev wg0 2>/dev/null || true
fi

echo "✅ Routes configured (google=$WG_ROUTE_GOOGLE, telegram=$WG_ROUTE_TELEGRAM, tg_media=$WG_ROUTE_TG_MEDIA)"

# If requested, make wg0 a full-tunnel (default route via wg0 in custom table).
# This preserves existing behavior unless WG_FULL_TUNNEL=1 is set in the container env.
if [ "${WG_FULL_TUNNEL}" = "true" ]; then
  echo "🔒 Enabling full-tunnel mode: routing default traffic via ${WG_IF}"
  # Add default route in the WG table and ensure traffic uses the table unless fwmark is present
  ip route replace default dev "${WG_IF}" table "${WG_TABLE}" 2>/dev/null || true
  # Ensure packets marked for the table (by fwmark) are routed using it
  ip rule add not fwmark "${WG_FWMARK}" table "${WG_TABLE}" 2>/dev/null || true
  ip rule add fwmark "${WG_FWMARK}" table "${WG_TABLE}" 2>/dev/null || true
  # Suppress main table to prefer the WG table where appropriate
  ip rule add table main suppress_prefixlength 0 2>/dev/null || true
  echo "✅ Full-tunnel enabled (table ${WG_TABLE} default via ${WG_IF})"
fi

# Finally exec the di entrypoint (which will run the requested subcommand)
echo "🚀 Starting application: /opt/di/entrypoint.sh $*"
exec /opt/di/entrypoint.sh "$@"
