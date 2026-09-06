#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
import time
import threading
from datetime import datetime
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

try:
    from pocketoptionapi.stable_api import PocketOption
    LIB_TYPE = "pocketoptionapi2"
except ImportError:
    try:
        from pocket_option import PocketOptionClient, AuthorizationData
        LIB_TYPE = "pocket_option"
    except ImportError:
        LIB_TYPE = "none"

CONFIG_FILE = "signal_config.json"
CREDENTIALS_FILE = "pocket_credentials.json"
BOT_TOKEN = "8604552604:AAHcgisRhhpDVi4wXj29EFooNEBH-AKEfcA"

FOREX_SYMBOLS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC", "USDCAD-OTC"]
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

    def connect(self) -> bool:
        try:
            if LIB_TYPE == "pocketoptionapi2":
                self.client = PocketOption(demo=True)
                self.client.connect()
                self.connected = True
                return True
        except Exception:
            pass
        self.connected = False
        return False

    def get_candles(self, symbol: str, timeframe: int = 60, limit: int = 30) -> List:
        if not self.connected or not self.client:
            return []
        try:
            return self.client.get_candles(symbol, timeframe, limit)
        except Exception:
            return []

    def get_balance(self) -> float:
        if not self.connected or not self.client:
            return 0.0
        try:
            return self.client.get_balance()
        except Exception:
            return 0.0

    def generate_signal_for_symbol(self, symbol: str, timeframe: int = 60) -> Dict:
        if not self.connected:
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

    if data == "connect":
        success = publisher.connect()
        await query.edit_message_text("✅ تم الاتصال!" if success else "❌ فشل الاتصال.")

    elif data == "balance":
        if not publisher.connected:
            await query.edit_message_text("⚠️ البوت غير متصل.")
            return
        bal = publisher.get_balance()
        await query.edit_message_text(f"💰 الرصيد: {bal:.2f}$")

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
            await query.edit_message_text("⚠️ البوت غير متصل.")
            return
        signal = publisher.generate_signal_for_symbol(publisher.selected_symbol, publisher.selected_timeframe)
        msg = publisher.format_single_signal_message(publisher.selected_symbol, signal, publisher.selected_timeframe, publisher.selected_duration)
        await query.edit_message_text(msg, parse_mode="HTML")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 البوت يعمل على Hugging Face...")
    app.run_polling()

if __name__ == "__main__":
    main()
