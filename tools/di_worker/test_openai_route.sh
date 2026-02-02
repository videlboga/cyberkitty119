#!/bin/bash
set -euo pipefail
OPENAI_IP=$(getent hosts api.openai.com | awk '{print $1}' | head -n1 || true)
echo "OPENAI_IP=$OPENAI_IP"

echo '--- ip route get before ---'
if [ -n "$OPENAI_IP" ]; then
  ip route get "$OPENAI_IP" || true
else
  echo 'no OPENAI_IP resolved'
fi

echo '--- adding route ${OPENAI_IP}/32 -> wg0 (best-effort) ---'
if [ -n "$OPENAI_IP" ]; then
  ip route add ${OPENAI_IP}/32 dev wg0 2>/dev/null || echo 'route add failed or existed'
fi

echo '--- ip route get after ---'
if [ -n "$OPENAI_IP" ]; then
  ip route get "$OPENAI_IP" || true
fi

echo '--- curl to OpenAI (HEAD, no auth) ---'
if [ -n "$OPENAI_IP" ]; then
  curl -sS --max-time 15 --resolve api.openai.com:443:${OPENAI_IP} -I https://api.openai.com/ || echo 'curl failed'
else
  echo 'skipping curl (no openai ip)'
fi

echo '--- external ip via ifconfig.co ---'
curl -sS --max-time 10 https://ifconfig.co/ip || echo 'ifconfig failed'

echo done
