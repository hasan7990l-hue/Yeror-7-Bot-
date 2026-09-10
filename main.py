#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
import threading
import traceback
from datetime import datetime
from typing import Dict, List

import asyncio

# --- معالجة صلاحيات الكتابة لمنصة Streamlit Cloud ---
TMP_DIR = "/tmp/pocket_data"
os.makedirs(TMP_DIR, exist_ok=True)
os.environ["HOME"] = TMP_DIR
os.environ["TMPDIR"] = TMP_DIR
os.environ.setdefault("POCKETOPTION_HISTORY_PATH", TMP_DIR)

# ========== الإضافة الجديدة #1: حل مشكلة global_value.py (os.makedirs) ==========
try:
    os.chdir(TMP_DIR)
except Exception as _chdir_err:
    print(f"Warning: could not chdir to {TMP_DIR}: {_chdir_err}")

for _sub in ["history", "history/data", "logs", "cache", "data"]:
    try:
        os.makedirs(os.path.join(TMP_DIR, _sub), exist_ok=True)
    except Exception:
        pass

try:
    _site_pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _sub in ["history", "logs"]:
        try:
            os.makedirs(os.path.join(_site_pkg, _sub), exist_ok=True)
        except Exception:
            pass
except Exception:
    pass

os.environ.setdefault("POCKETOPTION_DATA_DIR", TMP_DIR)
os.environ.setdefault("POCKETOPTION_LOGS_DIR", os.path.join(TMP_DIR, "logs"))
os.environ.setdefault("POCKETOPTION_CACHE_DIR", os.path.join(TMP_DIR, "cache"))
# ========== نهاية الإضافة #1 ==========

# ========== التعديل الجذري: سيرفر الصحة الآن في عملية منفصلة (multiprocessing) ==========
# هذا يمنع Flask من حجب البوت داخل Streamlit.
def _health_worker(port: int):
    """يعمل في عملية منفصلة تماماً — لا يحجب البوت."""
    try:
        from flask import Flask
        _app = Flask("health")

        @_app.route("/")
        def _hc():
            return "Bot is alive and running!", 200

        _app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as _e:
        print(f"[Health Worker] error: {_e}")


def run_health_server():
    """تشغيل سيرفر الصحة في عملية منفصلة. إذا فشل، يكمل البوت عمله."""
    port = int(os.environ.get("PORT", 8080))
    try:
        import multiprocessing
        # استخدام spawn لتفادي مشاكل fork مع asyncio/telegram
        try:
            ctx = multiprocessing.get_context("spawn")
        except Exception:
            ctx = multiprocessing
        p = ctx.Process(target=_health_worker, args=(port,), daemon=True)
        p.start()
        print(f"ℹ️ Health server started in separate process (PID: {p.pid}) on port {port}")
    except Exception as e:
        # في حال فشل multiprocessing، نكتفي بتعطيل سيرفر الصحة بدل تعطيل البوت
        print(f"⚠️ Could not start health server (continuing without it): {e}")
# ========== نهاية التعديل الجذري ==========

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== الإضافة الجديدة #2: ترقيع آمن قبل استيراد المكتبة ==========
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
# ========== نهاية الإضافة #2 ==========

# --- تحديد نوع المكتبة ---
LIB_TYPE = "none"
try:
    from pocketoptionapi2.stable_api import PocketOption
    LIB_TYPE = "pocketoptionapi2"
except Exception:
    try:
        from pocketoptionapi.stable_api import PocketOption
        LIB_TYPE = "pocketoptionapi"
    except Exception:
        try:
            from pocket_option import PocketOptionClient, AuthorizationData
            LIB_TYPE = "pocket_option"
        except Exception:
            LIB_TYPE = "none"

# ========== الإضافة الجديدة #3: إعادة os.makedirs الأصلي ==========
try:
    os.makedirs = _original_makedirs
except Exception:
    pass
# ========== نهاية الإضافة #3 ==========

