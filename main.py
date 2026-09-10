#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import asyncio
import inspect
import traceback
from datetime import datetime
from typing import Dict, List, Optional

# --- ترقيع asyncio لبيئة Streamlit ---
try:
    _original_get_event_loop = asyncio.get_event_loop
    def _patched_get_event_loop():
        try:
            return _original_get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
    asyncio.get_event_loop = _patched_get_event_loop
except Exception:
    pass

try:
    asyncio.get_event_loop()
except Exception:
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass

import streamlit as st

# --- مسارات الكتابة ---
TMP_DIR = "/tmp/pocket_data"
os.makedirs(TMP_DIR, exist_ok=True)
os.environ["HOME"] = TMP_DIR
os.environ["TMPDIR"] = TMP_DIR
try:
    os.chdir(TMP_DIR)
except Exception:
    pass

# --- استيراد المكتبة الجديدة ---
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
                "session": '42["auth",{"session":"a%3A4%3A%7Bs%3A10%3A%22session_id%22%3Bs%3A32%3A%22dd9920ddafa73b322244df17e0ba2009%22%3Bs%3A10%3A%22ip_address%22%3Bs%3A11%3A%22169.224.4.6%22%3Bs%3A10%3A%22user_agent%22%3Bs%3A108%3A%22Mozilla%2F5.0%20%28Linux%3B%20Android%2013%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F120.0.0.0%20Mobile%20Safari%2F537.36%22%3Bs%3A13%3A%22last_activity%22%3Bi%3A1789007882%3B%7Decbc04e37c4181aa586dfbc8bbd9c12d","isDemo":0,"uid":101884312,"platform":1,"isFastHistory":true,"isOptimized":true}]',
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
# دوال مساعدة
# ============================================================
def generate_signal(candles, short_period=5, long_period=20) -> Dict:
    if not candles or len(candles) < long_period + 1:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "بيانات غير كافية"}
    try:
        closes = [c['close'] for c in candles]
    except Exception:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "صيغة شموع غير معروفة"}
    current_price = closes[-1]
    sma_short = sum(closes[-short_period:]) / short_period
    sma_long = sum(closes[-long_period:]) / long_period
    prev_sma_short = sum(closes[-short_period-1:-1]) / short_period
    prev_sma_long = sum(closes[-long_period-1:-1]) / long_period
    diff = abs((sma_short - sma_long) / sma_long) * 100 if sma_long > 0 else 0
    confidence = min(90, 50 + diff * 3)
    if prev_sma_short <= prev_sma_long and sma_short > sma_long:
        return {"signal": "CALL 🟢", "confidence": round(confidence, 1), "price": current_price, "reason": f"SMA({short_period}) تجاوز SMA({long_period})"}
    elif prev_sma_short >= prev_sma_long and sma_short < sma_long:
        return {"signal": "PUT 🔴", "confidence": round(confidence, 1), "price": current_price, "reason": f"SMA({short_period}) نزل تحت SMA({long_period})"}
    return {"signal": "NEUTRAL ⚪", "confidence": 50.0, "price": current_price, "reason": "لا يوجد تقاطع واضح"}


# ============================================================
# 🔧 دالة انتظار الاتصال
# ============================================================
async def _wait_for_socket_connection(client, max_wait: float = 30.0, step: float = 0.5, progress_cb=None) -> bool:
    waited = 0.0
    while waited < max_wait:
        await asyncio.sleep(step)
        waited += step
        try:
            sio = (getattr(client, "sio", None)
                   or getattr(client, "_sio", None)
                   or getattr(client, "socket", None)
                   or getattr(client, "_socket", None))
            if sio is not None and getattr(sio, "connected", False):
                print(f"[DEBUG] Socket connected after {waited:.1f}s")
                return True
            if getattr(client, "is_connected", False):
                print(f"[DEBUG] client.is_connected=True after {waited:.1f}s")
                return True
        except Exception:
            pass
        if progress_cb and int(waited) % 2 == 0:
            try:
                progress_cb(f"⏳ انتظار الاتصال بـ Socket... ({waited:.0f}s / {max_wait:.0f}s)")
            except Exception:
                pass
    print(f"[DEBUG] Socket NOT connected after {max_wait}s")
    return False


