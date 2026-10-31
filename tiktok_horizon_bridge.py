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
from TikTokLive.events import CommentEvent, GiftEvent


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
FIREWORK_LIFETIME_TICKS = 20

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


def run_horizon_command(command: str) -> None:
    """Выполняет одну игровую команду через horizon-ctl."""
    result = subprocess.run(
        [HORIZON_CTL_PATH, "command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(details or f"Команда Horizon завершилась с кодом {result.returncode}")


def player_position() -> tuple[float, float, float]:
    """Читает позицию управляемого игрока, чтобы запускать фейерверк рядом с ним."""
    result = subprocess.run(
        [HORIZON_CTL_PATH, "state"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(details or "Не удалось получить состояние Horizon")

    state = json.loads(result.stdout)
    position = state["player"]["position"]
    return float(position[0]), float(position[1]), float(position[2])


def show_gift_in_horizon(nickname: str, gift_name: str, quantity: int) -> None:
    """Показывает подарок на экране и запускает цветной фейерверк у игрока."""
    gift_name = clean_text(gift_name, 48) or "подарок"
    quantity = max(1, quantity)
    title = json.dumps(
        {"text": f"@{nickname}", "color": "light_purple", "bold": True},
        ensure_ascii=False,
    )
    subtitle = json.dumps(
        {"text": f"подарил(а): {gift_name} x{quantity}", "color": "gold"},
        ensure_ascii=False,
    )

    # Текст виден несколько секунд поверх игрового экрана.
    run_horizon_command("title @a times 5 50 10")
    run_horizon_command(f"title @a title {title}")
    run_horizon_command(f"title @a subtitle {subtitle}")

    # Компонент фейерверка задаёт цветной взрыв без выдачи предмета игроку.
    x, y, z = player_position()
    firework = (
        'summon minecraft:firework_rocket '
        f'{x:.3f} {y + 1.0:.3f} {z:.3f} '
        '{LifeTime:' + str(FIREWORK_LIFETIME_TICKS) + ',FireworksItem:'
        '{id:"minecraft:firework_rocket",count:1,components:'
        '{"minecraft:fireworks":{flight_duration:1,explosions:'
        '[{shape:"large_ball",colors:[I;16711935],has_trail:true}]}}}}'
    )
    run_horizon_command(firework)


async def forward_events(
    queue: asyncio.Queue[tuple[str, str, str, int] | None],
) -> None:
    """Последовательно отправляет комментарии и обрабатывает подарки."""
    while True:
        item = await queue.get()
        try:
            if item is None:
                return
            event_type, nickname, text, quantity = item
            try:
                if event_type == "comment":
                    await asyncio.to_thread(send_to_horizon, nickname, text)
                    logging.info("Отправлено в Horizon: @%s: %s", nickname, text)
                elif event_type == "gift":
                    await asyncio.to_thread(show_gift_in_horizon, nickname, text, quantity)
                    logging.info("Подарок в Horizon: @%s подарил(а) %s x%s", nickname, text, quantity)
            except subprocess.TimeoutExpired:
                logging.warning("horizon-ctl не ответил вовремя; событие пропущено.")
            except (OSError, RuntimeError, ValueError, KeyError, IndexError, TypeError) as error:
                logging.warning("Не удалось обработать событие в Horizon: %s", error)
        finally:
            queue.task_done()


async def run_bridge() -> None:
    queue: asyncio.Queue[tuple[str, str, str, int] | None] = asyncio.Queue(maxsize=QUEUE_LIMIT)
    worker = asyncio.create_task(forward_events(queue))

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
                    queue.put_nowait(("comment", nickname, comment, 1))
                except asyncio.QueueFull:
                    logging.warning("Очередь переполнена; новый комментарий пропущен.")

            @client.on(GiftEvent)
            async def on_gift(event: GiftEvent) -> None:
                user = getattr(event, "user", None)
                gift = getattr(event, "gift", None)
                nickname = clean_text(getattr(user, "unique_id", None), MAX_NICK_LENGTH)
                gift_name = clean_text(getattr(gift, "name", None), 48)
                if not nickname or not gift_name:
                    return

                # Серийные подарки приходят несколькими событиями; реагируем только на финальное.
                if getattr(event, "streaking", False):
                    return
                try:
                    quantity = max(1, int(getattr(event, "repeat_count", 1) or 1))
                except (TypeError, ValueError):
                    quantity = 1

                logging.info("Подарок из TikTok: @%s — %s x%s", nickname, gift_name, quantity)
                try:
                    queue.put_nowait(("gift", nickname, gift_name, quantity))
                except asyncio.QueueFull:
                    logging.warning("Очередь переполнена; подарок пропущен.")

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

    # Убираем ответы игровых команд из чата; комментарии зрителей через tellraw останутся видны.
    try:
        run_horizon_command("gamerule send_command_feedback false")
        logging.info("Служебные ответы игровых команд отключены для этого мира.")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        logging.warning("Не удалось отключить ответы команд в игровом чате: %s", error)

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

