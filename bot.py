import io
import logging
import asyncio
import sys
import os
import sqlite3
import base64
import json
import requests
import time
import random
from datetime import datetime, timedelta
from PIL import Image, ImageEnhance, ImageOps
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors.rpcerrorlist import UserNotParticipantError, FloodWaitError
import cv2
import numpy as np

# ==========================================
# ضبط التشفير والبيانات الأساسية
# ==========================================
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_ID = 27485469
API_HASH = '544459a0701b32741254945b08daebfe'
BOT_TOKEN = '8217717390:AAGsekYq5_wvyC23I48UobKnHQK3-SkiH6o'

OWNER_ID = 8456056018 
OWNER_USERNAME = "@Eror_7"
DEFAULT_CHANNEL = "@Tl2_2"

# ==========================================
# إدارة قاعدة البيانات (بدون أي حذف)
# ==========================================
def setup_db():
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats (user_id INTEGER PRIMARY KEY, wins INTEGER, losses INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TEXT, status TEXT DEFAULT 'FREE')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS custom_buttons (btn_id TEXT PRIMARY KEY, btn_text TEXT, is_active INTEGER DEFAULT 1)''')
    
    default_btns = [
        ('how_it_works', '❓ طريقة الاستخدام'), 
        ('my_stats', '📊 إحصائياتي'), 
        ('risk_calc', '💰 حاسبة المخاطرة'), 
        ('martingale_info', '🔄 نظام التعويض')
    ]
    cursor.executemany("INSERT OR IGNORE INTO custom_buttons (btn_id, btn_text) VALUES (?, ?)", default_btns)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('channel_username', DEFAULT_CHANNEL))
    conn.commit()
    conn.close()

setup_db()

def get_setting(key, default=None):
    with sqlite3.connect('trading_history.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def update_stats(user_id, status):
    with sqlite3.connect('trading_history.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT wins, losses FROM stats WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO stats (user_id, wins, losses) VALUES (?, ?, ?)", (user_id, 0, 0))
            w, l = 0, 0
        else: w, l = row
        if status == 'win':
            cursor.execute("UPDATE stats SET wins = wins + 1 WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("UPDATE stats SET losses = losses + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

# ==========================================
# محرك التحليل المحلي (بدون API - قراءة مباشرة)
# ==========================================
def analyze_chart_locally(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return "❌ تعذر قراءة الصورة.", None
        
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # تحديد الشموع الخضراء
        lower_green = np.array([35, 40, 40])
        upper_green = np.array([85, 255, 255])
        mask_green = cv2.inRange(hsv, lower_green, upper_green)
        green_pixels = cv2.countNonZero(mask_green)
        
        # تحديد الشموع الحمراء
        lower_red = np.array([0, 50, 50])
        upper_red = np.array([10, 255, 255])
        mask_red = cv2.inRange(hsv, lower_red, upper_red)
        red_pixels = cv2.countNonZero(mask_red)
        
        total = green_pixels + red_pixels
        if total == 0: return "⚠️ لم يتم اكتشاف شموع تداول واضحة.", None
        
        green_p = (green_pixels / total) * 100
        red_p = (red_pixels / total) * 100
        
        if green_p > 52:
            res = f"🚀 **تحليل Hyper Vision (محلي):**\n\n✅ الإشارة: **شراء (BUY)**\n📊 قوة الثيران: {green_p:.1f}%\n📈 الاتجاه: صاعد"
            return res, "up_img"
        elif red_p > 52:
            res = f"📉 **تحليل Hyper Vision (محلي):**\n\n✅ الإشارة: **بيع (SELL)**\n📊 قوة الدببة: {red_p:.1f}%\n📉 الاتجاه: هابط"
            return res, "down_img"
        else:
            return "⚖️ **حالة السوق: تذبذب**\nيفضل انتظار شمعة تأكيدية قوية.", None
    except Exception as e:
        return f"❌ خطأ في المحرك المحلي: {str(e)}", None

# ==========================================
# نظام التيليجرام والواجهات (بدون اختصار)
# ==========================================
client = TelegramClient('hyper_final_v5_session', API_ID, API_HASH)

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    with sqlite3.connect('trading_history.db') as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, join_date) VALUES (?, ?)", (user_id, datetime.now().strftime("%Y-%m-%d")))
    
    welcome_msg = (
        "⚡ **مرحباً بك في Hyper Vision V5.0**\n\n"
        "هذا النظام يعمل بالتحليل البرمجي المباشر للشموع اليابانية.\n"
        "فقط أرسل صورة الشارت وسأقوم بالتحليل فوراً."
    )
    buttons = [
        [Button.inline("❓ طريقة الاستخدام", b"how_it_works"), Button.inline("📊 إحصائياتي", b"my_stats")],
        [Button.inline("💰 حاسبة المخاطرة", b"risk_calc"), Button.inline("🔄 نظام التعويض", b"martingale_info")],
        [Button.url("🌐 قناة التوصيات", f"https://t.me/{get_setting('channel_username', DEFAULT_CHANNEL).replace('@','')}")]
    ]
    await event.respond(welcome_msg, buttons=buttons)

@client.on(events.NewMessage)
async def message_listener(event):
    if not event.is_private or event.text.startswith('/'): return
    
    if event.photo:
        status_msg = await event.respond("🔍 جاري فحص الشارت محلياً...")
        photo_bytes = await event.download_media(file=bytes)
        
        analysis_result, img_type = analyze_chart_locally(photo_bytes)
        await status_msg.delete()
        
        final_buttons = [[Button.inline("✅ ربح", b"win"), Button.inline("❌ خسارة", b"loss")]]
        await event.respond(analysis_result, buttons=final_buttons)
    
    elif event.text:
        await event.respond("🤖 **Hyper AI:** أنا مبرمج حالياً لتحليل صور الشارت فقط. يرجى إرسال صورة واضحة للسوق.")

@client.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data
    user_id = event.sender_id
    
    if data == b"win":
        update_stats(user_id, 'win')
        await event.answer("🎉 مبروك! تم تسجيل الصفقة كربح.", alert=True)
    elif data == b"loss":
        update_stats(user_id, 'loss')
        await event.answer("📉 معوضة خير، تم تسجيل الخسارة.", alert=True)
    elif data == b"my_stats":
        with sqlite3.connect('trading_history.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT wins, losses FROM stats WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            wins, losses = row if row else (0, 0)
        await event.respond(f"📊 **إحصائياتك:**\n\n✅ صفقات ناجحة: {wins}\n❌ صفقات خاسرة: {losses}")
    elif data == b"how_it_works":
        text = "💡 **طريقة العمل:**\n1. افتح منصة التداول.\n2. خذ لقطة شاشة واضحة للشمعات.\n3. أرسل الصورة هنا وسيتم تحليل الزخم فوراً."
        await event.respond(text)
    elif data == b"risk_calc":
        await event.respond("💰 **حاسبة المخاطرة:**\nيفضل عدم دخول الصفقة بأكثر من 1% إلى 3% من رأس مالك الكلي.")
    elif data == b"martingale_info":
        await event.respond("🔄 **نظام التعويض (مارتينجال):**\nفي حال الخسارة، يمكنك مضاعفة المبلغ x2.2 في الصفقة التالية لتعويض الخسارة (استخدمه بحذر).")

# ==========================================
# تشغيل البوت (حماية من الانهيار)
# ==========================================
async def run_bot():
    print("🚀 HYPER VISION V5.0 IS STARTING...")
    print("🛠 Local Analysis Engine: ACTIVE")
    try:
        await client.start(bot_token=BOT_TOKEN)
        print("✅ BOT IS ONLINE ON RAILWAY")
        await client.run_until_disconnected()
    except FloodWaitError as e:
        print(f"⚠️ FloodWait: Waiting {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
        await run_bot()
    except Exception as e:
        print(f"❌ Critical Error: {str(e)}")
        await asyncio.sleep(5)
        await run_bot()

if __name__ == '__main__':
    asyncio.run(run_bot())