# ============================================================
# 🆕 دوال تشخيص واتصال صريح
# ============================================================
def _diagnose_client(client) -> str:
    lines = []
    lines.append("=== تشخيص كائن PocketOptionClient ===")
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
            if callable(val):
                lines.append(f"  • {a}()  [{kind}]")
            else:
                lines.append(f"  • {a} = {kind}")
        except Exception as e:
            lines.append(f"  • {a} = <خطأ: {e}>")
    return "\n".join(lines)


# 🆕 عناوين WebSocket الرسمية لـ PocketOption
POCKETOPTION_WS_URLS = [
    "wss://api.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
    "wss://api-us.po.market/socket.io/?EIO=4&transport=websocket",
]


async def _explicit_connect(client, auth_data, progress_cb=None) -> dict:
    result = {"success": False, "used": None, "errors": []}

    try:
        client.authorization_data = auth_data
        print(f"[DEBUG] تم تعيين client.authorization_data مباشرة.")
    except Exception as e:
        result["errors"].append(f"set authorization_data: {e}")

    for url in POCKETOPTION_WS_URLS:
        try:
            if progress_cb:
                progress_cb(f"🔌 محاولة الاتصال بـ: {url.split('//')[1].split('/')[0]}...")
            print(f"[DEBUG] محاولة الاتصال بـ: {url}")
            ret = client.connect(
                url=url,
                auth=auth_data,
                wait=True,
                wait_timeout=20,
                retry=True,
            )
            if inspect.isawaitable(ret):
                await ret
            result["used"] = f"connect({url})"
            result["success"] = True
            print(f"[DEBUG] _explicit_connect نجحت باستخدام: connect({url})")
            return result
        except TypeError as te:
            result["errors"].append(f"connect({url}) TypeError: {te}")
            print(f"[DEBUG] TypeError على {url}: {te}")
        except Exception as e:
            result["errors"].append(f"connect({url}): {e}")
            print(f"[DEBUG] فشل الاتصال بـ {url}: {e}")

    return result


async def _get_balance_async(acc: dict, progress_cb=None) -> float:
    """
    الحصول على الرصيد - مع دعم تتبع حي للعملية.
    """
    def _p(msg):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass
        print(f"[PROGRESS] {msg}")

    _p("🔄 المرحلة 1/4: تهيئة العميل...")
    client = PocketOptionClient()

    session_id = acc["session"].split('"session":"')[1].split('"')[0]

    auth_data = AuthorizationData.model_validate({
        "session": session_id,
        "isDemo": acc["is_demo"],
        "uid": acc["uid"],
        "platform": acc["platform"],
        "isFastHistory": True,
        "isOptimized": True,
    })

    balance_value = None

    @client.on.balance_success_update
    async def on_balance_update(data):
        nonlocal balance_value
        print(f"[DEBUG] Balance update received: {data}")
        if isinstance(data, dict):
            balance_value = data.get('balance', data.get('amount', data.get('value', 0)))
        elif hasattr(data, 'balance'):
            balance_value = data.balance
        else:
            balance_value = data

    default_init(
        client,
        authorization=auth_data,
        sub_assets=["EURUSD_otc"],
        sub_period=60,
    )

    _p("🔄 المرحلة 2/4: الاتصال بـ WebSocket...")
    conn_result = await _explicit_connect(client, auth_data, progress_cb=_p)
    print(f"[DEBUG] _explicit_connect result: {conn_result}")

    if not conn_result.get("success"):
        # فشل الاتصال بكل العناوين
        diagnosis = _diagnose_client(client)
        raise TimeoutError(
            f"❌ فشل الاتصال بجميع عناوين WebSocket.\n"
            f"الأخطاء: {conn_result.get('errors')}\n\n"
            f"⚠️ ملاحظة: Streamlit Cloud قد يحجب اتصالات WebSocket الصادرة.\n\n"
            f"{diagnosis}"
        )

    _p("🔄 المرحلة 3/4: انتظار التفويض...")
    connected = await _wait_for_socket_connection(client, max_wait=15.0, step=0.5, progress_cb=_p)

    authorized = False
    if connected:
        try:
            if hasattr(client, "wait_for_authorization"):
                ret = client.wait_for_authorization()
                if inspect.isawaitable(ret):
                    authorized = await asyncio.wait_for(ret, timeout=10)
                else:
                    authorized = ret
                print(f"[DEBUG] wait_for_authorization -> {authorized}")
            if getattr(client, "is_authorized", False):
                authorized = True
        except Exception as e_auth:
            print(f"[DEBUG] wait_for_authorization فشل: {e_auth}")

    # قراءة احتياطية
    if balance_value is None:
        try:
            for attr in ("balance", "_balance", "account_balance", "current_balance"):
                val = getattr(client, attr, None)
                if val is not None and isinstance(val, (int, float)) and val >= 0:
                    balance_value = val
                    print(f"[DEBUG] Fallback balance from client.{attr} = {val}")
                    break
        except Exception:
            pass

    _p("🔄 المرحلة 4/4: طلب الرصيد...")
    last_emit_error = None
    if balance_value is None and connected:
        for attempt in range(1, 4):
            try:
                await client.emit.update_balance()
                print(f"[DEBUG] update_balance emitted attempt {attempt}")
                last_emit_error = None
                break
            except Exception as e_emit:
                last_emit_error = e_emit
                print(f"[DEBUG] update_balance attempt {attempt} failed: {e_emit}")
                await asyncio.sleep(1.5)

    # انتظار استلام الرصيد (5 ثوانٍ فقط)
    elapsed = 0
    while balance_value is None and elapsed < 5:
        await asyncio.sleep(0.5)
        elapsed += 0.5

    try:
        await client.close()
    except Exception:
        pass

    if balance_value is None:
        diagnosis = _diagnose_client(client)
        extra = f" | آخر خطأ إرسال: {last_emit_error}" if last_emit_error else ""
        extra += f" | متصل: {connected}"
        extra += f" | مُفوَّض: {authorized}"
        raise TimeoutError(
            f"لم يتم استلام الرصيد.{extra}\n\n{diagnosis}"
        )

    return float(balance_value)


