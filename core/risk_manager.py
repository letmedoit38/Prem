"""
Risk Manager – the single source of truth for capital and loss control.

Rules enforced:
  • Daily loss limit = 5% of total capital (₹250 on ₹5k)
  • When daily loss limit is hit → all bots are halted immediately
  • Per-trade stop loss = configurable % of trade value (default 2%)
  • Position sizing = never risk more than MAX_TRADE_CAPITAL_PCT of capital per trade
  • Max simultaneous open positions = MAX_OPEN_POSITIONS

Thread-safe: uses a threading.Lock for shared state updates.
"""
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from config.settings import (
    TOTAL_CAPITAL, DAILY_LOSS_LIMIT, MAX_TRADE_CAPITAL_PCT, MAX_OPEN_POSITIONS
)
from utils.logger import setup_logger
from utils.notifier import notify_stop_loss_hit

log = setup_logger("risk_manager")


@dataclass
class Position:
    symbol: str
    qty: int
    entry_price: float
    stop_loss_price: float
    target_price: Optional[float]   # None = no fixed target (trailing)
    bot_name: str
    order_id: str
    entry_time: datetime = field(default_factory=datetime.now)
    is_open: bool = True

    @property
    def invested(self) -> float:
        return self.qty * self.entry_price

    def current_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.qty

    def is_stop_loss_triggered(self, current_price: float) -> bool:
        return current_price <= self.stop_loss_price

    def is_target_hit(self, current_price: float) -> bool:
        if self.target_price is None:
            return False
        return current_price >= self.target_price


class RiskManager:
    """
    Centralised risk controller shared across all bots.
    All bots must check `can_trade()` before placing any order.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.total_capital: float = TOTAL_CAPITAL
        self.available_capital: float = TOTAL_CAPITAL
        self.daily_pnl: float = 0.0
        self.daily_loss_limit: float = DAILY_LOSS_LIMIT
        self.positions: Dict[str, Position] = {}   # order_id → Position
        self.halted: bool = False
        self.trade_count: int = 0
        log.info(
            f"RiskManager initialised | Capital: ₹{self.total_capital:.0f} | "
            f"Daily loss limit: ₹{self.daily_loss_limit:.0f}"
        )

    # ── Gate checks ────────────────────────────────────────────────────────────

    def can_trade(self, bot_name: str = "") -> bool:
        """Return True only if all risk conditions permit a new trade."""
        with self._lock:
            if self.halted:
                log.warning(f"[{bot_name}] Trading HALTED – daily stop loss reached.")
                return False
            if len(self.open_positions) >= MAX_OPEN_POSITIONS:
                log.info(f"[{bot_name}] Max open positions ({MAX_OPEN_POSITIONS}) reached.")
                return False
            if self.available_capital < 100:   # Minimum meaningful trade size
                log.warning(f"[{bot_name}] Insufficient available capital.")
                return False
            return True

    def max_trade_value(self) -> float:
        """Maximum INR allowed for the next trade."""
        with self._lock:
            cap_limit = self.total_capital * (MAX_TRADE_CAPITAL_PCT / 100)
            return min(cap_limit, self.available_capital)

    def calculate_position_size(self, price: float, stop_loss_pct: float = 2.0) -> int:
        """
        Calculate quantity based on risk-per-trade.
        Risk per trade = 1% of total capital.
        qty = risk_amount / (price * stop_loss_pct / 100)
        Also capped by max_trade_value.
        """
        risk_per_trade = self.total_capital * 0.01   # Risk 1% per trade
        raw_qty = int(risk_per_trade / (price * stop_loss_pct / 100))
        # Cap by max investable value
        max_qty = int(self.max_trade_value() / price)
        qty = min(raw_qty, max_qty)
        return max(qty, 1)   # At least 1 share

    # ── Position lifecycle ─────────────────────────────────────────────────────

    def register_trade(self, position: Position) -> None:
        """Called immediately after a BUY order is filled."""
        with self._lock:
            self.positions[position.order_id] = position
            self.available_capital -= position.invested
            self.trade_count += 1
            log.info(
                f"[{position.bot_name}] TRADE REGISTERED | "
                f"{position.symbol} x{position.qty} @ ₹{position.entry_price:.2f} | "
                f"SL: ₹{position.stop_loss_price:.2f} | "
                f"Available capital: ₹{self.available_capital:.2f}"
            )

    def close_trade(self, order_id: str, exit_price: float) -> float:
        """
        Called when a position is closed (profit or stop loss).
        Returns the realised PnL.
        """
        with self._lock:
            pos = self.positions.get(order_id)
            if pos is None:
                log.error(f"close_trade: order_id {order_id} not found!")
                return 0.0

            pnl = pos.current_pnl(exit_price)
            self.daily_pnl += pnl
            self.available_capital += pos.invested + pnl
            pos.is_open = False

            log.info(
                f"[{pos.bot_name}] TRADE CLOSED | {pos.symbol} | "
                f"Exit: ₹{exit_price:.2f} | PnL: ₹{pnl:+.2f} | "
                f"Daily PnL: ₹{self.daily_pnl:+.2f}"
            )

            # Check daily stop loss
            if self.daily_pnl <= -self.daily_loss_limit:
                self._trigger_halt()

            return pnl

    def _trigger_halt(self) -> None:
        """Hard-halt all bots for the day."""
        self.halted = True
        log.critical(
            f"DAILY STOP LOSS TRIGGERED | Loss: ₹{abs(self.daily_pnl):.2f} | "
            f"Limit: ₹{self.daily_loss_limit:.2f} | ALL BOTS HALTED"
        )
        notify_stop_loss_hit(abs(self.daily_pnl), self.daily_loss_limit)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @property
    def open_positions(self) -> Dict[str, Position]:
        return {oid: p for oid, p in self.positions.items() if p.is_open}

    def get_position_by_symbol(self, symbol: str) -> Optional[Position]:
        for pos in self.open_positions.values():
            if pos.symbol == symbol:
                return pos
        return None

    def daily_summary(self) -> dict:
        return {
            "total_capital": self.total_capital,
            "available_capital": self.available_capital,
            "daily_pnl": self.daily_pnl,
            "trade_count": self.trade_count,
            "open_positions": len(self.open_positions),
            "halted": self.halted,
        }


# Module-level singleton shared across all bots
_risk_manager: RiskManager | None = None


def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
