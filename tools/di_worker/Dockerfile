FROM debian:bookworm-slim

ARG APT_PROXY=""

# Install runtime deps (ffmpeg removed: audio preparation is done by another microservice)
RUN if [ -n "$APT_PROXY" ]; then \
        echo "Acquire::HTTP::Proxy \"$APT_PROXY\";" > /etc/apt/apt.conf.d/99proxy; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 \
      python3-distutils \
      python3-pip \
      curl \
      jq \
      ca-certificates \
      iproute2 \
      bash \
      wget \
      unzip \
      ffmpeg \
      python3-requests \
      wireguard-tools \
      openresolv \
      procps \
      iptables \
    && rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/apt/apt.conf.d/99proxy

# Replace apt yt-dlp (may be outdated) with the latest binary release
RUN curl -L -o /usr/local/bin/yt-dlp \
      https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    && chmod +x /usr/local/bin/yt-dlp || true

# Install Deno (lightweight JS runtime) which helps yt-dlp extract YouTube player JS
RUN curl -fsSL https://deno.land/x/install/install.sh | sh || true \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno || true

# Create app dir
WORKDIR /opt/di

# Copy scripts
COPY run_chunk_scan.sh /opt/di/run_chunk_scan.sh
COPY run_e2e.sh /opt/di/run_e2e.sh
COPY run_benchmark_timeouts.sh /opt/di/run_benchmark_timeouts.sh
COPY entrypoint.sh /opt/di/entrypoint.sh
COPY extract_segments.py /opt/di/extract_segments.py
COPY wg_entrypoint.sh /opt/di/wg_entrypoint.sh
COPY prepare_audio.py /opt/di/prepare_audio.py
RUN chmod +x /opt/di/*.sh
RUN chmod +x /opt/di/extract_segments.py || true
RUN chmod +x /opt/di/wg_entrypoint.sh || true
RUN chmod +x /opt/di/prepare_audio.py || true

ENV DEEPINFRA_API_KEY=""

## Use the WireGuard wrapper entrypoint so the container can optionally bring up wg0
# If USE_WG=1 and /etc/wireguard/wg0.conf is mounted, wg_entrypoint.sh will run wg-quick up wg0
ENTRYPOINT ["/opt/di/wg_entrypoint.sh"]
