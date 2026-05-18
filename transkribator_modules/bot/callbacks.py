CABINET_REPLY_MARKUP_KEY = "_cabinet_reply_markup"
CABINET_SUPPRESS_INLINE_FLAG = "_suppress_cabinet_inline"
"""
Обработчики колбеков для CyberKitty Transkribator
"""

import json
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    logger,
    GOOGLE_OAUTH_CONFIGURED,
    SHOW_GOOGLE_OAUTH_IN_MENU,
    MINIAPP_EFFECTIVE_URL,
    TELEGRAM_REFERRAL_URL,
)
from transkribator_modules.db.database import (
    SessionLocal,
    UserService,
    ApiKeyService,
    log_event,
    log_telegram_event,
    ReferralService,
)
from transkribator_modules.db.models import ApiKey, PlanType
from transkribator_modules.bot.payments import handle_payment_callback, show_payment_plans, initiate_payment, initiate_yukassa_payment
from transkribator_modules.bot.logging_utils import log_step, trace_handler
from transkribator_modules.google_api import (
    GoogleCredentialService,
    generate_state,
    build_authorization_url,
)

SUPPORT_CONTACT_URL = "https://t.me/like_a_duck"


def _get_target_message(update: Update):
    if update.message:
        return update.message
    if update.callback_query:
        return update.callback_query.message
    return None


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    message = _get_target_message(update)
    if message:
        return await message.reply_text(text, **kwargs)
    if update.callback_query:
        return await context.bot.send_message(chat_id=update.effective_user.id, text=text, **kwargs)
    return None


