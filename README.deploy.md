# Инструкция по развертыванию Transkribator на сервере

Это руководство описывает процесс развертывания бота Transkribator (КиберКотик 119) на сервере Linux.

## Системные требования

- Linux-сервер с доступом по SSH
- Python 3.8 или выше
- FFmpeg
- tmux
- Минимум 2 ГБ оперативной памяти
- Достаточно места на диске для хранения видео и аудио файлов

## Быстрая установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-username/transkribator.git
   cd transkribator
   ```

2. Запустите скрипт установки:
   ```bash
   ./install.sh
   ```

3. Отредактируйте файл `.env` и добавьте необходимые ключи API:
   ```bash
   nano .env
   ```

4. Запустите бота:
   ```bash
   ./cyberkitty_modular_start.sh
   ```

## Ручная установка (если автоматический скрипт не работает)

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-username/transkribator.git
   cd transkribator
   ```

2. Установите зависимости системы:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip ffmpeg tmux
   ```

3. Создайте и активируйте виртуальное окружение:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. Установите зависимости Python:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Создайте файл .env на основе примера:
   ```bash
   cp .env.sample .env
   nano .env
   ```

6. Сделайте скрипты исполняемыми:
   ```bash
   chmod +x *.sh
   ```

7. Создайте необходимые директории:
   ```bash
   mkdir -p videos audio transcriptions
   ```

## Автозапуск при старте системы

Для автоматического запуска бота при перезагрузке сервера, вы можете использовать systemd.

1. Создайте файл сервиса:
   ```bash
   sudo nano /etc/systemd/system/transkribator.service
   ```

2. Добавьте следующее содержимое (замените пути на соответствующие вашей системе):
   ```
   [Unit]
   Description=Transkribator Bot Service
   After=network.target

   [Service]
   Type=forking
   User=YOUR_USERNAME
   WorkingDirectory=/path/to/transkribator
   ExecStart=/path/to/transkribator/cyberkitty_modular_start.sh
   ExecStop=/path/to/transkribator/cyberkitty_modular_stop.sh
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

3. Включите и запустите сервис:
   ```bash
   sudo systemctl enable transkribator.service
   sudo systemctl start transkribator.service
   ```

4. Для просмотра статуса:
   ```bash
   sudo systemctl status transkribator.service
   ```

## Настройка Pyrogram Worker для больших видео

Если вы хотите обрабатывать большие видео (>20 МБ), вам потребуется настроить Pyrogram Worker:

1. Добавьте следующие параметры в .env файл:
   ```
   PYROGRAM_WORKER_ENABLED=true
   PYROGRAM_WORKER_CHAT_ID=ваш_id_чата
   TELEGRAM_API_ID=ваш_api_id
   TELEGRAM_API_HASH=ваш_api_hash
   ```

   Для получения TELEGRAM_API_ID и TELEGRAM_API_HASH, перейдите на https://my.telegram.org/apps

2. Запустите скрипт авторизации (это нужно сделать только один раз):
   ```bash
   ./pyro_auth_run.sh
   ```
   Следуйте инструкциям для ввода номера телефона и кода подтверждения.

3. Запустите Pyrogram Worker:
   ```bash
   ./pyro_worker_start.sh
   ```

4. Для проверки статуса воркера:
   ```bash
   ./pyro_worker_status.sh
   ```

## Мониторинг и управление

### Просмотр логов

```bash
# Логи основного бота
tail -f cyberkitty_modular.log

# Логи Pyrogram Worker
tail -f pyro_worker.log
```

### Управление tmux сессиями вручную

```bash
# Присоединиться к сессии бота
tmux attach -t cyberkitty

# Присоединиться к сессии Pyrogram Worker
tmux attach -t pyro_worker

# Выйти из сессии tmux (без остановки)
# Нажмите Ctrl+B, затем D
```

## Решение проблем

### Бот не запускается или не отвечает

1. Проверьте логи:
   ```bash
   tail -f cyberkitty_modular.log
   ```

2. Убедитесь, что все ключи API правильные в файле .env

3. Проверьте, что все скрипты имеют права на исполнение:
   ```bash
   chmod +x *.sh
   ```

4. Перезапустите бота:
   ```bash
   ./cyberkitty_modular_stop.sh
   ./cyberkitty_modular_start.sh
   ```

### Проблемы с обработкой больших видео

1. Проверьте, что Pyrogram Worker запущен и работает:
   ```bash
   ./pyro_worker_status.sh
   ```

2. Проверьте логи воркера:
   ```bash
   tail -f pyro_worker.log
   ```

3. Убедитесь, что PYROGRAM_WORKER_CHAT_ID, TELEGRAM_API_ID и TELEGRAM_API_HASH в файле .env указаны правильно.

## Обновление бота

1. Остановите бота и воркера:
   ```bash
   ./cyberkitty_modular_stop.sh
   ./pyro_worker_stop.sh
   ```

2. Обновите репозиторий:
   ```bash
   git pull
   ```

3. Активируйте виртуальное окружение и обновите зависимости:
   ```bash
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. Перезапустите бота и воркера:
   ```bash
   ./cyberkitty_modular_start.sh
   ./pyro_worker_start.sh
   ``` 