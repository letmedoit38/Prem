"""
Market Data Module.

Fetches:
  • Historical OHLCV candles (for indicator calculation)
  • Real-time LTP (Last Traded Price) via KiteConnect
  • Instrument token lookup

Uses KiteConnect historical data API (requires paid subscription or
falls back to quote endpoint for intraday tick data).
"""
from datetime import datetime, timedelta
from typing import List

import numpy as np
import pandas as pd

from utils.logger import setup_logger

log = setup_logger("market_data")


# ── Pure-pandas/numpy indicator functions ─────────────────────────────────────────────

def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=length - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=length - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=length - 1, adjust=False).mean()


def _vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical_price = (high + low + close) / 3
    cum_vol = volume.cumsum()
    cum_tp_vol = (typical_price * volume).cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast   = _ema(series, fast)
    ema_slow   = _ema(series, slow)
    macd_line  = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram  = macd_line - signal_line
    return pd.DataFrame({
        f"MACD_{fast}_{slow}_{signal}": macd_line,
        f"MACDs_{fast}_{slow}_{signal}": signal_line,
        f"MACDh_{fast}_{slow}_{signal}": histogram,
    }, index=series.index)


def _bbands(series: pd.Series, length: int = 20, std: float = 2.0):
    sma  = series.rolling(length).mean()
    sd   = series.rolling(length).std(ddof=0)
    upper = sma + std * sd
    lower = sma - std * sd
    bw    = (upper - lower) / sma.replace(0, np.nan)
    bp    = (series - lower) / (upper - lower).replace(0, np.nan)
    return pd.DataFrame({
        f"BBL_{length}_{std}": lower,
        f"BBM_{length}_{std}": sma,
        f"BBU_{length}_{std}": upper,
        f"BBB_{length}_{std}": bw,
        f"BBP_{length}_{std}": bp,
    }, index=series.index)


# ── MarketData class ───────────────────────────────────────────────────────────

class MarketData:
    """
    Wrapper around KiteConnect data APIs.
    All bots share a single MarketData instance.
    """

    def __init__(self, kite):
        self.kite = kite
        self._instrument_cache: dict = {}

    # ── Instrument token ───────────────────────────────────────────────────────

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

    # ── Historical OHLCV ───────────────────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        interval: str = "5minute",
        lookback_days: int = 5,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV candles and return as DataFrame."""
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

    # ── Real-time quotes ─────────────────────────────────────────────────────

    def get_ltp(self, symbols: List[str]) -> dict:
        """Return {symbol: ltp} for a list of 'EXCHANGE:SYMBOL' strings."""
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
            df[f"ema_{p}"] = _ema(df["close"], p)
        return df

    def add_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        df["rsi"] = _rsi(df["close"], period)
        return df

    def add_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """VWAP calculated from intraday candles (resets each session)."""
        df["vwap"] = _vwap(df["high"], df["low"], df["close"], df["volume"])
        return df

    def add_atr(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        df["atr"] = _atr(df["high"], df["low"], df["close"], period)
        return df

    def add_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        macd = _macd(df["close"])
        df = pd.concat([df, macd], axis=1)
        return df

    def add_bollinger(self, df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        bbands = _bbands(df["close"], period)
        df = pd.concat([df, bbands], axis=1)
        return df
