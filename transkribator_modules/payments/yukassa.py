"""
Модуль для интеграции с ЮKassa
Обработка платежей через ЮKassa API
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from yookassa import Payment, Configuration
from yookassa.domain.request import PaymentRequest

from transkribator_modules.config import logger
from transkribator_modules.db.models import PlanType

class YukassaPaymentService:
    """Сервис для работы с платежами через ЮKassa"""
    
    def __init__(self):
        """Инициализация сервиса ЮKassa"""
        # Получаем настройки из переменных окружения
        shop_id = os.getenv('YUKASSA_SHOP_ID')
        secret_key = os.getenv('YUKASSA_SECRET_KEY')
        
        if not shop_id or not secret_key:
            logger.error("ЮKassa не настроен: отсутствуют YUKASSA_SHOP_ID или YUKASSA_SECRET_KEY")
            raise ValueError("ЮKassa не настроен")
        
        # Инициализируем ЮKassa
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key
        
        self.shop_id = shop_id
        self.secret_key = secret_key
        logger.info(f"ЮKassa инициализирован для магазина {shop_id}")
    
    def create_payment(self, user_id: int, plan_type: str, amount: float, 
                      description: str = None, receipt: dict = None) -> Dict[str, Any]:
        """
        Создает платеж в ЮKassa
        
        Args:
            user_id: ID пользователя Telegram
            plan_type: Тип плана (basic, pro, unlimited)
            amount: Сумма в рублях
            description: Описание платежа
            receipt: dict с чеком (обязательно для РФ)
            
        Returns:
            Dict с данными платежа (id, confirmation_url, status)
        """
        try:
            # Генерируем уникальный ID платежа
            payment_id = str(uuid.uuid4())
            
            # Создаем запрос на платеж
            payment_request = PaymentRequest(
                amount={
                    "value": str(amount),
                    "currency": "RUB"
                },
                confirmation={
                    "type": "redirect",
                    "return_url": f"https://t.me/CyberKitty19_bot?start=payment_{payment_id}"
                },
                capture=True,
                description=description or f"План {plan_type} для пользователя {user_id}",
                metadata={
                    "user_id": user_id,
                    "plan_type": plan_type,
                    "payment_id": payment_id
                },
                receipt=receipt if receipt else None
            )
            
            # Создаем платеж
            payment = Payment.create(payment_request)
            
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
        """
        Проверяет статус платежа
        
        Args:
            payment_id: ID платежа в ЮKassa
            
        Returns:
            Dict с данными платежа или None если не найден
        """
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
        """
        Возвращает цену плана в рублях
        
        Args:
            plan_type: Тип плана
            
        Returns:
            Цена в рублях
        """
        prices = {
            PlanType.BASIC: 599.0,      # Базовый план
            PlanType.PRO: 2990.0,       # Продвинутый план
            PlanType.UNLIMITED: 9990.0  # Безлимитный план
        }
        
        return prices.get(plan_type, 0.0)
    
    def get_plan_description(self, plan_type: str) -> str:
        """
        Возвращает описание плана
        
        Args:
            plan_type: Тип плана
            
        Returns:
            Описание плана
        """
        descriptions = {
            PlanType.BASIC: "Базовый план - 180 минут в месяц",
            PlanType.PRO: "Профессиональный план - 600 минут в месяц + API",
            PlanType.UNLIMITED: "Безлимитный план - без ограничений + VIP"
        }
        
        return descriptions.get(plan_type, "Неизвестный план")
    
    def process_webhook(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает webhook от ЮKassa
        
        Args:
            webhook_data: Данные webhook'а
            
        Returns:
            Dict с данными платежа или None если ошибка
        """
        try:
            # Проверяем, что это уведомление о платеже
            if webhook_data.get('event') != 'payment.succeeded':
                logger.info(f"Получен webhook с событием: {webhook_data.get('event')}")
                return None
            
            # Получаем данные платежа
            payment_data = webhook_data.get('object', {})
            payment_id = payment_data.get('id')
            
            if not payment_id:
                logger.error("Webhook не содержит ID платежа")
                return None
            
            # Проверяем платеж
            payment_info = self.verify_payment(payment_id)
            
            if payment_info and payment_info['status'] == 'succeeded':
                logger.info(f"Платеж {payment_id} успешно обработан")
                return payment_info
            else:
                logger.warning(f"Платеж {payment_id} не подтвержден")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка обработки webhook ЮKassa: {e}")
            return None 