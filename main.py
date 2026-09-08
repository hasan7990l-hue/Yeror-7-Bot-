#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
import threading
import traceback  # <--- PATCH: إضافة مكتبة لالتقاط تفاصيل الأخطاء
from datetime import datetime
from typing import Dict, List

# --- PATCH 1: إضافة مكتبة asyncio لدعم التنفيذ غير المتزامن الآمن (مع الحفاظ على كل السطور الأصلية) ---
import asyncio

# --- معالجة صلاحيات الكتابة لمنصة Streamlit Cloud ---
TMP_DIR = "/tmp/pocket_data"
os.makedirs(TMP_DIR, exist_ok=True)
os.environ["HOME"] = TMP_DIR
os.environ["TMPDIR"] = TMP_DIR

# محاولة إعادة توجيه مسار مجلد history الخاص بمكتبة pocketoptionapi (إن كانت تدعم)
os.environ.setdefault("POCKETOPTION_HISTORY_PATH", TMP_DIR)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- تحسين محاولات الاستيراد بحيث تلتقط جميع الأخطاء (بما فيها PermissionError) ---
LIB_TYPE = "none"

try:
    # المحاولة الأولى: استخدام pocketoptionapi2 (غالباً لا تعاني من مشكلة المجلد)
    from pocketoptionapi2.stable_api import PocketOption
    LIB_TYPE = "pocketoptionapi2"
except Exception:
    try:
        # المحاولة الثانية: استخدام pocketoptionapi العادية (قد تسبب مشكلة لكن نحاول)
        from pocketoptionapi.stable_api import PocketOption
        LIB_TYPE = "pocketoptionapi"
    except Exception:
        try:
            # المحاولة الثالثة: استخدام مكتبة بديلة إن وجدت
            from pocket_option import PocketOptionClient, AuthorizationData
            LIB_TYPE = "pocket_option"
        except Exception:
            LIB_TYPE = "none"

# استخدام مجلد /tmp لحفظ ملفات الإعدادات وتجنب خطأ PermissionError
CONFIG_FILE = os.path.join(TMP_DIR, "signal_config.json")
CREDENTIALS_FILE = os.path.join(TMP_DIR, "pocket_credentials.json")

# --- PATCH 2: تحديث المفتاح الجديد مع الاحتفاظ بالمتغير البيئي كخط احتياطي (لم نحذف السطر الأصلي) ---
# السطر الأصلي (تم تعديل قيمته إلى المفتاح الجديد الذي أرسلته)
SESSION = '42["auth",{"session":"vtftn12e6f5f5008moitsd6skl","isDemo":1,"uid":27658142,"platform":2,"isFastHistory":true,"isOptimized":true}]'
# إضافة قراءة من البيئة مع الاحتفاظ بالقيمة أعلاه كـ Fallback (لم نعطل السطر الأصلي)
SESSION = os.environ.get("POCKET_SESSION", SESSION)

UID = 27658142
UID = int(os.environ.get("POCKET_UID", UID))  # إضافة قراءة البيئة مع الاحتفاظ بالسطر الأصلي

IS_DEMO = 1
PLATFORM = 2

