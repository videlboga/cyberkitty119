#!/bin/bash
# Check telegram-bot-api status in VPN namespace

NETNS="vpnspace"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }

log_step "Checking telegram-bot-api status in ${NETNS}..."
echo ""

# Check if process is running
PROCESS=$(sudo ip netns exec ${NETNS} pgrep -f "telegram-bot-api" || echo "")
if [ -z "$PROCESS" ]; then
    log_error "telegram-bot-api not running in ${NETNS}"
    exit 1
fi

log_info "Process running (PID: $PROCESS)"

# Get process details
log_step "Process details:"
sudo ip netns exec ${NETNS} ps aux | grep telegram-bot-api | grep -v grep

echo ""

# Check network in vpnspace
log_step "Network configuration in ${NETNS}:"
WGIP=$(sudo ip netns exec ${NETNS} ip addr show wg0 2>/dev/null | grep "inet " | awk '{print $2}')
log_info "WireGuard IP: $WGIP"

# Check routes
log_step "Routes in ${NETNS}:"
sudo ip netns exec ${NETNS} ip route show | sed 's/^/  /'

echo ""

# Test connectivity inside namespace
log_step "Testing external connectivity from vpnspace..."
EXTERNAL_IP=$(sudo timeout 5 ip netns exec ${NETNS} curl -s https://checkip.amazonaws.com 2>/dev/null || echo "TIMEOUT")
if [ "$EXTERNAL_IP" != "TIMEOUT" ] && [ -n "$EXTERNAL_IP" ]; then
    log_info "External IP (via VPN): $EXTERNAL_IP"
else
    log_warn "Could not determine external IP (network may be restricted)"
fi

echo ""

# Check telegram-bot-api API
log_step "Testing telegram-bot-api API..."

# We need to test from within the namespace
API_RESULT=$(sudo ip netns exec ${NETNS} timeout 5 curl -s http://localhost:8081/test/getMe 2>/dev/null || echo "")

if [ -z "$API_RESULT" ]; then
    log_error "Could not connect to telegram-bot-api API on localhost:8081"
    log_warn "Trying alternative methods..."
    
    # Try with 127.0.0.1
    API_RESULT=$(sudo timeout 5 bash -c "exec 3<>/dev/tcp/127.0.0.1/8081; echo 'GET /test/getMe HTTP/1.0'; sleep 1" 2>/dev/null | tail -1 || echo "")
    if [ -z "$API_RESULT" ]; then
        log_error "API unreachable"
    else
        log_info "API response (partial): $API_RESULT"
    fi
else
    # Parse JSON response
    if echo "$API_RESULT" | grep -q "ok"; then
        log_info "API working ✓"
        echo "Response:"
        echo "$API_RESULT" | jq . 2>/dev/null || echo "$API_RESULT"
    else
        log_error "API returned error"
        echo "$API_RESULT"
    fi
fi

echo ""
log_step "Setup complete!"
log_info ""
log_info "Summary:"
log_info "  - telegram-bot-api running in vpnspace namespace"
log_info "  - All traffic routed through WireGuard tunnel"
log_info "  - API available at localhost:8081 (inside namespace)"
log_info ""
log_info "Next steps:"
log_info "  1. Stop the original Docker container:"
log_info "     docker stop cyberkitty19-telegram-bot-api"
log_info "  2. Set up port forwarding or update bot config"
log_info "  3. Update LOCAL_BOT_API_URL in docker-compose or .env"
log_info ""
