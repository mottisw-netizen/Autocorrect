#!/bin/bash
# Installs Autocorrect on Ubuntu (GNOME, Wayland or X11) and registers keyboard shortcuts.
# Safe to run again: it updates the existing shortcuts instead of adding duplicates.
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

echo "==> Installing system packages (needs sudo)..."
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip xclip wl-clipboard xdotool libnotify-bin

echo "==> Creating Python environment..."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

# Creates config.json with defaults if it doesn't exist yet.
.venv/bin/python -c "import autocorrect" >/dev/null 2>&1 || true

echo "==> Registering keyboard shortcuts from config.json..."
.venv/bin/python - "$APP_DIR" <<'PY'
import ast, json, subprocess, sys
app_dir = sys.argv[1]
SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"

def to_gnome(combo):
    names = {"ctrl": "<Primary>", "alt": "<Alt>", "shift": "<Shift>", "cmd": "<Super>", "super": "<Super>"}
    out = ""
    for part in combo.split("+"):
        part = part.strip()
        if part.startswith("<") and part.endswith(">"):
            out += names.get(part[1:-1].lower(), "")
        else:
            out += part.lower()
    return out

cfg = json.load(open(f"{app_dir}/config.json", encoding="utf-8"))
current = subprocess.run(["gsettings", "get", SCHEMA, "custom-keybindings"],
                         capture_output=True, text=True).stdout.strip()
paths = ast.literal_eval(current.replace("@as ", "")) if current else []
paths = [p for p in paths if "/autocorrect" not in p]  # drop our old entries

for i, (combo, action) in enumerate(cfg["hotkeys"].items()):
    path = f"{BASE}autocorrect{i}/"
    if action["action"] == "translate":
        args, name = f"translate {action['target']}", f"Autocorrect: translate to {action['target']}"
    else:
        args, name = "fix", "Autocorrect: fix spelling & grammar"
    command = f"'{app_dir}/.venv/bin/python' '{app_dir}/autocorrect.py' --once {args}"
    key = f"{SCHEMA}.custom-keybinding:{path}"
    subprocess.run(["gsettings", "set", key, "name", name], check=True)
    subprocess.run(["gsettings", "set", key, "command", command], check=True)
    subprocess.run(["gsettings", "set", key, "binding", to_gnome(combo)], check=True)
    paths.append(path)
    print(f"   {to_gnome(combo):<20} {name}")

subprocess.run(["gsettings", "set", SCHEMA, "custom-keybindings", str(paths)], check=True)
PY

echo
echo "Done!"
if ! grep -q '"api_key": "[^"]' config.json; then
  echo "Next step: put your Claude API key in $APP_DIR/config.json (\"api_key\")."
fi
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
  echo "Note: you're on Wayland. After the text is processed you'll get a notification"
  echo "      and just press Ctrl+V. (Or log in with 'Ubuntu on Xorg' for automatic pasting.)"
fi
