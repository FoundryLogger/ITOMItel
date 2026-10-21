"""The ITOMI logo as plain ASCII.

The logo is a grid of 21 x 12 square modules ('#' = dark). Each module is
drawn two characters wide, because a character cell is about twice as tall
as it is wide. That makes 42 columns: fine on 80, two too many for 40. In
compact mode the two vertical lines of the outer frame (first and last
module) get one character each: 1 + 19 * 2 + 1 = 40.
"""
GRID = [
    "....#................",
    "###.##.##############",
    "#...#...............#",
    "#.#.#.#.###.#####.#.#",
    "#...#.#...#.#.#.#...#",
    "#.#.#.#.#.#.#.#.#.#.#",
    "#.#.#.#...#.#.#.#.#.#",
    "#.#.#.###.#.#.#.#.#.#",
    "#.#.........#.#.#.#.#",
    "#.###########.#.###.#",
    "#...................#",
    "#####################",
]

COLS = len(GRID[0])


def lines(compact: bool = True, ink: str = "#") -> list[str]:
    """The logo: 12 rows, 40 columns if compact, 42 otherwise."""
    out = []
    for row in GRID:
        line = ""
        for c, module in enumerate(row):
            width = 1 if compact and c in (0, COLS - 1) else 2
            line += (ink if module == "#" else " ") * width
        out.append(line)
    return out
