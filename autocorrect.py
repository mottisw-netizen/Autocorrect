"""
Autocorrect - select text anywhere, press a hotkey, get it translated / fixed in place.

Default hotkeys (editable in config.json):
    Ctrl+Alt+E  ->  translate selection to English
    Ctrl+Alt+H  ->  translate selection to Hebrew
    Ctrl+Alt+F  ->  fix spelling & grammar (keeps the original language)

How it works: the app copies the current selection, sends it to the AI
(your server, Claude, OpenRouter, ... - see "providers" in config.json),
then pastes the result back over the selection. Your original clipboard
content is restored afterwards.

On Ubuntu/Linux (especially Wayland) run install-ubuntu.sh instead: it registers
system keyboard shortcuts that call this script in one-shot mode, e.g.
    python autocorrect.py --once translate English
    python autocorrect.py --once fix
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pyperclip

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
from autocorrect_core import Action, ProviderError, build_chain  # noqa: E402

CONFIG_PATH = APP_DIR / "config.json"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# "providers" is tried in order; switch method by editing this list.
# Types: server, anthropic, openrouter, openai_compatible (see autocorrect_core/providers.py).
DEFAULT_CONFIG = {
    "providers": [
        {"type": "server", "url": "", "access_code": ""},
    ],
    "hotkeys": {
        "<ctrl>+<alt>+e": {"action": "translate", "target": "English"},
        "<ctrl>+<alt>+h": {"action": "translate", "target": "Hebrew"},
        "<ctrl>+<alt>+f": {"action": "fix"},
    },
}

EXAMPLES = {
    "server": {"type": "server", "url": "https://your-server", "access_code": "ABCD-EFGH-JKMN"},
    "anthropic": {"type": "anthropic", "api_key": "sk-ant-...", "model": "claude-opus-5-5", "effort": "low"},
    "openrouter": {"type": "openrouter", "api_key": "sk-or-...", "model": "<model id from openrouter.ai/models>"},
    "openai_compatible": {"type": "openai_compatible", "base_url": "https://api.openai.com/v1",
                          "api_key": "...", "model": "..."},
}


def migrate_old_config(cfg: dict) -> dict:
    """Configs from the first version had server_url/access_code/api_key at the top level."""
    if "providers" in cfg:
        return cfg
    providers = []
    if cfg.get("server_url") and cfg.get("access_code"):
        providers.append({"type": "server", "url": cfg["server_url"], "access_code": cfg["access_code"]})
    if cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY"):
        providers.append({"type": "anthropic", "api_key": cfg.get("api_key", ""),
                          "model": cfg.get("model", "claude-opus-5-5"), "effort": cfg.get("effort", "low")})
    for key in ("server_url", "access_code", "api_key", "model", "effort"):
        cfg.pop(key, None)
    cfg["providers"] = providers or DEFAULT_CONFIG["providers"]
    return cfg


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        cfg = dict(DEFAULT_CONFIG, provider_examples=EXAMPLES)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = migrate_old_config(dict(raw))
    if cfg != raw:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    for key, value in DEFAULT_CONFIG.items():
        cfg.setdefault(key, value)
    return cfg


def is_configured(provider: dict) -> bool:
    if provider.get("type") == "server":
        return bool(provider.get("url") and provider.get("access_code"))
    if provider.get("type") == "anthropic":
        return bool(provider.get("api_key") or os.environ.get("ANTHROPIC_API_KEY"))
    return bool(provider.get("model"))


CONFIG = load_config()
busy = threading.Lock()
keyboard = None  # pynput, imported only in hotkey-listener mode
kb = None
MOD = None
_chain = None


def init_pynput():
    global keyboard, kb, MOD
    from pynput import keyboard as _keyboard
    keyboard = _keyboard
    kb = keyboard.Controller()
    MOD = keyboard.Key.cmd if IS_MAC else keyboard.Key.ctrl


def has_credentials() -> bool:
    return any(is_configured(p) for p in CONFIG["providers"])


def chain():
    global _chain
    if _chain is None:
        _chain = build_chain([p for p in CONFIG["providers"] if is_configured(p)])
    return _chain


def transform(text: str, action: Action) -> str:
    try:
        return chain().transform(text, action, log=lambda m: print(f"    ({m})"))
    except ProviderError as e:
        msg = str(e)
        if e.status == 401 and not msg.endswith("."):
            msg = "Invalid API key - check config.json."
        elif msg == "unreachable":
            msg = "No connection - check your internet."
        raise RuntimeError(msg) from e


def release_modifiers():
    # The user is still holding Ctrl/Alt from the hotkey; release them so our
    # simulated Ctrl+C / Ctrl+V isn't read as Ctrl+Alt+C.
    for key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
                keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                keyboard.Key.shift, keyboard.Key.cmd):
        try:
            kb.release(key)
        except Exception:
            pass


def press_combo(char: str):
    with kb.pressed(MOD):
        kb.press(char)
        kb.release(char)


def copy_selection() -> str:
    marker = f"__autocorrect_{time.time_ns()}__"
    pyperclip.copy(marker)
    press_combo("c")
    for _ in range(40):  # wait up to ~1s for the clipboard to update
        time.sleep(0.025)
        current = pyperclip.paste()
        if current != marker:
            return current
    return ""


def handle(action: Action):
    if not busy.acquire(blocking=False):
        return
    try:
        time.sleep(0.15)
        release_modifiers()
        time.sleep(0.05)

        try:
            original_clipboard = pyperclip.paste()
        except Exception:
            original_clipboard = ""

        text = copy_selection()
        if not text.strip():
            print("[!] No text selected.")
            pyperclip.copy(original_clipboard)
            return

        print(f"[...] {action.describe()}: {len(text)} chars")
        try:
            result = transform(text, action)
        except Exception as e:  # noqa: BLE001 - show any other failure to the user
            print(f"[x] {e}")
            pyperclip.copy(original_clipboard)
            return

        pyperclip.copy(result)
        time.sleep(0.05)
        press_combo("v")
        print("[ok] Done.")

        time.sleep(0.4)  # let the target app read the clipboard before restoring it
        pyperclip.copy(original_clipboard)
    finally:
        busy.release()


# ---------------------------------------------------------------------------
# Linux one-shot mode (works on Wayland and X11, triggered by a system shortcut)
# ---------------------------------------------------------------------------

def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def run(cmd: list, input_text: str | None = None) -> str | None:
    try:
        out = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=5)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def notify(message: str):
    print(message)
    if shutil.which("notify-send"):
        run(["notify-send", "-a", "Autocorrect", "-t", "3000", "Autocorrect", message])


def linux_read_selection() -> str:
    # On Linux, highlighted text is available as the PRIMARY selection, no Ctrl+C needed.
    candidates = []
    if is_wayland() and shutil.which("wl-paste"):
        candidates.append(["wl-paste", "--primary", "--no-newline"])
    if shutil.which("xclip"):
        candidates.append(["xclip", "-o", "-selection", "primary"])
    if shutil.which("xsel"):
        candidates.append(["xsel", "--primary", "--output"])
    for cmd in candidates:
        text = run(cmd)
        if text and text.strip():
            return text
    return ""


def linux_write_clipboard(text: str) -> bool:
    if is_wayland() and shutil.which("wl-copy"):
        # wl-copy forks and keeps serving the clipboard after we exit.
        try:
            subprocess.run(["wl-copy"], input=text, text=True, timeout=5)
            return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    if shutil.which("xclip"):
        try:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, text=True)
            p.communicate(text, timeout=5)
            return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def linux_paste() -> bool:
    time.sleep(0.15)
    if not is_wayland() and shutil.which("xdotool"):
        return run(["xdotool", "key", "--clearmodifiers", "ctrl+v"]) is not None
    if shutil.which("ydotool"):
        # Release Ctrl/Alt/Shift that may still be held from the shortcut, then Ctrl+V.
        # Key codes: 29=LeftCtrl 56=LeftAlt 42=LeftShift 47=V
        return run(["ydotool", "key", "56:0", "42:0", "29:1", "47:1", "47:0", "29:0"]) is not None
    return False


def run_once(action: Action):
    if not has_credentials():
        notify(f"Not configured - set up \"providers\" in {CONFIG_PATH}")
        sys.exit(1)

    text = linux_read_selection() if IS_LINUX else pyperclip.paste()
    if not text.strip():
        notify("No text selected.")
        return

    try:
        result = transform(text, action)
    except Exception as e:  # noqa: BLE001
        notify(f"Error: {e}")
        return

    if not linux_write_clipboard(result):
        notify("Could not write to the clipboard (install wl-clipboard or xclip).")
        return
    if linux_paste():
        print("[ok] Done.")
    else:
        notify("Ready - press Ctrl+V to paste.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_once(args: list) -> Action:
    try:
        if args[0] == "fix":
            return Action.fix()
        if args[0] == "translate" and len(args) > 1:
            return Action.translate(" ".join(args[1:]))
    except ValueError:
        pass
    sys.exit("Usage: --once fix | --once translate <Language>")


def main():
    parser = argparse.ArgumentParser(description="Translate / fix selected text with Claude.")
    parser.add_argument("--once", nargs="+", metavar="ACTION",
                        help="run one action on the current selection and exit "
                             "(e.g. --once translate English, --once fix)")
    args = parser.parse_args()

    if args.once:
        run_once(parse_once(args.once))
        return

    if IS_LINUX and is_wayland():
        print("Wayland detected: global hotkeys can't be captured here.\n"
              "Run ./install-ubuntu.sh to register system shortcuts instead.")
        sys.exit(1)

    if not has_credentials():
        print(f"Not configured. Fill in \"providers\" in {CONFIG_PATH}\n"
              f"(see \"provider_examples\" there: server + access code, or your own key).")
        sys.exit(1)

    init_pynput()
    bindings = {}
    print(f"Autocorrect is running ({chain().describe()}). Select text and press:")
    for combo, spec in CONFIG["hotkeys"].items():
        action = Action.from_dict(spec)
        print(f"  {combo:<20} {action.describe()}")
        bindings[combo] = (lambda a=action: threading.Thread(target=handle, args=(a,), daemon=True).start())
    print("Press Ctrl+C in this window to quit.\n")

    with keyboard.GlobalHotKeys(bindings) as listener:
        listener.join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
