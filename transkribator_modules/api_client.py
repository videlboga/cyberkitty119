#!/usr/bin/env python3
"""
API клиент для работы бота с локальным API сервером
"""

import asyncio
import aiohttp
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from transkribator_modules.config import logger

class LocalAPIClient:
    """Клиент для работы с локальным API сервером"""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        timeout = aiohttp.ClientTimeout(total=300)  # 5 минут для больших файлов
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                'User-Agent': 'CyberKitty-Bot/2.0',
                'Accept': 'application/json'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        if self.session:
            await self.session.close()
            
    def _get_headers(self) -> Dict[str, str]:
        """Получить заголовки для запросов"""
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
            headers['X-API-Key'] = self.api_key
        return headers
        
    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния API сервера"""
        if not self.session:
            raise RuntimeError("Сессия не инициализирована. Используйте async with")
            
        async with self.session.get(f"{self.base_url}/health") as response:
            return await response.json()
            
    async def get_plans(self) -> List[Dict[str, Any]]:
        """Получить список доступных планов"""
        if not self.session:
            raise RuntimeError("Сессия не инициализирована. Используйте async with")
            
        async with self.session.get(f"{self.base_url}/plans") as response:
            return await response.json()
            
    async def get_user_info(self) -> Dict[str, Any]:
        """Получить информацию о пользователе"""
        if not self.session:
            raise RuntimeError("Сессия не инициализирована. Используйте async with")
            
        headers = self._get_headers()
        async with self.session.get(f"{self.base_url}/user/info", headers=headers) as response:
            if response.status == 401:
                raise ValueError("Недействительный API ключ")
            return await response.json()
            
    async def transcribe_file(self, file_path: Path, format_with_llm: bool = True) -> Dict[str, Any]:
        """Отправить файл на транскрибацию"""
        if not self.session:
            raise RuntimeError("Сессия не инициализирована. Используйте async with")
            
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
            
        headers = self._get_headers()
        data = aiohttp.FormData()
        
        # Добавляем файл
        data.add_field('file', open(file_path, 'rb'), filename=file_path.name)
            
        # Добавляем параметры
        data.add_field('format_with_llm', str(format_with_llm).lower())
        
        logger.info(f"Отправляю файл {file_path.name} ({file_path.stat().st_size} байт) на транскрибацию")
        
        async with self.session.post(
            f"{self.base_url}/transcribe", 
            data=data,
            headers=headers
        ) as response:
            if response.status == 401:
                raise ValueError("Недействительный API ключ")
            elif response.status == 413:
                raise ValueError("Файл слишком большой")
            elif response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"Ошибка транскрибации: {response.status} - {error_text}")
                
            return await response.json()
            
    async def check_transcription_status(self, task_id: str) -> Dict[str, Any]:
        """Проверить статус транскрибации"""
        if not self.session:
            raise RuntimeError("Сессия не инициализирована. Используйте async with")
            
        headers = self._get_headers()
        async with self.session.get(
            f"{self.base_url}/transcription/{task_id}/status",
            headers=headers
        ) as response:
            if response.status == 404:
                raise ValueError(f"Задача {task_id} не найдена")
            return await response.json()


class MockTelegramBot:
    """Мок-объект для эмуляции Telegram бота при работе с локальным API"""
    
    def __init__(self, api_client: LocalAPIClient):
        self.api_client = api_client
        
    async def send_message(self, chat_id: int, text: str, **kwargs) -> Dict[str, Any]:
        """Отправить сообщение (эмулирует Telegram API)"""
        logger.info(f"[MOCK] Отправка сообщения в чат {chat_id}: {text[:100]}...")
        return {
            'message_id': int(datetime.now().timestamp()),
            'chat': {'id': chat_id},
            'text': text
        }
        
    async def edit_message_text(self, chat_id: int, message_id: int, text: str, **kwargs) -> Dict[str, Any]:
        """Редактировать сообщение (эмулирует Telegram API)"""
        logger.info(f"[MOCK] Редактирование сообщения {message_id} в чате {chat_id}: {text[:100]}...")
        return {
            'message_id': message_id,
            'chat': {'id': chat_id},
            'text': text
        }
        
    async def send_document(self, chat_id: int, document: Path, caption: str = None, **kwargs) -> Dict[str, Any]:
        """Отправить документ (эмулирует Telegram API)"""
        logger.info(f"[MOCK] Отправка документа {document.name} в чат {chat_id}")
        return {
            'message_id': int(datetime.now().timestamp()),
            'chat': {'id': chat_id},
            'document': {'file_name': document.name}
        }


# Глобальный экземпляр клиента
api_client: Optional[LocalAPIClient] = None
mock_bot: Optional[MockTelegramBot] = None

def initialize_api_client(base_url: str = None, api_key: str = None) -> LocalAPIClient:
    """Инициализировать глобальный API клиент"""
    global api_client, mock_bot
    
    if base_url is None:
        base_url = "http://localhost:8000"
        
    api_client = LocalAPIClient(base_url, api_key)
    mock_bot = MockTelegramBot(api_client)
    
    logger.info(f"API клиент инициализирован: {base_url}")
    return api_client

def get_api_client() -> LocalAPIClient:
    """Получить глобальный API клиент"""
    if api_client is None:
        raise RuntimeError("API клиент не инициализирован. Вызовите initialize_api_client()")
    return api_client

def get_mock_bot() -> MockTelegramBot:
    """Получить мок-бот"""
    if mock_bot is None:
        raise RuntimeError("Мок-бот не инициализирован. Вызовите initialize_api_client()")
    return mock_bot 