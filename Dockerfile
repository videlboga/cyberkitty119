FROM python:3.10-slim

# Optional apt proxy for faster builds (e.g., local apt-cacher-ng)
ARG APT_PROXY=""
# Optional custom mirrors (can be overridden via --build-arg)
ARG APT_MIRROR="http://deb.debian.org/debian"
ARG APT_SECURITY_MIRROR="http://deb.debian.org/debian-security"

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DEFAULT_TIMEOUT=180

# Configure apt proxy if provided
RUN if [ -n "$APT_PROXY" ]; then \
        echo "Acquire::HTTP::Proxy \"$APT_PROXY\";" > /etc/apt/apt.conf.d/99proxy; \
    fi

# Optionally override Debian mirrors to work around slow defaults
RUN set -eux; \
    release="$(. /etc/os-release && printf '%s' "$VERSION_CODENAME")"; \
    : "${release:=stable}"; \
    rm -f /etc/apt/sources.list.d/debian.sources; \
    printf 'deb %s %s main contrib non-free non-free-firmware\n' "${APT_MIRROR}" "${release}" > /etc/apt/sources.list; \
    printf 'deb %s %s-updates main contrib non-free non-free-firmware\n' "${APT_MIRROR}" "${release}" >> /etc/apt/sources.list; \
    printf 'deb %s %s-security main contrib non-free non-free-firmware\n' "${APT_SECURITY_MIRROR}" "${release}" >> /etc/apt/sources.list

# Install minimal system packages first (procps needed for sysctl access)
# Defer large packages (ffmpeg, git) to a later layer to reduce chance of dpkg/apt transient failures
RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools \
    iproute2 \
    iptables \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем файлы с зависимостями
COPY requirements/ ./requirements/
COPY requirements.txt .

# Copy pre-downloaded wheels (if any) to avoid building heavy packages inside the container
# Create wheelhouse on the build host with: python3 -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse
COPY wheelhouse/ /wheelhouse/

# Устанавливаем зависимости по группам, чтобы уменьшить пиковое потребление памяти
# Сначала небольшой набор (core utilities) — низкий объём памяти
RUN pip install --no-cache-dir --prefer-binary \
    python-dotenv \
    requests==2.31.0 \
    httpx==0.27.0 \
    aiohttp==3.9.1 \
    pytest==8.1.1

# Затем более тяжёлые библиотеки и сервис-специфичные зависимости
RUN pip install --no-cache-dir --prefer-binary \
    cryptography==42.0.5 \
    google-auth==2.28.0 \
    google-auth-oauthlib==1.2.0 \
    google-auth-httplib2==0.2.0 \
    google-api-python-client==2.119.0 \
    numpy==1.26.4 \
    pgvector==0.2.4 \
    python-telegram-bot[job-queue]==22.1 \
    openai==1.14.0 \
    sqlalchemy==2.0.25 \
    fastapi==0.108.0 \
    uvicorn==0.25.0 \
    pydantic==2.5.3 \
    alembic==1.13.1 \
    "psycopg[binary,pool]==3.1.18" \
    yt-dlp==2025.9.26 \
    gdown==5.1.0 \
    python-docx==1.1.2 \
    yookassa==3.0.0 \
    mega.py==1.0.8

# Копируем файлы проекта
COPY transkribator_modules/ ./transkribator_modules/
COPY core_api/ ./core_api/
COPY transcribe_client/ ./transcribe_client/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY prompts_catalog.json .
COPY implementation_plan.md .
COPY cyberkitty_modular.py .
COPY job_worker.py .
COPY .env .

# Создаем необходимые директории
RUN mkdir -p /app/videos /app/audio /app/transcriptions

# Install heavier runtime packages (ffmpeg, git) in a separate layer after Python deps
# This can reduce chance of apt/dpkg transient failures on constrained build hosts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Clean up apt proxy config to avoid leaking into runtime image
RUN rm -f /etc/apt/apt.conf.d/99proxy

# Запускаем модульного бота
# Old entrypoint
COPY entrypoint-wg.sh /entrypoint-wg.sh
COPY entrypoint-worker.sh /entrypoint-worker.sh
RUN chmod +x /entrypoint-wg.sh /entrypoint-worker.sh
ENTRYPOINT ["/bin/bash", "/entrypoint-wg.sh"]
CMD []
