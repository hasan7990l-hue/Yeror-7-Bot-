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
DEFAULT_CHANNEL = "@Tl2_2"

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

    # التأكد من وجود إعداد القناة الافتراضية
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('channel_username', DEFAULT_CHANNEL))
    
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
    cursor.execute("UPDATE custom_buttons WHERE btn_id = ?", (status, btn_id))
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
        prompt = """أنت خبير تداول محترف. حلل صورة الشارت تقنياً وأعطِ إشارة واضحة: [BUY_SIGNAL] للشراء أو [SELL_SIGNAL] للبيع، مع توضيح السبب ونسبة القوة والدعم والمقاومة."""
        
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

async def ask_gemini(question):
    try:
        # تصحيح استدعاء الموديل ليكون مباشر بدون models/
        response = await asyncio.to_thread(
            client_ai.models.generate_content,
            model="gemini-1.5-flash",
            contents=[f"أجب على هذا السؤال باختصار وذكاء كخبير تداول: {question}"]
        )
        return response.text
    except Exception as e:
        return f"⚠️ عذراً، لم أستطع معالجة سؤالك الآن. ({str(e)})"

# ==========================================
# إعداد عميل التيليجرام (Telethon)
# ==========================================
client = TelegramClient('pocket_option_session', API_ID, API_HASH)

async def check_subscription(user_id):
    if user_id == OWNER_ID: return True
    channel = get_setting('channel_username', DEFAULT_CHANNEL)
    try:
        await client(GetParticipantRequest(channel=channel, user_id=user_id))
        return True
    except UserNotParticipantError: return False
    except: return True 

# نصوص الواجهة الجديدة
START_TEXT = (
    "🌟 **مرحباً بك في نظام Hyper Trading المطور V5.0** 🌟\n\n"
    "أنا مساعدك الذكي المعتمد على أقوى تقنيات الذكاء الاصطناعي لتحليل سوق الـ Binary Options.\n\n"
    "✅ **بماذا يمكنني مساعدتك؟**\n"
    "1️⃣ أرسل صورة للشارت لتحليلها فوراً.\n"
    "2️⃣ اسألني أي سؤال حول التداول وسأجيبك.\n"
    "3️⃣ استخدم أدوات الحساب المدمجة لإدارة مخاطرك.\n\n"
    f"🛠️ **المطور المسؤول:** {OWNER_USERNAME}\n"
    "🛡️ **الحالة:** متصل وجاهز للتحليل"
)

