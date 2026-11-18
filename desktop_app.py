"""
Autocorrect desktop app: tray icon + global hotkeys. This is what the installers ship.

    desktop_app.py               run the app (tray icon, hotkeys)
    desktop_app.py --selftest    check that everything loads, then exit (used by CI)

Settings open as a page in the user's browser (see settings_web.py).
"""

import sys
import threading


def make_icon_image(size: int = 64):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.rounded_rectangle([2 * s, 2 * s, 62 * s, 62 * s], radius=14 * s, fill=(79, 70, 229, 255))
    # "A"
    d.polygon([(32 * s, 12 * s), (46 * s, 48 * s), (40 * s, 48 * s), (37 * s, 40 * s),
               (27 * s, 40 * s), (24 * s, 48 * s), (18 * s, 48 * s)], fill="white")
    d.polygon([(29 * s, 34 * s), (35 * s, 34 * s), (32 * s, 25 * s)], fill=(79, 70, 229, 255))
    # check mark
    d.line([(36 * s, 52 * s), (41 * s, 57 * s), (54 * s, 44 * s)], fill=(165, 243, 252, 255),
           width=max(2, int(4 * s)), joint="curve")
    return img


def run_tray():
    import pystray

    import autocorrect as engine
    from settings_web import SettingsServer

    settings = SettingsServer()
    icon = pystray.Icon("Autocorrect", make_icon_image(), "Autocorrect")

    def tray_notify(message: str):
        if engine.IS_MAC:
            raise RuntimeError("use the system notifier")  # pystray can't notify on macOS
        icon.notify(message, "Autocorrect")

    engine.notify_hook = tray_notify

    def hotkey_lines():
        engine.reload_config_if_changed()
        heb = {"translate to English": "תרגום לאנגלית", "translate to Hebrew": "תרגום לעברית",
               "fix spelling & grammar": "תיקון שגיאות"}
        return [pystray.MenuItem(f"{label}  –  {heb.get(desc, desc)}", None, enabled=False)
                for label, desc in engine.describe_hotkeys()]

    def quit_app(icon_, _item):
        settings.stop()
        icon_.stop()

    icon.menu = pystray.Menu(
        lambda: [
            *hotkey_lines(),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("הגדרות", lambda *_: settings.open(), default=True),
            pystray.MenuItem("יציאה", quit_app),
        ]
    )

    def on_ready(icon_):
        icon_.visible = True
        try:
            engine.start_hotkeys()
        except Exception as e:  # noqa: BLE001
            engine.notify(f"Could not start the keyboard shortcuts: {e}")
        if not engine.has_credentials():
            settings.open()  # first run: ask for the access code / key
        else:
            threading.Timer(1.0, engine.notify, ["Autocorrect פועל. סמנו טקסט ולחצו על הקיצור."]).start()

    icon.run(setup=on_ready)


def selftest():
    import json
    import urllib.request

    import pynput  # noqa: F401
    import pystray  # noqa: F401

    import autocorrect as engine
    from autocorrect_core import Action
    from settings_web import SettingsServer

    assert engine.describe_hotkeys(), "no hotkeys"
    assert Action.translate("English").task()
    make_icon_image()
    server = SettingsServer()
    local = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
    page = local.open(server.url, timeout=5).read().decode("utf-8")
    assert "Autocorrect" in page, "settings page missing"
    state = json.load(local.open(server.url + "api/state", timeout=5))
    assert state["hotkeys"], "settings api broken"
    server.stop()
    print("selftest ok:", engine.CONFIG_PATH)


def main():
    if "--selftest" in sys.argv:
        # The installed app has no console (and on Windows an uncaught error would open a
        # dialog box), so report the result through a file and the exit code.
        import os
        import traceback

        out = os.environ.get("AUTOCORRECT_SELFTEST_OUT")
        try:
            selftest()
            result, code = "ok", 0
        except BaseException:  # noqa: BLE001
            result, code = traceback.format_exc(), 1
        if out:
            with open(out, "w", encoding="utf-8") as f:
                f.write(result)
        sys.exit(code)
    else:
        run_tray()


if __name__ == "__main__":
    main()
