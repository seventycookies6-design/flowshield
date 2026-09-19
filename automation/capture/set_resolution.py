import ctypes, ctypes.wintypes as w, sys
sys.path.insert(0, r"C:\FlowShield-Lab\downloads")
from res_probe import DEVMODE  # reuse the struct

u = ctypes.windll.user32
dm, i, found = DEVMODE(), 0, None
dm.dmSize = ctypes.sizeof(DEVMODE)
while u.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
    if (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmBitsPerPel) == (1920, 1080, 32):
        found = DEVMODE.from_buffer_copy(dm)
        break
    i += 1

if not found:
    print("1920x1080 not offered", flush=True)
else:
    DM_PELSWIDTH, DM_PELSHEIGHT, DM_BITSPERPEL = 0x80000, 0x100000, 0x40000
    CDS_UPDATEREGISTRY = 0x01
    found.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_BITSPERPEL
    rc = u.ChangeDisplaySettingsExW(None, ctypes.byref(found), None, CDS_UPDATEREGISTRY, None)
    print("ChangeDisplaySettingsEx returned", rc, "(0 = success)", flush=True)

print("now:", u.GetSystemMetrics(0), "x", u.GetSystemMetrics(1), flush=True)
