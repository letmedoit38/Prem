"""
Windows-friendly interactive setup script.
Run this ONCE to create your .env file by answering prompts.
Usage: python setup_wizard.py
"""
import os
import sys


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def banner():
    print("=" * 52)
    print("   PREM TRADING BOT — First-Time Setup Wizard")
    print("=" * 52)
    print()


def ask(prompt, secret=False):
    import getpass
    if secret:
        val = getpass.getpass(f"  {prompt}: ")
    else:
        val = input(f"  {prompt}: ").strip()
    return val


def main():
    clear()
    banner()
    print("This wizard will create your .env credentials file.")
    print("Your details are stored ONLY on your computer.\n")

    print("─── Zerodha Credentials ─────────────────────────────")
    api_key    = ask("Zerodha API Key (from kite.trade → My Apps)")
    api_secret = ask("Zerodha API Secret", secret=True)
    user_id    = ask("Zerodha User ID (e.g. AB1234)")
    password   = ask("Zerodha Password", secret=True)
    totp_secret= ask("TOTP Secret (Base32 string from Zerodha 2FA setup)")

    print()
    print("─── Trading Configuration ───────────────────────────")
    capital = ask("Starting capital in INR [press Enter for 5000]")
    if not capital:
        capital = "5000"

    print()
    print("─── Optional: Telegram Alerts ───────────────────────")
    print("  (Press Enter to skip if you don't want alerts)")
    tg_token  = ask("Telegram Bot Token (or press Enter to skip)")
    tg_chat   = ask("Telegram Chat ID   (or press Enter to skip)") if tg_token else ""

    # Write .env file
    env_content = f"""# Zerodha KiteConnect Credentials
ZERODHA_API_KEY={api_key}
ZERODHA_API_SECRET={api_secret}
ZERODHA_USER_ID={user_id}
ZERODHA_PASSWORD={password}
ZERODHA_TOTP_SECRET={totp_secret}

# Trading Configuration
TOTAL_CAPITAL={capital}
STOP_LOSS_PCT=5.0
MAX_TRADE_CAPITAL_PCT=40
MAX_OPEN_POSITIONS=3

# Telegram Alerts (optional)
TELEGRAM_BOT_TOKEN={tg_token}
TELEGRAM_CHAT_ID={tg_chat}
"""
    with open(".env", "w") as f:
        f.write(env_content)

    print()
    print("=" * 52)
    print("  ✓  .env file created successfully!")
    print()
    print("  Next step — validate your credentials:")
    print()
    print("     python main.py --check")
    print()
    print("=" * 52)


if __name__ == "__main__":
    main()
