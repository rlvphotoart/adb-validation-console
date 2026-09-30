"""ADB discovery and argument-safe process execution."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CREATE_FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

@dataclass
class Result:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False

class PlatformToolsManager:
    def __init__(self, configured: str = '', executable: str | None = None,
                 source: str | None = None, cwd: str | None = None, which: Callable = shutil.which):
        self.configured = configured
        self.executable = executable or sys.executable
        self.source = source or __file__
        self.cwd = cwd or os.getcwd()
        self.which = which
        self.adb: Path | None = None

    def detect(self) -> Path | None:
        candidates = []
        if getattr(sys, 'frozen', False) or Path(self.executable).name.lower().startswith('adbvalidationconsole'):
            candidates.append(Path(self.executable).resolve().parent)
        candidates.extend((Path(self.source).resolve().parent, Path(self.cwd).resolve()))
        if self.configured:
            candidates.append(Path(self.configured).expanduser())
        for directory in candidates:
            for name in ('adb.exe', 'adb') if os.name != 'nt' else ('adb.exe',):
                path = directory / name
                if path.is_file():
                    self.adb = path.resolve()
                    return self.adb
        found = self.which('adb.exe') or self.which('adb')
        self.adb = Path(found).resolve() if found else None
        return self.adb

    @property
    def directory(self) -> Path:
        if self.adb is None:
            raise FileNotFoundError('adb.exe was not found. Select the Platform Tools folder in Settings.')
        return self.adb.parent

    def argv(self, args: list[str], serial: str | None = None) -> list[str]:
        if self.adb is None:
            raise FileNotFoundError('adb.exe was not found. Select the Platform Tools folder in Settings.')
        return [str(self.adb), *(['-s', serial] if serial else []), *args]

    def run(self, args: list[str], serial: str | None = None, timeout: float = 30,
            stop=None) -> Result:
        argv = self.argv(args, serial)
        start = time.monotonic()
        process = subprocess.Popen(argv, cwd=self.directory, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=CREATE_FLAGS)
        timed_out = False
        deadline = start + timeout
        while True:
            if stop is not None and stop.is_set():
                process.kill(); stdout, stderr = process.communicate(); break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill(); stdout, stderr = process.communicate(); timed_out = True; break
            try:
                stdout, stderr = process.communicate(timeout=min(0.25, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        return Result(argv, process.returncode, stdout.decode('utf-8', 'replace'),
                      stderr.decode('utf-8', 'replace'), time.monotonic()-start, timed_out)

    def start(self, args: list[str], serial: str | None = None, binary: bool = False):
        argv = self.argv(args, serial)
        return subprocess.Popen(argv, cwd=self.directory, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                bufsize=0 if binary else 1, creationflags=CREATE_FLAGS)

@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    details: str = ''


def parse_devices(output: str) -> list[Device]:
    devices = []
    for line in output.splitlines():
        if '\t' not in line:
            continue
        serial, rest = line.split('\t', 1)
        parts = rest.split(maxsplit=1)
        if serial and parts:
            devices.append(Device(serial, parts[0], parts[1] if len(parts) > 1 else ''))
    return devices


def friendly_error(result: Result) -> str:
    msg = (result.stdout + '\n' + result.stderr).lower()
    if result.timed_out: return 'Command timed out. The device may be busy or disconnected.'
    if 'failed to authenticate' in msg or 'unauthorized' in msg: return 'Device unauthorized. Accept the RSA prompt on the device and retry.'
    if 'offline' in msg: return 'Device offline. Reconnect it and refresh the list.'
    if 'connection refused' in msg: return 'Connection refused. Check the IP, port and ADB TCP mode.'
    if 'permission denied' in msg: return 'Permission denied by Android or the device filesystem.'
    if 'cannot run as root' in msg: return 'ROOT NOT AVAILABLE — PRODUCTION BUILD'
    if 'device not found' in msg or 'no devices' in msg: return 'Device disconnected or unavailable.'
    return ''
