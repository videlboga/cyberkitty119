#!/usr/bin/env python3
"""
Скрипт миграции базы данных для поддержки Telegram Stars
"""

import os
import sqlite3
from transkribator_modules.db.database import SessionLocal, init_database
from transkribator_modules.db.models import Base, engine

def migrate_database():
    """Миграция базы данных к новой схеме"""
    print("Начинаем миграцию базы данных...")
    
    # Подключаемся к базе данных
    db_path = "transkribator.db"
    
    if not os.path.exists(db_path):
        print("База данных не найдена, создаем новую...")
        init_database()
        print("✅ Новая база данных создана")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Проверяем, есть ли уже новые поля
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'amount_stars' in columns:
            print("✅ База данных уже обновлена")
            return
        
        print("Обновляем схему таблицы transactions...")
        
        # Создаем новую таблицу с правильной схемой
        cursor.execute("""
        CREATE TABLE transactions_new (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan_purchased VARCHAR NOT NULL,
            amount_rub FLOAT,
            amount_usd FLOAT,
            amount_stars INTEGER,
            currency VARCHAR DEFAULT 'RUB',
            status VARCHAR DEFAULT 'pending',
            payment_provider VARCHAR,
            provider_payment_charge_id VARCHAR,
            telegram_payment_charge_id VARCHAR,
            external_payment_id VARCHAR,
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """)
        
        # Копируем данные из старой таблицы
        cursor.execute("""
        INSERT INTO transactions_new (
            id, user_id, plan_purchased, amount_rub, amount_usd, 
            status, external_payment_id, created_at, completed_at
        )
        SELECT 
            id, user_id, plan_name, amount_rub, amount_usd,
            status, external_payment_id, created_at, completed_at
        FROM transactions
        """)
        
        # Удаляем старую таблицу и переименовываем новую
        cursor.execute("DROP TABLE transactions")
        cursor.execute("ALTER TABLE transactions_new RENAME TO transactions")
        
        conn.commit()
        print("✅ Миграция таблицы transactions завершена")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database() 