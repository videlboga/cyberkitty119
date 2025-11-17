# Инструкция по развертыванию Cyberkitty19 Transkribator на сервере

Это руководство описывает процесс развертывания бота Cyberkitty19 Transkribator (КиберКотик 119) на сервере Linux.

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
   git clone https://github.com/your-username/cyberkitty19-transkribator.git
   cd cyberkitty19-transkribator
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
   git clone https://github.com/your-username/cyberkitty19-transkribator.git
   cd cyberkitty19-transkribator
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
   sudo nano /etc/systemd/system/cyberkitty19-transkribator.service
   ```

2. Добавьте следующее содержимое (замените пути на соответствующие вашей системе):
   ```
   [Unit]
   Description=Cyberkitty19 Transkribator Bot Service
   After=network.target

   [Service]
   Type=forking
   User=YOUR_USERNAME
   WorkingDirectory=/path/to/cyberkitty19-transkribator
   ExecStart=/path/to/cyberkitty19-transkribator/cyberkitty_modular_start.sh
   ExecStop=/path/to/cyberkitty19-transkribator/cyberkitty_modular_stop.sh
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

3. Включите и запустите сервис:
   ```bash
   sudo systemctl enable cyberkitty19-transkribator.service
   sudo systemctl start cyberkitty19-transkribator.service
   ```

4. Для просмотра статуса:
   ```bash
   sudo systemctl status cyberkitty19-transkribator.service
   ```

## Мониторинг и управление

### Просмотр логов

```bash
# Логи основного бота
tail -f cyberkitty_modular.log
```

### Управление tmux сессиями вручную

```bash
# Присоединиться к сессии бота
tmux attach -t cyberkitty

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

## Обновление бота

1. Остановите бота:
   ```bash
   ./cyberkitty_modular_stop.sh
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

4. Перезапустите бота:
   ```bash
   ./cyberkitty_modular_start.sh
   ```
