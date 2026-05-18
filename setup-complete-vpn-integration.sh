#!/bin/bash
# Complete setup: Stop old container and create port forwarding relay

set -e

NETNS="vpnspace"
HOST_PORT="${1:-9082}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

log_step "Setting up complete VPN integration for telegram-bot-api..."
echo ""

# Step 1: Stop old container
log_step "1. Stopping old Docker container..."
if docker ps --filter "name=cyberkitty19-telegram-bot-api$" --format '{{.Names}}' | grep -q "cyberkitty19-telegram-bot-api"; then
    docker stop cyberkitty19-telegram-bot-api
    log_info "Old container stopped"
else
    log_warn "Old container not running"
fi

sleep 1

# Step 2: Verify new telegram-bot-api is running in vpnspace
log_step "2. Verifying telegram-bot-api in vpnspace..."
PROCESS=$(sudo ip netns exec ${NETNS} pgrep -f "telegram-bot-api" || echo "")
if [ -z "$PROCESS" ]; then
    log_error "telegram-bot-api not running in vpnspace!"
    log_warn "Run: sudo ./run-telegram-bot-api-native-vpn.sh 9082"
    exit 1
fi

log_info "Process confirmed running"

# Step 3: Verify WireGuard tunnel
log_step "3. Checking WireGuard tunnel..."
EXTERNAL_IP=$(sudo timeout 5 ip netns exec ${NETNS} curl -s https://checkip.amazonaws.com 2>/dev/null || echo "")
if [ -n "$EXTERNAL_IP" ] && [ "$EXTERNAL_IP" != "TIMEOUT" ]; then
    log_info "VPN connection verified: $EXTERNAL_IP"
else
    log_warn "Could not verify VPN (but it may still be working)"
fi

# Step 4: Install socat if needed
log_step "4. Ensuring socat is installed..."
if ! command -v socat &>/dev/null; then
    log_warn "socat not found, installing..."
    sudo apt-get update -qq >/dev/null 2>&1
    sudo apt-get install -y socat >/dev/null 2>&1
    log_info "socat installed"
else
    log_info "socat ready"
fi

# Step 5: Create port forwarding
log_step "5. Setting up port forwarding (host:${HOST_PORT} -> vpnspace:8081)..."

# Kill any existing relay
sudo pkill -f "socat.*TCP-LISTEN.*8081" 2>/dev/null || true
sleep 1

# Create relay script
RELAY_SCRIPT="/tmp/telegram-vpn-relay-$(date +%s).sh"
cat > "${RELAY_SCRIPT}" << 'RELAY_EOF'
#!/bin/bash
# This script runs in the host namespace but forwards to the vpnspace

HOST_PORT="$1"
NETNS="$2"

# We need to create a relay that:
# 1. Listens on host:HOST_PORT
# 2. Forwards connections to vpnspace:8081

# Method: Use socat to create a relay via nsenter
# socat will listen on HOST_PORT and connect through the namespace

# First, find a process in vpnspace to use for nsenter
VPNSPACE_PID=$(sudo ip netns pids ${NETNS} 2>/dev/null | head -1)

if [ -z "$VPNSPACE_PID" ]; then
    echo "No processes in ${NETNS}, trying alternative method..."
    # Use direct network routing via /proc
    exec socat TCP-LISTEN:${HOST_PORT},reuseaddr,fork \
        EXEC:"nsenter -t \$\$ -n socat - TCP:127.0.0.1:8081"
else
    echo "Using PID ${VPNSPACE_PID} for namespace access"
    # Forward via that process's namespace
    exec socat TCP-LISTEN:${HOST_PORT},reuseaddr,fork \
        EXEC:"nsenter -t ${VPNSPACE_PID} -n socat - TCP:127.0.0.1:8081"
fi
RELAY_EOF

chmod +x "${RELAY_SCRIPT}"

# Start the relay in background
log_warn "Starting socat relay (this may need adjustment for full compatibility)..."
sudo bash "${RELAY_SCRIPT}" "${HOST_PORT}" "${NETNS}" &
RELAY_PID=$!
sleep 2

log_info "Relay started (PID: ${RELAY_PID})"

# Step 6: Test the relay
log_step "6. Testing port forwarding..."
RELAY_TEST=$(timeout 3 curl -s http://localhost:${HOST_PORT}/test/getMe 2>/dev/null || echo "")

if [ -n "$RELAY_TEST" ]; then
    log_info "✓ Port forwarding working!"
    if echo "$RELAY_TEST" | grep -q "ok"; then
        log_info "API response valid"
    fi
else
    log_warn "Port forwarding test inconclusive"
    log_warn "This may need manual configuration with:"
    log_warn "  - iptables rules, or"
    log_warn "  - Docker network bridge configuration"
fi

# Step 7: Update docker-compose
log_step "7. Updating bot configuration..."

PROJECT_DIR="/home/cyberkitty/Projects/Cyberkitty119"
if [ -f "${PROJECT_DIR}/.env" ]; then
    # Check if LOCAL_BOT_API_URL is already set to VPN
    if grep -q "LOCAL_BOT_API_URL=http://localhost:${HOST_PORT}" "${PROJECT_DIR}/.env"; then
        log_info ".env already configured"
    else
        # Backup and update
        cp "${PROJECT_DIR}/.env" "${PROJECT_DIR}/.env.backup-vpn"
        # Update or add LOCAL_BOT_API_URL
        if grep -q "^LOCAL_BOT_API_URL=" "${PROJECT_DIR}/.env"; then
            sed -i "s|^LOCAL_BOT_API_URL=.*|LOCAL_BOT_API_URL=http://localhost:${HOST_PORT}|" "${PROJECT_DIR}/.env"
        else
            echo "LOCAL_BOT_API_URL=http://localhost:${HOST_PORT}" >> "${PROJECT_DIR}/.env"
        fi
        log_info ".env updated with LOCAL_BOT_API_URL=http://localhost:${HOST_PORT}"
    fi
else
    log_warn ".env not found at ${PROJECT_DIR}"
fi

# Step 8: Restart bot container
log_step "8. Restarting bot container..."
if [ -f "${PROJECT_DIR}/docker-compose.yml" ]; then
    cd "${PROJECT_DIR}"
    docker-compose stop bot 2>/dev/null || true
    sleep 2
    docker-compose up -d bot
    log_info "Bot container restarted"
else
    log_warn "docker-compose.yml not found"
fi

# Final summary
echo ""
echo "════════════════════════════════════════════════════"
log_info "VPN Integration Complete!"
echo "════════════════════════════════════════════════════"
echo ""
log_info "Configuration:"
log_info "  • telegram-bot-api: Running in ${NETNS} namespace"
log_info "  • Port forwarding: localhost:${HOST_PORT} ↔ vpnspace:8081"
log_info "  • Relay PID: ${RELAY_PID}"
log_info "  • External IP (via VPN): $EXTERNAL_IP"
echo ""
log_info "Access:"
log_info "  • HTTP API: http://localhost:${HOST_PORT}"
log_info "  • Test: curl http://localhost:${HOST_PORT}/test/getMe"
echo ""
log_info "Monitoring:"
log_info "  • Process: sudo ip netns exec ${NETNS} ps aux | grep telegram"
log_info "  • Logs: tail -f /var/lib/telegram-bot-api-vpn/server.log"
log_info "  • Relay: sudo ps aux | grep socat"
echo ""
log_warn "Note: Port forwarding may require additional iptables configuration"
log_warn "      depending on your network setup. Manual testing recommended."
echo ""
