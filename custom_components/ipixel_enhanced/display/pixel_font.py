"""Bitmap pixel font for 32×32 LED matrix — 5×7 px per glyph, pixel-perfect."""
from __future__ import annotations
from PIL import Image

# Each glyph = 7 rows × 5 columns, '#'=lit '.'=dark
# Designed specifically for LED matrix: clean digits, no serifs on 1/7
_GLYPHS_RAW: dict[str, list[str]] = {
    ' ': ['.....',  '.....',  '.....',  '.....',  '.....',  '.....',  '.....'],
    '0': ['.###.',  '#...#',  '#...#',  '#...#',  '#...#',  '#...#',  '.###.'],
    '1': ['..#..',  '.##..',  '..#..',  '..#..',  '..#..',  '..#..',  '..#..'],
    '2': ['.###.',  '#...#',  '....#',  '..##.',  '.#...',  '#....',  '#####'],
    '3': ['.###.',  '#...#',  '....#',  '..##.',  '....#',  '#...#',  '.###.'],
    '4': ['...#.',  '..##.',  '.#.#.',  '#..#.',  '#####',  '...#.',  '...#.'],
    '5': ['#####',  '#....',  '####.',  '....#',  '....#',  '#...#',  '.###.'],
    '6': ['..##.',  '.#...',  '#....',  '####.',  '#...#',  '#...#',  '.###.'],
    '7': ['#####',  '....#',  '...#.',  '..#..',  '.#...',  '.#...',  '.#...'],
    '8': ['.###.',  '#...#',  '#...#',  '.###.',  '#...#',  '#...#',  '.###.'],
    '9': ['.###.',  '#...#',  '#...#',  '.####',  '....#',  '...#.',  '.##..'],
    ':': ['.....',  '.##..',  '.##..',  '.....',  '.##..',  '.##..',  '.....'],
    '%': ['##...',  '##..#',  '...#.',  '..#..',  '.#...',  '#..##',  '...##'],
    'A': ['..#..',  '.#.#.',  '#...#',  '#####',  '#...#',  '#...#',  '#...#'],
    'B': ['####.',  '#...#',  '#...#',  '####.',  '#...#',  '#...#',  '####.'],
    'C': ['.###.',  '#...#',  '#....',  '#....',  '#....',  '#...#',  '.###.'],
    'H': ['#...#',  '#...#',  '#...#',  '#####',  '#...#',  '#...#',  '#...#'],
    'K': ['#...#',  '#..#.',  '#.#..',  '##...',  '#.#..',  '#..#.',  '#...#'],
    'O': ['.###.',  '#...#',  '#...#',  '#...#',  '#...#',  '#...#',  '.###.'],
    'm': ['.....',  '.....',  '.#.#.',  '##.##',  '#...#',  '#...#',  '#...#'],
}

CHAR_W = 5
CHAR_H = 7
CHAR_GAP = 1

# Pre-compile glyphs into integer bitmasks (bit4=leftmost col)
_GLYPHS: dict[str, list[int]] = {}
for _ch, _rows in _GLYPHS_RAW.items():
    _compiled = []
    for _row in _rows:
        _val = 0
        for _i, _px in enumerate(_row):
            if _px == '#':
                _val |= (1 << (CHAR_W - 1 - _i))
        _compiled.append(_val)
    _GLYPHS[_ch] = _compiled


def pixel_text_width(text: str) -> int:
    n = sum(1 for ch in text if ch in _GLYPHS)
    return max(0, n * CHAR_W + max(0, n - 1) * CHAR_GAP)


def draw_pixel_text(
    canvas: Image.Image,
    x: int,
    y: int,
    text: str,
    color: tuple[int, int, int],
) -> int:
    """Draw text pixel by pixel. Returns next x cursor (after last char + gap)."""
    px_data = canvas.load()
    w, h = canvas.size
    cx = x
    for ch in text:
        glyph = _GLYPHS.get(ch)
        if glyph is None:
            cx += CHAR_W + CHAR_GAP
            continue
        for row_i, row_bits in enumerate(glyph):
            py = y + row_i
            if py < 0 or py >= h:
                continue
            for col_i in range(CHAR_W):
                if row_bits & (1 << (CHAR_W - 1 - col_i)):
                    px = cx + col_i
                    if 0 <= px < w:
                        px_data[px, py] = color
        cx += CHAR_W + CHAR_GAP
    return cx
