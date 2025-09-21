#!/usr/bin/env python3
"""
Тестовый скрипт для отладки интеграции с ЮКассой
"""

import sys
import os
sys.path.append('/root/transkribator')

from transkribator_modules.config import logger, YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY, YUKASSA_DEFAULT_EMAIL, YUKASSA_VAT_CODE, YUKASSA_TAX_SYSTEM_CODE
from transkribator_modules.payments.yukassa import YukassaPaymentService

def test_yukassa_config():
    """Тестирует конфигурацию ЮКассы"""
    print("🔧 Проверка конфигурации ЮКассы:")
    print(f"  Shop ID: {YUKASSA_SHOP_ID}")
    print(f"  Secret Key: {YUKASSA_SECRET_KEY[:20]}..." if YUKASSA_SECRET_KEY else "  Secret Key: НЕ УСТАНОВЛЕН")
    print(f"  Default Email: {YUKASSA_DEFAULT_EMAIL}")
    print(f"  VAT Code: {YUKASSA_VAT_CODE}")
    print(f"  Tax System Code: {YUKASSA_TAX_SYSTEM_CODE}")
    print()

def test_yukassa_service_init():
    """Тестирует инициализацию сервиса ЮКассы"""
    print("🚀 Тестирование инициализации сервиса ЮКассы:")
    try:
        service = YukassaPaymentService()
        print("  ✅ Сервис ЮКассы успешно инициализирован")
        return service
    except Exception as e:
        print(f"  ❌ Ошибка инициализации: {e}")
        return None

def test_payment_creation(service):
    """Тестирует создание платежа"""
    if not service:
        print("❌ Сервис не инициализирован, пропускаем тест создания платежа")
        return

    print("💳 Тестирование создания платежа:")
    try:
        # Тестовые данные
        user_id = 12345
        plan_type = "pro"
        amount = 299.0
        description = "Тестовый платеж"

        print(f"  Создаем платеж:")
        print(f"    User ID: {user_id}")
        print(f"    Plan: {plan_type}")
        print(f"    Amount: {amount} RUB")
        print(f"    Description: {description}")

        payment_result = service.create_payment(
            user_id=user_id,
            plan_type=plan_type,
            amount=amount,
            description=description
        )

        print("  ✅ Платеж успешно создан:")
        print(f"    Payment ID: {payment_result['payment_id']}")
        print(f"    Status: {payment_result['status']}")
        print(f"    Confirmation URL: {payment_result['confirmation_url']}")

    except Exception as e:
        print(f"  ❌ Ошибка создания платежа: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Основная функция тестирования"""
    print("🏦 Тестирование интеграции с ЮКассой")
    print("=" * 50)

    # Тест 1: Конфигурация
    test_yukassa_config()

    # Тест 2: Инициализация сервиса
    service = test_yukassa_service_init()

    # Тест 3: Создание платежа
    test_payment_creation(service)

    print("=" * 50)
    print("🏁 Тестирование завершено")

if __name__ == "__main__":
    main()


