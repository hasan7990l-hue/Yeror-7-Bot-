#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from typing import Dict, Any, List
from po_ws import get_candles

CONFIG = {
    "po_url": os.environ.get(
        "PO_URL",
        "https://pocketoption.com/en/cabinet/demo-quick-high-low/"
    ),
    "assets": [
        "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc",
        "USDCAD_otc", "NZDUSD_otc", "EURGBP_otc",
        "EURUSD", "GBPUSD", "USDJPY",
    ],
    "periods": [60, 120, 300, 900],
    "demo_session": os.environ.get("PO_DEMO_SESSION", ""),
    "demo_uid": int(os.environ.get("PO_DEMO_UID", "0") or 0),
    "real_session": os.environ.get("PO_REAL_SESSION", ""),
    "real_uid": int(os.environ.get("PO_REAL_UID", "0") or 0),
}

def _sma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None

def _ema(values, n):
    if len(values) < n:
        return None
    k = 2 / (n + 1)
    e = sum(values[:n]) / n
    for x in values[n:]:
        e = x * k + e * (1 - k)
    return e

def _rsi(values, n=14):
    if len(values) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[-n:]) / n
    al = sum(losses[-n:]) / n
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))

def analyze_from_candles(candles: List[Dict]) -> Dict[str, Any]:
    closes = [c["close"] for c in candles if c.get("close")]
    if len(closes) < 25:
        return {
            "signal": "NEUTRAL",
            "confidence": 0.0,
            "price": closes[-1] if closes else 0.0,
            "reason": "بيانات غير كافية (%d شمعة)" % len(closes),
        }

    price = closes[-1]
    s5n, s20n = _sma(closes, 5), _sma(closes, 20)
    s5p, s20p = _sma(closes[:-1], 5), _sma(closes[:-1], 20)
    e9, e21 = _ema(closes, 9), _ema(closes, 21)
    rsi = _rsi(closes, 14)

    score = 0
    reasons = []

    if s5p and s20p:
        if s5p <= s20p and s5n > s20n:
            score += 2
            reasons.append("SMA5 crossed above SMA20")
        elif s5p >= s20p and s5n < s20n:
            score -= 2
            reasons.append("SMA5 crossed below SMA20")

    if e9 and e21:
        if e9 > e21:
            score += 1
            reasons.append("EMA9 above EMA21")
        elif e9 < e21:
            score -= 1
            reasons.append("EMA9 below EMA21")

    if rsi is not None:
        if rsi < 30:
            score += 1
            reasons.append("RSI=%.0f oversold" % rsi)
        elif rsi > 70:
            score -= 1
            reasons.append("RSI=%.0f overbought" % rsi)

    if score >= 3:
        sig, conf = "CALL", min(95, 55 + score * 8)
    elif score <= -3:
        sig, conf = "PUT", min(95, 55 + abs(score) * 8)
    else:
        sig, conf = "NEUTRAL", 50.0

    return {
        "signal": sig,
        "confidence": round(conf, 1),
        "price": round(float(price), 5),
        "reason": " | ".join(reasons) if reasons else "no clear signal",
        "indicators": {
            "sma5": round(s5n, 5) if s5n else None,
            "sma20": round(s20n, 5) if s20n else None,
            "ema9": round(e9, 5) if e9 else None,
            "ema21": round(e21, 5) if e21 else None,
            "rsi": round(rsi, 2) if rsi is not None else None,
        },
        "candles_count": len(closes),
    }

def analyze_chart(asset="EURUSD_otc", period=60,
                  session_type="demo", progress_cb=None):
    if session_type == "real":
        sess = CONFIG["real_session"]
        uid = CONFIG["real_uid"]
        demo = 0
        plat = 1
    else:
        sess = CONFIG["demo_session"]
        uid = CONFIG["demo_uid"]
        demo = 1
        plat = 2

    if not sess:
        return {
            "signal": "NEUTRAL",
            "confidence": 0.0,
            "price": 0.0,
            "reason": "PO_%s_SESSION not set" % session_type.upper(),
        }

    try:
        candles = get_candles(sess, uid, demo, plat, asset,
                              period, timeout=25.0, progress_cb=progress_cb)
    except Exception as e:
        return {
            "signal": "NEUTRAL",
            "confidence": 0.0,
            "price": 0.0,
            "reason": "connection failed: %s: %s" % (type(e).__name__, str(e)[:180]),
        }

    return analyze_from_candles(candles)
