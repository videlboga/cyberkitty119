FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Создание необходимых директорий
RUN mkdir -p /app/data /app/videos /app/audio /app/transcriptions

# Копирование файлов требований
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY transkribator_modules/ ./transkribator_modules/

# Указание команды по умолчанию
CMD ["python", "-m", "transkribator_modules.main"] 