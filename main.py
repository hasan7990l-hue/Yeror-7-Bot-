#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
تطبيق ويب Streamlit لإشارات OTC
- نظام تسجيل دخول / تسجيل حساب
- قاعدة بيانات SQLite محلية
- لا يحتاج Telegram / Flask
"""

import os
import sys
import json
import time
import sqlite3
import hashlib
import secrets
import traceback
import asyncio
import threading
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ============================================================
# 🔧 ترقيع asyncio BEFORE أي استيراد آخر
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

# --- ترقيع آمن لـ os.makedirs ---
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

# --- تحديد نوع المكتبة ---
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
# 🗄️ قاعدة البيانات
# ============================================================
DB_PATH = os.path.join(TMP_DIR, "users.db")


def _db_connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            session_key TEXT,
            uid INTEGER,
            is_demo INTEGER DEFAULT 1,
            platform INTEGER DEFAULT 2,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)
    conn.commit()
    conn.close()


def hash_password(password: str, salt: str = None) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return h.hex(), salt


def register_user(email: str, password: str) -> Tuple[bool, str]:
    email = email.strip().lower()
    if not email or "@" not in email or "." not in email:
        return False, "❌ البريد الإلكتروني غير صالح."
    if len(password) < 6:
        return False, "❌ كلمة المرور يجب أن تكون 6 أحرف على الأقل."
    try:
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cur.fetchone():
            conn.close()
            return False, "⚠️ هذا البريد مسجّل مسبقاً. جرّب تسجيل الدخول."
        pwd_hash, salt = hash_password(password)
        cur.execute("""
            INSERT INTO users (email, password_hash, salt, created_at)
            VALUES (?, ?, ?, ?)
        """, (email, pwd_hash, salt, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True, "✅ تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن."
    except Exception as e:
        return False, f"❌ خطأ في التسجيل: {e}"


def login_user(email: str, password: str) -> Tuple[bool, Optional[dict], str]:
    email = email.strip().lower()
    try:
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return False, None, "❌ البريد أو كلمة المرور غير صحيحة."
        pwd_hash, _ = hash_password(password, row["salt"])
        if pwd_hash != row["password_hash"]:
            conn.close()
            return False, None, "❌ البريد أو كلمة المرور غير صحيحة."
        cur.execute("UPDATE users SET last_login = ? WHERE id = ?",
                    (datetime.now().isoformat(), row["id"]))
        conn.commit()
        user = dict(row)
        conn.close()
        return True, user, "✅ تم تسجيل الدخول."
    except Exception as e:
        return False, None, f"❌ خطأ في الدخول: {e}"


def update_user_session(user_id: int, session_key: str, uid: int, is_demo: int, platform: int) -> bool:
    try:
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
            SET session_key = ?, uid = ?, is_demo = ?, platform = ?
            WHERE id = ?
        """, (session_key, uid, is_demo, platform, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def load_user_session(user_id: int) -> Optional[dict]:
    try:
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute("SELECT session_key, uid, is_demo, platform FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if row and row["session_key"]:
            return dict(row)
        return None
    except Exception:
        return None


init_db()

# ============================================================
# الإعدادات
# ============================================================
SESSION_DEFAULT = ''
UID_DEFAULT = 0
IS_DEMO_DEFAULT = 1
PLATFORM_DEFAULT = 2

FOREX_SYMBOLS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC", "USDCAD-OTC",
                 "NZDUSD-OTC", "EURGBP-OTC",
                 "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]

# ============================================================
# دوال مساعدة (نفس المنطق السابق)
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
        return "⏱️ انتهت المهلة أثناء سحب الرصيد (15 ثانية)."
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
        print("⏱️ انتهت مهلة جلب الشموع (15 ثانية).")
        return []
    except Exception as e:
        print(f"خطأ في جلب الشموع: {e}")
        return []


# ============================================================
# إعدادات الصفحة
# ============================================================
st.set_page_config(
    page_title="بوت إشارات OTC",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
# 🔐 نظام الدخول / التسجيل
# ============================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.logged_in:
    st.markdown('<div class="main-title">📈 بوت إشارات OTC</div>', unsafe_allow_html=True)
    st.markdown("---")

    tab_login, tab_register = st.tabs(["🔑 تسجيل الدخول", "📝 حساب جديد"])

    with tab_login:
        st.markdown('<div class="auth-box">', unsafe_allow_html=True)
        st.subheader("تسجيل الدخول")
        login_email = st.text_input("📧 البريد الإلكتروني", key="login_email")
        login_pass = st.text_input("🔒 كلمة المرور", type="password", key="login_pass")
        if st.button("دخول", type="primary", key="btn_login"):
            if not login_email or not login_pass:
                st.warning("⚠️ أدخل البريد وكلمة المرور.")
            else:
                ok, user, msg = login_user(login_email, login_pass)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab_register:
        st.markdown('<div class="auth-box">', unsafe_allow_html=True)
        st.subheader("إنشاء حساب جديد")
        reg_email = st.text_input("📧 البريد الإلكتروني", key="reg_email")
        reg_pass = st.text_input("🔒 كلمة المرور (6 أحرف على الأقل)", type="password", key="reg_pass")
        reg_pass2 = st.text_input("🔒 تأكيد كلمة المرور", type="password", key="reg_pass2")
        if st.button("تسجيل", type="primary", key="btn_register"):
            if not reg_email or not reg_pass or not reg_pass2:
                st.warning("⚠️ املأ جميع الحقول.")
            elif reg_pass != reg_pass2:
                st.error("❌ كلمتا المرور غير متطابقتين.")
            else:
                ok, msg = register_user(reg_email, reg_pass)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)

    st.stop()


# ============================================================
# المستخدم مسجّل الدخول — تحميل جلسته المحفوظة
# ============================================================
user = st.session_state.user
saved = load_user_session(user["id"])

if "session_input" not in st.session_state:
    st.session_state.session_input = (saved["session_key"] if saved else "") or SESSION_DEFAULT
if "uid_input" not in st.session_state:
    st.session_state.uid_input = int((saved["uid"] if saved else UID_DEFAULT) or UID_DEFAULT)
if "is_demo_input" not in st.session_state:
    st.session_state.is_demo_input = int((saved["is_demo"] if saved else IS_DEMO_DEFAULT) or IS_DEMO_DEFAULT)
if "platform_input" not in st.session_state:
    st.session_state.platform_input = int((saved["platform"] if saved else PLATFORM_DEFAULT) or PLATFORM_DEFAULT)

# --- باقي State ---
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
    # شريط المستخدم
    st.markdown(f'<div class="user-badge">👤 {user["email"]}</div>', unsafe_allow_html=True)
    if st.button("🚪 تسجيل الخروج"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.session_state.client = None
        st.session_state.connected = False
        st.rerun()

    st.markdown("---")
    st.header("⚙️ الإعدادات")

    st.subheader("🔑 بيانات الاتصال")
    session_input = st.text_area(
        "SESSION",
        value=st.session_state.session_input,
        height=100,
        help="الصق مفتاح الجلسة من Pocket Option"
    )
    uid_input = st.number_input("UID", value=st.session_state.uid_input, step=1)
    is_demo_input = st.selectbox(
        "نوع الحساب",
        options=[1, 0],
        format_func=lambda x: "تجريبي" if x == 1 else "حقيقي",
        index=0 if st.session_state.is_demo_input == 1 else 1
    )
    platform_input = st.number_input("Platform", value=st.session_state.platform_input, step=1)

    # زر حفظ المفتاح في حساب المستخدم
    if st.button("💾 حفظ المفتاح في حسابي", type="primary"):
        if not session_input.strip():
            st.warning("⚠️ أدخل مفتاح SESSION أولاً.")
        else:
            ok = update_user_session(user["id"], session_input.strip(), int(uid_input), int(is_demo_input), int(platform_input))
            if ok:
                st.session_state.session_input = session_input.strip()
                st.session_state.uid_input = int(uid_input)
                st.session_state.is_demo_input = int(is_demo_input)
                st.session_state.platform_input = int(platform_input)
                # تحديث نسخة الجلسة في user
                st.session_state.user["session_key"] = session_input.strip()
                st.session_state.user["uid"] = int(uid_input)
                st.session_state.user["is_demo"] = int(is_demo_input)
                st.session_state.user["platform"] = int(platform_input)
                st.success("✅ تم ربط المفتاح بحسابك.")
            else:
                st.error("❌ فشل الحفظ.")

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
    st.caption(f"👤 المستخدم: `{user['email']}`")


# ============================================================
# الواجهة الرئيسية
# ============================================================
st.markdown('<div class="main-title">📈 بوت إشارات OTC — نسخة الويب</div>', unsafe_allow_html=True)
st.markdown("---")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🔌 اتصال بالمنصة", type="primary"):
        with st.spinner("جاري الاتصال..."):
            client, ok, err, trc = connect_pocket(
                session_input, int(uid_input), int(is_demo_input), int(platform_input)
            )
            if ok:
                st.session_state.client = client
                st.session_state.connected = True
                st.session_state.last_error = None
                st.session_state.last_error_trace = None
                st.success("✅ تم الاتصال بالمنصة بنجاح!")
            else:
                st.session_state.connected = False
                st.session_state.last_error = err
                st.session_state.last_error_trace = trc
                st.error(f"❌ فشل الاتصال: {err}")

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
                    st.error("❌ لا توجد بيانات (ربما انتهت المهلة أو العملة غير مدعومة).")
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
                    st.error("❌ لا توجد بيانات (ربما انتهت المهلة أو العملة غير مدعومة).")

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
                rows.append({
                    "الوقت": dt,
                    "فتح": f"{c[1]:.5f}",
                    "أعلى": f"{c[2]:.5f}",
                    "أدنى": f"{c[3]:.5f}",
                    "إغلاق": f"{c[4]:.5f}",
                })
            except Exception:
                rows.append({"الوقت": str(c), "فتح": "", "أعلى": "", "أدنى": "", "إغلاق": ""})

        st.dataframe(rows, use_container_width=True)

        try:
            import pandas as pd
            chart_data = pd.DataFrame({"الإغلاق": closes[-30:]})
            st.line_chart(chart_data)
        except Exception:
            pass
    except Exception as e:
        st.error(f"خطأ في عرض البيانات: {e}")

st.markdown("---")
st.caption(f"🕒 آخر تحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("⚠️ هذا التطبيق لأغراض تعليمية فقط. التداول يحمل مخاطر.")
