"""
Bot 4 – Multi-Timeframe Confluence (MTC) Strategy.

PHILOSOPHY: High-probability trades occur ONLY when multiple independent
signals align across timeframes. A single indicator generates noise;
five indicators pointing the same direction is a high-conviction setup.

THE 5 PILLARS — ALL must align before entering a trade:

  Pillar 1 — HTF Trend (15m):
              EMA-20 > EMA-50 on the 15-minute chart  AND  price > EMA-20
              → We are in a confirmed uptrend; trade WITH institutional bias

  Pillar 2 — MACD Crossover (5m):
              MACD line crosses ABOVE signal line on the current 5m candle
              → Short-term momentum is shifting in our favour

  Pillar 3 — RSI Momentum Zone (5m):
              RSI between 50–70 (not overbought, already in momentum)
              → Confirms buyers are in control but room remains to run

  Pillar 4 — Volume Surge:
              Current bar volume ≥ 1.5× the 20-bar rolling average
              → Institutional players are participating (no low-volume fakeouts)

  Pillar 5 — Session Filter:
              Trade ONLY in 09:30–11:30 IST  OR  14:00–15:00 IST
              → Avoids choppy low-volume lunch hours (11:30–13:00)
              → Morning session has strongest directional momentum
              → Afternoon session has second directional impulse

SMART 2-STAGE EXIT:
  Stage 1: When LTP reaches Entry + 1.0×ATR → SELL 50% qty (lock partial profit)
           SL immediately moves to breakeven (entry price)
  Stage 2: Trail remaining 50% with a 2×ATR trailing stop
  Hard SL:  Entry - 1.5×ATR (absolute maximum loss per trade)
  EOD:      Force close ALL positions at 15:15 IST

RISK SIZING:
  Risk per trade: 1% of total capital
  SL distance:    1.5×ATR
  Max position:   40% of total capital cap

Instruments: BAJFINANCE, AXISBANK, WIPRO — non-overlapping with other bots,
             high-momentum, highly liquid NSE stocks.
Candle interval: 5 minutes (entry timing)
HTF interval:    15 minutes (trend filter)
"""

from datetime import datetime, time as dt_time

import pytz

from config.settings import (
    MTC_BOT_SYMBOLS, MTC_HTF_EMA_FAST, MTC_HTF_EMA_SLOW,
    MTC_RSI_LOW, MTC_RSI_HIGH, MTC_VOLUME_MULTIPLIER,
    MTC_PARTIAL_EXIT_ATR, MTC_STOP_LOSS_ATR, MTC_TARGET_ATR,
    SQUARE_OFF_TIME, TIMEZONE,
)
from core.risk_manager import Position, get_risk_manager
from data.market_data import MarketData
from strategies.base_strategy import BaseStrategy
from utils.logger import log_trade
from utils.notifier import notify_trade

# MACD column names produced by pandas-ta default parameters (fast=12, slow=26, signal=9)
_MACD_LINE   = "MACD_12_26_9"
_MACD_SIGNAL = "MACDs_12_26_9"

# Trading session windows (IST) — only trade during these high-probability periods
_MORNING_START   = dt_time(9, 30)
_MORNING_END     = dt_time(11, 30)
_AFTERNOON_START = dt_time(14, 0)
_AFTERNOON_END   = dt_time(15, 0)


