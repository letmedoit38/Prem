"""
CLI management tool for the Stock Alert Bot.

Usage
─────
  python manage.py watchlist              — show all symbols
  python manage.py add ZOMATO             — add with default name/sector
  python manage.py add ZOMATO "Zomato" "Internet"
  python manage.py remove ZOMATO          — remove custom symbol
  python manage.py check                  — run price check + send alerts now
  python manage.py news                   — fetch & send latest news now
  python manage.py status                 — print live snapshot (no WhatsApp)
  python manage.py test                   — send a test WhatsApp message
"""
import sys
import os
from dotenv import load_dotenv

load_dotenv()


def cmd_watchlist():
    from watchlist_manager import get_watchlist_text
    # Plain text version for CLI
    from watchlist_manager import DEFAULT_STOCKS, DEFAULT_ETFS, _load
    custom = _load().get("custom", {})
    print("\n=== Watchlist ===")
    print("\nLarge-Cap Stocks:")
    for sym, info in DEFAULT_STOCKS.items():
        print(f"  {sym:<20} {info['name']:<35} [{info['sector']}]")
    print("\nETFs:")
    for sym, info in DEFAULT_ETFS.items():
        print(f"  {sym:<20} {info['name']:<35} [{info['sector']}]")
    if custom:
        print("\nCustom / Small-Cap:")
        for sym, info in custom.items():
            print(f"  {sym:<20} {info['name']:<35} [{info['sector']}]")
    total = len(DEFAULT_STOCKS) + len(DEFAULT_ETFS) + len(custom)
    print(f"\nTotal: {total} symbols\n")


def cmd_add(args):
    if not args:
        print("Usage: python manage.py add SYMBOL [Name] [Sector]")
        sys.exit(1)
    from watchlist_manager import add_symbol
    ticker = args[0]
    name   = args[1] if len(args) > 1 else ""
    sector = args[2] if len(args) > 2 else "Custom"
    ok, msg = add_symbol(ticker, name=name, sector=sector)
    print(msg)


def cmd_remove(args):
    if not args:
        print("Usage: python manage.py remove SYMBOL")
        sys.exit(1)
    from watchlist_manager import remove_symbol
    ok, msg = remove_symbol(args[0])
    print(msg)


def cmd_check():
    from watchlist_manager import get_all_symbols
    from stock_monitor import fetch_snapshots, make_alert_messages, make_status_report
    from whatsapp import send

    print("Fetching prices...")
    snaps  = fetch_snapshots(get_all_symbols())
    alerts = make_alert_messages(snaps)
    if alerts:
        print(f"Found {len(alerts)} alert(s). Sending via WhatsApp...")
        for msg in alerts:
            print(f"\n{msg}\n")
            send(msg)
    else:
        print("No alerts — all stocks within normal range.")
        print(make_status_report(snaps))


def cmd_news():
    from watchlist_manager import get_all_symbols
    from news_monitor import fetch_news, format_news
    from whatsapp import send

    print("Fetching news...")
    sectors = list({v["sector"] for v in get_all_symbols().values()})
    items   = fetch_news(watched_sectors=sectors, max_per_feed=5)
    if items:
        print(f"Found {len(items)} item(s). Sending via WhatsApp...")
        for item in items[:5]:
            msg = format_news(item)
            print(f"\n{msg}\n---")
            send(msg)
    else:
        print("No new important news.")


def cmd_status():
    from watchlist_manager import get_all_symbols
    from stock_monitor import fetch_snapshots, make_status_report

    print("Fetching live prices...")
    snaps = fetch_snapshots(get_all_symbols())
    print(make_status_report(snaps))


def cmd_test():
    from whatsapp import send
    print(f"Sending test message to {os.getenv('WHATSAPP_PHONE')}...")
    ok = send("Stock Alert Bot is running! This is a test message.")
    print("Sent successfully." if ok else "FAILED. Check WHATSAPP_PHONE and CALLMEBOT_APIKEY in .env")


COMMANDS = {
    "watchlist": (cmd_watchlist, []),
    "add":       (cmd_add,       "args"),
    "remove":    (cmd_remove,    "args"),
    "check":     (cmd_check,     []),
    "news":      (cmd_news,      []),
    "status":    (cmd_status,    []),
    "test":      (cmd_test,      []),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0)
    cmd, argspec = COMMANDS[sys.argv[1]]
    if argspec == "args":
        cmd(sys.argv[2:])
    else:
        cmd()
