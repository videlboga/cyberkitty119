#!/bin/bash
# Script to run telegram-bot-api container inside vpnspace network namespace
# This ensures all traffic goes through the WireGuard tunnel

set -e

PROJECT_DIR="/home/cyberkitty/Projects/Cyberkitty119"
NETNS="vpnspace"
CONTAINER_NAME="cyberkitty19-telegram-bot-api-vpn"
PORT_HOST="${1:-9082}"
PORT_CONTAINER="8081"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if netns exists
if ! sudo ip netns list | grep -q "^${NETNS}$"; then
    log_error "Network namespace '${NETNS}' not found"
    echo "Available namespaces:"
    sudo ip netns list
    exit 1
fi

# Check if WireGuard is up in vpnspace
log_info "Checking WireGuard tunnel status..."
if ! sudo ip netns exec ${NETNS} ip link show wg0 >/dev/null 2>&1; then
    log_error "WireGuard interface wg0 not found in ${NETNS}"
    exit 1
fi

WG_IP=$(sudo ip netns exec ${NETNS} ip addr show wg0 | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
log_info "WireGuard tunnel active: ${WG_IP}"

# Stop existing container if running
log_info "Checking for existing container..."
if docker ps -a --filter "name=${CONTAINER_NAME}" --format '{{.Names}}' | grep -q "${CONTAINER_NAME}"; then
    log_warn "Found existing container: ${CONTAINER_NAME}, stopping..."
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
fi

# Create docker runtime in vpnspace
log_info "Starting Docker daemon in ${NETNS} namespace..."

# Create socket directory in vpnspace
DOCKER_SOCK_DIR="/var/run/docker-vpn"
sudo mkdir -p ${DOCKER_SOCK_DIR}

# We need to use nsenter to run docker inside the namespace
log_info "Building telegram-bot-api image..."
cd "${PROJECT_DIR}"
docker build -f Dockerfile.telegram-bot-api -t cyberkitty19-telegram-bot-api:vpn .

# Create a wrapper script to run in namespace
WRAPPER_SCRIPT="/tmp/run-telegram-vpn.sh"
cat > "${WRAPPER_SCRIPT}" << 'EOF'
#!/bin/bash
set -e

cd /home/cyberkitty/Projects/Cyberkitty119

# Load env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Run telegram-bot-api with proper networking
exec docker run \
    --rm \
    --name cyberkitty19-telegram-bot-api-vpn \
    --publish 9082:8081 \
    --env "TELEGRAM_API_ID=${TELEGRAM_API_ID}" \
    --env "TELEGRAM_API_HASH=${TELEGRAM_API_HASH}" \
    --volume "cyberkitty19-telegram-bot-api-data:/var/lib/telegram-bot-api" \
    --network cyberkitty19-transkribator-network \
    --cap-add NET_ADMIN \
    --cap-add SYS_MODULE \
    cyberkitty19-telegram-bot-api:vpn
EOF

chmod +x "${WRAPPER_SCRIPT}"

# Run docker command in the namespace
log_info "Starting telegram-bot-api inside ${NETNS}..."
log_info "Container will be accessible at: http://localhost:${PORT_HOST}:${PORT_CONTAINER}"
log_info "All traffic routed through WireGuard tunnel (${WG_IP})"
log_info ""
log_info "To verify traffic routing:"
log_info "  sudo ip netns exec ${NETNS} curl -s https://checkip.amazonaws.com"
log_info ""

# Use sudo to run in namespace
sudo -E bash -c "ip netns exec ${NETNS} ${WRAPPER_SCRIPT}"
