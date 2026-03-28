"""
Market Data Module.

Fetches:
  • Historical OHLCV candles (for indicator calculation)
  • Real-time LTP (Last Traded Price) via KiteConnect
  • Instrument token lookup

Uses KiteConnect historical data API (requires paid subscription or
falls back to quote endpoint for intraday tick data).
"""
import time
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
import pandas_ta as ta
from kiteconnect import KiteConnect

from utils.logger import setup_logger

log = setup_logger("market_data")


class MarketData:
    """
    Wrapper around KiteConnect data APIs.
    All bots share a single MarketData instance.
    """

    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self._instrument_cache: dict = {}

    # ── Instrument token ──────────────────────────────────────────────────────

    def get_instrument_token(self, tradingsymbol: str, exchange: str = "NSE") -> int:
        """Return the numeric instrument token for a symbol."""
        key = f"{exchange}:{tradingsymbol}"
        if key in self._instrument_cache:
            return self._instrument_cache[key]

        instruments = self.kite.instruments(exchange)
        for inst in instruments:
            if inst["tradingsymbol"] == tradingsymbol:
                self._instrument_cache[key] = inst["instrument_token"]
                return inst["instrument_token"]
        raise ValueError(f"Instrument not found: {key}")

    # ── Historical OHLCV ──────────────────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,             # e.g. "NSE:RELIANCE"
        interval: str = "5minute",
        lookback_days: int = 5,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles and return as DataFrame.
        Columns: date, open, high, low, close, volume
        """
        exchange, tradingsymbol = symbol.split(":")
        token = self.get_instrument_token(tradingsymbol, exchange)

        to_date   = datetime.now()
        from_date = to_date - timedelta(days=lookback_days)

        try:
            records = self.kite.historical_data(
                token, from_date, to_date, interval, continuous=False
            )
            df = pd.DataFrame(records)
            if df.empty:
                log.warning(f"No candle data returned for {symbol}")
                return pd.DataFrame()
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            log.debug(f"Fetched {len(df)} candles for {symbol} [{interval}]")
            return df
        except Exception as e:
            log.error(f"Failed to fetch candles for {symbol}: {e}")
            return pd.DataFrame()

    # ── Real-time quotes ──────────────────────────────────────────────────────

    def get_ltp(self, symbols: List[str]) -> dict:
        """
        Return {symbol: ltp} for a list of 'EXCHANGE:SYMBOL' strings.
        Uses KiteConnect quote() which is real-time.
        """
        try:
            quotes = self.kite.ltp(symbols)
            return {sym: quotes[sym]["last_price"] for sym in quotes}
        except Exception as e:
            log.error(f"LTP fetch failed: {e}")
            return {}

    def get_quote(self, symbol: str) -> dict:
        """Full quote including OHLC, depth, etc."""
        try:
            return self.kite.quote([symbol]).get(symbol, {})
        except Exception as e:
            log.error(f"Quote fetch failed for {symbol}: {e}")
            return {}

    # ── Technical indicators ──────────────────────────────────────────────────

    def add_ema(self, df: pd.DataFrame, periods: List[int]) -> pd.DataFrame:
        """Append EMA columns to DataFrame."""
        for p in periods:
            df[f"ema_{p}"] = ta.ema(df["close"], length=p)
        return df

    def add_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        df["rsi"] = ta.rsi(df["close"], length=period)
        return df

    def add_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """VWAP calculated from intraday candles (resets each session)."""
        df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        return df

    def add_atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=period)
        return df

    def add_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        macd = ta.macd(df["close"])
        df = pd.concat([df, macd], axis=1)
        return df

    def add_bollinger(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        bbands = ta.bbands(df["close"], length=period)
        df = pd.concat([df, bbands], axis=1)
        return df
