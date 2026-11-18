"""
Manage customer access codes.

    python manage.py add "Dana Cohen" --limit 200   # create a code (200 actions per day)
    python manage.py list                           # show all customers and today's usage
    python manage.py disable ABCD-EFGH-JKMN         # block a code
    python manage.py enable  ABCD-EFGH-JKMN
    python manage.py limit   ABCD-EFGH-JKMN 500     # change the daily limit

Switch the AI (takes effect on the next request, no restart):
    python manage.py providers show
    python manage.py providers use openrouter,anthropic       # OpenRouter first, Claude as backup
    python manage.py providers use '[{"type": "openrouter", "model": "..."}]'
    python manage.py providers reset                          # back to the AI_PROVIDERS env var
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for autocorrect_core

import db  # noqa: E402
import provider_config  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Manage Autocorrect access codes")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("--limit", type=int, default=200, help="actions per day (default 200)")
    sub.add_parser("list")
    for name in ("disable", "enable"):
        sub.add_parser(name).add_argument("code")
    lim = sub.add_parser("limit")
    lim.add_argument("code")
    lim.add_argument("daily_limit", type=int)
    prov = sub.add_parser("providers")
    prov.add_argument("op", choices=["show", "use", "reset"])
    prov.add_argument("spec", nargs="?", help="comma list of names or a JSON list of provider configs")
    args = p.parse_args()

    if args.cmd == "providers":
        if args.op == "use":
            if not args.spec:
                sys.exit("Give providers, e.g.: providers use openrouter,anthropic")
            provider_config.save(provider_config.parse_spec(args.spec))
        elif args.op == "reset":
            provider_config.reset()
        source = "providers.json" if provider_config.PROVIDERS_FILE.exists() else "environment"
        specs = provider_config.configured_specs()
        safe = [{k: ("***" if k == "api_key" and not str(v).startswith("env:") else v) for k, v in c.items()}
                for c in specs]
        print(f"Active providers (from {source}), tried in order:")
        print(json.dumps(safe, indent=2))
        print("Chain:", provider_config.build_chain(specs).describe())
        return

    db.init()
    if args.cmd == "add":
        code = db.add_customer(args.name, args.limit)
        print(f"Access code for {args.name}: {code}")
    elif args.cmd == "list":
        rows = db.list_customers()
        if not rows:
            print("No customers yet.")
        for r in rows:
            status = "active" if r["active"] else "DISABLED"
            print(f"{r['code']}  {status:<8}  {r['used_today']:>4}/{r['daily_limit']:<5}  {r['name']}")
    elif args.cmd in ("disable", "enable"):
        ok = db.set_active(args.code, args.cmd == "enable")
        print("Done." if ok else "Code not found.")
    elif args.cmd == "limit":
        print("Done." if db.set_limit(args.code, args.daily_limit) else "Code not found.")


if __name__ == "__main__":
    main()
