# Тест DeepInfra API с продового окружения

echo "🔍 Проверяю DEEPINFRA_API_KEY..."
if [ -z "$DEEPINFRA_API_KEY" ]; then
    echo "❌ DEEPINFRA_API_KEY не установлен"
    echo "Попробую взять из .env..."
    source /root/transkribator/.env 2>/dev/null
    if [ -z "$DEEPINFRA_API_KEY" ]; then
        echo "❌ Не найден в .env"
        exit 1
    fi
fi

echo "✅ API Key найден: ${DEEPINFRA_API_KEY:0:10}...${DEEPINFRA_API_KEY: -5}"
echo ""

# Создаём тестовый короткий wav файл (1 секунда тишины)
echo "📝 Создаю тестовый аудио файл..."
ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 1 -acodec pcm_s16le /tmp/test_deepinfra.wav -y 2>/dev/null

if [ ! -f /tmp/test_deepinfra.wav ]; then
    echo "❌ Не удалось создать тестовый файл"
    exit 1
fi

echo "✅ Тестовый файл создан: /tmp/test_deepinfra.wav"
ls -lh /tmp/test_deepinfra.wav
echo ""

# Отправляем на DeepInfra
echo "🚀 Отправляю запрос на DeepInfra API..."
echo "URL: https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo"
echo ""

curl -X POST "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo"   -H "Authorization: Bearer $DEEPINFRA_API_KEY"   -F "language=ru"   -F "audio=@/tmp/test_deepinfra.wav"   -w "\n\n⏱️  HTTP Code: %{http_code}\n⏱️  Time: %{time_total}s\n"   --max-time 60

echo ""
echo "✅ Тест завершён"

# Удаляем тестовый файл
rm -f /tmp/test_deepinfra.wav
