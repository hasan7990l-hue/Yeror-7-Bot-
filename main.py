#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import re
import asyncio
import inspect
import urllib.parse
import traceback
from datetime import datetime
from typing import Dict, List, Optional

# --- مسارات الكتابة ---
TMP_DIR = "/tmp/pocket_data"
os.makedirs(TMP_DIR, exist_ok=True)
os.environ["HOME"] = TMP_DIR
os.environ["TMPDIR"] = TMP_DIR
try:
    os.chdir(TMP_DIR)
except Exception:
    pass

import streamlit as st

# --- استيراد المكتبة ---
LIB_TYPE = "none"
try:
    from pocket_option import PocketOptionClient
    from pocket_option.models import AuthorizationData, Asset
    from pocket_option.contrib.default_init import default_init
    LIB_TYPE = "pocket-option"
except Exception as e:
    LIB_TYPE = f"none: {e}"

print(f"[INIT] LIB_TYPE = {LIB_TYPE}")


# ============================================================
# 👥 المستخدمون + الحسابات
# ============================================================
USERS: Dict[str, Dict] = {
    "b1b2b3h45h@gmail.com": {
        "password": "123456",
        "accounts": {
            "demo": {
                "label": "🟡 حساب تجريبي",
                "session": '42["auth",{"session":"vtftn12e6f5f5008moitsd6skl","isDemo":1,"uid":27658142,"platform":2,"isFastHistory":true,"isOptimized":true}]',
                "uid": 27658142,
                "is_demo": 1,
                "platform": 2,
            },
            "real": {
                "label": "🟢 حساب حقيقي",
                "session": '42["auth",{"session":"dd9920ddafa73b322244df17e0ba2009","isDemo":0,"uid":101884312,"platform":1,"isFastHistory":true,"isOptimized":true}]',
                "uid": 101884312,
                "is_demo": 0,
                "platform": 1,
            },
        },
    },
}

FOREX_SYMBOLS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc",
                 "NZDUSD_otc", "EURGBP_otc", "EURUSD", "GBPUSD", "USDJPY"]


# ============================================================
# 🔑 استخراج جلسة WS من أي صيغة
# ============================================================
def extract_ws_session(raw_session: str) -> str:
    """
    يستخرج WS session_id من:
    - 42["auth",{"session":"vtftn..."}]                ← رسالة Socket.IO
    - a%3A4%3A%7Bs%3A10%3A%22session_id%22...          ← PHP cookie مُرمَّز
    - hex خام 32 حرف
    """
    if not raw_session:
        raise ValueError("session فارغة")

    # الحالة 1: JSON داخل 42["auth",{...}]
    m = re.search(r'"session"\s*:\s*"([^"]+)"', raw_session)
    if m:
        candidate = m.group(1)
        if 8 <= len(candidate) <= 64 and "%" not in candidate and "\\" not in candidate:
            return candidate

    # الحالة 2: PHP serialized URL-encoded
    try:
        decoded = urllib.parse.unquote(raw_session)
        m2 = re.search(r's:\d+:"session_id";s:\d+:"([A-Za-z0-9]{16,64})"', decoded)
        if m2:
            return m2.group(1)
    except Exception:
        pass

    # الحالة 3: hex خام
    m3 = re.search(r'\b([a-f0-9]{32})\b', raw_session.lower())
    if m3:
        return m3.group(1)

    raise ValueError(f"تعذّر استخراج WS session من: {raw_session[:80]}...")


def parse_auth_message(session_str: str) -> dict:
    """يستخرج dict من رسالة 42["auth",{...}] إن وُجدت."""
    m = re.search(r'42\["auth",\s*(\{.*?\})\s*\]', session_str)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


