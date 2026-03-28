"""
Abstract base class for all trading strategy bots.

Each concrete bot must implement:
  - scan()   → look for entry signals across watched symbols
  - manage() → check existing open positions for exit conditions

The base class handles:
  - Risk gate (delegates to RiskManager)
  - Order placement (delegates to OrderManager)
  - Loop timing with configurable scan interval
  - Graceful shutdown on halt signal
"""
import time
import threading
from abc import ABC, abstractmethod
from typing import List

from core.risk_manager import RiskManager, get_risk_manager
from utils.logger import setup_logger


class BaseStrategy(ABC):
    """Base class for all trading bots."""

    def __init__(
        self,
        name: str,
        symbols: List[str],
        scan_interval_seconds: int = 60,
    ):
        self.name = name
        self.symbols = symbols
        self.scan_interval = scan_interval_seconds
        self.risk: RiskManager = get_risk_manager()
        self.log = setup_logger(name)
        self._stop_event = threading.Event()
        self.log.info(f"{name} initialised | Watching: {symbols}")

    # ── Interface methods ──────────────────────────────────────────────────────

    @abstractmethod
    def scan(self) -> None:
        """
        Scan all watched symbols for entry signals.
        Must call self.risk.can_trade() before placing any order.
        """
        ...

    @abstractmethod
    def manage_positions(self) -> None:
        """
        Check all open positions held by this bot.
        Apply trailing stop, check targets, force-close near EOD.
        """
        ...

    # ── Run loop ───────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Main loop: scan → manage → sleep → repeat until stopped."""
        self.log.info(f"{self.name} starting run loop (interval={self.scan_interval}s)")
        while not self._stop_event.is_set():
            try:
                if not self.risk.halted:
                    self.scan()
                    self.manage_positions()
                else:
                    self.log.warning(f"{self.name} is halted – skipping scan.")
            except Exception as e:
                self.log.exception(f"Unexpected error in {self.name} run loop: {e}")
            self._stop_event.wait(self.scan_interval)
        self.log.info(f"{self.name} stopped.")

    def stop(self) -> None:
        """Signal the bot to stop gracefully."""
        self._stop_event.set()

    def start_in_thread(self) -> threading.Thread:
        """Launch the bot's run loop in a daemon thread."""
        t = threading.Thread(target=self.run, name=self.name, daemon=True)
        t.start()
        self.log.info(f"{self.name} thread started.")
        return t
