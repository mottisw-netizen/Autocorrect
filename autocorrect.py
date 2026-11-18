"""
Autocorrect engine - select text anywhere, press a hotkey, get it translated / fixed in place.

Default hotkeys (editable in config.json):
    Ctrl+Alt+E  ->  translate selection to English
    Ctrl+Alt+H  ->  translate selection to Hebrew
    Ctrl+Alt+F  ->  fix spelling & grammar (keeps the original language)

How it works: the app copies the current selection, sends it to the AI
(your server, Claude, OpenRouter, ... - see "providers" in config.json),
then pastes the result back over the selection. Your original clipboard
content is restored afterwards.

Ways to run:
    desktop_app.py              tray icon + settings window (what the installers ship)
    autocorrect.py              console version of the same hotkey listener
    autocorrect.py --once fix   one action on the current selection (used by install-ubuntu.sh)
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
from pathlib import Path

import pyperclip

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(APP_DIR))
from autocorrect_core import Action, ProviderError, build_chain  # noqa: E402

IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
FROZEN = getattr(sys, "frozen", False)  # running from an installer build


def user_config_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home())) / "Autocorrect"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "Autocorrect"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autocorrect"


# Installed app: settings live in the user's folder. Running from source: next to the script.
CONFIG_PATH = Path(os.environ.get("AUTOCORRECT_CONFIG") or
                   (user_config_dir() / "config.json" if FROZEN else APP_DIR / "config.json"))

# "providers" is tried in order; switch method by editing this list (or in the settings window).
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


def build_defaults() -> dict:
    """DEFAULT_CONFIG plus anything baked into the installer (defaults.json: server url, ...)."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    baked = APP_DIR / "defaults.json"
    if baked.exists():
        try:
            extra = json.loads(baked.read_text(encoding="utf-8"))
            if extra.get("server_url"):
                cfg["providers"][0]["url"] = extra["server_url"]
        except (ValueError, OSError):
            pass
    return cfg


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
    cfg["providers"] = providers or build_defaults()["providers"]
    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        save_config(dict(build_defaults(), provider_examples=EXAMPLES))
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg = migrate_old_config(dict(raw))
    if cfg != raw:
        save_config(cfg)
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
_config_mtime = CONFIG_PATH.stat().st_mtime
_chain = None
busy = threading.Lock()

# Optional hook so the tray app can show notifications its own way.
notify_hook = None


def reload_config_if_changed():
    """Pick up changes saved by the settings window without restarting."""
    global CONFIG, _config_mtime, _chain
    try:
        mtime = CONFIG_PATH.stat().st_mtime
    except OSError:
        return
    if mtime != _config_mtime:
        CONFIG, _config_mtime, _chain = load_config(), mtime, None


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
        if e.status in (401, 403) and not msg.endswith("."):
            msg = "Invalid API key - check the settings."
        elif e.status == 402:
            msg = "The AI account is out of credit."
        elif msg == "unreachable":
            msg = "No connection - check your internet."
        raise RuntimeError(msg) from e


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def run(cmd: list, input_text: str | None = None) -> str | None:
    try:
        out = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=5)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def notify(message: str):
    print(message)
    if notify_hook:
        try:
            notify_hook(message)
            return
        except Exception:
            pass
    if IS_MAC:
        safe = message.replace("\\", "\\\\").replace('"', '\\"')
        run(["osascript", "-e", f'display notification "{safe}" with title "Autocorrect"'])
    elif shutil.which("notify-send"):
        run(["notify-send", "-a", "Autocorrect", "-t", "3000", "Autocorrect", message])


# ---------------------------------------------------------------------------
# Keyboard (pynput). Keys are matched by their physical position, so the hotkeys
# and the simulated Ctrl+C / Ctrl+V also work with a Hebrew (or any) keyboard layout.
# ---------------------------------------------------------------------------

keyboard = None  # pynput.keyboard, imported only in hotkey mode
kb = None
MOD = None

# macOS virtual key codes for letters/digits (layout independent).
_MAC_VK = {0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v", 11: "b",
           12: "q", 13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4",
           22: "6", 23: "5", 25: "9", 26: "7", 28: "8", 29: "0", 31: "o", 32: "u", 34: "i", 35: "p",
           37: "l", 38: "j", 40: "k", 45: "n", 46: "m"}
_MAC_VK_BY_CHAR = {c: vk for vk, c in _MAC_VK.items()}


def init_pynput():
    global keyboard, kb, MOD
    from pynput import keyboard as _keyboard
    keyboard = _keyboard
    kb = keyboard.Controller()
    MOD = keyboard.Key.cmd if IS_MAC else keyboard.Key.ctrl


def physical_letter(key) -> str | None:
    """The letter/digit printed on the key, regardless of the active keyboard layout."""
    vk = getattr(key, "vk", None)
    char = getattr(key, "char", None)
    if IS_WINDOWS and vk is not None and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
        return chr(vk).lower()
    if IS_MAC and vk in _MAC_VK:
        return _MAC_VK[vk]
    if char and len(char) == 1 and char.isascii() and char.isalnum():
        return char.lower()
    if vk is not None and (0x61 <= vk <= 0x7A or 0x30 <= vk <= 0x39):  # X11 keysyms
        return chr(vk)
    return None


