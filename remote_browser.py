"""Read-only remote file listing helpers for the selected Android device."""
from __future__ import annotations
import posixpath
import re
import shlex
from dataclasses import dataclass

@dataclass(frozen=True)
class RemoteEntry:
    name: str
    path: str
    kind: str
    size: int | None
    modified: str
    permissions: str
    target: str = ''


def normalize_remote_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith('/') or '\x00' in path or '\n' in path or '\r' in path:
        raise ValueError('Enter an absolute Android path without control characters.')
    return posixpath.normpath(path)


def child_path(directory: str, name: str) -> str:
    if not name or name in ('.', '..') or '/' in name or '\x00' in name or '\n' in name or '\r' in name:
        raise ValueError('Invalid file name in device listing.')
    return normalize_remote_path(posixpath.join(normalize_remote_path(directory), name))


def parent_path(path: str) -> str:
    return posixpath.dirname(normalize_remote_path(path)) or '/'


def safe_push_target(path: str) -> bool:
    try: target = normalize_remote_path(path)
    except ValueError: return False
    return any(target == root or target.startswith(root + '/')
               for root in ('/sdcard', '/data/local/tmp', '/storage/emulated/0'))


def list_command(path: str) -> list[str]:
    # adb shell passes this single string to Android's shell. POSIX quoting protects
    # spaces, quotes and shell metacharacters in a device path. A trailing slash
    # opens directory symlinks such as /sdcard instead of listing the link itself.
    directory = normalize_remote_path(path)
    if directory != '/': directory += '/'
    return ['shell', 'ls -la -- ' + shlex.quote(directory)]


def parse_long_listing(output: str, directory: str) -> tuple[list[RemoteEntry], list[str]]:
    directory = normalize_remote_path(directory)
    entries: list[RemoteEntry] = []
    skipped: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith('total '):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6 or not re.match(r'^[bcdlps-][rwxStTs-]{9}', parts[0]) or not parts[4].isdigit():
            skipped.append(raw)
            continue
        permissions, _, _, _, size_text, tail = parts
        iso = re.match(r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\s+(.+)$', tail)
        classic = re.match(r'^([A-Za-z]{3}\s+\d{1,2}\s+(?:\d{2}:\d{2}|\d{4}))\s+(.+)$', tail)
        match = iso or classic
        if not match:
            skipped.append(raw)
            continue
        modified, name = match.groups()
        if name in ('.', '..'):
            continue
        target = ''
        if permissions.startswith('l') and ' -> ' in name:
            name, target = name.split(' -> ', 1)
        try:
            path = child_path(directory, name)
        except ValueError:
            skipped.append(raw)
            continue
        kind = 'Folder' if permissions.startswith('d') else 'Link' if permissions.startswith('l') else 'File'
        entries.append(RemoteEntry(name, path, kind, int(size_text), modified, permissions, target))
    entries.sort(key=lambda e: (e.kind != 'Folder', e.name.casefold()))
    return entries, skipped


def display_size(size: int | None) -> str:
    if size is None: return '—'
    if size < 1024: return f'{size} B'
    unit = 0
    number = float(size)
    while number >= 1024 and unit < 4:
        number /= 1024
        unit += 1
    return f'{number:.1f} {("B", "KB", "MB", "GB", "TB")[unit]}'
