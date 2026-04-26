"""
smc_engine.py
=============
Real SMC (Smart Money Concepts) signal engine.
- Fetches real OHLC data via yfinance (free, no API key)
- H4 bias detection (BoS / CHoCH)
- M15 entry: FVG, Order Block, Inducement Sweep
- Risk levels: structural SL, 2R TP
- Caches data to avoid repeated downloads
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

import pandas as pd
import numpy as np
import yfinance as yf

from price_feed import get_gold_price

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────
MIN_RR          = 2.0
CONFIDENCE_THRESHOLD = 0.58
DATA_WINDOW_H4  = 200    # bars
DATA_WINDOW_M15 = 300    # bars
SWING_CANDLES   = 5      # pivot detection lookback
CACHE_TTL_SECS  = 60 * 14   # re-fetch OHLC every 14 min


class SMCEngine:
    def __init__(self):
        self._h4: Optional[pd.DataFrame] = None
        self._m15: Optional[pd.DataFrame] = None
        self._last_fetch: float = 0

    # ── Public ────────────────────────────────────────────

    def run(self) -> Dict:
        """Full pipeline. Returns signal dict ready for the API."""
        self._maybe_refresh_data()

        if self._h4 is None or self._m15 is None:
            return self._no_signal("OHLC data unavailable")

        price = get_gold_price()
        bias  = self._get_bias(self._h4)

        if bias == 0:
            return self._no_signal("No H4 structural bias")

        sig = self._find_entry(self._m15, bias, price)
        if sig is None:
            return self._no_signal(f"No M15 setup for {'LONG' if bias==1 else 'SHORT'} bias")

        return sig

    # ── Data fetch ────────────────────────────────────────

    def _maybe_refresh_data(self):
        if time.time() - self._last_fetch < CACHE_TTL_SECS:
            return
        try:
            ticker = yf.Ticker("GC=F")   # Gold futures — best free OHLC
            self._h4  = ticker.history(period="60d",  interval="1h").tail(DATA_WINDOW_H4)
            self._m15 = ticker.history(period="10d",  interval="15m").tail(DATA_WINDOW_M15)
            # Normalise column names
            for df in [self._h4, self._m15]:
                df.columns = [c.lower() for c in df.columns]
            self._last_fetch = time.time()
            log.info(f"OHLC refreshed — H4:{len(self._h4)} bars, M15:{len(self._m15)} bars")
        except Exception as e:
            log.error(f"yfinance fetch failed: {e}")
            self._h4  = None
            self._m15 = None

    # ── Swing detection ───────────────────────────────────

    def _detect_swings(self, df: pd.DataFrame, n: int = SWING_CANDLES) -> Tuple[List[int], List[int]]:
        highs = df['high'].values
        lows  = df['low'].values
        sh, sl = [], []
        for i in range(n, len(df) - n):
            if all(highs[i] > highs[i-j] for j in range(1, n+1)) and \
               all(highs[i] > highs[i+j] for j in range(1, n+1)):
                sh.append(i)
            if all(lows[i] < lows[i-j] for j in range(1, n+1)) and \
               all(lows[i] < lows[i+j] for j in range(1, n+1)):
                sl.append(i)
        return sh, sl

    # ── H4 Bias ───────────────────────────────────────────

    def _market_structure(self, df: pd.DataFrame) -> int:
        sh, sl = self._detect_swings(df, n=3)
        if len(sh) < 2 or len(sl) < 2:
            return 0
        lh = df['high'].iloc[sh[-1]]
        ph = df['high'].iloc[sh[-2]]
        ll = df['low'].iloc[sl[-1]]
        pl = df['low'].iloc[sl[-2]]
        if lh > ph and ll > pl:
            return 1    # bullish BoS
        if lh < ph and ll < pl:
            return -1   # bearish BoS
        return 0

    def _premium_discount(self, df: pd.DataFrame) -> Tuple[float, float, float]:
        sh, sl = self._detect_swings(df)
        if not sh or not sl:
            return None, None, None
        h  = df['high'].iloc[sh[-1]]
        l  = df['low'].iloc[sl[-1]]
        eq = (h + l) / 2
        return h, l, eq

    def _get_bias(self, df_h4: pd.DataFrame) -> int:
        bias = self._market_structure(df_h4)
        if bias == 0:
            return 0
        h, l, eq = self._premium_discount(df_h4)
        if eq is None:
            return 0
        price = df_h4['close'].iloc[-1]
        # Only trade from discount in bull, premium in bear
        if bias == 1  and price >= eq:
            return 0
        if bias == -1 and price <= eq:
            return 0
        return bias

    # ── M15 Setups ────────────────────────────────────────

    def _fvg(self, df: pd.DataFrame, i: int) -> Optional[Dict]:
        """3-candle Fair Value Gap."""
        if i < 2:
            return None
        # Bullish FVG
        if df['high'].iloc[i-2] < df['low'].iloc[i]:
            return {'dir': 'bull',
                    'high': df['low'].iloc[i],
                    'low':  df['high'].iloc[i-2],
                    'mid':  (df['low'].iloc[i] + df['high'].iloc[i-2]) / 2}
        # Bearish FVG
        if df['low'].iloc[i-2] > df['high'].iloc[i]:
            return {'dir': 'bear',
                    'high': df['low'].iloc[i-2],
                    'low':  df['high'].iloc[i],
                    'mid':  (df['low'].iloc[i-2] + df['high'].iloc[i]) / 2}
        return None

    def _order_block(self, df: pd.DataFrame, i: int, bias: int) -> Optional[Dict]:
        """Last opposite-colour candle before strong impulse."""
        if i < 3:
            return None
        body      = df['close'].iloc[i]   - df['open'].iloc[i]
        prev_body = df['close'].iloc[i-1] - df['open'].iloc[i-1]
        if bias == 1 and prev_body < 0 and body > 0 and body > abs(prev_body) * 1.5:
            return {'type': 'bull',
                    'high': df['high'].iloc[i-1],
                    'low':  df['low'].iloc[i-1],
                    'mid':  (df['high'].iloc[i-1] + df['low'].iloc[i-1]) / 2}
        if bias == -1 and prev_body > 0 and body < 0 and abs(body) > prev_body * 1.5:
            return {'type': 'bear',
                    'high': df['high'].iloc[i-1],
                    'low':  df['low'].iloc[i-1],
                    'mid':  (df['high'].iloc[i-1] + df['low'].iloc[i-1]) / 2}
        return None

    def _inducement_sweep(self, df: pd.DataFrame, i: int, bias: int) -> bool:
        """Stop-hunt: wick through a swing, close back inside."""
        sh, sl = self._detect_swings(df.iloc[:i+1], n=3)
        if not sh or not sl:
            return False
        if bias == 1 and sl:
            last_low = df['low'].iloc[sl[-1]]
            return (df['low'].iloc[i] < last_low and
                    df['close'].iloc[i] > last_low and
                    df['close'].iloc[i] > df['open'].iloc[i])
        if bias == -1 and sh:
            last_high = df['high'].iloc[sh[-1]]
            return (df['high'].iloc[i] > last_high and
                    df['close'].iloc[i] < last_high and
                    df['close'].iloc[i] < df['open'].iloc[i])
        return False

    def _session_ok(self) -> Tuple[bool, str]:
        """Only trade London or NY sessions (UTC)."""
        h = datetime.now(timezone.utc).hour
        if 8 <= h < 16:
            return True, "London"
        if 13 <= h < 21:
            return True, "New York"
        return False, "Off-session"

    # ── Entry logic ───────────────────────────────────────

    def _find_entry(self, df: pd.DataFrame, bias: int, price: float) -> Optional[Dict]:
        ok, session = self._session_ok()
        i = len(df) - 1

        fvg   = self._fvg(df, i)
        ob    = self._order_block(df, i, bias)
        sweep = self._inducement_sweep(df, i, bias)

        # Need at least one confluence
        fvg_match = fvg and fvg['dir'] == ('bull' if bias == 1 else 'bear')
        ob_match  = ob  and ob['type']  == ('bull' if bias == 1 else 'bear')

        if not fvg_match and not ob_match:
            return None

        # Confidence score
        conf = 0.35
        if fvg_match:   conf += 0.18
        if ob_match:    conf += 0.15
        if sweep:       conf += 0.14
        if ok:          conf += 0.12
        # ATR filter (avoid choppy conditions)
        atr = self._atr(df, 14)
        if atr and atr > 0:
            atr_pct = atr / price
            if atr_pct > 0.0015:
                conf += 0.08   # good volatility

        if conf < CONFIDENCE_THRESHOLD:
            return None

        # Structural SL
        sh, sl = self._detect_swings(df.iloc[:i+1], n=5)
        if bias == 1:
            sl_price = (df['low'].iloc[sl[-1]] - 0.30) if sl else (price - 8)
        else:
            sl_price = (df['high'].iloc[sh[-1]] + 0.30) if sh else (price + 8)

        sl_dist = abs(price - sl_price)
        if sl_dist < 0.5:
            return None   # SL too tight

        tp_price = price + (sl_dist * MIN_RR) if bias == 1 else price - (sl_dist * MIN_RR)
        rr       = round(sl_dist * MIN_RR / sl_dist, 1)   # always MIN_RR

        tags = {
            "fvg":     fvg_match,
            "ob":      ob_match,
            "sweep":   sweep,
            "bos":     True,   # we already confirmed BoS in H4
            "session": ok,
            "pd":      True    # bias only from discount/premium zone
        }

        return {
            "signal":     True,
            "bias":       "LONG" if bias == 1 else "SHORT",
            "entry":      round(price, 2),
            "sl":         round(sl_price, 2),
            "tp":         round(tp_price, 2),
            "rr":         rr,
            "confidence": round(min(conf, 0.97), 2),
            "session":    session,
            "tags":       tags,
            "atr":        round(atr, 2) if atr else None,
            "time":       datetime.utcnow().isoformat()
        }

    # ── Helpers ───────────────────────────────────────────

    def _atr(self, df: pd.DataFrame, n: int = 14) -> Optional[float]:
        try:
            high = df['high']
            low  = df['low']
            close_prev = df['close'].shift(1)
            tr = pd.concat([
                high - low,
                (high - close_prev).abs(),
                (low  - close_prev).abs()
            ], axis=1).max(axis=1)
            return tr.rolling(n).mean().iloc[-1]
        except Exception:
            return None

    def _no_signal(self, reason: str) -> Dict:
        log.info(f"No signal: {reason}")
        return {
            "signal":  False,
            "reason":  reason,
            "time":    datetime.utcnow().isoformat()
        }
