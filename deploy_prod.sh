#!/bin/bash
echo "--- DEPLOY START ---"
cd /root/Cyberkitty119_build || exit 1
if [ -f ../deploy_pack.tar.gz ]; then
    echo "Extracting deploy pack..."
    mv ../deploy_pack.tar.gz .
    tar -xzf deploy_pack.tar.gz
fi

echo "--- STOPPING OLD CONTAINERS ---"
docker rm -f cyberkitty19-postgres cyberkitty19-telegram-bot-api cyberkitty19-transkribator-bot cyberkitty19-transkribator-worker cyberkitty19-transkribator-api || true

echo "--- STARTING SERVICES ---"
# Ensure volume exists
docker volume create transkribator_postgres-data || true

# Run compose
docker-compose -f docker-compose.prod.yml up -d --build

echo "--- DEPLOY FINISHED ---"
docker-compose -f docker-compose.prod.yml ps
