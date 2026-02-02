#!/usr/bin/env python3
"""
Скрипт для анализа использования минут пользователями
"""

import os
import sys
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def main():
    # Получаем URL базы данных
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        return

    print(f"🔗 Подключение к базе данных: {database_url.replace(database_url.split('@')[0], '***:***')}")

    try:
        # Создаем подключение
        engine = create_engine(database_url, pool_pre_ping=True)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Запрос 1: Статистика по пользователям из таблицы users
        print("\n📊 Статистика по пользователям (из таблицы users):")
        print("-" * 80)

        query_users = text("""
            SELECT
                telegram_id,
                username,
                first_name || ' ' || COALESCE(last_name, '') as full_name,
                total_minutes_transcribed,
                minutes_used_this_month,
                current_plan,
                created_at
            FROM users
            WHERE is_active = true
            ORDER BY total_minutes_transcribed DESC
        """)

        result_users = session.execute(query_users)
        users_data = result_users.fetchall()

        total_users = len(users_data)
        total_minutes_all = sum(user.total_minutes_transcribed for user in users_data)
        avg_minutes_per_user = total_minutes_all / total_users if total_users > 0 else 0

        print(f"👥 Всего активных пользователей: {total_users}")
        print(".2f"        print(".2f"
        print("\n📋 Топ пользователей по использованию минут:")
        print("Telegram ID | Имя | Минут всего | Минут в мес | План")
        print("-" * 80)

        for user in users_data[:20]:  # Показываем топ 20
            name = user.full_name.strip() or user.username or f"ID:{user.telegram_id}"
            print("10d")

        # Запрос 2: Статистика по транскрибациям
        print("\n🎵 Статистика по транскрибациям:")
        print("-" * 80)

        query_transcriptions = text("""
            SELECT
                COUNT(*) as total_transcriptions,
                SUM(audio_duration_minutes) as total_minutes_transcribed,
                AVG(audio_duration_minutes) as avg_duration,
                MIN(audio_duration_minutes) as min_duration,
                MAX(audio_duration_minutes) as max_duration
            FROM transcriptions
            WHERE user_id IS NOT NULL
        """)

        result_transcriptions = session.execute(query_transcriptions)
        trans_data = result_transcriptions.fetchone()

        print(f"📝 Всего транскрибаций: {trans_data.total_transcriptions}")
        print(".2f"        print(".2f"        print(".2f"        print(".2f"
        # Запрос 3: Минуты по пользователям из транскрибаций
        print("\n📈 Минуты по пользователям (из транскрибаций):")
        print("-" * 80)

        query_user_minutes = text("""
            SELECT
                u.telegram_id,
                u.username,
                u.first_name || ' ' || COALESCE(u.last_name, '') as full_name,
                COUNT(t.id) as transcription_count,
                SUM(t.audio_duration_minutes) as total_minutes_from_transcriptions,
                u.total_minutes_transcribed as total_minutes_from_users,
                u.minutes_used_this_month
            FROM users u
            LEFT JOIN transcriptions t ON u.id = t.user_id
            WHERE u.is_active = true
            GROUP BY u.id, u.telegram_id, u.username, u.first_name, u.last_name, u.total_minutes_transcribed, u.minutes_used_this_month
            ORDER BY total_minutes_from_transcriptions DESC NULLS LAST
        """)

        result_user_minutes = session.execute(query_user_minutes)
        user_minutes_data = result_user_minutes.fetchall()

        print("Telegram ID | Имя | Транскрибаций | Минут (транскр) | Минут (пользователь)")
        print("-" * 100)

        for user in user_minutes_data[:15]:  # Показываем топ 15
            name = user.full_name.strip() or user.username or f"ID:{user.telegram_id}"
            transcr_minutes = user.total_minutes_from_transcriptions or 0
            user_minutes = user.total_minutes_from_users or 0
            print("10d")

        # Запрос 4: API ключи
        print("\n🔑 Статистика по API ключам:")
        print("-" * 80)

        query_api_keys = text("""
            SELECT
                COUNT(*) as total_api_keys,
                SUM(minutes_used) as total_api_minutes,
                AVG(minutes_used) as avg_api_minutes
            FROM api_keys
            WHERE is_active = true
        """)

        result_api = session.execute(query_api_keys)
        api_data = result_api.fetchone()

        print(f"🔑 Всего активных API ключей: {api_data.total_api_keys}")
        print(".2f"        print(".2f"
        # Финальная сводка
        print("\n📊 СВОДКА:")
        print("=" * 80)
        print(f"👥 Активных пользователей: {total_users}")
        print(".2f"        print(".2f"        print(f"📝 Всего транскрибаций: {trans_data.total_transcriptions}")
        print(".2f"        print(".2f"        print(f"🔑 API ключей: {api_data.total_api_keys}")
        print(".2f"
        session.close()

    except Exception as e:
        print(f"❌ Ошибка при работе с базой данных: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()