#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
import threading
import signal
from datetime import datetime
from typing import Dict, List, Optional

# ------------------- استخدام pocketoptionapi2 (متزامن) -------------------
try:
    from pocketoptionapi.stable_api import PocketOption
    LIB_TYPE = "pocketoptionapi2"
    print("[+] تم استيراد pocketoptionapi2")
except ImportError:
    try:
        from pocket_option import PocketOptionClient
        from pocket_option.models import AuthorizationData, Candle
        LIB_TYPE = "pocket_option"
        print("[+] تم استيراد pocket-option")
    except ImportError:
        print("[!] لم يتم العثور على أي مكتبة مدعومة.")
        print("[!] ثبّت إحدى المكتبات:")
        print("    pip install pocketoptionapi2==0.1.1")
        print("    أو")
        print("    pip install pocket-option")
        sys.exit(1)

# ------------------- مكتبات Telegram -------------------
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
except ImportError:
    print("[!] ثبّت: pip install python-telegram-bot")
    sys.exit(1)

# ------------------- الإعدادات -------------------
CONFIG_FILE = "signal_config.json"
CREDENTIALS_FILE = "pocket_credentials.json"
BOT_TOKEN = "8604552604:AAHwikPup65nkkv6xLzJEOhYO4jY5PJAS1M"

FOREX_SYMBOLS = [
    "EURUSD-OTC",
    "GBPUSD-OTC",
    "USDJPY-OTC",
    "AUDUSD-OTC",
    "USDCAD-OTC"
]

TRADE_DURATIONS = [60, 120, 300]

SESSION = "vtftn12e6f5f5008moitsd6skl"
UID = 27658142
IS_DEMO = 1
PLATFORM = 2

DEFAULT_CONFIG = {
    "publish_channel": None,
    "interval": 60,
    "min_confidence": 60,
    "enabled": False,
    "selected_symbol": "EURUSD-OTC",
    "selected_timeframe": 60,
    "selected_duration": 60
}

# ------------------- دوال الإعدادات -------------------
def load_config() -> Dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    return DEFAULT_CONFIG

def save_config(config: Dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def load_credentials() -> Dict:
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            return json.load(f)
    data = {
        "ssid": f'42["auth",{{"session":"{SESSION}","isDemo":{IS_DEMO},"uid":{UID},"platform":{PLATFORM},"isFastHistory":true,"isOptimized":true}}]',
        "uid": UID,
        "is_demo": IS_DEMO,
        "platform": PLATFORM
    }
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return data

# ------------------- معالج إشارة Ctrl+C -------------------
def signal_handler(sig, frame):
    print("\n[!] جاري إيقاف البوت...")
    if publisher:
        publisher.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ------------------- محرك الإشارات -------------------
def generate_signal(candles, short_period: int = 5, long_period: int = 20) -> Dict:
    if not candles or len(candles) < long_period + 1:
        return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "بيانات غير كافية"}

    if LIB_TYPE == "pocketoptionapi2":
        closes = [c[4] for c in candles] if isinstance(candles[0], list) else [c.close for c in candles]
    else:
        closes = [c.close for c in candles]

    current_price = closes[-1]
    sma_short = sum(closes[-short_period:]) / short_period
    sma_long = sum(closes[-long_period:]) / long_period

    prev_sma_short = sum(closes[-short_period-1:-1]) / short_period if len(closes) > short_period else sma_short
    prev_sma_long = sum(closes[-long_period-1:-1]) / long_period if len(closes) > long_period else sma_long

    diff = abs((sma_short - sma_long) / sma_long) * 100 if sma_long > 0 else 0
    confidence = min(90, 50 + diff * 3)

    if prev_sma_short <= prev_sma_long and sma_short > sma_long:
        return {"signal": "CALL 🟢", "confidence": round(confidence, 1), "price": current_price, "reason": f"SMA({short_period}) تجاوز SMA({long_period})"}
    elif prev_sma_short >= prev_sma_long and sma_short < sma_long:
        return {"signal": "PUT 🔴", "confidence": round(confidence, 1), "price": current_price, "reason": f"SMA({short_period}) نزل تحت SMA({long_period})"}
    else:
        return {"signal": "NEUTRAL ⚪", "confidence": 50.0, "price": current_price, "reason": "لا يوجد تقاطع واضح"}

