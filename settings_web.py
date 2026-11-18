"""
Settings page for the desktop app, shown in the user's browser.

A tiny web server on 127.0.0.1 (random port) serves one page. Every URL carries a
random token, so websites and other users on the machine can't read or change the
settings. Browsers render Hebrew / right-to-left text properly on every OS, which
desktop GUI toolkits like Tk don't.
"""

import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import autocorrect as engine
from autocorrect_core import Action, build_chain

PAGE = Path(engine.APP_DIR) / "settings.html"

HEBREW_ACTIONS = {"translate to English": "תרגום לאנגלית", "translate to Hebrew": "תרגום לעברית",
                  "fix spelling & grammar": "תיקון שגיאות"}


def split_config(cfg: dict) -> dict:
    """Current providers -> simple form fields."""
    f = {"mode": "server", "url": "", "code": "", "service": "openrouter",
         "api_key": "", "model": "", "base_url": ""}
    for p in cfg.get("providers", []):
        if p.get("type") == "server":
            f.update(url=p.get("url", ""), code=p.get("access_code", ""))
    first = (cfg.get("providers") or [{}])[0]
    t = first.get("type")
    if t and t != "server":
        f.update(mode="own_key", api_key=first.get("api_key", ""), model=first.get("model", ""))
        if t == "openai_compatible":
            base = first.get("base_url", "")
            f.update(service="openai" if "api.openai.com" in base else "custom", base_url=base)
        else:
            f["service"] = t
    return f


def provider_from_fields(f: dict) -> dict:
    if f.get("mode") == "server":
        return {"type": "server", "url": f.get("url", "").strip().rstrip("/"),
                "access_code": f.get("code", "").strip().upper()}
    service = f.get("service")
    p = {"api_key": f.get("api_key", "").strip(), "model": f.get("model", "").strip()}
    if service == "anthropic":
        return {"type": "anthropic", "effort": "low", **p, "model": p["model"] or "claude-opus-5-5"}
    if service == "openrouter":
        return {"type": "openrouter", **p}
    base = "https://api.openai.com/v1" if service == "openai" else f.get("base_url", "").strip().rstrip("/")
    return {"type": "openai_compatible", "base_url": base, **p}


def missing_fields(provider: dict) -> bool:
    if provider["type"] == "server":
        return not (provider["url"] and provider["access_code"])
    if provider["type"] == "openai_compatible" and not provider.get("base_url"):
        return True
    return not (provider.get("api_key") and provider.get("model"))


def hebrew_error(e: Exception) -> str:
    status = getattr(e, "status", None)
    msg = str(e)
    if status == 401:
        return "קוד הגישה לא תקין." if msg.startswith("Invalid access code") else "המפתח לא תקין."
    if status == 403:
        return "המפתח לא תקין או שאין לו הרשאה."
    if status == 402:
        return "נגמרה היתרה בחשבון ה-AI."
    if status == 404:
        return "הכתובת או שם המודל לא נמצאו."
    if status == 429:
        return "הגעתם למכסה היומית." if msg.startswith("Daily limit") else "השירות עמוס, נסו שוב בעוד רגע."
    if msg == "unreachable":
        return "אין חיבור. בדקו את האינטרנט ואת הכתובת."
    return msg


def state() -> dict:
    engine.reload_config_if_changed()
    cfg = engine.load_config()
    fields = split_config(cfg)
    preset_url = engine.build_defaults()["providers"][0]["url"]
    return {
        "fields": fields,
        "server_preset": bool(preset_url) and fields["url"] == preset_url,
        "configured": engine.has_credentials(),
        "hotkeys": [{"keys": k, "action": HEBREW_ACTIONS.get(d, d)} for k, d in engine.describe_hotkeys()],
    }


def save(fields: dict) -> dict:
    provider = provider_from_fields(fields)
    if missing_fields(provider):
        return {"ok": False, "message": "חסרים פרטים. מלאו את כל השדות."}
    cfg = engine.load_config()
    # The chosen method goes first; a working access code stays as a backup.
    backup = [p for p in cfg.get("providers", [])
              if provider["type"] != "server" and p.get("type") == "server" and engine.is_configured(p)]
    cfg["providers"] = [provider] + backup
    cfg.pop("provider_examples", None)
    engine.save_config(cfg)
    try:
        build_chain([provider]).transform("helo", Action.fix())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "saved": True, "message": f"ההגדרות נשמרו, אבל הבדיקה נכשלה: {hebrew_error(e)}"}
    return {"ok": True, "saved": True, "message": "נשמר ✓  הכול עובד! אפשר לסגור את הדף."}


class SettingsServer:
    def __init__(self):
        self.token = secrets.token_urlsafe(16)
        token = self.token

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _allowed(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0]
                return host in ("127.0.0.1", "localhost") and self.path.startswith(f"/{token}/")

            def _send(self, code: int, body: bytes, ctype: str):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, data: dict, code: int = 200):
                self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json")

            def do_GET(self):
                if not self._allowed():
                    return self._send(404, b"", "text/plain")
                route = self.path[len(token) + 2:]
                if route in ("", "index.html"):
                    return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                if route == "api/state":
                    return self._json(state())
                self._send(404, b"", "text/plain")

            def do_POST(self):
                if not self._allowed() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self._send(404, b"", "text/plain")
                route = self.path[len(token) + 2:]
                length = min(int(self.headers.get("Content-Length") or 0), 100_000)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._json({"ok": False, "message": "bad request"}, 400)
                if route == "api/save":
                    return self._json(save(data))
                self._send(404, b"", "text/plain")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/{self.token}/"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def open(self):
        webbrowser.open(self.url)

    def stop(self):
        self.httpd.shutdown()
