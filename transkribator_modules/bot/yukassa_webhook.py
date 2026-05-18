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
from transkribator_modules.payments.monitoring import record_yukassa_webhook_status


async def handle_yukassa_webhook(request: Request) -> JSONResponse:
    """Обрабатывает webhook от ЮКассы"""
    try:
        # Получаем данные webhook
        webhook_data = await request.json()
        logger.info(f"Получен webhook от ЮКассы: {webhook_data}")
        record_yukassa_webhook_status(
            "received",
            {
                "event": webhook_data.get("event"),
                "object_id": webhook_data.get("object", {}).get("id"),
            },
        )

        # Создаем сервис ЮКассы
        yukassa_service = YukassaPaymentService()

        # Обрабатываем webhook
        payment_info = yukassa_service.process_webhook(webhook_data)

        if not payment_info:
            logger.info("Webhook не требует обработки")
            record_yukassa_webhook_status(
                "ignored",
                {
                    "reason": "not_succeeded",
                    "event": webhook_data.get("event"),
                },
            )
            return JSONResponse(content={"status": "ignored"})

        # Получаем информацию о платеже
        payment_id = payment_info['payment_id']
        metadata = payment_info.get('metadata') or {}
        raw_user_id = metadata.get('user_id')
        plan_type = metadata.get('plan_type')
        amount = payment_info['amount']

        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            logger.error(
                "Некорректный user_id в метаданных платежа",
                extra={"payment_id": payment_id, "raw_user_id": raw_user_id},
            )
            record_yukassa_webhook_status(
                "error",
                {
                    "payment_id": payment_id,
                    "user_id": raw_user_id,
                    "error": "invalid_user_id",
                },
            )
            return JSONResponse(
                content={"status": "error", "message": "invalid user_id"},
                status_code=400,
            )

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
                payment_method="yukassa",
                currency="RUB",
                external_payment_id=payment_id,
            )

            # Обновляем план пользователя
            upgrade_success = user_service.upgrade_user_plan(db_user, plan_type)
            if upgrade_success:
                logger.info(f"Подписка пользователя {user_id} успешно обновлена до плана {plan_type}")
            else:
                logger.error(f"Ошибка при обновлении плана пользователя {user_id} до {plan_type}")

            record_yukassa_webhook_status(
                "success",
                {
                    "payment_id": payment_id,
                    "user_id": user_id,
                    "plan_type": plan_type,
                },
            )
            return JSONResponse(content={"status": "success"})

        except Exception as e:
            logger.error(f"Ошибка при обработке платежа ЮКассы: {e}")
            record_yukassa_webhook_status(
                "error",
                {
                    "payment_id": payment_id,
                    "user_id": user_id,
                    "error": str(e),
                },
            )
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при обработке webhook ЮКассы: {e}")
        record_yukassa_webhook_status("error", {"exception": str(e)})
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


def setup_yukassa_webhook(app: FastAPI) -> None:
    """Настраивает webhook для ЮКассы"""
    app.post("/webhook/yukassa")(handle_yukassa_webhook)
    logger.info("Webhook ЮКассы настроен: /webhook/yukassa")
