#!/usr/bin/env python3

import asyncio
import os
import sys

async def test_ffmpeg_async():
    """Тест запуска ffmpeg через asyncio.create_subprocess_exec"""
    print("Тест запуска ffmpeg через asyncio.create_subprocess_exec")
    
    try:
        cmd = [
            'ffmpeg',
            '-i', 'videos/telegram_video_3736.mp4',
            '-vn',
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            '-y',
            'test_async.wav'
        ]
        
        print(f"Запускаю команду: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        print(f"Код возврата: {process.returncode}")
        
        if process.returncode == 0:
            if os.path.exists('test_async.wav') and os.path.getsize('test_async.wav') > 0:
                print(f"Успех! Файл создан, размер: {os.path.getsize('test_async.wav')} байт")
            else:
                print("Ошибка: Файл не создан или пустой")
        else:
            print(f"Ошибка ffmpeg: {stderr.decode()}")
    
    except Exception as e:
        print(f"Исключение: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_ffmpeg_async()) 