CONFIG_FILE = os.path.join(TMP_DIR, "signal_config.json")
CREDENTIALS_FILE = os.path.join(TMP_DIR, "pocket_credentials.json")

# --- المفتاح الجديد (مضمن) ---
SESSION = '42["auth",{"session":"vtftn12e6f5f5008moitsd6skl","isDemo":1,"uid":27658142,"platform":2,"isFastHistory":true,"isOptimized":true}]'
SESSION = os.environ.get("POCKET_SESSION", SESSION)
UID = 27658142
UID = int(os.environ.get("POCKET_UID", UID))
IS_DEMO = 1
PLATFORM = 2

BOT_TOKEN = "8604552604:AAGc6DOu4EMl9n-6uyc1IV8ZD9yz02KyBQU"
BOT_TOKEN = os.environ.get("BOT_TOKEN", BOT_TOKEN)

FOREX_SYMBOLS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC", "USDCAD-OTC"]
TRADE_DURATIONS = [60, 120, 300]

DEFAULT_CONFIG = {
    "publish_channel": None,
    "interval": 60,
    "min_confidence": 60,
    "enabled": False,
    "selected_symbol": "EURUSD-OTC",
    "selected_timeframe": 60,
    "selected_duration": 60
}

def load_config() -> Dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    except Exception:
        pass
    return DEFAULT_CONFIG

def save_config(config: Dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass

def generate_signal(candles, short_period: int = 5, long_period: int = 20) -> Dict:
    if not candles or len(candles) < long_period + 1:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "بيانات غير كافية"}
    closes = [c[4] for c in candles] if isinstance(candles[0], list) else [c.close for c in candles]
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

class SignalPublisher:
    def __init__(self):
        self.config = load_config()
        self.client = None
        self.connected = False
        self.selected_symbol = self.config.get("selected_symbol", "EURUSD-OTC")
        self.selected_timeframe = self.config.get("selected_timeframe", 60)
        self.selected_duration = self.config.get("selected_duration", 60)
        self.last_error = None
        self.last_error_trace = None

    def connect(self) -> bool:
        self.last_error = None
        self.last_error_trace = None
        self.connected = False

        if LIB_TYPE == "none":
            self.last_error = "لم يتم العثور على أي مكتبة PocketOption مثبتة. تأكد من تثبيت pocketoptionapi2 أو pocketoptionapi."
            self.last_error_trace = "LIB_TYPE = none"
            return False

        try:
            if LIB_TYPE == "pocketoptionapi":
                self.client = PocketOption(ssid=SESSION, demo=True)
                self.client.connect()
                self.connected = True
                return True

            elif LIB_TYPE == "pocketoptionapi2":
                self.client = PocketOption(demo=True)
                self.client.connect(session=SESSION, uid=UID, isDemo=IS_DEMO, platform=PLATFORM)
                self.connected = True
                return True

            else:
                self.client = PocketOption(demo=True)
                try:
                    self.client.set_session(SESSION, UID, IS_DEMO, PLATFORM)
                    self.client.connect()
                    self.connected = True
                    return True
                except Exception:
                    self.client.connect(session=SESSION, uid=UID, isDemo=IS_DEMO, platform=PLATFORM)
                    self.connected = True
                    return True

        except Exception as e:
            self.last_error = f"فشل الاتصال: {str(e)}"
            self.last_error_trace = traceback.format_exc()
            self.connected = False
            return False

    def get_candles(self, symbol: str, timeframe: int = 60, limit: int = 30) -> List:
        if not self.connected or not self.client:
            return []
        try:
            return self.client.get_candles(symbol, timeframe, limit)
        except Exception as e:
            self.last_error = f"فشل جلب الشموع: {str(e)}"
            self.last_error_trace = traceback.format_exc()
            return []

    def get_balance(self) -> float:
        if not self.connected or not self.client:
            self.last_error = "محاولة سحب الرصيد بدون اتصال"
            return 0.0
        try:
            return self.client.get_balance()
        except Exception as e:
            self.last_error = f"فشل سحب الرصيد: {str(e)}"
            self.last_error_trace = traceback.format_exc()
            return 0.0

    def generate_signal_for_symbol(self, symbol: str, timeframe: int = 60) -> Dict:
        if not self.connected:
            self.last_error = "محاولة توليد إشارة بدون اتصال"
            return {"signal": "NO_CONNECTION", "confidence": 0.0, "price": 0.0, "reason": "غير متصل"}
        candles = self.get_candles(symbol, timeframe, 30)
        if not candles:
            return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "لا توجد بيانات"}
        return generate_signal(candles)

    def format_single_signal_message(self, symbol: str, signal: Dict, timeframe: int, duration: int) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        tf_str = {60: "1m", 300: "5m", 900: "15m", 3600: "1h"}.get(timeframe, f"{timeframe}s")
        emoji = "🟢" if "CALL" in signal["signal"] else "🔴" if "PUT" in signal["signal"] else "⚪"
        return (
            f"📈 <b>إشارة {symbol}</b>\n"
            f"🕒 {now}\n"
            f"📊 الفريم: {tf_str}\n"
            f"⏱️ مدة الصفقة: {duration} ثانية\n\n"
            f"{emoji} <b>{signal['signal']}</b>\n"
            f"🎯 الثقة: {signal['confidence']}%\n"
            f"💵 السعر: {signal['price']:.4f}\n"
            f"📝 {signal['reason']}"
        )

    async def async_connect(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.connect)

    async def async_get_balance(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_balance)

    async def async_generate_signal(self, symbol, timeframe):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate_signal_for_symbol, symbol, timeframe)

