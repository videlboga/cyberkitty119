#!/bin/bash
# Most effective: Run telegram-bot-api NATIVELY (not in Docker) inside vpnspace namespace
# This ensures 100% of traffic routes through WireGuard tunnel

set -e

NETNS="vpnspace"
DATA_DIR="/var/lib/telegram-bot-api-vpn"
PORT="${1:-9082}"
API_ID="${TELEGRAM_API_ID}"
API_HASH="${TELEGRAM_API_HASH}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }

# Verify vpnspace and WireGuard
log_step "Verifying VPN namespace..."
# Check if we have sudo, if not, request privileges
NETNS_CHECK=$(sudo ip netns list 2>/dev/null | grep "vpnspace" || echo "")
if [ -z "$NETNS_CHECK" ]; then
    log_error "Network namespace '${NETNS}' not found"
    exit 1
fi

WG_CHECK=$(sudo ip netns exec ${NETNS} ip link show awg0 2>/dev/null || echo "")
if [ -z "$WG_CHECK" ]; then
    log_error "WireGuard not active in ${NETNS}"
    exit 1
fi

WG_IP=$(sudo ip netns exec ${NETNS} ip addr show awg0 | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
log_info "WireGuard tunnel: $WG_IP"

# Verify Telegram API credentials
if [ -z "$API_ID" ] || [ -z "$API_HASH" ]; then
    log_step "Loading environment..."
    PROJECT_DIR="/home/cyberkitty/Projects/Cyberkitty119"
    if [ -f "${PROJECT_DIR}/.env" ]; then
        set -a
        source "${PROJECT_DIR}/.env"
        set +a
        API_ID="${TELEGRAM_API_ID}"
        API_HASH="${TELEGRAM_API_HASH}"
    fi
fi

if [ -z "$API_ID" ] || [ -z "$API_HASH" ]; then
    log_error "TELEGRAM_API_ID and TELEGRAM_API_HASH not set"
    exit 1
fi

log_info "API credentials loaded"

# Setup data directory
log_step "Setting up data directory..."
sudo mkdir -p "${DATA_DIR}"
sudo chmod 777 "${DATA_DIR}"
sudo mkdir -p "${DATA_DIR}/temp"
sudo chmod 777 "${DATA_DIR}/temp"
log_info "Data directory: ${DATA_DIR}"

# Resolve telegram-bot-api binary location
if [ -x "/usr/local/bin/telegram-bot-api-native" ]; then
    TBA_BINARY="/usr/local/bin/telegram-bot-api-native"
elif [ -x "/tmp/telegram-bot-api" ]; then
    TBA_BINARY="/tmp/telegram-bot-api"
else
    log_step "Extracting telegram-bot-api binary from running container..."
    if docker exec cyberkitty19-telegram-bot-api true 2>/dev/null; then
        docker cp cyberkitty19-telegram-bot-api:/usr/local/bin/telegram-bot-api /tmp/telegram-bot-api
        chmod +x /tmp/telegram-bot-api
        TBA_BINARY="/tmp/telegram-bot-api"
        log_info "Binary extracted to /tmp/telegram-bot-api"
    else
        log_error "Cannot find telegram-bot-api binary (checked /usr/local/bin/telegram-bot-api-native and /tmp/telegram-bot-api)"
        exit 1
    fi
fi

log_info "Using binary: ${TBA_BINARY}"

# Verify binary exists and is executable
if [ ! -x "${TBA_BINARY}" ]; then
    log_error "telegram-bot-api binary not found or not executable: ${TBA_BINARY}"
    exit 1
fi

# Create entrypoint script to run in vpnspace
ENTRYPOINT="/tmp/telegram-bot-api-vpn-start.sh"
cat > "${ENTRYPOINT}" << ENDPOINT_SCRIPT
#!/bin/bash
set -e

BINARY="${TBA_BINARY}"
DATA_DIR="${DATA_DIR}"
PORT="${PORT}"
API_ID="${API_ID}"
API_HASH="${API_HASH}"

echo "[VPN] Starting telegram-bot-api in vpnspace namespace..."
echo "[VPN] PID: \$\$"
echo "[VPN] Data dir: \${DATA_DIR}"
echo "[VPN] Listen port: \${PORT}"

# Show network info
echo "[VPN] Network interfaces:"
ip link show
echo ""
echo "[VPN] Routes:"
ip route show
echo ""

# Start telegram-bot-api
exec "\${BINARY}" \\
    --api-id "\${API_ID}" \\
    --api-hash "\${API_HASH}" \\
    --local \\
    --http-port "\${PORT}" \\
    --dir "\${DATA_DIR}" \\
    --temp-dir "\${DATA_DIR}/temp"
ENDPOINT_SCRIPT

chmod +x "${ENTRYPOINT}"

# Display network info
log_step "Ensuring loopback interface is up in ${NETNS}..."
sudo ip netns exec ${NETNS} ip link set lo up || log_warn "Failed to bring loopback up (it may already be up)"

log_step "Network configuration in ${NETNS}:"
sudo ip netns exec ${NETNS} ip addr show | grep -E "inet |^[0-9]:" | head -20

log_step "Verifying network connectivity in ${NETNS}..."
PING_TEST=$(sudo ip netns exec ${NETNS} timeout 5 ping -c 1 8.8.8.8 2>&1 | tail -1 || echo "TIMEOUT")
if echo "$PING_TEST" | grep -q "1 received"; then
    log_info "Network connectivity verified ✓"
elif echo "$PING_TEST" | grep -q "0 received"; then
    log_warn "Network unreachable (may be expected in restricted network)"
else
    log_warn "Connectivity test inconclusive: $PING_TEST"
fi

# Display final startup message
log_info ""
log_info "════════════════════════════════════════════════════"
log_info "  TELEGRAM BOT API - NATIVE IN VPN NAMESPACE"
log_info "════════════════════════════════════════════════════"
log_info ""
log_info "Starting telegram-bot-api inside ${NETNS}..."
log_info "All traffic will route through WireGuard tunnel"
log_info ""
log_info "Access at: http://localhost:${PORT}"
log_info "API ID: ${API_ID}"
log_info "Data dir: ${DATA_DIR}"
log_info ""
log_info "To monitor:"
log_info "  \$ tail -f ${DATA_DIR}/server.log"
log_info ""
log_info "To stop:"
log_info "  \$ pkill -f 'telegram-bot-api.*vpnspace'"
log_info ""

# Run telegram-bot-api in the vpnspace namespace
sudo ip netns exec ${NETNS} "${ENTRYPOINT}"