# ------------------- البوت الرئيسي (متزامن بالكامل) -------------------
class SignalPublisher:
    def __init__(self):
        self.config = load_config()
        creds = load_credentials()
        self.ssid = creds.get("ssid")
        self.uid = creds.get("uid")
        self.client = None
        self.connected = False
        self.is_running = False
        self._stop_event = threading.Event()
        self.selected_symbol = self.config.get("selected_symbol", "EURUSD-OTC")
        self.selected_timeframe = self.config.get("selected_timeframe", 60)
        self.selected_duration = self.config.get("selected_duration", 60)

    def connect(self) -> bool:
        try:
            if LIB_TYPE == "pocketoptionapi2":
                self.client = PocketOption(demo=True)
                self.client.connect()
                self.connected = True
                print("[+] تم الاتصال بـ Pocket Option (pocketoptionapi2)")
            else:
                from pocket_option import AuthorizationData
                self.client = PocketOptionClient()
                auth = AuthorizationData(
                    session=self.ssid,
                    isDemo=1,
                    uid=self.uid,
                    platform=2
                )
                import asyncio
                asyncio.run(self.client.connect(auth))
                self.connected = True
                print("[+] تم الاتصال بـ Pocket Option (pocket-option)")
            return True
        except Exception as e:
            print(f"[!] فشل الاتصال: {e}")
            self.connected = False
            return False

    def get_candles(self, symbol: str, timeframe: int = 60, limit: int = 30) -> List:
        if not self.connected or not self.client:
            return []
        try:
            if LIB_TYPE == "pocketoptionapi2":
                return self.client.get_candles(symbol, timeframe, limit)
            else:
                import asyncio
                return asyncio.run(self.client.get_candles(symbol, timeframe, limit))
        except Exception as e:
            print(f"[!] فشل جلب {symbol}: {e}")
            return []

    def get_balance(self) -> float:
        if not self.connected or not self.client:
            return 0.0
        try:
            return self.client.get_balance()
        except Exception as e:
            print(f"[!] فشل جلب الرصيد: {e}")
            return 0.0

    def generate_all_signals(self) -> Dict:
        if not self.connected:
            return {}
        signals = {}
        for sym in FOREX_SYMBOLS:
            candles = self.get_candles(sym, 60, 30)
            if candles:
                signals[sym] = generate_signal(candles)
            else:
                signals[sym] = {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "لا توجد بيانات"}
            time.sleep(0.5)
        return signals

    def generate_signal_for_symbol(self, symbol: str, timeframe: int = 60) -> Dict:
        if not self.connected:
            return {"signal": "NO_CONNECTION", "confidence": 0.0, "price": 0.0, "reason": "غير متصل"}
        candles = self.get_candles(symbol, timeframe, 30)
        if not candles:
            return {"signal": "NO_DATA", "confidence": 0.0, "price": 0.0, "reason": "لا توجد بيانات"}
        return generate_signal(candles)

    def format_signal_message(self, signals: Dict) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"📊 <b>إشارات OTC - فوركس</b>\n🕒 {now}\n\n"
        for sym, sig in signals.items():
            emoji = "🟢" if "CALL" in sig["signal"] else "🔴" if "PUT" in sig["signal"] else "⚪"
            msg += f"{emoji} <b>{sym}</b>\n"
            msg += f"   📈 الإشارة: {sig['signal']}\n"
            msg += f"   🎯 الثقة: {sig['confidence']}%\n"
            msg += f"   💵 السعر: {sig['price']:.4f}\n"
            msg += f"   📝 {sig['reason']}\n\n"
        return msg

    def format_single_signal_message(self, symbol: str, signal: Dict, timeframe: int, duration: int) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        timeframe_str = {60: "1m", 300: "5m", 900: "15m", 3600: "1h"}.get(timeframe, f"{timeframe}s")
        emoji = "🟢" if "CALL" in signal["signal"] else "🔴" if "PUT" in signal["signal"] else "⚪"
        msg = (
            f"📈 <b>إشارة {symbol}</b>\n"
            f"🕒 {now}\n"
            f"📊 الفريم: {timeframe_str}\n"
            f"⏱️ مدة الصفقة: {duration} ثانية\n\n"
            f"{emoji} <b>{signal['signal']}</b>\n"
            f"🎯 الثقة: {signal['confidence']}%\n"
            f"💵 السعر: {signal['price']:.4f}\n"
            f"📝 {signal['reason']}"
        )
        return msg

    def should_publish(self, signals: Dict, min_confidence: int) -> bool:
        for sym, sig in signals.items():
            if sig["signal"] in ["CALL 🟢", "PUT 🔴"] and sig["confidence"] >= min_confidence:
                return True
        return False

    def publish(self, bot, chat_id: str, message: str):
        try:
            bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            print(f"[+] تم النشر في {chat_id}")
        except Exception as e:
            print(f"[!] فشل النشر: {e}")

    def run_loop(self, bot):
        if not self.config.get("enabled", False):
            print("[!] البوت متوقف. فعّل عبر /start_publishing")
            return

        channel = self.config.get("publish_channel")
        if not channel:
            print("[!] لم يتم تعيين قناة النشر. استخدم /set_channel")
            return

        print("[*] بدء نشر الإشارات...")
        self.is_running = True
        self._stop_event.clear()

        while not self._stop_event.is_set():
            try:
                signals = self.generate_all_signals()
                if self.should_publish(signals, self.config.get("min_confidence", 60)):
                    message = self.format_signal_message(signals)
                    self.publish(bot, channel, message)
                else:
                    print("[*] لا توجد إشارات قوية للنشر")

                for _ in range(self.config.get("interval", 60)):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)

            except Exception as e:
                print(f"[!] خطأ في الحلقة: {e}")
                time.sleep(30)

        self.is_running = False
        print("[*] توقف النشر.")

    def stop(self):
        self._stop_event.set()
        self.is_running = False

