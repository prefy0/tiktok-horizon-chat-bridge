# TikTok LIVE Chat Bridge for Horizon

This small Windows app sends TikTok LIVE comments to the in-game chat in
[Horizon](https://github.com/horizon-rust/horizon). Horizon is a Rust
reimplementation of Minecraft: Java Edition.

The bridge adds each viewer's TikTok username to their comment and shows it as a
system message in Horizon. This is a companion Python app. It is not Horizon,
and it is not a Minecraft Java mod or a Horizon WASM mod. TikTok gifts trigger
an on-screen username and gift alert plus a firework near the local player.

## What you need

- Windows
- Python 3.10 or newer
- Horizon installed with Horizon Launcher
- A public TikTok LIVE stream

## Setup

1. Download or clone this repository.
2. Open PowerShell in the project folder and install the Python package:

   ```powershell
   py -m pip install -r requirements.txt
   ```

3. In Horizon Launcher, open **Settings → Game arguments**, add `--control`,
   and restart Horizon.
4. Open your world to LAN. Allow commands/cheats so Horizon can show comments
   as system messages.
5. Double-click `run_bridge.bat`. When asked, enter the TikTok username of the
   account streaming LIVE. You can enter it with or without `@`.

The bridge finds `horizon-ctl.exe` in the Horizon version selected in the
launcher. Keep the bridge window open while streaming. Press `Ctrl+C` in that
window to stop it.

## How it works

- TikTok comments appear in Horizon like this:

  ```text
  @viewer_name: Hello, chat!
  ```

- Comments are sent in order.
- Gifts display the TikTok username and gift name on screen and launch a firework
  near the local player. Gift streaks trigger once, when the streak is complete.
- At startup, the bridge disables command feedback for the world so title and
  firework command confirmations do not fill the chat. Viewer comments and gift
  alerts remain visible. To restore command feedback later, run
  `/gamerule send_command_feedback true` in the world.
- The bridge reconnects if TikTok disconnects.
- Only one bridge window can run at a time.
- The message text is shortened and cleaned before it is sent to the game.

## Troubleshooting

- **Horizon control is unavailable:** check that `--control` is in Horizon
  Launcher's game arguments, then restart Horizon.
- **Comments do not appear:** for a LAN world, make sure commands/cheats are
  allowed. The bridge uses Horizon's `tellraw` command to show system messages.
- **TikTok does not connect:** make sure the creator is live and the username
  was entered correctly. TikTokLive is an unofficial library, and TikTok may
  change how its LIVE chat works.

## Third-party dependencies and licenses

This repository's own code is licensed under MIT (see [LICENSE](LICENSE)).
It uses [TikTokLive](https://github.com/isaackogan/TikTokLive) version 7.0.1,
which is installed separately by pip and is not bundled in this repository.
TikTokLive has its own Modified AGPL-3.0 license and additional terms; see its
[license file](https://github.com/isaackogan/TikTokLive/blob/master/LICENSE).
Those terms include an exception for integration into client applications,
stream bots, and similar tools, as well as restrictions on certain hosted
services. Review the upstream license if you modify how this project is
distributed or operated.

Horizon is a separate project and is not bundled here. See the
[Horizon license](https://github.com/horizon-rust/horizon/blob/main/LICENSE).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
