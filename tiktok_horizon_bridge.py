"""Пересылает комментарии TikTok LIVE в игровой чат Horizon."""

import asyncio
import json
import logging
import msvcrt
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent


# Укажите имя аккаунта, который ведёт эфир, или ссылку на его LIVE.
TIKTOK_CREATOR = os.environ.get("TIKTOK_CREATOR", "").strip()

# Можно вписать полный путь вручную. Если оставить None, путь возьмётся из
# выбранной версии лаунчера, а при отсутствии настроек будет найдена свежая сборка.
HORIZON_CTL = None

# Ограничения длины не дают одному комментарию занять весь игровой чат.
MAX_NICK_LENGTH = 32
MAX_COMMENT_LENGTH = 240
QUEUE_LIMIT = 100
RECONNECT_DELAY_SECONDS = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)


def clean_text(value: Any, limit: int) -> str:
    """Удаляет переводы строк и управляющие символы, затем обрезает текст."""
    text = str(value or "")
    text = re.sub(r"[\r\n\t\x00-\x1f\x7f]", " ", text)
    return " ".join(text.split())[:limit]


def find_horizon_ctl() -> str | None:
    """Находит CLI в выбранной лаунчером версии Horizon или в PATH."""
    if HORIZON_CTL:
        return HORIZON_CTL if Path(HORIZON_CTL).is_file() else None

    launcher_root = Path(os.environ.get("APPDATA", "")) / "horizon-launcher"
    versions_dir = launcher_root / "versions"
    settings_file = launcher_root / "settings.json"

    # В первую очередь используем выбранную в лаунчере сборку.
    try:
        selected = json.loads(settings_file.read_text(encoding="utf-8")).get("selected")
        if selected:
            selected_cli = versions_dir / selected / "horizon-ctl.exe"
            if selected_cli.is_file():
                return str(selected_cli)
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    # Если настройки недоступны, берём последнюю установленную сборку.
    try:
        candidates = sorted(
            versions_dir.glob("*/horizon-ctl.exe"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return str(candidates[0])
    except OSError:
        pass

    return shutil.which("horizon-ctl") or shutil.which("horizon-ctl.exe")


def send_to_horizon(nickname: str, comment: str) -> None:
    """Публикует системное сообщение без имени игрового аккаунта."""
    line = json.dumps(f"@{nickname}: {comment}", ensure_ascii=False)
    result = subprocess.run(
        [HORIZON_CTL_PATH, "command", f"tellraw @a {line}"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(details or f"horizon-ctl завершился с кодом {result.returncode}")


async def forward_comments(queue: asyncio.Queue[tuple[str, str] | None]) -> None:
    """Отправляет сообщения по одному, сохраняя порядок комментариев."""
    while True:
        item = await queue.get()
        try:
            if item is None:
                return
            nickname, comment = item
            try:
                await asyncio.to_thread(send_to_horizon, nickname, comment)
                logging.info("Отправлено в Horizon: @%s: %s", nickname, comment)
            except subprocess.TimeoutExpired:
                logging.warning("horizon-ctl не ответил за 8 секунд; сообщение пропущено.")
            except (OSError, RuntimeError) as error:
                logging.warning("Не удалось отправить сообщение в Horizon: %s", error)
        finally:
            queue.task_done()


async def run_bridge() -> None:
    queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue(maxsize=QUEUE_LIMIT)
    worker = asyncio.create_task(forward_comments(queue))

    try:
        while True:
            client = TikTokLiveClient(unique_id=TIKTOK_CREATOR)

            @client.on(CommentEvent)
            async def on_comment(event: CommentEvent) -> None:
                user = getattr(event, "user", None)
                # unique_id — именно TikTok-ник; nickname является отображаемым именем.
                nickname = clean_text(getattr(user, "unique_id", None), MAX_NICK_LENGTH)
                comment = clean_text(getattr(event, "comment", ""), MAX_COMMENT_LENGTH)
                if not nickname or not comment:
                    return
                logging.info("Комментарий получен из TikTok: @%s: %s", nickname, comment)
                try:
                    queue.put_nowait((nickname, comment))
                except asyncio.QueueFull:
                    logging.warning("Очередь переполнена; новый комментарий пропущен.")

            try:
                logging.info("Подключаюсь к LIVE автора %s", TIKTOK_CREATOR)
                # start() создаёт фоновую задачу и сразу возвращается.
                # connect() ждёт закрытия эфира и не плодит подключения.
                await client.connect()
                logging.warning("Соединение с TikTok завершилось.")
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("TikTok отключился или не удалось подключиться.")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

            logging.info("Повторное подключение через %s секунд.", RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


def acquire_single_instance_lock():
    """Не даёт запустить несколько копий моста и дублировать сообщения."""
    lock_path = Path(os.environ.get("TEMP", ".")) / "tiktok_horizon_bridge.lock"
    handle = lock_path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        raise SystemExit("Мост уже запущен. Закрой другое окно моста и попробуй снова.")
    return handle


def main() -> None:
    if not TIKTOK_CREATOR or TIKTOK_CREATOR == "@ваш_аккаунт":
        raise SystemExit("Сначала укажите автора эфира в TIKTOK_CREATOR.")
    global HORIZON_CTL_PATH
    HORIZON_CTL_PATH = find_horizon_ctl()
    if HORIZON_CTL_PATH is None:
        raise SystemExit("Не найден horizon-ctl.exe: проверь установку Horizon или укажи путь в HORIZON_CTL.")
    logging.info("Используется Horizon CLI: %s", HORIZON_CTL_PATH)
    try:
        control_check = subprocess.run(
            [HORIZON_CTL_PATH, "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"Не удалось проверить управление Horizon: {error}")
    if control_check.returncode != 0:
        raise SystemExit(
            "Horizon запущен без управления для horizon-ctl. В Horizon Launcher открой "
            "Settings → Game arguments, добавь --control, перезапусти игру, снова "
            "открой мир для сети и запусти мост."
        )
    lock_handle = acquire_single_instance_lock()
    try:
        asyncio.run(run_bridge())
    except KeyboardInterrupt:
        logging.info("Мост остановлен пользователем.")
    finally:
        try:
            lock_handle.seek(0)
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            lock_handle.close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as error:
        # При запуске двойным щелчком окно не закроется до прочтения ошибки.
        if error.code:
            print(f"\nОшибка запуска: {error}")
            input("Нажмите Enter, чтобы закрыть это окно...")
            raise

