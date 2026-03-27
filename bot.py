import os
import asyncio
import time
import glob
import re
import json
import requests
import shutil 
from loguru import logger 

# --- إعداد المجلدات الضرورية لنظام الرفع المباشر ---
if not os.path.exists('downloads'):
    os.makedirs('downloads')
if not os.path.exists('assets'):
    os.makedirs('assets')

# --- إعداد ملف السجلات (Logs) للمراقبة الاحترافية ---
logger.add("bot_activity.log", rotation="10 MB", retention="3 days", compression="zip")

from telethon import TelegramClient, events, utils, Button
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo
from telethon.network import ConnectionTcpFull
from telethon.errors import UserNotParticipantError, ForbiddenError, WebpageMediaEmptyError
from telethon.tl.functions.channels import GetParticipantRequest, GetFullChannelRequest
import yt_dlp

# --- إعداد نظام التعرف على الموسيقى AcoustID ---
ACOUSTID_AVAILABLE = False
try:
    import acoustid
    ACOUSTID_AVAILABLE = True
    ACOUSTID_API_KEY = 'H68K069UsY' 
    logger.info("🎵 نظام AcoustID نشط وجاهز للتعرف على الموسيقى.")
except ImportError:
    logger.error("❌ مكتبة pyacoustid مفقودة! ميزة التعرف معطلة.")

# --- بيانات البوت والمطور ---
API_ID = 27485469
API_HASH = '544459a0701b32741254945b08daebfe'
BOT_TOKEN = '8180650384:AAE0M2gDMWQ6MuXvSLXNRPpfJWMiafTjyxI'
DEV_ID = 8456056018 
DEV_USER = '@Eror_7' 
CH_USERNAME = '@lb2_c' 

DB_FILE = "bot_data.json"
download_semaphore = asyncio.Semaphore(10) 

# مخازن البيانات المؤقتة
active_tasks = {}
pending_verify_msgs = {}
search_results = {}
broadcast_tasks = {} 
cancelled_conversations = set() 

# --- نظام قاعدة البيانات ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "users": [], 
            "channels": [CH_USERNAME], 
            "welcome_msg": None,
            "start_img": "assets/start.jpg",
            "admin_img": "assets/admin.jpg",
            "format_img": "assets/format.jpg", 
            "notify_join": True,
            "notify_left": True,
            "user_stats": {}, 
            "language": "ar"
        }
    with open(DB_FILE, "r") as f:
        data = json.load(f)
        # تصحيح مسارات الصور لتكون محلية (حل مشكلة الروابط التالفة)
        if "start_img" not in data or data["start_img"].startswith("http"): data["start_img"] = "assets/start.jpg"
        if "admin_img" not in data or data["admin_img"].startswith("http"): data["admin_img"] = "assets/admin.jpg"
        if "format_img" not in data or data["format_img"].startswith("http"): data["format_img"] = "assets/format.jpg"
        return data

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

db = load_db()

# --- إعداد العميل (Telethon) ---
bot = TelegramClient(
    'FaqedYoutubeBot', 
    API_ID, 
    API_HASH,
    connection_retries=None, 
    retry_delay=10, 
    auto_reconnect=True,
    connection=ConnectionTcpFull
)

# --- دالة الإرسال الآمن (لحل مشكلة WebpageMediaEmptyError) ---
async def send_safe_file(chat_id, key, caption, buttons, reply_to=None):
    file_path = db.get(key)
    try:
        if file_path and os.path.exists(file_path):
            await bot.send_file(chat_id, file_path, caption=caption, buttons=buttons, reply_to=reply_to)
        else:
            # إذا لم توجد الصورة محلياً، نرسل النص فقط لضمان عدم توقف البوت
            await bot.send_message(chat_id, caption, buttons=buttons, reply_to=reply_to)
    except Exception as e:
        logger.error(f"Error sending file {key}: {e}")
        await bot.send_message(chat_id, caption, buttons=buttons, reply_to=reply_to)

# --- الدوال المساعدة ---
def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

async def get_dynamic_names():
    try:
        target_ch = db["channels"][0] if db["channels"] else CH_USERNAME
        ch_entity = await bot.get_entity(target_ch)
        ch_name = ch_entity.title
        dev_entity = await bot.get_entity(DEV_ID)
        dev_display_name = dev_entity.first_name
        return ch_name, dev_display_name
    except:
        return "قناة السورس", "المطور"

async def check_subscription(user_id):
    if user_id == DEV_ID: return True
    for ch in db["channels"]:
        try:
            await bot(GetParticipantRequest(ch, user_id))
        except:
            return False
    return True

