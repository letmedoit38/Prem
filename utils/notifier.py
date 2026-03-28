"""
Optional Telegram notifications for trade alerts and daily summary.
Silently skips if credentials are not configured.
"""
import requests
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(message: str) -> None:
    """Send a message via Telegram bot. No-op if not configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception:
        pass  # Notifications are best-effort


def notify_trade(bot: str, action: str, symbol: str, qty: int,
                 price: float, pnl: float = 0.0) -> None:
    emoji = "🟢" if action == "BUY" else "🔴"
    msg = (f"{emoji} [{bot}] {action} {qty}x {symbol} @ ₹{price:.2f}")
    if pnl:
        msg += f"\n  P&L: ₹{pnl:+.2f}"
    send_telegram(msg)


def notify_daily_summary(total_pnl: float, trades: int, capital_used: float) -> None:
    status = "✅ Profit" if total_pnl >= 0 else "❌ Loss"
    msg = (
        f"📊 Daily Summary\n"
        f"{status}: ₹{total_pnl:+.2f}\n"
        f"Trades executed: {trades}\n"
        f"Capital deployed: ₹{capital_used:.2f}"
    )
    send_telegram(msg)


def notify_stop_loss_hit(daily_loss: float, limit: float) -> None:
    send_telegram(
        f"🚨 DAILY STOP LOSS HIT\n"
        f"Loss: ₹{daily_loss:.2f} / Limit: ₹{limit:.2f}\n"
        f"All bots halted for today."
    )
