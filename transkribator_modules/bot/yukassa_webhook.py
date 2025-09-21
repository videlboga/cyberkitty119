"""
Webhook обработчик для ЮКассы
"""

import json
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from transkribator_modules.config import logger
from transkribator_modules.payments.yukassa import YukassaPaymentService
from transkribator_modules.db.database import SessionLocal, UserService, TransactionService


async def handle_yukassa_webhook(request: Request) -> JSONResponse:
    """Обрабатывает webhook от ЮКассы"""
    try:
        # Получаем данные webhook
        webhook_data = await request.json()
        logger.info(f"Получен webhook от ЮКассы: {webhook_data}")

        # Создаем сервис ЮКассы
        yukassa_service = YukassaPaymentService()

        # Обрабатываем webhook
        payment_info = yukassa_service.process_webhook(webhook_data)

        if not payment_info:
            logger.info("Webhook не требует обработки")
            return JSONResponse(content={"status": "ignored"})

        # Получаем информацию о платеже
        payment_id = payment_info['payment_id']
        user_id = payment_info['metadata'].get('user_id')
        plan_type = payment_info['metadata'].get('plan_type')
        amount = payment_info['amount']

        logger.info(f"Обрабатываем успешный платеж {payment_id} от пользователя {user_id}")

        # Обновляем подписку пользователя в базе данных
        db = SessionLocal()
        try:
            user_service = UserService(db)
            transaction_service = TransactionService(db)

            # Получаем пользователя
            db_user = user_service.get_or_create_user(telegram_id=user_id)

            # Создаем транзакцию
            transaction = transaction_service.create_transaction(
                user=db_user,
                plan_type=plan_type,
                amount_rub=amount,
                amount_stars=0,
                payment_method="yukassa"
            )

            # Обновляем план пользователя
            upgrade_success = user_service.upgrade_user_plan(db_user, plan_type)
            if upgrade_success:
                logger.info(f"Подписка пользователя {user_id} успешно обновлена до плана {plan_type}")
            else:
                logger.error(f"Ошибка при обновлении плана пользователя {user_id} до {plan_type}")

            return JSONResponse(content={"status": "success"})

        except Exception as e:
            logger.error(f"Ошибка при обработке платежа ЮКассы: {e}")
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при обработке webhook ЮКассы: {e}")
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


def setup_yukassa_webhook(app: FastAPI) -> None:
    """Настраивает webhook для ЮКассы"""
    app.post("/webhook/yukassa")(handle_yukassa_webhook)
    logger.info("Webhook ЮКассы настроен: /webhook/yukassa")
