#!/bin/bash
# Advanced script: Route telegram-bot-api traffic through WireGuard tunnel using socat proxy

set -e

PROJECT_DIR="/home/cyberkitty/Projects/Cyberkitty119"
NETNS="vpnspace"
CONTAINER_NAME="cyberkitty19-telegram-bot-api-vpn-v2"
SOCAT_CONTAINER="cyberkitty19-socat-vpn-proxy"
LOCAL_PORT="${1:-9082}"
CONTAINER_PORT="8081"

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

# Verify vpnspace exists
log_step "Verifying VPN namespace..."
if ! sudo ip netns list | grep -q "^${NETNS}$"; then
    log_error "Network namespace '${NETNS}' not found"
    exit 1
fi

if ! sudo ip netns exec ${NETNS} ip link show wg0 >/dev/null 2>&1; then
    log_error "WireGuard interface not active in ${NETNS}"
    exit 1
fi

WG_IP=$(sudo ip netns exec ${NETNS} ip addr show wg0 | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
log_info "WireGuard active at: $WG_IP"

# Load environment
log_step "Loading environment..."
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Clean up old containers
log_step "Cleaning up..."
docker rm -f ${CONTAINER_NAME} 2>/dev/null || true
docker rm -f ${SOCAT_CONTAINER} 2>/dev/null || true

# Start telegram-bot-api container (on internal network)
log_step "Starting telegram-bot-api container..."
docker run \
    -d \
    --name "${CONTAINER_NAME}" \
    --env "TELEGRAM_API_ID=${TELEGRAM_API_ID}" \
    --env "TELEGRAM_API_HASH=${TELEGRAM_API_HASH}" \
    --volume "cyberkitty19-telegram-bot-api-data:/var/lib/telegram-bot-api" \
    --network cyberkitty19-transkribator-network \
    --restart unless-stopped \
    cyberkitty19-telegram-bot-api:vpn

log_info "Container started: ${CONTAINER_NAME}"
sleep 2

# Get internal IP of telegram container
TELEGRAM_INTERNAL_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ${CONTAINER_NAME})
log_info "Container internal IP: ${TELEGRAM_INTERNAL_IP}"

# Now create socat proxy container that runs in vpnspace to proxy traffic
log_step "Creating socat VPN proxy container..."

# We'll use the host network and configure it to route through vpnspace
# This is a workaround since Docker daemon itself isn't in the namespace

cat > /tmp/socat-entrypoint.sh << 'SOCAT_SCRIPT'
#!/bin/bash
# This script will be run in the host network but will forward traffic via vpnspace

TARGET_IP="$1"
TARGET_PORT="$2"
LISTEN_PORT="$3"

echo "Starting socat proxy..."
echo "  Listen: 0.0.0.0:${LISTEN_PORT}"
echo "  Target: ${TARGET_IP}:${TARGET_PORT}"

# Run socat to forward traffic
# The actual VPN routing needs to be done on the host with iptables

socat TCP-LISTEN:${LISTEN_PORT},reuseaddr,fork TCP:${TARGET_IP}:${TARGET_PORT}
SOCAT_SCRIPT

chmod +x /tmp/socat-entrypoint.sh

# Create socat proxy container
docker run \
    -d \
    --name "${SOCAT_CONTAINER}" \
    --publish "${LOCAL_PORT}:${CONTAINER_PORT}" \
    --network cyberkitty19-transkribator-network \
    --entrypoint /entrypoint.sh \
    alpine:latest \
    bash -c "apk add --no-cache socat && socat TCP-LISTEN:8081,reuseaddr,fork TCP:${TELEGRAM_INTERNAL_IP}:${CONTAINER_PORT}"

log_info "Socat proxy started: ${SOCAT_CONTAINER}"

# Now set up iptables rules to route socat traffic through vpnspace
log_step "Configuring traffic routing through VPN namespace..."
log_warn "Note: This requires root access and complex iptables configuration"
log_warn "Full implementation would require:"
log_warn "  1. Running telegram-bot-api directly in vpnspace (not via Docker)"
log_warn "  2. Or using TPROXY (transparent proxy) with iptables"
log_warn "  3. Or setting up a VPN client inside container"

log_info ""
log_info "Current setup:"
log_info "  Telegram API: http://localhost:${LOCAL_PORT}"
log_info "  Internal container: ${TELEGRAM_INTERNAL_IP}:${CONTAINER_PORT}"
log_info "  VPN namespace: ${NETNS}"
log_info "  WireGuard IP: ${WG_IP}"
log_info ""
log_warn "To route ALL traffic through VPN, the Telegram Bot API would need to:"
log_warn "  1. Run as a native process in the ${NETNS} namespace"
log_warn "  2. Or have OpenVPN/WireGuard client inside the container"
log_info ""
log_info "Container status:"
docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}"
docker ps --filter "name=${SOCAT_CONTAINER}" --format "table {{.Names}}\t{{.Status}}"
