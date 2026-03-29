"""
Bot 1 – EMA Crossover Momentum Strategy.

Logic:
  Entry  : Fast EMA (9) crosses ABOVE slow EMA (21) while price is
            above the trend EMA (50). RSI between 45–65. Volume ≥ 1.2×
            20-bar average (confirms institutional participation).
            Session filter: skip the choppy 11:30–13:00 lunch window.
  Exit   :
    • Stop loss   : Entry price - (1.5 × ATR)
    • Target      : Entry price + (2.5 × ATR)  [risk:reward ≈ 1:1.67]
    • Trailing SL : Once price moves 1×ATR in favour, SL trails at
                    current_price - 1×ATR
    • Force close : 15:15 IST regardless of position

Instruments: highly-liquid large-cap NSE stocks.
Candle interval: 5 minutes.
"""
from datetime import datetime, time as dt_time

import pytz

from config.settings import EMA_FAST, EMA_SLOW, EMA_TREND, SQUARE_OFF_TIME, TIMEZONE
from core.risk_manager import Position, get_risk_manager
from data.market_data import MarketData
from strategies.base_strategy import BaseStrategy
from utils.logger import log_trade
from utils.notifier import notify_trade


class EMACrossoverBot(BaseStrategy):
    """Bot 1: EMA Crossover Momentum."""

    def __init__(self, kite, symbols: list):
        super().__init__(
            name="Bot1_EMA_Crossover",
            symbols=symbols,
            scan_interval_seconds=60,   # Re-scan every 1 minute
        )
        self.kite = kite
        self.market_data = MarketData(kite)

    # ── Entry scan ─────────────────────────────────────────────────────────────

    def _in_valid_session(self) -> bool:
        """Skip the choppy 11:30–13:00 lunch window."""
        ist = pytz.timezone(TIMEZONE)
        now_time = datetime.now(ist).time()
        return not (dt_time(11, 30) <= now_time <= dt_time(13, 0))

    def scan(self) -> None:
        if not self.risk.can_trade(self.name):
            return
        if not self._in_valid_session():
            return

        for symbol in self.symbols:
            # Skip if we already hold a position in this symbol
            if self.risk.get_position_by_symbol(symbol):
                continue

            try:
                self._evaluate_entry(symbol)
            except Exception as e:
                self.log.error(f"Error evaluating {symbol}: {e}")

    def _evaluate_entry(self, symbol: str) -> None:
        df = self.market_data.get_candles(symbol, interval="5minute", lookback_days=3)
        if df.empty or len(df) < EMA_TREND + 5:
            return

        df = self.market_data.add_ema(df, [EMA_FAST, EMA_SLOW, EMA_TREND])
        df = self.market_data.add_rsi(df)
        df = self.market_data.add_atr(df)

        last  = df.iloc[-1]
        prev  = df.iloc[-2]

        # Golden cross: fast crossed above slow THIS candle
        crossed_up = (prev[f"ema_{EMA_FAST}"] <= prev[f"ema_{EMA_SLOW}"]) and \
                     (last[f"ema_{EMA_FAST}"] >  last[f"ema_{EMA_SLOW}"])

        above_trend = last["close"] > last[f"ema_{EMA_TREND}"]
        rsi_ok      = 45 < last["rsi"] < 65   # Tightened: was 40–65
        atr         = last["atr"]

        # Volume confirmation: require 1.2× 20-bar average (was no check)
        avg_vol  = df["volume"].rolling(20).mean().iloc[-1]
        vol_ok   = last["volume"] >= avg_vol * 1.2 if avg_vol > 0 else False

        if not (crossed_up and above_trend and rsi_ok and vol_ok):
            return

        # Size the position
        entry_price    = last["close"]
        stop_loss_px   = round(entry_price - 1.5 * atr, 2)
        target_px      = round(entry_price + 2.5 * atr, 2)
        sl_pct         = ((entry_price - stop_loss_px) / entry_price) * 100
        qty            = self.risk.calculate_position_size(entry_price, sl_pct)

        if qty < 1:
            return

        self.log.info(
            f"SIGNAL | {symbol} | EMA cross-up | "
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

                # Force square-off before market close
                if now_time >= SQUARE_OFF_TIME:
                    self.log.info(f"Square-off time reached. Closing {pos.symbol}.")
                    self._place_sell(pos, ltp, reason="EOD_SQUAREOFF")
                    continue

                # Stop loss
                if pos.is_stop_loss_triggered(ltp):
                    self.log.info(f"SL triggered for {pos.symbol} @ ₹{ltp:.2f}")
                    self._place_sell(pos, ltp, reason="STOP_LOSS")
                    continue

                # Target hit
                if pos.is_target_hit(ltp):
                    self.log.info(f"Target hit for {pos.symbol} @ ₹{ltp:.2f}")
                    self._place_sell(pos, ltp, reason="TARGET")
                    continue

                # Trailing stop: once in profit by 1×ATR, trail SL up
                df = self.market_data.get_candles(pos.symbol, interval="5minute", lookback_days=1)
                if not df.empty:
                    df = self.market_data.add_atr(df)
                    atr = df.iloc[-1]["atr"]
                    trail_sl = round(ltp - 1.0 * atr, 2)
                    if trail_sl > pos.stop_loss_price:
                        self.log.debug(
                            f"Trailing SL for {pos.symbol}: "
                            f"₹{pos.stop_loss_price:.2f} → ₹{trail_sl:.2f}"
                        )
                        pos.stop_loss_price = trail_sl

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
                product=self.kite.PRODUCT_MIS,     # Intraday
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
            self.log.info(f"BUY order placed: {symbol} x{qty} | order_id={order_id}")
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
