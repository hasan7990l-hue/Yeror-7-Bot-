#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
تطبيق ويب Streamlit لإشارات OTC
- تسجيل دخول بالإيميل/كلمة المرور
- كل حساب مرتبط بـ SESSION/UID خاص به
- اتصال تلقائي بعد الدخول
"""

import os
import sys
import json
import time
import hashlib
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

LIB_TYPE = "none"
PocketOption = None
try:
    from pocketoptionapi2.stable_api import PocketOption
    LIB_TYPE = "pocketoptionapi2"
except Exception:
    try:
        from pocketoptionapi.stable_api import PocketOption
        LIB_TYPE = "pocketoptionapi"
    except Exception:
        LIB_TYPE = "none"

try:
    os.makedirs = _original_makedirs
except Exception:
    pass


# ============================================================
# 👥 جدول المستخدمين — عدّل هنا لإضافة حساباتك
# ============================================================
# كل مستخدم: email → {password, session, uid, is_demo, platform}
#
# ⚠️ ملاحظة أمنية: كلمة المرور مكتوبة هنا كنص صريح لأن الكود خاص بك.
#    إذا أردت زيادة الأمان، استخدم دالة hash بسيطة أدناه.
USERS: Dict[str, Dict] = {
    "b1b2b3h45h@gmail.com": {
        "password": "ضع_كلمة_المرور_هنا",
        "session": '42["auth",{"session":"vtftn12e6f5f5008moitsd6skl","isDemo":1,"uid":27658142,"platform":2,"isFastHistory":true,"isOptimized":true}]',
        "uid": 27658142,
        "is_demo": 1,
        "platform": 2,
    },
    # ======== إضافة مستخدم آخر (اختياري) ========
    # "user2@example.com": {
    #     "password": "another_password",
    #     "session": '42["auth",{"session":"xxxxx","isDemo":1,"uid":12345678,"platform":2}]',
    #     "uid": 12345678,
    #     "is_demo": 1,
    #     "platform": 2,
    # },
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


def connect_pocket(session: str, uid: int, is_demo: int, platform: int):
    if LIB_TYPE == "none":
        return None, False, "لم يتم العثور على أي مكتبة PocketOption مثبتة.", "LIB_TYPE = none"
    _ensure_event_loop()
    try:
        if LIB_TYPE == "pocketoptionapi":
            _ensure_event_loop()
            client = PocketOption(ssid=session, demo=bool(is_demo))
            client.connect()
            return client, True, None, None
        elif LIB_TYPE == "pocketoptionapi2":
            _ensure_event_loop()
            client = PocketOption(demo=bool(is_demo))
            try:
                client.connect(session=session, uid=uid, isDemo=is_demo, platform=platform)
            except TypeError:
                client.set_session(session, uid, is_demo, platform)
                client.connect()
            return client, True, None, None
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
        if hasattr(client, "get_balance"):
            return client.get_balance()
        if hasattr(client, "GetBalance"):
            return client.GetBalance()
        return 0.0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch)
            return future.result(timeout=15)
    except concurrent.futures.TimeoutError:
        return "⏱️ انتهت المهلة أثناء سحب الرصيد."
    except Exception as e:
        return f"خطأ: {e}"


def get_candles_safe(client, symbol, timeframe, limit=30):
    _ensure_event_loop()
    def _fetch():
        if hasattr(client, "get_candles"):
            return client.get_candles(symbol, timeframe, limit)
        if hasattr(client, "GetCandles"):
            return client.GetCandles(symbol, timeframe, limit)
        return []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch)
            return future.result(timeout=15)
    except concurrent.futures.TimeoutError:
        return []
    except Exception:
        return []


def verify_login(email: str, password: str) -> Optional[dict]:
    """يتحقق من بيانات الدخول ويُرجع بيانات المستخدم أو None."""
    email = email.strip().lower()
    for stored_email, info in USERS.items():
        if stored_email.lower() == email and info["password"] == password:
            return {"email": stored_email, **info}
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


def auto_connect():
    """يتصل تلقائياً باستخدام مفاتيح المستخدم الحالي."""
    if not st.session_state.user:
        return
    u = st.session_state.user
    with st.spinner("🔌 جاري الاتصال التلقائي بالمنصة..."):
        client, ok, err, trc = connect_pocket(u["session"], int(u["uid"]), int(u["is_demo"]), int(u["platform"]))
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
                # تهيئة الحالة
                st.session_state.client = None
                st.session_state.connected = False
                st.session_state.last_error = None
                st.session_state.last_error_trace = None
                st.session_state.last_signal = None
                st.session_state.last_candles = None
                st.success("✅ تم الدخول. جاري الاتصال بالمنصة...")
                # اتصال تلقائي
                auto_connect()
                st.rerun()
            else:
                st.error("❌ البريد أو كلمة المرور غير صحيحة.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.caption("💡 إذا نسيت كلمة المرور، عدّل قاموس `USERS` في الكود.")
    st.stop()


# ============================================================
# ✅ المستخدم مسجّل الدخول
# ============================================================
user = st.session_state.user

# تهيئة الحالة إذا لم تكن موجودة
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
    st.caption(f"🆔 UID: `{user['uid']}` | {'تجريبي' if user['is_demo'] == 1 else 'حقيقي'}")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔌 إعادة اتصال"):
            auto_connect()
            st.rerun()
    with col_b:
        if st.button("🚪 خروج"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.client = None
            st.session_state.connected = False
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

    # معلومات المفاتيح (مخفية جزئياً)
    with st.expander("🔑 المفاتيح المرتبطة بحسابك"):
        sess_short = user["session"][:60] + "..." if len(user["session"]) > 60 else user["session"]
        st.code(sess_short, language="text")
        st.text(f"UID: {user['uid']}")


# ============================================================
# الواجهة الرئيسية
# ============================================================
st.markdown('<div class="main-title">📈 بوت إشارات OTC — نسخة الويب</div>', unsafe_allow_html=True)
st.markdown(f"### مرحباً، `{user['email']}` 👋")

# محاولة اتصال تلقائي عند أول دخول
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
    st.success("🟢 متصل بالمنصة") if st.session_state.connected else st.error("🔴 غير متصل")
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
