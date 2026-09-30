"""Portable local configuration and bounded command history."""
import json
import sys
from pathlib import Path

BASE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
CONFIG = BASE / 'adb_console_config.json'
DEFAULT = {'platform_tools': '', 'target_ip': '10.19.229.1', 'target_port': '5555',
           'favorites': [], 'history': [], 'geometry': '1500x900', 'refresh_seconds': 12}

class Config:
    def __init__(self, path=CONFIG):
        self.path = Path(path)
        self.data = dict(DEFAULT)
        try:
            loaded = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict): self.data.update(loaded)
        except (OSError, ValueError): pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)

    def add_history(self, record):
        self.data['history'] = ([record] + self.data.get('history', []))[:200]
        self.save()
