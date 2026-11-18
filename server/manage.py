"""
Manage customer access codes.

    python manage.py add "Dana Cohen" --limit 200   # create a code (200 actions per day)
    python manage.py list                           # show all customers and today's usage
    python manage.py disable ABCD-EFGH-JKMN         # block a code
    python manage.py enable  ABCD-EFGH-JKMN
    python manage.py limit   ABCD-EFGH-JKMN 500     # change the daily limit
"""

import argparse

import db


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
    args = p.parse_args()

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
