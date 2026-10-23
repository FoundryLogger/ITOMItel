"""Screensaver: the whole screen filled with "#", the ITOMI logo carved out at the centre.

"Negative" means the logo is the empty part: where the logo has ink the screen is
blank, and everything else, all the way to the edges, is filled. The logo is centred.

The cycle is a list of (screen, pause) pairs: blank, then the filled screen appearing
one row at a time from the top, a long hold, and the screen emptying from the bottom.
When the screen is empty the building starts again at once, with no pause in between.
Row by row suits a 1200 baud line: each row is one write, so the construction is
visible without any extra delay.

Screensaver is the small state machine that decides, from the clock alone,
which frame to draw next, so the same logic can be tested without hardware.
"""
from __future__ import annotations

from . import logo

HEIGHT = 24


def logo_origin(width: int = 80) -> tuple[int, int]:
    """(top row, left column) of the logo on the screen."""
    rows = len(logo.GRID)
    cols = len(logo.lines(compact=width < 80)[0])
    return (HEIGHT - rows) // 2, (width - cols) // 2


def negative_screen(width: int = 80, ink: str = "#") -> list[str]:
    """The full screen: ink everywhere, the logo carved out of it in the middle.
    On 40 columns the compact logo (40 wide) is used, so it spans the whole width."""
    art = logo.lines(compact=width < 80, ink="#")
    top, left = logo_origin(width)
    rows = [ink * width for _ in range(HEIGHT)]
    for i, line in enumerate(art):
        carved = "".join(" " if ch == "#" else ink for ch in line)
        rows[top + i] = ink * left + carved + ink * (width - left - len(line))
    return rows


def cycle(width: int = 80, ink: str = "#", step: float = 0.2, hold: float = 30.0,
          gap: float = 0.0) -> list[tuple[list[str], float]]:
    """(screen, seconds to wait before the next frame) for one full cycle.
    The first frame is the blank screen that starts the screensaver; when it loops,
    Screensaver skips it, so the last (blank) frame is followed by the first row."""
    full = negative_screen(width, ink)
    blank = " " * width

    def screen(built: int) -> list[str]:
        return full[:built] + [blank] * (HEIGHT - built)

    frames = [(screen(0), 1.0)]
    frames += [(screen(k), step) for k in range(1, HEIGHT + 1)]
    frames[-1] = (frames[-1][0], hold)
    frames += [(screen(k), step / 2) for k in range(HEIGHT - 1, -1, -1)]
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
        # After the last frame go back to frame 1: frame 0 is only the blank start,
        # and the screen is already blank, so the next round begins with no pause.
        self._i = self._i + 1 if self._i + 1 < len(self.frames) else 1
        self._due = now + pause
        return rows

    def wake(self) -> bool:
        """Stop it. True if it was running (the key that woke it is then not a command)."""
        was, self.active = self.active, False
        return was
