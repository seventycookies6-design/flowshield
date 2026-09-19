import ctypes, os
from PIL import Image
import winreg

# A plain, dark desktop: the recording is about the app, and the stock
# Windows photo behind it is just noise.
path = r"C:\FlowShield-Lab\desk.png"
Image.new("RGB", (1920, 1080), (18, 17, 16)).save(path)
ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)   # SPI_SETDESKWALLPAPER

key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                     r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
                     0, winreg.KEY_SET_VALUE)
winreg.SetValueEx(key, "HideIcons", 0, winreg.REG_DWORD, 1)
winreg.CloseKey(key)
os.system("taskkill /f /im explorer.exe >nul 2>&1")
os.system("start explorer.exe")
print("desktop cleaned", flush=True)
