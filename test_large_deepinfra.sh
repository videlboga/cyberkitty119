# Тест DeepInfra API с большим файлом

source /root/transkribator/.env

echo "🎬 ТЕСТ ТРАНСКРИБАЦИИ БОЛЬШОГО ФАЙЛА"
echo "============================================"
echo ""
echo "📁 Файл: /tmp/test_large_video.mp3"
ls -lh /tmp/test_large_video.mp3
echo ""

# Получаем длительность аудио
duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /tmp/test_large_video.mp3 2>/dev/null)
minutes=$(echo "scale=1; $duration / 60" | bc)
echo "⏱️  Длительность: ${minutes} минут"
echo ""

echo "🚀 Отправляю на DeepInfra API..."
echo "⚠️  Это займёт несколько минут"
echo ""

start_time=$(date +%s)

curl -X POST "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo" \
  -H "Authorization: Bearer $DEEPINFRA_API_KEY" \
  -F "language=ru" \
  -F "audio=@/tmp/test_large_video.mp3" \
  --max-time 600 \
  -o /tmp/transcription_result.json \
  -w "\n\n⏱️  HTTP Code: %{http_code}\n⏱️  Time: %{time_total}s\n"

end_time=$(date +%s)
elapsed=$((end_time - start_time))

echo ""
echo "⏱️  Общее время: ${elapsed} секунд"
echo ""

if [ -f /tmp/transcription_result.json ]; then
    echo "📄 Результат (первые 1000 символов):"
    echo "============================================"
    cat /tmp/transcription_result.json | jq -r '.text' 2>/dev/null | head -c 1000
    echo ""
    echo "============================================"
    echo ""
    
    text_length=$(cat /tmp/transcription_result.json | jq -r '.text' 2>/dev/null | wc -c)
    echo "📊 Длина транскрипции: ${text_length} символов"
    
    echo ""
    echo "✅ ТЕСТ ПРОЙДЕН"
else
    echo "❌ ТЕСТ ПРОВАЛЕН - нет результата"
fi