# ============================================================
# 🔧 بناء AuthorizationData
# ============================================================
def build_auth_data(acc: dict) -> AuthorizationData:
    """يبني AuthorizationData بشكل صحيح للحساب demo أو real."""
    parsed = parse_auth_message(acc.get("session", ""))
    ws_session = extract_ws_session(acc["session"])
    print(f"[AUTH] ws_session = {ws_session[:10]}... (len={len(ws_session)})")

    payload = {
        "session":       ws_session,
        "isDemo":        int(acc.get("is_demo", parsed.get("isDemo", 1))),
        "uid":           int(acc.get("uid", parsed.get("uid", 0))),
        "platform":      int(acc.get("platform", parsed.get("platform", 2))),
        "isFastHistory": True,
        "isOptimized":   True,
    }
    return AuthorizationData.model_validate(payload)


# ============================================================
# 🔌 إنشاء client + اتصال صحيح
# ============================================================
def make_client(auth_data: AuthorizationData):
    """
    يحاول إنشاء العميل بعدة توقيعات محتملة للمكتبة.
    يُعيد (client, how) حيث how = وصف طريقة الإنشاء.
    """
    # محاولة 1: تمرير auth في المُنشئ
    try:
        c = PocketOptionClient(auth_data)
        return c, "PocketOptionClient(auth_data)"
    except TypeError:
        pass

    # محاولة 2: بلا وسائط ثم تعيين AuthorizationData
    try:
        c = PocketOptionClient()
        for attr in ("authorization_data", "auth_data", "authorization"):
            if hasattr(c, attr):
                try:
                    setattr(c, attr, auth_data)
                    return c, f"PocketOptionClient() + set {attr}"
                except Exception:
                    continue
        return c, "PocketOptionClient() (no auth set)"
    except Exception as e:
        raise RuntimeError(f"فشل إنشاء PocketOptionClient: {e}")


async def _call_maybe_async(fn, *args, timeout: float = 25.0, **kwargs):
    """يستدعي دالة قد تكون sync أو async مع timeout."""
    ret = fn(*args, **kwargs)
    if inspect.isawaitable(ret):
        return await asyncio.wait_for(ret, timeout=timeout)
    return ret


async def explicit_connect(client, auth_data, progress_cb=None) -> dict:
    """
    يحاول عدة توقيعات للاتصال. لا يفرض url.
    """
    result = {"success": False, "used": None, "errors": []}

    def _p(msg):
        if progress_cb:
            try: progress_cb(msg)
            except Exception: pass
        print(f"[CONNECT] {msg}")

    # قائمة المحاولات بالترتيب — من الأكثر احتمالاً للأقل
    attempts = []

    # connect() بلا وسائط
    attempts.append(("connect()", lambda: client.connect()))

    # connect(wait=True)
    try:
        sig = inspect.signature(client.connect)
        if "wait" in sig.parameters:
            attempts.append(("connect(wait=True)", lambda: client.connect(wait=True)))
        if "auth" in sig.parameters:
            attempts.append(("connect(auth=auth_data)", lambda: client.connect(auth=auth_data)))
        if "authorization" in sig.parameters:
            attempts.append(("connect(authorization=auth_data)",
                             lambda: client.connect(authorization=auth_data)))
    except Exception:
        pass

    # connect(auth_data) positional
    attempts.append(("connect(auth_data)", lambda: client.connect(auth_data)))

    for name, fn in attempts:
        try:
            _p(f"🔌 محاولة: {name}")
            await _call_maybe_async(fn, timeout=25.0)
            result["used"] = name
            result["success"] = True
            _p(f"✅ نجح: {name}")
            return result
        except TypeError as te:
            result["errors"].append(f"{name} → TypeError: {te}")
        except asyncio.TimeoutError:
            result["errors"].append(f"{name} → Timeout 25s")
        except Exception as e:
            result["errors"].append(f"{name} → {type(e).__name__}: {e}")

    return result


def _get_sio(client):
    """يجد كائن socket.io بأي اسم سمة."""
    for attr in ("sio", "_sio", "socket", "_socket", "ws", "_ws"):
        obj = getattr(client, attr, None)
        if obj is not None and hasattr(obj, "connected"):
            return obj
    return None


