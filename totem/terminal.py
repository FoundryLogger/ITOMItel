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
from .app import (ANNUL, CORREZIONE, DESTRA, GUIDA, INDICE, INVIO, PRECEDENTE, RIPETIZ,
                  SEGUENTE, SINISTRA)

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
    # The arrows are the standard ANSI ones (seen in the log of the real HCS 80/08: right
    # ESC [ C, left ESC [ D); the other keys differ per terminal and come from keymap.json.
    DEFAULTS = {INVIO: [b"\r"], CORREZIONE: [b"\x08", b"\x7f"], SEGUENTE: [b"\t"],
                DESTRA: [b"\x1b[C"], SINISTRA: [b"\x1b[D"]}

    def __init__(self, keymap: dict[str, list[bytes]] | None = None):
        table = {k: list(v) for k, v in self.DEFAULTS.items()}
        for name, seqs in (keymap or {}).items():
            table[name] = list(seqs)
        self.seqs: dict[bytes, str] = {s: name for name, ss in table.items() for s in ss}
        self.buf = b""
        self.unknown: list[bytes] = []      # escape sequences nobody has taught us yet

    def take_unknown(self) -> list[bytes]:
        """The escape sequences seen and ignored since the last call (to log them)."""
        seen, self.unknown = self.unknown, []
        return seen

    @staticmethod
    def _escape_length(buf: bytes) -> int | None:
        """Length of the escape sequence at the start of buf, or None if it's not complete."""
        if len(buf) < 2:
            return None
        if buf[1] == 0x5B:                          # CSI: ESC [ parameters final-byte
            for i in range(2, len(buf)):
                if 0x40 <= buf[i] <= 0x7E:
                    return i + 1
            return None
        if buf[1] == 0x4F:                          # SS3: ESC O x
            return 3 if len(buf) >= 3 else None
        return 2                                     # ESC and one more character

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
            if self.buf[0] == 0x1B:
                # An escape sequence we don't know (an arrow key, say): drop the whole thing,
                # so its "[" and "C" are not typed as letters, and remember it.
                n = self._escape_length(self.buf)
                if n is None:
                    if not final:
                        break                        # the rest may still arrive
                    n = len(self.buf)                # a pause: it was cut short
                self.unknown.append(self.buf[:n])
                self.buf = self.buf[n:]
                continue
            b = self.buf[0]
            self.buf = self.buf[1:]
            if 32 <= b < 127:
                out.append(chr(b))
            # other control bytes are dropped
        return out


KEY_NAMES = [INDICE, SEGUENTE, PRECEDENTE, ANNUL, CORREZIONE, GUIDA, RIPETIZ, INVIO,
             DESTRA, SINISTRA]


def load_keymap(path: str | Path) -> dict[str, list[bytes]]:
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text())
    return {k: [bytes.fromhex(h) for h in v] for k, v in raw.items()}


def save_keymap(path: str | Path, keymap: dict[str, list[bytes]]) -> None:
    Path(path).write_text(json.dumps(
        {k: [s.hex() for s in v] for k, v in keymap.items()}, indent=2))


def chunks(data: bytes, size: int) -> list[bytes]:
    """Cut data into pieces of about `size` bytes, never inside an escape sequence.

    A drawing can be stopped between two pieces; stopping halfway through a cursor
    jump would leave the terminal waiting for the rest of it. Joined together the
    pieces are exactly `data`.
    """
    out, start, i, n = [], 0, 0, len(data)
    while i < n:
        if data[i] == 0x1B:                          # skip a whole escape sequence
            j = i + 2
            if i + 1 < n and data[i + 1] == 0x5B:     # CSI: ESC [ parameters final-byte
                while j < n and not 0x40 <= data[j] <= 0x7E:
                    j += 1
                j += 1
            i = min(j, n)
        else:
            i += 1
        if i - start >= size:
            out.append(data[start:i])
            start = i
    if start < n:
        out.append(data[start:])
    return out


class KeyWatcher:
    """Listens to the port while a screen is being drawn.

    interrupted() is what draw() asks between two pieces: it reads whatever has arrived,
    decodes it and says True as soon as a command we know is waiting. Those commands are
    kept in `pending` for the main loop; bytes we don't understand (noise, keys nobody has
    taught us) never interrupt anything.
    """

    def __init__(self, port, decoder: "KeyDecoder", log=None):
        self.port, self.decoder, self.log = port, decoder, log
        self.pending: list[str] = []

    def interrupted(self) -> bool:
        waiting = getattr(self.port, "in_waiting", 0)
        if waiting:
            self.pending.extend(self.decoder.feed(self.port.read(waiting)))
            if self.log:
                for seq in self.decoder.take_unknown():
                    self.log(seq)
        return bool(self.pending)

    def take(self) -> list[str]:
        """The commands that arrived during a drawing (and forget them)."""
        out, self.pending = self.pending, []
        return out


class SerialTerminal:
    """Thin wrapper over a pyserial port (or anything with read/write)."""

    PIECE_SECONDS = 0.2            # how long one piece of a drawing takes to send

    def __init__(self, port, profile: str = "plain", margin: int = 0,
                 baud: int = 1200):
        self.port = port
        self.profile = profile
        self.margin = margin
        self.baud = baud
        self.prev: list[str] | None = None

    def draw(self, rows: list[str], full: bool = False, abort=None) -> float:
        """Send the screen. With abort, a function that says whether to stop, the bytes go
        out in short pieces (about 0.2 s each) and abort() is asked between them: if it says
        yes the rest is not sent. What is on the terminal is then half a screen, so the
        next draw is a full redraw. Returns the transmission time of what was sent."""
        data = encode_screen(rows, self.prev, self.profile, self.margin, full)
        if abort is None:
            self.port.write(data)
            self.prev = list(rows)
            return estimate_seconds(data, self.baud)
        size = max(8, int(self.baud / 10 * self.PIECE_SECONDS))
        sent = 0
        for piece in chunks(data, size):
            if abort():
                self.prev = None
                return estimate_seconds(data[:sent], self.baud)
            self.port.write(piece)
            drain = getattr(self.port, "flush", None)
            if drain:
                drain()                                # wait until it has really gone out
            sent += len(piece)
        self.prev = list(rows)
        return estimate_seconds(data, self.baud)

    def try_draw(self, rows: list[str], full: bool = False, abort=None) -> float:
        """draw() that never raises: a stuck or failing port must not stop the totem.

        After a failure the terminal's screen is in an unknown state, so the
        next draw is a full redraw.
        """
        try:
            return self.draw(rows, full, abort)
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
