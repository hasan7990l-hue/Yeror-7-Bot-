#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import traceback
import asyncio
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ============================================================
# 🔧 ترقيع asyncio
# ============================================================
try:
    _original_get_event_loop = asyncio.get_event_loop

    def _patched_get_event_loop():
        try:
            return _original_get_event_loop()
        except RuntimeError:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop
            except Exception:
                return asyncio.new_event_loop()

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
# ============================================================

import streamlit as st

# --- معالجة صلاحيات الكتابة ---
TMP_DIR = "/tmp/pocket_data"
os.makedirs(TMP_DIR, exist_ok=True)
os.environ["HOME"] = TMP_DIR
os.environ["TMPDIR"] = TMP_DIR
os.environ.setdefault("POCKETOPTION_HISTORY_PATH", TMP_DIR)

try:
    os.chdir(TMP_DIR)
except Exception:
    pass

for _sub in ["history", "history/data", "logs", "cache", "data"]:
    try:
        os.makedirs(os.path.join(TMP_DIR, _sub), exist_ok=True)
    except Exception:
        pass

_original_makedirs = os.makedirs
def _safe_makedirs(name, mode=0o777, exist_ok=False):
    try:
        return _original_makedirs(name, mode, exist_ok)
    except (PermissionError, FileExistsError, OSError):
        try:
            safe_name = os.path.join(TMP_DIR, os.path.basename(name))
            return _original_makedirs(safe_name, mode, exist_ok=True)
        except Exception:
            return None
os.makedirs = _safe_makedirs

# ============================================================
# 🔍 اكتشاف المكتبة — يفضل الجديدة أولاً
# ============================================================
LIB_TYPE = "none"
PocketOption = None
try:
    # 1) المكتبة الجديدة pocketoptionapi2
    from pocketoptionapi2.stable_api import PocketOption
    LIB_TYPE = "pocketoptionapi2"
except Exception:
    try:
        # 2) المكتبة الجديدة (نسخة Mastaaa) — نفس اسم الوحدة
        from pocketoptionapi.stable_api import PocketOption
        LIB_TYPE = "pocketoptionapi"
    except Exception:
        try:
            from pocket_option import PocketOptionClient, AuthorizationData
            LIB_TYPE = "pocket_option"
        except Exception:
            LIB_TYPE = "none"

try:
    os.makedirs = _original_makedirs
except Exception:
    pass

print(f"[INIT] LIB_TYPE = {LIB_TYPE}")


# ============================================================
# 👥 المستخدمون + الحسابات المتعددة
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


# ============================================================
# الإعدادات
# ============================================================
FOREX_SYMBOLS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC", "USDCAD-OTC",
                 "NZDUSD-OTC", "EURGBP-OTC",
                 "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]


# ============================================================
# دوال مساعدة
# ============================================================
def generate_signal(candles, short_period: int = 5, long_period: int = 20) -> Dict:
    if not candles or len(candles) < long_period + 1:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "بيانات غير كافية"}
    try:
        closes = [c[4] for c in candles] if isinstance(candles[0], (list, tuple)) else [c.close for c in candles]
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


def _ensure_event_loop():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception:
            pass


