"""Builds the app icons (icon.ico for Windows, icon.icns for macOS) from the tray icon drawing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from desktop_app import make_icon_image  # noqa: E402

out = Path(__file__).resolve().parent
img = make_icon_image(1024)
img.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(out / "icon.icns")
img.resize((256, 256)).save(out / "icon.png")
print("icons written to", out)
