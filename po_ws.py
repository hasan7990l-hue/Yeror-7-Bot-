#!/usr/bin/env python3
import json, time, threading, re, urllib.parse
import socketio

PO_WS_URLS = [
    "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api.po.market/socket.io/?EIO=4&transport=websocket",
]

def clean_session(raw):
    if not raw:
        raise ValueError("session is empty")
    m = re.search(r'"session"\s*:\s*"([^"]+)"', raw)
    if m:
        c = m.group(1)
        if 8 <= len(c) <= 80 and "%" not in c:
            return c
    try:
        d = urllib.parse.unquote(raw)
        m2 = re.search(r's:\d+:"session_id";s:\d+:"([A-Za-z0-9]{16,80})"', d)
        if m2:
            return m2.group(1)
    except Exception:
        pass
    m3 = re.search(r'\b([a-f0-9]{32})\b', raw.lower())
    if m3:
        return m3.group(1)
    s = raw.strip()
    if 8 <= len(s) <= 80:
        return s
    raise ValueError("session parse failed")

class POWebSocketClient:
    def __init__(self, session_raw, uid, is_demo, platform=2, timeout=25.0):
        self.session = clean_session(session_raw)
        self.uid = int(uid)
        self.is_demo = int(is_demo)
        self.platform = int(platform)
        self.timeout = timeout
        self.sio = socketio.Client(reconnection=False)
        self._authorized = threading.Event()
        self._got_history = threading.Event()
        self._candles_by_asset = {}
        self._error = None
        self._register_handlers()

    def _register_handlers(self):
        sio = self.sio

        @sio.on("successauth")
        def _sa(d):
            print("[PO] auth ok")
            self._authorized.set()

        @sio.on("updateHistoryNew")
        def _uh(d):
            self._handle_candles(d)

        @sio.on("updateHistory")
        def _uh2(d):
            self._handle_candles(d)

        @sio.on("updateStream")
        def _us(d):
            self._handle_stream(d)

        @sio.on("*")
        def _any(ev, d=None):
            if ev in ("successauth", "updateHistoryNew", "updateHistory", "updateStream"):
                return
            if isinstance(d, dict) and "candles" in d:
                self._handle_candles(d)

    def _handle_candles(self, data):
        try:
            asset = None
            candles = None
            if isinstance(data, dict):
                asset = data.get("asset") or data.get("symbol")
                candles = data.get("candles") or data.get("data") or data.get("history")
            elif isinstance(data, list):
                if len(data) >= 2 and isinstance(data[0], str):
                    asset = data[0]
                    inner = data[1]
                    if isinstance(inner, dict):
                        candles = inner.get("candles") or inner.get("data")
                    elif isinstance(inner, list):
                        candles = inner
                elif data and isinstance(data[0], list):
                    candles = data
            if not candles:
                return
            key = asset or "__default__"
            self._candles_by_asset[key] = candles
            print("[PO] got %d candles" % len(candles))
            self._got_history.set()
        except Exception as e:
            print("[PO] err:", e)

    def _handle_stream(self, data):
        try:
            if not isinstance(data, dict):
                return
            asset = data.get("asset")
            candle = data.get("candle") or data.get("data")
            if not asset or not candle:
                return
            bucket = self._candles_by_asset.setdefault(asset, [])
            if isinstance(candle, list) and len(candle) >= 5:
                if bucket and bucket[-1][0] == candle[0]:
                    bucket[-1] = candle
                else:
                    bucket.append(candle)
        except Exception:
            pass

    def _try_connect(self):
        for url in PO_WS_URLS:
            try:
                print("[PO] trying %s" % url)
                self.sio.connect(url, transports=["websocket"], wait_timeout=15)
                if self.sio.connected:
                    return True
            except Exception as e:
                print("[PO] fail: %s" % e)
        self._error = "all urls failed"
        return False

    def fetch_candles(self, asset, period, progress_cb=None):
        def _p(m):
            if progress_cb:
                try:
                    progress_cb(m)
                except Exception:
                    pass
            print("[PO] %s" % m)

        _p("open ws")
        if not self._try_connect():
            raise ConnectionError(self._error)
        _p("auth")
        self.sio.emit("auth", {
            "session": self.session,
            "isDemo": self.is_demo,
            "uid": self.uid,
            "platform": self.platform,
            "isFastHistory": True,
            "isOptimized": True,
        })
        self._authorized.wait(timeout=10)
        _p("subscribe %s" % asset)
        self.sio.emit("changeSymbol", {"asset": asset, "period": int(period)})
        waited = 0.0
        while waited < self.timeout:
            if self._got_history.is_set():
                break
            time.sleep(1)
            waited += 1
            if int(waited) % 4 == 0:
                _p("wait %ds" % waited)
                self.sio.emit("changeSymbol", {"asset": asset, "period": int(period)})
        try:
            self.sio.disconnect()
        except Exception:
            pass
        cr = (self._candles_by_asset.get(asset)
              or self._candles_by_asset.get("__default__")
              or [])
        if not cr:
            raise TimeoutError("no candles. keys=%s" % list(self._candles_by_asset.keys()))
        _p("%d candles" % len(cr))
        return self._normalize(cr)

    def _normalize(self, raw):
        out = []
        for c in raw:
            try:
                if isinstance(c, (list, tuple)) and len(c) >= 5:
                    out.append({
                        "time": int(c[0]),
                        "open": float(c[1]),
                        "close": float(c[2]),
                        "high": float(c[3]),
                        "low": float(c[4]),
                    })
                elif isinstance(c, dict):
                    out.append({
                        "time": int(c.get("time") or c.get("timestamp") or 0),
                        "open": float(c.get("open") or c.get("o") or 0),
                        "close": float(c.get("close") or c.get("c") or 0),
                        "high": float(c.get("high") or c.get("h") or 0),
                        "low": float(c.get("low") or c.get("l") or 0),
                    })
            except Exception:
                continue
        return out

def get_candles(session_raw, uid, is_demo, platform, asset, period,
                timeout=25.0, progress_cb=None):
    cli = POWebSocketClient(session_raw, uid, is_demo, platform, timeout)
    return cli.fetch_candles(asset, period, progress_cb=progress_cb)