# ============================================================
# 🔌 تنظيف الاتصال القديم (إجباري)
# ============================================================
def cleanup_old_connection():
    """يقوم بإغلاق أي WebSocket/API قديم عالق في global_value."""
    cleaned = False
    try:
        import pocketoptionapi.global_value as gv
        # إغلاق websocket
        if hasattr(gv, "websocket") and gv.websocket is not None:
            try:
                gv.websocket.close()
                cleaned = True
            except Exception:
                pass
            gv.websocket = None
        # إغلاق api
        if hasattr(gv, "api") and gv.api is not None:
            try:
                gv.api.close()
                cleaned = True
            except Exception:
                pass
            gv.api = None
        # تصفير بعض الأعلام
        for flag in ["_is_connected", "connected", "is_connected"]:
            if hasattr(gv, flag):
                try:
                    setattr(gv, flag, False)
                except Exception:
                    pass
    except Exception as e:
        print(f"[CLEANUP] pocketoptionapi غير موجود أو فشل التنظيف: {e}")

    # محاولة تنظيف المكتبة الجديدة
    try:
        import pocketoptionapi2.global_value as gv2
        for attr in ["websocket", "api", "client", "_client"]:
            if hasattr(gv2, attr):
                obj = getattr(gv2, attr)
                if obj is not None:
                    try:
                        if hasattr(obj, "close"):
                            obj.close()
                            cleaned = True
                    except Exception:
                        pass
                    try:
                        setattr(gv2, attr, None)
                    except Exception:
                        pass
    except Exception:
        pass

    # إعادة تعيين event loop (بعض المكتبات تعلق عليه)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception:
        pass

    print(f"[CLEANUP] cleaned={cleaned}")
    return cleaned


def connect_pocket(session: str, uid: int, is_demo: int, platform: int):
    if LIB_TYPE == "none":
        return None, False, "لم يتم العثور على أي مكتبة PocketOption مثبتة.", "LIB_TYPE = none"

    # ============================
    # 🔧 تنظيف إجباري قبل أي اتصال
    # ============================
    cleanup_old_connection()
    time.sleep(1.5)

    _ensure_event_loop()

    try:
        # ============================
        # المكتبة القديمة pocketoptionapi
        # ============================
        if LIB_TYPE == "pocketoptionapi":
            _ensure_event_loop()
            # محاولة كلا التوقيعين
            try:
                client = PocketOption(ssid=session, demo=bool(is_demo))
            except TypeError:
                client = PocketOption(demo=bool(is_demo))

            # محاولة الاتصال بعدة طرق
            try:
                client.connect()
            except TypeError:
                try:
                    client.connect(session=session, uid=uid, isDemo=is_demo, platform=platform)
                except TypeError:
                    client.set_session(session, uid, is_demo, platform)
                    client.connect()
            return client, True, None, None

        # ============================
        # المكتبة الجديدة pocketoptionapi2
        # ============================
        elif LIB_TYPE == "pocketoptionapi2":
            _ensure_event_loop()
            client = PocketOption(demo=bool(is_demo))
            try:
                client.connect(session=session, uid=uid, isDemo=is_demo, platform=platform)
            except TypeError:
                try:
                    client.set_session(session, uid, is_demo, platform)
                    client.connect()
                except TypeError:
                    client.connect(session=session)
            return client, True, None, None

        # ============================
        # مكتبة pocket_option (نادرة)
        # ============================
        else:
            _ensure_event_loop()
            client = PocketOption(demo=bool(is_demo))
            try:
                client.set_session(session, uid, is_demo, platform)
                client.connect()
            except Exception:
                client.connect(session=session, uid=uid, isDemo=is_demo, platform=platform)
            return client, True, None, None

    except Exception as e:
        return None, False, f"فشل الاتصال: {str(e)}", traceback.format_exc()


def get_balance_safe(client):
    _ensure_event_loop()

    def _fetch():
        # محاولة عدة أسماء دوال
        for name in ["get_balance", "GetBalance", "balance", "getBalance"]:
            if hasattr(client, name):
                try:
                    val = getattr(client, name)
                    return val() if callable(val) else val
                except Exception:
                    continue
        return 0.0

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch)
            return future.result(timeout=20)
    except concurrent.futures.TimeoutError:
        return "⏱️ انتهت المهلة أثناء سحب الرصيد (20 ثانية)."
    except Exception as e:
        return f"خطأ: {e}"


def get_candles_safe(client, symbol, timeframe, limit=30):
    _ensure_event_loop()

    def _fetch():
        # محاولة عدة أسماء دوال
        for name in ["get_candles", "GetCandles", "getCandleData", "get_candle_data"]:
            if hasattr(client, name):
                try:
                    return getattr(client, name)(symbol, timeframe, limit)
                except Exception:
                    continue
        return []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch)
            return future.result(timeout=20)
    except concurrent.futures.TimeoutError:
        print("[CANDLES] timeout")
        return []
    except Exception as e:
        print(f"[CANDLES] error: {e}")
        return []