def key_for(letter: str):
    """A pynput key that presses the physical key for `letter` (for simulating Ctrl+C / Ctrl+V)."""
    if IS_WINDOWS:
        return keyboard.KeyCode.from_vk(ord(letter.upper()))
    if IS_MAC:
        return keyboard.KeyCode.from_vk(_MAC_VK_BY_CHAR[letter])
    return keyboard.KeyCode.from_char(letter)


def parse_combo(combo: str) -> tuple[frozenset, str]:
    mods, letter = set(), None
    for part in combo.lower().split("+"):
        part = part.strip()
        if part in ("<ctrl>", "<control>"):
            mods.add("ctrl")
        elif part in ("<alt>", "<option>"):
            mods.add("alt")
        elif part == "<shift>":
            mods.add("shift")
        elif part in ("<cmd>", "<super>", "<win>"):
            mods.add("cmd")
        else:
            letter = part.strip("<>")
    if not letter:
        raise ValueError(f"bad hotkey {combo!r}")
    return frozenset(mods), letter


class HotkeyListener:
    """Global hotkeys matched by physical key (unlike pynput.GlobalHotKeys, which uses the typed character)."""

    def __init__(self, bindings: dict):
        self.bindings = {parse_combo(c): fn for c, fn in bindings.items()}
        self.mods: set[str] = set()
        K = keyboard.Key
        self.mod_names = {}
        for name, keys in {"ctrl": ("ctrl", "ctrl_l", "ctrl_r"), "alt": ("alt", "alt_l", "alt_r", "alt_gr"),
                           "shift": ("shift", "shift_l", "shift_r"), "cmd": ("cmd", "cmd_l", "cmd_r")}.items():
            for k in keys:
                if hasattr(K, k):
                    self.mod_names[getattr(K, k)] = name
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)

    def _press(self, key):
        if key in self.mod_names:
            self.mods.add(self.mod_names[key])
            return
        letter = physical_letter(key)
        fn = self.bindings.get((frozenset(self.mods), letter)) if letter else None
        if fn:
            fn()

    def _release(self, key):
        self.mods.discard(self.mod_names.get(key))

    def start(self):
        self.listener.start()

    def join(self):
        self.listener.join()

    def stop(self):
        self.listener.stop()


def release_modifiers():
    # The user is still holding Ctrl/Alt from the hotkey; release them so our
    # simulated Ctrl+C / Ctrl+V isn't read as Ctrl+Alt+C.
    for name in ("alt", "alt_l", "alt_r", "alt_gr", "ctrl", "ctrl_l", "ctrl_r", "shift", "cmd"):
        key = getattr(keyboard.Key, name, None)
        if key is None:
            continue
        try:
            kb.release(key)
        except Exception:
            pass


def press_combo(letter: str):
    key = key_for(letter)
    with kb.pressed(MOD):
        kb.press(key)
        kb.release(key)


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
    """Run one action on the current selection (hotkey mode)."""
    if not busy.acquire(blocking=False):
        return
    try:
        reload_config_if_changed()
        if not has_credentials():
            notify("Autocorrect isn't set up yet - open Settings.")
            return

        time.sleep(0.15)
        release_modifiers()
        time.sleep(0.05)

        try:
            original_clipboard = pyperclip.paste()
        except Exception:
            original_clipboard = ""

        text = copy_selection()
        if not text.strip():
            notify("No text selected.")
            pyperclip.copy(original_clipboard)
            return

        print(f"[...] {action.describe()}: {len(text)} chars")
        try:
            result = transform(text, action)
        except Exception as e:  # noqa: BLE001 - show any failure to the user
            notify(str(e))
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


def start_hotkeys() -> HotkeyListener:
    """Start listening for the configured hotkeys in the background."""
    init_pynput()
    bindings = {}
    for combo, spec in CONFIG["hotkeys"].items():
        action = Action.from_dict(spec)
        bindings[combo] = (lambda a=action: threading.Thread(target=handle, args=(a,), daemon=True).start())
    listener = HotkeyListener(bindings)
    listener.start()
    return listener


def describe_hotkeys() -> list[tuple[str, str]]:
    out = []
    for combo, spec in CONFIG["hotkeys"].items():
        mods, letter = parse_combo(combo)
        names = {"ctrl": "Ctrl", "alt": "Option" if IS_MAC else "Alt", "shift": "Shift",
                 "cmd": "Cmd" if IS_MAC else "Win"}
        order = ["ctrl", "alt", "shift", "cmd"]
        label = "+".join([names[m] for m in order if m in mods] + [letter.upper()])
        out.append((label, Action.from_dict(spec).describe()))
    return out


# ---------------------------------------------------------------------------
# Linux one-shot mode (works on Wayland and X11, triggered by a system shortcut)
# ---------------------------------------------------------------------------

def is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


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
# Entry point (console version)
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
    parser = argparse.ArgumentParser(description="Translate / fix selected text with AI.")
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

    print(f"Autocorrect is running ({chain().describe()}). Select text and press:")
    for label, desc in describe_hotkeys():
        print(f"  {label:<20} {desc}")
    print("Press Ctrl+C in this window to quit.\n")
    start_hotkeys().join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
