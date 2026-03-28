"""
Order Manager – utilities for checking order/position status via Kite API.

Provides:
  - Sync open positions from Zerodha (reconciliation on startup)
  - Check order fill status
  - Emergency square-off: close ALL open MIS positions
"""
from typing import List, Dict, Any

from kiteconnect import KiteConnect

from utils.logger import setup_logger

log = setup_logger("order_manager")


class OrderManager:
    """Thin wrapper around KiteConnect order/position APIs."""

    def __init__(self, kite: KiteConnect):
        self.kite = kite

    # ── Position reconciliation ────────────────────────────────────────────────

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """
        Return list of open intraday (MIS/CNC day) positions from Zerodha.
        Used to reconcile on startup in case of crash recovery.
        """
        try:
            positions = self.kite.positions()
            day_positions = positions.get("day", [])
            open_pos = [p for p in day_positions if p["quantity"] != 0]
            log.info(f"Zerodha reports {len(open_pos)} open position(s).")
            return open_pos
        except Exception as e:
            log.error(f"Failed to fetch positions: {e}")
            return []

    def get_order_status(self, order_id: str) -> str:
        """Return the status string of an order ('COMPLETE', 'REJECTED', etc.)."""
        try:
            orders = self.kite.orders()
            for o in orders:
                if str(o["order_id"]) == str(order_id):
                    return o["status"]
            return "NOT_FOUND"
        except Exception as e:
            log.error(f"Failed to fetch order status: {e}")
            return "ERROR"

    def get_average_price(self, order_id: str) -> float:
        """Return the average fill price of a completed order."""
        try:
            orders = self.kite.orders()
            for o in orders:
                if str(o["order_id"]) == str(order_id):
                    return float(o.get("average_price", 0))
            return 0.0
        except Exception as e:
            log.error(f"Failed to fetch fill price: {e}")
            return 0.0

    # ── Emergency square-off ──────────────────────────────────────────────────

    def emergency_square_off(self) -> None:
        """
        Immediately close ALL open MIS positions.
        Called when daily stop loss is triggered or on manual halt.
        """
        log.warning("EMERGENCY SQUARE-OFF initiated.")
        open_positions = self.get_open_positions()
        for pos in open_positions:
            qty = pos["quantity"]
            if qty == 0:
                continue
            # If qty > 0 we're long → SELL; if qty < 0 we're short → BUY
            txn = (self.kite.TRANSACTION_TYPE_SELL if qty > 0
                   else self.kite.TRANSACTION_TYPE_BUY)
            try:
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=pos["exchange"],
                    tradingsymbol=pos["tradingsymbol"],
                    transaction_type=txn,
                    quantity=abs(qty),
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                )
                log.info(
                    f"Square-off order placed: {pos['tradingsymbol']} x{abs(qty)} | "
                    f"order_id={order_id}"
                )
            except Exception as e:
                log.error(
                    f"Square-off FAILED for {pos['tradingsymbol']}: {e}"
                )
        log.info("Emergency square-off completed.")

    # ── Daily summary ──────────────────────────────────────────────────────────

    def get_todays_pnl(self) -> float:
        """
        Calculate realised + unrealised PnL for today from Zerodha directly.
        Useful as a cross-check against the in-memory RiskManager figure.
        """
        try:
            positions = self.kite.positions()
            day_pos = positions.get("day", [])
            total_pnl = sum(p.get("pnl", 0) for p in day_pos)
            log.info(f"Zerodha reports today's PnL: ₹{total_pnl:+.2f}")
            return total_pnl
        except Exception as e:
            log.error(f"Failed to fetch PnL: {e}")
            return 0.0
