#!/bin/bash
set -e

CONFIG_DIR=/config
WG_CONF=${CONFIG_DIR}/wg0.conf

log() { echo "[vpn-gateway] $*"; }

if [ "${ENABLE_WG}" = "1" ] ; then
  if [ -f "${WG_CONF}" ]; then
    log "Bringing up WireGuard (wg-quick) using ${WG_CONF} (ENABLE_WG=1)"
    # don't fail the container if wg-quick has issues; we still want the proxy up
    wg-quick up "${WG_CONF}" || log "wg-quick failed (continuing)"
    # Fix MTU issues for outgoing requests from local namespace via TCP MSS clamping
    # Add a POSTROUTING rule on the wg0 interface to explicitly set MSS conservatively.
    # WireGuard MTU is 1420, so we set MSS to 1380 (leave 40 bytes for TCP/IP headers).
    # This avoids excessive fragmentation while allowing proper packet flow.
    if ! iptables -t mangle -C POSTROUTING -o wg0 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1380 2>/dev/null; then
      iptables -t mangle -A POSTROUTING -o wg0 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1380 || true
    else
      log "POSTROUTING TCPMSS rule already present"
    fi

    # Keep an OUTPUT clamp as a fallback for locally-originated sockets
    if ! iptables -t mangle -C OUTPUT -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null; then
      iptables -t mangle -A OUTPUT -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu || true
    else
      log "OUTPUT TCPMSS clamp already present"
    fi

    # Log current mangle rules and wg0 link info for easier debugging in container logs
    log "--- iptables mangle table (startup) ---"
    iptables -t mangle -L -n -v || true
    log "--- wg0 link info (startup) ---"
    ip link show wg0 || true
  else
    log "ENABLE_WG=1 but WireGuard config not found at ${WG_CONF}; continuing without WireGuard"
  fi
else
  log "WireGuard disabled in container (set ENABLE_WG=1 to enable). Continuing without WireGuard"
fi

log "Starting squid proxy"
# ensure logfile and cache directories exist and are writable by 'proxy' user
mkdir -p /var/log/squid /var/spool/squid
chown -R proxy:proxy /var/log/squid /var/spool/squid || true
touch /var/log/squid/access.log /var/log/squid/cache.log || true

# If swap directories are missing, initialize them
if [ ! -d /var/spool/squid/00 ]; then
  log "Initializing squid swap dirs (squid -z)"
  if ! /usr/sbin/squid -z -f /etc/squid/squid.conf; then
    log "squid -z failed, attempting to create missing swap subdirectories and retry"
    # create hex-prefixed swap subdirs (00..FF) which squid expects
    for n in $(seq 0 255); do
      dir=$(printf "%02X" "$n")
      mkdir -p /var/spool/squid/${dir} || true
    done
    chown -R proxy:proxy /var/spool/squid /var/log/squid || true
    if ! /usr/sbin/squid -z -f /etc/squid/squid.conf; then
      log "squid -z retry failed; printing cache.log and aborting"
      cat /var/log/squid/cache.log || true
      exit 1
    fi
  fi
  chown -R proxy:proxy /var/spool/squid /var/log/squid || true
fi

# Remove stale PID file if present
rm -f /run/squid.pid || true

# start squid in foreground so container lifecycle follows squid
exec /usr/sbin/squid -N -f /etc/squid/squid.conf
