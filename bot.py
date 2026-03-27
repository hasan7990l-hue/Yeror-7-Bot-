import os
import asyncio
import time
import glob
import re
import json
import requests
import shutil # مضافة للتأكد من وجود الأدوات البرمجية
from loguru import logger  # المكتبة المضافة للقوة الاحترافية ⚡️

# --- إعداد ملف السجلات (للمراقبة والحماية من الانهيار) ---
logger.add("bot_activity.log", rotation="10 MB", retention="3 days", compression="zip")

# محاولة استيراد uvloop لتحسين الأداء في تيرمكس والبيئات الداعمة
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    logger.success("🚀 تم تفعيل محرك uvloop بنجاح لسرعة قصوى!")
except ImportError:
    logger.warning("⚠️ مكتبة uvloop غير مثبتة، سيتم العمل بالمحرك الافتراضي.")
    pass

from telethon import TelegramClient, events, utils, Button
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeVideo
from telethon.network import ConnectionTcpFull
from telethon.errors import UserNotParticipantError, ForbiddenError
from telethon.tl.functions.channels import GetParticipantRequest, GetFullChannelRequest
import yt_dlp

# --- معالجة التعرف على الأغاني بن نظام AcoustID المتوافق مع تيرمكس ---
ACOUSTID_AVAILABLE = False
try:
    import acoustid
    ACOUSTID_AVAILABLE = True
    # تم تحديث مفتاح API الخاص بك هنا بنجاح ⚡
    ACOUSTID_API_KEY = 'H68K069UsY' 
    logger.info("🎵 نظام AcoustID نشط وجاهز للتعرف على الموسيقى.")
except ImportError:
    logger.error("❌ مكتبة pyacoustid مفقودة! ميزة التعرف معطلة.")
    print("⚠️ تحذير: مكتبة pyacoustid غير مثبتة. ميزة التعرف على الأغاني ستكون معطلة مؤقتاً.")

# --- بيانات المطور والقناة ---
API_ID = 27485469
API_HASH = '544459a0701b32741254945b08daebfe'
BOT_TOKEN = '8180650384:AAE0M2gDMWQ6MuXvSLXNRPpfJWMiafTjyxI'
DEV_ID = 8456056018 # ايدي المطور
DEV_USER = '@Eror_7' # يوزر المطور
CH_USERNAME = '@lb2_c' # يوزر القناة الافتراضية

# ملف البيانات لضمان عدم ضياع الإعدادات والصور
DB_FILE = "bot_data.json"

# --- تحديد عدد التحميلات المتزامنة (Semaphore) لزيادة الأداء ---
download_semaphore = asyncio.Semaphore(10) 

# مخازن البيانات
active_tasks = {}
pending_verify_msgs = {}
search_results = {}
broadcast_tasks = {} 
# القفل البرمجي لمنع تداخل الإذاعة بعد الإلغاء
cancelled_conversations = set() 

def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "users": [], 
            "channels": [CH_USERNAME], 
            "welcome_msg": None,
            "start_img": "https://graph.org/file/dc5a6064703a45a0e980a.jpg",
            "admin_img": "https://graph.org/file/984b39e6580f55e0a6d07.jpg",
            "format_img": "https://graph.org/file/dc5a6064703a45a0e980a.jpg", 
            "notify_join": True,
            "notify_left": True,
            "user_stats": {}, 
            "language": "ar"
        }
    with open(DB_FILE, "r") as f:
        data = json.load(f)
        if "start_img" not in data: data["start_img"] = "https://graph.org/file/dc5a6064703a45a0e980a.jpg"
        if "admin_img" not in data: data["admin_img"] = "https://graph.org/file/984b39e6580f55e0a6d07.jpg"
        if "format_img" not in data: data["format_img"] = "https://graph.org/file/dc5a6064703a45a0e980a.jpg"
        if "notify_join" not in data: data["notify_join"] = True
        if "notify_left" not in data: data["notify_left"] = True
        if "user_stats" not in data: data["user_stats"] = {}
        if "language" not in data: data["language"] = "ar"
        return data

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

db = load_db()

# --- تحسين إعدادات الاتصال لتجنب مشاكل الشبكة في تيرمكس ---
bot = TelegramClient(
    'FaqedYoutubeBot', 
    API_ID, 
    API_HASH,
    connection_retries=None, 
    retry_delay=10, 
    auto_reconnect=True,
    connection=ConnectionTcpFull
)

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

async def get_dynamic_names():
    try:
        target_ch = db["channels"][0] if db["channels"] else CH_USERNAME
        ch_entity = await bot.get_entity(target_ch)
        ch_name = ch_entity.title
        dev_entity = await bot.get_entity(DEV_ID)
        dev_display_name = dev_entity.first_name
        if dev_entity.last_name:
            dev_display_name += f" {dev_entity.last_name}"
        return ch_name, dev_display_name
    except Exception as e:
        logger.error(f"خطأ في جلب الأسماء الديناميكية: {e}")
        return "قناة السورس", "المطور"

async def get_all_channels_names():
    names_list = []
    for ch in db["channels"]:
        try:
            entity = await bot.get_entity(ch)
            names_list.append(f"• {entity.title} ({ch})")
        except:
            names_list.append(f"• قناة غير معروفة ({ch})")
    return "\n".join(names_list)

