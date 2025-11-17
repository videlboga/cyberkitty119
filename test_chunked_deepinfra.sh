# Тест параллельной транскрибации через DeepInfra

source /root/transkribator/.env

echo "🧪 ТЕСТ ТРАНСКРИБАЦИИ С РАЗБИВКОЙ НА ЧАНКИ"
echo "============================================"
echo ""

TEST_FILE="/tmp/test_large_video.mp3"

# Проверяем файл
if [ ! -f "$TEST_FILE" ]; then
    echo "❌ Тестовый файл не найден: $TEST_FILE"
    exit 1
fi

echo "📁 Тестовый файл: $TEST_FILE"
ls -lh $TEST_FILE
echo ""

# Получаем длительность
duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $TEST_FILE 2>/dev/null)
minutes=$(echo "scale=1; $duration / 60" | bc)
echo "⏱️  Длительность: ${minutes} минут"
echo ""

# Разбиваем на чанки по 30 минут
echo "✂️  Разбиваю на чанки по 30 минут..."
CHUNK_DIR="/tmp/deepinfra_chunks_$$"
mkdir -p $CHUNK_DIR

ffmpeg -i $TEST_FILE \
  -f segment \
  -segment_time 1800 \
  -c copy \
  -reset_timestamps 1 \
  $CHUNK_DIR/chunk_%03d.mp3 \
  -y 2>&1 | grep -E "Output|segment|time="

echo ""
echo "📊 Созданные чанки:"
ls -lh $CHUNK_DIR/
echo ""

# Подсчитываем количество чанков
chunk_count=$(ls -1 $CHUNK_DIR/chunk_*.mp3 2>/dev/null | wc -l)
echo "✅ Создано $chunk_count чанков"
echo ""

# Транскрибируем первые 2 чанка для теста
echo "🚀 Транскрибирую первые 2 чанка для теста..."
echo ""

for chunk_file in $CHUNK_DIR/chunk_000.mp3 $CHUNK_DIR/chunk_001.mp3; do
    if [ -f "$chunk_file" ]; then
        chunk_name=$(basename $chunk_file)
        chunk_duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $chunk_file 2>/dev/null)
        chunk_minutes=$(echo "scale=1; $chunk_duration / 60" | bc)
        chunk_size=$(ls -lh $chunk_file | awk '{print $5}')
        
        echo "📝 Чанк: $chunk_name"
        echo "   Размер: $chunk_size"
        echo "   Длительность: ${chunk_minutes} минут"
        echo "   Отправляю на DeepInfra..."
        
        start_time=$(date +%s)
        
        result=$(curl -s -X POST "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo" \
          -H "Authorization: Bearer $DEEPINFRA_API_KEY" \
          -F "language=ru" \
          -F "audio=@$chunk_file" \
          --max-time 600 \
          -w "\nHTTP_CODE:%{http_code}\nTIME:%{time_total}" 2>&1)
        
        end_time=$(date +%s)
        elapsed=$((end_time - start_time))
        
        http_code=$(echo "$result" | grep "HTTP_CODE:" | cut -d: -f2)
        time_total=$(echo "$result" | grep "TIME:" | cut -d: -f2)
        
        if [ "$http_code" = "200" ]; then
            text_length=$(echo "$result" | jq -r '.text' 2>/dev/null | wc -c)
            echo "   ✅ Успешно! HTTP 200"
            echo "   ⏱️  Время: ${time_total}s"
            echo "   📏 Длина текста: ${text_length} символов"
            
            # Показываем первые 200 символов
            preview=$(echo "$result" | jq -r '.text' 2>/dev/null | head -c 200)
            echo "   📄 Превью: ${preview}..."
        else
            echo "   ❌ Ошибка! HTTP $http_code"
            echo "   ⏱️  Время: ${elapsed}s"
            error_msg=$(echo "$result" | head -c 300)
            echo "   📄 Ответ: ${error_msg}"
        fi
        
        echo ""
    fi
done

# Очищаем чанки
echo "🗑️  Удаляю временные чанки..."
rm -rf $CHUNK_DIR
echo "✅ Удалено"

echo ""
echo "============================================"
echo "✅ ТЕСТ ЗАВЕРШЁН"