async def _get_candles_async(acc: dict, asset: str, period: int, progress_cb=None) -> List:
    def _p(msg):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass
        print(f"[PROGRESS] {msg}")

    _p("🔄 تهيئة العميل للشموع...")
    client = PocketOptionClient()
    session_id = acc["session"].split('"session":"')[1].split('"')[0]

    auth_data = AuthorizationData.model_validate({
        "session": session_id,
        "isDemo": acc["is_demo"],
        "uid": acc["uid"],
        "platform": acc["platform"],
        "isFastHistory": True,
        "isOptimized": True,
    })

    default_init(
        client,
        authorization=auth_data,
        sub_assets=[asset],
        sub_period=period,
    )

    _p("🔌 الاتصال للشموع...")
    await _explicit_connect(client, auth_data, progress_cb=_p)
    await _wait_for_socket_connection(client, max_wait=15.0, step=0.5, progress_cb=_p)

    try:
        if hasattr(client, "wait_for_authorization"):
            ret = client.wait_for_authorization()
            if inspect.isawaitable(ret):
                await asyncio.wait_for(ret, timeout=10)
    except Exception:
        pass

    _p("📊 جلب الشموع...")
    candles = await client.get_candles(Asset(asset), period, 30)
    try:
        await client.close()
    except Exception:
        pass
    return candles


def verify_login(email, password):
    email = email.strip().lower()
    for stored, info in USERS.items():
        if stored.lower() == email and info["password"] == password:
            return {"email": stored, "accounts": info["accounts"]}
    return None