publisher = SignalPublisher()
publishing_thread = None

# ------------------- دوال Telegram -------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = publisher.config.get("publish_channel") or "غير معين"
    status = "🟢 مفعل" if publisher.config.get("enabled") else "🔴 معطل"
    symbol = publisher.selected_symbol
    timeframe = publisher.selected_timeframe
    duration = publisher.selected_duration
    timeframe_str = {60: "1m", 300: "5m", 900: "15m", 3600: "1h"}.get(timeframe, f"{timeframe}s")

    keyboard = [
        [InlineKeyboardButton("🔌 اتصال بالمنصة", callback_data="connect")],
        [InlineKeyboardButton("💰 الرصيد", callback_data="balance")],
        [InlineKeyboardButton("📊 اختيار العملة", callback_data="select_symbol")],
        [InlineKeyboardButton(f"📈 إشارة فورية ({symbol})", callback_data="signal_now")],
        [InlineKeyboardButton("📡 تعيين قناة النشر", callback_data="set_channel")],
        [InlineKeyboardButton(f"▶️ بدء النشر ({status})", callback_data="toggle_publish")],
        [InlineKeyboardButton("📋 الحالة", callback_data="status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"🤖 <b>بوت نشر إشارات OTC - فوركس</b>\n\n"
        f"📡 القناة: <code>{channel}</code>\n"
        f"⚡ النشر: {status}\n"
        f"📊 العملة الحالية: <b>{symbol}</b>\n"
        f"📈 فريم الشمعة: {timeframe_str}\n"
        f"⏱️ مدة الصفقة: {duration} ثانية\n"
        f"📊 العملات المتاحة: {', '.join(FOREX_SYMBOLS)}\n\n"
        "استخدم الأزرار للتحكم:"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        await update.callback_query.answer()
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global publisher, publishing_thread
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "connect":
        if publisher.connected:
            await query.edit_message_text("✅ متصل بالفعل.")
            return
        success = publisher.connect()
        await query.edit_message_text("✅ تم الاتصال!" if success else "❌ فشل الاتصال. تأكد من SSID.")

    elif data == "balance":
        if not publisher.connected:
            await query.edit_message_text("⚠️ البوت غير متصل. اضغط 'اتصال بالمنصة' أولاً.")
            return
        balance = publisher.get_balance()
        if balance is not None:
            await query.edit_message_text(f"💰 الرصيد التجريبي: {balance:.2f}$")
        else:
            await query.edit_message_text("⚠️ فشل جلب الرصيد. قد تكون الجلسة منتهية.")

    elif data == "select_symbol":
        keyboard = [[InlineKeyboardButton(sym, callback_data=f"set_symbol_{sym}")] for sym in FOREX_SYMBOLS]
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📊 اختر العملة:", reply_markup=reply_markup)

    elif data.startswith("set_symbol_"):
        symbol = data.replace("set_symbol_", "")
        publisher.selected_symbol = symbol
        publisher.config["selected_symbol"] = symbol
        save_config(publisher.config)
        keyboard = [
            [InlineKeyboardButton("🕐 1 دقيقة", callback_data=f"set_tf_60")],
            [InlineKeyboardButton("🕐 5 دقائق", callback_data=f"set_tf_300")],
            [InlineKeyboardButton("🕐 15 دقيقة", callback_data=f"set_tf_900")],
            [InlineKeyboardButton("🕐 1 ساعة", callback_data=f"set_tf_3600")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="select_symbol")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"✅ تم تعيين العملة: {symbol}\nالآن اختر فريم الشمعة:", reply_markup=reply_markup)

    elif data.startswith("set_tf_"):
        tf = int(data.replace("set_tf_", ""))
        publisher.selected_timeframe = tf
        publisher.config["selected_timeframe"] = tf
        save_config(publisher.config)
        keyboard = [
            [InlineKeyboardButton(f"⏱️ {d} ثانية", callback_data=f"set_dur_{d}") for d in TRADE_DURATIONS[:2]],
            [InlineKeyboardButton(f"⏱️ {TRADE_DURATIONS[2]} ثانية", callback_data=f"set_dur_{TRADE_DURATIONS[2]}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="select_symbol")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        tf_str = {60: "1 دقيقة", 300: "5 دقائق", 900: "15 دقيقة", 3600: "1 ساعة"}.get(tf, f"{tf} ثانية")
        await query.edit_message_text(f"✅ تم تعيين فريم الشمعة: {tf_str}\nالآن اختر مدة الصفقة:", reply_markup=reply_markup)

    elif data.startswith("set_dur_"):
        dur = int(data.replace("set_dur_", ""))
        publisher.selected_duration = dur
        publisher.config["selected_duration"] = dur
        save_config(publisher.config)
        symbol = publisher.selected_symbol
        timeframe = publisher.selected_timeframe
        tf_str = {60: "1m", 300: "5m", 900: "15m", 3600: "1h"}.get(timeframe, f"{timeframe}s")
        await query.edit_message_text(
            f"✅ تم تعيين كل الإعدادات:\n"
            f"📊 العملة: {symbol}\n"
            f"📈 فريم الشمعة: {tf_str}\n"
            f"⏱️ مدة الصفقة: {dur} ثانية\n\n"
            "يمكنك الآن الضغط على '📈 إشارة فورية' للحصول على الإشارة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
        )

    elif data == "signal_now":
        if not publisher.connected:
            await query.edit_message_text("⚠️ البوت غير متصل. اضغط 'اتصال بالمنصة' أولاً.")
            return
        symbol = publisher.selected_symbol
        timeframe = publisher.selected_timeframe
        duration = publisher.selected_duration
        signal = publisher.generate_signal_for_symbol(symbol, timeframe)
        if signal["signal"] == "NO_DATA":
            await query.edit_message_text(f"⚠️ لا توجد بيانات كافية للعملة {symbol}.")
            return
        if signal["signal"] == "NO_CONNECTION":
            await query.edit_message_text("⚠️ البوت غير متصل.")
            return
        message = publisher.format_single_signal_message(symbol, signal, timeframe, duration)
        await query.edit_message_text(message, parse_mode="HTML")

    elif data == "set_channel":
        await query.edit_message_text(
            "📡 أرسل معرف القناة (مثل <code>@my_channel</code> أو <code>-100123456789</code>):",
            parse_mode="HTML"
        )
        context.user_data['awaiting_channel'] = True

    elif data == "toggle_publish":
        config = publisher.config
        config["enabled"] = not config.get("enabled", False)
        save_config(config)
        if config["enabled"]:
            if not publisher.connected:
                await query.edit_message_text("⚠️ البوت غير متصل. اضغط 'اتصال بالمنصة' أولاً.")
                return
            if not config.get("publish_channel"):
                await query.edit_message_text("⚠️ لم يتم تعيين قناة النشر. استخدم 'تعيين قناة النشر'.")
                return
            if publishing_thread is None or not publishing_thread.is_alive():
                bot = context.bot
                publishing_thread = threading.Thread(
                    target=lambda: publisher.run_loop(bot),
                    daemon=True
                )
                publishing_thread.start()
            await query.edit_message_text("✅ تم تفعيل النشر التلقائي.")
        else:
            publisher.stop()
            await query.edit_message_text("⏹️ تم إيقاف النشر التلقائي.")

    elif data == "status":
        channel = publisher.config.get("publish_channel") or "غير معين"
        symbol = publisher.selected_symbol
        tf_str = {60: "1m", 300: "5m", 900: "15m", 3600: "1h"}.get(publisher.selected_timeframe, f"{publisher.selected_timeframe}s")
        status_text = (
            f"📊 <b>حالة البوت</b>\n"
            f"🔗 الاتصال: {'✅ متصل' if publisher.connected else '❌ غير متصل'}\n"
            f"📡 القناة: <code>{channel}</code>\n"
            f"⚡ النشر: {'🟢 مفعل' if publisher.config.get('enabled') else '🔴 معطل'}\n"
            f"📊 العملة: {symbol}\n"
            f"📈 فريم الشمعة: {tf_str}\n"
            f"⏱️ مدة الصفقة: {publisher.selected_duration} ثانية\n"
            f"📊 العملات المتاحة: {len(FOREX_SYMBOLS)}"
        )
        await query.edit_message_text(status_text, parse_mode="HTML")

    elif data == "back_main":
        await start_command(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_channel'):
        channel = update.message.text.strip()
        config = publisher.config
        config["publish_channel"] = channel
        save_config(config)
        context.user_data['awaiting_channel'] = False
        await update.message.reply_text(f"✅ تم تعيين القناة إلى: <code>{channel}</code>", parse_mode="HTML")
        await start_command(update, context)

# ------------------- التشغيل -------------------
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 بوت الإشارات يعمل...")
    try:
        application.run_polling()
    except KeyboardInterrupt:
        print("\n[!] تم إيقاف البوت بواسطة المستخدم.")
        publisher.stop()
        sys.exit(0)

if __name__ == "__main__":
    main()
