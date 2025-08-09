#!/usr/bin/env python3

import subprocess
import os
import sys

def test_ffmpeg_subprocess_run():
    """Тест запуска ffmpeg через subprocess.run"""
    print("Тест запуска ffmpeg через subprocess.run")
    
    try:
        cmd = [
            'ffmpeg',
            '-i', 'videos/telegram_video_3736.mp4',
            '-vn',
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            '-y',
            'test_subprocess_run.wav'
        ]
        
        print(f"Запускаю команду: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        print(f"Код возврата: {result.returncode}")
        
        if result.returncode == 0:
            if os.path.exists('test_subprocess_run.wav') and os.path.getsize('test_subprocess_run.wav') > 0:
                print(f"Успех! Файл создан, размер: {os.path.getsize('test_subprocess_run.wav')} байт")
            else:
                print("Ошибка: Файл не создан или пустой")
        else:
            print(f"Ошибка ffmpeg: {result.stderr}")
    
    except Exception as e:
        print(f"Исключение: {str(e)}")

if __name__ == "__main__":
    test_ffmpeg_subprocess_run() 