# ============================================================
# واجهة Streamlit
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
    letter-spacing: 0.5px;
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
.welcome-box::before {
    content: "";
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: conic-gradient(from 0deg, transparent, rgba(34,211,238,0.12), transparent 30%);
    animation: rotateGlow 8s linear infinite;
    pointer-events: none;
}
@keyframes rotateGlow {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
.welcome-box h2 {
    margin: 0 0 0.5rem 0;
    font-size: 1.6rem;
    color: #22d3ee;
    position: relative;
    z-index: 1;
}
.welcome-box p {
    margin: 0.3rem 0;
    font-size: 1.02rem;
    color: #cbd5e1;
    position: relative;
    z-index: 1;
    line-height: 1.7;
}
.welcome-box .highlight {
    color: #fbbf24;
    font-weight: 700;
}
.info-card {
    background: rgba(30,41,59,0.75);
    border: 1px solid rgba(148,163,184,0.15);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    backdrop-filter: blur(8px);
    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    color: #e2e8f0;
}
.stButton > button {
    background: linear-gradient(135deg, #1e3a8a, #3b82f6) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.6rem 1rem !important;
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
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #22d3ee, #67e8f9) !important;
    box-shadow: 0 8px 26px rgba(34,211,238,0.7) !important;
}
.signal-call{background:linear-gradient(90deg,#00c853,#64dd17);padding:1.3rem;border-radius:14px;color:#fff;text-align:center;font-size:1.5rem;font-weight:800;box-shadow:0 6px 24px rgba(0,200,83,0.45)}
.signal-put{background:linear-gradient(90deg,#d50000,#ff1744);padding:1.3rem;border-radius:14px;color:#fff;text-align:center;font-size:1.5rem;font-weight:800;box-shadow:0 6px 24px rgba(213,0,0,0.45)}
.signal-neutral{background:linear-gradient(90deg,#616161,#9e9e9e);padding:1.3rem;border-radius:14px;color:#fff;text-align:center;font-size:1.5rem;font-weight:800}
@keyframes pulseGlow {
    0% { transform: scale(1); box-shadow: 0 4px 15px rgba(245,158,11,0.4); }
    50% { transform: scale(1.02); box-shadow: 0 6px 25px rgba(245,158,11,0.8); }
    100% { transform: scale(1); box-shadow: 0 4px 15px rgba(245,158,11,0.4); }
}
.reminder-box{animation:pulseGlow 1.5s infinite;background:linear-gradient(90deg,#f59e0b,#fbbf24);padding:1.2rem;border-radius:12px;color:#1f2937;text-align:center;font-size:1.15rem;font-weight:bold;margin-top:1rem}
.progress-box{background:rgba(30,41,59,0.95);border:1px solid rgba(34,211,238,0.4);border-radius:12px;padding:1rem;color:#22d3ee;font-family:monospace;font-size:0.95rem;margin:0.5rem 0;box-shadow:0 4px 15px rgba(34,211,238,0.2)}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(15,23,42,0.98), rgba(30,41,59,0.98)) !important;
    border-right: 1px solid rgba(34,211,238,0.15);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #22d3ee, #3b82f6);
}
hr { border-color: rgba(34,211,238,0.15) !important; }
</style>
""", unsafe_allow_html=True)

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user" not in st.session_state: st.session_state.user = None
if "selected_account" not in st.session_state: st.session_state.selected_account = None
if "last_signal" not in st.session_state: st.session_state.last_signal = None
if "last_candles" not in st.session_state: st.session_state.last_candles = None


if not st.session_state.logged_in:
    st.markdown('<div class="main-title">📈 إشارات OTC الاحترافية</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">منصة التداول الذكية — إصدار 2099</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="welcome-box">
        <h2>👋 أهلاً بك في منصة إشارات OTC</h2>
        <p>منصة تحليلية متقدمة تعتمد على <span class="highlight">تقاطع المتوسطات المتحركة (SMA)</span> لتوليد إشارات دقيقة على أزواج العملات.</p>
        <p>🔹 اتصال مباشر بخوادم <span class="highlight">PocketOption</span> عبر Socket.IO.</p>
        <p>🔹 دعم الحسابات <span class="highlight">التجريبية والحقيقية</span>.</p>
        <p>🔹 تحليل فوري، شموع حية، وإشارات لحظية.</p>
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
if "last_signal" not in st.session_state: st.session_state.last_signal = None
if "last_candles" not in st.session_state: st.session_state.last_candles = None

with st.sidebar:
    st.markdown(f"### 👤 {user['email']}")
    keys = list(user["accounts"].keys())
    labels = [user["accounts"][k]["label"] for k in keys]
    sel = st.radio("🎯 اختر الحساب:", labels,
                   index=keys.index(st.session_state.selected_account) if st.session_state.selected_account in keys else 0)
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
    <p>🚀 اضغط على <span class="highlight">«بدء الاتصال»</span> لتهيئة الجلسة، ثم على <span class="highlight">«عرض الرصيد»</span> لإكمال الاتصال.</p>
</div>
""", unsafe_allow_html=True)

st.info(f"الحساب النشط: **{acc['label']}** — UID: `{acc['uid']}`")
st.markdown("---")

# ============================================================
# ✅ بوابة الاتصال + العد التنازلي + التذكير
# ============================================================
if "connection_ready" not in st.session_state: st.session_state.connection_ready = False

st.markdown("### 🔌 بوابة الاتصال بالمنصة")

col_conn1, col_conn2 = st.columns([1, 2])

with col_conn1:
    if st.button("🚀 بدء الاتصال (عد تنازلي 15 ثانية)", type="primary", key="connect_countdown_btn"):
        st.session_state.connection_ready = False

        countdown_placeholder = st.empty()
        total_seconds = 15

        for i in range(total_seconds, 0, -1):
            progress = (total_seconds - i) / total_seconds * 100
            countdown_placeholder.markdown(
                f"""
                <div style="background:linear-gradient(90deg,#1e3a8a,#3b82f6);padding:1.2rem;border-radius:12px;color:#fff;text-align:center;font-size:1.3rem;font-weight:bold;box-shadow:0 4px 15px rgba(59,130,246,0.4)">
                    ⏳ جاري تجهيز الاتصال... <span style="font-size:2rem;color:#fbbf24">{i}</span> ثانية
                    <div style="background:#0f172a;border-radius:8px;height:12px;margin-top:0.8rem;overflow:hidden">
                        <div style="width:{progress:.1f}%;height:100%;background:linear-gradient(90deg,#22d3ee,#3b82f6);transition:width 0.3s"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            time.sleep(1)

        countdown_placeholder.markdown(
            """
            <div style="background:linear-gradient(90deg,#00c853,#64dd17);padding:1.2rem;border-radius:12px;color:#fff;text-align:center;font-size:1.4rem;font-weight:bold;box-shadow:0 4px 15px rgba(0,200,83,0.4)">
                ✅ اكتمل العد التنازلي! الاتصال جاهز.
            </div>
            """,
            unsafe_allow_html=True
        )
        time.sleep(1.2)
        st.session_state.connection_ready = True
        st.rerun()

with col_conn2:
    if st.session_state.connection_ready:
        st.markdown(
            """
            <div class="reminder-box">
                🎯 <b>تذكير هام:</b><br>
                الآن اضغط على زر <b>«💰 عرض الرصيد»</b> بالأسفل لإكمال الاتصال فعلياً وسحب الرصيد من المنصة.
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.info("💡 اضغط على زر **«بدء الاتصال»** لبدء العد التنازلي. بعد انتهائه ستظهر لك رسالة تذكير لسحب الرصيد.")

st.markdown("---")


c1, c2, c3 = st.columns(3)

# ============================================================
# 🆕 قسم الرصيد مع شريط تقدم حي
# ============================================================
with c1:
    if st.button("💰 عرض الرصيد", type="primary"):
        # 🆕 مكان مخصص لعرض المراحل الحية
        progress_placeholder = st.empty()

        def _on_progress(msg):
            """دالة تُستدعى من داخل العملية لتحديث الشاشة فورياً."""
            try:
                progress_placeholder.markdown(
                    f'<div class="progress-box">🟢 {msg}</div>',
                    unsafe_allow_html=True
                )
            except Exception:
                pass

        try:
            with st.spinner("جاري سحب الرصيد (قد يستغرق حتى 60 ثانية)..."):
                # 🆕 حد زمني صارم: 90 ثانية كحد أقصى
                bal = asyncio.run(
                    asyncio.wait_for(
                        _get_balance_async(acc, progress_cb=_on_progress),
                        timeout=90
                    )
                )
                progress_placeholder.markdown(
                    f'<div class="progress-box" style="border-color:#22c55e;color:#22c55e">✅ اكتمل بنجاح! الرصيد: {bal}</div>',
                    unsafe_allow_html=True
                )
                st.success(f"💰 الرصيد: **{bal}**")
                st.session_state.connection_ready = False
        except asyncio.TimeoutError:
            progress_placeholder.markdown(
                '<div class="progress-box" style="border-color:#ef4444;color:#ef4444">❌ تجاوز الحد الزمني (90 ثانية)</div>',
                unsafe_allow_html=True
            )
            st.error("⏱️ **تجاوز الحد الزمني (90 ثانية).**\n\nالسبب المحتمل: Streamlit Cloud قد يحجب اتصالات WebSocket الصادرة. جرّب:")
            st.markdown("""
            - 🔹 استخدم **VPS** أو **خادم محلي** بدلاً من Streamlit Cloud.
            - 🔹 تحقق من صلاحية الجلسة (Session) — انسخ جلسة جديدة من PocketOption عبر F12 → Network → WebSocket.
            - 🔹 راجع السجلات (Logs) في Streamlit Cloud لمعرفة آخر رسالة `[PROGRESS]`.
            """)
        except Exception as e:
            progress_placeholder.markdown(
                f'<div class="progress-box" style="border-color:#ef4444;color:#ef4444">❌ فشل: {str(e)[:150]}...</div>',
                unsafe_allow_html=True
            )
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())

# ============================================================
# 🆕 قسم الإشارة الفورية مع شريط تقدم حي
# ============================================================
with c2:
    if st.button("📈 إشارة فورية"):
        progress_placeholder2 = st.empty()

        def _on_progress2(msg):
            try:
                progress_placeholder2.markdown(
                    f'<div class="progress-box">🟢 {msg}</div>',
                    unsafe_allow_html=True
                )
            except Exception:
                pass

        try:
            with st.spinner("جاري التحليل..."):
                candles = asyncio.run(
                    asyncio.wait_for(
                        _get_candles_async(acc, symbol, int(period), progress_cb=_on_progress2),
                        timeout=90
                    )
                )
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                    st.rerun()
                else:
                    st.error("❌ لا توجد بيانات.")
        except asyncio.TimeoutError:
            st.error("⏱️ تجاوز الحد الزمني (90 ثانية). Streamlit Cloud قد يحجب WebSocket.")
        except Exception as e:
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())

with c3:
    if st.button("📊 آخر بيانات السوق"):
        progress_placeholder3 = st.empty()

        def _on_progress3(msg):
            try:
                progress_placeholder3.markdown(
                    f'<div class="progress-box">🟢 {msg}</div>',
                    unsafe_allow_html=True
                )
            except Exception:
                pass

        try:
            with st.spinner("جاري الجلب..."):
                candles = asyncio.run(
                    asyncio.wait_for(
                        _get_candles_async(acc, symbol, int(period), progress_cb=_on_progress3),
                        timeout=90
                    )
                )
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                    st.rerun()
                else:
                    st.error("❌ لا توجد بيانات.")
        except asyncio.TimeoutError:
            st.error("⏱️ تجاوز الحد الزمني (90 ثانية).")
        except Exception as e:
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())

st.markdown("---")

if st.session_state.last_signal:
    s = st.session_state.last_signal
    st.subheader("📢 الإشارة الحالية")
    cls = "signal-call" if "CALL" in s["signal"] else ("signal-put" if "PUT" in s["signal"] else "signal-neutral")
    st.markdown(f'<div class="{cls}">{s["signal"]} — ثقة {s["confidence"]}%</div>', unsafe_allow_html=True)
    st.markdown(f"**💵 السعر:** `{s['price']:.5f}`")
    st.markdown(f"**📝 السبب:** {s['reason']}")

if st.session_state.last_candles:
    cl = st.session_state.last_candles
    st.markdown("---")
    st.subheader(f"📋 آخر شموع — {symbol}")
    try:
        closes = [c['close'] for c in cl]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("السعر", f"{closes[-1]:.5f}")
        m2.metric("SMA(5)", f"{sum(closes[-5:])/5:.5f}")
        m3.metric("SMA(20)", f"{sum(closes[-20:])/20 if len(closes)>=20 else sum(closes)/len(closes):.5f}")
        m4.metric("عدد الشموع", len(cl))
        rows = []
        for c in cl[-10:]:
            try:
                dt = datetime.fromtimestamp(c['time']).strftime("%H:%M:%S")
                rows.append({"الوقت": dt, "فتح": f"{c['open']:.5f}", "أعلى": f"{c['high']:.5f}",
                             "أدنى": f"{c['low']:.5f}", "إغلاق": f"{c['close']:.5f}"})
            except Exception:
                rows.append({"الوقت": str(c), "فتح": "", "أعلى": "", "أدنى": "", "إغلاق": ""})
        st.dataframe(rows, use_container_width=True)
        try:
            import pandas as pd
            st.line_chart(pd.DataFrame({"الإغلاق": closes[-30:]}))
        except Exception:
            pass
    except Exception as e:
        st.error(f"خطأ في العرض: {e}")

st.caption(f"🕒 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
