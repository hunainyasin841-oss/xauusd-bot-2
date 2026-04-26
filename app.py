"""
XAUUSD SMC Signal API Server
=============================
Flask REST API that wraps the SMC signal engine.
Deploy on Railway.app / Render.com / any VPS.

Endpoints:
  GET /signal        → latest SMC signal
  GET /price         → live XAUUSD price
  GET /health        → server status
"""

from flask import Flask, jsonify
from flask_cors import CORS
import logging
from datetime import datetime
from smc_engine import SMCEngine
from price_feed import get_gold_price

# ── Setup ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)   # allow mobile app to call this API

engine = SMCEngine()

# ── Routes ───────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.route('/price')
def price():
    try:
        p = get_gold_price()
        return jsonify({"price": p, "symbol": "XAUUSD", "time": datetime.utcnow().isoformat()})
    except Exception as e:
        log.error(f"Price error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/signal')
def signal():
    try:
        result = engine.run()
        return jsonify(result)
    except Exception as e:
        log.error(f"Signal error: {e}")
        return jsonify({"error": str(e), "signal": None}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
