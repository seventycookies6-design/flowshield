"""
Repair CP1252 round-trip mojibake in text files and normalise the star glyph.

Kept in the repo because editing UTF-8 files with Windows PowerShell 5.1's
Get-Content / Set-Content silently corrupts non-ASCII characters: the bytes are
read as the ANSI code page, so an em dash (UTF-8 E2 80 94) comes back as the
three characters "â€”" and gets written out as UTF-8 again.

    python tools/fix_mojibake.py path/to/file.py [more files...]

A naive fix that only looks for bytes 0x80-0xBF misses most real cases, because
cp1252 maps 0x80-0x9F to characters well outside Latin-1 (0x80 -> U+20AC EUR,
0x94 -> U+201D). The candidate set is therefore derived from cp1252 itself.

Safety: a run is only rewritten if it round-trips to valid UTF-8. Genuine
accented text fails that decode and is left untouched.
"""

import re
import sys
from pathlib import Path

# Every character a single byte 0x80-0xFF can decode to under cp1252, plus the
# C1 controls that .NET substitutes for cp1252's five undefined slots.
_SUSPECT = set()
for _b in range(0x80, 0x100):
    try:
        _SUSPECT.add(bytes([_b]).decode("cp1252"))
    except UnicodeDecodeError:
        pass
    _SUSPECT.add(chr(_b))

_RUN = re.compile(f"[{re.escape(''.join(sorted(_SUSPECT)))}]{{2,}}")


def _decode_run(run: str) -> str:
    """Turn one mojibake run back into the text it came from, or leave it be."""
    for codec in ("cp1252", "latin-1"):
        try:
            repaired = run.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        # A successful UTF-8 decode of re-encoded bytes is strong evidence this
        # really was mojibake rather than legitimate accented text.
        return repaired
    return run


def repair(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    fixed = _RUN.sub(lambda m: _decode_run(m.group(0)), text)
    fixed = fixed.replace("⭐", "★")  # emoji star -> text star

    # Set-Content -Encoding UTF8 prepends a BOM. Harmless in most places, but a
    # leading U+FEFF is a syntax error to Python's ast and to some parsers.
    if fixed.startswith("﻿"):
        fixed = fixed.lstrip("﻿")

    if fixed != text:
        path.write_text(fixed, encoding="utf-8")
        changed = sum(1 for a, b in zip(text, fixed) if a != b) or abs(len(text) - len(fixed))
        print(f"repaired: {path}  (~{changed} chars)")
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