class MTCBot(BaseStrategy):
    """
    Bot 4: Multi-Timeframe Confluence.

    Waits for all 5 pillars to align before entering, then uses a 2-stage
    exit to maximise winners while protecting capital on losers.
    """

    def __init__(self, kite, symbols: list):
        super().__init__(
            name="Bot4_MTC",
            symbols=symbols,
            scan_interval_seconds=60,
        )
        self.kite = kite
        self.market_data = MarketData(kite)
        # Tracks whether Stage-1 partial exit has been executed per position
        self._partial_done: dict = {}   # order_id → bool

    # ── Session filter ─────────────────────────────────────────────────────────

    def _in_valid_session(self) -> bool:
        """Return True only during the two high-probability session windows."""
        ist = pytz.timezone(TIMEZONE)
        now_time = datetime.now(ist).time()
        in_morning   = _MORNING_START <= now_time <= _MORNING_END
        in_afternoon = _AFTERNOON_START <= now_time <= _AFTERNOON_END
        return in_morning or in_afternoon

    # ── Entry scan ─────────────────────────────────────────────────────────────

    def scan(self) -> None:
        if not self.risk.can_trade(self.name):
            return
        if not self._in_valid_session():
            return

        for symbol in self.symbols:
            if self.risk.get_position_by_symbol(symbol):
                continue
            try:
                self._evaluate_entry(symbol)
            except Exception as e:
                self.log.error(f"Error evaluating {symbol}: {e}")

    def _evaluate_entry(self, symbol: str) -> None:
        # ── Pillar 1: HTF Trend confirmation (15-minute chart) ─────────────────
        df_15m = self.market_data.get_candles(symbol, interval="15minute", lookback_days=5)
        if df_15m.empty or len(df_15m) < MTC_HTF_EMA_SLOW + 5:
            return

        df_15m = self.market_data.add_ema(df_15m, [MTC_HTF_EMA_FAST, MTC_HTF_EMA_SLOW])
        htf = df_15m.iloc[-1]

        # Bullish structure: fast EMA above slow EMA and price above fast EMA
        htf_bullish = (
            htf["close"] > htf[f"ema_{MTC_HTF_EMA_FAST}"] and
            htf[f"ema_{MTC_HTF_EMA_FAST}"] > htf[f"ema_{MTC_HTF_EMA_SLOW}"]
        )

        if not htf_bullish:
            return  # Trading against the 15m trend — skip

        # ── Pillars 2, 3, 4: MACD + RSI + Volume on 5-minute chart ───────────
        df_5m = self.market_data.get_candles(symbol, interval="5minute", lookback_days=3)
        if df_5m.empty or len(df_5m) < 35:
            return

        df_5m = self.market_data.add_macd(df_5m)
        df_5m = self.market_data.add_rsi(df_5m)
        df_5m = self.market_data.add_atr(df_5m)

        last = df_5m.iloc[-1]
        prev = df_5m.iloc[-2]

        # Pillar 2: MACD crossover — MACD line just crossed above signal line
        if _MACD_LINE not in df_5m.columns or _MACD_SIGNAL not in df_5m.columns:
            self.log.warning(f"MACD columns not found for {symbol}; skipping.")
            return

        macd_cross_up = (
            prev[_MACD_LINE] <= prev[_MACD_SIGNAL] and
            last[_MACD_LINE] >  last[_MACD_SIGNAL]
        )
        if not macd_cross_up:
            return  # No fresh momentum crossover this candle

        # Pillar 3: RSI is in the momentum zone (50–70)
        rsi_ok = MTC_RSI_LOW <= last["rsi"] <= MTC_RSI_HIGH
        if not rsi_ok:
            return  # Either not enough momentum (<50) or overbought (>70)

        # Pillar 4: Volume surge — current bar must have institutional-grade volume
        avg_vol = df_5m["volume"].rolling(20).mean().iloc[-1]
        if avg_vol == 0:
            return
        vol_surge = last["volume"] >= avg_vol * MTC_VOLUME_MULTIPLIER
        if not vol_surge:
            return  # Low-volume move — likely retail noise, skip

        # ── All 5 pillars confirmed → calculate sizing and enter ───────────────
        entry_price  = last["close"]
        atr          = last["atr"]
        stop_loss_px = round(entry_price - MTC_STOP_LOSS_ATR * atr, 2)
        target_px    = round(entry_price + MTC_TARGET_ATR  * atr, 2)
        sl_pct       = ((entry_price - stop_loss_px) / entry_price) * 100
        qty          = self.risk.calculate_position_size(entry_price, sl_pct)

        if qty < 1:
            return

        self.log.info(
            f"MTC SIGNAL | {symbol} | HTF✓ MACD✓ RSI={last['rsi']:.1f}✓ "
            f"Vol={last['volume'] / avg_vol:.1f}x✓ | "
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

                # Force square-off at EOD
                if now_time >= SQUARE_OFF_TIME:
                    self.log.info(f"EOD square-off: {pos.symbol}")
                    self._place_sell(pos, ltp, reason="EOD_SQUAREOFF")
                    self._partial_done.pop(order_id, None)
                    continue

                # Hard stop loss (Stage 0)
                if pos.is_stop_loss_triggered(ltp):
                    self.log.info(f"Hard SL hit: {pos.symbol} @ ₹{ltp:.2f}")
                    self._place_sell(pos, ltp, reason="STOP_LOSS")
                    self._partial_done.pop(order_id, None)
                    continue

                # Full target hit
                if pos.is_target_hit(ltp):
                    self.log.info(f"Full target hit: {pos.symbol} @ ₹{ltp:.2f}")
                    self._place_sell(pos, ltp, reason="FULL_TARGET")
                    self._partial_done.pop(order_id, None)
                    continue

                # Fetch current ATR for dynamic management
                df = self.market_data.get_candles(pos.symbol, interval="5minute", lookback_days=1)
                if df.empty:
                    continue
                df = self.market_data.add_atr(df)
                atr = df.iloc[-1]["atr"]

                # Stage 1: Partial exit at 1×ATR profit (50% of position)
                partial_done = self._partial_done.get(order_id, False)
                partial_target = pos.entry_price + MTC_PARTIAL_EXIT_ATR * atr

                if not partial_done and ltp >= partial_target and pos.qty >= 2:
                    partial_qty = pos.qty // 2
                    self.log.info(
                        f"PARTIAL EXIT (Stage 1) | {pos.symbol} | "
                        f"{partial_qty} shares @ ₹{ltp:.2f} | SL → breakeven"
                    )
                    self._place_partial_sell(pos, partial_qty, ltp)
                    self._partial_done[order_id] = True
                    # Move SL to breakeven — no risk remains on this trade
                    pos.stop_loss_price = pos.entry_price
                    continue

                # Stage 2: Trail remaining position with 2×ATR trailing stop
                trail_sl = round(ltp - 2.0 * atr, 2)
                if trail_sl > pos.stop_loss_price:
                    self.log.debug(
                        f"Trail SL | {pos.symbol}: "
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
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            pos = Position(
                symbol=symbol, qty=qty, entry_price=price,
                stop_loss_price=sl, target_price=target,
                bot_name=self.name, order_id=str(order_id),
            )
            self.risk.register_trade(pos)
            self._partial_done[str(order_id)] = False
            notify_trade(self.name, "BUY", symbol, qty, price)
            log_trade("BUY", symbol, qty, price, str(order_id), self.name)
            self.log.info(f"BUY placed: {symbol} x{qty} @ ₹{price:.2f} | order_id={order_id}")
        except Exception as e:
            self.log.error(f"BUY order failed for {symbol}: {e}")

    def _place_partial_sell(self, pos: Position, qty: int, price: float) -> None:
        """
        Close a portion of the position (Stage-1 exit).
        Updates risk manager state directly (thread-safe via lock) since
        RiskManager.close_trade() expects full position closure.
        """
        exchange, tradingsymbol = pos.symbol.split(":")
        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=self.kite.TRANSACTION_TYPE_SELL,
                quantity=qty,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
            )
            partial_pnl = (price - pos.entry_price) * qty
            # Thread-safe capital and PnL update for the partial exit
            with self.risk._lock:
                self.risk.daily_pnl      += partial_pnl
                self.risk.available_capital += qty * pos.entry_price + partial_pnl
                pos.qty -= qty   # Reduce remaining qty (close_trade will handle the rest)

            notify_trade(self.name, "PARTIAL_SELL", pos.symbol, qty, price, partial_pnl)
            log_trade("PARTIAL_SELL", pos.symbol, qty, price, str(order_id), self.name, partial_pnl)
            self.log.info(
                f"PARTIAL SELL | {pos.symbol} x{qty} @ ₹{price:.2f} | "
                f"Partial PnL: ₹{partial_pnl:+.2f} | Remaining qty: {pos.qty}"
            )
        except Exception as e:
            self.log.error(f"Partial sell failed for {pos.symbol}: {e}")

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
                f"SELL [{reason}] | {pos.symbol} x{pos.qty} @ ₹{price:.2f} | "
                f"PnL: ₹{pnl:+.2f}"
            )
        except Exception as e:
            self.log.error(f"SELL order failed for {pos.symbol}: {e}")
