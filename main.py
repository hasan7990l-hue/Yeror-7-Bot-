import os
import sys
import asyncio
import json
import telethon
import random
from telethon import TelegramClient, events, Button
from yt_dlp import YoutubeDL
from aiohttp import web  # استيراد مكتبة الويب لمنع توقف البوت

# --- البيانات الخاصة بك (مدمجة بالكامل بدون تغيير) ---
BOT_TOKEN = "8386513995:AAE1EzgXIUwVz4YYs31pp3iwAyixQjerUxA"
API_ID = 27485469
API_HASH = "544459a0701b32741254945b08daebfe"
DEVELOPER_USER = "@Eror_7"
CHANNEL_USER = "@lb2_c"
OWNER_ID = 8456056018

# تحويل يوزر القناة والمطور إلى روابط مباشرة للاستخدام في الأزرار
CHANNEL_URL = f"https://t.me/{CHANNEL_USER.replace('@', '')}"
DEVELOPER_URL = f"https://t.me/{DEVELOPER_USER.replace('@', '')}"

# قائمة لحفظ معرفات الفيديوهات المنشورة منعاً للتكرار أثناء تشغيل السكربت
POSTED_VIDEOS = set()

# --- إعدادات مكتبة yt-dlp المحدثة بأعلى درجات الحماية لتخطي حظر SSL وتجنب طلب الكوكيز ---
ydl_opts = {
    'format': 'best[ext=mp4]/best',  # جلب أفضل جودة جاهزة مدمجة مباشرة لتفادي استهلاك الـ RAM والمعالج في الدمج
    'outtmpl': 'downloads/%(id)s.%(ext)s',  # الحفظ باستخدام الآيدي لتجنب مشاكل الأسماء العربية
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': False,
    # إعدادات كسر جدار الحماية وتخطي الـ SSL المتقدمة وتطوير سرعة التحميل:
    'nocheckcertificate': True,
    'check_certificate': False,
    'prefer_insecure': True,  # إجبار الأداة على التخطي في حال فشل بروتوقول الحماية الرقمي
    'concurrent_fragments': 5, # زيادة سرعة تحميل أجزاء الفيديو بالتوازي
    'socket_timeout': 15, # منع تعليق الاتصال بالخوادم البطيئة
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'referer': 'https://www.tiktok.com/',
    'extractor_args': {
        'tiktok': {
            'web_id': '7351000000000000000',
            'app_id': '1180'
        }, 
        'youtube': {'skip': ['dash', 'hls']}
    },
    'http_headers': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ar-IQ;q=0.8,ar;q=0.7',
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }
}

# فحص ذكي: إذا كان ملف الكوكيز موجوداً في السيرفر يتم دمج مساره تلقائياً، وإن لم يوجد يستمر بدون مشاكل
if os.path.exists('cookies.txt'):
    ydl_opts['cookiefile'] = 'cookies.txt'

# التأكد من وجود مجلد التحميلات عند إقلاع السكربت
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# إنشاء جلسة البوت والاتصال بتيليجرام
print("[+] جاري تشغيل البوت والاتصال بسيرفرات تيليجرام...")
bot = TelegramClient('tiktok_downloader_bot', API_ID, API_HASH)

# متغيرات عالمية لحفظ الأسماء المجلوبة تلقائياً من السيرفر
bot_name = "بوت التنزيل"
developer_name = "المطور"
channel_name = "قناة المطور"

async def fetch_telegram_data():
    """
    جلب معلومات البوت، المطور، والقناة تلقائياً من سيرفرات تيليجرام عند تشغيل السكربت.
    """
    global bot_name, developer_name, channel_name
    try:
        # 1. جلب اسم البوت تلقائياً
        me = await bot.get_me()
        bot_name = me.first_name
        print(f"[✔] تم جلب اسم البوت تلقائياً: {bot_name}")
        
        # 2. جلب اسم المطور تلقائياً من ملفه الشخصي باستخدام الآيدي
        dev_user = await bot.get_entity(OWNER_ID)
        if dev_user.first_name:
            developer_name = dev_user.first_name
        print(f"[✔] تم جلب اسم المطور تلقائياً من ملفه الشخصي: {developer_name}")
        
        # 3. جلب اسم القناة تلقائياً باستخدام معرف القناة
        ch_entity = await bot.get_entity(CHANNEL_USER)
        if ch_entity.title:
            channel_name = ch_entity.title
        print(f"[✔] تم جلب اسم القناة تلقائياً: {channel_name}")
        
    except Exception as e:
        print(f"[⚠️] تحذير أثناء جلب البيانات تلقائياً (سيتم استخدام الأسماء الافتراضية): {e}")


# =========================================================================
# --- ملف وقاعدة بيانات حفظ الإعدادات والمستخدمين (تحديث لوحة التحكم) ---
# =========================================================================
DATA_FILE = "bot_settings.json"

