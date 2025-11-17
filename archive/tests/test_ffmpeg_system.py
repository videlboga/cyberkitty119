#!/usr/bin/env python3

import os
import sys

def test_ffmpeg_system():
    """Тест запуска ffmpeg через os.system"""
    print("Тест запуска ffmpeg через os.system")
    
    try:
        cmd = f'ffmpeg -i "videos/telegram_video_3736.mp4" -vn -acodec pcm_s16le -ar 44100 -ac 2 -y "test_system.wav"'
        
        print(f"Запускаю команду: {cmd}")
        
        return_code = os.system(cmd)
        
        print(f"Код возврата: {return_code}")
        
        if return_code == 0:
            if os.path.exists('test_system.wav') and os.path.getsize('test_system.wav') > 0:
                print(f"Успех! Файл создан, размер: {os.path.getsize('test_system.wav')} байт")
            else:
                print("Ошибка: Файл не создан или пустой")
        else:
            print(f"Ошибка ffmpeg, код возврата: {return_code}")
    
    except Exception as e:
        print(f"Исключение: {str(e)}")

if __name__ == "__main__":
    test_ffmpeg_system() 