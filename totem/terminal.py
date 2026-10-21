"""Plain-text serial backend for the Minitel in Ascii 80 col mode.

Two jobs: turn the 40x24 screen into bytes (encode_screen) and turn bytes
from the keyboard into app keys (KeyDecoder). Neither touches the serial
port, so both are testable without hardware.

At 1200 baud a 7E1 byte takes 10 bit times, so only ~120 characters per
second get through: a full 40x24 redraw takes several seconds. That's why
encode_screen sends only the rows that changed when the terminal supports
cursor addressing, and trims trailing spaces.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .app import (ANNUL, CORREZIONE, GUIDA, INDICE, INVIO, PRECEDENTE, RIPETIZ,
                  SEGUENTE)

ROWS = 24

# Terminal control profiles. The HCS 80's command set in Ascii mode isn't
# documented in what we have, so "probe" tries them and you pick the one
# that works. "plain" needs nothing but CR+LF.
PROFILES = {
    "plain": {"clear": b"", "goto": None, "eol": b""},
    "ff": {"clear": b"\x0c", "goto": None, "eol": b""},
    "ansi": {"clear": b"\x1b[2J\x1b[H",
             "goto": lambda r, c: f"\x1b[{r + 1};{c + 1}H".encode(),
             "eol": b"\x1b[K"},
    "vt52": {"clear": b"\x1bH\x1bJ",
             "goto": lambda r, c: bytes([0x1B, ord("Y"), 32 + r, 32 + c]),
             "eol": b"\x1bK"},
}

_ACCENTS = {"à": "a'", "è": "e'", "é": "e'", "ì": "i'", "ò": "o'", "ù": "u'",
            "À": "A'", "È": "E'", "É": "E'", "Ì": "I'", "Ò": "O'", "Ù": "U'",
            "ç": "c", "Ç": "C", "€": "EUR", "£": "GBP", "§": "par.", "°": "o"}


def to_ascii(s: str) -> str:
    """Spell out the characters plain ASCII lacks (è -> e', € -> EUR)."""
    s = "".join(_ACCENTS.get(ch, ch) for ch in s)
    return s.encode("ascii", "replace").decode("ascii")


def _row_bytes(row: str, margin: int) -> bytes:
    return to_ascii(" " * margin + row.rstrip()).encode("ascii")


def encode_screen(rows: list[str], prev: list[str] | None, profile: str = "plain",
                  margin: int = 0, force_full: bool = False) -> bytes:
    """Bytes that turn the terminal from `prev` into `rows`.

    margin shifts everything right (only useful to centre a 40-column screen).
    """
    p = PROFILES[profile]
    goto = p["goto"]
    shown = rows
    if p["clear"]:
        # The clear sequence already blanked the screen, so blank rows at the
        # bottom need no bytes.
        while shown and not shown[-1].strip():
            shown = shown[:-1]
    full = p["clear"] + b"\r\n".join(_row_bytes(r, margin) for r in shown)
    if goto is None:
        # No cursor addressing: scroll the new screen in below the old one.
        return (b"\r\n" + full) if profile == "plain" else full
    if prev is None or force_full:
        return full
    diff = b"".join(goto(i, 0) + _row_bytes(r, margin) + p["eol"]
                    for i, (r, o) in enumerate(zip(rows, prev)) if r != o)
    # Park the cursor on the last row so a local echo lands out of the way.
    diff += goto(ROWS - 1, len(rows[0]) - 1)
    return diff if len(diff) < len(full) else full


def estimate_seconds(data: bytes, baud: int = 1200) -> float:
    """Transmission time for 7E1: 10 bit times per byte."""
    return len(data) * 10 / baud


class KeyDecoder:
    """Bytes from the terminal -> app keys, using a learned keymap.

    keymap maps key names (INDICE, SEGUENTE, ...) to lists of byte
    sequences. Printable ASCII passes through as typed characters.
    """
    DEFAULTS = {INVIO: [b"\r"], CORREZIONE: [b"\x08", b"\x7f"], SEGUENTE: [b"\t"]}

    def __init__(self, keymap: dict[str, list[bytes]] | None = None):
        table = {k: list(v) for k, v in self.DEFAULTS.items()}
        for name, seqs in (keymap or {}).items():
            table[name] = list(seqs)
        self.seqs: dict[bytes, str] = {s: name for name, ss in table.items() for s in ss}
        self.buf = b""

    def _is_prefix(self, b: bytes) -> bool:
        return any(s.startswith(b) and s != b for s in self.seqs)

    def feed(self, data: bytes) -> list[str]:
        self.buf += data
        return self._drain(final=False)

    def flush(self) -> list[str]:
        """Called after a pause: nothing more is coming, resolve what's left."""
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[str]:
        out: list[str] = []
        while self.buf:
            if not final and self._is_prefix(self.buf):
                break  # may still turn into a longer sequence
            match = max((s for s in self.seqs if self.buf.startswith(s)),
                        key=len, default=None)
            if match:
                out.append(self.seqs[match])
                self.buf = self.buf[len(match):]
                continue
            b = self.buf[0]
            self.buf = self.buf[1:]
            if 32 <= b < 127:
                out.append(chr(b))
            # other control bytes are dropped
        return out


KEY_NAMES = [INDICE, SEGUENTE, PRECEDENTE, ANNUL, CORREZIONE, GUIDA, RIPETIZ, INVIO]


def load_keymap(path: str | Path) -> dict[str, list[bytes]]:
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text())
    return {k: [bytes.fromhex(h) for h in v] for k, v in raw.items()}


def save_keymap(path: str | Path, keymap: dict[str, list[bytes]]) -> None:
    Path(path).write_text(json.dumps(
        {k: [s.hex() for s in v] for k, v in keymap.items()}, indent=2))


class SerialTerminal:
    """Thin wrapper over a pyserial port (or anything with read/write)."""

    def __init__(self, port, profile: str = "plain", margin: int = 0,
                 baud: int = 1200):
        self.port = port
        self.profile = profile
        self.margin = margin
        self.baud = baud
        self.prev: list[str] | None = None

    def draw(self, rows: list[str], full: bool = False) -> float:
        data = encode_screen(rows, self.prev, self.profile, self.margin, full)
        self.port.write(data)
        self.prev = list(rows)
        return estimate_seconds(data, self.baud)

    def read(self) -> bytes:
        return self.port.read(64)


def open_port(device: str, baud: int = 1200, bits: int = 7, parity: str = "E",
              stop: int = 1, timeout: float = 0.1):
    import serial  # imported late so tests and console mode don't need it
    return serial.Serial(
        device, baudrate=baud, bytesize=bits, parity=parity,
        stopbits=stop, timeout=timeout, write_timeout=5)


def now() -> float:
    return time.monotonic()