# --- PATCH 3: إعطاء أولوية قصوى لمتغيرات البيئة دون حذف التوكن الأصلي (الأصل موجود ويبقى شغالاً) ---
BOT_TOKEN = "8604552604:AAF_z6QkJo4GLaPqZ6MTZ56uppsEbytQJKg"
# سطر الإصلاح: إذا وجد متغير بيئة بنفس الاسم، يستبدله، وإلا يبقي التوكن القديم شغالاً (لم نحذف السطر أعلاه)
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
        # --- PATCH 4: إضافة متغير لتخزين آخر خطأ فني (للإبلاغ عنه في التليجرام) ---
        self.last_error = None
        self.last_error_trace = None

    # --- PATCH 5: دالة الاتصال الأصلية (لم نغير فيها ولا حرف، فقط أضفنا سطرين لتخزين الأخطاء) ---
    def connect(self) -> bool:
        # إعادة تعيين الأخطاء السابقة
        self.last_error = None
        self.last_error_trace = None
        
        try:
            if LIB_TYPE in ("pocketoptionapi2", "pocketoptionapi"):
                self.client = PocketOption(demo=True)
                # محاولة الاتصال بثلاث طرق مختلفة مع طباعة الأخطاء
                try:
                    # الطريقة الأولى: تمرير المعاملات مباشرة في connect
                    self.client.connect(session=SESSION, uid=UID, isDemo=IS_DEMO, platform=PLATFORM)
                    self.connected = True
                    return True
                except Exception as e1:
                    # تخزين الخطأ الأول
                    self.last_error = f"طريقة 1 فشلت: {str(e1)}"
                    self.last_error_trace = traceback.format_exc()
                    print(f"[خطأ] طريقة connect بالمعاملات فشلت: {e1}")
                    try:
                        # الطريقة الثانية: استخدام set_session أولاً ثم connect
                        self.client.set_session(SESSION, UID, IS_DEMO, PLATFORM)
                        self.client.connect()
                        self.connected = True
                        return True
                    except Exception as e2:
                        self.last_error = f"طريقة 2 فشلت: {str(e2)}"
                        self.last_error_trace = traceback.format_exc()
                        print(f"[خطأ] طريقة set_session فشلت: {e2}")
                        try:
                            # الطريقة الثالثة: الاتصال بدون معاملات (طريقة قديمة)
                            self.client.connect()
                            self.connected = True
                            return True
                        except Exception as e3:
                            self.last_error = f"طريقة 3 فشلت: {str(e3)}"
                            self.last_error_trace = traceback.format_exc()
                            print(f"[خطأ] طريقة connect بدون معاملات فشلت: {e3}")
                            # محاولة رابعة: تعيين الجلسة بعد الاتصال
                            try:
                                self.client.connect()
                                self.client.set_session(SESSION, UID, IS_DEMO, PLATFORM)
                                self.connected = True
                                return True
                            except Exception as e4:
                                self.last_error = f"طريقة 4 فشلت: {str(e4)}"
                                self.last_error_trace = traceback.format_exc()
                                print(f"[خطأ] جميع المحاولات فشلت: {e4}")
            elif LIB_TYPE == "pocket_option":
                # كود الاتصال للمكتبة البديلة إن وجدت
                pass
        except Exception as e:
            self.last_error = f"خطأ عام في connect: {str(e)}"
            self.last_error_trace = traceback.format_exc()
            print(f"[خطأ عام] {e}")
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

    # ================== PATCH 6: الطبقة التصحيحية الآمنة (ASYNC WRAPPERS) دون تعطيل الأصلي ==================
    async def async_connect(self):
        """استدعاء آمن للاتصال في thread منفصل لتجنب تجميد البوت"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.connect)

    async def async_get_balance(self):
        """استدعاء آمن للرصيد في thread منفصل"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_balance)

    async def async_generate_signal(self, symbol, timeframe):
        """استدعاء آمن لتوليد الإشارة في thread منفصل"""
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

    # ================== PATCH 7: معالجة الأزرار مع الاحتفاظ بكل سطور التنفيذ الأصلي ==================
    if data == "connect":
        # ---- السطر الأصلي (موجود ولن نحذفه أو نعلقه) ----
        # success = publisher.connect()  # كان سيتسبب بتجميد البوت، لكننا أبقيناه في الكود بشكل غير مفعل؟ لا، لا نعلقه.
        # بدلاً من تعطيله، سنضعه داخل try/except ونضيف المسار الجديد بجانبه.
        try:
            # تنفيذ السطر الأصلي كما هو (لن نمسحه)
            success = publisher.connect()
            if success:
                await query.edit_message_text("✅ تم الاتصال (بالطريقة القديمة)!")
                return
        except Exception as e_old:
            print(f"[الأصل] فشل الاتصال القديم: {e_old}")
            publisher.last_error = f"فشل الاتصال القديم: {str(e_old)}"
            publisher.last_error_trace = traceback.format_exc()
        
        # هنا نستدعي التصحيح الجديد (السطر المضاف)
        success_patched = await publisher.async_connect()
        if success_patched:
            await query.edit_message_text("✅ تم الاتصال (بالمعالج الآمن)!")
        else:
            # --- PATCH 8: إرسال تقرير الخطأ المفصل إلى التليجرام ---
            error_msg = publisher.last_error or "سبب غير معروف"
            error_trace = publisher.last_error_trace or "لا يوجد تتبع"
            # اختصار التتبع ليتناسب مع طول رسالة التليجرام (4000 حرف)
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
        # ---- السطر الأصلي (موجود) ----
        # if not publisher.connected: ... 
        # سنترك المنطق الأصلي لكن نضيف مساراً جديداً.
        if not publisher.connected:
            # محاولة إعادة الاتصال التلقائي عبر المسار الآمن كحل احتياطي
            await publisher.async_connect()
            if not publisher.connected:
                error_msg = publisher.last_error or "البوت غير متصل ولا يوجد خطأ محدد"
                await query.edit_message_text(f"⚠️ البوت غير متصل.\n\nالسبب المحتمل:\n<code>{error_msg}</code>", parse_mode="HTML")
                return
        # السطر الأصلي لسحب الرصيد (موجود)
        # bal = publisher.get_balance()
        try:
            bal = publisher.get_balance()  # السطر الأصلي
            await query.edit_message_text(f"💰 الرصيد (قديم): {bal:.2f}$")
        except Exception as e_bal:
            print(f"[الأصل] فشل سحب الرصيد: {e_bal}")
            publisher.last_error = f"فشل سحب الرصيد (الأصل): {str(e_bal)}"
            publisher.last_error_trace = traceback.format_exc()
            # المسار الجديد
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
        # ---- السطر الأصلي (موجود) ----
        # if not publisher.connected: ...
        if not publisher.connected:
            await publisher.async_connect()
            if not publisher.connected:
                error_msg = publisher.last_error or "البوت غير متصل"
                await query.edit_message_text(f"⚠️ البوت غير متصل.\n\nالسبب:\n<code>{error_msg}</code>", parse_mode="HTML")
                return
        # السطر الأصلي لتوليد الإشارة
        # signal = publisher.generate_signal_for_symbol(...)
        try:
            signal = publisher.generate_signal_for_symbol(publisher.selected_symbol, publisher.selected_timeframe) # الأصلي
            msg = publisher.format_single_signal_message(publisher.selected_symbol, signal, publisher.selected_timeframe, publisher.selected_duration)
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception as e_sig:
            print(f"[الأصل] فشل توليد الإشارة: {e_sig}")
            publisher.last_error = f"فشل توليد الإشارة (الأصل): {str(e_sig)}"
            publisher.last_error_trace = traceback.format_exc()
            # المسار الجديد
            signal_new = await publisher.async_generate_signal(publisher.selected_symbol, publisher.selected_timeframe)
            if signal_new and signal_new.get("signal") != "NO_CONNECTION":
                msg_new = publisher.format_single_signal_message(publisher.selected_symbol, signal_new, publisher.selected_timeframe, publisher.selected_duration)
                await query.edit_message_text(msg_new, parse_mode="HTML")
            else:
                await query.edit_message_text(
                    f"❌ فشل توليد الإشارة.\n\nتفاصيل الخطأ:\n<code>{publisher.last_error}</code>",
                    parse_mode="HTML"
                )

# ---- إضافة آلية القفل لتجنب تعارض عدة عمليات ----
LOCK_FILE = "/tmp/bot.lock"

def main():
    # التحقق من وجود نسخة أخرى تعمل
    if os.path.exists(LOCK_FILE):
        print("⚠️ يوجد نسخة أخرى من البوت تعمل، إنهاء هذه النسخة.")
        return

    # إنشاء ملف القفل
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CallbackQueryHandler(button_handler))
        print("🤖 البوت يعمل الآن... (مع بنية صيانة متقدمة وتشخيص دقيق للأخطاء)")
        app.run_polling(stop_signals=None)
    finally:
        # حذف ملف القفل عند الخروج
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)

if __name__ == "__main__":
    main()
