#!/bin/bash
echo "--- WRAPPER START ---"
cd /root || echo "cd /root failed"
mkdir -p Cyberkitty119_build || echo "mkdir failed"
if [ -f build_pack.tar.gz ]; then
    echo "Moving tarball..."
    mv build_pack.tar.gz Cyberkitty119_build/ || echo "mv failed"
fi
cd Cyberkitty119_build || echo "cd build failed"
if [ -f build_pack.tar.gz ]; then
    echo "Extracting tarball..."
    tar -xzf build_pack.tar.gz || echo "tar failed"
fi
# Create empty wheelhouse to satisfy COPY instruction
mkdir -p wheelhouse
echo "Files:"
ls -la
echo "--- DOCKER BUILD START ---"
export DOCKER_BUILDKIT=0
docker build -f Dockerfile.local -t cyberkitty119_bot_test:prod .
EXIT_CODE=$?
echo "--- DOCKER BUILD END (Exit: $EXIT_CODE) ---"
