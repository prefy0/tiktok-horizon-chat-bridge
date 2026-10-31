# TikTok LIVE → Horizon Chat Bridge

This is a companion integration for [Horizon](https://github.com/horizon-rust/horizon),
the open-source Rust reimplementation of Minecraft: Java Edition. It forwards
TikTok LIVE comments to the in-game Horizon chat, including each viewer's TikTok
handle, so stream viewers can take part in a Horizon session. This project is a
Python bridge, not a standalone game, a Java Edition mod, or a Horizon WASM mod.

Это внешний Python-мост для [Horizon](https://github.com/horizon-rust/horizon) —
Rust-переосмысления Minecraft: Java Edition. Он передаёт комментарии TikTok LIVE
в игровой чат Horizon вместе с TikTok-ником зрителя, чтобы аудитория стрима могла
участвовать в игре. Это интеграция для Horizon, а не отдельная игра или мод.

Сообщения появляются в чате как системные:

```text
@viewer_name: привет, чат!
```

Это внешний Python-мост, а не Wasm-мод Horizon. Он использует `TikTokLive` для
чтения эфира и `horizon-ctl` для управления запущенной игрой.

## Требования

- Windows и Python 3.10+
- Horizon Launcher с установленным Horizon
- `horizon-ctl.exe` в папке выбранной сборки лаунчера
- Публичный TikTok LIVE

## Установка

1. Установите зависимость:

   ```powershell
   py -m pip install -r requirements.txt
   ```

2. Укажите TikTok-аккаунт эфира через переменную окружения. Подойдёт имя с `@`
   или ссылка на эфир:

   ```powershell
   $env:TIKTOK_CREATOR = "@your_channel"
   ```

3. В Horizon Launcher откройте **Settings → Game arguments**, добавьте
   `--control` и перезапустите игру.
4. Подключитесь к миру/серверу с работающим чатом. Для локального мира откройте
   его для сети и разрешите команды/читы, чтобы `tellraw` мог отправлять
   системные сообщения.
5. Запустите `run_bridge.bat`.

Остановить мост можно сочетанием `Ctrl+C` в его окне. `horizon-ctl.exe` выбирается
автоматически по версии, выбранной в настройках Horizon Launcher.

## Поведение

- Комментарии отправляются по одному и в порядке получения.
- При отключении TikTok выполняется повторное подключение.
- Очередь ограничена 100 сообщениями, чтобы ограничить расход памяти.
- Одновременно работает только один экземпляр моста.
- Если Horizon не запущен с `--control`, скрипт выводит понятную ошибку.
- Текст ограничен по длине и очищается от переводов строк и управляющих знаков.

## Ограничения

`TikTokLive` — сторонняя неофициальная библиотека. TikTok может изменить протокол
эфира без предупреждения. `tellraw` требует разрешённых команд в игровом мире.
Сам мост не запускает Horizon, не открывает мир для сети и не управляет доступом
к эфиру.

## Лицензия

Проект распространяется по лицензии MIT. Подробности — в файле `LICENSE`.

