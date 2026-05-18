"""
Справочник событий пользователя с человекочитаемыми названиями.
Используется для логирования и отображения в административном дашборде.
"""

from typing import Dict, Optional

# Категории событий
class EventCategory:
    BOT_COMMAND = "bot_command"
    BOT_BUTTON = "bot_button"
    BOT_MEDIA = "bot_media"
    MINIAPP_AUTH = "miniapp_auth"
    MINIAPP_NOTE = "miniapp_note"
    MINIAPP_AGENT = "miniapp_agent"
    MINIAPP_NAV = "miniapp_navigation"
    PAYMENT = "payment"
    PROMO = "promo"
    REFERRAL = "referral"
    ERROR = "error"
    GOOGLE = "google"
    API = "api"


# Маппинг событий на человекочитаемые названия
EVENT_NAMES: Dict[str, str] = {
    # User lifecycle
    "user_registered": "👤 Регистрация пользователя",

    # Bot Commands
    "bot_command_start": "▶️ Запуск бота",
    "bot_command_help": "❓ Запрос помощи",
    "bot_command_stats": "📊 Просмотр статистики",
    
    # Bot Buttons - Main Menu
    "bot_button_personal_cabinet": "🏠 Личный кабинет",
    "bot_button_show_payment_plans": "💎 Просмотр тарифов",
    "bot_button_enter_promo_code": "🎁 Ввод промокода",
    "bot_button_show_help": "❓ Помощь",
    "bot_button_back_to_start": "🔙 Главное меню",
    
    # Bot Buttons - Transcription
    "bot_button_process_transcript": "🔧 Обработка транскрипции",
    "bot_button_send_more": "📤 Отправка ещё файлов",
    "bot_button_main_menu": "🏠 Возврат в меню",
    
    # Bot Buttons - Plans
    "bot_button_show_plans": "📊 Просмотр планов",
    "bot_button_stay_basic": "🆓 Остаться на бесплатном",
    "bot_button_buy_plan_stars": "⭐ Покупка через Stars",
    "bot_button_buy_plan_yukassa": "💳 Покупка через ЮKassa",
    
    # Bot Buttons - Google
    "bot_button_google_connect": "🔗 Подключить Google",
    "bot_button_google_reconnect": "🔄 Переподключить Google",
    "bot_button_google_disconnect": "🚫 Отключить Google",
    
    # Bot Buttons - API Keys
    "bot_button_show_api_keys": "🔑 Просмотр API ключей",
    "bot_button_create_api_key": "➕ Создать API ключ",
    "bot_button_list_api_keys": "📋 Список API ключей",
    
    # Bot Buttons - Beta/Agent
    "bot_beta_note_confirm": "✅ Подтверждение создания заметки",
    "bot_beta_note_decline": "❌ Отказ от создания заметки",
    
    # Bot Media Processing
    "bot_media_video_received": "🎥 Получено видео",
    "bot_media_audio_received": "🎵 Получено аудио",
    "bot_media_video_transcribed": "✅ Видео транскрибировано",
    "bot_media_audio_transcribed": "✅ Аудио транскрибировано",
    "bot_media_transcription_failed": "❌ Ошибка транскрибации",
    "bot_media_youtube_link": "🎬 YouTube ссылка",
    "bot_media_vk_link": "🎬 VK видео ссылка",
    "bot_media_gdrive_link": "📎 Google Drive ссылка",
    "bot_media_dropbox_link": "📎 Dropbox ссылка",
    "bot_media_mega_link": "📎 Mega.nz ссылка",
    "bot_media_yandex_disk_link": "📎 Яндекс.Диск ссылка",
    
    # MiniApp Auth
    "miniapp_auth": "🔐 Авторизация в MiniApp",
    "miniapp_auth_failed": "❌ Ошибка авторизации MiniApp",
    
    # MiniApp Notes
    "miniapp_note_created": "➕ Создана заметка",
    "miniapp_note_updated": "✏️ Обновлена заметка",
    "miniapp_note_deleted": "🗑️ Удалена заметка",
    "miniapp_note_viewed": "👁️ Просмотр заметки",
    "miniapp_note_archived": "📦 Заметка архивирована",
    "miniapp_note_restored": "♻️ Заметка восстановлена",
    "miniapp_note_search": "🔍 Поиск заметок",
    
    # MiniApp Agent
    "miniapp_agent_session_fetch": "🤖 Получение сессии агента",
    "miniapp_agent_activate_note": "📝 Активация заметки в агенте",
    "miniapp_agent_message": "💬 Сообщение агенту",
    "miniapp_agent_upload": "📤 Загрузка файла агенту",
    "miniapp_agent_clear_history": "🧹 Очистка истории агента",
    
    # MiniApp Navigation
    "miniapp_page_home": "🏠 Главная страница",
    "miniapp_page_notes": "📝 Страница заметок",
    "miniapp_page_search": "🔍 Страница поиска",
    "miniapp_page_settings": "⚙️ Настройки",
    "miniapp_page_agent": "🤖 Страница агента",
    "miniapp_page_groups": "📁 Группы заметок",
    
    # MiniApp Beta
    "miniapp_beta_status": "🧪 Проверка бета-статуса",
    "miniapp_beta_update": "🔄 Обновление бета-статуса",
    
    # Payments
    "payment_initiated": "💳 Инициирован платёж",
    "payment_completed": "✅ Платёж завершён",
    "payment_failed": "❌ Платёж не прошёл",
    "payment_refunded": "↩️ Возврат средств",
    
    # Promo
    "promo_activated": "🎁 Промокод активирован",
    "promo_validation_failed": "❌ Промокод недействителен",
    "promo_entered": "🎁 Ввод промокода",
    
    # Referral
    "referral_code_generated": "🔗 Реферальный код создан",
    "referral_user_registered": "👥 Регистрация по реферальной ссылке",
    "referral_commission_recorded": "💰 Начислена реферальная комиссия",
    "referral_bonus_applied": "🎁 Применён реферальный бонус",
    
    # Google Integration
    "google_auth_started": "🔗 Начало авторизации Google",
    "google_auth_completed": "✅ Google авторизован",
    "google_auth_failed": "❌ Ошибка авторизации Google",
    "google_calendar_sync": "📅 Синхронизация Google Calendar",
    "google_disconnected": "🚫 Google отключен",
    
    # API
    "api_key_created": "🔑 API ключ создан",
    "api_key_deleted": "🗑️ API ключ удалён",
    "api_request": "🌐 API запрос",
    "api_error": "❌ Ошибка API",
    
    # Errors
    "error_critical": "🚨 Критическая ошибка",
    "error_transcription": "❌ Ошибка транскрибации",
    "error_payment": "❌ Ошибка платежа",
    "error_database": "❌ Ошибка БД",
    "error_external_api": "❌ Ошибка внешнего API",
    "error_validation": "❌ Ошибка валидации",
    
    # Search
    "search_performed": "🔍 Выполнен поиск",
    "search_result_clicked": "👆 Клик по результату поиска",
    "search_feedback_positive": "👍 Положительный отзыв на поиск",
    "search_feedback_negative": "👎 Отрицательный отзыв на поиск",
}


