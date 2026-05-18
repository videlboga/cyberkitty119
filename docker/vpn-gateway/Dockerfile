FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
   procps \
   wireguard-tools \
   squid \
   curl \
   iproute2 \
   iptables \
   openresolv \
   ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

COPY squid.conf /etc/squid/squid.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Ensure squid log/cache directories exist and are owned by proxy user
RUN mkdir -p /var/log/squid /var/spool/squid \
 && chown -R proxy:proxy /var/log/squid /var/spool/squid

# Initialize Squid cache directories at build time to avoid runtime init issues
RUN /usr/sbin/squid -z -f /etc/squid/squid.conf || true

EXPOSE 3128
ENTRYPOINT ["/entrypoint.sh"]
