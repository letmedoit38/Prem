"""
Bot 2 – RSI Mean Reversion Strategy.

Logic:
  Entry  : RSI drops below oversold threshold (35) on a stock that is
            still in an overall uptrend (price > 50 EMA).
            Wait for RSI to turn back up (previous candle RSI < current RSI)
            — this confirms the reversal rather than catching a falling knife.
  Exit   :
    • Stop loss   : Entry price - (1.5 × ATR)
    • Target      : RSI reaches 60 OR price + (2 × ATR)
    • Trailing SL : trails at entry_price - ATR once breakeven is cleared
    • Force close : 15:15 IST

Instruments: banking / financial stocks (tend to mean-revert well).
Candle interval: 15 minutes (less noise than 5m for RSI).
"""
from datetime import datetime

import pytz

from config.settings import (
    RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, SQUARE_OFF_TIME, TIMEZONE
)
from core.risk_manager import Position, get_risk_manager
from data.market_data import MarketData
from strategies.base_strategy import BaseStrategy
from utils.logger import log_trade
from utils.notifier import notify_trade


class RSIReversalBot(BaseStrategy):
    """Bot 2: RSI Mean Reversion."""

    def __init__(self, kite, symbols: list):
        super().__init__(
            name="Bot2_RSI_Reversal",
            symbols=symbols,
            scan_interval_seconds=90,   # 15m candles, re-check every 90s
        )
        self.kite = kite
        self.market_data = MarketData(kite)

    # ── Entry scan ─────────────────────────────────────────────────────────────

    def scan(self) -> None:
        if not self.risk.can_trade(self.name):
            return

        for symbol in self.symbols:
            if self.risk.get_position_by_symbol(symbol):
                continue
            try:
                self._evaluate_entry(symbol)
            except Exception as e:
                self.log.error(f"Error evaluating {symbol}: {e}")

    def _evaluate_entry(self, symbol: str) -> None:
        df = self.market_data.get_candles(symbol, interval="15minute", lookback_days=5)
        if df.empty or len(df) < 60:
            return

        df = self.market_data.add_rsi(df, RSI_PERIOD)
        df = self.market_data.add_ema(df, [50])
        df = self.market_data.add_atr(df)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Conditions
        uptrend       = last["close"] > last["ema_50"]
        rsi_was_below = prev["rsi"] < RSI_OVERSOLD
        rsi_turning   = last["rsi"] > prev["rsi"]    # RSI starting to recover

        if not (uptrend and rsi_was_below and rsi_turning):
            return

        entry_price  = last["close"]
        atr          = last["atr"]
        stop_loss_px = round(entry_price - 1.5 * atr, 2)
        target_px    = round(entry_price + 2.0 * atr, 2)
        sl_pct       = ((entry_price - stop_loss_px) / entry_price) * 100
        qty          = self.risk.calculate_position_size(entry_price, sl_pct)

        if qty < 1:
            return

        self.log.info(
            f"SIGNAL | {symbol} | RSI reversal @ {last['rsi']:.1f} | "
            f"Entry: ₹{entry_price:.2f} | SL: ₹{stop_loss_px:.2f} | "
            f"Target: ₹{target_px:.2f} | Qty: {qty}"
        )
        self._place_buy(symbol, qty, entry_price, stop_loss_px, target_px)

    # ── Position management ────────────────────────────────────────────────────

    def manage_positions(self) -> None:
        ist = pytz.timezone(TIMEZONE)
        now_time = datetime.now(ist).strftime("%H:%M")

        for order_id, pos in list(self.risk.open_positions.items()):
            if pos.bot_name != self.name:
                continue
            try:
                ltp = self.market_data.get_ltp([pos.symbol]).get(pos.symbol, 0)
                if ltp == 0:
                    continue

                # Force square-off
                if now_time >= SQUARE_OFF_TIME:
                    self._place_sell(pos, ltp, reason="EOD_SQUAREOFF")
                    continue

                # Stop loss
                if pos.is_stop_loss_triggered(ltp):
                    self._place_sell(pos, ltp, reason="STOP_LOSS")
                    continue

                # RSI target: fetch latest RSI
                df = self.market_data.get_candles(pos.symbol, interval="15minute", lookback_days=1)
                if not df.empty:
                    df = self.market_data.add_rsi(df, RSI_PERIOD)
                    df = self.market_data.add_atr(df)
                    current_rsi = df.iloc[-1]["rsi"]
                    atr = df.iloc[-1]["atr"]

                    # Exit when RSI reaches overbought territory
                    if current_rsi >= RSI_OVERBOUGHT:
                        self.log.info(
                            f"RSI overbought ({current_rsi:.1f}) | exiting {pos.symbol}"
                        )
                        self._place_sell(pos, ltp, reason="RSI_TARGET")
                        continue

                    # Price target
                    if pos.is_target_hit(ltp):
                        self._place_sell(pos, ltp, reason="PRICE_TARGET")
                        continue

                    # Trailing SL once past breakeven
                    if ltp > pos.entry_price:
                        trail_sl = round(ltp - 1.0 * atr, 2)
                        if trail_sl > pos.stop_loss_price:
                            pos.stop_loss_price = trail_sl
                            self.log.debug(
                                f"Trailing SL updated for {pos.symbol}: ₹{trail_sl:.2f}"
                            )

            except Exception as e:
                self.log.error(f"Error managing {pos.symbol}: {e}")

    # ── Order helpers ──────────────────────────────────────────────────────────

    def _place_buy(self, symbol: str, qty: int, price: float,
                   sl: float, target: float) -> None:
        exchange, tradingsymbol = symbol.split(":")
        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=self.kite.TRANSACTION_TYPE_BUY,
                quantity=qty,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            pos = Position(
                symbol=symbol, qty=qty, entry_price=price,
                stop_loss_price=sl, target_price=target,
                bot_name=self.name, order_id=str(order_id),
            )
            self.risk.register_trade(pos)
            notify_trade(self.name, "BUY", symbol, qty, price)
            log_trade("BUY", symbol, qty, price, str(order_id), self.name)
        except Exception as e:
            self.log.error(f"BUY order failed for {symbol}: {e}")

    def _place_sell(self, pos: Position, price: float, reason: str) -> None:
        exchange, tradingsymbol = pos.symbol.split(":")
        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                quantity=pos.qty,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            pnl = self.risk.close_trade(pos.order_id, price)
            notify_trade(self.name, "SELL", pos.symbol, pos.qty, price, pnl)
            log_trade("SELL", pos.symbol, pos.qty, price, str(order_id), self.name, pnl)
            self.log.info(
                f"SELL [{reason}] {pos.symbol} x{pos.qty} @ ₹{price:.2f} | "
                f"PnL: ₹{pnl:+.2f}"
            )
        except Exception as e:
            self.log.error(f"SELL order failed for {pos.symbol}: {e}")
