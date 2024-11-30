import os
import time
import telebot
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime

# Конфигурация
BOT_TOKEN = 'BOT_TOKEN'
CHAT_ID = 'CHAT_ID'
BASE_DIRECTORY = '/zoneminder/'  # Директория, в которой появляются новые подпапки
WAIT_TIME = 15  # Время ожидания перед удалением файлов (в секундах)
TARGET_FRAME = '00065-capture.jpg'  # Кадр для отправки

bot = telebot.TeleBot(BOT_TOKEN)

# Словарь перевода месяцев
MONTHS_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря"
}

def send_to_telegram(image_path):
    """Отправляет изображение в Telegram с сообщением."""
    try:
        # Формируем дату на русском языке
        now = datetime.now()
        date_str = f"{now.day} {MONTHS_RU[now.month]} {now.year}, {now.strftime('%H:%M:%S')}"
        # Формируем сообщение
        message = f"Обнаружено движение в кадре.\n{date_str}"
        
        with open(image_path, 'rb') as photo:
            bot.send_photo(CHAT_ID, photo, caption=message)
        print(f"Изображение {image_path} успешно отправлено с сообщением:\n{message}")
    except Exception as e:
        print(f"Ошибка при отправке изображения {image_path}: {e}")

def delete_capture_files(directory):
    """Удаляет все файлы с именем *****-capture.jpg в указанной директории."""
    try:
        for file in os.listdir(directory):
            if file.endswith('-capture.jpg'):
                file_path = os.path.join(directory, file)
                os.remove(file_path)
                print(f"Удален файл: {file_path}")
        print(f"Все файлы с именем *****-capture.jpg удалены в папке {directory}.")
    except Exception as e:
        print(f"Ошибка при удалении файлов: {e}")

class FolderHandler(FileSystemEventHandler):
    """Обрабатывает события файловой системы."""
    def on_created(self, event):
        # Если обнаружена новая папка
        if event.is_directory:
            print(f"Обнаружена новая папка: {event.src_path}")
            # Следим за этой папкой
            process_new_folder(event.src_path)

def process_new_folder(folder_path):
    """Обрабатывает новую папку."""
    while True:
        try:
            # Ищем файл 00050-capture.jpg
            for file in os.listdir(folder_path):
                if file == TARGET_FRAME:
                    file_path = os.path.join(folder_path, file)
                    print(f"Обнаружен файл: {file_path}")
                    # Отправляем в Telegram
                    send_to_telegram(file_path)
                    # Ждём 15 секунд и удаляем все capture.jpg
                    time.sleep(WAIT_TIME)
                    delete_capture_files(folder_path)
                    return
        except FileNotFoundError:
            print(f"Папка {folder_path} больше не существует.")
            return
        except Exception as e:
            print(f"Ошибка при обработке папки {folder_path}: {e}")
        time.sleep(1)

if __name__ == "__main__":
    # Создаем наблюдателя
    event_handler = FolderHandler()
    observer = Observer()
    observer.schedule(event_handler, BASE_DIRECTORY, recursive=True)

    print(f"Начато наблюдение за директорией: {BASE_DIRECTORY}")
    observer.start()

    try:
        while True:
            time.sleep(1)  # Поддерживаем процесс активным
    except KeyboardInterrupt:
        print("Остановка наблюдателя.")
        observer.stop()

    observer.join()
