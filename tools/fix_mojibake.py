"""
Repair CP1252 round-trip mojibake in text files and normalise the star glyph.

Kept in the repo because editing UTF-8 XAML with PowerShell's Get-Content /
Set-Content on Windows PowerShell 5.1 silently corrupts non-ASCII characters —
this undoes that damage if it ever happens again.

    python tools/fix_mojibake.py DesktopApp/MainWindow.xaml
"""

import re
import sys
from pathlib import Path

SEQ = re.compile(r"[Â-ô][-¿]{1,3}")


def _fix(match: re.Match) -> str:
    # cp1252 first (the usual culprit), then latin-1 — .NET maps cp1252's
    # undefined slots (0x81, 0x8d, 0x90, 0x9d) to the matching control chars,
    # which cp1252 itself refuses to encode back.
    for codec in ("cp1252", "latin-1"):
        try:
            return match.group(0).encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return match.group(0)


def repair(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    fixed = SEQ.sub(_fix, text)
    fixed = fixed.replace("⭐", "★")  # emoji star -> text star

    leftovers = sorted({c for c in fixed if 0x80 <= ord(c) <= 0xBF})
    if leftovers:
        print(f"  WARNING {path.name}: leftover bytes {leftovers}")

    if fixed != text:
        path.write_text(fixed, encoding="utf-8")
        print(f"repaired: {path}")
        return True
    print(f"clean:    {path}")
    return False


if __name__ == "__main__":
    targets = sys.argv[1:]
    if not targets:
        print(__doc__)
        raise SystemExit(2)
    for arg in targets:
        repair(Path(arg))
