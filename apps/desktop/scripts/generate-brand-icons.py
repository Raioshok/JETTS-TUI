"""Render the code-native Jetts-TUI mark for desktop packaging assets.

Run with a Python environment containing Pillow. The geometry mirrors
docs/assets/img/jetts-tui-mark.svg and does not depend on upstream art.
"""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[3]
DESKTOP = ROOT / "apps" / "desktop"
SIZE = 1024
SCALE = 4
DARK = "#111827"
TEAL = "#60e4ca"


def diamond(cx: int, cy: int, radius: int) -> list[tuple[int, int]]:
    return [(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)]


def icon() -> Image.Image:
    size = SIZE * SCALE
    center = size // 2
    draw_size = lambda value: round(value * size / 64)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=draw_size(15), fill=DARK)
    draw.polygon(diamond(center, center, draw_size(24)), fill=TEAL)
    draw.polygon(diamond(center, center, draw_size(19)), fill=DARK)
    draw.polygon(diamond(center, center, draw_size(14)), fill=TEAL)
    draw.polygon(diamond(center, center, draw_size(7)), fill=DARK)
    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    image = icon()
    assets = DESKTOP / "assets"
    image.save(assets / "icon.png")
    image.save(assets / "icon.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    image.save(assets / "icon.icns")
    image.resize((180, 180), Image.Resampling.LANCZOS).save(DESKTOP / "public" / "apple-touch-icon.png")
    image.save(ROOT / "web" / "public" / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])


if __name__ == "__main__":
    main()
