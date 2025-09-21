# 🏦 Руководство по настройке ЮКассы

## ✅ Восстановление функциональности завершено

Функциональность оплаты через ЮКассу была успешно восстановлена с новыми учетными данными:

- **Shop ID:** `1146505`
- **Secret Key:** `live_HS1FeHDwDeAesa0mp0MmY01NmL9s-UJioHK5DOXt2Z8`

## 🔧 Что было сделано

### 1. Обновлен модуль ЮКассы
- ✅ Обновлены учетные данные в `transkribator_modules/payments/yukassa.py`
- ✅ Исправлены цены планов (PRO: 299₽, UNLIMITED: 699₽)
- ✅ Обновлены описания планов

### 2. Интегрирована ЮКасса в основной модуль платежей
- ✅ Добавлена функция `initiate_yukassa_payment()` в `payments.py`
- ✅ Обновлены кнопки для выбора способа оплаты (Stars/ЮКасса)
- ✅ Добавлена обработка новых колбеков

### 3. Обновлены обработчики колбеков
- ✅ Добавлена поддержка колбеков `buy_plan_pro_yukassa` и `buy_plan_unlimited_yukassa`
- ✅ Обновлен `callbacks.py` для обработки платежей через ЮКассу

### 4. Настроена конфигурация
- ✅ Добавлены переменные окружения для ЮКассы в `config.py`
- ✅ Настроена интеграция с основным конфигом

### 5. Добавлен webhook обработчик
- ✅ Создан `yukassa_webhook.py` для обработки уведомлений от ЮКассы
- ✅ Интегрирован в API сервер (`/webhook/yukassa`)
- ✅ Автоматическая активация подписок после успешной оплаты

## 🚀 Как использовать

### Для пользователей:
1. Нажмите кнопку "💎 Тарифы" в боте
2. Выберите план (PRO или UNLIMITED)
3. Выберите способ оплаты:
   - **⭐ Купить PRO (Stars)** - оплата через Telegram Stars
   - **⭐ Купить PRO (ЮКасса)** - оплата через ЮКассу
4. При выборе ЮКассы получите ссылку для оплаты
5. После успешной оплаты подписка активируется автоматически

### Для администраторов:
- Webhook URL: `https://your-domain.com/webhook/yukassa`
- Все платежи автоматически обрабатываются и сохраняются в базе данных
- Логи платежей доступны в логах бота

## 📋 Настройка webhook в ЮКассе

1. Войдите в личный кабинет ЮКассы
2. Перейдите в раздел "Настройки" → "Webhook"
3. Добавьте URL: `https://your-domain.com/webhook/yukassa`
4. Выберите события: `payment.succeeded`
5. Сохраните настройки

## 🔍 Мониторинг

### Логи платежей:
```bash
# Просмотр логов бота
docker logs cyberkitty19-transkribator-bot | grep -E "(yukassa|payment)"

# Просмотр логов API сервера
docker logs cyberkitty19-transkribator-api | grep -E "(webhook|yukassa)"
```

### Проверка транзакций в базе данных:
```sql
SELECT * FROM transactions WHERE payment_provider = 'yukassa' ORDER BY created_at DESC;
```

## 🛠️ Технические детали

### Файлы, которые были изменены:
- `transkribator_modules/payments/yukassa.py` - основной модуль ЮКассы
- `transkribator_modules/bot/payments.py` - интеграция в систему платежей
- `transkribator_modules/bot/callbacks.py` - обработчики колбеков
- `transkribator_modules/config.py` - конфигурация
- `transkribator_modules/bot/yukassa_webhook.py` - webhook обработчик
- `api_server.py` - интеграция webhook в API сервер

### Новые колбеки:
- `buy_plan_pro_stars` - покупка PRO через Telegram Stars
- `buy_plan_pro_yukassa` - покупка PRO через ЮКассу
- `buy_plan_unlimited_stars` - покупка UNLIMITED через Telegram Stars
- `buy_plan_unlimited_yukassa` - покупка UNLIMITED через ЮКассу

## 🎯 Результат

Теперь пользователи могут:
- ✅ Выбирать между оплатой через Telegram Stars и ЮКассу
- ✅ Получать ссылки для оплаты через ЮКассу
- ✅ Автоматически активировать подписки после оплаты
- ✅ Видеть историю всех платежей в личном кабинете

Функциональность оплаты через ЮКассу полностью восстановлена и готова к использованию! 🎉