async def wait_socket_connected(client, max_wait=20.0, step=0.5, progress_cb=None) -> bool:
    waited = 0.0
    last_msg = 0
    while waited < max_wait:
        await asyncio.sleep(step)
        waited += step

        sio = _get_sio(client)
        if sio is not None and getattr(sio, "connected", False):
            print(f"[DEBUG] socket connected after {waited:.1f}s")
            return True
        if getattr(client, "is_connected", False):
            print(f"[DEBUG] is_connected=True after {waited:.1f}s")
            return True

        if progress_cb and int(waited) - last_msg >= 2:
            last_msg = int(waited)
            try: progress_cb(f"⏳ انتظار Socket... ({waited:.0f}s / {max_wait:.0f}s)")
            except Exception: pass

    return False


def diagnose_client(client) -> str:
    lines = ["=== تشخيص كائن PocketOptionClient ==="]
    lines.append(f"النوع: {type(client).__name__}")
    lines.append(f"الوحدة: {type(client).__module__}")
    try:
        attrs = [a for a in dir(client) if not a.startswith("__")]
    except Exception:
        attrs = []
    for a in attrs:
        try:
            val = getattr(client, a)
            kind = type(val).__name__
            lines.append(f"  • {a}{'()' if callable(val) else ''}  [{kind}]")
        except Exception as e:
            lines.append(f"  • {a} = <خطأ: {e}>")
    return "\n".join(lines)


# ============================================================
# 💰 سحب الرصيد
# ============================================================
async def _get_balance_async(acc: dict, progress_cb=None) -> float:
    def _p(msg):
        if progress_cb:
            try: progress_cb(msg)
            except Exception: pass
        print(f"[PROGRESS] {msg}")

    _p("🔄 المرحلة 1/4: تجهيز بيانات التفويض...")
    auth_data = build_auth_data(acc)

    _p("🔄 المرحلة 2/4: إنشاء العميل...")
    client, how = make_client(auth_data)
    print(f"[DEBUG] client created via: {how}")

    # تسجيل مستقبل الرصيد
    balance_value = {"v": None}

    @client.on.balance_success_update
    async def on_balance(data):
        print(f"[DEBUG] balance update: {data}")
        if isinstance(data, dict):
            balance_value["v"] = data.get("balance", data.get("amount", data.get("value", 0)))
        elif hasattr(data, "balance"):
            balance_value["v"] = data.balance
        else:
            balance_value["v"] = data

    # default_init قد لا يكون ضرورياً وربما يسبب مشاكل — نلفّه بـ try
    try:
        default_init(client, authorization=auth_data,
                     sub_assets=["EURUSD_otc"], sub_period=60)
    except Exception as e:
        print(f"[DEBUG] default_init تخطّاه: {e}")

    _p("🔄 المرحلة 3/4: الاتصال بـ WebSocket...")
    conn = await explicit_connect(client, auth_data, progress_cb=_p)
    print(f"[DEBUG] connect result: {conn}")

    if not conn["success"]:
        diagnosis = diagnose_client(client)
        raise TimeoutError(
            f"❌ فشل الاتصال بكل التوقيعات.\n"
            f"الأخطاء: {conn['errors']}\n\n{diagnosis}"
        )

    connected = await wait_socket_connected(client, max_wait=15.0, progress_cb=_p)
    _p(f"✅ Socket: {'متصل' if connected else 'غير متصل'}")

    authorized = False
    try:
        if hasattr(client, "wait_for_authorization"):
            authorized = await _call_maybe_async(client.wait_for_authorization, timeout=10.0)
        if getattr(client, "is_authorized", False):
            authorized = True
    except Exception as e:
        print(f"[DEBUG] wait_for_authorization فشل: {e}")

    # Fallback: اقرأ الرصيد من سمات العميل
    if balance_value["v"] is None:
        for attr in ("balance", "_balance", "account_balance", "current_balance"):
            v = getattr(client, attr, None)
            if isinstance(v, (int, float)) and v >= 0:
                balance_value["v"] = v
                print(f"[DEBUG] fallback balance from client.{attr} = {v}")
                break

    _p("🔄 المرحلة 4/4: طلب الرصيد...")
    if balance_value["v"] is None:
        for attempt in range(1, 4):
            try:
                em = getattr(client, "emit", None)
                if em and hasattr(em, "update_balance"):
                    await _call_maybe_async(em.update_balance, timeout=5.0)
                    print(f"[DEBUG] update_balance attempt {attempt} OK")
                    break
                elif hasattr(client, "update_balance"):
                    await _call_maybe_async(client.update_balance, timeout=5.0)
                    break
            except Exception as e:
                print(f"[DEBUG] update_balance {attempt} فشل: {e}")
                await asyncio.sleep(1.5)

    elapsed = 0.0
    while balance_value["v"] is None and elapsed < 6.0:
        await asyncio.sleep(0.5)
        elapsed += 0.5

    try:
        await _call_maybe_async(client.close, timeout=5.0)
    except Exception:
        pass

    if balance_value["v"] is None:
        raise TimeoutError(
            f"لم يتم استلام الرصيد. متصل={connected}, مفوَّض={authorized}\n\n"
            f"{diagnose_client(client)}"
        )

    return float(balance_value["v"])


