import asyncio
import random
from datetime import datetime, timedelta
from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService

class MarketingManager:
    """Менеджер маркетинговых уведомлений и акций"""
    
    def __init__(self, bot):
        self.bot = bot
        self.promo_messages = [
            {
                "text": "🎁 **Пятничная акция!** Промокод `FRIDAY30` дает скидку 30% на все тарифы!\n\n"
                       "💡 Действует только до воскресенья! Поторопись!",
                "day": 4  # Пятница
            },
            {
                "text": "🚀 **Новая неделя — новые возможности!** \n\n"
                       "📈 Обнови тариф и получи +25% бонусных минут в подарок!\n\n"
                       "⭐ /plans — смотреть все тарифы",
                "day": 0  # Понедельник
            },
            {
                "text": "🎯 **Середина недели!** Самое время для продуктивности!\n\n"
                       "💎 Промокод `СРЕДА20` — скидка 20% на профессиональный тариф\n\n"
                       "🔥 Успей до четверга!",
                "day": 2  # Среда
            }
        ]
        
        self.limit_reminders = [
            "🔔 **Напоминание:** У тебя осталось мало минут для транскрибации в этом месяце!\n\n"
            "💡 Обнови тариф и получи безлимитный доступ!",
            
            "⏰ **Дружеское напоминание:** Твой лимит почти исчерпан!\n\n" 
            "🎁 Специальная скидка 15% при обновлении сегодня!",
            
            "📢 **Последнее предупреждение:** У тебя остались считанные минуты!\n\n"
            "🚀 Обновись сейчас и продолжи транскрибировать без ограничений!"
        ]
    
    async def send_daily_promo(self):
        """(Отключено) Ранее отправляло ежедневные промо-сообщения. Теперь не используется."""
        logger.info("send_daily_promo вызван, но функция отключена и ничего не делает.")
        return
    
    async def send_limit_reminder(self, user_telegram_id, remaining_minutes):
        """Отправляет напоминание о лимитах"""
        try:
            if remaining_minutes <= 5:  # Критический лимит
                message = self.limit_reminders[2]
            elif remaining_minutes <= 15:  # Низкий лимит
                message = self.limit_reminders[1]
            else:  # Предупреждение
                message = self.limit_reminders[0]
            
            await self.bot.send_message(
                chat_id=user_telegram_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания о лимите: {e}")
    
    async def send_monthly_reset_notification(self):
        """Отправляет уведомления о сбросе месячных лимитов"""
        try:
            message = """🎉 **Лимиты обновлены!**

🔄 Начался новый месяц — твои лимиты транскрибации полностью восстановлены!

📊 **Что тебя ждет:**
• Полный месячный лимит минут
• Новые промокоды и акции
• Улучшения в работе бота

🚀 **Готов к новым достижениям?** Отправляй видео и транскрибируй без ограничений!

🐾 *радостно мурчит и машет хвостиком*"""

            db = SessionLocal()
            try:
                user_service = UserService(db)
                # Отправляем всем пользователям с ограниченными тарифами
                users_with_limits = user_service.get_users_with_limits()
                
                sent_count = 0
                for user in users_with_limits:
                    try:
                        await self.bot.send_message(
                            chat_id=user.telegram_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                        sent_count += 1
                        await asyncio.sleep(0.1)
                        
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления о сбросе {user.telegram_id}: {e}")
                        continue
                
                logger.info(f"🔄 Отправлено {sent_count} уведомлений о сбросе лимитов")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка в send_monthly_reset_notification: {e}")
    
    async def send_welcome_series(self, user_telegram_id, day_number):
        """Отправляет серию приветственных сообщений новым пользователям"""
        welcome_series = {
            1: """👋 **Добро пожаловать в CyberKitty!**

Спасибо за регистрацию! Я помогу тебе максимально эффективно использовать бота.

🎯 **Сегодняшний совет:** Попробуй разные типы обработки видео — обычную транскрипцию и с ИИ-форматированием. Разница впечатляет!

💡 Есть вопросы? Просто напиши /help""",
            
            3: """🚀 **День 3: Открываем новые возможности**

Знаешь ли ты, что можно создавать саммари видео?

📋 После транскрибации нажми кнопки "Краткое саммари" или "Подробное саммари" — получишь структурированный анализ!

🎁 Бонус: промокод `НОВИЧОК` даёт +50% к лимиту на первый месяц!""",
            
            7: """💎 **Неделя с CyberKitty: время для апгрейда?**

Поздравляю! Ты используешь бота уже неделю!

📊 **Посмотри статистику:** /stats
⭐ **Рассмотри тарифы:** /plans

🔥 **Специально для тебя:** скидка 25% на любой платный тариф с промокодом `НЕДЕЛЯ25`"""
        }
        
        if day_number in welcome_series:
            try:
                await self.bot.send_message(
                    chat_id=user_telegram_id,
                    text=welcome_series[day_number],
                    parse_mode='Markdown'
                )
                logger.info(f"📬 Отправлено приветственное сообщение день {day_number} пользователю {user_telegram_id}")
                
            except Exception as e:
                logger.error(f"Ошибка отправки приветственной серии: {e}")

# Глобальная переменная для менеджера (будет инициализирована в main)
marketing_manager = None

def initialize_marketing_manager(bot):
    """Инициализирует менеджер маркетинга"""
    global marketing_manager
    marketing_manager = MarketingManager(bot)
    return marketing_manager 