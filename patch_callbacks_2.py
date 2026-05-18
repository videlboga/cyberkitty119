import sys

with open("transkribator_modules/bot/callbacks.py", "r", encoding="utf-8") as f:
    content = f.read()

start_str = "async def show_personal_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:"
end_str = "        await _reply(update, context, \"❌ Ошибка при загрузке личного кабинета\")\n"

start_idx = content.find(start_str)
if start_idx == -1:
    print("Could not find start str.")
    sys.exit(1)

end_idx = content.find(end_str, start_idx)
if end_idx == -1:
    print("Could not find end str.")
    sys.exit(1)

end_idx += len(end_str)

old_text = content[start_idx:end_idx]

replacement = """async def show_personal_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    \"\"\"Показывает личный кабинет пользователя.\"\"\"
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

            usage_text = "📊 **Использование в этом месяце:**\\n"
            if current_plan == 'free':
                limit = stats_data.get("free_generations_limit", 30)
                used = stats_data.get("generations_used_this_month", 0)
                remaining = max(0, limit - used)
                total = stats_data.get("total_generations", 0)
                minutes = stats_data.get("minutes_used_this_month", 0)
                
                usage_text += f"• Использовано: {used} из {limit} генераций\\n"
                usage_text += f"• Осталось: {remaining} генераций\\n"
                usage_text += f"• Всего генераций: {total}\\n"
                usage_text += f"• Минут транскрибировано: {minutes:.1f} мин"
            else:
                limit = stats_data.get("minutes_limit", 0)
                used = stats_data.get("minutes_used_this_month", 0)
                if limit > 0:
                    remaining = max(0, limit - used)
                    usage_text += f"• Использовано: {used:.1f} из {limit:.0f} мин\\n"
                    usage_text += f"• Осталось: {remaining:.1f} мин"
                else:
                    usage_text += f"• Использовано: {used:.1f} мин\\n"
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
                    "💸 **Партнёрская программа:**\\n"
                    f"• Баланс: {ref_earned:.2f} ₽ (30% от оплат)\\n"
                    f"• Оплат: {ref_paid} • Переходов: {ref_visits}\\n\\n"
                    f"🔗 Пригласи друзей: `{referral_link}`\\n\\n"
                )

            google_section = f"🔗 **Google Drive:** {google_status}\\n" if google_status is not None else ""

            cabinet_text = f\"\"\"🐱 **Личный кабинет**

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
\"\"\"

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
                await update.message.reply_text(error_text)\n"""

new_content = content[:start_idx] + replacement + content[end_idx:]
with open("transkribator_modules/bot/callbacks.py", "w", encoding="utf-8") as f:
    f.write(new_content)
print("Replaced successfully.")
