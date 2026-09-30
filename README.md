# ADB Validation Console

Portable, local desktop utility for Android Automotive / IVI validation. Python 3, Tkinter and the standard library are sufficient to run from source on Windows or macOS. It never calls a cloud service.

## Put it beside Platform Tools

```text
C:\platform-tools\
  adb.exe
  AdbWinApi.dll
  AdbWinUsbApi.dll
  fastboot.exe
  adb_validation_console.py
  platform_tools.py
  command_library.py
  config_manager.py
  Launch_ADB_Console.bat
  build_exe.bat
```

Double-click `Launch_ADB_Console.bat`. Alternatively, type `cmd` in the Explorer address bar while in `platform-tools`, then run `python adb_validation_console.py` (or `py -3 adb_validation_console.py`). If you build an EXE, copy `dist\AdbValidationConsole.exe` beside `adb.exe` and double-click it. Python is not needed to run that EXE.

On macOS, review the source UI with `python3 adb_validation_console.py`. It can use the installed `adb` from PATH. Run `python3 adb_validation_console.py --preview` for a labeled sample view that executes no ADB commands. A packaged macOS app is not included yet.

Discovery order: EXE directory when frozen, source directory, current working directory, saved Platform Tools folder, system PATH. Every ADB process receives the absolute ADB path and its directory as the working directory. `adb version` and `adb devices -l` run at startup. If ADB is missing, choose a Platform Tools folder in Settings.

## Use

Select an online, authorized device from the top selector. Commands targeting a device include `-s SERIAL`. Buttons display their exact command in the preview bar before execution. Safe reads run immediately; state-changing commands ask for confirmation. The Stop button terminates active streams and cancellable report/bugreport commands. F5 refreshes devices, Ctrl+L clears console, Ctrl+K opens Shell, Ctrl+S saves console.

On macOS, Command+L, Command+K, and Command+S also work. Click the command preview footer to copy its full command.

Right-click a preset button to add/remove a favorite. History and favorites are stored in `adb_console_config.json` beside the application. `ADB_Output` beside the application contains Bugreports, Logcat, Screenshots, ScreenRecords, Pulls, Reports and SupportBundle. Copy logcat files and support bundles only after reviewing them: they can contain device identifiers and private diagnostic data.

## Commands and areas

- **Connection:** devices, server start/kill/reconnect, USB/TCP mode, connect/disconnect/reconnect target.
- **Device/build/security:** selected `getprop` fields, `uname`, `id`, `getenforce`, verified boot, root/unroot, factory paths and SELinux denials.
- **Logs/kernel/input:** live and saved logcat, Python text/regex filters and log levels, dmesg presets, input device discovery and live getevent.
- **Apps/processes:** package lists, package details, force stop, clear, launch, uninstall, disable/enable; ps, top, activity stack.
- **Files/display:** list, push, pull, screenshot, screenrecord, resolution, density, keyevents.
- **Device file browser:** the Files page opens `/sdcard` on the selected device, shows names, type, size, modification time and permissions, and supports Up, Go, Refresh, quick paths, name filtering and double-click folder navigation. Pull copies a selected file or folder to a chosen local directory. Push copies a chosen local file into the current device folder and requires confirmation. Browser push targets are limited to `/sdcard`, `/data/local/tmp` and equivalent emulated storage; factory and system paths are read-only.
- **Network/Bluetooth/audio/automotive:** IP/route/neighbors, connectivity/wifi, Bluetooth, audio/media, car_service and service list.
- **Diagnostics:** 16 dumpsys presets, custom service, storage/system reads, reboot controls, validation snapshot and zipped support bundle.
- **Shell:** custom ADB or Android shell subcommands. Arguments are parsed into a list; the app never invokes a host shell or `shell=True`.

## Build on Windows

Run `py -3 -m pip install pyinstaller`, then double-click `build_exe.bat`. The output is `dist\AdbValidationConsole.exe`; copy it to the folder containing `adb.exe` and its DLLs. The source launcher still works without PyInstaller. A Windows build should be smoke-tested on the target corporate image before relying on it for validation work.

The private GitHub repository also builds a Windows x64 executable on every push to `main`, or manually from **Actions → Windows executable → Run workflow**. Open a successful run and download the `ADB-Validation-Console-Windows-x64` artifact. Extract `AdbValidationConsole.exe` and `SHA256.txt`; put the EXE beside Android Platform Tools (`adb.exe` and its DLLs), or choose the Platform Tools folder in Settings. GitHub Actions verifies source tests and the executable file format; opening the GUI and using a real device still require a Windows machine.

## Boundaries

The tool does not provide an interactive `adb shell` terminal; the Shell page runs one command at a time. Android permissions, root availability, vendor service names and `dmesg` access vary by build. Live logcat/getevent and screenrecord end through Stop. Some long Android operations may leave a partial output file after cancellation. ADB output is decoded as UTF-8 with replacement for invalid bytes. Manual command blocking is a convenience check, not a security sandbox; review command previews before running custom commands. No flashing, partition modification, factory reset, privilege escalation or SELinux changes are implemented.

The device file browser uses Android `ls -la` output. Most current Android builds support this format; unusual vendor `ls` formats may leave some rows unparsed, which the page reports. The browser has been tested with sample listings and on macOS without a connected device, but it still needs a live Android/IVI check for the target build.
