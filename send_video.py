import os
import time
from datetime import datetime
import telebot

# Конфигурация
BOT_TOKEN = 'BOT_TOKEN'
CHAT_ID = 'CHAT_ID'
VIDEO_DIRECTORY = '/zoneminder/'  # Директория с видеофайлами
LOG_FILE = '/zoneminder/log.txt'  # Путь к файлу лога
TIME_LIMIT = 10 * 60  # Время фильтрации (в секундах, 10 минут)

bot = telebot.TeleBot(BOT_TOKEN)

def write_log(message):
    """Записывает сообщение в лог-файл."""
    with open(LOG_FILE, 'a') as log_file:
        log_file.write(f"{message}\n")

def is_file_complete(file_path, check_time=1, retries=3):
    """
    Проверяет, завершена ли запись файла.
    file_path: путь к файлу.
    check_time: время в секундах между проверками.
    retries: количество проверок на отсутствие изменений размера.
    """
    try:
        for _ in range(retries):
            initial_size = os.path.getsize(file_path)
            time.sleep(check_time)  # Ждём указанное время
            final_size = os.path.getsize(file_path)
            if initial_size != final_size:
                print(f"Файл {file_path} ещё записывается...")
                return False
        return True  # Если файл не изменялся в течение всех проверок
    except FileNotFoundError:
        return False  # Если файл уже удалён или недоступен
    except Exception as e:
        print(f"Ошибка проверки завершения файла {file_path}: {e}")
        return False

def process_videos(directory):
    """Перебирает все видеофайлы в директории и её подпапках."""
    current_time = time.time()
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(('.mp4', '.avi', '.mkv')):  # Добавьте нужные форматы
                file_path = os.path.join(root, file)

                # Проверка времени создания
                file_creation_time = os.path.getctime(file_path)
                if current_time - file_creation_time > TIME_LIMIT:
                    continue  # Пропускаем старые файлы

                # Проверка, завершена ли запись файла
                if not is_file_complete(file_path, check_time=1, retries=3):
                    continue  # Пропускаем файлы, которые ещё записываются

                # Отправка видео
                send_and_delete_video(file_path)

def send_and_delete_video(video_path):
    """Отправляет видео в Telegram и удаляет его."""
    try:
        # Отправляем видео в Telegram
        with open(video_path, 'rb') as video_file:
            bot.send_video(CHAT_ID, video_file)
        write_log(f"Успешная отправка видео {video_path} в {datetime.now()}")
        print(f"Видео {video_path} успешно отправлено.")

        # Удаляем отправленное видео
        os.remove(video_path)

    except Exception as e:
        # Запись ошибки в лог
        write_log(f"Неуспешная отправка видео {video_path} в {datetime.now()}: {e}")
        print(f"Ошибка при обработке {video_path}: {e}")

        # Отправка ошибки в Telegram
        bot.send_message(CHAT_ID, f"Ошибка при обработке файла {video_path}: {e}")

# Основной запуск
if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)  # Создаёт папку для логов, если её нет
    process_videos(VIDEO_DIRECTORY)
    print("Обработка завершена.")
