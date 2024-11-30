
# ZoneMinder Automation

Этот проект предоставляет автоматизацию для работы с ZoneMinder, обеспечивая оперативное уведомление о движении через Telegram и отправку записанных видео. Проект состоит из двух скриптов:

1. **`send_video.py`** — отправляет видео через Telegram.
2. **`watch_capture.py`** — отправляет оперативное уведомление с кадром движения через Telegram.

---

## Скрипты

### 1. `send_video.py`
Этот скрипт:
- Отправляет видео из папки `/zoneminder/` в Telegram.
- Проверяет, завершена ли запись файла (анализирует изменение размера файла).
- Логирует успешные и неуспешные отправки в файл `/zoneminder/log.txt`.
- Автоматически удаляет отправленные видео.
- Работает на основе планировщика задач, например, `cron`.

**Настройка:**
- Настройте `cron` для запуска скрипта каждую минуту:
  ```bash
  * * * * * /usr/bin/python3 /path/to/send_video.py >> /zoneminder/log.txt 2>&1
  ```

---

### 2. `watch_capture.py`
Этот скрипт:
- Отслеживает папку `/zoneminder/` на появление новых подпапок.
- Ищет в каждой новой папке файл `00050-capture.jpg` (можно изменить в конфигурации).
- Немедленно отправляет этот кадр в Telegram с сообщением:
  ```
  Обнаружено движение в кадре.
  1 декабря 2024, 13:39:03
  ```
- Удаляет все файлы `*****-capture.jpg` в папке через 15 секунд после отправки.

**Особенности:**
- Используется библиотека `watchdog` для отслеживания файловой системы.
- Скрипт работает как демон, рекомендуется запускать его в `screen` или `tmux`.

---

## Требования

1. **Python 3.6+**
2. Библиотеки:
   - `telebot`:
     ```bash
     pip install pytelegrambotapi
     ```
   - `watchdog` (для `watch_capture.py`):
     ```bash
     pip install watchdog
     ```

---

## Запуск

### `send_video.py`
Запускается вручную или через `cron`:
```bash
python3 send_video.py
```

### `watch_capture.py`
Рекомендуется запускать в `screen`:
```bash
screen -S watch_capture
python3 watch_capture.py
```

Отключиться от `screen`, оставив его работать:
```plaintext
Ctrl + A, затем D
```

Вернуться к сессии:
```bash
screen -r watch_capture
```

---

## Настройка

### Telegram
- Укажите в обоих скриптах:
  - `BOT_TOKEN` — токен вашего Telegram-бота.
  - `CHAT_ID` — ID вашего Telegram-чата.

### Папки
- Обе программы работают с директорией `/zoneminder/`. Убедитесь, что ZoneMinder сохраняет файлы в указанное место.

---

## Возможности для расширения
- Добавление уведомлений о статусе работы бота.
- Улучшение логирования, включая ротацию лог-файлов.
- Интеграция с облачным хранилищем для резервного копирования видео.

---

## Лицензия
Проект предоставляется "как есть". Вы можете модифицировать его под свои нужды.

---

**Авторы:**  
Этот проект был разработан совместно с [ChatGPT](https://openai.com/) и с использованием лучших практик Python.
