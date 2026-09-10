#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
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


async def _get_balance_async(acc: dict) -> float:
    """
    الحصول على الرصيد باستخدام نظام الأحداث في مكتبة pocket-option.
    """
    client = PocketOptionClient()
    
    # استخراج معرف الجلسة من النص
    session_id = acc["session"].split('"session":"')[1].split('"')[0]
    
    # تهيئة العميل مع تمرير الأصول والفترات لتفعيل الاشتراكات
    default_init(
        client,
        authorization=AuthorizationData.model_validate({
            "session": session_id,
            "isDemo": acc["is_demo"],
            "uid": acc["uid"],
            "platform": acc["platform"],
            "isFastHistory": True,
            "isOptimized": True,
        }),
        sub_assets=["EURUSD_otc"],  # يمكن تعديلها حسب الحاجة
        sub_period=60,
    )
    
    # متغير لتخزين الرصيد
    balance_value = None
    
    # تعريف معالج الحدث لاستقبال الرصيد
    @client.on.balance_success_update
    async def on_balance_update(data):
        nonlocal balance_value
        print(f"[DEBUG] Balance update received: {data}")  # للتشخيص
        # محاولة استخراج الرصيد من الحقول المحتملة
        if isinstance(data, dict):
            balance_value = data.get('balance', data.get('amount', data.get('value', 0)))
        elif hasattr(data, 'balance'):
            balance_value = data.balance
        else:
            balance_value = data  # افتراض أن البيانات هي الرصيد مباشرة
    
    # انتظار الاتصال والتفويض
    await asyncio.sleep(8)
    
    # طلب تحديث الرصيد
    await client.emit.update_balance()
    
    # انتظار استلام الرصيد (مع مهلة 10 ثوانٍ)
    timeout = 10
    elapsed = 0
    while balance_value is None and elapsed < timeout:
        await asyncio.sleep(0.5)
        elapsed += 0.5
    
    await client.close()
    
    if balance_value is None:
        raise TimeoutError("لم يتم استلام الرصيد خلال المهلة المحددة. تحقق من صحة الجلسة أو المكتبة.")
    
    return float(balance_value)


async def _get_candles_async(acc: dict, asset: str, period: int) -> List:
    client = PocketOptionClient()
    session_id = acc["session"].split('"session":"')[1].split('"')[0]
    default_init(
        client,
        authorization=AuthorizationData.model_validate({
            "session": session_id,
            "isDemo": acc["is_demo"],
            "uid": acc["uid"],
            "platform": acc["platform"],
            "isFastHistory": True,
            "isOptimized": True,
        }),
        sub_assets=[asset],
        sub_period=period,
    )
    await asyncio.sleep(8)
    candles = await client.get_candles(Asset(asset), period, 30)
    await client.close()
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
.main-title{font-size:2.2rem;font-weight:bold;color:#00d4ff;text-align:center}
.signal-call{background:linear-gradient(90deg,#00c853,#64dd17);padding:1rem;border-radius:10px;color:#fff;text-align:center;font-size:1.4rem;font-weight:bold}
.signal-put{background:linear-gradient(90deg,#d50000,#ff1744);padding:1rem;border-radius:10px;color:#fff;text-align:center;font-size:1.4rem;font-weight:bold}
.signal-neutral{background:linear-gradient(90deg,#616161,#9e9e9e);padding:1rem;border-radius:10px;color:#fff;text-align:center;font-size:1.4rem;font-weight:bold}
</style>
""", unsafe_allow_html=True)

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user" not in st.session_state: st.session_state.user = None
if "selected_account" not in st.session_state: st.session_state.selected_account = None
if "last_signal" not in st.session_state: st.session_state.last_signal = None
if "last_candles" not in st.session_state: st.session_state.last_candles = None


if not st.session_state.logged_in:
    st.markdown('<div class="main-title">📈 إشارات OTC</div>', unsafe_allow_html=True)
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


st.markdown('<div class="main-title">📈 إشارات OTC</div>', unsafe_allow_html=True)
acc = user["accounts"][st.session_state.selected_account]
st.info(f"الحساب النشط: **{acc['label']}** — UID: `{acc['uid']}`")
st.markdown("---")

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("💰 عرض الرصيد", type="primary"):
        try:
            with st.spinner("جاري سحب الرصيد..."):
                bal = asyncio.run(_get_balance_async(acc))
                st.success(f"💰 الرصيد: **{bal}**")
        except Exception as e:
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())

with c2:
    if st.button("📈 إشارة فورية"):
        try:
            with st.spinner("جاري التحليل..."):
                candles = asyncio.run(_get_candles_async(acc, symbol, int(period)))
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                    st.rerun()
                else:
                    st.error("❌ لا توجد بيانات.")
        except Exception as e:
            st.error(f"❌ فشل: {e}")
            st.code(traceback.format_exc())

with c3:
    if st.button("📊 آخر بيانات السوق"):
        try:
            with st.spinner("جاري الجلب..."):
                candles = asyncio.run(_get_candles_async(acc, symbol, int(period)))
                if candles:
                    st.session_state.last_candles = candles
                    st.session_state.last_signal = generate_signal(candles)
                    st.rerun()
                else:
                    st.error("❌ لا توجد بيانات.")
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