publisher = SignalPublisher()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbol = publisher.selected_symbol
    timeframe = publisher.selected_timeframe
    duration = publisher.selected_duration
    tf_str = {60: "1m", 300: "5m", 900: "15m", 3600: "1h"}.get(timeframe, f"{timeframe}s")

    keyboard = [
        [InlineKeyboardButton("🔌 اتصال بالمنصة", callback_data="connect")],
        [InlineKeyboardButton("💰 الرصيد", callback_data="balance")],
        [InlineKeyboardButton("📊 اختيار العملة", callback_data="select_symbol")],
        [InlineKeyboardButton(f"📈 إشارة فورية ({symbol})", callback_data="signal_now")],
        [InlineKeyboardButton("📊 آخر بيانات السوق", callback_data="last_data")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"🤖 <b>بوت إشارات OTC</b>\n\n"
        f"📊 العملة الحالية: <b>{symbol}</b>\n"
        f"📈 فريم الشمعة: {tf_str}\n"
        f"⏱️ مدة الصفقة: {duration} ثانية\n"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "connect":
        try:
            success = publisher.connect()
            if success:
                await query.edit_message_text("✅ تم الاتصال (بالطريقة القديمة)!")
                return
        except Exception as e_old:
            print(f"[الأصل] فشل الاتصال القديم: {e_old}")
            publisher.last_error = f"فشل الاتصال القديم: {str(e_old)}"
            publisher.last_error_trace = traceback.format_exc()
        
        success_patched = await publisher.async_connect()
        if success_patched:
            await query.edit_message_text("✅ تم الاتصال (بالمعالج الآمن)!")
        else:
            error_msg = publisher.last_error or "سبب غير معروف"
            error_trace = publisher.last_error_trace or "لا يوجد تتبع"
            if len(error_trace) > 500:
                error_trace = error_trace[:500] + "...\n(تم اختصار التتبع)"
            
            full_error_report = (
                f"❌ <b>فشل الاتصال بالمنصة</b>\n\n"
                f"🔍 <b>تفاصيل الخطأ:</b>\n"
                f"<code>{error_msg}</code>\n\n"
                f"📋 <b>تتبع المكدس (Stack Trace):</b>\n"
                f"<code>{error_trace}</code>\n\n"
                f"🛠️ <b>الفحص الذاتي:</b>\n"
                f"- مفتاح SESSION المستخدم: {'موجود' if SESSION else '⚠️ فارغ'}\n"
                f"- نوع المكتبة: {LIB_TYPE}\n"
                f"- UID: {UID}\n"
                f"- الحساب: {'تجريبي' if IS_DEMO == 1 else 'حقيقي'}\n"
                f"- المنصة: {PLATFORM}"
            )
            await query.edit_message_text(full_error_report, parse_mode="HTML")

    elif data == "balance":
        if not publisher.connected:
            await publisher.async_connect()
            if not publisher.connected:
                error_msg = publisher.last_error or "البوت غير متصل ولا يوجد خطأ محدد"
                await query.edit_message_text(f"⚠️ البوت غير متصل.\n\nالسبب المحتمل:\n<code>{error_msg}</code>", parse_mode="HTML")
                return
        try:
            bal = publisher.get_balance()
            await query.edit_message_text(f"💰 الرصيد (قديم): {bal:.2f}$")
        except Exception as e_bal:
            print(f"[الأصل] فشل سحب الرصيد: {e_bal}")
            publisher.last_error = f"فشل سحب الرصيد (الأصل): {str(e_bal)}"
            publisher.last_error_trace = traceback.format_exc()
            bal_new = await publisher.async_get_balance()
            if bal_new > 0:
                await query.edit_message_text(f"💰 الرصيد (جديد/آمن): {bal_new:.2f}$")
            else:
                await query.edit_message_text(
                    f"❌ فشل سحب الرصيد.\n\nتفاصيل الخطأ:\n<code>{publisher.last_error}</code>",
                    parse_mode="HTML"
                )

    elif data == "select_symbol":
        keyboard = [[InlineKeyboardButton(sym, callback_data=f"set_symbol_{sym}")] for sym in FOREX_SYMBOLS]
        await query.edit_message_text("📊 اختر العملة:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("set_symbol_"):
        symbol = data.replace("set_symbol_", "")
        publisher.selected_symbol = symbol
        publisher.config["selected_symbol"] = symbol
        save_config(publisher.config)
        await query.edit_message_text(f"✅ تم اختيار {symbol}. ارجع للقائمة الرئيسية عبر /start")

    elif data == "signal_now":
        if not publisher.connected:
            await publisher.async_connect()
            if not publisher.connected:
                error_msg = publisher.last_error or "البوت غير متصل"
                await query.edit_message_text(f"⚠️ البوت غير متصل.\n\nالسبب:\n<code>{error_msg}</code>", parse_mode="HTML")
                return
        try:
            signal = publisher.generate_signal_for_symbol(publisher.selected_symbol, publisher.selected_timeframe)
            msg = publisher.format_single_signal_message(publisher.selected_symbol, signal, publisher.selected_timeframe, publisher.selected_duration)
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception as e_sig:
            print(f"[الأصل] فشل توليد الإشارة: {e_sig}")
            publisher.last_error = f"فشل توليد الإشارة (الأصل): {str(e_sig)}"
            publisher.last_error_trace = traceback.format_exc()
            signal_new = await publisher.async_generate_signal(publisher.selected_symbol, publisher.selected_timeframe)
            if signal_new and signal_new.get("signal") != "NO_CONNECTION":
                msg_new = publisher.format_single_signal_message(publisher.selected_symbol, signal_new, publisher.selected_timeframe, publisher.selected_duration)
                await query.edit_message_text(msg_new, parse_mode="HTML")
            else:
                await query.edit_message_text(
                    f"❌ فشل توليد الإشارة.\n\nتفاصيل الخطأ:\n<code>{publisher.last_error}</code>",
                    parse_mode="HTML"
                )

    elif data == "last_data":
        if not publisher.connected:
            await publisher.async_connect()
        
        candles = publisher.get_candles(publisher.selected_symbol, publisher.selected_timeframe, 30)
        if not candles:
            await query.edit_message_text(
                f"❌ لا توجد بيانات لعرضها.\n"
                f"🔹 الحالة: {'✅ متصل' if publisher.connected else '❌ غير متصل'}\n"
                f"🔹 آخر خطأ: {publisher.last_error or 'لا يوجد'}"
            )
            return

        closes = [c[4] for c in candles]
        current_price = closes[-1]
        sma5 = sum(closes[-5:]) / 5
        sma20 = sum(closes[-20:]) / 20
        signal = generate_signal(candles)

        msg = f"📊 <b>بيانات السوق الحالية</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🔹 الرمز: <b>{publisher.selected_symbol}</b>\n"
        msg += f"🔹 الفريم: {publisher.selected_timeframe} ثانية\n"
        msg += f"🔹 حالة الاتصال: {'✅ متصل' if publisher.connected else '❌ غير متصل'}\n"
        msg += f"🔹 عدد الشموع المجلوبة: {len(candles)}\n"
        msg += f"🔹 السعر الحالي (الإغلاق): <b>{current_price:.5f}</b>\n"
        msg += f"🔹 المتوسط المتحرك SMA(5): {sma5:.5f}\n"
        msg += f"🔹 المتوسط المتحرك SMA(20): {sma20:.5f}\n"
        msg += f"🔹 الإشارة الحالية: <b>{signal['signal']}</b> (ثقة {signal['confidence']}%)\n"
        msg += f"🔹 سبب الإشارة: {signal['reason']}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📋 <b>آخر 5 شموع (الخزانة):</b>\n"
        
        for idx, c in enumerate(candles[-5:], 1):
            try:
                dt = datetime.fromtimestamp(c[0]).strftime("%H:%M:%S")
                msg += (
                    f"  {idx}⟩ {dt} | فتح: {c[1]:.5f} | أعلى: {c[2]:.5f} | "
                    f"أدنى: {c[3]:.5f} | إغلاق: <b>{c[4]:.5f}</b>\n"
                )
            except Exception:
                msg += f"  {idx}⟩ {c}\n"
        
        await query.edit_message_text(msg, parse_mode="HTML")

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 جاري اختبار الاتصال بالمنصة...")
    success = await publisher.async_connect()
    if success:
        await update.message.reply_text("✅ الاتصال ناجح! المنصة جاهزة.")
    else:
        error_msg = publisher.last_error or "سبب غير معروف"
        error_trace = publisher.last_error_trace or "لا يوجد تتبع"
        if len(error_trace) > 500:
            error_trace = error_trace[:500] + "...\n(تم اختصار التتبع)"
        full_report = (
            f"❌ <b>فشل اختبار الاتصال</b>\n\n"
            f"🔍 <b>التفاصيل:</b>\n"
            f"<code>{error_msg}</code>\n\n"
            f"📋 <b>التتبع:</b>\n"
            f"<code>{error_trace}</code>\n\n"
            f"🛠️ <b>المتغيرات:</b>\n"
            f"- نوع المكتبة: {LIB_TYPE}\n"
            f"- UID: {UID}\n"
            f"- الحساب: {'تجريبي' if IS_DEMO == 1 else 'حقيقي'}"
        )
        await update.message.reply_text(full_report, parse_mode="HTML")

# ---- آلية القفل ----
LOCK_FILE = "/tmp/bot.lock"

def main():
    if os.path.exists(LOCK_FILE):
        print("⚠️ يوجد نسخة أخرى من البوت تعمل، إنهاء هذه النسخة.")
        return

    # تشغيل سيرفر الصحة في عملية منفصلة (لن يحجب البوت)
    run_health_server()

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("test", test_command))
        app.add_handler(CallbackQueryHandler(button_handler))
        print("🤖 البوت يعمل الآن... (مع التصحيح النهائي للمكتبة وأمر /test وتحديد مهلة 30 ثانية)")
        print("🚀 جاهز لتشغيل run_polling...")
        app.run_polling(stop_signals=None)
    finally:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)

if __name__ == "__main__":
    main()
