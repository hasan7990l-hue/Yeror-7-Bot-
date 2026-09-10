#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
تطبيق ويب Streamlit لإشارات OTC
- نظام تسجيل دخول / تسجيل حساب
- اتصال بـ Pocket Option عبر BinaryOptionsToolsV2
- دعم الحسابين التجريبي والحقيقي
"""

import os
import sys
import json
import time
import traceback
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

# ============================================================
# 🔧 ترقيع asyncio (ضروري لبيئة Streamlit)
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

# ============================================================
# 🔍 استيراد المكتبة الجديدة
# ============================================================
try:
    from BinaryOptionsToolsV2 import PocketOptionAsync
    LIB_TYPE = "BinaryOptionsToolsV2"
except Exception as e:
    LIB_TYPE = f"none: {e}"

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
            },
            "real": {
                "label": "🟢 حساب حقيقي",
                "session": '42["auth",{"session":"a%3A4%3A%7Bs%3A10%3A%22session_id%22%3Bs%3A32%3A%22dd9920ddafa73b322244df17e0ba2009%22%3Bs%3A10%3A%22ip_address%22%3Bs%3A11%3A%22169.224.4.6%22%3Bs%3A10%3A%22user_agent%22%3Bs%3A108%3A%22Mozilla%2F5.0%20%28Linux%3B%20Android%2013%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F120.0.0.0%20Mobile%20Safari%2F537.36%22%3Bs%3A13%3A%22last_activity%22%3Bi%3A1789007882%3B%7Decbc04e37c4181aa586dfbc8bbd9c12d","isDemo":0,"uid":101884312,"platform":1,"isFastHistory":true,"isOptimized":true}]',
                "uid": 101884312,
            },
        },
    },
}


# ============================================================
# الإعدادات
# ============================================================
FOREX_SYMBOLS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc",
                 "NZDUSD_otc", "EURGBP_otc",
                 "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]


# ============================================================
# دوال مساعدة
# ============================================================
def generate_signal(candles, short_period: int = 5, long_period: int = 20) -> Dict:
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


async def get_balance_async(ssid: str) -> float:
    """يجلب الرصيد باستخدام المكتبة الجديدة."""
    async with PocketOptionAsync(ssid) as api:
        await asyncio.sleep(5)  # انتظار لتحميل البيانات
        return await api.balance()


async def get_candles_async(ssid: str, asset: str, period: int, offset: int) -> List:
    """يجلب الشموع باستخدام المكتبة الجديدة."""
    async with PocketOptionAsync(ssid) as api:
        await asyncio.sleep(5)
        return await api.get_candles(asset, period, offset)


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


if not st.session_state.logged_in:
    st.markdown('<div class="main-title">📈 بوت إشارات OTC</div>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.subheader("🔐 تسجيل الدخول")
    login_email = st.text_input("📧 البريد الإلكتروني", key="login_email")
    login_pass = st.text_input("🔒 كلمة المرور", type="password", key="login_pass")

    if st.button("دخول", type="primary", key="btn_login"):
        if not login_email or not login_pass:
            st.warning("⚠️ أدخل البريد وكلمة المرور.")
        else:
            user_info = verify_login(login_email, login_pass)
            if user_info:
                st.session_state.logged_in = True
                st.session_state.user = user_info
                st.session_state.selected_account = list(user_info["accounts"].keys())[0]
                st.session_state.last_signal = None
                st.session_state.last_candles = None
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

    if new_acc_key != st.session_state.selected_account:
        st.session_state.selected_account = new_acc_key
        st.session_state.last_signal = None
        st.session_state.last_candles = None
        st.rerun()

    active_acc = user["accounts"][st.session_state.selected_account]
    st.caption(f"🆔 UID: `{active_acc['uid']}`")

    if st.button("🚪 خروج"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.selected_account = None
        st.session_state.last_signal = None
        st.session_state.last_candles = None
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

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("💰 عرض الرصيد", type="primary"):
        try:
            with st.spinner("جاري سحب الرصيد..."):
                bal = asyncio.run(get_balance_async(active_acc["session"]))
                st.success(f"💰 الرصيد: **{bal}**")
        except Exception as e:
            st.error(f"❌ فشل سحب الرصيد: {e}")
            st.code(traceback.format_exc(), language="python")

with col2:
    if st.button("📈 إشارة فورية"):
        try:
            with st.spinner("جاري تحليل السوق..."):
                candles = asyncio.run(get_candles_async(active_acc["session"], symbol_input, int(timeframe_input), 30))
                if not candles:
                    st.error("❌ لا توجد بيانات.")
                else:
                    st.session_state.last_signal = generate_signal(candles)
                    st.session_state.last_candles = candles
                    st.rerun()
        except Exception as e:
            st.error(f"❌ فشل جلب الشموع: {e}")
            st.code(traceback.format_exc(), language="python")

with col3:
    if st.button("📊 آخر بيانات السوق"):
        try:
            with st.spinner("جاري جلب البيانات..."):
                candles = asyncio.run(get_candles_async(active_acc["session"], symbol_input, int(timeframe_input), 30))
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                    st.rerun()
                else:
                    st.error("❌ لا توجد بيانات.")
        except Exception as e:
            st.error(f"❌ فشل جلب الشموع: {e}")
            st.code(traceback.format_exc(), language="python")

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
        closes = [c['close'] for c in candles]
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
        st.error(f"خطأ في عرض البيانات: {e}")

st.markdown("---")
st.caption(f"🕒 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("⚠️ لأغراض تعليمية فقط.")
