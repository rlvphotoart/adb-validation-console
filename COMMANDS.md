# Command Reference

The preview bar displays the absolute `adb.exe` path and selected `-s SERIAL` argument. Presets below use the listed argument sequence after `adb.exe`.

## Connection

| Action | ADB arguments | Safety |
|---|---|---|
| ADB Devices | `devices -l` | SAFE |
| ADB Kill Server | `kill-server` | CAUTION |
| ADB Start Server | `start-server` | CAUTION |
| ADB Reconnect | `reconnect` | CAUTION |
| ADB USB | `usb` | CAUTION |
| ADB TCP/IP 5555 | `tcpip 5555` | CAUTION |

## System

| Action | ADB arguments | Safety |
|---|---|---|
| Uptime | `shell uptime` | SAFE |
| Date | `shell date` | SAFE |
| Memory | `shell free -m` | SAFE |
| CPU Info | `shell cat /proc/cpuinfo` | SAFE |
| Memory Info | `shell cat /proc/meminfo` | SAFE |

## Build

| Action | ADB arguments | Safety |
|---|---|---|
| All Properties | `shell getprop` | SAFE |
| Build Type | `shell getprop ro.build.type` | SAFE |

## Apps

| Action | ADB arguments | Safety |
|---|---|---|
| List Packages | `shell pm list packages` | SAFE |
| System Packages | `shell pm list packages -s` | SAFE |
| Third Party Packages | `shell pm list packages -3` | SAFE |
| Running Processes | `shell ps -A` | SAFE |
| CPU Snapshot | `shell top -n 1` | SAFE |
| Top Activity | `shell dumpsys activity top` | SAFE |
| Activity Stack | `shell dumpsys activity activities` | SAFE |

## Network

| Action | ADB arguments | Safety |
|---|---|---|
| IP Addresses | `shell ip addr` | SAFE |
| Routes | `shell ip route` | SAFE |
| Neighbors | `shell ip neigh` | SAFE |
| Ping | `shell ping -c 4 8.8.8.8` | SAFE |
| ADB TCP Port | `shell getprop service.adb.tcp.port` | SAFE |
| Persistent ADB Port | `shell getprop persist.adb.tcp.port` | SAFE |

## Bluetooth

| Action | ADB arguments | Safety |
|---|---|---|
| Bluetooth State | `shell dumpsys bluetooth_manager` | SAFE |
| Bluetooth Properties | `shell getprop` | SAFE |

## Audio

| Action | ADB arguments | Safety |
|---|---|---|
| Audio State | `shell dumpsys audio` | SAFE |
| Audio Flinger | `shell dumpsys media.audio_flinger` | SAFE |
| Media Sessions | `shell dumpsys media_session` | SAFE |

## Automotive

| Action | ADB arguments | Safety |
|---|---|---|
| Car Service | `shell dumpsys car_service` | SAFE |
| Service List | `shell service list` | SAFE |

## Display

| Action | ADB arguments | Safety |
|---|---|---|
| Display Info | `shell dumpsys display` | SAFE |
| Window Info | `shell dumpsys window` | SAFE |
| Resolution | `shell wm size` | SAFE |
| Density | `shell wm density` | SAFE |

## Files

| Action | ADB arguments | Safety |
|---|---|---|
| List /sdcard | `shell ls -lah /sdcard` | SAFE |
| List /data/local/tmp | `shell ls -lah /data/local/tmp` | SAFE |

## Security

| Action | ADB arguments | Safety |
|---|---|---|
| Check Root | `shell id` | SAFE |
| Check SELinux | `shell getenforce` | SAFE |
| Verified Boot | `shell getprop ro.boot.verifiedbootstate` | SAFE |
| VBMeta State | `shell getprop ro.boot.vbmeta.device_state` | SAFE |
| Factory Directory | `shell ls -ld /factory` | SAFE |
| Factory Context | `shell ls -ldZ /factory` | SAFE |
| Vendor Factory Directory | `shell ls -ld /mnt/vendor/factory` | SAFE |
| Vendor Factory Context | `shell ls -ldZ /mnt/vendor/factory` | SAFE |
| Mounts | `shell mount` | SAFE |
| Factory Mounts | `shell mount` | SAFE |
| SELinux Denials | `logcat -b all -d` | SAFE |

## Kernel

