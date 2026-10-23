"""Does the terminal scroll text by itself? A test to run on the real HCS 80/08.

Scrolling a long text one line at a time would change every row, and redrawing 18
rows at 1200 baud takes more than ten seconds. If the terminal can delete and insert
lines on its own, scrolling needs only the one new line (about a second).

Each test draws a screen of numbered rows (row 3 says "03", row 4 "04", ...), applies
one scroll operation at row 5 and leaves the result on screen, with a caption in row 1
and what you should see in row 2. Compare: if the numbers are where row 2 says, that
operation works.

    python3 -m totem scrolltest --port /dev/serial0

The totem must not be reading the port meanwhile (deploy/test-scroll.sh pauses it).
"""
from __future__ import annotations

import time

CLEAR = b"\x1b[2J\x1b[H"

# name, what it does, bytes sent, and what must be on screen afterwards: row -> text
# at the start of that row ("" = empty row). The numbers come from the rows drawn below.
TESTS = [
    ("A", "ESC [ M : cancella la riga 5 (DL)",
     b"\x1b[5;1H\x1b[M",
     {5: "06", 23: "24", 24: ""}),
    ("B", "ESC [ L : inserisce una riga vuota alla riga 5 (IL)",
     b"\x1b[5;1H\x1b[L",
     {5: "", 6: "05", 24: "23"}),
    ("C", "ESC [ 5;20 r + ESC [ M : scorrimento solo tra le righe 5 e 20",
     b"\x1b[5;20r\x1b[5;1H\x1b[M\x1b[r",
     {5: "06", 19: "20", 20: "", 21: "21", 24: "24"}),
    ("D", "ESC [ M alla riga 5, poi ESC [ L alla riga 20 (la base resta ferma)",
     b"\x1b[5;1H\x1b[M\x1b[20;1H\x1b[L",
     {5: "06", 19: "20", 20: "", 21: "21", 24: "24"}),
]


def setup(name: str, caption: str, expected: dict[int, str]) -> bytes:
    """A fresh screen: caption (row 1), what to expect (row 2), numbered rows 3-24."""
    seen = ", ".join(f"riga {r} = {v or 'vuota'}" for r, v in expected.items())
    rows = [f"TEST {name}: {caption}", f"ATTESO: {seen}"]
    rows += [f"{n:02d} riga di prova" for n in range(3, 25)]
    return CLEAR + "\r\n".join(rows).encode("ascii")


def run(port, pause: float = 20.0, only: str | None = None) -> None:
    """Play the tests one after the other, each left on screen for `pause` seconds."""
    for name, caption, ops, expected in TESTS:
        if only and name != only.upper():
            continue
        port.write(setup(name, caption, expected))
        port.flush()
        time.sleep(1.0)
        port.write(ops)
        port.flush()
        time.sleep(pause)
    port.write(CLEAR)
    port.flush()
