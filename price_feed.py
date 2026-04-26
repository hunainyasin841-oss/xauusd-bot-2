"""
price_feed.py
=============
Fetches live XAUUSD spot price from free public APIs.
Falls back down the chain if one fails.
"""

import requests
import logging
import time

log = logging.getLogger(__name__)

TIMEOUT = 6   # seconds per request

# Cache so we don't hammer APIs on every signal call
_cache = {"price": None, "ts": 0}
CACHE_TTL = 25   # seconds


def get_gold_price() -> float:
    """Return live XAUUSD price. Cached for 25s."""
    now = time.time()
    if _cache["price"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["price"]

    price = (
        _try_metals_live()
        or _try_frankfurter()
        or _try_coinbase()
    )

    if not price:
        raise RuntimeError("All price APIs failed")

    _cache["price"] = price
    _cache["ts"] = now
    log.info(f"XAUUSD price fetched: {price}")
    return price


# ── Individual API tries ─────────────────────────────────

def _try_metals_live() -> float:
    """metals.live — free, no key needed"""
    try:
        r = requests.get("https://api.metals.live/v1/spot/gold", timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        # response: [{"gold": 2345.67}]  or  {"price": 2345.67}
        if isinstance(data, list):
            return float(data[0].get("price") or data[0].get("gold", 0))
        return float(data.get("price") or data.get("gold", 0))
    except Exception as e:
        log.warning(f"metals.live failed: {e}")
        return 0.0


def _try_frankfurter() -> float:
    """
    Frankfurter gives EUR/USD etc but NOT gold directly.
    We use it as a cross-check proxy only — skip in real use.
    Kept as structural fallback placeholder.
    """
    return 0.0


def _try_coinbase() -> float:
    """Coinbase public spot price for XAU-USD"""
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/XAU-USD/spot", timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return float(data["data"]["amount"])
    except Exception as e:
        log.warning(f"Coinbase failed: {e}")
        return 0.0