| Action | ADB arguments | Safety |
|---|---|---|
| Kernel Log | `shell dmesg` | SAFE |
| Touchscreen | `shell dmesg` | SAFE |
| Kernel USB | `shell dmesg` | SAFE |
| Kernel Wi-Fi | `shell dmesg` | SAFE |
| Kernel Bluetooth | `shell dmesg` | SAFE |
| Kernel Errors | `shell dmesg` | SAFE |
| Input Devices | `shell cat /proc/bus/input/devices` | SAFE |
| Input Capabilities | `shell getevent -lp` | SAFE |

## Storage

| Action | ADB arguments | Safety |
|---|---|---|
| Storage Overview | `shell df -h` | SAFE |
| Disk Usage | `shell df -h` | SAFE |
| Mount Table | `shell cat /proc/mounts` | SAFE |

## Diagnostics

| Action | ADB arguments | Safety |
|---|---|---|
| Logcat Dump | `logcat -d` | SAFE |
| Crash Buffer | `logcat -b crash -d` | SAFE |
| Reboot Android | `reboot` | DESTRUCTIVE |
| Reboot Recovery | `reboot recovery` | DESTRUCTIVE |
| Reboot Bootloader | `reboot bootloader` | DESTRUCTIVE |
| ADB Root | `root` | CAUTION |
| ADB Unroot | `unroot` | CAUTION |
| Clear Logcat | `logcat -c` | CAUTION |

## Dumpsys

| Action | ADB arguments | Safety |
|---|---|---|
| Dumpsys activity | `shell dumpsys activity` | SAFE |
| Dumpsys window | `shell dumpsys window` | SAFE |
| Dumpsys package | `shell dumpsys package` | SAFE |
| Dumpsys power | `shell dumpsys power` | SAFE |
| Dumpsys battery | `shell dumpsys battery` | SAFE |
| Dumpsys display | `shell dumpsys display` | SAFE |
| Dumpsys input | `shell dumpsys input` | SAFE |
| Dumpsys audio | `shell dumpsys audio` | SAFE |
| Dumpsys media.audio_flinger | `shell dumpsys media.audio_flinger` | SAFE |
| Dumpsys media_session | `shell dumpsys media_session` | SAFE |
| Dumpsys bluetooth_manager | `shell dumpsys bluetooth_manager` | SAFE |
| Dumpsys wifi | `shell dumpsys wifi` | SAFE |
| Dumpsys connectivity | `shell dumpsys connectivity` | SAFE |
| Dumpsys usb | `shell dumpsys usb` | SAFE |
| Dumpsys meminfo | `shell dumpsys meminfo` | SAFE |
| Dumpsys cpuinfo | `shell dumpsys cpuinfo` | SAFE |

## Input

| Action | ADB arguments | Safety |
|---|---|---|
| Home | `shell input keyevent KEYCODE_HOME` | CAUTION |
| Back | `shell input keyevent KEYCODE_BACK` | CAUTION |
| Recent Apps | `shell input keyevent KEYCODE_APP_SWITCH` | CAUTION |
| Volume Up | `shell input keyevent KEYCODE_VOLUME_UP` | CAUTION |
| Volume Down | `shell input keyevent KEYCODE_VOLUME_DOWN` | CAUTION |
| Mute | `shell input keyevent KEYCODE_VOLUME_MUTE` | CAUTION |
| Power | `shell input keyevent KEYCODE_POWER` | CAUTION |

## Additional workflows

- Device Info: reads 16 `getprop` values, `uname -a`, `id`, and `getenforce`.
- Live logcat: `logcat *:LEVEL`, with Python text or regex filtering; saved under `ADB_Output/Logcat`.
- Live touch events: `shell getevent`; touchscreen discovery reads `/proc/bus/input/devices`.
- Push/Pull: `push LOCAL REMOTE` and `pull REMOTE LOCAL`.
- Device file browser: `shell ls -la -- PATH/` on the selected device, with path quoting, folder navigation and local name filtering.
- Apps: `dumpsys package`, `am force-stop`, `pm clear`, `monkey -p PACKAGE 1`, `uninstall`, `pm disable-user --user 0`, `pm enable`.
- Screenshots: `exec-out screencap -p`; recording: `shell screenrecord /sdcard/validation_recording.mp4` and `pull`.
- Bugreport: `bugreport PATH`; snapshot and support bundle collect the read-only commands documented in `command_library.py`.
- Network target actions: `connect IP:PORT` and `disconnect IP:PORT`.
- Shell page: custom ADB or Android shell argv, with explicit preview and safety classification.
