"""Generate Basalt's multi-resolution Windows icons from the Causeway logo.

The shapes and colours are read from the approved SVGs in `design/brand/`
(the source of truth for the logo), so the icons are never redrawn by hand.
The file names keep the old internal name: installs, the .csproj and
`MainWindow.xaml.cs` `LoadIcon` depend on them.
"""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "DesktopApp" / "Assets"
BRAND = ROOT / "design" / "brand"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SVG_NS = "{http://www.w3.org/2000/svg}"
CANVAS = 1024  # supersampled, then reduced to each icon size

# icon file stem -> Causeway tile. Running is the Firm tile (design/brand/README.md).
ICONS = {
    "FlowShield": "basalt-icon.svg",
    "FlowShield.Running": "basalt-icon-firm.svg",
}


def render(svg: Path) -> Image.Image:
    root = ET.parse(svg).getroot()
    _, _, width, _ = (float(v) for v in root.get("viewBox").split())
    k = CANVAS / width
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    tile = root.find(f"{SVG_NS}rect")
    radius = float(tile.get("rx")) * k
    draw.rounded_rectangle((0, 0, CANVAS - 1, CANVAS - 1), radius=radius, fill=tile.get("fill"))

    for group in root.iter(f"{SVG_NS}g"):
        joint = group.get("stroke")
        joint_width = max(1, round(float(group.get("stroke-width")) * k))
        for polygon in group.iter(f"{SVG_NS}polygon"):
            pts = [tuple(float(v) * k for v in pair.split(",")) for pair in polygon.get("points").split()]
            draw.polygon(pts, fill=polygon.get("fill"), outline=joint, width=joint_width)
    return image


def save_icon(stem: str, source: str) -> None:
    svg = BRAND / source
    target = ASSETS / f"{stem}.ico"
    render(svg).save(target, format="ICO", sizes=[(size, size) for size in SIZES])
    shutil.copyfile(svg, ASSETS / f"{stem}.svg")
    print(f"wrote {target.relative_to(ROOT)} and {stem}.svg from design/brand/{source}")


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    for stem, source in ICONS.items():
        save_icon(stem, source)