ADMIN_WELCOME = (
    "👨‍💻 **أهلاً بك يا مطورنا في لوحة التحكم**\n\n"
    "هنا يمكنك إدارة البوت بالكامل، التحكم بالأزرار، تغيير قنوات الاشتراك، وإرسال الإذاعات للمستخدمين."
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
    channel = get_setting('channel_username', DEFAULT_CHANNEL)
    btns.append([Button.url("🌐 قناة التحديثات", f"https://t.me/{channel.replace('@', '')}")])
    return btns

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if not await check_subscription(event.sender_id):
        channel = get_setting('channel_username', DEFAULT_CHANNEL)
        return await event.respond(f"⚠️ **عذراً! يجب عليك الاشتراك في القناة أولاً لاستخدام البوت.**", 
                                 buttons=[Button.url("🔗 اضغط هنا للاشتراك", f"https://t.me/{channel.replace('@', '')}")])
    add_user(event.sender_id)
    welcome_img = get_setting('welcome_img')
    if welcome_img: await client.send_file(event.chat_id, welcome_img, caption=START_TEXT, buttons=get_start_buttons())
    else: await event.respond(START_TEXT, buttons=get_start_buttons())

@client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if event.sender_id != OWNER_ID: return await event.respond("⚠️ هذا الأمر مخصص للمطور فقط.")
    conn = sqlite3.connect('trading_history.db'); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users"); total_users = cursor.fetchone()[0]; conn.close()
    
    admin_text = f"{ADMIN_WELCOME}\n\n📊 **إحصائيات النظام:**\n👥 عدد المشتركين: {total_users}\n📡 القناة الحالية: {get_setting('channel_username')}"
    
    buttons = [
        [Button.inline("🖼️ إعداد صور النظام", b"set_images"), Button.inline("🔘 إدارة الأزرار", b"manage_btns")],
        [Button.inline("📢 إذاعة عامة", b"broadcast"), Button.inline("🔗 قناة الاشتراك", b"set_channel")],
        [Button.inline("🔙 العودة للواجهة", b"back_to_start_del")]
    ]
    
    admin_img = get_setting('admin_img')
    if admin_img: await client.send_file(event.chat_id, admin_img, caption=admin_text, buttons=buttons)
    else: await event.respond(admin_text, buttons=buttons)

@client.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id; data = event.data
    
    # تنفيذ نظام الحذف لضمان التحديث النظيف
    if data in [b"back_to_start_del", b"back_admin_del"]:
        await event.delete()
        if data == b"back_to_start_del":
            welcome_img = get_setting('welcome_img')
            if welcome_img: await client.send_file(event.chat_id, welcome_img, caption=START_TEXT, buttons=get_start_buttons())
            else: await client.send_message(event.chat_id, START_TEXT, buttons=get_start_buttons())
        else:
            await admin_panel(event)
        return

    if not await check_subscription(user_id): return await event.answer("⚠️ اشترك أولاً!", alert=True)

    if data == b"set_images":
        btns = [
            [Button.inline("👋 صورة الترحيب", b"set_welcome_img"), Button.inline("🛠️ صورة الإدارة", b"set_admin_img")],
            [Button.inline("📈 صورة الصعود", b"set_up_img"), Button.inline("📉 صورة الهبوط", b"set_down_img")],
            [Button.inline("🔙 عودة", b"back_admin_del")]
        ]
        await event.delete()
        await client.send_message(event.chat_id, "🖼️ **إعدادات الوسائط:**\nاختر الصورة التي تريد تغييرها:", buttons=btns)

    elif data.startswith(b"set_") and data.endswith(b"_img"):
        img_key = data.decode().replace("set_", ""); await event.delete()
        async with client.conversation(user_id) as conv:
            await conv.send_message("📸 **أرسل الصورة الجديدة الآن (أو أرسل 'إلغاء'):**")
            msg = await conv.get_response()
            if msg.photo:
                if not os.path.exists('settings'): os.makedirs('settings')
                file_path = await client.download_media(msg.photo, file="settings/")
                set_setting(img_key, file_path)
                await conv.send_message("✅ تم تحديث الصورة بنجاح!")
                # العودة للوحة الإدارة
                await admin_panel(event)
            else: await conv.send_message("❌ تم إلغاء العملية.")

    elif data == b"set_channel":
        await event.delete()
        async with client.conversation(user_id) as conv:
            await conv.send_message("🔗 **أرسل يوزر القناة الجديد مع الـ @ (مثال: @Tl2_2):**")
            msg = await conv.get_response()
            if msg.text and msg.text.startswith("@"):
                set_setting('channel_username', msg.text)
                await conv.send_message(f"✅ تم تغيير قناة الاشتراك إلى: {msg.text}")
                await admin_panel(event)
            else: await conv.send_message("❌ يوزر غير صحيح.")

    elif data == b"manage_btns":
        btns = [
            [Button.inline(f"{'🔴 تعطيل' if is_button_active('how_it_works') else '🟢 تفعيل'} الاستخدام", b"tog_how_it_works")],
            [Button.inline(f"{'🔴 تعطيل' if is_button_active('my_stats') else '🟢 تفعيل'} الإحصائيات", b"tog_my_stats")],
            [Button.inline("🔙 عودة", b"back_admin_del")]
        ]
        await event.delete()
        await client.send_message(event.chat_id, "🔘 **إدارة أزرار الواجهة:**", buttons=btns)

    elif data.startswith(b"tog_"):
        btn_id = data.decode().replace("tog_", ""); 
        toggle_button(btn_id, 0 if is_button_active(btn_id) else 1)
        # تحديث القائمة فوراً
        await callback_handler(event)

    elif data == b"win": update_stats(user_id, 'win'); await event.answer("🎯 مبروك! تم تسجيل الربح.", alert=True)
    elif data == b"loss": update_stats(user_id, 'loss'); await event.answer("⚠️ تعوضها بإذن الله. تم تسجيل الخسارة.", alert=True)

    elif data == b"broadcast":
        await event.delete()
        async with client.conversation(user_id) as conv:
            await conv.send_message("📝 **أرسل الرسالة التي تريد إذاعتها (نص فقط):**")
            msg = await conv.get_response()
            conn = sqlite3.connect('trading_history.db'); cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users"); users = cursor.fetchall(); conn.close()
            sent = 0
            for u in users:
                try: await client.send_message(u[0], msg.text); sent += 1
                except: continue
            await conv.send_message(f"✅ تم إرسال الرسالة إلى {sent} مستخدم.")
            await admin_panel(event)

    elif data == b"how_it_works":
        await event.delete()
        text = "💡 **طريقة استخدام البوت:**\n\n1. ادخل لمنصة التداول الخاصة بك.\n2. التقط صورة شاشة (Screenshot) واضحة للشارت.\n3. أرسل الصورة هنا مباشرة.\n4. انتظر ثواني وسيقوم الذكاء الاصطناعي بتحليل الشموع والاتجاهات ليعطيك أفضل قرار (بيع أو شراء)."
        await client.send_message(event.chat_id, text, buttons=[[Button.inline("🔙 عودة", b"back_to_start_del")]])

    elif data == b"my_stats":
        conn = sqlite3.connect('trading_history.db'); cursor = conn.cursor()
        cursor.execute("SELECT wins, losses FROM stats WHERE user_id = ?", (user_id,)); row = cursor.fetchone(); conn.close()
        w = row[0] if row else 0; l = row[1] if row else 0
        text = f"📊 **إحصائياتك الشخصية:**\n\n✅ صفقات ناجحة: {w}\n❌ صفقات خاسرة: {l}\n📈 معدل الفوز: {(w/(w+l)*100 if (w+l)>0 else 0):.1f}%"
        await event.delete()
        await client.send_message(event.chat_id, text, buttons=[[Button.inline("🔙 عودة", b"back_to_start_del")]])

@client.on(events.NewMessage)
async def handle_messages(event):
    # منع التكرار والرد على البوت نفسه أو الأوامر
    if event.is_private is False: return 
    if not event.sender or event.sender.bot: return
    if event.text and event.text.startswith('/'): return
    if not await check_subscription(event.sender_id): return

    if event.photo:
        photo_data = await event.download_media(file=bytes)
        if not is_chart_image(photo_data): 
            return await event.respond("⚠️ عذراً، هذه لا تبدو صورة شارت تداول. يرجى إرسال صورة واضحة للشارت.")
        
        status_msg = await event.respond("🔍 **جاري تشغيل محرك Hyper AI...**")
        await asyncio.sleep(0.5); await status_msg.edit("⚙️ **جاري فحص الشموع والنماذج الفنية...**")

        try:
            result_text_ai, img_type = await local_vision_analysis(photo_data)
            analysis_buttons = [
                [Button.inline("✅ ربح", b"win"), Button.inline("❌ خسارة", b"loss")],
                [Button.inline("🔙 القائمة الرئيسية", b"back_to_start_del")]
            ]
            
            await status_msg.delete()
            await asyncio.sleep(0.3)
            
            custom_img = get_setting(img_type)
            if custom_img and os.path.exists(custom_img):
                await client.send_file(event.chat_id, custom_img, caption=result_text_ai, buttons=analysis_buttons)
            else:
                await client.send_message(event.chat_id, result_text_ai, buttons=analysis_buttons)
        except Exception as e:
            try: await status_msg.delete()
            except: pass
            await event.respond(f"❌ حدث خطأ أثناء التحليل: {str(e)}")

    elif event.text:
        t = event.text.lower()
        
        # حاسبة مخاطرة سريعة (تحسين المنطق لمنع الرد العشوائي)
        if "حساب" in t and any(char.isdigit() for char in t):
            try:
                parts = [float(s) for s in t.split() if s.replace('.','',1).isdigit()]
                if len(parts) >= 2:
                    balance, risk = parts[0], parts[1]
                    return await event.respond(f"💰 **حساب المخاطرة:**\nمبلغ الصفقة المناسب: **${balance*(risk/100):.2f}**")
            except: pass

        # ردود ذكية فقط للرسائل النصية التي ليست أوامر
        loading = await event.respond("🤔 **جاري التفكير...**")
        ai_reply = await ask_gemini(event.text)
        await loading.delete()
        await event.respond(f"🤖 **Hyper AI:**\n\n{ai_reply}")

async def main():
    if not os.path.exists('settings'): os.makedirs('settings')
    print("⚡ HYPER VISION V5.0 ONLINE - SYSTEM READY ⚡")
    await client.start(bot_token=BOT_TOKEN)
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
