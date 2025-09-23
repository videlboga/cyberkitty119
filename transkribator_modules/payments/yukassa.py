"""
Модуль для интеграции с ЮKassa
Обработка платежей через ЮKassa API
"""

import os
import uuid
from typing import Optional, Dict, Any
from yookassa import Payment, Configuration

from transkribator_modules.config import logger, YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY, YUKASSA_DEFAULT_EMAIL, YUKASSA_VAT_CODE, YUKASSA_TAX_SYSTEM_CODE
from transkribator_modules.db.models import PlanType


class YukassaPaymentService:
    """Сервис для работы с платежами через ЮKassa"""

    def __init__(self):
        """Инициализация сервиса ЮKassa"""
        # Используем конфигурацию из config.py
        shop_id = YUKASSA_SHOP_ID
        secret_key = YUKASSA_SECRET_KEY
        self.default_customer_email = YUKASSA_DEFAULT_EMAIL
        self.vat_code = YUKASSA_VAT_CODE
        self.tax_system_code = YUKASSA_TAX_SYSTEM_CODE

        if not shop_id or not secret_key:
            logger.error("ЮKassa не настроен: отсутствуют YUKASSA_SHOP_ID или YUKASSA_SECRET_KEY")
            raise ValueError("ЮKassa не настроен")

        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key
        self.shop_id = shop_id
        self.secret_key = secret_key
        logger.info(f"ЮKassa инициализирован для магазина {shop_id}")

    def create_payment(self, user_id: int, plan_type: str, amount: float,
                       description: str = "", receipt: dict | None = None) -> Dict[str, Any]:
        """
        Создает платеж в ЮKassa
        """
        try:
            payment_id = str(uuid.uuid4())

            # Собираем чек (receipt) — обязателен в ряде режимов ЮKassa
            auto_receipt: Dict[str, Any] = {
                "customer": {"email": self.default_customer_email},
                "items": [
                    {
                        "description": f"Подписка {str(plan_type).upper()}",
                        "quantity": "1.00",
                        "amount": {"value": f"{float(amount):.2f}", "currency": "RUB"},
                        "vat_code": self.vat_code,
                        "payment_subject": "service",
                        "payment_mode": "full_prepayment",
                    }
                ],
            }
            if self.tax_system_code:
                try:
                    auto_receipt["tax_system_code"] = int(self.tax_system_code)
                except Exception:
                    pass

            # Если передан кастомный receipt — аккуратно объединяем с автогенерированным
            final_receipt = auto_receipt.copy()
            if isinstance(receipt, dict):
                try:
                    incoming_customer = receipt.get("customer") or {}
                    if isinstance(incoming_customer, dict):
                        # Перекрываем email/phone из пользовательских данных
                        for k in ("email", "phone"):
                            v = incoming_customer.get(k)
                            if v:
                                final_receipt.setdefault("customer", {})[k] = v
                    incoming_items = receipt.get("items")
                    if isinstance(incoming_items, list) and incoming_items:
                        final_receipt["items"] = incoming_items
                    if isinstance(receipt.get("tax_system_code"), int):
                        final_receipt["tax_system_code"] = receipt["tax_system_code"]
                except Exception:
                    # На любой проблеме просто используем auto_receipt
                    final_receipt = auto_receipt

            payment_data: Dict[str, Any] = {
                "amount": {
                    "value": f"{float(amount):.2f}",
                    "currency": "RUB",
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/{os.getenv('BOT_USERNAME','') }?start=payment_{payment_id}",
                },
                "capture": True,
                "description": (description or f"План {plan_type} для пользователя {user_id}")[:128],
                "metadata": {
                    "user_id": user_id,
                    "plan_type": plan_type,
                    "payment_id": payment_id,
                },
                "receipt": final_receipt,
            }

            # Рекомендуется использовать идемпотентный ключ (передаем позиционным аргументом)
            payment = Payment.create(payment_data, payment_id)
            logger.info(f"Создан платеж ЮKassa: {payment.id} для пользователя {user_id}")

            return {
                "payment_id": payment.id,
                "confirmation_url": payment.confirmation.confirmation_url,
                "status": payment.status,
                "amount": amount,
                "currency": "RUB",
                "metadata": {
                    "user_id": user_id,
                    "plan_type": plan_type,
                    "internal_payment_id": payment_id
                }
            }
        except Exception as e:
            logger.error(f"Ошибка создания платежа ЮKassa: {e}")
            raise

    def verify_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Проверяет статус платежа"""
        try:
            payment = Payment.find_one(payment_id)
            return {
                "payment_id": payment.id,
                "status": payment.status,
                "amount": float(payment.amount.value),
                "currency": payment.amount.currency,
                "metadata": payment.metadata,
                "created_at": payment.created_at,
                "paid_at": payment.paid_at
            }
        except Exception as e:
            logger.error(f"Ошибка проверки платежа ЮKassa {payment_id}: {e}")
            return None

    def get_plan_price(self, plan_type: str) -> float:
        prices = {
            PlanType.PRO.value: 299.0,
            PlanType.UNLIMITED.value: 699.0,
        }
        return prices.get(plan_type, 0.0)

    def get_plan_description(self, plan_type: str) -> str:
        descriptions = {
            PlanType.PRO.value: "PRO план — 600 минут в месяц + API доступ",
            PlanType.UNLIMITED.value: "UNLIMITED план — безлимитно + VIP функции",
        }
        return descriptions.get(plan_type, "Неизвестный план")

    def process_webhook(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обрабатывает webhook от ЮKassa"""
        try:
            if webhook_data.get('event') != 'payment.succeeded':
                logger.info(f"Получен webhook с событием: {webhook_data.get('event')}")
                return None

            payment_data = webhook_data.get('object', {})
            payment_id = payment_data.get('id')
            if not payment_id:
                logger.error("Webhook не содержит ID платежа")
                return None

            payment_info = self.verify_payment(payment_id)
            if payment_info and payment_info['status'] == 'succeeded':
                logger.info(f"Платеж {payment_id} успешно подтвержден")
                return payment_info
            return None
        except Exception as e:
            logger.error(f"Ошибка обработки webhook ЮKassa: {e}")
            return None
