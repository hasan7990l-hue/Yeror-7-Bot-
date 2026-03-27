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
from telethon.errors.rpcerrorlist import UserNotParticipantError
import cv2
import numpy as np

# استيراد المكتبة الحديثة المعتمدة لدعم Gemini 1.5 & 2.0
from google import genai
from google.genai import types

# ==========================================
# ضبط تشفير النظام ليدعم العربية في Termux و Railway
# ==========================================
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ==========================================
# بيانات الاعتماد والربط (Hyper Projects)
# ==========================================
API_ID = 27485469
API_HASH = '544459a0701b32741254945b08daebfe'
BOT_TOKEN = '8217717390:AAGsekYq5_wvyC23I48UobKnHQK3-SkiH6o'

# تم تحديث المفتاح الخاص بك هنا
GEMINI_KEY = "AIzaSyDkm0AKk4sECKdhzAOEpLXELQNML41XcZ4" 
client_ai = genai.Client(api_key=GEMINI_KEY)

OWNER_ID = 8456056018 
OWNER_USERNAME = "@Eror_7"
CHANNEL_USERNAME = "@Tl2_2" # قناة الاشتراك الإجباري

# ==========================================
# إعداد قاعدة البيانات المتطورة
# ==========================================
def setup_db():
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats 
                      (user_id INTEGER PRIMARY KEY, wins INTEGER, losses INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, join_date TEXT, status TEXT DEFAULT 'FREE')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS custom_buttons 
                      (btn_id TEXT PRIMARY KEY, btn_text TEXT, is_active INTEGER DEFAULT 1)''')

    default_btns = [
        ('how_it_works', '❓ طريقة الاستخدام'),
        ('my_stats', '📊 إحصائياتي'),
        ('risk_calc', '💰 حاسبة المخاطرة'),
        ('martingale_info', '🔄 نظام التعويض')
    ]
    cursor.executemany("INSERT OR IGNORE INTO custom_buttons (btn_id, btn_text) VALUES (?, ?)", default_btns)

    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'status' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'FREE'")
    
    conn.commit()
    conn.close()

setup_db()

# --- دالات مساعدة للإعدادات ---
def get_setting(key, default=None):
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def is_button_active(btn_id):
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM custom_buttons WHERE btn_id = ?", (btn_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] == 1 if row else True

def toggle_button(btn_id, status):
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE custom_buttons SET is_active = ? WHERE btn_id = ?", (status, btn_id))
    conn.commit()
    conn.close()

def update_stats(user_id, status):
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute("SELECT wins, losses FROM stats WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO stats (user_id, wins, losses) VALUES (?, ?, ?)", (user_id, 0, 0))
        wins, losses = 0, 0
    else:
        wins, losses = row
    if status == 'win':
        cursor.execute("UPDATE stats SET wins = wins + 1 WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("UPDATE stats SET losses = losses + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, join_date, status) VALUES (?, ?, ?)", 
                   (user_id, datetime.now().strftime("%Y-%m-%d"), 'FREE'))
    conn.commit()
    conn.close()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# محرك التحليل والمنع (Hyper Vision V5.0 - Gemini AI)
# ==========================================
def is_chart_image(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: return False
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask_green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
        mask_red = cv2.inRange(hsv, np.array([0, 50, 50]), np.array([10, 255, 255]))
        green_ratio = cv2.countNonZero(mask_green) / (img.shape[0] * img.shape[1])
        red_ratio = cv2.countNonZero(mask_red) / (img.shape[0] * img.shape[1])
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=50, maxLineGap=10)
        if (green_ratio + red_ratio) > 0.015 and lines is not None:
            return True
        return False
    except:
        return False

async def local_vision_analysis(image_bytes):
    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        prompt = """أنت خبير تداول محترف. حلل صورة الشارت تقنياً وأعطِ إشارة واضحة: [BUY_SIGNAL] للشراء أو [SELL_SIGNAL] للبيع، مع توضيح السبب ونسبة القوة."""
        
        response = await asyncio.to_thread(
            client_ai.models.generate_content,
            model="gemini-1.5-flash",
            contents=[prompt, image_part]
        )
        
        full_text = response.text
        img_type = "up_img" if "[BUY_SIGNAL]" in full_text else "down_img"
        clean_text = full_text.replace("[BUY_SIGNAL]", "").replace("[SELL_SIGNAL]", "").strip()
        
        return f"🚀 **نتائج تحليل Hyper Vision AI:**\n\n{clean_text}", img_type
    except Exception as e:
        logger.error(f"AI Engine Error: {str(e)}")
        return f"⚠️ خطأ في المحرك الذكي: {str(e)}", None

# ==========================================
# إعداد عميل التيليجرام (Telethon)
# ==========================================
client = TelegramClient('pocket_option_session', API_ID, API_HASH)

async def check_subscription(user_id):
    if user_id == OWNER_ID: return True
    try:
        await client(GetParticipantRequest(channel=CHANNEL_USERNAME, user_id=user_id))
        return True
    except UserNotParticipantError: return False
    except: return True 

START_TEXT = (
    f"🚀 **مرحباً بك في Hyper Trading System**\n\n"
    f"أنا المساعد الذكي المطور خصيصاً لتحليل أسواق الخيارات الثنائية. "
    f"أعمل بأحدث تقنيات Gemini AI للرؤية الحاسوبية.\n\n"
    f"🛡️ **للبدء:** أرسل صورة الشارت الآن.\n\n"
    f"👨‍💻 **المطور:** {OWNER_USERNAME}"
)

def get_start_buttons():
    btns = []
    row1 = []
    if is_button_active('how_it_works'): row1.append(Button.inline("❓ طريقة الاستخدام", b"how_it_works"))
    if is_button_active('my_stats'): row1.append(Button.inline("📊 إحصائياتي", b"my_stats"))
    if row1: btns.append(row1)
    row2 = []
    if is_button_active('risk_calc'): row2.append(Button.inline("💰 حاسبة المخاطرة", b"risk_calc"))
    if is_button_active('martingale_info'): row2.append(Button.inline("🔄 نظام التعويض", b"martingale_info"))
    if row2: btns.append(row2)
    btns.append([Button.url("🌐 قناة التحديثات", f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")])
    return btns

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if not await check_subscription(event.sender_id):
        return await event.respond(f"⚠️ **اشترك بالقناة أولاً!**", buttons=[Button.url("🔗 اشتراك", f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")])
    add_user(event.sender_id)
    welcome_img = get_setting('welcome_img')
    if welcome_img: await client.send_file(event.chat_id, welcome_img, caption=START_TEXT, buttons=get_start_buttons())
    else: await event.respond(START_TEXT, buttons=get_start_buttons())

@client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if event.sender_id != OWNER_ID: return await event.respond("⚠️ للمطور فقط.")
    conn = sqlite3.connect('trading_history.db'); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users"); total_users = cursor.fetchone()[0]; conn.close()
    admin_text = f"🛠️ **لوحة التحكم**\n\n📊 عدد المستخدمين: {total_users}"
    buttons = [[Button.inline("🖼️ تعيين صور النظام", b"set_images")], [Button.inline("🔘 إدارة الأزرار", b"manage_btns")], [Button.inline("📢 إذاعة", b"broadcast")], [Button.inline("🔙 القائمة", b"back_to_start")]]
    admin_img = get_setting('admin_img')
    if admin_img: await client.send_file(event.chat_id, admin_img, caption=admin_text, buttons=buttons)
    else: await event.respond(admin_text, buttons=buttons)

@client.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id; data = event.data
    if not await check_subscription(user_id): return await event.answer("⚠️ اشترك أولاً!", alert=True)

    if data == b"back_to_start":
        await event.delete(); welcome_img = get_setting('welcome_img')
        if welcome_img: await client.send_file(event.chat_id, welcome_img, caption=START_TEXT, buttons=get_start_buttons())
        else: await client.send_message(event.chat_id, START_TEXT, buttons=get_start_buttons())

    elif data == b"set_images":
        btns = [[Button.inline("👋 الترحيب", b"set_welcome_img")], [Button.inline("🛠️ الإدارة", b"set_admin_img")], [Button.inline("📈 صعود", b"set_up_img")], [Button.inline("📉 هبوط", b"set_down_img")], [Button.inline("🔙 عودة", b"back_admin")]]
        await event.edit("🖼️ إعدادات الصور:", buttons=btns)

    elif data.startswith(b"set_") and data.endswith(b"_img"):
        img_key = data.decode().replace("set_", ""); await event.delete()
        async with client.conversation(user_id) as conv:
            await conv.send_message("📸 أرسل الصورة الآن:"); msg = await conv.get_response()
            if msg.photo:
                if not os.path.exists('settings'): os.makedirs('settings')
                file_path = await client.download_media(msg.photo, file="settings/"); set_setting(img_key, file_path)
                await conv.send_message("✅ تم التحديث!")
            else: await conv.send_message("❌ إلغاء.")

    elif data == b"manage_btns":
        btns = [[Button.inline(f"{'🔴 حذف' if is_button_active(b) else '🟢 تفعيل'} {b}", f"tog_{b}".encode()) for b in ['how_it_works', 'my_stats']], [Button.inline("🔙 عودة", b"back_admin")]]
        await event.edit("🔘 إدارة الأزرار:", buttons=btns)

    elif data.startswith(b"tog_"):
        btn_id = data.decode().replace("tog_", ""); toggle_button(btn_id, 0 if is_button_active(btn_id) else 1)
        await callback_handler(event) # تحديث القائمة

    elif data == b"back_admin": await admin_panel(event)
    elif data == b"win": update_stats(user_id, 'win'); await event.edit("🎯 تم تسجيل الربح!")
    elif data == b"loss": update_stats(user_id, 'loss'); await event.edit("⚠️ تم تسجيل الخسارة.")

    elif data == b"broadcast":
        async with client.conversation(user_id) as conv:
            await conv.send_message("📝 أكتب الرسالة:"); msg = await conv.get_response()
            conn = sqlite3.connect('trading_history.db'); cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users"); users = cursor.fetchall(); conn.close()
            for u in users:
                try: await client.send_message(u[0], msg.text)
                except: continue
            await conv.send_message("✅ تم.")

    elif data == b"how_it_works":
        await event.respond("💡 التقط صورة واضحة للشارت وأرسلها هنا.", buttons=[[Button.inline("🔙 عودة", b"back_to_start")]])

    elif data == b"my_stats":
        conn = sqlite3.connect('trading_history.db'); cursor = conn.cursor()
        cursor.execute("SELECT wins, losses FROM stats WHERE user_id = ?", (user_id,)); row = cursor.fetchone(); conn.close()
        text = f"📊 إحصائياتك: ✅ {row[0] if row else 0} | ❌ {row[1] if row else 0}"
        await event.respond(text, buttons=[[Button.inline("🔙 عودة", b"back_to_start")]])

@client.on(events.NewMessage)
async def handle_messages(event):
    if event.text and event.text.startswith('/'): return
    if not await check_subscription(event.sender_id): return

    if event.photo:
        photo_data = await event.download_media(file=bytes)
        if not is_chart_image(photo_data): return await event.respond("⚠️ أرسل صورة شارت واضحة.")
        
        # نظام الحذف الجديد
        status_msg = await event.respond("🔍 **جاري تشغيل محرك Hyper AI...**")
        await asyncio.sleep(0.5); await status_msg.edit("⚙️ **جاري التحليل الفني...**")

        try:
            result_text_ai, img_type = await local_vision_analysis(photo_data)
            analysis_buttons = [[Button.inline("✅ ربح", b"win"), Button.inline("❌ خسارة", b"loss")], [Button.inline("🔙 الرئيسية", b"back_to_start")]]
            
            # تنفيذ التعديل بالحذف لضمان عمله على Railway
            await status_msg.delete()
            await asyncio.sleep(0.5)
            
            custom_img = get_setting(img_type)
            if custom_img and os.path.exists(custom_img):
                await client.send_file(event.chat_id, custom_img, caption=result_text_ai, buttons=analysis_buttons)
            else:
                await client.send_message(event.chat_id, result_text_ai, buttons=analysis_buttons)
        except Exception as e:
            try: await status_msg.delete()
            except: pass
            await event.respond(f"❌ خطأ: {str(e)}")

    elif event.text and "حساب" in event.text:
        try:
            p = event.text.split(); b, r = float(p[1]), float(p[2])
            await event.respond(f"💰 مخاطرة: **${b*(r/100):.2f}**")
        except: pass

    elif event.is_private and event.text:
        loading = await event.respond("🌀 **جاري معالجة طلبك...**")
        await asyncio.sleep(0.8); await loading.delete()
        
        t = event.text.lower()
        if any(w in t for w in ["هلا", "مرحبا"]): res = "أهلاً بك! أرسل صورة الشارت وسأحللها لك."
        else: res = f"استلمت رسالتك: '{event.text}'. هل تريد تحليل شارت؟"
        await event.respond(res)

async def main():
    if not os.path.exists('settings'): os.makedirs('settings')
    print("⚡ HYPER VISION V5.0 ONLINE ⚡")
    await client.start(bot_token=BOT_TOKEN)
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
