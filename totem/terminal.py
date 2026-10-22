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
import re
import sys
import time
from pathlib import Path

from .text import ascii_spell
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

to_ascii = ascii_spell  # kept as the terminal-facing name


def _row_bytes(row: str, margin: int) -> bytes:
    return to_ascii(" " * margin + row.rstrip()).encode("ascii")


def _segments(text: str, min_gap: int) -> list[tuple[int, str]]:
    """Split a row into (column, text) pieces, dropping runs of at least
    min_gap spaces: jumping over them costs fewer bytes than sending them."""
    segs, col = [], 0
    for m in re.finditer(" {%d,}" % max(1, min_gap), text):
        if m.start() > col:
            segs.append((col, text[col:m.start()]))
        col = m.end()
    if col < len(text):
        segs.append((col, text[col:]))
    return segs


def _sparse_row(i: int, row: str, goto, margin: int) -> bytes:
    """Row i drawn piece by piece with cursor jumps. Assumes it is blank."""
    text = row.rstrip()
    min_gap = len(goto(i, 79)) + 1          # a jump costs about this many bytes
    return b"".join(goto(i, c + margin) + to_ascii(seg).encode("ascii")
                    for c, seg in _segments(text, min_gap))


def _full_draw(rows: list[str], goto, margin: int) -> bytes:
    """Draw every row on a blank screen, cursor at home, choosing for each row the
    cheaper of 'line feeds + the row as it is' and 'jump + only the pieces'."""
    out = []
    cur = None                      # row the cursor is on; None = still at home
    for i, row in enumerate(rows):
        if not row.strip():
            continue
        moves = i if cur is None else i - cur
        dense = b"\r\n" * moves + _row_bytes(row, margin)
        sparse = _sparse_row(i, row, goto, margin)
        out.append(min(dense, sparse, key=len))
        cur = i
    return b"".join(out)


def encode_screen(rows: list[str], prev: list[str] | None, profile: str = "plain",
                  margin: int = 0, force_full: bool = False) -> bytes:
    """Bytes that turn the terminal from `prev` into `rows`.

    margin shifts everything right (only useful to centre a 40-column screen).
    With cursor addressing, long runs of spaces are skipped with a cursor jump
    instead of being sent, and only changed rows are redrawn.
    """
    p = PROFILES[profile]
    goto = p["goto"]
    shown = rows
    if p["clear"]:
        # The clear sequence already blanked the screen, so blank rows at the
        # bottom need no bytes.
        while shown and not shown[-1].strip():
            shown = shown[:-1]
    if goto is None:
        # No cursor addressing: scroll the new screen in below the old one.
        full = p["clear"] + b"\r\n".join(_row_bytes(r, margin) for r in shown)
        return (b"\r\n" + full) if profile == "plain" else full
    full = p["clear"] + _full_draw(shown, goto, margin)
    if prev is None or force_full:
        return full
    pieces = []
    for i, (r, o) in enumerate(zip(rows, prev)):
        if r == o:
            continue
        dense = goto(i, 0) + _row_bytes(r, margin) + p["eol"]
        sparse = goto(i, 0) + p["eol"] + _sparse_row(i, r, goto, margin)
        pieces.append(min(dense, sparse, key=len))
    # Park the cursor on the last row so a local echo lands out of the way.
    diff = b"".join(pieces) + goto(ROWS - 1, len(rows[0]) - 1)
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

    def try_draw(self, rows: list[str], full: bool = False) -> float:
        """draw() that never raises: a stuck or failing port must not stop the totem.

        After a failure the terminal's screen is in an unknown state, so the
        next draw is a full redraw.
        """
        try:
            return self.draw(rows, full)
        except Exception as e:  # serial timeouts, device errors...
            print(f"[errore di scrittura sulla seriale: {type(e).__name__}: {e}]",
                  file=sys.stderr, flush=True)
            self.prev = None
            return 0.0

    def read(self) -> bytes:
        return self.port.read(64)


def open_port(device: str, baud: int = 1200, bits: int = 7, parity: str = "E",
              stop: int = 1, timeout: float = 0.1):
    import serial  # imported late so tests and console mode don't need it
    return serial.Serial(
        device, baudrate=baud, bytesize=bits, parity=parity,
        stopbits=stop, timeout=timeout, write_timeout=60)


def now() -> float:
    return time.monotonic()
