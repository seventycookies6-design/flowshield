"""Generate FlowShield's multi-resolution Windows icons."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "DesktopApp" / "Assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SCALE = 4


def points(values):
    return [(round(x * SCALE), round(y * SCALE)) for x, y in values]


def render(*, running: bool) -> Image.Image:
    size = 256 * SCALE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    background = "#3AA892" if running else "#121110"
    shield = "#F2F0EB" if running else "#3AA892"
    check = "#0B1F1B" if running else "#F2F0EB"

    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=48 * SCALE, fill=background)
    outline = [(128, 20), (36, 56), (36, 129.6)]
    for index in range(1, 25):
        t = index / 24
        mt = 1 - t
        outline.append((
            mt**3 * 36 + 3 * mt**2 * t * 36 + 3 * mt * t**2 * 73.6 + t**3 * 128,
            mt**3 * 129.6 + 3 * mt**2 * t * 182.4 + 3 * mt * t**2 * 222.4 + t**3 * 236,
        ))
    for index in range(1, 25):
        t = index / 24
        mt = 1 - t
        outline.append((
            mt**3 * 128 + 3 * mt**2 * t * 182.4 + 3 * mt * t**2 * 220 + t**3 * 220,
            mt**3 * 236 + 3 * mt**2 * t * 222.4 + 3 * mt * t**2 * 182.4 + t**3 * 129.6,
        ))
    outline.extend([(220, 56), (128, 20)])
    draw.polygon(points(outline), fill=shield)
    draw.line(points([(84, 132), (113, 161), (172, 98)]), fill=check, width=18 * SCALE, joint="curve")
    return image


def save_icon(name: str, *, running: bool) -> None:
    target = ASSETS / name
    render(running=running).save(target, format="ICO", sizes=[(size, size) for size in SIZES])
    print(f"wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    save_icon("FlowShield.ico", running=False)
    save_icon("FlowShield.Running.ico", running=True)