# ============================================================
# 📊 سحب الشموع
# ============================================================
async def _get_candles_async(acc: dict, asset: str, period: int, progress_cb=None) -> List:
    def _p(msg):
        if progress_cb:
            try: progress_cb(msg)
            except Exception: pass
        print(f"[PROGRESS] {msg}")

    _p("🔄 تجهيز التفويض...")
    auth_data = build_auth_data(acc)

    _p("🔄 إنشاء العميل...")
    client, how = make_client(auth_data)
    print(f"[DEBUG] client via: {how}")

    try:
        default_init(client, authorization=auth_data,
                     sub_assets=[asset], sub_period=period)
    except Exception as e:
        print(f"[DEBUG] default_init تخطّاه: {e}")

    _p("🔌 الاتصال...")
    conn = await explicit_connect(client, auth_data, progress_cb=_p)
    if not conn["success"]:
        raise TimeoutError(f"فشل الاتصال: {conn['errors']}")

    await wait_socket_connected(client, max_wait=15.0, progress_cb=_p)

    try:
        if hasattr(client, "wait_for_authorization"):
            await _call_maybe_async(client.wait_for_authorization, timeout=10.0)
    except Exception:
        pass

    _p("📊 جلب الشموع...")
    candles = await _call_maybe_async(
        client.get_candles, Asset(asset), period, 30, timeout=30.0
    )
    try:
        await _call_maybe_async(client.close, timeout=5.0)
    except Exception:
        pass

    return candles or []


# ============================================================
# 📈 توليد الإشارة
# ============================================================
def generate_signal(candles, short_period=5, long_period=20) -> Dict:
    if not candles or len(candles) < long_period + 1:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0,
                "reason": "بيانات غير كافية"}

    def _close(c):
        if isinstance(c, dict):
            return c.get("close")
        return getattr(c, "close", None)

    try:
        closes = [_close(c) for c in candles]
        closes = [c for c in closes if isinstance(c, (int, float))]
    except Exception:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0,
                "reason": "صيغة شموع غير معروفة"}

    if len(closes) < long_period + 1:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0,
                "reason": "بيانات غير كافية"}

    price = closes[-1]
    sma_s = sum(closes[-short_period:]) / short_period
    sma_l = sum(closes[-long_period:]) / long_period
    prev_s = sum(closes[-short_period-1:-1]) / short_period
    prev_l = sum(closes[-long_period-1:-1]) / long_period

    diff = abs((sma_s - sma_l) / sma_l) * 100 if sma_l else 0
    conf = min(90, 50 + diff * 3)

    if prev_s <= prev_l and sma_s > sma_l:
        return {"signal": "CALL 🟢", "confidence": round(conf, 1),
                "price": price, "reason": f"SMA({short_period}) تجاوز SMA({long_period})"}
    if prev_s >= prev_l and sma_s < sma_l:
        return {"signal": "PUT 🔴", "confidence": round(conf, 1),
                "price": price, "reason": f"SMA({short_period}) نزل تحت SMA({long_period})"}
    return {"signal": "NEUTRAL ⚪", "confidence": 50.0, "price": price,
            "reason": "لا يوجد تقاطع واضح"}