async def progress_bar(current, total, event, start_time, action="الرفع", task_id=None):
    now = time.time()
    diff = now - start_time
    if getattr(event, '_last_update', 0) > now - 1.5: return
    event._last_update = now
    
    percentage = current * 100 / total
    speed = current / diff if diff > 0 else 0
    speed_mb = speed / (1024 * 1024)
    filled_len = int(12 * current // total)
    bar = '🎬' * filled_len + '▫️' * (12 - filled_len)
    
    msg = (f"**🚀 نظام الرفع السحابي**\n**━━━━━━━━━━━━━━━━━━**\n"
           f"**⚙️ العملية:** `{action}`\n**[{bar}] {percentage:.1f}%**\n"
           f"**⚡️ السرعة:** `{speed_mb:.2f} MB/s`\n**━━━━━━━━━━━━━━━━━━**")
    
    buttons = [[Button.inline("❌ إلغاء", f"cancel_{task_id}")]] if task_id else []
    try: await event.edit(msg, buttons=buttons)
    except: pass

def get_ydl_opts(uid, fmt="mp3"):
    has_aria2 = shutil.which("aria2c") is not None
    if fmt == "mp3":
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'downloads/{uid}.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
        }
    else:
        opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': f'downloads/{uid}.%(ext)s',
        }
    
    common = {
        'nocheckcertificate': True, 'quiet': True, 'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if has_aria2:
        common.update({'external_downloader': 'aria2c', 'external_downloader_args': ['--min-split-size=1M', '--max-connection-per-server=16', '--split=32']})
    
    opts.update(common)
    return opts

async def recognize_audio_logic(file_path):
    if not ACOUSTID_AVAILABLE or not shutil.which("fpcalc"): return {"found": False}
    try:
        def get_match(): return list(acoustid.match(ACOUSTID_API_KEY, file_path))
        results = await asyncio.to_thread(get_match)
        if results:
            score, recording_id, title, artist = results[0]
            return {"found": True, "title": title, "subtitle": artist, "full": f"{title} - {artist}"}
    except: pass
    return {"found": False}

# --- الأحداث (Events) ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    user_id = event.sender_id
    if str(user_id) not in db["user_stats"]: db["user_stats"][str(user_id)] = 0
    db["user_stats"][str(user_id)] += 1
    if user_id not in db["users"]:
        db["users"].append(user_id)
        save_db(db)
        try: await bot.send_message(DEV_ID, f"🔔 دخول مستخدم جديد: `{user_id}`")
        except: pass

    if not await check_subscription(user_id):
        buttons = [[Button.url("اشترك هنا", f"https://t.me/{CH_USERNAME[1:]}")], [Button.url("🔄 تم الاشتراك", f"https://t.me/{(await bot.get_me()).username}?start=verify")]]
        return await bot.send_message(event.chat_id, "**⚠️ يجب عليك الاشتراك في القناة لاستخدام البوت.**", buttons=buttons)

    ch_name, dev_display_name = await get_dynamic_names()
    welcome_text = (f"**🌟 مرحباً بك في أسرع بوت تحميل!**\n**━━━━━━━━━━━━━━━━━━**\n"
                   f"**أنا أدعم يوتيوب، تيك توك، والتعرف على الموسيقى.**\n\n"
                   f"**📟 المطور:** {DEV_USER}")
    buttons = [[Button.url(f"📢 {ch_name}", f"https://t.me/{CH_USERNAME[1:]}")], [Button.url(f"👨‍💻 {dev_display_name}", f"https://t.me/{DEV_USER[1:]}")]]
    await send_safe_file(event.chat_id, "start_img", welcome_text, buttons)

@bot.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if event.sender_id != DEV_ID: return
    text = "**🛠 لوحة التحكم - نظام الرفع المباشر**\n\nاستخدم الأزرار لتحديث صور البوت برفعها مباشرة."
    buttons = [
        [Button.inline("📊 الإحصائيات", "stats")],
        [Button.inline("🖼 تحديث الصور (رفع)", "img_settings")],
        [Button.inline("🗑 تنظيف الملفات", "clean_cache")],
        [Button.inline("❌ إغلاق", "close_admin")]
    ]
    await send_safe_file(event.chat_id, "admin_img", text, buttons)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    u_id = event.sender_id
    
    if data == "stats":
        total = sum(db["user_stats"].values())
        await event.edit(f"**📊 إحصائيات:**\n**الأعضاء:** `{len(db['users'])}` \n**العمليات:** `{total}`", buttons=[Button.inline("🔙 رجوع", "admin_panel_back")])
    
    elif data == "admin_panel_back":
        await admin_panel(event)

    elif data == "img_settings":
        buttons = [[Button.inline("🖼 صورة الترحيب", "set_start_img")], [Button.inline("🖼 صورة اختيار الصيغ", "set_format_img")], [Button.inline("🔙 رجوع", "admin_panel_back")]]
        await event.edit("**🖼 اختر الصورة المراد تحديثها (ارسلها كملف بعد الضغط):**", buttons=buttons)

    elif data in ["set_start_img", "set_format_img"]:
        key = data.replace("set_", "")
        async with bot.conversation(event.chat_id, timeout=60) as conv:
            await conv.send_message("**📤 ارسل الآن الصورة (ملف أو صورة):**")
            msg = await conv.get_response()
            if msg.photo or msg.document:
                path = f"assets/{key}.jpg"
                await bot.download_media(msg, path)
                db[key] = path
                save_db(db)
                await conv.send_message("✅ تم الحفظ بنجاح!")
        await admin_panel(event)

    elif data.startswith("dl_"):
        mode = "mp3" if "mp3" in data else "mp4"
        msg = await event.get_message()
        url = re.search(r'(https?://[^\s]+)', msg.text).group(1)
        await event.delete()
        task_id = str(event.id)
        active_tasks[task_id] = asyncio.create_task(process_youtube_download(event, url, task_id, mode))

    elif data == "clean_cache":
        for f in glob.glob("downloads/*"): 
            try: os.remove(f)
            except: pass
        await event.answer("✅ تم التنظيف", alert=True)

    elif data == "close_admin":
        await event.delete()

async def process_youtube_download(event, url, task_id, mode="mp3"):
    try:
        async with download_semaphore:
            status = await bot.send_message(event.chat_id, "⚡️ **جاري التحميل...**")
            ydl_opts = get_ydl_opts(task_id, mode)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(lambda: ydl.extract_info(url, download=True))
                ext = 'mp3' if mode == 'mp3' else 'mp4'
                file_path = f"downloads/{task_id}.{ext}"
                if not os.path.exists(file_path):
                    for f in glob.glob(f"downloads/{task_id}.*"): file_path = f; break
                
                start_time = time.time()
                await status.edit("🚀 **جاري الرفع...**")
                await bot.send_file(event.chat_id, file_path, caption=f"**🎬 {info.get('title')}**", progress_callback=lambda c, t: progress_bar(c, t, status, start_time, "رفع", task_id))
                await status.delete()
    except Exception as e:
        logger.error(f"Download error: {e}")
    finally:
        for f in glob.glob(f"downloads/*{task_id}*"):
            try: os.remove(f)
            except: pass

@bot.on(events.NewMessage(pattern=r'(https?://).+'))
async def handle_links(event):
    if not await check_subscription(event.sender_id): return
    url = event.text
    format_text = f"**🔗 تم فحص الرابط بنجاح!**\n\n{url}\n\n**📥 اختر الصيغة:**"
    buttons = [[Button.inline("🎵 MP3", "dl_mp3"), Button.inline("🎥 MP4", "dl_mp4")]]
    await send_safe_file(event.chat_id, "format_img", format_text, buttons, reply_to=event.id)

@bot.on(events.NewMessage(func=lambda e: e.text and not e.text.startswith('/') and not e.text.startswith('http')))
async def search_handler(event):
    if not await check_subscription(event.sender_id): return
    query = event.text
    # حل مشكلة EntityBoundsInvalidError بضمان نص نظيف بدون Markdown مكسور
    search_msg = await event.reply(f"🔍 جاري البحث عن: `{query}`")
    try:
        ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(lambda: ydl.extract_info(f"ytsearch1:{query}", download=False))
            if not info['entries']: return await search_msg.edit("❌ لا توجد نتائج.")
            res = info['entries'][0]
            caption = f"**🎯 نتيجة البحث الأولى:**\n\n**📝 العنوان:** {res['title']}\n**🔗 الرابط:** {res['webpage_url']}"
            buttons = [[Button.inline("🎵 MP3", "dl_mp3"), Button.inline("🎥 MP4", "dl_mp4")]]
            await search_msg.delete()
            await send_safe_file(event.chat_id, "format_img", caption, buttons)
    except:
        await search_msg.edit("❌ حدث خطأ أثناء البحث.")

async def main():
    logger.success("🚀 البوت الآن في وضع التشغيل الكامل على Railway!")
    await bot.start(bot_token=BOT_TOKEN)
    await bot.run_until_disconnected()

if __name__ == '__main__':
    # حل مشكلة RuntimeError: There is no current event loop
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
