# PyInstaller build spec:  pyinstaller packaging/autocorrect.spec  (run from the repository root)
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = Path(SPECPATH)

if sys.platform == "win32":
    platform_modules = ["pynput.keyboard._win32", "pynput.mouse._win32", "pystray._win32"]
elif sys.platform == "darwin":
    platform_modules = ["pynput.keyboard._darwin", "pynput.mouse._darwin", "pystray._darwin"]
else:
    platform_modules = ["pynput.keyboard._xorg", "pynput.mouse._xorg", "pystray._xorg"]

datas = [(str(ROOT / "settings.html"), ".")]
if (PKG / "defaults.json").exists():  # server address baked in at build time
    datas.append((str(PKG / "defaults.json"), "."))

a = Analysis(
    [str(ROOT / "desktop_app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=platform_modules + ["autocorrect", "settings_web", "anthropic"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

icon = str(PKG / ("icon.ico" if sys.platform == "win32" else "icon.icns"))
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Autocorrect",
    console=False,  # no black console window
    icon=icon if Path(icon).exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Autocorrect")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Autocorrect.app",
        icon=icon,
        bundle_identifier="com.autocorrect.desktop",
        info_plist={
            "CFBundleDisplayName": "Autocorrect",
            "CFBundleShortVersionString": "1.0.0",
            "LSUIElement": True,  # menu-bar app, no Dock icon
            "NSAppleEventsUsageDescription": "Autocorrect pastes the translated text into the app you are using.",
        },
    )
