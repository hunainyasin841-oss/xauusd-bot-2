# XAUUSD SMC Signal Bot — Deployment Guide
==========================================

## What you have
```
xauusd-bot/
├── app.py            ← Flask API server (main)
├── smc_engine.py     ← Real SMC candle analysis
├── price_feed.py     ← Live gold price fetcher
├── requirements.txt  ← Python dependencies
├── Procfile          ← For Railway/Render
├── railway.toml      ← Railway config
└── mobile_app/
    └── index.html    ← Your mobile app (install as PWA)
```

---

## STEP 1 — Deploy Flask API to Railway (FREE, 10 min)

1. Go to https://railway.app → Sign up free (GitHub login)
2. Click "New Project" → "Deploy from GitHub repo"
3. Upload these files to a GitHub repo first:
   - app.py, smc_engine.py, price_feed.py, requirements.txt, Procfile, railway.toml
4. Railway auto-detects Python and deploys
5. Click your project → Settings → Domains → "Generate Domain"
6. Copy your URL: e.g. https://xauusd-bot-production.railway.app

### Test your server:
Open browser → https://YOUR-URL.railway.app/health
Should return: {"status": "ok", "time": "..."}

Open browser → https://YOUR-URL.railway.app/signal
Should return real SMC signal JSON.

---

## STEP 2 — Connect mobile app to server

1. Open mobile_app/index.html in a text editor
2. Find this line near the top of <script>:
   const DEFAULT_URL = "https://YOUR-APP.railway.app";
3. Replace with your actual Railway URL
4. Save the file

OR — use the in-app settings:
- Open the app → tap ⚙️ button (bottom right)
- Enter your Railway URL
- Tap "Save & Connect"

---

## STEP 3 — Install as mobile app (PWA)

### Android (Chrome):
1. Open index.html in Chrome
2. Tap 3-dot menu → "Add to Home Screen"
3. Done — launches like a native app

### iPhone (Safari):
1. Open index.html in Safari
2. Tap Share → "Add to Home Screen"
3. Done

### Alternative — host the HTML file free:
Upload index.html to https://netlify.app (drag & drop)
Then open that URL on your phone and add to home screen.

---

## STEP 4 — Verify signals are real

Hit /signal on your server. Real signal looks like:
```json
{
  "signal": true,
  "bias": "LONG",
  "entry": 3321.40,
  "sl": 3314.20,
  "tp": 3335.80,
  "rr": 2.0,
  "confidence": 0.74,
  "session": "London",
  "tags": {
    "fvg": true,
    "ob": false,
    "sweep": true,
    "bos": true,
    "session": true,
    "pd": true
  },
  "time": "2026-04-26T10:30:00"
}
```

No signal looks like:
```json
{
  "signal": false,
  "reason": "No M15 setup for LONG bias",
  "time": "2026-04-26T10:30:00"
}
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| /health returns error | Check Railway logs → re-deploy |
| Signal always false | Market may be closed or no setup — normal |
| yfinance timeout | Railway free tier spins down — first request is slow |
| CORS error in browser | flask-cors is included — check requirements.txt installed |

---

## Upgrade path (optional)
- Add Telegram bot alerts when signal fires
- Add cTrader live execution (your original Python bot)
- Add backtesting endpoint /backtest
- Add ML model training endpoint /train
