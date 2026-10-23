"""Does the terminal talk faster than 1200 baud? A test to run on the real HCS 80/08.

The terminal's own speed is not something the Pi can read: it has to be tried. Two ways:

1. Raw: just send at 2400, 4800, 9600. If the terminal listens at that speed on its
   own the text is readable; if it stays at 1200 the screen shows garbage.
2. Command: Minitel-family terminals can be told to change speed with the PRO command
   ESC : k <code> (0x76 = 4800, 0x7F = 9600, 0x64 = 1200). The Pi sends it at 1200,
   changes its own speed and sends the text; at the end it sends the command that
   takes the terminal back to 1200.

Every step leaves its label on screen and says what speed it is; compare what you read.
A terminal that really switched and was not switched back (the test was cut short)
goes back to 1200 when it is turned off and on again.

    python3 -m totem baudtest --port /dev/serial0
"""
from __future__ import annotations

import time

CLEAR = b"\x1b[2J\x1b[H"
RATES = {1200: 0x64, 4800: 0x76, 9600: 0x7F}          # PRO speed codes (Teletel)


def pro(baud: int) -> bytes:
    """The command that tells the terminal to change its speed to `baud`."""
    return b"\x1b:k" + bytes([RATES[baud]])


# (label, speed the text is sent at, speed command to send first at 1200 or None)
STEPS = [
    ("1 di 6: 1200 baud, riferimento", 1200, None),
    ("2 di 6: 2400 baud, senza comando", 2400, None),
    ("3 di 6: 4800 baud, senza comando", 4800, None),
    ("4 di 6: 9600 baud, senza comando", 9600, None),
    ("5 di 6: 4800 baud, con il comando di cambio velocita'", 4800, 4800),
    ("6 di 6: 9600 baud, con il comando di cambio velocita'", 9600, 9600),
]


def message(label: str, baud: int) -> bytes:
    lines = [f"PROVA VELOCITA'  {label}",
             "",
             f"Se leggi questa riga, il terminale ascolta a {baud} baud.",
             "ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789",
             "abcdefghijklmnopqrstuvwxyz .,;:-+=()/",
             "",
             "Una riga lunga serve a vedere se si perde qualcosa lungo la strada: " + "0123456789" * 3]
    return CLEAR + "\r\n".join(lines).encode("ascii")


def _send(port, data: bytes) -> None:
    port.write(data)
    port.flush()


def run(port, hold: float = 12.0, only: int | None = None) -> None:
    """Play the steps (all, or just step number `only`), each left on screen for `hold`
    seconds, and always finish with the port and the terminal back at 1200 baud."""
    switched = False
    try:
        for number, (label, baud, command) in enumerate(STEPS, 1):
            if only and number != only:
                continue
            port.baudrate = 1200
            if command:
                _send(port, pro(command))
                switched = True
                time.sleep(0.6)                    # let the terminal change speed
            port.baudrate = baud
            _send(port, message(label, baud))
            time.sleep(hold)
            if command:                            # take the terminal back to 1200
                _send(port, pro(1200))
                time.sleep(0.6)
                switched = False
    finally:
        if switched:                               # cut short while the terminal was switched
            try:
                _send(port, pro(1200))
                time.sleep(0.6)
            except Exception:
                pass
        port.baudrate = 1200
        _send(port, CLEAR)