def load_settings():
    defaults = {
        "users": {},          # "user_id": {"lang": "ar", "starts": 1, "username": "", "name": ""}
        "blocked_users": [],  # قائمة المستخدمين الذين حظروا البوت (تم كشفهم عبر الخطأ)
        "fsub_channels": [],  # أقصى حد 4 قنوات: [{"username": "@channel", "title": "القناة 1"}]
        "welcome_media": None,# قاموس يحتوي على تفاصيل الميديا للواجهة الرئيسية لضمان التوافق مع JSON
        "admin_media": None,  # قاموس يحتوي على تفاصيل الميديا للوحة التحكم لضمان التوافق مع JSON
        "fsub_media": None,   # قاموس يحتوي على تفاصيل الميديا لكليشة الاشتراك الإجباري لضمان التوافق مع JSON
        "total_blocks_count": 0 # عدد مرات رصد حظر البوت
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return defaults
    return defaults

def save_settings(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# تحميل الإعدادات عند الإقلاع
bot_data = load_settings()

# حالة انتظار الإدخال للمطور عبر الأزرار
ADMIN_STATES = {}

# نصوص اللغات المتعددة (تم تحديث اللغة العربية لتكون فخمة وبدون رموز تعبيرية)
LANGUAGES = {
    "ar": {
        "welcome": "مرحبا بك في رحاب منصة {bot_name}\n\nيرجى ارسال رابط مقطع تيك توك ليتم معالجته وتوفيره لك بجودته الاصلية الكاملة وبشكل مرئي مباشر دون اية حقوق او علامات مائية مرافقة للمحتوى",
        "lang_btn": "🌐 تغيير اللغة / Change Language",
        "fsub_msg": "إشعار إداري\n\nعذرا يا {name} لم يتم العثور على القيود الخاصة بحسابك في قاعدة بيانات العضوية الرسمية للمنصة\n\nيتطلب تفعيل كامل صلاحيات البوت انضمام حسابك إلى القنوات الموضحة أدناه أولا ثم الضغط على خيار تأكيد الانضمام المتاح",
        "fsub_btn": "الانضمام للمنصة الرسمية",
        "check_btn": "تأكيد والتحقق من الانضمام"
    },
    "en": {
        "welcome": "Welcome to {bot_name} platform.\n\nPlease send a TikTok video link to process and deliver it in its original full quality directly without watermark.",
        "lang_btn": "🌐 Change Language / تغيير اللغة",
        "fsub_msg": "Administrative Notice\n\nSorry {name}, your account record was not found in the official platform membership database.\n\nActivating full bot capabilities requires joining the channels listed below first, then pressing the verification button.",
        "fsub_btn": "Join Official Channel",
        "check_btn": "Confirm and Verify Membership"
    }
}


# =========================================================================
# --- دوال المساعد والتحقق من الاشتراك الإجباري ---
# =========================================================================
async def check_force_subscribe(user_id):
    """التحقق من اشتراك العضو في القنوات المحددة (حتى 4 قنوات) مع معالجة قيود الاستدعاء"""
    if user_id == OWNER_ID:
        return True, []
    
    not_joined = []
    for ch in bot_data.get("fsub_channels", []):
        try:
            # محاولة جلب الكيان الخاص بالقناة أولاً لضمان صحة المعرف
            channel_entity = await bot.get_entity(ch['username'])
            
            # محاولة الفحص بالطلب المباشر القياسي
            participant = await bot(telethon.functions.channels.GetParticipantRequest(
                channel=channel_entity,
                participant=user_id
            ))
        except telethon.errors.rpcerrorlist.UserNotParticipantError:
            # إذا أرجع تليجرام صراحة أن العضو ليس مشتركاً
            not_joined.append(ch)
        except Exception:
            # في حال حدوث خطأ صلاحيات أو قيود، يتم فحص حالة العضوية عبر قائمة المشاركين كخيار بديل ذكي
            try:
                joined = False
                async for user in bot.iter_participants(channel_entity, filter=telethon.tl.types.ChannelParticipantsSearch(q=str(user_id))):
                    if user.id == user_id:
                        joined = True
                        break
                if not joined:
                    # إذا اكتمل البحث ولم يتم العثور على الأيدي في قائمة المشتركين
                    not_joined.append(ch)
            except Exception as inner_error:
                print(f"[⚠️] فشل الفحص البديل للقناة {ch['username']}: {inner_error}")
                # إذا فشلت كل الحلول نعتبرها غير مشترك احتياطاً لضمان عدم تخطي النظام
                not_joined.append(ch)
    
    if not_joined:
        return False, not_joined
    return True, []


# =========================================================================
# --- معالجة الأوامر والرسائل (الأحداث) ---
# =========================================================================

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """
    الرد على أمر /start وإرسال رسالة الترحيب مع الأزرار الديناميكية المجلوبة تلقائياً ونظام اللغات والإشعارات.
    """
    user_id = event.sender_id
    user_str = str(user_id)
    chat = await event.get_chat()
    
    username = f"@{chat.username}" if getattr(chat, 'username', None) else "لا يوجد"
    first_name = chat.first_name if getattr(chat, 'first_name', None) else "مستخدم تيليجرام"
    
    # تحديث إحصائيات المستخدم ونظام إشعارات الدخول - فحص صارم لمنع تكرار الإشعار للمطور
    is_new = False
    if user_str not in bot_data["users"]:
        is_new = True
        bot_data["users"][user_str] = {
            "lang": "ar",
            "starts": 1,
            "username": username,
            "name": first_name
        }
    else:
        bot_data["users"][user_str]["starts"] += 1
        bot_data["users"][user_str]["username"] = username
        bot_data["users"][user_str]["name"] = first_name
    
    # إزالة العضو من قائمة الحظر في حال عاد وشغل البوت
    if user_id in bot_data["blocked_users"]:
        bot_data["blocked_users"].remove(user_id)
        
    save_settings(bot_data)
    
    # منع التكرار: يتم إرسال إشعار الدخول للمطور فقط وحصرياً إذا كان العضو جديد كلياً في قاعدة البيانات
    if is_new:
        log_text = (
            "🔔 **إشعار دخول عضو جديد إلى البوت:**\n\n"
            f"👤 **الاسم:** {first_name}\n"
            f"🆔 **الأيدي:** `{user_id}`\n"
            f"🔗 **اليوزر:** {username}\n"
            f"📈 **عدد مرات الدخول:** {bot_data['users'][user_str]['starts']}"
        )
        user_btn = [[Button.url("🔗 حساب العضو", f"tg://user?id={user_id}")]]
        try:
            await bot.send_message(OWNER_ID, log_text, buttons=user_btn)
        except Exception as e:
            print(f"تعذر إرسال إشعار الدخول للمطور: {e}")

    # التحقق من الاشتراك الإجباري أولاً
    is_joined, channels_to_join = await check_force_subscribe(user_id)
    if not is_joined:
        user_lang = bot_data["users"][user_str]["lang"]
        fsub_buttons = []
        for ch in channels_to_join:
            ch_url = f"https://t.me/{ch['username'].replace('@', '')}"
            fsub_buttons.append([Button.url(f"{ch['title']}", ch_url)])
        
        # إضافة زر التحقق بعد قنوات الاشتراك الإجباري مباشرة لحث المستخدم على التفعيل
        fsub_buttons.append([Button.inline(LANGUAGES[user_lang]["check_btn"], b"verify_user_subscription")])
        
        # نظام التحقق من وجود ميديا مخصصة لكليشة الاشتراك الإجباري
        fsub_media_data = bot_data.get("fsub_media")
        if fsub_media_data:
            try:
                # إعادة تشكيل كائن الميديا الأصلي من القاموس المحفوظ لضمان الإرسال النظيف
                fsub_media = telethon.tl.types.MessageMediaDocument(
                    document=telethon.tl.types.Document(
                        id=fsub_media_data['id'],
                        access_hash=fsub_media_data['access_hash'],
                        file_reference=bytes.fromhex(fsub_media_data['file_reference']),
                        date=fsub_media_data['date'],
                        mime_type=fsub_media_data['mime_type'],
                        size=fsub_media_data['size'],
                        dc_id=fsub_media_data['dc_id'],
                        attributes=[]
                    )
                ) if fsub_media_data.get('type') == 'document' else fsub_media_data.get('url')
                await bot.send_file(event.chat_id, fsub_media, caption=LANGUAGES[user_lang]["fsub_msg"].format(name=first_name), buttons=fsub_buttons)
                return
            except Exception:
                pass
                
        await event.respond(LANGUAGES[user_lang]["fsub_msg"].format(name=first_name), buttons=fsub_buttons)
        return

    # إشعار نجاح التحقق والاشتراك الإجبارى الجديد للمطور مع الإحصائيات الكاملة للمستخدم (عند أول اشتراك صحيح بعد القنوات)
    if is_new:
        sub_log_text = (
            "📢 **إشعار تحقق واشتراك جديد بالبوت:**\n\n"
            f"👤 **اسم العضو:** {first_name}\n"
            f"🆔 **أيدي الحساب:** `{user_id}`\n"
            f"🔗 **يوزر الحساب:** {username}\n"
            f"📊 **إجمالي المشتركين الحالي:** {len(bot_data['users'])}\n"
        )
        sub_user_btn = [[Button.url("🔗 رابط الحساب", f"tg://user?id={user_id}")]]
        try:
            await bot.send_message(OWNER_ID, sub_log_text, buttons=sub_user_btn)
        except Exception as e:
            print(f"تعذر إرسال إشعار الاشتراك للمطور: {e}")

    # جلب لغة المستخدم الحالية
    user_lang = bot_data["users"][user_str]["lang"]
    welcome_text = LANGUAGES[user_lang]["welcome"].format(bot_name=bot_name)
    
    # تصميم الأزرار الشفافة باستخدام الأسماء المجلوبة تلقائياً فقط دون نصوص زائدة
    buttons = [
        [
            Button.url(developer_name, DEVELOPER_URL),
            Button.url(channel_name, CHANNEL_URL)
        ],
        [
            Button.inline(LANGUAGES[user_lang]["lang_btn"], b"change_language")
        ]
    ]
    
    # إذا كان المرسل هو المطور، يظهر له زر إضافي للدخول إلى لوحة التحكم
    if user_id == OWNER_ID:
        buttons.append([Button.inline("⚙️ لوحة تحكم المطور", b"admin_panel")])
        
    # التحقق من وجود ميديا معينة للواجهة الرئيسية
    welcome_media_data = bot_data.get("welcome_media")
    if welcome_media_data:
        try:
            welcome_media = telethon.tl.types.MessageMediaDocument(
                document=telethon.tl.types.Document(
                    id=welcome_media_data['id'],
                    access_hash=welcome_media_data['access_hash'],
                    file_reference=bytes.fromhex(welcome_media_data['file_reference']),
                    date=welcome_media_data['date'],
                    mime_type=welcome_media_data['mime_type'],
                    size=welcome_media_data['size'],
                    dc_id=welcome_media_data['dc_id'],
                    attributes=[]
                )
            ) if welcome_media_data.get('type') == 'document' else welcome_media_data.get('url')
            await bot.send_file(event.chat_id, welcome_media, caption=welcome_text, buttons=buttons)
            return
        except Exception:
            pass # في حال فشل إرسال الميديا يتم إرسالها كنص افتراضي تلقائياً
            
    await event.respond(welcome_text, buttons=buttons)


@bot.on(events.NewMessage)
async def download_handler(event):
    """
    فحص الرسائل الواردة، وتنزيل الفيديو المرئي تلقائياً وإرساله مع العنوان الكامل وزر المطور الحقيقي.
    """
    text = event.text.strip() if event.text else ""
    user_id = event.sender_id
    user_str = str(user_id)
    
    # تخطي الأوامر الخاصة بالبوت إذا كان نصاً
    if text.startswith('/'):
        return

    # معالجة مدخلات لوحة التحكم الخاصة بالمطور (نصوص وميديا)
    if user_id == OWNER_ID and user_id in ADMIN_STATES:
        state = ADMIN_STATES[user_id]
        
        # أولاً: معالجة رفع الميديا المباشرة واجهتي التحكم والترحيب والاشتراك الإجباري بشكل آمن مع الـ JSON
        if state in ["set_welcome_media", "set_admin_media", "set_fsub_media"]:
            if event.media and hasattr(event.message.media, 'document') and event.message.media.document:
                # الهندسة الآمنة: استخراج الخصائص الرقمية والنصية الثابتة من الكائن المعقد وحفظها كـ dictionary عادي متوافق مع الـ JSON
                doc = event.message.media.document
                media_id = {
                    "type": "document",
                    "id": doc.id,
                    "access_hash": doc.access_hash,
                    "file_reference": doc.file_reference.hex(),
                    "date": int(doc.date.timestamp()),
                    "mime_type": doc.mime_type,
                    "size": doc.size,
                    "dc_id": doc.dc_id
                }
                
                if state == "set_welcome_media":
                    bot_data["welcome_media"] = media_id
                    target = "الواجهة الرئيسية"
                elif state == "set_admin_media":
                    bot_data["admin_media"] = media_id
                    target = "لوحة التحكم"
                elif state == "set_fsub_media":
                    bot_data["fsub_media"] = media_id
                    target = "الاشتران الإجباري"
                    
                save_settings(bot_data)
                await event.respond(f"✔ تم بنجاح تعيين الميديا لـ **{target}** كميديا مباشرة جاهزة للعرض.", buttons=[[Button.inline("🔙 العودة للوحة التحكم", b"admin_panel")]])
                del ADMIN_STATES[user_id]
                return
            
            # معالجة إضافية وذكية للغاية في حال قام المطور بإرسال رابط نصي للميديا بدلاً من الملف المباشر
            elif text and ("http" in text or text.startswith("http")):
                media_link = {"type": "url", "url": text}
                if state == "set_welcome_media":
                    bot_data["welcome_media"] = media_link
                    target = "الواجهة الرئيسية"
                elif state == "set_admin_media":
                    bot_data["admin_media"] = media_link
                    target = "لوحة التحكم"
                elif state == "set_fsub_media":
                    bot_data["fsub_media"] = media_link
                    target = "الاشتراك الإجباري"
                    
                save_settings(bot_data)
                await event.respond(f"✔ تم بنجاح تعيين رابط الميديا لـ **{target}**.", buttons=[[Button.inline("🔙 العودة للوحة التحكم", b"admin_panel")]])
                del ADMIN_STATES[user_id]
                return
                
            else:
                await event.respond("❌ خطأ، يرجى إرسال ملف ميديا مباشر (فيديو مستند) أو رابط ميديا مباشر لضمان استقرار السيرفر!")
                del ADMIN_STATES[user_id]
                return

        # ثانياً: معالجة نصوص إدخال قنوات الاشتراك الإجباري
        if state == "add_fsub":
            if not text.startswith("@"):
                await event.respond("❌ خطأ، يجب أن يبدأ المعرف بـ @ كالمثال التالي: @lb2_c")
                del ADMIN_STATES[user_id]
                return
            try:
                ch_entity = await bot.get_entity(text)
                title = ch_entity.title
                
                if "fsub_channels" not in bot_data:
                    bot_data["fsub_channels"] = []
                    
                if len(bot_data["fsub_channels"]) >= 4:
                    await event.respond("❌ لا يمكنك إضافة أكثر من 4 قنوات اشتراك إجباري.")
                    del ADMIN_STATES[user_id]
                    return
                    
                bot_data["fsub_channels"].append({"username": text, "title": title})
                save_settings(bot_data)
                await event.respond(f"✔ تم إضافة القناة بنجاح:\n**{title}** ({text})", buttons=[[Button.inline("🔙 العودة للوحة التحكم", b"admin_panel")]])
            except Exception as e:
                await event.respond(f"❌ تعذر العثور على القناة أو أن البوت ليس مشرفاً بها.\nالخطأ: {e}", buttons=[[Button.inline("🔙 العودة للوحة التحكم", b"admin_panel")]])
            del ADMIN_STATES[user_id]
            return

    # --- تصحيح هندسي صارم لمنع التكرار التلقائي عند مطابقة النصوص الفرعية ---
    if text and (text == developer_name or text == DEVELOPER_USER or text == "المطور" or text == "مطور"):
        try:
            # جلب ميديا الملف الشخصي للمطور من سيرفرات تليجرام مباشرة
            dev_entity = await bot.get_entity(OWNER_ID)
            photos = await bot.get_profile_photos(dev_entity, limit=1)
            
            dev_info_text = (
                f"👑 **مـعـلـومـاـت مـطـور الـبـوت والـسـكـريـبـت**\n"
                f"───────────────────\n"
                f"👤 **الاسم الحقيقي:** {developer_name}\n"
                f"🆔 **الآيدي الخاص:** `{OWNER_ID}`\n"
                f"🔗 **المعرف الرسمي:** {DEVELOPER_USER}\n"
                f"📡 **قناة المطور:** {CHANNEL_USER}\n"
                f"───────────────────\n"
                f"🛠 **Developed by Engineer: Hyper**"
            )
            dev_buttons = [[Button.url(developer_name, DEVELOPER_URL)]]
            
            if photos:
                await bot.send_file(event.chat_id, photos[0], caption=dev_info_text, buttons=dev_buttons, reply_to=event.id)
            else:
                await event.respond(dev_info_text, buttons=dev_buttons, reply_to=event.id)
            return
        except Exception as e:
            print(f"خطأ أثناء جلب معلومات وصورة المطور: {e}")

    # التأكد الصارم من أن الرسالة تحتوي على رابط تيك توك فقط، وإذا لم تكن كذلك يتم تجاهلها فوراً دون إرسال رسائل خطأ
    if text and "tiktok.com" in text:
        # التحقق من الاشتراك الإجباري أولاً للمخدم قبل تفعيل التحميل
        is_joined, channels_to_join = await check_force_subscribe(user_id)
        if not is_joined:
            user_lang = bot_data.get("users", {}).get(user_str, {}).get("lang", "ar")
            chat = await event.get_chat()
            first_name = chat.first_name if getattr(chat, 'first_name', None) else "مستخدم تيليجرام"
            fsub_buttons = []
            for ch in channels_to_join:
                ch_url = f"https://t.me/{ch['username'].replace('@', '')}"
                fsub_buttons.append([Button.url(f"{ch['title']}", ch_url)])
                
            # إضافة زر التحقق بعد القنوات مباشرة لحماية تدفق العمل
            fsub_buttons.append([Button.inline(LANGUAGES[user_lang]["check_btn"], b"verify_user_subscription")])
                
            fsub_media_data = bot_data.get("fsub_media")
            if fsub_media_data:
                try:
                    fsub_media = telethon.tl.types.MessageMediaDocument(
                        document=telethon.tl.types.Document(
                            id=fsub_media_data['id'],
                            access_hash=fsub_media_data['access_hash'],
                            file_reference=bytes.fromhex(fsub_media_data['file_reference']),
                            date=fsub_media_data['date'],
                            mime_type=fsub_media_data['mime_type'],
                            size=fsub_media_data['size'],
                            dc_id=fsub_media_data['dc_id'],
                            attributes=[]
                        )
                    ) if fsub_media_data.get('type') == 'document' else fsub_media_data.get('url')
                    await bot.send_file(event.chat_id, fsub_media, caption=LANGUAGES[user_lang]["fsub_msg"].format(name=first_name), buttons=fsub_buttons)
                    return
                except Exception:
                    pass
            await event.respond(LANGUAGES[user_lang]["fsub_msg"].format(name=first_name), buttons=fsub_buttons)
            return

        # تسريع هندسي: تم حذف الفواصل الزمنية المزيفة والعداد الوهمي لبدء المعالجة والتحميل فوراً ودون أي تأخير
        status_msg = await event.respond("⏳ جاري سحب بيانات الفيديو وفك التشفير الرقمي بدون علامة مائية...")
        
        # تشغيل دالة التنزيل داخل loop منفصل لمنع تجميد البوت
        current_loop = asyncio.get_event_loop()
        file_path = None
        
        try:
            # دالة مدمجة مع نظام المحاولات الذكي لتفادي جدار حماية تيك توك وتغير استجابة الخوادم
            def download_action():
                max_retries = 3
                last_error = None
                
                for attempt in range(1, max_retries + 1):
                    try:
                        # تصحيح الخطأ البرمجي: تعديل أبعاد التوليد العشوائي لتكون متناسقة رياضياً ومنع خطأ ValueError
                        local_opts = ydl_opts.copy()
                        if attempt > 1:
                            new_web_id = f"7351{random.randint(10000000000000, 99999999999999)}"
                            local_opts['extractor_args']['tiktok']['web_id'] = new_web_id
                        
                        with YoutubeDL(local_opts) as ydl:
                            info = ydl.extract_info(text, download=True)
                            full_title = info.get('title', 'شعر بيت تيك توك')
                            filename = ydl.prepare_filename(info)
                            
                            if not os.path.exists(filename):
                                base, _ = os.path.splitext(filename)
                                filename = f"{base}.mp4"
                            return filename, full_title
                    except Exception as exc:
                        last_error = exc
                        # إذا كان الخطأ بسبب حظر الصفحة نقوم بالمحاولة مرة أخرى فوراً
                        if "Unexpected response from webpage request" in str(exc) and attempt < max_retries:
                            continue
                        else:
                            raise exc
                raise last_error

            # تشغيل عملية التنزيل واستخراج البيانات للفيديو المرئي بالخلفية
            file_path, video_title = await current_loop.run_in_executor(None, download_action)
            
            if os.path.exists(file_path):
                # نص وصف الفيديو يحتوي على العنوان الكامل فقط كما طلبت
                caption_text = f"📝 **العنوان الكامل:**\n{video_title}\n\n👨‍💻 Developed by Engineer: Hyper"
                
                # زر المطور الشفاف باسم المطور الحقيقي المجلوب تلقائياً من الحساب فقط بدون أي نصوص إضافية
                video_buttons = [
                    [
                        Button.url(developer_name, DEVELOPER_URL)
                    ]
                ]
                
                # إرسال ملف الفيديو المرئي كاملاً مع العنوان وزر المطور
                await bot.send_file(
                    event.chat_id, 
                    file_path, 
                    caption=caption_text,
                    buttons=video_buttons,
                    reply_to=event.id,
                    supports_streaming=True  # السماح للمستخدم بمشاهدة الفيديو مباشرة أثناء التحميل دون الحاجة لانتظار اكتمال تحميله بالكامل
                )
                
                # حذف رسالة الحالة بعد الإرسال
                await status_msg.delete()
                
                # حذف ملف الفيديو من الذاكرة لتوفير المساحة تلقائياً بعد الإرسال
                os.remove(file_path)
            else:
                await status_msg.edit("❌ عذراً، تعذر العثور على ملف الفيديو المرئي المنزل.")
                
        except Exception as e:
            print(f"[❌] خطأ أثناء معالجة الرابط: {e}")
            # التأكد من مسح الملف التالف إن وجد لمنع ملء الذاكرة
            if file_path and os.path.exists(file_path):
                try: os.remove(file_path)
                except: pass
            
            # --- إصلاح هندسي ذكي لرصد حظر البوت الحقيقي وتجنب تداخل أخطاء المخدمات الخارجية ---
            is_telegram_block = False
            # 1. التحقق من نوع الخطأ البرمجي التابع لتيليجرام صراحة
            if isinstance(e, (telethon.errors.rpcerrorlist.UserIsBlockedError, telethon.errors.rpcerrorlist.ChatWriteForbiddenError)):
                is_telegram_block = True
            # 2. التحقق من نصوص أخطاء التوجيه والإرسال الصادرة من مكتبة سيرفر تيليجرام فقط
            elif any(msg in str(e) for msg in ["bot was blocked", "blocked by the user", "ChatWriteForbidden"]):
                is_telegram_block = True

            if is_telegram_block:
                if user_id not in bot_data["blocked_users"]:
                    bot_data["blocked_users"].append(user_id)
                    bot_data["total_blocks_count"] += 1
                    save_settings(bot_data)
                    # إرسال إشعار حظر البوت للمطور
                    block_log = (
                        "🚨 **إشعار جديد: قام عضو بحظر البوت!**\n\n"
                        f"👤 **الاسم:** {bot_data['users'].get(user_str, {}).get('name', 'غير معروف')}\n"
                        f"🆔 **الأيدي:** `{user_id}`\n"
                        f"🔗 **اليوزر:** {bot_data['users'].get(user_str, {}).get('username', 'لا يوجد')}\n"
                        f"📉 **إجمالي عدد مرات حظر البوت المكتشفة:** {bot_data['total_blocks_count']}"
                    )
                    try:
                        await bot.send_message(OWNER_ID, block_log, buttons=[[Button.url("🔗 حساب العضو", f"tg://user?id={user_id}")]])
                    except:
                        pass
            else:
                # إذا كان الخطأ قادماً من السيرفر أو الشبكة الخاصة بـ TikTok وليس حظراً للبوت من المستخدم
                try:
                    await status_msg.edit(f"❌ حدث خطأ أثناء تنزيل الفيديو. تأكد من أن الرابط صحيح وشغال.\n\nنوع الخطأ: {str(e)[:100]}")
                except:
                    pass
    else:
        # تجاهل تام لأي نص آخر لا يحتوي على رابط تيك توك لضمان عدم حدوث أي تداخل
        return


# =========================================================================
# --- معالجة الضغط على الأزرام الشفافة (Inline Callbacks) ---
# =========================================================================

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    user_str = str(user_id)
    data = event.data

    # --- معالجة زر التحقق من الاشتراك الإجباري المضاف حديثاً ---
    if data == b"verify_user_subscription":
        is_joined, channels_to_join = await check_force_subscribe(user_id)
        if is_joined:
            await event.answer("تم تأكيد العضوية بنجاح، يمكنك استخدام الخدمة الآن", alert=True)
            await event.delete()
            # إعادة توجيه المستخدم تلقائياً للترحيب الأساسي للبوت
            user_lang = bot_data["users"].get(user_str, {}).get("lang", "ar")
            welcome_text = LANGUAGES[user_lang]["welcome"].format(bot_name=bot_name)
            buttons = [
                [Button.url(developer_name, DEVELOPER_URL), Button.url(channel_name, CHANNEL_URL)],
                [Button.inline(LANGUAGES[user_lang]["lang_btn"], b"change_language")]
            ]
            if user_id == OWNER_ID:
                buttons.append([Button.inline("⚙️ لوحة تحكم المطور", b"admin_panel")])
            
            welcome_media_data = bot_data.get("welcome_media")
            if welcome_media_data:
                try:
                    welcome_media = telethon.tl.types.MessageMediaDocument(
                        document=telethon.tl.types.Document(
                            id=welcome_media_data['id'],
                            access_hash=welcome_media_data['access_hash'],
                            file_reference=bytes.fromhex(welcome_media_data['file_reference']),
                            date=welcome_media_data['date'],
                            mime_type=welcome_media_data['mime_type'],
                            size=welcome_media_data['size'],
                            dc_id=welcome_media_data['dc_id'],
                            attributes=[]
                        )
                    ) if welcome_media_data.get('type') == 'document' else welcome_media_data.get('url')
                    await bot.send_file(event.chat_id, welcome_media, caption=welcome_text, buttons=buttons)
                    return
                except:
                    pass
            await bot.send_message(event.chat_id, welcome_text, buttons=buttons)
        else:
            await event.answer("فشل التحقق، يرجى الانضمام لكافة القنوات أولا قبل الضغط هنا", alert=True)

    # --- 1. تغيير لغة البوت للمستخدم ---
    elif data == b"change_language":
        current_lang = bot_data["users"].get(user_str, {}).get("lang", "ar")
        new_lang = "en" if current_lang == "ar" else "ar"
        
        if user_str not in bot_data["users"]:
            bot_data["users"][user_str] = {"lang": new_lang, "starts": 1, "username": "", "name": ""}
        else:
            bot_data["users"][user_str]["lang"] = new_lang
            
        save_settings(bot_data)
        await event.delete() # حذف لحذف أي وسائط سابقة منعاً للتداخل
        
        welcome_text = LANGUAGES[new_lang]["welcome"].format(bot_name=bot_name)
        buttons = [
            [
                Button.url(developer_name, DEVELOPER_URL),
                Button.url(channel_name, CHANNEL_URL)
            ],
            [Button.inline(LANGUAGES[new_lang]["lang_btn"], b"change_language")]
        ]
        if user_id == OWNER_ID:
            buttons.append([Button.inline("⚙️ لوحة تحكم المطور", b"admin_panel")])
            
        welcome_media_data = bot_data.get("welcome_media")
        if welcome_media_data:
            try:
                welcome_media = telethon.tl.types.MessageMediaDocument(
                    document=telethon.tl.types.Document(
                        id=welcome_media_data['id'],
                        access_hash=welcome_media_data['access_hash'],
                        file_reference=bytes.fromhex(welcome_media_data['file_reference']),
                        date=welcome_media_data['date'],
                        mime_type=welcome_media_data['mime_type'],
                        size=welcome_media_data['size'],
                        dc_id=welcome_media_data['dc_id'],
                        attributes=[]
                    )
                ) if welcome_media_data.get('type') == 'document' else welcome_media_data.get('url')
                await bot.send_file(event.chat_id, welcome_media, caption=welcome_text, buttons=buttons)
                await event.answer("🌐 تم تغيير اللغة بنجاح / Language updated!", alert=True)
                return
            except Exception:
                pass
        await bot.send_message(event.chat_id, welcome_text, buttons=buttons)
        await event.answer("🌐 تم تغيير اللغة بنجاح / Language updated!", alert=True)

    # --- 2. فتح لوحة التحكم (تمت إزالة الرموز التعبيرية وجعل النص فخماً ورسمياً) ---
    elif data == b"admin_panel":
        if user_id != OWNER_ID:
            await event.answer("❌ هذا الأمر خاص بمطور السكربت فقط.", alert=True)
            return
            
        # إلغاء أي حالة إدخال معلقة
        if user_id in ADMIN_STATES:
            del ADMIN_STATES[user_id]
            
        await event.delete() # حذف الرسالة السابقة كلياً لضمان إزالة الميديا
            
        admin_text = (
            f"لوحة التحكم الإدارية\n"
            f"───────────────────────\n"
            f"المنصة العامة: {bot_name}\n"
            f"المطور المسؤول: {developer_name}\n"
            f"البصمة البرمجية: Developed by Engineer: Hyper\n"
            f"───────────────────────\n"
            f"مرحبا بك في وحدة التحكم الاستراتيجية. يرجى تحديد الخيار المطلوب لإدارة البيانات الفنية وقنوات الاشتراك الإجباري والوسائط بكفاءة عالية."
        )
        
        buttons = [
            [
                Button.inline("📊 الإحصائيات والمعلومات", b"admin_stats"),
                Button.inline("📢 قنوات الاشتراك الإجباري", b"admin_fsub")
            ],
            [
                Button.inline("🖼 ميديا الواجهة الرئيسية", b"set_welcome_media_btn"),
                Button.inline("🖼 ميديا لوحة التحكم", b"set_admin_media_btn")
            ],
            [
                Button.inline("🖼 ميديا الاشتراك الإجباري", b"set_fsub_media_btn"),
                Button.inline("⚡ خروج وإغلاق اللوحة ⚡", b"close_admin")
            ]
        ]
        
        # تحقق من وجود ميديا مخصصة للوحة التحكم
        admin_media_data = bot_data.get("admin_media")
        if admin_media_data:
            try:
                admin_media = telethon.tl.types.MessageMediaDocument(
                    document=telethon.tl.types.Document(
                        id=admin_media_data['id'],
                        access_hash=admin_media_data['access_hash'],
                        file_reference=bytes.fromhex(admin_media_data['file_reference']),
                        date=admin_media_data['date'],
                        mime_type=admin_media_data['mime_type'],
                        size=admin_media_data['size'],
                        dc_id=admin_media_data['dc_id'],
                        attributes=[]
                    )
                ) if admin_media_data.get('type') == 'document' else admin_media_data.get('url')
                await bot.send_file(event.chat_id, admin_media, caption=admin_text, buttons=buttons)
                return
            except Exception:
                pass
                
        await bot.send_message(event.chat_id, admin_text, buttons=buttons)

    # --- 3. إحصائيات البوت الكاملة ---
    elif data == b"admin_stats":
        if user_id != OWNER_ID:
            return
            
        await event.delete() # حذف الرسالة والوسائط السابقة
            
        total_users = len(bot_data.get("users", {}))
        active_users = total_users - len(bot_data.get("blocked_users", []))
        total_fsub = len(bot_data.get("fsub_channels", []))
        posted_count = len(POSTED_VIDEOS)
        
        stats_text = (
            "📊 **إحصائيات ومعلومات البوت الكاملة:**\n\n"
            f"👥 **إجمالي المستخدمين المسجلين:** {total_users}\n"
            f"🟢 **المستخدمين النشطين (التقريبي):** {max(0, active_users)}\n"
            f"🚨 **المستخدمين الذين قاموا بحظر البوت:** {len(bot_data.get('blocked_users', []))}\n"
            f"🔢 **إجمالي إشعارات الحظر المستلمة:** {bot_data.get('total_blocks_count', 0)}\n"
            f"📢 **عدد قنوات الاشتراك المربوطة:** {total_fsub}/4\n"
            f"🎬 **مقاطع النشر التلقائي المنشورة حالياً:** {posted_count}"
        )
        await bot.send_message(event.chat_id, stats_text, buttons=[[Button.inline("🔙 العودة للوحة التحكم", b"admin_panel")]])

    # --- 4. إدارة قنوات الاشتراك الإجباري ---
    elif data == b"admin_fsub":
        if user_id != OWNER_ID:
            return
            
        await event.delete() # حذف الرسالة والوسائط السابقة
            
        fsub_list = bot_data.get("fsub_channels", [])
        text = "📢 **قنوات الاشتراك الإجباري المضافة حالياً (الحد الأقصى 4):**\n\n"
        
        buttons = []
        if not fsub_list:
            text += "⚠️ لا يوجد أي قنوات مضافة حالياً. البوت متاح للجميع مباشرة."
        else:
            for idx, ch in enumerate(fsub_list):
                text += f"{idx + 1}. **{ch['title']}** -> {ch['username']}\n"
                # أزرار حذف لكل قالب على حدة
                buttons.append([Button.inline(f"❌ حذف: {ch['title']}", f"conf_del_{idx}".encode('utf-8'))])
                
        # زر إضافة قناة جديدة إذا لم يتخطى الحد الأقصى
        if len(fsub_list) < 4:
            buttons.append([Button.inline("➕ إضافة قناة جديدة", b"add_fsub_channel")])
            
        buttons.append([Button.inline("🔙 العودة للوحة التحكم", b"admin_panel")])
        await bot.send_message(event.chat_id, text, buttons=buttons)

    # --- 5. طلب إضافة قناة اشتراك إجباري ---
    elif data == b"add_fsub_channel":
        if user_id != OWNER_ID:
            return
        ADMIN_STATES[user_id] = "add_fsub"
        await event.delete() # التعديل بالحذف الكامل
        await bot.send_message(
            event.chat_id,
            "📥 **قم بإرسال معرف القناة الآن.**\n\n"
            "⚠️ **ملاحظة هامة:** يجب أولاً رفع البوت مشرفاً داخل القناة بصلاحية كاملة لكي يستطيع فحص المشتركين، ثم أرسل معرف القناة هنا بشكل صحيح يبدأ بـ @ (مثال: `@lb2_c`)."
        )

    # --- 6. تأكيد حذف قناة الاشتراك الإجباري ---
    elif data.startswith(b"conf_del_"):
        if user_id != OWNER_ID:
            return
        await event.delete() # التعديل بالحذف الكامل
        ch_idx = int(data.decode('utf-8').split('_')[2])
        fsub_list = bot_data.get("fsub_channels", [])
        
        if ch_idx < len(fsub_list):
            ch = fsub_list[ch_idx]
            confirm_text = f"❓ **هل أنت متأكد تماماً من رغبتك في حذف القناة التالية من الاشتراك الإجباري؟**\n\n🏷 **اسم القناة:** {ch['title']}\n🔗 **المعرف:** {ch['username']}"
            buttons = [
                [
                    Button.inline("✔ نعم، تأكيد الحذف نهائياً", f"execute_del_{ch_idx}".encode('utf-8')),
                    Button.inline("❌ إلغاء", b"admin_fsub")
                ]
            ]
            await bot.send_message(event.chat_id, confirm_text, buttons=buttons)

    # --- 7. تنفيذ حذف القناة بعد التأكيد الصارم ---
    elif data.startswith(b"execute_del_"):
        if user_id != OWNER_ID:
            return
        ch_idx = int(data.decode('utf-8').split('_')[2])
        if "fsub_channels" in bot_data and ch_idx < len(bot_data["fsub_channels"]):
            removed = bot_data["fsub_channels"].pop(ch_idx)
            save_settings(bot_data)
            await event.answer(f"✔ تم حذف قناة {removed['title']} بنجاح.", alert=True)
        await callback_handler(events.CallbackQuery(event.query)) # إعادة توجيه لصفحة القنوات تلقائياً
        
    # --- 8. أزرار تعيين الميديا (الصور أو الفيديو) للواجهات الثلاثة ---
    elif data in [b"set_welcome_media_btn", b"set_admin_media_btn", b"set_fsub_media_btn"]:
        if user_id != OWNER_ID:
            return
        await event.delete() # التعديل بالحذف الكامل قبل الانتقال لإدخال الميديا
        if data == b"set_welcome_media_btn":
            ADMIN_STATES[user_id] = "set_welcome_media"
            await bot.send_message(event.chat_id, "📥 **يرجى إرسال الصورة أو مقطع الفيديو الآن لواجهة الترحيب الرئيسية (/start) بشكل مباشر (معرض/ألبوم) أو أرسل رابط ميديا مباشر:**\n\nسيقوم البوت بحفظ المعرف وتثبيته تلقائياً.")
        elif data == b"set_admin_media_btn":
            ADMIN_STATES[user_id] = "set_admin_media"
            await bot.send_message(event.chat_id, "📥 **يرجى إرسال الصورة أو مقطع الفيديو الآن المخصص للوحة تحكم المطور بشكل مباشر (معرض/ألبوم) أو أرسل رابط ميديا مباشر:**\n\nسيتم عرضها في الالفية عند فتح اللوحة في المرات القادمة.")
        elif data == b"set_fsub_media_btn":
            ADMIN_STATES[user_id] = "set_fsub_media"
            await bot.send_message(event.chat_id, "📥 **يرجى إرسال الصورة أو مقطع الفيديو المخصص لكليشة الاشتراك الإجباري بشكل مباشر (معرض/ألبوم) أو أرسل رابط ميديا مباشر:**\n\nسيتم عرضها تلقائياً للمستخدم غير المشترك لإجباره على الاشتراك.")

    # --- 9. إغلاق لوحة التحكم والعودة للترحيب ---
    elif data == b"close_admin":
        if user_id != OWNER_ID:
            return
        await event.delete() # حذف كامل اللوحة والوسائط
        # إرسال رسالة ترحيبية نظيفة
        user_lang = bot_data.get("users", {}).get(user_str, {}).get("lang", "ar")
        welcome_text = LANGUAGES[user_lang]["welcome"].format(bot_name=bot_name)
        buttons = [
            [Button.url(developer_name, DEVELOPER_URL), Button.url(channel_name, CHANNEL_URL)],
            [Button.inline(LANGUAGES[user_lang]["lang_btn"], b"change_language")],
            [Button.inline("⚙️ لوحة تحكم المطور", b"admin_panel")]
        ]
        welcome_media_data = bot_data.get("welcome_media")
        if welcome_media_data:
            try:
                welcome_media = telethon.tl.types.MessageMediaDocument(
                    document=telethon.tl.types.Document(
                        id=welcome_media_data['id'],
                        access_hash=welcome_media_data['access_hash'],
                        file_reference=bytes.fromhex(welcome_media_data['file_reference']),
                        date=welcome_media_data['date'],
                        mime_type=welcome_media_data['mime_type'],
                        size=welcome_media_data['size'],
                        dc_id=welcome_media_data['dc_id'],
                        attributes=[]
                    )
                ) if welcome_media_data.get('type') == 'document' else welcome_media_data.get('url')
                await bot.send_file(event.chat_id, welcome_media, caption=welcome_text, buttons=buttons)
                return
            except:
                pass
        await bot.send_message(event.chat_id, welcome_text, buttons=buttons)


# --- نظام ويب مصغر مدمج لمنع توقف السكربت (Keep Alive Web Server) ---
async def web_handle(request):
    """الرد على طلبات الويب للتأكيد على أن البوت حي ويعمل بنجاح"""
    return web.Response(text="Bot is running successfully 24/7!")

async def main():
    """
    الدالة الرئيسية الموحدة لتشغيل سيرفر الويب وجلسة البوت معاً بشكل صحيح هندسياً يتوافق مع البيئات السحابية.
    """
    # 1. بدء جلسة البوت والاتصال
    await bot.start(bot_token=BOT_TOKEN)
    await fetch_telegram_data()
    
    # ترحيب عند بدء التشغيل في الترمينال
    print("=" * 50)
    print(f"    اسم البوت: {bot_name}")
    print(f"    اسم المطور المجلوب: {developer_name}")
    print(f"    اسم القناة المجلوب: {channel_name}")
    print("    Developed by Engineer: Hyper")
    print("=" * 50)

    # 2. إعداد وتشغيل سيرفر الويب كمهمة خلفية مدمجة بالـ Loop الأساسي هندسياً
    app = web.Application()
    app.router.add_get('/', web_handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 7860))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"[🌐] تم تشغيل نظام الويب بنجاح على المنفذ المخصص: {port}")

    # 3. الحفاظ على تشغيل الـ Loop والانتظار حتى انتهاء الاتصال بالبوت
    await bot.run_until_disconnected()

# تشغيل البوت عبر دالة الـ main
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("[!] تم إيقاف البوت يدويًا.")