def verify_login(email: str, password: str) -> Optional[dict]:
    email = email.strip().lower()
    for stored_email, info in USERS.items():
        if stored_email.lower() == email and info["password"] == password:
            return {"email": stored_email, "accounts": info["accounts"]}
    return None


# ============================================================
# إعدادات الصفحة
# ============================================================
st.set_page_config(page_title="بوت إشارات OTC", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .main-title { font-size: 2.2rem; font-weight: bold; color: #00d4ff; text-align: center; }
    .stButton>button { width: 100%; height: 3rem; font-size: 1rem; font-weight: bold; border-radius: 10px; }
    .signal-call { background: linear-gradient(90deg,#00c853,#64dd17); padding: 1rem; border-radius: 10px; color: white; text-align: center; font-size: 1.4rem; font-weight: bold; }
    .signal-put { background: linear-gradient(90deg,#d50000,#ff1744); padding: 1rem; border-radius: 10px; color: white; text-align: center; font-size: 1.4rem; font-weight: bold; }
    .signal-neutral { background: linear-gradient(90deg,#616161,#9e9e9e); padding: 1rem; border-radius: 10px; color: white; text-align: center; font-size: 1.4rem; font-weight: bold; }
    .auth-box { background: #1e1e1e; padding: 2rem; border-radius: 15px; border: 1px solid #333; max-width: 480px; margin: 0 auto; }
    .user-badge { background: #0d47a1; color: white; padding: 0.6rem; border-radius: 8px; text-align: center; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 🔐 شاشة تسجيل الدخول
# ============================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "selected_account" not in st.session_state:
    st.session_state.selected_account = None


def get_active_account():
    if not st.session_state.user:
        return None
    acc_key = st.session_state.selected_account
    if not acc_key:
        acc_key = list(st.session_state.user["accounts"].keys())[0]
        st.session_state.selected_account = acc_key
    return st.session_state.user["accounts"][acc_key]


def auto_connect():
    if not st.session_state.user:
        return
    acc = get_active_account()
    if not acc:
        return
    with st.spinner(f"🔌 جاري الاتصال ({acc['label']})..."):
        client, ok, err, trc = connect_pocket(acc["session"], int(acc["uid"]), int(acc["is_demo"]), int(acc["platform"]))
        if ok:
            st.session_state.client = client
            st.session_state.connected = True
            st.session_state.last_error = None
            st.session_state.last_error_trace = None
        else:
            st.session_state.connected = False
            st.session_state.last_error = err
            st.session_state.last_error_trace = trc


if not st.session_state.logged_in:
    st.markdown('<div class="main-title">📈 بوت إشارات OTC</div>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.subheader("🔐 تسجيل الدخول")
    login_email = st.text_input("📧 البريد الإلكتروني", key="login_email")
    login_pass = st.text_input("🔒 كلمة المرور", type="password", key="login_pass")

    if st.button("دخول واتصال تلقائي", type="primary", key="btn_login"):
        if not login_email or not login_pass:
            st.warning("⚠️ أدخل البريد وكلمة المرور.")
        else:
            user_info = verify_login(login_email, login_pass)
            if user_info:
                st.session_state.logged_in = True
                st.session_state.user = user_info
                st.session_state.selected_account = list(user_info["accounts"].keys())[0]
                st.session_state.client = None
                st.session_state.connected = False
                st.session_state.last_error = None
                st.session_state.last_error_trace = None
                st.session_state.last_signal = None
                st.session_state.last_candles = None
                st.success("✅ تم الدخول. جاري الاتصال بالمنصة...")
                auto_connect()
                st.rerun()
            else:
                st.error("❌ البريد أو كلمة المرور غير صحيحة.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.caption("💡 كلمة مرور التطبيق: `123456`.")
    st.stop()


# ============================================================
# ✅ المستخدم مسجّل الدخول
# ============================================================
user = st.session_state.user

if "client" not in st.session_state:
    st.session_state.client = None
if "connected" not in st.session_state:
    st.session_state.connected = False
if "last_error" not in st.session_state:
    st.session_state.last_error = None
if "last_error_trace" not in st.session_state:
    st.session_state.last_error_trace = None
if "last_signal" not in st.session_state:
    st.session_state.last_signal = None
if "last_candles" not in st.session_state:
    st.session_state.last_candles = None


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.markdown(f'<div class="user-badge">👤 {user["email"]}</div>', unsafe_allow_html=True)

    acc_keys = list(user["accounts"].keys())
    acc_labels = [user["accounts"][k]["label"] for k in acc_keys]

    selected_label = st.radio(
        "🎯 اختر الحساب:",
        options=acc_labels,
        index=acc_keys.index(st.session_state.selected_account) if st.session_state.selected_account in acc_keys else 0,
        key="acc_radio"
    )
    new_acc_key = acc_keys[acc_labels.index(selected_label)]

    # عند تغيير الحساب → تنظيف + إعادة اتصال
    if new_acc_key != st.session_state.selected_account:
        st.session_state.selected_account = new_acc_key
        st.session_state.connected = False
        st.session_state.client = None
        cleanup_old_connection()
        st.rerun()

    active_acc = user["accounts"][st.session_state.selected_account]
    st.caption(f"🆔 UID: `{active_acc['uid']}` | {'تجريبي' if active_acc['is_demo'] == 1 else 'حقيقي'} | Platform: {active_acc['platform']}")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔌 إعادة اتصال"):
            auto_connect()
            st.rerun()
    with col_b:
        if st.button("🚪 خروج"):
            cleanup_old_connection()
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.selected_account = None
            st.session_state.client = None
            st.session_state.connected = False
            st.rerun()

    # زر قطع الاتصال
    if st.button("⛔ قطع الاتصال"):
        cleanup_old_connection()
        st.session_state.client = None
        st.session_state.connected = False
        st.success("✅ تم قطع الاتصال وتنظيفه.")
        st.rerun()

    st.markdown("---")
    st.subheader("📊 اختيار السوق")
    symbol_input = st.selectbox("العملة", FOREX_SYMBOLS, index=0)
    timeframe_input = st.selectbox(
        "الفريم (ثانية)",
        options=[60, 120, 300, 900],
        format_func=lambda x: {60: "1m", 120: "2m", 300: "5m", 900: "15m"}[x],
        index=0
    )
    duration_input = st.selectbox("مدة الصفقة (ثانية)", options=[60, 120, 300], index=0)

    st.markdown("---")
    st.caption(f"🔌 نوع المكتبة: **{LIB_TYPE}**")


# ============================================================
# الواجهة الرئيسية
# ============================================================
st.markdown('<div class="main-title">📈 بوت إشارات OTC — نسخة الويب</div>', unsafe_allow_html=True)
st.markdown(f"### مرحباً، `{user['email']}` 👋")

active_acc = user["accounts"][st.session_state.selected_account]
st.info(f"الحساب النشط: **{active_acc['label']}** — UID: `{active_acc['uid']}`")

if not st.session_state.connected and not st.session_state.last_error:
    auto_connect()

st.markdown("---")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🔌 اتصال بالمنصة", type="primary"):
        auto_connect()
        st.rerun()

with col2:
    if st.button("💰 عرض الرصيد"):
        if not st.session_state.connected or st.session_state.client is None:
            st.warning("⚠️ يجب الاتصال أولاً.")
        else:
            with st.spinner("جاري سحب الرصيد..."):
                bal = get_balance_safe(st.session_state.client)
                if isinstance(bal, str):
                    st.error(bal)
                else:
                    st.success(f"💰 الرصيد: **{bal:.2f}$**")

with col3:
    if st.button("📈 إشارة فورية"):
        if not st.session_state.connected or st.session_state.client is None:
            st.warning("⚠️ يجب الاتصال أولاً.")
        else:
            with st.spinner("جاري تحليل السوق..."):
                candles = get_candles_safe(st.session_state.client, symbol_input, int(timeframe_input), 30)
                if not candles:
                    st.error("❌ لا توجد بيانات.")
                else:
                    st.session_state.last_signal = generate_signal(candles)
                    st.session_state.last_candles = candles

with col4:
    if st.button("📊 آخر بيانات السوق"):
        if not st.session_state.connected or st.session_state.client is None:
            st.warning("⚠️ يجب الاتصال أولاً.")
        else:
            with st.spinner("جاري جلب البيانات..."):
                candles = get_candles_safe(st.session_state.client, symbol_input, int(timeframe_input), 30)
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                else:
                    st.error("❌ لا توجد بيانات.")

if st.session_state.last_error and not st.session_state.connected:
    with st.expander("🔍 تفاصيل الخطأ", expanded=False):
        st.code(st.session_state.last_error, language="text")
        if st.session_state.last_error_trace:
            st.code(st.session_state.last_error_trace, language="python")

st.markdown("---")

status_col1, status_col2, status_col3 = st.columns(3)
with status_col1:
    if st.session_state.connected:
        st.success("🟢 متصل بالمنصة")
    else:
        st.error("🔴 غير متصل")
with status_col2:
    st.info(f"📊 العملة: **{symbol_input}**")
with status_col3:
    tf_name = {60: "1m", 120: "2m", 300: "5m", 900: "15m"}.get(int(timeframe_input), f"{timeframe_input}s")
    st.info(f"⏱️ الفريم: **{tf_name}** | المدة: **{duration_input}s**")

st.markdown("---")

if st.session_state.last_signal:
    sig = st.session_state.last_signal
    st.subheader("📢 الإشارة الحالية")
    if "CALL" in sig["signal"]:
        st.markdown(f'<div class="signal-call">{sig["signal"]} — ثقة {sig["confidence"]}%</div>', unsafe_allow_html=True)
    elif "PUT" in sig["signal"]:
        st.markdown(f'<div class="signal-put">{sig["signal"]} — ثقة {sig["confidence"]}%</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="signal-neutral">{sig["signal"]} — ثقة {sig["confidence"]}%</div>', unsafe_allow_html=True)
    st.markdown(f"**💵 السعر:** `{sig['price']:.5f}`")
    st.markdown(f"**📝 السبب:** {sig['reason']}")

if st.session_state.last_candles:
    candles = st.session_state.last_candles
    st.markdown("---")
    st.subheader(f"📋 آخر 10 شموع — {symbol_input}")
    try:
        closes = [c[4] for c in candles]
        current_price = closes[-1]
        sma5 = sum(closes[-5:]) / 5
        sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else sum(closes) / len(closes)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("السعر الحالي", f"{current_price:.5f}")
        m2.metric("SMA(5)", f"{sma5:.5f}")
        m3.metric("SMA(20)", f"{sma20:.5f}")
        m4.metric("عدد الشموع", len(candles))
        rows = []
        for c in candles[-10:]:
            try:
                dt = datetime.fromtimestamp(c[0]).strftime("%H:%M:%S")
                rows.append({"الوقت": dt, "فتح": f"{c[1]:.5f}", "أعلى": f"{c[2]:.5f}",
                             "أدنى": f"{c[3]:.5f}", "إغلاق": f"{c[4]:.5f}"})
            except Exception:
                rows.append({"الوقت": str(c), "فتح": "", "أعلى": "", "أدنى": "", "إغلاق": ""})
        st.dataframe(rows, use_container_width=True)
        try:
            import pandas as pd
            st.line_chart(pd.DataFrame({"الإغلاق": closes[-30:]}))
        except Exception:
            pass
    except Exception as e:
        st.error(f"خطأ في عرض البيانات: {e}")

st.markdown("---")
st.caption(f"🕒 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("⚠️ لأغراض تعليمية فقط.")