async def check_subscription(user_id):
    if user_id == DEV_ID: return True
    for ch in db["channels"]:
        try:
            await bot(GetParticipantRequest(ch, user_id))
        except UserNotParticipantError:
            return False
        except:
            continue
    return True

# --- [تحديث] كليشة الرفع السينمائية المحسنة ⚡️ ---
async def progress_bar(current, total, event, start_time, action="الرفع", task_id=None):
    now = time.time()
    diff = now - start_time
    if getattr(event, '_last_update', 0) > now - 1.2: 
        return
    event._last_update = now
    
    percentage = current * 100 / total
    speed = current / diff if diff > 0 else 0
    speed_mb = speed / (1024 * 1024)
    elapsed_time = round(diff)
    
    # حساب الوقت المتبقي التقديري
    remaining_bytes = total - current
    eta = round(remaining_bytes / speed) if speed > 0 else 0
    
    # تصميم شريط تقدم احترافي متدرج
    filled_len = int(12 * current // total)
    bar = '🎬' * filled_len + '▫️' * (12 - filled_len)
    
    msg = (
        f"**🚀 نظام الرفع السحابي النشط**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**⚙️ العملية:** `{action} الصاروخي`\n"
        f"**[{bar}] {percentage:.1f}%**\n\n"
        f"**📥 المكتمل:** `{current / (1024 * 1024):.2f}` / `{total / (1024 * 1024):.2f} MB`\n"
        f"**⚡️ السرعة الحالية:** `{speed_mb:.2f} MB/s`\n"
        f"**⏱ الوقت:** المنقضي `{elapsed_time}s` | المتبقي `{eta}s`\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📟 المطور:** {DEV_USER}"
    )
    
    buttons = []
    if task_id:
        buttons = [[Button.inline("❌ إلغاء التحميل الآن", f"cancel_{task_id}")]]
    
    try:
        await event.edit(msg, buttons=buttons)
    except:
        pass

def get_ydl_opts(uid, fmt="mp3"):
    has_aria2 = shutil.which("aria2c") is not None
    
    if fmt == "mp3":
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'downloads/{uid}.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192',},{'key': 'FFmpegMetadata',}],
        }
    else:
        opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': f'downloads/{uid}.%(ext)s',
        }
    
    common_opts = {
        'writethumbnail': False,
        'nocheckcertificate': True, 
        'quiet': True, 
        'no_warnings': True,
        'cachedir': False,
        'no_part': True,
        'extract_flat': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    if has_aria2:
        common_opts.update({
            'external_downloader': 'aria2c', 
            'external_downloader_args': [
                '--min-split-size=1M', 
                '--max-connection-per-server=16', 
                '--split=32', 
                '--max-overall-download-limit=0',
                '--connect-timeout=20'
            ]
        })
        
    opts.update(common_opts)
    return opts

async def recognize_audio_logic(file_path):
    if not ACOUSTID_AVAILABLE:
        return {"found": False, "error": "المكتبة غير مثبتة"}
    
    if not shutil.which("fpcalc"):
        logger.error("❌ أداة fpcalc غير موجودة في النظام!")
        return {"found": False, "error": "أداة fpcalc مفقودة"}

    try:
        def get_match():
            return list(acoustid.match(ACOUSTID_API_KEY, file_path))
        
        results = await asyncio.to_thread(get_match)
        
        if results:
            score, recording_id, title, artist = results[0]
            if title:
                return {
                    "found": True, 
                    "title": title, 
                    "subtitle": artist if artist else "غير معروف", 
                    "thumb": None, 
                    "full": f"{title} - {artist}" if artist else title
                }
    except Exception as e:
        logger.error(f"Error in recognition logic: {e}")
    return {"found": False}

# --- [تحديث] كليشة ترحيب سينمائية احترافية ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    user_id = event.sender_id
    user_name = event.sender.first_name
    username = f"@{event.sender.username}" if event.sender.username else "لا يوجد"
    
    logger.info(f"👤 مستخدم جديد ضغط start: {user_id} - {user_name}")

    is_verify = "verify" in event.raw_text
    
    if is_verify:
        is_subscribed = await check_subscription(user_id)
        if is_subscribed:
            if user_id in pending_verify_msgs:
                try:
                    await bot.delete_messages(event.chat_id, pending_verify_msgs[user_id])
                    del pending_verify_msgs[user_id]
                except: pass
            try: await event.delete()
            except: pass
        else:
            try: await event.delete()
            except: pass
            return await event.answer("⚠️ عزيزي، لم تشترك في كافة القنوات بعد!", alert=True)

    if str(user_id) not in db["user_stats"]:
        db["user_stats"][str(user_id)] = 0
    db["user_stats"][str(user_id)] += 1
    
    if user_id not in db["users"]:
        db["users"].append(user_id)
        save_db(db)
        if db.get("notify_join"):
            join_msg = (
                f"**🔔 إشعار دخول مستخدم جديد!**\n\n"
                f"**1- الاسم:** {user_name}\n"
                f"**2- الايدي:** `{user_id}`\n"
                f"**3- اليوزر:** {username}\n"
                f"**4- الحالة:** مستخدم جديد 🆕"
            )
            try:
                await bot.send_message(DEV_ID, join_msg, buttons=[Button.url("🔗 ملف المستخدم", f"tg://user?id={user_id}")])
            except: pass
    else:
        save_db(db)

    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        buttons = []
        for ch in db["channels"]:
            try:
                entity = await bot.get_entity(ch)
                btn_text = f"{entity.title}"
            except:
                btn_text = f"القناة"
            buttons.append([Button.url(btn_text, f"https://t.me/{ch.replace('@', '')}")])
        
        buttons.append([Button.url("🔄 تم الاشتراك", f"https://t.me/{(await bot.get_me()).username}?start=verify")])
        
        msg_text = (
            f"**⚠️ عذراً عزيزي المستخدم..**\n\n"
            f"**يجب عليك الاشتراك في قنوات البوت أولاً لتتمكن من استخدام كافة المميزات.**\n"
            f"**اشترك ثم اضغط على زر (تم الاشتراك) بالأسفل.**"
        )
        sent_msg = await bot.send_message(event.chat_id, msg_text, buttons=buttons)
        
        pending_verify_msgs[user_id] = sent_msg.id
        return

    ch_name, dev_display_name = await get_dynamic_names()
    user_mention = f"[{user_name}](tg://user?id={user_id})"
    
    welcome_text = (
        f"**🌟 مرحباً بك عزيزي {user_mention} في النسخة المطورة!**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**أنا البوت الأسرع لتحميل المحتوى والتعرف على الموسيقى:**\n"
        f"**• يوتيوب (فيديو، صوت، شورتس) 🎥**\n"
        f"**• تيك توك (بدون علامة مائية) 💎**\n"
        f"**• التعرف على الأغاني (AcoustID) 🎧**\n\n"
        f"**💡 كيف تستخدم البوت؟**\n"
        f"**1- ارسل رابط المحتوى مباشرة.**\n"
        f"**2- ارسل اسم الأغنية أو الفيديو للبحث.**\n"
        f"**3- ارسل بصمة صوتية لمعرفة اسم الأغنية.**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📟 المطور:** {DEV_USER}"
    )
    
    buttons = [
        [Button.url(f"📢 {ch_name}", f"https://t.me/{CH_USERNAME.replace('@', '')}")],
        [Button.url(f"👨‍💻 {dev_display_name}", f"https://t.me/{DEV_USER.replace('@', '')}")]
    ]
    
    try:
        await bot.send_file(event.chat_id, db["start_img"], caption=welcome_text, buttons=buttons)
    except:
        await bot.send_message(event.chat_id, welcome_text, buttons=buttons)

@bot.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if event.sender_id != DEV_ID: return
    # تنظيف حالة الإلغاء للمطور لضمان عمل اللوحة بشكل سليم
    cancelled_conversations.discard(event.sender_id)
    admin_welcome = (
        f"**🛠 لوحة تحكم الإدارة العليا | Master Control**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📟 أهلاً بك سيدي المطور في نظام التحكم الشامل.**\n"
        f"**يمكنك إدارة البوت وتعديل الإعدادات من خلال الأزرار أدناه.**"
    )
    n_join = "مفعّل ✅" if db.get("notify_join") else "معطل ❌"
    n_left = "مفعّل ✅" if db.get("notify_left") else "معطل ❌"
    buttons = [
        [Button.inline("📊 الإحصائيات الشاملة", "stats")],
        [Button.inline("📢 قسم الإذاعة العام", "bc_settings")],
        [Button.inline("⚙️ إعدادات الاشتراك", "subs_settings")],
        [Button.inline("🖼 إعدادات الصور", "img_settings")],
        [Button.inline(f"🔔 دخول: {n_join}", "toggle_join"), Button.inline(f"🚫 حظر: {n_left}", "toggle_left")],
        [Button.inline("🗑 تنظيف الملفات المؤقتة", "clean_cache")],
        [Button.inline("❌ إغلاق اللوحة", "close_admin")]
    ]
    try:
        await bot.send_file(event.chat_id, db["admin_img"], caption=admin_welcome, buttons=buttons)
    except:
        await bot.send_message(event.chat_id, admin_welcome, buttons=buttons)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    u_id = event.sender_id
    
    # --- نظام كسر المحادثة الجذري والقفل البرمجي ---
    if data == "back_to_admin" or data == "cancel_all_waiting":
        try:
            # تفعيل القفل لمنع البوت من "التقاط" أي رسالة إذاعة تم إرسالها بعد الإلغاء
            cancelled_conversations.add(u_id)
            
            # إنهاء الجلسات
            for conv in bot._conversations.get(event.chat_id, []):
                conv.cancel()
                
            # إرسال إشارة إلغاء لكافة مهام الإذاعة النشطة
            for bc_id in list(broadcast_tasks.keys()):
                broadcast_tasks[bc_id].cancel()
                del broadcast_tasks[bc_id]
            logger.info(f"✅ تم تفعيل القفل وإنهاء الجلسات للمستخدم: {u_id}")
        except Exception as e:
            logger.error(f"خطأ أثناء كسر جلسات الانتظار: {e}")
        
        await event.answer("🔄 تم إلغاء الانتظار والرجوع للوحة", alert=False)
        await admin_panel_edit(event)
        return

    # --- نظام الحذف العميق للإذاعة عند الإلغاء ---
    if data.startswith("cancel_bc_"):
        bc_task_id = data.replace("cancel_", "")
        if bc_task_id in broadcast_tasks:
            broadcast_tasks[bc_task_id].cancel()
            del broadcast_tasks[bc_task_id]
            logger.warning(f"🛑 تم تفعيل الحذف العميق للإذاعة: {bc_task_id}")
            await event.edit("⚠️ **تم إيقاف الإذاعة فوراً وحذف المهمة من النظام.**")
            return await event.answer("تم الحذف العميق", alert=True)

    if data.startswith("cancel_"):
        t_id = data.split("_")[1]
        if t_id in active_tasks:
            active_tasks[t_id].cancel()
            logger.warning(f"⚠️ تم إلغاء المهمة: {t_id}")
            await event.edit("✅ **تم إلغاء عملية التحميل بنجاح.**")
            return await event.answer("تم الإلغاء", alert=True)
        else:
            return await event.answer("⚠️ العملية مكتملة بالفعل أو غير موجودة.", alert=True)

    if data.startswith("shazam_dl_"):
        song_name = data.replace("shazam_dl_", "")
        await event.delete()
        return await start_search_engine(event, song_name)

    if data.startswith("dl_") or data.startswith("tk_"):
        if "_search" in data:
            if u_id in search_results:
                curr = search_results[u_id]["current"]
                res = search_results[u_id]["results"][curr]
                url = res["url"]
                mode = "mp3" if "mp3" in data else "mp4"
                await event.delete()
                task_id = str(event.id)
                task = asyncio.create_task(process_youtube_download(event, url, task_id, mode))
                active_tasks[task_id] = task
                return
        
        parts = data.split("_")
        mode = parts[1] 
        
        reply_msg = await event.get_message()
        if not reply_msg: return await event.answer("❌ خطأ في البيانات.", alert=True)
        
        # --- استخراج الرابط ---
        url = None
        url_match = re.search(r'(https?://[^\s]+)', reply_msg.text or "")
        if url_match:
            url = url_match.group(1)
        
        if not url and reply_msg.reply_to_msg_id:
            orig_msg = await reply_msg.get_reply_message()
            if orig_msg and orig_msg.text:
                url_match = re.search(r'(https?://[^\s]+)', orig_msg.text)
                if url_match:
                    url = url_match.group(1)
        
        if not url and reply_msg.buttons:
            for row in reply_msg.buttons:
                for btn in row:
                    if btn.url:
                        url = btn.url
                        break

        if not url: return await event.answer("❌ الرابط مفقود في نص الرسالة.", alert=True)
        
        orig_id = None
        if reply_msg.reply_to_msg_id:
            orig_id = reply_msg.reply_to_msg_id

        await event.delete() 
        task_id = str(event.id)
        task = asyncio.create_task(process_youtube_download(event, url, task_id, mode, orig_id))
        active_tasks[task_id] = task
        return

    # --- معالجة أزرار تصفح البحث ---
    if data.startswith("search_next") or data.startswith("search_prev"):
        if u_id not in search_results:
            return await event.answer("⚠️ انتهت جلسة البحث، ابحث من جديد.", alert=True)
        
        if data == "search_next":
            if search_results[u_id]["current"] < len(search_results[u_id]["results"]) - 1:
                search_results[u_id]["current"] += 1
            else:
                return await event.answer("هذه هي النتيجة الأخيرة.", alert=True)
        else:
            if search_results[u_id]["current"] > 0:
                search_results[u_id]["current"] -= 1
            else:
                return await event.answer("هذه هي النتيجة الأولى.", alert=True)
        
        await update_search_ui(event)
        return

    if event.sender_id != DEV_ID: return

    if data == "stats":
        await event.answer()
        files_count = len(glob.glob("downloads/*"))
        total_uses = sum(db["user_stats"].values())
        top_user = max(db["user_stats"], key=db["user_stats"].get) if db["user_stats"] else "لا يوجد"
        
        stats_text = (
            f"**📊 إحصائيات النظام الشاملة:**\n"
            f"**━━━━━━━━━━━━━━━━━━**\n"
            f"**👥 الأعضاء:** `{len(db['users'])}` مستخدم\n"
            f"**🔄 العمليات المنفذة:** `{total_uses}`\n"
            f"**📁 كاش الملفات:** `{files_count}` ملف مؤقت\n"
            f"**🏆 المستخدم الأنشط:** `{top_user}`\n"
            f"**🚀 المحرك النشط:** `Uvloop & Aria2c`\n"
            f"**━━━━━━━━━━━━━━━━━━**"
        )
        try: await admin_panel_edit(event, stats_text, buttons=[Button.inline("🔙 رجوع للوحة", "back_to_admin")])
        except: pass

    elif data == "toggle_join":
        db["notify_join"] = not db.get("notify_join", True)
        save_db(db)
        await event.answer()
        await admin_panel_edit(event)

    elif data == "toggle_left":
        db["notify_left"] = not db.get("notify_left", True)
        save_db(db)
        await event.answer()
        await admin_panel_edit(event)

    elif data == "subs_settings":
        await event.answer()
        channels_info = await get_all_channels_names()
        buttons = [[Button.inline("➕ إضافة قناة جديدة", "add_ch")], [Button.inline("🗑 حذف كافة القنوات", "del_ch")], [Button.inline("🔙 رجوع", "back_to_admin")]]
        txt = (
            f"**📢 إدارة قنوات الاشتراك الإجباري:**\n"
            f"**━━━━━━━━━━━━━━━━━━**\n"
            f"**القنوات المرتبطة حالياً:**\n{channels_info}"
        )
        try: await admin_panel_edit(event, txt, buttons=buttons)
        except: pass

    elif data == "img_settings":
        await event.answer()
        buttons = [[Button.inline("🖼 صورة الترحيب", "set_start_img"), Button.inline("🖼 صورة التحكم", "set_admin_img")],[Button.inline("🖼 صورة اختيار الصيغ", "set_format_img")],[Button.inline("🔙 رجوع", "back_to_admin")]]
        txt = (
            f"**🖼 إعدادات واجهات الصور الخاصة بالبوت:**\n"
            f"**⚙️ اختر القسم الذي تود تغيير صورته الافتراضية:**"
        )
        try: await admin_panel_edit(event, txt, buttons=buttons)
        except: pass

    elif data in ["set_start_img", "set_admin_img", "set_format_img"]:
        if data == "set_start_img": target, key = "ترحيب", "start_img"
        elif data == "set_admin_img": target, key = "لوحة التحكم", "admin_img"
        else: target, key = "اختيار الصيغ", "format_img"
        await event.answer()
        async with bot.conversation(event.chat_id, timeout=60) as conv:
            try:
                ask_msg = await conv.send_message(
                    f"**🔄 ارسل الآن صورة {target} الجديدة (كـ رابط أو ملف صورة):**",
                    buttons=[Button.inline("🔙 إلغاء والرجوع للوحة", "back_to_admin")]
                )
                msg = await conv.get_response()
                if not msg.text or msg.text != "/start": 
                    if msg.photo:
                        file_path = await bot.download_media(msg.photo, "downloads/")
                        db[key] = file_path
                        save_db(db)
                        await conv.send_message(f"✅ تم تحديث صورة {target} بنجاح.")
                    elif msg.text and msg.text.startswith("http"):
                        db[key] = msg.text
                        save_db(db)
                        await conv.send_message(f"✅ تم تحديث رابط صورة {target} بنجاح.")
                await admin_panel(event)
            except Exception:
                await admin_panel(event)
            finally:
                await conv.cancel_all()

    elif data == "add_ch":
        await event.answer()
        async with bot.conversation(event.chat_id, timeout=60) as conv:
            try:
                ask_msg = await conv.send_message(
                    "**➕ ارسل معرف القناة الآن (مثال: @lb2_c):**",
                    buttons=[Button.inline("🔙 إلغاء والرجوع للوحة", "back_to_admin")]
                )
                msg = await conv.get_response()
                if msg.text and msg.text.startswith("@"):
                    db["channels"].append(msg.text)
                    save_db(db)
                    await conv.send_message("✅ تمت إضافة القناة بنجاح.")
                await admin_panel(event)
            except Exception:
                await admin_panel(event)
            finally:
                await conv.cancel_all()

    elif data == "del_ch":
        await event.answer()
        db["channels"] = [CH_USERNAME]
        save_db(db)
        try: await admin_panel_edit(event, "**📢 تم تصفير كافة القنوات والعودة للقناة الأساسية.**", buttons=[Button.inline("🔙 رجوع", "subs_settings")])
        except: pass

    elif data == "bc_settings":
        await event.answer()
        cancelled_conversations.discard(u_id)
        buttons = [
            [Button.inline("👤 إذاعة خاص (Users)", "bc_users"), Button.inline("📺 إذاعة قنوات (Channels)", "bc_channels")],
            [Button.inline("🔙 رجوع للوحة التحكم", "back_to_admin")]
        ]
        txt = (
            f"**📣 نظام التبليغ والإذاعة الذكي | Broadcast**\n"
            f"**━━━━━━━━━━━━━━━━━━**\n"
            f"**• يدعم (النصوص، الصور، الفيديوهات، والملفات).**\n"
            f"**• يتضمن نظام حماية ضد التعليق وإمكانية الإلغاء.**\n\n"
            f"**⚙️ اختر الفئة المستهدفة للتبليغ:**"
        )
        try: await admin_panel_edit(event, txt, buttons=buttons)
        except: pass

    elif data == "bc_users" or data == "bc_channels":
        await event.answer()
        cancelled_conversations.discard(u_id)
        target_mode = "bc_users" if data == "bc_users" else "bc_channels"
        target_label = "المستخدمين" if data == "bc_users" else "القنوات"
        await event.delete()
        async with bot.conversation(event.chat_id, timeout=300) as conv:
            try:
                ask_msg = await conv.send_message(
                    f"**✏️ ارسل الآن محتوى الإذاعة الموجه لـ {target_label}:**", 
                    buttons=[Button.inline("🔙 إلغاء والرجوع للوحة", "cancel_all_waiting")]
                )
                msg = await conv.get_response()
                
                if u_id in cancelled_conversations:
                    cancelled_conversations.discard(u_id)
                    return 

                bc_task_id = f"bc_{int(time.time())}"
                status_bc = await bot.send_message(
                    event.chat_id,
                    f"⏳ **جاري النشر...**\n🚀 المهمة: `{bc_task_id}`",
                    buttons=[[Button.inline("❌ إلغاء وحذف عميق", f"cancel_bc_{bc_task_id}")]]
                )
                
                async def run_broadcast(task_key):
                    count = 0
                    recipients = db["users"] if target_mode == "bc_users" else db["channels"]
                    for r in recipients:
                        if task_key not in broadcast_tasks:
                            break
                        try:
                            await bot.send_message(r, msg)
                            count += 1
                            if count % 15 == 0:
                                await status_bc.edit(f"⏳ جاري النشر: ({count}/{len(recipients)})\n🚀 المهمة: `{task_key}`", buttons=[[Button.inline("❌ إلغاء وحذف عميق", f"cancel_bc_{task_key}")]])
                            await asyncio.sleep(0.05)
                        except asyncio.CancelledError:
                            break
                        except: continue
                    
                    if task_key in broadcast_tasks:
                        await status_bc.edit(f"✅ اكتملت الإذاعة لـ: {count} وجهة.", buttons=[Button.inline("🔙 رجوع للوحة", "back_to_admin")])
                        del broadcast_tasks[task_key]

                bc_task = asyncio.create_task(run_broadcast(bc_task_id))
                broadcast_tasks[bc_task_id] = bc_task
            except Exception:
                await admin_panel(event)
            finally:
                await conv.cancel_all()

    elif data == "clean_cache":
        await event.answer()
        files = glob.glob("downloads/*")
        for f in files: 
            try: os.remove(f)
            except: pass
        try: await admin_panel_edit(event, "**✅ تم تنظيف كافة الملفات المؤقتة بنجاح.**", buttons=[Button.inline("🔙 رجوع للوحة", "back_to_admin")])
        except: pass

    elif data == "close_admin":
        await event.answer()
        await event.delete()

async def admin_panel_edit(event, text=None, buttons=None):
    admin_welcome = text or (
        f"**🛠 لوحة تحكم الإدارة العليا | Master Control**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📟 أهلاً بك سيدي المطور في نظام التحكم الشامل.**"
    )
    if not buttons:
        n_join = "مفعّل ✅" if db.get("notify_join") else "معطل ❌"
        n_left = "مفعّل ✅" if db.get("notify_left") else "معطل ❌"
        buttons = [
            [Button.inline("📊 الإحصائيات الشاملة", "stats")],
            [Button.inline("📢 قسم الإذاعة العام", "bc_settings")],
            [Button.inline("⚙️ إعدادات الاشتراك", "subs_settings")],
            [Button.inline("🖼 إعدادات الصور", "img_settings")],
            [Button.inline(f"🔔 دخول: {n_join}", "toggle_join"), Button.inline(f"🚫 حظر: {n_left}", "toggle_left")],
            [Button.inline("🗑 تنظيف الملفات المؤقتة", "clean_cache")],
            [Button.inline("❌ إغلاق اللوحة", "close_admin")]
        ]
    try:
        await event.delete()
        await bot.send_file(event.chat_id, db["admin_img"], caption=admin_welcome, buttons=buttons)
    except:
        try: await bot.send_message(event.chat_id, admin_welcome, buttons=buttons)
        except: pass

# --- [تحديث] رسالة فحص وتحميل احترافية ---
async def process_youtube_download(event, url, task_id, mode="mp3", original_msg_id=None):
    try:
        async with download_semaphore:
            is_tiktok = "tiktok.com" in str(url)
            display_type = "تيك توك" if is_tiktok else ("فيديو" if mode=="mp4" else "صوت")
            
            status_msg = await bot.send_message(
                event.chat_id, 
                f"⚡️ **جاري فحص الرابط ومعالجة {display_type}...**\n"
                f"🛰 **السرعة:** `عالية جداً`\n"
                f"⏳ **انتظر ثوانٍ معدودة...**",
                buttons=[[Button.inline("❌ إلغاء العملية", f"cancel_{task_id}")]]
            )
            
            if not os.path.exists('downloads'): os.makedirs('downloads', exist_ok=True)
            ydl_opts = get_ydl_opts(task_id, mode)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(lambda: ydl.extract_info(url, download=True))
                title = info.get('title', 'محتوى جديد')
                performer = info.get('uploader') or "Hyper Developer"
                ext = info.get('ext', 'mp3' if mode == 'mp3' else 'mp4')
                file_path = f"downloads/{task_id}.{ext}"
                
                if not os.path.exists(file_path):
                    found = glob.glob(f"downloads/{task_id}.*")
                    for f in found:
                        if not f.endswith('.jpg') and not f.endswith('.aria2'): 
                            file_path = f; break

                thumbnail_path = f"downloads/thumb_{task_id}.jpg"
                thumb_url = info.get('thumbnail')
                if thumb_url:
                    try:
                        res = requests.get(thumb_url, timeout=5)
                        with open(thumbnail_path, 'wb') as f: f.write(res.content)
                    except: thumbnail_path = None
                
                duration = int(info.get('duration', 0))
                start_upload_time = time.time()
                
                source_btn_label = "🌐 TikTok" if is_tiktok else "🌐 YouTube"
                
                await status_msg.edit(f"✅ **اكتمل التحميل بنجاح!**\n🚀 **جاري البدء في الرفع السحابي...**")
                
                if mode == "mp3":
                    await bot.send_file(
                        event.chat_id, file_path,
                        thumb=thumbnail_path if thumbnail_path and os.path.exists(thumbnail_path) else None,
                        buttons=[[Button.url(source_btn_label, url)]], 
                        attributes=[DocumentAttributeAudio(duration=duration, title=title, performer=performer)],
                        progress_callback=lambda c, t: progress_bar(c, t, status_msg, start_upload_time, "رفع", task_id)
                    )
                else:
                    caption = (
                        f"**🎬 تم التحميل بنجاح!**\n"
                        f"**━━━━━━━━━━━━━━━━━━**\n"
                        f"**📝 العنوان:** {title}\n"
                        f"**👤 بواسطة:** {performer}\n"
                        f"**⏱ المدة:** {duration} ثانية\n"
                        f"**━━━━━━━━━━━━━━━━━━**\n"
                        f"**📟 المطور:** {DEV_USER}"
                    )
                    await bot.send_file(
                        event.chat_id, file_path,
                        thumb=thumbnail_path if thumbnail_path and os.path.exists(thumbnail_path) else None,
                        caption=caption,
                        buttons=[[Button.url(source_btn_label, url)]],
                        supports_streaming=True,
                        attributes=[DocumentAttributeVideo(duration=duration, w=info.get('width', 0), h=info.get('height', 0), supports_streaming=True)],
                        progress_callback=lambda c, t: progress_bar(c, t, status_msg, start_upload_time, "رفع", task_id)
                    )
                
                try:
                    await status_msg.delete()
                    if original_msg_id: await bot.delete_messages(event.chat_id, original_msg_id)
                except: pass
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
    finally:
        if task_id in active_tasks: del active_tasks[task_id]
        for f in glob.glob(f"downloads/*{task_id}*"):
            try: os.remove(f)
            except: pass

# --- [ترتيب معدل] معالجة الروابط أولاً ثم البحث ---

@bot.on(events.NewMessage(pattern=r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'))
async def handle_youtube_link(event):
    if not await check_subscription(event.sender_id): return
    url = event.text
    wait_msg = await event.reply("🔍 **جاري تحليل الرابط...**")
    rec_data = {"found": False}
    try:
        ydl_opts = {'format': 'bestaudio/best', 'outtmpl': f'downloads/rec_{event.id}.%(ext)s', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            f_path = ydl.prepare_filename(info)
            rec_data = await recognize_audio_logic(f_path)
            if os.path.exists(f_path): os.remove(f_path)
    except: pass
    
    format_text = (
        f"**🎥 تم التعرف على الرابط بنجاح!**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📥 يرجى اختيار صيغة التحميل المفضلة:**\n"
    )
    buttons = [[Button.inline("🎵 تحميل صوت (MP3)", "dl_mp3_vid"), Button.inline("🎥 تحميل فيديو (MP4)", "dl_mp4_vid")]]
    if rec_data["found"]:
        format_text += f"**🎧 الأغنية المكتشفة:** `{rec_data['full']}`\n"
        buttons.insert(0, [Button.inline(f"⬇️ تحميل الأغنية الأصلية (MP3)", f"shazam_dl_{rec_data['full']}")])
    
    format_text += f"**━━━━━━━━━━━━━━━━━━**\n**📟 المطور:** {DEV_USER}"
    buttons.append([Button.inline("❌ إلغاء العملية", "close_admin")])
    
    await wait_msg.delete()
    await bot.send_file(event.chat_id, db["format_img"], caption=format_text, buttons=buttons, reply_to=event.id)

@bot.on(events.NewMessage(pattern=r'(https?://)?(www\.|vm\.|vt\.)?tiktok\.com/.+'))
async def handle_tiktok_link(event):
    if not await check_subscription(event.sender_id): return
    url = event.text
    wait_msg = await event.reply("🔍 **جاري معالجة فيديو تيك توك...**")
    rec_data = {"found": False}
    try:
        ydl_opts = {'format': 'bestaudio/best', 'outtmpl': f'downloads/rec_{event.id}.%(ext)s', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            f_path = ydl.prepare_filename(info)
            rec_data = await recognize_audio_logic(f_path)
            if os.path.exists(f_path): os.remove(f_path)
    except: pass
    
    format_text = (
        f"**💎 تم التعرف على رابط تيك توك!**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📥 اختر كيف تريد تحميل المحتوى:**\n"
    )
    buttons = [[Button.inline("🎥 فيديو (بدون علامة)", "tk_mp4_tk"), Button.inline("🎵 صوت فقط (MP3)", "tk_mp3_tk")]]
    if rec_data["found"]:
        format_text += f"**🎧 الأغنية المكتشفة:** `{rec_data['full']}`\n"
        buttons.insert(0, [Button.inline(f"⬇️ تحميل الأغنية الأصلية (MP3)", f"shazam_dl_{rec_data['full']}")])
    
    format_text += f"**━━━━━━━━━━━━━━━━━━**\n**📟 المطور:** {DEV_USER}"
    buttons.append([Button.inline("❌ إلغاء العملية", "close_admin")])
    
    await wait_msg.delete()
    await bot.send_file(event.chat_id, db["format_img"], caption=format_text, buttons=buttons, reply_to=event.id)

# --- [تعديل فلتر البحث] لضمان عدم التقاط الروابط ---
@bot.on(events.NewMessage(func=lambda e: e.text and not e.text.startswith('/') and not e.text.startswith('http') and not '://' in e.text and not e.text.startswith('تحميل') and not e.text.startswith('تح')))
async def auto_search_handler(event):
    if event.chat_id in bot._conversations: return
    query = event.text
    await start_search_engine(event, query)

@bot.on(events.NewMessage(pattern=r'^(تحميل|تح|@tore)\s+(.+)$'))
async def handle_search_command(event):
    query = event.pattern_match.group(2)
    await start_search_engine(event, query)

async def start_search_engine(event, query):
    user_id = event.sender_id
    if not await check_subscription(user_id): return
    search_msg = await event.reply(f"🔍 **جاري البحث في الأرشيف عن: ({query}) ...**")
    try:
        ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_all = await asyncio.to_thread(lambda: ydl.extract_info(f"ytsearch10:{query}", download=False))
            results = []
            for entry in info_all['entries']:
                results.append({"title": entry['title'], "url": entry['webpage_url'], "duration": entry.get('duration', 0), "uploader": entry.get('uploader', 'Unknown')})
            if not results: return await search_msg.edit("❌ لم يتم العثور على نتائج تطابق بحثك.")
            search_results[user_id] = {"results": results, "current": 0, "query": query}
            await search_msg.delete()
            await send_search_ui(event)
    except Exception as e:
        logger.error(f"Search Error: {e}")
        await search_msg.edit(f"❌ حدث خطأ غير متوقع أثناء البحث.")

async def send_search_ui(event):
    user_id = event.sender_id
    data = search_results[user_id]
    curr = data["results"][data["current"]]
    total = len(data["results"])
    caption = (
        f"**🎯 نتائج البحث لـ: ({data['query']})**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📝 العنوان:** {curr['title']}\n"
        f"**👤 القناة:** {curr['uploader']}\n"
        f"**🔢 النتيجة:** {data['current'] + 1} من {total}\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**⚡️ اختر صيغة التحميل للبدء فوراً:**"
    )
    buttons = [
        [Button.inline("🎵 صوت (MP3)", "dl_mp3_search"), Button.inline("🎥 فيديو (MP4)", "dl_mp4_search")],
        [Button.inline("⬅️ السابق", "search_prev"), Button.inline("➡️ التالي", "search_next")],
        [Button.url("🌐 مشاهدة الرابط", curr['url'])]
    ]
    await bot.send_file(event.chat_id, db["format_img"], caption=caption, buttons=buttons)

async def update_search_ui(event):
    user_id = event.sender_id
    data = search_results[user_id]
    curr = data["results"][data["current"]]
    total = len(data["results"])
    caption = (
        f"**🎯 نتائج البحث لـ: ({data['query']})**\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**📝 العنوان:** {curr['title']}\n"
        f"**👤 القناة:** {curr['uploader']}\n"
        f"**🔢 النتيجة:** {data['current'] + 1} من {total}\n"
        f"**━━━━━━━━━━━━━━━━━━**\n"
        f"**⚡️ اختر صيغة التحميل للبدء فوراً:**"
    )
    buttons = [
        [Button.inline("🎵 صوت (MP3)", "dl_mp3_search"), Button.inline("🎥 فيديو (MP4)", "dl_mp4_search")],
        [Button.inline("⬅️ السابق", "search_prev"), Button.inline("➡️ التالي", "search_next")],
        [Button.url("🌐 مشاهدة الرابط", curr['url'])]
    ]
    try: await event.edit(caption, buttons=buttons)
    except: pass

@bot.on(events.NewMessage(func=lambda e: e.voice or e.audio))
async def shazam_recognize(event):
    if not await check_subscription(event.sender_id): return
    wait_msg = await event.reply("🔍 **جاري التعرف على البصمة الصوتية...**")
    try:
        path = await event.download_media("downloads/shazam_temp")
        rec_data = await recognize_audio_logic(path)
        if not rec_data["found"]: return await wait_msg.edit("❌ **عذراً، لم أستطع التعرف على هذه الأغنية من البصمة.**")
        shazam_text = f"**🎧 تم التعرف على الأغنية بنجاح!**\n**━━━━━━━━━━━━━━━━━━**\n**🎵 العنوان:** `{rec_data['title']}`\n**👤 الفنان:** `{rec_data['subtitle']}`"
        buttons = [[Button.inline("⬇️ تحميل الأغنية كاملة (MP3)", f"shazam_dl_{rec_data['full']}")], [Button.inline("❌ إغلاق", "close_admin")]]
        await wait_msg.delete()
        await bot.send_message(event.chat_id, shazam_text, buttons=buttons, reply_to=event.id)
    except: pass
    finally:
        if 'path' in locals() and os.path.exists(path): os.remove(path)

# --- نظام البقاء حياً (Anti-Idle) لمنع إغلاق البوت في تيرمكس ---
async def keep_alive():
    """وظيفة تعمل في الخلفية لمنع خمول البوت وتسريع الاستجابة"""
    while True:
        try:
            # تحديث بسيط لقاعدة البيانات أو مجرد تسجيل نشاط لمنع النوم
            logger.debug("⚡️ نظام Anti-Idle: البوت في حالة تأهب قصوى...")
            # محاكاة اتصال داخلي للحفاظ على استمرارية الـ Event Loop
            await bot.get_me()
        except:
            pass
        await asyncio.sleep(600) # العمل كل 10 دقائق

async def main():
    if not os.path.exists('downloads'): os.makedirs('downloads', exist_ok=True)
    logger.info("✅ جاري تشغيل البوت المطور بكامل التحديثات (تيرمكس) ...")
    
    # تشغيل نظام البقاء حياً كمهمة منفصلة
    asyncio.create_task(keep_alive())
    
    while True:
        try:
            # إعدادات بدء التشغيل مع نظام الاسترداد التلقائي
            await bot.start(bot_token=BOT_TOKEN)
            logger.success("🚀 البوت الآن في وضع الاستعداد القصوى!")
            await bot.run_until_disconnected()
        except Exception as e:
            logger.error(f"⚠️ حدث خطأ في الاتصال، إعادة المحاولة بعد 5 ثوانٍ: {e}")
            await asyncio.sleep(5)

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # تشغيل المحرك الرئيسي
    loop.run_until_complete(main())
