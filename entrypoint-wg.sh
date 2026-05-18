set -e

WG_IF="wg0"
WG_CONF="/etc/wireguard/${WG_IF}.conf"
WG_TABLE=51820
WG_FWMARK=51820
WG_MTU=${WG_MTU:-1420}
WG_TMP_CONF=""

cleanup() {
    ip link delete "${WG_IF}" 2>/dev/null || true
    ip rule delete not fwmark "${WG_FWMARK}" table "${WG_TABLE}" 2>/dev/null || true
    ip rule delete table main suppress_prefixlength 0 2>/dev/null || true
    ip route delete 0.0.0.0/0 dev "${WG_IF}" table "${WG_TABLE}" 2>/dev/null || true
    [ -n "${WG_TMP_CONF}" ] && rm -f "${WG_TMP_CONF}"
}

trap cleanup EXIT

echo "🔧 Starting WireGuard..."

if [ ! -f "${WG_CONF}" ]; then
    echo "⚠️ /etc/wireguard/wg0.conf not found, starting without VPN"
    if [ "$#" -gt 0 ]; then
        exec "$@"
    else
        exec python cyberkitty_modular.py
    fi
fi

# Create interface and apply configuration
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
  ip route add 34.64.0.0/10 dev wg0 2>/dev/null || echo "Route 34.64.0.0/10 exists"
  ip route add 35.184.0.0/13 dev wg0 2>/dev/null || echo "Route 35.184.0.0/13 exists"
  ip route add 64.233.160.0/19 dev wg0 2>/dev/null || echo "Route 64.233.160.0/19 exists"
  ip route add 66.102.0.0/20 dev wg0 2>/dev/null || echo "Route 66.102.0.0/20 exists"
  ip route add 66.249.64.0/19 dev wg0 2>/dev/null || echo "Route 66.249.64.0/19 exists"
  ip route add 72.14.192.0/18 dev wg0 2>/dev/null || echo "Route 72.14.192.0/18 exists"
  ip route add 74.125.0.0/16 dev wg0 2>/dev/null || echo "Route 74.125.0.0/16 exists"
  ip route add 108.177.0.0/17 dev wg0 2>/dev/null || echo "Route 108.177.0.0/17 exists"
  ip route add 172.217.0.0/16 dev wg0 2>/dev/null || echo "Route 172.217.0.0/16 exists"
  ip route add 172.253.0.0/16 dev wg0 2>/dev/null || echo "Route 172.253.0.0/16 exists"
  ip route add 173.194.0.0/16 dev wg0 2>/dev/null || echo "Route 173.194.0.0/16 exists"
  ip route add 209.85.128.0/17 dev wg0 2>/dev/null || echo "Route 209.85.128.0/17 exists"
  ip route add 216.58.192.0/19 dev wg0 2>/dev/null || echo "Route 216.58.192.0/19 exists"
  ip route add 216.239.32.0/19 dev wg0 2>/dev/null || echo "Route 216.239.32.0/19 exists"
  ip route add 142.250.0.0/15 dev wg0 2>/dev/null || echo "Route 142.250.0.0/15 exists"
fi

if [ "$WG_ROUTE_TELEGRAM" = "true" ]; then
  # Telegram IP ranges (to ensure local bot API fetches files)
  ip route add 91.108.4.0/22 dev wg0 2>/dev/null || echo "Route 91.108.4.0/22 exists"
  ip route add 91.108.8.0/22 dev wg0 2>/dev/null || echo "Route 91.108.8.0/22 exists"
  ip route add 91.108.12.0/22 dev wg0 2>/dev/null || echo "Route 91.108.12.0/22 exists"
  ip route add 91.108.16.0/22 dev wg0 2>/dev/null || echo "Route 91.108.16.0/22 exists"
  ip route add 91.108.56.0/22 dev wg0 2>/dev/null || echo "Route 91.108.56.0/22 exists"
  ip route add 149.154.160.0/20 dev wg0 2>/dev/null || echo "Route 149.154.160.0/20 exists"
fi

if [ "$WG_ROUTE_TG_MEDIA" = "true" ]; then
  # Narrow Telegram media/CDN ranges often used for large files
  ip route add 91.108.56.0/22 dev wg0 2>/dev/null || echo "Route 91.108.56.0/22 exists"
  ip route add 91.108.12.0/22 dev wg0 2>/dev/null || echo "Route 91.108.12.0/22 exists"
  ip route add 91.108.16.0/22 dev wg0 2>/dev/null || echo "Route 91.108.16.0/22 exists"
  ip route add 149.154.164.0/22 dev wg0 2>/dev/null || echo "Route 149.154.164.0/22 exists"
fi

echo "✅ Routes configured (google=$WG_ROUTE_GOOGLE, telegram=$WG_ROUTE_TELEGRAM, tg_media=$WG_ROUTE_TG_MEDIA)"

# Start target application (bot by default if no args)
if [ "$#" -eq 0 ]; then
    set -- python cyberkitty_modular.py
fi

echo "🚀 Starting application: $*"
exec "$@"
