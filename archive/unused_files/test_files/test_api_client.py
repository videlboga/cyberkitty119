#!/usr/bin/env python3
import requests
import sys
from pathlib import Path

def test_api_health():
    """Проверяем состояние API"""
    try:
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ API сервер работает")
            print(f"Ответ: {response.json()}")
            return True
        else:
            print(f"❌ API сервер недоступен: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка подключения к API: {e}")
        return False

def transcribe_video(video_path, format_with_llm=True):
    """Отправляем видео на транскрибацию"""
    video_file = Path(video_path)
    
    if not video_file.exists():
        print(f"❌ Видеофайл не найден: {video_path}")
        return None
    
    print(f"📤 Отправляю файл на транскрибацию: {video_file.name}")
    print(f"Размер файла: {video_file.stat().st_size / (1024*1024):.1f} МБ")
    
    try:
        with open(video_file, 'rb') as f:
            files = {'file': (video_file.name, f, 'video/mp4')}
            data = {'format_with_llm': format_with_llm}
            
            print("⏳ Отправляю запрос... (это может занять несколько минут)")
            response = requests.post(
                "http://localhost:8000/transcribe",
                files=files,
                data=data,
                timeout=600  # 10 минут таймаут
            )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Транскрибация завершена успешно!")
            print(f"Task ID: {result['task_id']}")
            print(f"Размер аудио: {result['audio_size_mb']} МБ")
            print(f"Длина транскрипции: {result['transcript_length']} символов")
            print(f"Отформатировано LLM: {result['formatted_with_llm']}")
            
            print("\n📝 Результат транскрибации:")
            print("=" * 50)
            print(result['formatted_transcript'][:1000] + "..." if len(result['formatted_transcript']) > 1000 else result['formatted_transcript'])
            print("=" * 50)
            
            return result
        else:
            print(f"❌ Ошибка транскрибации: {response.status_code}")
            print(f"Ответ: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка при отправке запроса: {e}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Использование: python test_api_client.py <путь_к_видеофайлу>")
        print("Пример: python test_api_client.py /home/cyberkitty/Videos/video1254700787.mp4")
        sys.exit(1)
    
    video_path = sys.argv[1]
    
    print("🔍 Проверяю состояние API сервера...")
    if not test_api_health():
        print("Убедитесь, что API сервер запущен: ./run_api_server.sh")
        sys.exit(1)
    
    print("\n🎬 Начинаю транскрибацию видео...")
    result = transcribe_video(video_path)
    
    if result:
        print(f"\n✅ Готово! Task ID: {result['task_id']}")
    else:
        print("\n❌ Транскрибация не удалась")
        sys.exit(1)

if __name__ == "__main__":
    main() 