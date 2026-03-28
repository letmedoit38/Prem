"""
Centralised logger using loguru.
Each bot writes to its own rotating log file + shared combined log.
"""
import sys
import os
from loguru import logger
from config.settings import LOG_DIR, LOG_LEVEL


def setup_logger(bot_name: str = "main") -> "logger":
    """
    Configure loguru for a given bot/module name.
    Returns the configured logger instance.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console – coloured, human-readable
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               f"<cyan>{bot_name}</cyan> | "
               "<level>{message}</level>",
        colorize=True,
    )

    # Per-bot rotating file
    logger.add(
        f"{LOG_DIR}/{bot_name}_{{time:YYYY-MM-DD}}.log",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )

    # Combined log for all bots
    logger.add(
        f"{LOG_DIR}/combined_{{time:YYYY-MM-DD}}.log",
        level="INFO",
        rotation="1 day",
        retention="30 days",
        compression="zip",
        format=f"{{time:YYYY-MM-DD HH:mm:ss}} | {{level: <8}} | {bot_name} | {{message}}",
    )

    return logger


# Trade-specific audit log (plain CSV-style for easy review)
def log_trade(action: str, symbol: str, qty: int, price: float,
              order_id: str, bot: str, pnl: float = 0.0):
    os.makedirs(LOG_DIR, exist_ok=True)
    from datetime import datetime
    line = (f"{datetime.now().isoformat()},{bot},{action},{symbol},"
            f"{qty},{price:.2f},{order_id},{pnl:.2f}\n")
    with open(f"{LOG_DIR}/trade_audit.csv", "a") as f:
        f.write(line)
