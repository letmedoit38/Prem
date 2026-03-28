"""
Market calendar utilities for NSE India.

Determines whether today is a trading day:
  - Not a weekend (Sat/Sun)
  - Not an NSE holiday (uses the `holidays` library for India)

Used by the scheduler to decide whether to start the bots.
"""
from datetime import date, datetime

import holidays
import pytz

from config.settings import TIMEZONE


# NSE observes all national Indian holidays plus some exchange-specific ones.
# The `holidays` library covers the common ones; exchange-specific closures
# (like budget day, election day) would need manual override.
INDIA_HOLIDAYS = holidays.India(years=range(2024, 2030))

# Additional NSE-specific holidays not in the standard calendar can be added here
NSE_EXTRA_HOLIDAYS: set = set()


def is_market_open_today(check_date: date | None = None) -> bool:
    """Return True if NSE is open on the given date (defaults to today IST)."""
    ist = pytz.timezone(TIMEZONE)
    if check_date is None:
        check_date = datetime.now(ist).date()

    # Weekend check
    if check_date.weekday() >= 5:   # 5=Saturday, 6=Sunday
        return False

    # Holiday check
    if check_date in INDIA_HOLIDAYS:
        return False

    if check_date in NSE_EXTRA_HOLIDAYS:
        return False

    return True


def next_trading_day(from_date: date | None = None) -> date:
    """Return the next NSE trading day after `from_date`."""
    from datetime import timedelta
    ist = pytz.timezone(TIMEZONE)
    if from_date is None:
        from_date = datetime.now(ist).date()
    candidate = from_date + timedelta(days=1)
    while not is_market_open_today(candidate):
        candidate += timedelta(days=1)
    return candidate