def verify_login(email, password):
    email = email.strip().lower()
    for stored, info in USERS.items():
        if stored.lower() == email and info["password"] == password:
            return {"email": stored, "accounts": info["accounts"]}
    return None


# ============================================================
# 🎨 واجهة Streamlit
# ============================================================
st.set_page_config(page_title="إشارات OTC", page_icon="📈", layout="wide")

st.markdown("""
<style>
@keyframes gradientBG {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
.stApp {
    background: linear-gradient(-45deg, #0f172a, #1e293b, #0f172a, #1e3a8a, #0f172a);
    background-size: 400% 400%;
    animation: gradientBG 18s ease infinite;
    min-height: 100vh;
}
.stApp::before {
    content: "";
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(circle at 20% 20%, rgba(34,211,238,0.06), transparent 40%),
                radial-gradient(circle at 80% 80%, rgba(168,85,247,0.06), transparent 40%);
    pointer-events: none;
    z-index: 0;
}
.main-title {
    font-size: 2.6rem;
    font-weight: 900;
    text-align: center;
    background: linear-gradient(90deg, #22d3ee, #3b82f6, #a855f7, #22d3ee);
    background-size: 300% 300%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: gradientBG 6s ease infinite;
    margin-bottom: 0.3rem;
    letter-spacing: 1px;
    filter: drop-shadow(0 0 20px rgba(34,211,238,0.35));
}
.sub-title {
    text-align: center;
    color: #94a3b8;
    font-size: 1rem;
    margin-bottom: 1.5rem;
}
@keyframes welcomeFade {
    0% { opacity: 0; transform: translateY(-15px); }
    100% { opacity: 1; transform: translateY(0); }
}
.welcome-box {
    background: linear-gradient(135deg, rgba(34,211,238,0.12), rgba(168,85,247,0.12));
    border: 1px solid rgba(34,211,238,0.35);
    border-radius: 18px;
    padding: 1.8rem 2rem;
    margin: 1rem 0 1.8rem 0;
    color: #e2e8f0;
    animation: welcomeFade 0.9s ease-out;
    box-shadow: 0 8px 32px rgba(34,211,238,0.15), inset 0 0 60px rgba(168,85,247,0.05);
    backdrop-filter: blur(10px);
    position: relative;
    overflow: hidden;
}
.welcome-box h2 { margin: 0 0 0.5rem 0; font-size: 1.6rem; color: #22d3ee; position: relative; z-index: 1; }
.welcome-box p { margin: 0.3rem 0; font-size: 1.02rem; color: #cbd5e1; position: relative; z-index: 1; line-height: 1.7; }
.welcome-box .highlight { color: #fbbf24; font-weight: 700; }
.stButton > button {
    background: linear-gradient(135deg, #1e3a8a, #3b82f6) !important;
    color: #fff !important; border: none !important; border-radius: 10px !important;
    font-weight: 600 !important; padding: 0.6rem 1rem !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 4px 12px rgba(59,130,246,0.35) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 22px rgba(59,130,246,0.55) !important;
    background: linear-gradient(135deg, #3b82f6, #22d3ee) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0891b2, #22d3ee) !important;
    box-shadow: 0 4px 14px rgba(34,211,238,0.45) !important;
}
.signal-call{background:linear-gradient(90deg,#00c853,#64dd17);padding:1.3rem;border-radius:14px;color:#fff;text-align:center;font-size:1.5rem;font-weight:800;box-shadow:0 6px 24px rgba(0,200,83,0.45)}
.signal-put{background:linear-gradient(90deg,#d50000,#ff1744);padding:1.3rem;border-radius:14px;color:#fff;text-align:center;font-size:1.5rem;font-weight:800;box-shadow:0 6px 24px rgba(213,0,0,0.45)}
.signal-neutral{background:linear-gradient(90deg,#616161,#9e9e9e);padding:1.3rem;border-radius:14px;color:#fff;text-align:center;font-size:1.5rem;font-weight:800}
.reminder-box{background:linear-gradient(90deg,#f59e0b,#fbbf24);padding:1.2rem;border-radius:12px;color:#1f2937;text-align:center;font-size:1.15rem;font-weight:bold;margin-top:1rem;animation:pulseGlow 1.5s infinite}
@keyframes pulseGlow {
    0% { transform: scale(1); box-shadow: 0 4px 15px rgba(245,158,11,0.4); }
    50% { transform: scale(1.02); box-shadow: 0 6px 25px rgba(245,158,11,0.8); }
    100% { transform: scale(1); box-shadow: 0 4px 15px rgba(245,158,11,0.4); }
}
.progress-box{background:rgba(30,41,59,0.95);border:1px solid rgba(34,211,238,0.4);border-radius:12px;padding:1rem;color:#22d3ee;font-family:monospace;font-size:0.95rem;margin:0.5rem 0;box-shadow:0 4px 15px rgba(34,211,238,0.2)}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(15,23,42,0.98), rgba(30,41,59,0.98)) !important;
    border-right: 1px solid rgba(34,211,238,0.15);
}
section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
hr { border-color: rgba(34,211,238,0.15) !important; }
</style>
""", unsafe_allow_html=True)

