from PIL import Image, ImageDraw
import io
import os
import struct

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "DesktopApp", "Assets")

# Shield path from Website/index.html (viewBox effectively 0 0 32 32)
SHIELD_POLY = [
    (16.0, 2.5),
    (4.5, 7.0),
    (4.5, 16.2),
]

def cubic(p0, p1, p2, p3, steps=24):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        x = (
            (1 - t) ** 3 * p0[0]
            + 3 * (1 - t) ** 2 * t * p1[0]
            + 3 * (1 - t) * t ** 2 * p2[0]
            + t ** 3 * p3[0]
        )
        y = (
            (1 - t) ** 3 * p0[1]
            + 3 * (1 - t) ** 2 * t * p1[1]
            + 3 * (1 - t) * t ** 2 * p2[1]
            + t ** 3 * p3[1]
        )
        pts.append((x, y))
    return pts

# Bezier bottom-left to bottom-center
SHIELD_POLY.extend(cubic((4.5, 16.2), (4.5, 21.9), (9.1, 26.9), (16.0, 29.2)))
# Bezier bottom-center to bottom-right
SHIELD_POLY.extend(cubic((16.0, 29.2), (22.9, 26.9), (27.5, 21.9), (27.5, 16.2)))
SHIELD_POLY.append((27.5, 7.0))

# Check mark path from MainWindow.xaml nav rail
CHECK_POINTS = [(8.9, 13.3), (11.8, 16.2), (17.6, 9.9)]

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SUPERSAMPLE = 4


def scale_points(pts, scale):
    return [(x * scale, y * scale) for x, y in pts]


def build_icon(size, fill_color):
    ss = size * SUPERSAMPLE
    scale = ss / 32.0
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    poly = scale_points(SHIELD_POLY, scale)
    draw.polygon(poly, fill=fill_color)

    check = scale_points(CHECK_POINTS, scale)
    stroke = max(1, int(2.5 * scale))
    draw.line(check, fill="white", width=stroke, joint="curve")

    # Downsample with antialiasing
    return img.resize((size, size), Image.Resampling.LANCZOS)


def save_ico(path, frames):
    # Build a multi-resolution Windows icon with PNG-encoded frames (Vista+).
    pngs = []
    for f in frames:
        buf = io.BytesIO()
        f.save(buf, format="PNG")
        pngs.append(buf.getvalue())

    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    data = b""
    offset = 6 + 16 * count
    for img, png in zip(frames, pngs):
        w = img.width if img.width < 256 else 0
        h = img.height if img.height < 256 else 0
        entries += struct.pack(
            "<BBBBHHII",
            w, h, 0, 0, 1, 32, len(png), offset
        )
        data += png
        offset += len(png)

    with open(path, "wb") as f:
        f.write(header + entries + data)


def generate(filename, fill_color):
    frames = [build_icon(s, fill_color) for s in SIZES]
    out_path = os.path.join(OUT_DIR, filename)
    save_ico(out_path, frames)
    sizes = [(f.width, f.height) for f in frames]
    print(f"Wrote {out_path} with sizes {sizes}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    generate("FlowShield.ico", "#0c6b5c")
    generate("FlowShieldRunning.ico", "#3aa892")
