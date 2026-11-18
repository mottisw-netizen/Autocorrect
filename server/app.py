"""
Autocorrect server: holds the AI keys so customers don't need any.

Clients (desktop app, Android app) send the selected text plus an access code;
the server checks the code, applies the daily limit, runs the AI provider chain
and returns the result.

Which AI is used (first match wins):
  1. DATA_DIR/providers.json - switch any time with `python manage.py providers use ...`,
     picked up on the next request, no restart needed.
  2. AI_PROVIDERS env var - a JSON list of provider configs, or a comma list of
     names, e.g. "anthropic,openrouter" (models from ANTHROPIC_MODEL / OPENROUTER_MODEL ...).
  3. Default: anthropic.
See autocorrect_core/providers.py for every provider type and its options.

Other env vars: DATA_DIR (default ./data), MAX_CHARS (default 10000).
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for autocorrect_core

import db  # noqa: E402
import provider_config  # noqa: E402
from autocorrect_core import Action, InvalidRequest, ProviderError  # noqa: E402

MAX_CHARS = int(os.environ.get("MAX_CHARS", "10000"))


@asynccontextmanager
async def lifespan(_app):
    db.init()
    print(f"AI providers: {provider_config.current_chain().describe()}")
    yield


app = FastAPI(title="Autocorrect", lifespan=lifespan)


def require_code(authorization: str = Header(default="")) -> dict:
    code = authorization.removeprefix("Bearer ").strip()
    customer = db.get_customer(code) if code else None
    if not customer or not customer["active"]:
        raise HTTPException(401, "invalid access code")
    return customer


class TransformRequest(BaseModel):
    text: str = Field(min_length=1)
    action: str
    target: str | None = Field(default=None, max_length=40)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/v1/me")
def me(customer: dict = Depends(require_code)):
    return {
        "name": customer["name"],
        "daily_limit": customer["daily_limit"],
        "used_today": db.used_today(customer["code"]),
    }


# A plain `def` endpoint: FastAPI runs it in a thread pool, so many requests
# are served in parallel while each waits for the AI.
@app.post("/v1/transform")
def transform(req: TransformRequest, customer: dict = Depends(require_code)):
    if len(req.text) > MAX_CHARS:
        raise HTTPException(413, f"text too long (max {MAX_CHARS} characters)")
    try:
        action = Action.from_dict(req.model_dump())
    except InvalidRequest as e:
        raise HTTPException(422, str(e)) from e
    if not db.try_consume(customer["code"], customer["daily_limit"]):
        raise HTTPException(429, "daily limit reached")
    try:
        result = provider_config.current_chain().transform(req.text, action, log=print)
    except ProviderError as e:
        db.refund(customer["code"])
        raise HTTPException(503 if e.status in (429, 529) else 502, "AI provider failed") from e
    return {"result": result}
