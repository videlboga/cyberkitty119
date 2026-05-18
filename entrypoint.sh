#!/bin/sh
mkdir -p /var/lib/telegram-bot-api
chmod 755 /var/lib/telegram-bot-api

exec telegram-bot-api \
  --dir=/var/lib/telegram-bot-api \
  --temp-dir=/tmp/telegram-bot-api \
  --http-port=8081 \
  --local \
  --verbosity=5 \
  --api-id=${TELEGRAM_API_ID:-29612572} \
  --api-hash=${TELEGRAM_API_HASH:-fa4d9922f76dea00803d072510ced924}
