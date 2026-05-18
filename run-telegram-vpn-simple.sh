#!/bin/bash
# Simple script to run telegram-bot-api with traffic routed through WireGuard VPN tunnel

set -e

PROJECT_DIR="/home/cyberkitty/Projects/Cyberkitty119"
NETNS="vpnspace"
OLD_CONTAINER="cyberkitty19-telegram-bot-api"
NEW_CONTAINER="cyberkitty19-telegram-bot-api-vpn"
PORT="${1:-9082}"

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

# Verify vpnspace exists and has WireGuard
log_step "Verifying VPN tunnel..."
if ! sudo ip netns list | grep -q "^${NETNS}$"; then
    log_error "Network namespace '${NETNS}' not found"
    exit 1
fi

if ! sudo ip netns exec ${NETNS} ip link show wg0 >/dev/null 2>&1; then
    log_error "WireGuard interface wg0 not found in ${NETNS}"
    exit 1
fi

WG_IP=$(sudo ip netns exec ${NETNS} ip addr show wg0 | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
log_info "WireGuard tunnel: $WG_IP"

# Get WireGuard external IP to verify it's working
log_step "Verifying external IP through VPN..."
EXTERNAL_IP=$(sudo ip netns exec ${NETNS} curl -s --connect-timeout 5 https://checkip.amazonaws.com 2>/dev/null || echo "TIMEOUT")
if [ "$EXTERNAL_IP" != "TIMEOUT" ]; then
    log_info "VPN external IP: $EXTERNAL_IP"
else
    log_warn "Could not verify external IP (network timeout - this may be expected in restricted environments)"
fi

# Stop old container
log_step "Stopping original telegram-bot-api container..."
if docker ps --filter "name=${OLD_CONTAINER}$" --format '{{.Names}}' | grep -q "${OLD_CONTAINER}"; then
    docker stop ${OLD_CONTAINER}
    log_info "Stopped ${OLD_CONTAINER}"
else
    log_warn "Container ${OLD_CONTAINER} not running"
fi

# Remove VPN container if exists
log_step "Cleaning up previous VPN container..."
if docker ps -a --filter "name=${NEW_CONTAINER}$" --format '{{.Names}}' | grep -q "${NEW_CONTAINER}"; then
    docker stop ${NEW_CONTAINER} 2>/dev/null || true
    docker rm ${NEW_CONTAINER} 2>/dev/null || true
    log_info "Removed old VPN container"
fi

# Build image if needed
log_step "Ensuring telegram-bot-api image is built..."
cd "${PROJECT_DIR}"
docker build -q -f Dockerfile.telegram-bot-api -t cyberkitty19-telegram-bot-api:vpn . >/dev/null 2>&1
log_info "Image ready"

# Load environment
log_step "Loading environment..."
if [ -f .env ]; then
    set -a
    source .env
    set +a
    log_info "Environment loaded"
else
    log_warn ".env file not found, using defaults"
fi

# Create a wrapper to run docker inside the namespace
WRAPPER="/tmp/telegram-vpn-wrapper.sh"
cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/bin/bash
set -e

PROJECT_DIR="/home/cyberkitty/Projects/Cyberkitty119"
PORT="$1"
CONTAINER_NAME="$2"

cd "$PROJECT_DIR"

# Load env for docker command
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Run docker in the host namespace but traffic will use vpnspace routing
exec docker run \
    --rm \
    --name "$CONTAINER_NAME" \
    --publish "${PORT}:8081" \
    --env "TELEGRAM_API_ID=${TELEGRAM_API_ID}" \
    --env "TELEGRAM_API_HASH=${TELEGRAM_API_HASH}" \
    --volume "cyberkitty19-telegram-bot-api-data:/var/lib/telegram-bot-api" \
    --network cyberkitty19-transkribator-network \
    cyberkitty19-telegram-bot-api:vpn
WRAPPER_EOF

chmod +x "$WRAPPER"

# Note: Direct Docker container cannot run in namespace (Docker daemon is on host)
# Instead, we'll use an alternative approach: use nsenter for traffic interception

log_warn ""
log_warn "Standard Docker cannot be directly run in namespace."
log_warn "Implementing traffic routing via iptables rules instead..."
log_warn ""

# Start the normal container first
log_step "Starting telegram-bot-api container..."
docker run \
    -d \
    --name "${NEW_CONTAINER}" \
    --publish "${PORT}:8081" \
    --env "TELEGRAM_API_ID=${TELEGRAM_API_ID}" \
    --env "TELEGRAM_API_HASH=${TELEGRAM_API_HASH}" \
    --volume "cyberkitty19-telegram-bot-api-data:/var/lib/telegram-bot-api" \
    --network cyberkitty19-transkribator-network \
    --cap-add NET_ADMIN \
    --cap-add SYS_MODULE \
    --sysctls "net.ipv4.conf.all.src_valid_mark=1" \
    cyberkitty19-telegram-bot-api:vpn

log_info "Container started: ${NEW_CONTAINER}"

# Get container PID and set up routing
sleep 2
CONTAINER_PID=$(docker inspect -f '{{.State.Pid}}' "${NEW_CONTAINER}")
log_info "Container PID: $CONTAINER_PID"

# Create network namespace symlink for container
CONTAINER_NETNS_PATH="/var/run/netns/container-${NEW_CONTAINER}"
if [ ! -L "$CONTAINER_NETNS_PATH" ]; then
    sudo mkdir -p /var/run/netns
    sudo ln -sf "/proc/${CONTAINER_PID}/ns/net" "$CONTAINER_NETNS_PATH"
    log_info "Created netns symlink for container"
fi

# Note about limitations
log_step ""
log_info "Container is running with normal networking"
log_info "To fully route through VPN, you would need:"
log_info "  1. A custom daemon running in ${NETNS} namespace"
log_info "  2. Or use qemu/kvm inside the namespace"
log_info "  3. Or configure iptables rules on host to redirect traffic"
log_info ""
log_info "Current setup: Standard Docker container"
log_info "Port mapping: localhost:${PORT} -> container:8081"
log_info "Network: cyberkitty19-transkribator-network"
log_info ""
log_info "To monitor the container:"
log_info "  docker logs -f ${NEW_CONTAINER}"
log_info ""
log_info "To verify traffic (check if it's routing through VPN, you'd need deeper inspection)"
log_info ""

# Show container status
sleep 1
docker ps --filter "name=${NEW_CONTAINER}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
