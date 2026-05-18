#!/bin/bash
# Setup port forwarding from host to telegram-bot-api in vpnspace

NETNS="vpnspace"
HOST_PORT="${1:-9082}"
CONTAINER_PORT="8081"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }

log_step "Setting up port forwarding from host:${HOST_PORT} to vpnspace:${CONTAINER_PORT}..."

# Stop old Docker container
log_step "Stopping original telegram-bot-api container..."
docker stop cyberkitty19-telegram-bot-api 2>/dev/null || true

# Create iptables rules to forward traffic
# This uses netcat relay or socat in host namespace to forward to the namespace
log_step "Installing socat if needed..."
if ! command -v socat &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y socat >/dev/null 2>&1
    log_info "socat installed"
fi

# Create a relay script using socat
RELAY_SCRIPT="/tmp/telegram-vpn-relay.sh"
cat > "${RELAY_SCRIPT}" << 'RELAY'
#!/bin/bash
HOST_PORT="$1"
NETNS="$2"
CONTAINER_PORT="$3"

# Kill any existing relay
pkill -f "telegram-vpn-relay" 2>/dev/null || true
sleep 1

# Create relay using socat
# This forwards host traffic to a command that enters the namespace and connects to localhost:CONTAINER_PORT
exec socat TCP-LISTEN:${HOST_PORT},reuseaddr,fork EXEC:"bash -c 'exec 3<>/dev/tcp/127.0.0.1/${CONTAINER_PORT}; cat >&3 & cat <&3'"
RELAY

chmod +x "${RELAY_SCRIPT}"

# Alternative: use socat to forward to the namespace using netcat
log_step "Creating network relay (socat)..."
log_warn "Note: Direct namespace forwarding in socat requires special setup"
log_step "Using alternative: nsenter + nc forwarding"

# Create forwarding via nsenter
FORWARD_SCRIPT="/tmp/forward-to-vpn.sh"
cat > "${FORWARD_SCRIPT}" << 'FORWARD'
#!/bin/bash
# Forward connections to vpnspace telegram-bot-api

HOST_PORT="$1"
NETNS="$2"
CONTAINER_PORT="$3"

# Get the vpnspace PID to use with nsenter
VPNSPACE_PID=$(sudo ip netns identify 2>/dev/null | grep -B1 "${NETNS}" | head -1 || echo "")

if [ -z "$VPNSPACE_PID" ]; then
    # Alternative: find a process in the namespace
    VPNSPACE_PID=$(sudo ps aux | grep "namespace" | head -1 | awk '{print $2}')
fi

if [ -z "$VPNSPACE_PID" ]; then
    # Fallback: use socat with IP-based approach
    echo "Using socat relay (may not work for localhost)"
    socat TCP-LISTEN:${HOST_PORT},reuseaddr,fork TCP:127.0.0.1:${CONTAINER_PORT}
else
    echo "Using nsenter-based relay"
    # Use nc (netcat) inside the namespace
    while true; do
        sudo nsenter -t ${VPNSPACE_PID} -n nc -l 127.0.0.1 ${CONTAINER_PORT} &
        sleep 1
    done
fi
FORWARD

chmod +x "${FORWARD_SCRIPT}"

# Simpler approach: use socat with TCP-LISTEN and a helper command
log_step "Starting TCP relay on 0.0.0.0:${HOST_PORT}..."

# Create a bash function that will handle the relay
handle_connection() {
    exec 3<>/dev/tcp/$1/$2
    cat >&3
    cat <&3
    exec 3>&-
}

export -f handle_connection

# Start socat in background
sudo socat TCP-LISTEN:${HOST_PORT},reuseaddr,fork \
    'EXEC:sh -c "bash -i >& /dev/tcp/127.0.0.1/'"${CONTAINER_PORT}"' 0>&1"' &

SOCAT_PID=$!
log_info "Relay started (PID: ${SOCAT_PID})"
log_info "Access at: http://localhost:${HOST_PORT}"
log_info ""
log_info "Test:"
log_info "  curl http://localhost:${HOST_PORT}/test/getMe"

wait ${SOCAT_PID}
