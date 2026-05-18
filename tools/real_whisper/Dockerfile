FROM python:3.10-slim AS whisper-wheels

ARG APT_PROXY=""

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /tmp/build

# Build stage: download wheels for all whisper deps once (uses slim base to keep RAM requirements low)
COPY requirements.txt /tmp/requirements.txt
RUN if [ -n "$APT_PROXY" ]; then \
        echo "Acquire::HTTP::Proxy \"$APT_PROXY\";" > /etc/apt/apt.conf.d/99proxy; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/apt/apt.conf.d/99proxy && \
    python -m pip install --upgrade pip wheel setuptools && \
    pip wheel --prefer-binary --no-cache-dir -r /tmp/requirements.txt -w /wheelhouse_whisper


FROM pytorch/pytorch:2.2.0-cuda11.8-cudnn8-runtime

ARG APT_PROXY=""

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install system deps required to build / run PyAV and other libs
RUN if [ -n "$APT_PROXY" ]; then \
        echo "Acquire::HTTP::Proxy \"$APT_PROXY\";" > /etc/apt/apt.conf.d/99proxy; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        ffmpeg \
        libavcodec-dev libavformat-dev libavdevice-dev libavutil-dev libswresample-dev libavfilter-dev \
    && rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/apt/apt.conf.d/99proxy

COPY --from=whisper-wheels /wheelhouse_whisper /wheelhouse_whisper
COPY requirements.txt /tmp/requirements.txt

# Ensure pip and wheel are up to date, then install from the cached wheels
RUN pip3 install --upgrade pip wheel setuptools && \
    pip3 install --no-cache-dir --no-index --find-links=/wheelhouse_whisper -r /tmp/requirements.txt && \
    rm -rf /wheelhouse_whisper

COPY app.py /app/app.py

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
