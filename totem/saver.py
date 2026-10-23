"""Screensaver: the ITOMI logo, in negative, built row by row.

"Negative" means the logo is carved out of a solid field: where the logo has
ink the screen is blank, everywhere else (and in a one-module margin around
the logo) it is filled. The field is centred on the screen.

The cycle is a list of (screen, pause) pairs: blank, then the field appearing
one row at a time from the top, a long hold, the field disappearing from the
bottom, and a pause on a blank screen. Row by row suits a 1200 baud line: each
row is a short write, so the construction is visible without any extra delay.

Screensaver is the small state machine that decides, from the clock alone,
which frame to draw next, so the same logic can be tested without hardware.
"""
from __future__ import annotations

from . import logo

HEIGHT = 24


def negative_field(width: int = 80, ink: str = "#") -> list[str]:
    """The filled field with the logo carved out. 46 x 14 on 80 columns
    (a margin of one module around the logo), 40 x 12 on 40 columns."""
    grid, cols = logo.GRID, logo.COLS
    wide = width >= 80
    margin = 1 if wide else 0
    cell = lambda c: 2 if (wide or 0 < c < cols - 1) else 1     # compact sides on 40 columns
    out = []
    solid = ink * (2 * (cols + 2 * margin) if wide else 40)
    for _ in range(margin):
        out.append(solid)
    for row in grid:
        line = ink * 2 * margin
        for c, module in enumerate(row):
            line += (" " if module == "#" else ink) * cell(c)
        line += ink * 2 * margin
        out.append(line)
    for _ in range(margin):
        out.append(solid)
    return out


def cycle(width: int = 80, ink: str = "#", step: float = 0.5, hold: float = 30.0,
          gap: float = 20.0) -> list[tuple[list[str], float]]:
    """(screen, seconds to wait before the next frame) for one full cycle."""
    field = negative_field(width, ink)
    top = (HEIGHT - len(field)) // 2
    left = (width - len(field[0])) // 2

    def screen(built: int) -> list[str]:
        rows = [" " * width] * HEIGHT
        for i in range(built):
            rows[top + i] = (" " * left + field[i]).ljust(width)
        return rows

    n = len(field)
    frames = [(screen(0), 1.0)]
    frames += [(screen(k), step) for k in range(1, n + 1)]
    frames[-1] = (frames[-1][0], hold)
    frames += [(screen(k), step / 2) for k in range(n - 1, -1, -1)]
    frames[-1] = (frames[-1][0], gap)
    return frames


class Screensaver:
    """Starts after `after` seconds without activity and plays cycle() in a loop
    until wake() is called. after <= 0 disables it."""

    def __init__(self, width: int = 80, after: float = 300.0, ink: str = "#", **timing):
        self.width, self.after, self.ink, self.timing = width, after, ink, timing
        self.frames = cycle(width, ink, **timing) if after > 0 else []
        self.active = False
        self._i = 0
        self._due = 0.0

    def configure(self, after: float, ink: str, hold: float) -> None:
        """Apply new settings while the totem runs (Impostazioni screen)."""
        changed = ink != self.ink or hold != self.timing.get("hold", 30.0) or (after > 0 and not self.frames)
        self.after, self.ink = after, ink
        self.timing = {**self.timing, "hold": hold}
        if after <= 0:
            self.frames, self.active = [], False
        elif changed:
            self.frames = cycle(self.width, ink, **self.timing)
            self._i = 0

    def tick(self, now: float, last_activity: float) -> list[str] | None:
        """The next screen to draw at time `now`, or None if nothing is due."""
        if self.after <= 0:
            return None
        if not self.active:
            if now - last_activity < self.after:
                return None
            self.active, self._i, self._due = True, 0, now
        if now < self._due:
            return None
        rows, pause = self.frames[self._i]
        self._i = (self._i + 1) % len(self.frames)
        self._due = now + pause
        return rows

    def wake(self) -> bool:
        """Stop it. True if it was running (the key that woke it is then not a command)."""
        was, self.active = self.active, False
        return was