def get_event_display_name(event_kind: str) -> str:
    """Получить человекочитаемое название события."""
    return EVENT_NAMES.get(event_kind, event_kind)


def get_event_category(event_kind: str) -> str:
    """Определить категорию события по его типу."""
    if event_kind.startswith("bot_command_"):
        return EventCategory.BOT_COMMAND
    elif event_kind.startswith("bot_button_"):
        return EventCategory.BOT_BUTTON
    elif event_kind.startswith("bot_media_"):
        return EventCategory.BOT_MEDIA
    elif event_kind.startswith("miniapp_auth"):
        return EventCategory.MINIAPP_AUTH
    elif event_kind.startswith("miniapp_note_"):
        return EventCategory.MINIAPP_NOTE
    elif event_kind.startswith("miniapp_agent_"):
        return EventCategory.MINIAPP_AGENT
    elif event_kind.startswith("miniapp_page_") or event_kind.startswith("miniapp_beta_"):
        return EventCategory.MINIAPP_NAV
    elif event_kind.startswith("payment_"):
        return EventCategory.PAYMENT
    elif event_kind.startswith("promo_"):
        return EventCategory.PROMO
    elif event_kind.startswith("referral_"):
        return EventCategory.REFERRAL
    elif event_kind.startswith("google_"):
        return EventCategory.GOOGLE
    elif event_kind.startswith("api_"):
        return EventCategory.API
    elif event_kind.startswith("error_"):
        return EventCategory.ERROR
    elif event_kind.startswith("search_"):
        return "search"
    else:
        return "other"


def get_category_emoji(category: str) -> str:
    """Получить эмодзи для категории."""
    emojis = {
        EventCategory.BOT_COMMAND: "🤖",
        EventCategory.BOT_BUTTON: "🔘",
        EventCategory.BOT_MEDIA: "🎬",
        EventCategory.MINIAPP_AUTH: "🔐",
        EventCategory.MINIAPP_NOTE: "📝",
        EventCategory.MINIAPP_AGENT: "🤖",
        EventCategory.MINIAPP_NAV: "🧭",
        EventCategory.PAYMENT: "💳",
        EventCategory.PROMO: "🎁",
        EventCategory.REFERRAL: "👥",
        EventCategory.GOOGLE: "📅",
        EventCategory.API: "🔌",
        EventCategory.ERROR: "⚠️",
        "search": "🔍",
        "other": "📊",
    }
    return emojis.get(category, "📊")
