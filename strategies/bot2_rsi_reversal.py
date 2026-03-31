"""
Bot 2 – RSI Mean Reversion Strategy.

Logic:
  Entry  : RSI drops below oversold threshold (35) on a stock that is
            still in an overall uptrend (price > 50 EMA).
            Wait for RSI to turn back up (previous candle RSI < current RSI)
            — this confirms the reversal rather than catching a falling knife.
            Bollinger lower band must have been touched on the dip candle
            (dual-confirmation reduces false signals significantly).
            Bounce candle volume ≥ 1.2× 20-bar average (confirms buyers
            stepped in, not just a dead-cat bounce on low volume).
  Exit   :
    • Hard stop loss : Entry price × (1 - HARD_STOP_LOSS_PCT/100)  [10% below]
    • NO fixed target: profits are uncapped — let the recovery run fully
    • Trailing SL    : trails at (current_price - TRAILING_ATR_MULTIPLIER × ATR)
                       ratchets up continuously, exits only when price reverses
    • Force close    : 15:15 IST

Instruments: banking / financial stocks (tend to mean-revert well).
Candle interval: 15 minutes (less noise than 5m for RSI).
"""
from datetime import datetime

import pytz

from config.settings import (
    RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, SQUARE_OFF_TIME, TIMEZONE,
    HARD_STOP_LOSS_PCT, TRAILING_ATR_MULTIPLIER,
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
        df = self.market_data.add_bollinger(df)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # Core conditions (unchanged)
        uptrend       = last["close"] > last["ema_50"]
        rsi_was_below = prev["rsi"] < RSI_OVERSOLD
        rsi_turning   = last["rsi"] > prev["rsi"]   # RSI starting to recover

        # ADDED: Bollinger lower-band touch on the dip candle (dual confirmation)
        bb_lower_col = "BBL_20_2.0"
        bb_touched = (
            bb_lower_col in df.columns and
            prev["low"] <= prev[bb_lower_col]
        )

        # ADDED: Volume on the bounce candle must be above average
        avg_vol  = df["volume"].rolling(20).mean().iloc[-1]
        vol_ok   = last["volume"] >= avg_vol * 1.2 if avg_vol > 0 else False

        if not (uptrend and rsi_was_below and rsi_turning and bb_touched and vol_ok):
            return

        # Hard SL 10%, no fixed target — trailing SL exits the trade
        entry_price  = last["close"]
        stop_loss_px = round(entry_price * (1 - HARD_STOP_LOSS_PCT / 100), 2)
        qty          = self.risk.calculate_position_size(entry_price, HARD_STOP_LOSS_PCT)

        if qty < 1:
            return

        self.log.info(
            f"SIGNAL | {symbol} | RSI reversal @ {last['rsi']:.1f} | BB touch✓ | Vol✓ | "
            f"Entry: ₹{entry_price:.2f} | Hard SL: ₹{stop_loss_px:.2f} (-10%) | "
            f"Target: UNCAPPED (trailing SL) | Qty: {qty}"
        )
        self._place_buy(symbol, qty, entry_price, stop_loss_px, target=None)

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

                # Hard stop loss
                if pos.is_stop_loss_triggered(ltp):
                    self._place_sell(pos, ltp, reason="STOP_LOSS")
                    continue

                # No fixed target — trailing SL lets the recovery run fully
                df = self.market_data.get_candles(pos.symbol, interval="15minute", lookback_days=1)
                if not df.empty:
                    df = self.market_data.add_atr(df)
                    atr = df.iloc[-1]["atr"]

                    # Ratchet trailing SL up as price rises; never move it down
                    trail_sl = round(ltp - TRAILING_ATR_MULTIPLIER * atr, 2)
                    if trail_sl > pos.stop_loss_price:
                        self.log.info(
                            f"Trailing SL | {pos.symbol}: "
                            f"₹{pos.stop_loss_price:.2f} → ₹{trail_sl:.2f} "
                            f"(unrealised P&L: ₹{(ltp - pos.entry_price) * pos.qty:+.0f})"
                        )
                        pos.stop_loss_price = trail_sl

            except Exception as e:
                self.log.error(f"Error managing {pos.symbol}: {e}")

    # ── Order helpers ──────────────────────────────────────────────────────────

    def _place_buy(self, symbol: str, qty: int, price: float,
                   sl: float, target) -> None:
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
