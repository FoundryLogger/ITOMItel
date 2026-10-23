"""User-changeable settings, shown on the Impostazioni screen (Guida -> 1).

Each setting has a fixed list of values; pressing its number on the screen moves
to the next one, wrapping around. Values are saved to a small JSON file so they
survive a restart of the Raspberry Pi. Anything unknown in the file is ignored.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# key -> (label on the screen, short label for 40 columns, [(value, text), ...])
SPECS: dict[str, tuple[str, str, list]] = {
    "saver_after": ("Screensaver dopo", "Screensaver", [
        (60, "1 minuto"), (300, "5 minuti"), (600, "10 minuti"), (0, "mai")]),
    "idle_after": ("Ritorno alla home dopo", "Torna alla home", [
        (60, "1 minuto"), (120, "2 minuti"), (300, "5 minuti"), (0, "mai")]),
    "ink": ("Carattere di riempimento", "Riempimento", [
        ("#", "#"), ("@", "@"), ("X", "X"), ("*", "*"), ("+", "+"), ("O", "O")]),
    "hold": ("Schermo pieno fermo per", "Fermo per", [
        (15, "15 secondi"), (30, "30 secondi"), (60, "1 minuto"), (120, "2 minuti")]),
}

DEFAULTS = {"saver_after": 300, "idle_after": 120, "ink": "#", "hold": 30}
ORDER = list(SPECS)          # the number on the screen is the position + 1


class Settings:
    def __init__(self, path: str | Path | None = None, **overrides):
        self.path = Path(path) if path else None
        self.values = dict(DEFAULTS)
        self._load()
        for key, value in overrides.items():          # command-line choices win at start-up
            if value is not None and key in SPECS:
                self.values[key] = value

    @staticmethod
    def _valid(key: str, value) -> bool:
        return key in SPECS and any(value == v for v, _ in SPECS[key][2])

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            for key, value in data.items():
                if self._valid(key, value):
                    self.values[key] = value

    def save(self) -> None:
        if not self.path:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.values, indent=2))
            os.replace(tmp, self.path)
        except OSError:
            pass                                       # a read-only card must not stop the totem

    def __getitem__(self, key: str):
        return self.values[key]

    def text(self, key: str) -> str:
        value = self.values[key]
        for v, t in SPECS[key][2]:
            if v == value:
                return t
        return "mai" if value == 0 else f"{value} s" if isinstance(value, int) else str(value)

    def cycle(self, key: str) -> None:
        """Move to the next value of a setting and save. A value that isn't in the
        list (given on the command line) moves to the first one."""
        options = [v for v, _ in SPECS[key][2]]
        now = self.values[key]
        self.values[key] = options[(options.index(now) + 1) % len(options)] if now in options else options[0]
        self.save()

    # the names the rest of the program uses
    @property
    def saver_after(self) -> int:
        return self.values["saver_after"]

    @property
    def idle_after(self) -> int:
        return self.values["idle_after"]

    @property
    def ink(self) -> str:
        return self.values["ink"]

    @property
    def hold(self) -> int:
        return self.values["hold"]