# حالة الجلسة
for k, v in [("logged_in", False), ("user", None), ("selected_account", None),
             ("last_signal", None), ("last_candles", None), ("connection_ready", False)]:
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================
# 🔐 شاشة الدخول
# ============================================================
if not st.session_state.logged_in:
    st.markdown('<div class="main-title">📈 إشارات OTC الاحترافية</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">منصة التداول الذكية — إصدار 2099</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="welcome-box">
        <h2>👋 أهلاً بك في منصة إشارات OTC</h2>
        <p>منصة تحليلية متقدمة تعتمد على <span class="highlight">تقاطع المتوسطات المتحركة (SMA)</span>.</p>
        <p>🔹 اتصال مباشر بخوادم <span class="highlight">PocketOption</span> عبر Socket.IO.</p>
        <p>🔹 دعم الحسابات <span class="highlight">التجريبية والحقيقية</span>.</p>
        <p style="margin-top:1rem;color:#94a3b8;font-size:0.92rem">🔐 يرجى تسجيل الدخول للمتابعة.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    email = st.text_input("📧 البريد الإلكتروني")
    pwd = st.text_input("🔒 كلمة المرور", type="password")
    if st.button("دخول", type="primary"):
        info = verify_login(email, pwd)
        if info:
            st.session_state.logged_in = True
            st.session_state.user = info
            st.session_state.selected_account = list(info["accounts"].keys())[0]
            st.rerun()
        else:
            st.error("❌ البريد أو كلمة المرور غير صحيحة.")
    st.caption("كلمة مرور التطبيق: `123456`")
    st.stop()


user = st.session_state.user

# ============================================================
# 🎛️ الشريط الجانبي
# ============================================================
with st.sidebar:
    st.markdown(f"### 👤 {user['email']}")
    keys = list(user["accounts"].keys())
    labels = [user["accounts"][k]["label"] for k in keys]
    idx = keys.index(st.session_state.selected_account) if st.session_state.selected_account in keys else 0
    sel = st.radio("🎯 اختر الحساب:", labels, index=idx)
    new_key = keys[labels.index(sel)]
    if new_key != st.session_state.selected_account:
        st.session_state.selected_account = new_key
        st.session_state.last_signal = None
        st.session_state.last_candles = None
        st.rerun()

    acc = user["accounts"][st.session_state.selected_account]
    st.caption(f"🆔 UID: `{acc['uid']}` | {'تجريبي' if acc['is_demo']==1 else 'حقيقي'}")

    if st.button("🚪 خروج"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.selected_account = None
        st.rerun()

    st.markdown("---")
    symbol = st.selectbox("📊 العملة", FOREX_SYMBOLS, index=0)
    period = st.selectbox("⏱️ الفريم (ثانية)", [60, 120, 300, 900], index=0)
    st.caption(f"🔌 المكتبة: **{LIB_TYPE}**")


st.markdown('<div class="main-title">📈 إشارات OTC الاحترافية</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">لوحة التحكم الرئيسية — تحليل حي للسوق</div>', unsafe_allow_html=True)

acc = user["accounts"][st.session_state.selected_account]

st.markdown(f"""
<div class="welcome-box">
    <h2>🌟 مرحباً بك، أيها المتداول</h2>
    <p>الحساب النشط: <span class="highlight">{acc['label']}</span> — UID: <span class="highlight">{acc['uid']}</span></p>
    <p>🕒 آخر دخول: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <p>🚀 اضغط على <span class="highlight">«بدء الاتصال»</span> لتهيئة الجلسة، ثم على <span class="highlight">«عرض الرصيد»</span>.</p>
</div>
""", unsafe_allow_html=True)

st.info(f"الحساب النشط: **{acc['label']}** — UID: `{acc['uid']}`")
st.markdown("---")


# ============================================================
# 🔌 بوابة الاتصال
# ============================================================
st.markdown("### 🔌 بوابة الاتصال بالمنصة")
col_conn1, col_conn2 = st.columns([1, 2])

with col_conn1:
    if st.button("🚀 بدء الاتصال (عد تنازلي 15 ثانية)", type="primary", key="connect_btn"):
        st.session_state.connection_ready = False
        ph = st.empty()
        total = 15
        for i in range(total, 0, -1):
            prog = (total - i) / total * 100
            ph.markdown(f"""
            <div style="background:linear-gradient(90deg,#1e3a8a,#3b82f6);padding:1.2rem;border-radius:12px;color:#fff;text-align:center;font-size:1.3rem;font-weight:bold">
                ⏳ جاري تجهيز الاتصال... <span style="font-size:2rem;color:#fbbf24">{i}</span> ثانية
                <div style="background:#0f172a;border-radius:8px;height:12px;margin-top:0.8rem;overflow:hidden">
                    <div style="width:{prog:.1f}%;height:100%;background:linear-gradient(90deg,#22d3ee,#3b82f6);transition:width 0.3s"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            time.sleep(1)
        ph.markdown("""
        <div style="background:linear-gradient(90deg,#00c853,#64dd17);padding:1.2rem;border-radius:12px;color:#fff;text-align:center;font-size:1.4rem;font-weight:bold">
            ✅ اكتمل العد التنازلي! الاتصال جاهز.
        </div>
        """, unsafe_allow_html=True)
        time.sleep(1.0)
        st.session_state.connection_ready = True
        st.rerun()

with col_conn2:
    if st.session_state.connection_ready:
        st.markdown("""
        <div class="reminder-box">
            🎯 <b>تذكير هام:</b><br>
            الآن اضغط على زر <b>«💰 عرض الرصيد»</b> لإكمال الاتصال.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("💡 اضغط **«بدء الاتصال»** أولاً.")

st.markdown("---")

c1, c2, c3 = st.columns(3)


# ============================================================
# 💰 زر الرصيد
# ============================================================
with c1:
    if st.button("💰 عرض الرصيد", type="primary"):
        ph = st.empty()

        def _p(msg):
            try:
                ph.markdown(f'<div class="progress-box">🟢 {msg}</div>', unsafe_allow_html=True)
            except Exception:
                pass

        try:
            with st.spinner("جاري سحب الرصيد..."):
                bal = asyncio.run(asyncio.wait_for(
                    _get_balance_async(acc, progress_cb=_p), timeout=90))
                ph.markdown(f'<div class="progress-box" style="border-color:#22c55e;color:#22c55e">✅ الرصيد: {bal}</div>',
                            unsafe_allow_html=True)
                st.success(f"💰 الرصيد: **{bal}**")
                st.session_state.connection_ready = False
        except asyncio.TimeoutError:
            ph.markdown('<div class="progress-box" style="border-color:#ef4444;color:#ef4444">❌ تجاوز 90 ثانية</div>',
                        unsafe_allow_html=True)
            st.error("⏱️ تجاوز الحد الزمني. راجع السجلات للتفاصيل.")
        except Exception as e:
            ph.markdown(f'<div class="progress-box" style="border-color:#ef4444;color:#ef4444">❌ فشل</div>',
                        unsafe_allow_html=True)
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())


# ============================================================
# 📈 زر الإشارة
# ============================================================
with c2:
    if st.button("📈 إشارة فورية"):
        ph = st.empty()

        def _p(msg):
            try:
                ph.markdown(f'<div class="progress-box">🟢 {msg}</div>', unsafe_allow_html=True)
            except Exception:
                pass

        try:
            with st.spinner("جاري التحليل..."):
                candles = asyncio.run(asyncio.wait_for(
                    _get_candles_async(acc, symbol, int(period), progress_cb=_p), timeout=90))
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                    st.rerun()
                else:
                    st.error("❌ لا توجد بيانات.")
        except asyncio.TimeoutError:
            st.error("⏱️ تجاوز 90 ثانية.")
        except Exception as e:
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())


# ============================================================
# 📊 زر آخر بيانات السوق
# ============================================================
with c3:
    if st.button("📊 آخر بيانات السوق"):
        ph = st.empty()

        def _p(msg):
            try:
                ph.markdown(f'<div class="progress-box">🟢 {msg}</div>', unsafe_allow_html=True)
            except Exception:
                pass

        try:
            with st.spinner("جاري الجلب..."):
                candles = asyncio.run(asyncio.wait_for(
                    _get_candles_async(acc, symbol, int(period), progress_cb=_p), timeout=90))
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                    st.rerun()
                else:
                    st.error("❌ لا توجد بيانات.")
        except asyncio.TimeoutError:
            st.error("⏱️ تجاوز 90 ثانية.")
        except Exception as e:
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())


