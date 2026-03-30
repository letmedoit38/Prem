"""
Bot 3 – VWAP Scalping Strategy.

Logic:
  VWAP (Volume Weighted Average Price) acts as a dynamic support/resistance.
  Institutional traders often defend VWAP, making it a reliable mean-reversion
  anchor intraday.

  Entry  : Price dips BELOW VWAP by ≥ VWAP_DEVIATION_PCT (0.5%) while
            momentum is returning (current candle close > previous candle close)
            and volume on the dip candle > average volume (confirms buyers stepped in).

  Exit   :
    • Target      : Price returns to VWAP (quick scalp)
    • Stop loss   : Entry - 0.75 × ATR (tight stop – scalping)
    • Max hold    : 15 candles (15m on 1m chart = no overnight risk)
    • Force close : 15:15 IST

Instruments: Nifty 50 ETF (NIFTYBEES) and BankNifty ETF (BANKBEES)
             — extremely liquid, tight spreads, suitable for ₹5k capital.
Candle interval: 1 minute (scalp timeframe).
"""
from datetime import datetime

import pandas as pd
import pytz

from config.settings import VWAP_DEVIATION_PCT, SQUARE_OFF_TIME, TIMEZONE
from core.risk_manager import Position, get_risk_manager
from data.market_data import MarketData
from strategies.base_strategy import BaseStrategy
from utils.logger import log_trade
from utils.notifier import notify_trade

# ETFs that track the indices – tradable in cash segment, no F&O margin needed
VWAP_INSTRUMENTS = {
    "NSE:NIFTYBEES": "NSE:NIFTYBEES",   # Nifty 50 ETF
    "NSE:BANKBEES":  "NSE:BANKBEES",    # BankNifty ETF
}

MAX_CANDLES_HOLD = 15   # Force exit after 15 × 1m = 15 minutes


class VWAPScalperBot(BaseStrategy):
    """Bot 3: VWAP Scalper."""

    def __init__(self, kite, symbols: list):
        super().__init__(
            name="Bot3_VWAP_Scalper",
            symbols=symbols,
            scan_interval_seconds=30,   # 1m candles – scan every 30s
        )
        self.kite = kite
        self.market_data = MarketData(kite)
        self._candles_held: dict = {}   # order_id → candle count since entry

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
        df = self.market_data.get_candles(symbol, interval="minute", lookback_days=2)
        if df.empty or len(df) < 30:
            return

        df = self.market_data.add_vwap(df)
        df = self.market_data.add_atr(df, period=10)

        # Use only today's candles for VWAP relevance
        ist = pytz.timezone(TIMEZONE)
        today = datetime.now(ist).date()
        df.index = pd.to_datetime(df.index)
        # Handle both tz-aware and tz-naive DatetimeIndex
        naive_index = (df.index.tz_convert(None) if df.index.tz is not None
                       else df.index)
        df = df[naive_index.normalize() == pd.Timestamp(today)]

        if len(df) < 10:
            return

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        avg_vol = df["volume"].rolling(20).mean().iloc[-1]

        vwap = last["vwap"]
        if pd.isna(vwap) or vwap == 0:
            return

        price = last["close"]
        deviation_pct = ((vwap - price) / vwap) * 100   # positive = price below VWAP

        # Conditions
        below_vwap       = deviation_pct >= VWAP_DEVIATION_PCT
        momentum_return  = last["close"] > prev["close"]     # price bouncing back
        volume_spike     = last["volume"] >= avg_vol * 0.8   # decent volume

        if not (below_vwap and momentum_return and volume_spike):
            return

        entry_price  = price
        atr          = last["atr"]
        stop_loss_px = round(entry_price - 0.75 * atr, 2)
        target_px    = round(vwap, 2)                         # target = VWAP
        sl_pct       = ((entry_price - stop_loss_px) / entry_price) * 100
        qty          = self.risk.calculate_position_size(entry_price, sl_pct)

        if qty < 1:
            return

        self.log.info(
            f"SIGNAL | {symbol} | VWAP deviation={deviation_pct:.2f}% | "
            f"Entry: ₹{entry_price:.2f} | VWAP: ₹{vwap:.2f} | "
            f"SL: ₹{stop_loss_px:.2f} | Qty: {qty}"
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

                # Increment candle counter (approximate – called every 30s)
                self._candles_held[order_id] = self._candles_held.get(order_id, 0) + 1
                candles_held = self._candles_held[order_id]

                # Force square-off
                if now_time >= SQUARE_OFF_TIME:
                    self._place_sell(pos, ltp, reason="EOD_SQUAREOFF")
                    continue

                # Stop loss
                if pos.is_stop_loss_triggered(ltp):
                    self._place_sell(pos, ltp, reason="STOP_LOSS")
                    del self._candles_held[order_id]
                    continue

                # Target (price returned to VWAP)
                if pos.is_target_hit(ltp):
                    self._place_sell(pos, ltp, reason="VWAP_TARGET")
                    del self._candles_held[order_id]
                    continue

                # Time-based exit (max hold candles × 2 checks per candle)
                if candles_held >= MAX_CANDLES_HOLD * 2:
                    self.log.info(f"Max hold time reached for {pos.symbol}")
                    self._place_sell(pos, ltp, reason="MAX_HOLD")
                    del self._candles_held[order_id]
                    continue

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
            self._candles_held[str(order_id)] = 0
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
