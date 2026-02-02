FROM pytorch/pytorch:2.2.0-cuda11.8-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install system deps required to build / run PyAV and other libs
RUN apt-get update && apt-get install -y --no-install-recommends \
	build-essential \
	pkg-config \
	ffmpeg \
	libavcodec-dev libavformat-dev libavdevice-dev libavutil-dev libswresample-dev libavfilter-dev \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
# Ensure pip and wheel are up to date
RUN pip3 install --upgrade pip wheel setuptools && \
	pip3 install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