st.markdown("---")

# ============================================================
# 📢 عرض الإشارة
# ============================================================
if st.session_state.last_signal:
    s = st.session_state.last_signal
    st.subheader("📢 الإشارة الحالية")
    cls = "signal-call" if "CALL" in s["signal"] else \
          ("signal-put" if "PUT" in s["signal"] else "signal-neutral")
    st.markdown(f'<div class="{cls}">{s["signal"]} — ثقة {s["confidence"]}%</div>',
                unsafe_allow_html=True)
    st.markdown(f"**💵 السعر:** `{s['price']:.5f}`")
    st.markdown(f"**📝 السبب:** {s['reason']}")


# ============================================================
# 📋 عرض الشموع
# ============================================================
if st.session_state.last_candles:
    cl = st.session_state.last_candles
    st.markdown("---")
    st.subheader(f"📋 آخر شموع — {symbol}")

    def _c(c, key):
        return c.get(key) if isinstance(c, dict) else getattr(c, key, None)

    try:
        closes = [_c(c, "close") for c in cl]
        closes = [x for x in closes if isinstance(x, (int, float))]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("السعر", f"{closes[-1]:.5f}")
        m2.metric("SMA(5)", f"{sum(closes[-5:])/5:.5f}")
        m3.metric("SMA(20)",
                  f"{sum(closes[-20:])/20:.5f}" if len(closes) >= 20 else f"{sum(closes)/len(closes):.5f}")
        m4.metric("عدد الشموع", len(cl))

        rows = []
        for c in cl[-10:]:
            t = _c(c, "time")
            try:
                dt = datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else ""
            except Exception:
                dt = str(t)
            rows.append({
                "الوقت": dt,
                "فتح":  f"{_c(c,'open'):.5f}"  if isinstance(_c(c,'open'), (int,float)) else "",
                "أعلى": f"{_c(c,'high'):.5f}"  if isinstance(_c(c,'high'), (int,float)) else "",
                "أدنى": f"{_c(c,'low'):.5f}"   if isinstance(_c(c,'low'),  (int,float)) else "",
                "إغلاق": f"{_c(c,'close'):.5f}" if isinstance(_c(c,'close'),(int,float)) else "",
            })
        st.dataframe(rows, use_container_width=True)

        try:
            import pandas as pd
            st.line_chart(pd.DataFrame({"الإغلاق": closes[-30:]}))
        except Exception:
            pass
    except Exception as e:
        st.error(f"خطأ في العرض: {e}")

st.caption(f"🕒 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
