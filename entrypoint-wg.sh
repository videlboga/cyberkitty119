set -e

echo "🔧 Starting WireGuard..."

# Check if wg0.conf exists
if [ ! -f /etc/wireguard/wg0.conf ]; then
    echo "⚠️ /etc/wireguard/wg0.conf not found, starting without VPN"
    exec python cyberkitty_modular.py
fi

# Start WireGuard interface
wg-quick up wg0 || echo "⚠️ WireGuard already running or failed to start"

# Show interface status
echo "✅ WireGuard interface ready"
ip addr show wg0 || echo "Device wg0 not found"

# Add routes for Google IP ranges through VPN
echo "🌐 Setting up routing for Google/YouTube IP ranges..."
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
ip route add 87.245.220.0/24 dev wg0 2>/dev/null || echo "Route 87.245.220.0/24 exists"

echo "✅ All routes configured"

# Start the bot
echo "🚀 Starting bot application..."
exec python cyberkitty_modular.py
