#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import threading
import requests
import logging

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# -----------------------------------------------------------------------------
# 1) ЛОГИРОВАНИЕ
# -----------------------------------------------------------------------------
LOG_FILE = "/zoneminder/log.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 2) НАСТРОЙКИ ТЕЛЕГРАМА
# -----------------------------------------------------------------------------
BOT_TOKEN = "XXXXXXXXXXXXX"
CHAT_ID   = "XXXXXXXXXXXXX"

# -----------------------------------------------------------------------------
# 3) НАСТРОЙКИ СКРИПТА
# -----------------------------------------------------------------------------
ZONEMINDER_DIR            = "/zoneminder/"
CHECK_STABLE_INTERVAL     = 5     
CHECK_STABLE_MAX_ATTEMPTS = 7      # Итого 35 секунд ждём, пока видео "успокоится"
DELETE_VIDEO_DELAY        = 5      
SESSION_DURATION          = 120    # 2 минуты

# -----------------------------------------------------------------------------
# 4) ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# -----------------------------------------------------------------------------
discovered_files = set()  # Уже обработанные файлы
events_info = {}          # Логика (65/66 кадров)

# Мы позволяем только одну «сессию» за раз (упрощённо)
current_session = None

# -----------------------------------------------------------------------------
# 5) ФУНКЦИИ ОТПРАВКИ
# -----------------------------------------------------------------------------
def send_photo(file_path: str, caption: str = "") -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(file_path, 'rb') as f:
        files = {'photo': f}
        data  = {
            'chat_id': CHAT_ID,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        try:
            resp = requests.post(url, data=data, files=files, timeout=10)
            if resp.status_code == 200:
                logger.info(f"Фото отправлено: {file_path}")
                return True
            else:
                logger.error(f"Ошибка при отправке фото {file_path}: {resp.text}")
        except Exception as e:
            logger.error(f"Исключение при отправке фото {file_path}: {e}")
    return False


def send_video(file_path: str, caption: str = "") -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    with open(file_path, 'rb') as f:
        files = {'video': f}
        data  = {
            'chat_id': CHAT_ID,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        try:
            resp = requests.post(url, data=data, files=files, timeout=30)
            if resp.status_code == 200:
                logger.info(f"Видео отправлено: {file_path}")
                return True
            else:
                logger.error(f"Ошибка при отправке видео {file_path}: {resp.text}")
        except Exception as e:
            logger.error(f"Исключение при отправке видео {file_path}: {e}")
    return False


def send_media_group(video_paths, caption_prefix: str = "Видео"):
    """
    Отправляем несколько (до 10) видео одним "альбомом" (sendMediaGroup).
    """
    if not video_paths:
        return False

    max_items = 10
    sublist = video_paths[:max_items]

    media_list = []
    for i, path in enumerate(sublist):
        cap = ""
        if i == 0:
            cap = f"{caption_prefix} (всего файлов: {len(video_paths)})"
        media_list.append({
            "type": "video",
            "media": f"attach://file{i}",
            "caption": cap,
            "parse_mode": "HTML"
        })

    files = {}
    for i, path in enumerate(sublist):
        files[f"file{i}"] = (os.path.basename(path), open(path, 'rb'), 'video/mp4')

    data = {
        "chat_id": CHAT_ID,
        "media": str(media_list).replace("'", '"')
    }

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
            data=data,
            files=files,
            timeout=60
        )
        if resp.status_code == 200:
            logger.info(f"Медиагруппа отправлена. Всего видео: {len(video_paths)}")
            return True
        else:
            logger.error(f"Ошибка при отправке медиагруппы: {resp.text}")
    except Exception as e:
        logger.error(f"Исключение при отправке медиагруппы: {e}")

    return False


# -----------------------------------------------------------------------------
# 6) ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------------------------------------------------------
def wait_for_file_stable(file_path: str) -> bool:
    """
    Ждём, пока файл не перестанет расти в размере,
    максимум CHECK_STABLE_MAX_ATTEMPTS раз.
    """
    for attempt in range(CHECK_STABLE_MAX_ATTEMPTS):
        if not os.path.isfile(file_path):
            return False
        size1 = os.path.getsize(file_path)
        time.sleep(CHECK_STABLE_INTERVAL)

        if not os.path.isfile(file_path):
            return False
        size2 = os.path.getsize(file_path)

        if size1 == size2:
            return True
        else:
            logger.info(f"Файл {file_path} ещё растёт (попытка {attempt+1}).")
    return False


def parse_event_id(folder_path: str) -> str:
    parts = folder_path.strip("/").split("/")
    if not parts:
        return ''
    return parts[-1]


def parse_frame_number(filename: str) -> int:
    if not filename.endswith("-capture.jpg"):
        return -1
    try:
        base = filename.split("-capture")[0]  # '00065'
        return int(base)
    except ValueError:
        return -1


def delete_file_safe(path: str):
    """Удаляем файл с логированием."""
    if os.path.isfile(path):
        try:
            os.remove(path)
            logger.info(f"Удалён файл: {path}")
        except Exception as e:
            logger.error(f"Ошибка при удалении {path}: {e}")


def delete_all_captures_in_folder(folder_path: str):
    """Удалить все файлы '-capture.jpg' в указанной папке."""
    if not os.path.isdir(folder_path):
        return
    for fname in os.listdir(folder_path):
        if fname.endswith("-capture.jpg"):
            full_path = os.path.join(folder_path, fname)
            delete_file_safe(full_path)


# -----------------------------------------------------------------------------
# 7) ЛОГИКА «СЕССИЙ»
# -----------------------------------------------------------------------------
def start_session():
    global current_session
    if current_session is not None:
        logger.warning("start_session() вызван, а сессия уже идёт. Завершим старую (force) и создадим новую.")
        end_session(force=True)

    logger.info(f"Старт новой сессии (продолжительность {SESSION_DURATION} сек).")

    current_session = {
        "start_time": time.time(),
        "videos": [],
        "folders": set(),
        "sent_first_frame": False  # Как только отправим 65-й кадр — станет True
    }

    t = threading.Timer(SESSION_DURATION, end_session)
    t.daemon = True
    current_session["timer"] = t
    t.start()


def end_session(force=False):
    global current_session
    if current_session is None:
        return

    logger.info("Завершаем сессию...")

    if force:
        # Останавливаем таймер
        timer_obj = current_session.get("timer")
        if timer_obj:
            timer_obj.cancel()

    # (1) Отправляем накопленные видео «одним альбомом»
    videos = current_session.get("videos", [])
    if videos:
        logger.info(f"Всего видео в сессии: {len(videos)}. Отправляем медиагруппой...")
        ok = send_media_group(videos, caption_prefix="Все видео этой сессии")
        if ok:
            logger.info(f"Удаляем видеофайлы (всего: {len(videos)})...")
            for v in videos:
                time.sleep(DELETE_VIDEO_DELAY)
                delete_file_safe(v)
        else:
            logger.warning("Медиагруппа не была отправлена (ошибка?). Видео не удаляем.")
    else:
        logger.info("Нет накопленных видео, нечего отправлять.")

    # (2) Удаляем кадры (capture.jpg)
    folders = current_session.get("folders", set())
    if folders:
        logger.info(f"Удаляем кадры (capture.jpg) из {len(folders)} папок.")
        for f in folders:
            delete_all_captures_in_folder(f)

    # (3) Сбрасываем current_session
    current_session = None
    logger.info("Сессия закрыта.\n")


def add_video_to_session(file_path: str):
    global current_session
    if current_session is None:
        logger.info("Нет активной сессии, игнорируем видео.")
        return
    current_session["videos"].append(file_path)


def add_folder_to_session(folder_path: str):
    global current_session
    if current_session is None:
        return
    current_session["folders"].add(folder_path)


def session_active() -> bool:
    return (current_session is not None)


# -----------------------------------------------------------------------------
# 8) WATCHDOG ОБРАБОТЧИК
# -----------------------------------------------------------------------------
class ZoneMinderEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path

        # Защита от повторной обработки
        if file_path in discovered_files:
            logger.info(f"Файл {file_path} уже обрабатывали, пропускаем.")
            return
        discovered_files.add(file_path)

        filename = os.path.basename(file_path)
        folder   = os.path.dirname(file_path)

        e_id = parse_event_id(folder)
        if e_id not in events_info:
            events_info[e_id] = {
                "seen_frames": set(),
                "sent_65": False
            }

        # --- КАДР ---
        if filename.endswith("-capture.jpg"):
            frame_no = parse_frame_number(filename)
            if frame_no < 0:
                return

            events_info[e_id]["seen_frames"].add(frame_no)

            # Если сессия активна, добавим папку в "folders" для последующего удаления кадров
            if session_active():
                add_folder_to_session(folder)

            if frame_no == 65:
                # 1) Если нет активной сессии, создаём
                if not session_active():
                    start_session()

                # 2) Если уже отправляли кадр в ЭТОЙ сессии → пропускаем
                if current_session and current_session["sent_first_frame"]:
                    logger.info(f"Сессия уже активна, 65‑й кадр для event {e_id} игнорируем (уже был кадр).")
                    return

                # 3) Если уже отправляли 65 для самого event e_id — тоже пропускаем
                if events_info[e_id]["sent_65"]:
                    logger.info(f"65‑й кадр (event {e_id}) уже был отправлен, игнорируем.")
                    return

                # 4) Если 66 уже есть, отправим 65 сразу, иначе ждём 66
                if 66 in events_info[e_id]["seen_frames"]:
                    self._send_frame_65(folder, file_path, e_id)
                else:
                    logger.info(f"Пришёл 65‑й кадр (event {e_id}), но ждём 66‑й.")

            elif frame_no == 66:
                # Если 65 уже есть и не отправляли
                if 65 in events_info[e_id]["seen_frames"] and not events_info[e_id]["sent_65"]:
                    path_65 = os.path.join(folder, "00065-capture.jpg")
                    self._send_frame_65(folder, path_65, e_id)

            # Остальные кадры игнорируем

        # --- ВИДЕО ---
        elif filename.endswith("-video.mp4"):
            def handle_video():
                logger.info(f"Найден видеофайл: {file_path} (event {e_id}).")
                stable = wait_for_file_stable(file_path)
                if not stable:
                    logger.warning(f"Видео {filename} (event {e_id}) не стабилизировалось, пропускаем.")
                    return
                add_video_to_session(file_path)

            threading.Thread(target=handle_video, daemon=True).start()

    def _send_frame_65(self, folder: str, file_path_65: str, event_id: str):
        # --- Новая защита ---
        if current_session and current_session["sent_first_frame"]:
            logger.info(
                f"_send_frame_65: Сессия уже активна, первый кадр был. Игнорируем кадр из event {event_id}"
            )
            return
        # --- Конец новой защиты ---

        logger.info(f"Отправляем 65‑й кадр (event {event_id}): {file_path_65}")
        ok = send_photo(
            file_path_65, 
            caption=f"Скриншот (65-й кадр) — событие {event_id}"
        )
        if ok:
            events_info[event_id]["sent_65"] = True
            if current_session:
                current_session["sent_first_frame"] = True

            # Можно сразу удалить этот 65‑й кадр, если не нужен:
            # delete_file_safe(file_path_65)
            # Иначе он удалится при end_session()

# -----------------------------------------------------------------------------
# 9) MAIN
# -----------------------------------------------------------------------------
def main():
    observer = Observer()
    handler  = ZoneMinderEventHandler()
    observer.schedule(handler, path=ZONEMINDER_DIR, recursive=True)
    observer.start()

    logger.info(f"Запущено наблюдение за {ZONEMINDER_DIR}. Логи: {LOG_FILE}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
