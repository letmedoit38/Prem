"""
Centralised logger using loguru.
Each bot writes to its own rotating log file + shared combined log.
"""
import sys
import os
from loguru import logger
from config.settings import LOG_DIR, LOG_LEVEL

# Track which bot-specific file sinks have been added (avoids duplicate sinks)
_initialized: bool = False
_bot_sinks: dict = {}   # bot_name -> sink id


def setup_logger(bot_name: str = "main") -> "logger":
    """
    Configure loguru for a given bot/module name.
    Returns a context-bound logger that includes bot_name in every message.

    Safe to call multiple times with different bot names – each call adds
    a per-bot file sink once without wiping previously added sinks.
    """
    global _initialized

    os.makedirs(LOG_DIR, exist_ok=True)

    if not _initialized:
        # Remove the default loguru handler (stderr, no format)
        logger.remove()

        # Single console sink shared by all bots – uses the 'bot' bind key
        logger.add(
            sys.stdout,
            level=LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{extra[bot]}</cyan> | "
                   "<level>{message}</level>",
            colorize=True,
        )

        # Single combined file sink – all bots write here
        logger.add(
            f"{LOG_DIR}/combined_{{time:YYYY-MM-DD}}.log",
            level="INFO",
            rotation="1 day",
            retention="30 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[bot]} | {message}",
        )

        _initialized = True

    # Add a per-bot file sink only once per bot name
    if bot_name not in _bot_sinks:
        sink_id = logger.add(
            f"{LOG_DIR}/{bot_name}_{{time:YYYY-MM-DD}}.log",
            level="DEBUG",
            rotation="1 day",
            retention="30 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            filter=lambda record, _b=bot_name: record["extra"].get("bot") == _b,
        )
        _bot_sinks[bot_name] = sink_id

    # Return a context-bound logger that stamps bot_name on every record
    return logger.bind(bot=bot_name)


# Trade-specific audit log (plain CSV-style for easy review)
def log_trade(action: str, symbol: str, qty: int, price: float,
              order_id: str, bot: str, pnl: float = 0.0):
    os.makedirs(LOG_DIR, exist_ok=True)
    from datetime import datetime
    line = (f"{datetime.now().isoformat()},{bot},{action},{symbol},"
            f"{qty},{price:.2f},{order_id},{pnl:.2f}\n")
    with open(f"{LOG_DIR}/trade_audit.csv", "a") as f:
        f.write(line)