def _build_referral_deeplink(referral_code: str) -> str:
    parsed = urlparse(TELEGRAM_REFERRAL_URL)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.setdefault("utm_source", "telegram")
    params.setdefault("utm_medium", "bot")
    params.setdefault("utm_campaign", "referral")
    params["start"] = f"ref_{referral_code}"

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower().endswith("t.me") and path_segments:
        bot_segment = path_segments[0]
        base_path = f"/{bot_segment}"
        # Не добавляем startapp: нам важно сначала запустить сценарий /start
        params.pop("startapp", None)
        return urlunparse(parsed._replace(path=base_path, query=urlencode(params)))

    return urlunparse(parsed._replace(query=urlencode(params)))

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает колбек запросы от кнопок."""
    query = update.callback_query
    await query.answer()

    data = query.data
    logger.info(f"Получен колбек: {data}")
    logger.info(f"Полный update: {update.to_dict() if hasattr(update, 'to_dict') else str(update)}")
    log_step(update, "callback:entry", {"data": data})

    # Обработка различных типов колбеков
    if data.startswith("beta:"):
        from transkribator_modules.beta.handlers import handle_callback as handle_beta_callback

        await handle_beta_callback(update, context)
        return

    if data.startswith("agent:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else None
        note_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if action and note_id:
            from transkribator_modules.agent.dialog import save_raw_and_index, backlog_note
            if action == 'save_raw':
                # Логируем agent action
                try:
                    log_event(update.effective_user.id, "bot_agent_save_raw", {
                        "note_id": note_id,
                        "callback_data": data
                    })
                except Exception:
                    logger.debug("Failed to log agent save_raw event", exc_info=True)
                
                text = await save_raw_and_index(update, context, note_id)
                await query.edit_message_reply_markup(reply_markup=None)
                await _reply(update, context, text)
                return
            if action == 'backlog':
                # Логируем agent action
                try:
                    log_event(update.effective_user.id, "bot_agent_backlog", {
                        "note_id": note_id,
                        "callback_data": data
                    })
                except Exception:
                    logger.debug("Failed to log agent backlog event", exc_info=True)
                
                text = await backlog_note(update, context, note_id)
                await query.edit_message_reply_markup(reply_markup=None)
                await _reply(update, context, text)
                return

    if data == "show_payment_plans":
        logger.info("Получен колбек show_payment_plans")
        try:
            log_event(update.effective_user.id, "bot_button_show_payment_plans", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await show_payment_plans(update, context)

    elif data == "personal_cabinet":
        try:
            log_event(update.effective_user.id, "bot_button_personal_cabinet", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await show_personal_cabinet(update, context)

    elif data == "show_help":
        try:
            log_event(update.effective_user.id, "bot_button_show_help", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        from transkribator_modules.bot.commands import help_command
        await help_command(update, context)

    elif data == "toggle_beta":
        try:
            log_event(update.effective_user.id, "bot_button_toggle_beta", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await toggle_beta(update, context)

    elif data == "google_disconnect":
        try:
            log_event(update.effective_user.id, "bot_button_google_disconnect", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await disconnect_google(update, context)

    elif data.startswith("buy_plan_"):
        try:
            log_event(update.effective_user.id, "bot_button_buy_plan", {
                "callback_data": data,
                "payment_method": "stars" if data.endswith("_stars") else "yukassa" if data.endswith("_yukassa") else "legacy"
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
            
        if data.endswith("_stars"):
            # Платеж через Telegram Stars
            plan_id = data.replace("buy_plan_", "").replace("_stars", "")
            logger.info(f"Обнаружен колбек оплаты плана через Stars: {data}, извлеченный plan_id: {plan_id}")
            await initiate_payment(update, context, plan_id)
        elif data.endswith("_yukassa"):
            # Платеж через ЮКассу
            plan_id = data.replace("buy_plan_", "").replace("_yukassa", "")
            logger.info(f"Обнаружен колбек оплаты плана через ЮКассу: {data}, извлеченный plan_id: {plan_id}")
            await initiate_yukassa_payment(update, context, plan_id)
        else:
            # Старый формат для обратной совместимости
            plan_id = data.replace("buy_plan_", "")
            logger.info(f"Обнаружен колбек оплаты плана (старый формат): {data}, извлеченный plan_id: {plan_id}")
            await initiate_payment(update, context, plan_id)


    elif data == "show_stats":
        try:
            log_event(update.effective_user.id, "bot_button_show_stats", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        from transkribator_modules.bot.commands import stats_command
        await stats_command(update, context)

    elif data == "show_api_keys":
        try:
            log_event(update.effective_user.id, "bot_button_show_api_keys", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await show_api_keys(update, context)

    elif data == "enter_promo_code":
        try:
            log_event(update.effective_user.id, "bot_button_enter_promo_code", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await enter_promo_code(update, context)

    elif data == "show_promo_codes":
        try:
            log_event(update.effective_user.id, "bot_button_show_promo_codes", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        from transkribator_modules.bot.commands import promo_codes_command
        await promo_codes_command(update, context)

    elif data == "show_plans":
        try:
            log_event(update.effective_user.id, "bot_button_show_plans", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await show_plans_callback(update)

    elif data == "create_api_key":
        try:
            log_event(update.effective_user.id, "bot_button_create_api_key", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await create_api_key_callback(update)

    elif data == "list_api_keys":
        try:
            log_event(update.effective_user.id, "bot_button_list_api_keys", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await list_api_keys_callback(update)

    elif data.startswith("delete_api_key_"):
        key_id = int(data.split("_")[-1])
        try:
            log_event(update.effective_user.id, "bot_button_delete_api_key", {
                "callback_data": data,
                "key_id": key_id
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await delete_api_key_callback(update, key_id)

    elif data == "back_to_start":
        try:
            log_event(update.effective_user.id, "bot_button_back_to_start", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log button event", exc_info=True)
        await back_to_start_callback(update)

    elif data.startswith("brief_summary_") or data.startswith("detailed_summary_"):
        await handle_summary_callback(update, context)

    elif data.startswith("process_transcript_"):
        await handle_process_transcript_callback(update, context)

    elif data.startswith("send_more_"):
        await handle_send_more_callback(update, context)

    elif data.startswith("main_menu_"):
        await handle_main_menu_callback(update, context)

    else:
        await query.edit_message_text("Неизвестная команда")

async def show_personal_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает личный кабинет пользователя."""
    log_step(update, "callback:personal_cabinet")
    
    user = update.effective_user
    
    import httpx
    from transkribator_modules.config import LOCAL_BOT_API_URL
    api_url = "http://core-api:8000" if "telegram-bot-api" in LOCAL_BOT_API_URL else "http://localhost:8000"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{api_url}/api/v1/system/profile/tg/{user.id}")
            response.raise_for_status()
            data = response.json()
            
            user_data = data.get("user", {})
            google_data = data.get("google_integration", {})
            stats_data = data.get("usage_stats", {})
            ref_data = data.get("referral_program", {})
            
            current_plan = user_data.get("current_plan", "free")
            plan_expires_at = user_data.get("plan_expires_at")
            is_beta = user_data.get("is_beta_enabled", False)
            
            plan_label = "PRO 🌟" if current_plan == "pro" else "VIP 👑" if current_plan == "vip" else "Бесплатный 🆓"
            plan_status = ""
            if plan_expires_at:
                from datetime import datetime
                expires = datetime.fromisoformat(plan_expires_at.replace('Z', '+00:00'))
                days_left = (expires.replace(tzinfo=None) - datetime.utcnow()).days
                if days_left > 0:
                    plan_status = f"(истекает через {days_left} дн.)"
                else:
                    plan_status = "(истек)"
            elif current_plan != "free":
                plan_status = "(бессрочно 🎉)"

            usage_text = "📊 **Использование в этом месяце:**\n"
            limit = stats_data.get("minutes_limit", 0)
            used = stats_data.get("minutes_used_this_month", 0)
            if limit > 0:
                remaining = max(0, limit - used)
                usage_text += f"• Использовано: {used:.1f} из {limit:.0f} мин\n"
                usage_text += f"• Осталось: {remaining:.1f} мин"
            else:
                usage_text += f"• Использовано: {used:.1f} мин\n"
                usage_text += f"• Лимит: Безлимитно ♾️"
                
            transcriptions_count = stats_data.get("total_transcriptions", 0)
            total_minutes = stats_data.get("total_minutes_transcribed", 0.0)
            
            show_google_section = google_data.get("available", False)
            if show_google_section:
                is_connected = google_data.get("connected", False)
                google_status = "Подключён 🟢" if is_connected else "Не подключён ⚪"
                google_auth_url = google_data.get("auth_url") if not is_connected else None
            else:
                google_status = "Недоступно"
                google_auth_url = None
                
            referral_code = ref_data.get("referral_code")
            from transkribator_modules.bot.utils import get_bot_username
            try:
                bot_username = await get_bot_username(context.bot)
            except Exception:
                bot_username = "NeMolchiAiBot"
            referral_link = f"https://t.me/{bot_username}?start={referral_code}" if referral_code else None
            
            ref_stats = ref_data.get("stats", {})
            ref_visits = ref_stats.get("clicks", 0)
            ref_paid = ref_stats.get("registrations", 0) 
            ref_earned = ref_stats.get("earned", 0.0)
            
            beta_status = "Включен 🟢" if is_beta else "Выключен ⚪"

            referral_section = ""
            if referral_link:
                referral_section = (
                    "💸 **Партнёрская программа:**\n"
                    f"• Баланс: {ref_earned:.2f} ₽ (30% от оплат)\n"
                    f"• Оплат: {ref_paid} • Переходов: {ref_visits}\n\n"
                    f"🔗 Пригласи друзей: `{referral_link}`\n\n"
                )

            google_section = f"🔗 **Google Drive:** {google_status}\n" if google_status is not None else ""

            cabinet_text = f"""�� **Личный кабинет**

👤 **Профиль:**
• Имя: {user.first_name or 'Котик'} {user.last_name or ''}
• План: {plan_label} {plan_status}

{usage_text}

📈 **Статистика:**
• Файлов обработано: {transcriptions_count}
• Всего транскрибировано: {total_minutes:.1f} мин
• Последняя активность: Из API профиля

{referral_section}{google_section}🧪 **Бета-режим:** {beta_status}

• Управление доступно в мини-приложении CyberKitty

**Доступные функции:**
"""

            # Базовые кнопки
            keyboard = [
                # [InlineKeyboardButton("⚙️ Настройки модели", callback_data="model_settings")],
                [InlineKeyboardButton("💎 Тарифы", callback_data="show_plans")]
            ]

            # Google Drive секция
            if show_google_section:
                try:
                    if is_connected:
                        keyboard.append([InlineKeyboardButton("🔌 Отключить Google Drive", callback_data="disconnect_google")])
                    else:
                        if google_auth_url:
                            keyboard.append([InlineKeyboardButton("🔗 Подключить Google Drive", url=google_auth_url)])
                except Exception as exc:
                    logger.warning("Error checking Google Drive status", exc_info=exc)
                    
            # Бета версии
            beta_btn_text = "Выйти из Beta ✨" if is_beta else "Включить Beta ✨"
            keyboard.append([InlineKeyboardButton(beta_btn_text, callback_data="toggle_beta")])

            # Переходы
            keyboard.append([
                InlineKeyboardButton("👤 Профиль", callback_data="profile_menu"),
                InlineKeyboardButton("🔙 В главное меню", callback_data="main_menu")
            ])

            # Дополнительные
            keyboard.extend([
                [InlineKeyboardButton("🎁 Промокоды", callback_data="enter_promo_code")],
                [InlineKeyboardButton("❓ Помощь", callback_data="show_help")],
                [InlineKeyboardButton("Поддержка", url=SUPPORT_CONTACT_URL if globals().get('SUPPORT_CONTACT_URL') else "https://t.me/cyberkitty")]
            ])

            reply_markup = InlineKeyboardMarkup(keyboard)

            if update.callback_query:
                try:
                    await update.callback_query.edit_message_text(
                        cabinet_text, reply_markup=reply_markup, parse_mode='Markdown'
                    )
                except Exception as exc:
                    if "Message is not modified" in str(exc):
                        try:
                            await update.callback_query.answer("Уже открыт 🐾", show_alert=False)
                        except Exception:
                            pass
                    else:
                        raise
            else:
                from transkribator_modules.bot.utils import _reply
                try:
                    await _reply(update, context, cabinet_text, reply_markup=reply_markup, parse_mode='Markdown')
                except NameError:
                    await update.message.reply_text(cabinet_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка получения профиля: {e}")
        error_text = "❌ Ошибка при загрузке личного кабинета из API."
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(error_text)
            except Exception:
                pass
        elif update.message:
            try:
                from transkribator_modules.bot.utils import _reply
                await _reply(update, context, error_text)
            except NameError:
                await update.message.reply_text(error_text)

async def handle_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает кнопку 'Главное меню'."""
    query = update.callback_query
    await query.answer()
    log_step(update, "callback:main_menu")
    
    # Логируем событие
    try:
        log_event(update.effective_user.id, "bot_button_main_menu", {
            "callback_data": query.data
        })
    except Exception:
        logger.debug("Failed to log main_menu callback event", exc_info=True)

    try:
        # Возвращаемся в главное меню
        await back_to_start_callback(update)

    except Exception as e:
        logger.error(f"Ошибка при обработке кнопки 'Главное меню': {e}")
        await query.edit_message_text("❌ Произошла ошибка. Попробуйте позже.")


async def toggle_beta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    log_step(update, "callback:toggle_beta")

    user = update.effective_user
    if not user:
        await query.edit_message_text("Не удалось определить пользователя.")
        return

    #db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(
            telegram_id=user.id,
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
        )

        current = user_service.is_beta_enabled(db_user)
        new_status = not current
        user_service.set_beta_enabled(db_user, new_status)

        if not new_status:
            beta_state = context.user_data.get("beta")
            if beta_state:
                beta_state.pop("active_note_id", None)
                beta_state.pop("pending_note", None)

        text = "🧪 Бета-режим включен. Мур!" if new_status else "Бета-режим выключен. Возвращаюсь в обычный режим."
        await query.answer(text, show_alert=False)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to toggle beta mode",
            extra={"user_id": user.id if user else None, "error": str(exc)},
        )
        await query.answer("Не удалось переключить бета-режим. Попробуйте позже.", show_alert=True)
    finally:
        db.close()

    await show_personal_cabinet(update, context)
