FROM python:3.10-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем файлы с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файлы проекта
COPY transkribator_modules/ ./transkribator_modules/
COPY .env .

# Создаем необходимые директории
RUN mkdir -p /app/videos /app/audio /app/transcriptions

# Запускаем модульного бота
CMD ["python", "-m", "transkribator_modules.main"] 