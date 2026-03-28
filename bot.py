import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# إعداد السجلات (Logging) لمراقبة أداء البوت في الترمكس
logging.basicConfig(level=logging.INFO)

# --- إعدادات البوت الأساسية ---
API_ID = 8456056018  # معرف الأدمن الخاص بك
API_HASH = "544459a0701b32741254945b08daebfe" 
BOT_TOKEN = "8180650384:AAEMk7xiqf5uXaOUw0DXdYIsjko_bk4P_6M"

# قنوات المصدر الخاصة بك
CHANNEL_LINK = "https://t.me/Tl2_2"
SOURCE_CHANNEL = "@lb2_c"

app = Client(
    "Hyper_Downloader_Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# مجلد التحميل المؤقت
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- خيارات yt-dlp المتكاملة (بدون اختصار) ---
ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'cookiefile': 'cookies.txt',  # السطر المسؤول عن تخطي الحماية باستخدام الكوكيز
    'external_downloader': 'aria2c',  # استخدام aria2c للتحميل الصاروخي
    'external_downloader_args': [
        '-x', '16', 
        '-s', '16', 
        '-k', '1M',
        '--max-connection-per-server=16',
        '--min-split-size=1M'
    ],
    'quiet': False,
    'no_warnings': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'addreferers': True,
}

# --- أوامر البوت ---

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("قناة المطور ⚡", url=CHANNEL_LINK)],
        [InlineKeyboardButton("سورس البوت 🛡️", url=f"https://t.me/{SOURCE_CHANNEL[1:]}")]
    ])
    await message.reply_text(
        f"**أهلاً بك يا {message.from_user.first_name} في بوت V6 PRO ULTRA ⚡**\n\n"
        "أرسل لي رابط يوتيوب (فيديو أو شورتس) وسأقوم بتحويله إلى MP3 فوراً.\n\n"
        "**تنبيه:** تم تفعيل نظام الكوكيز لتجنب الحظر.",
        reply_markup=keyboard
    )

@app.on_message(filters.regex(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$"))
async def handle_youtube_link(client, message: Message):
    url = message.text
    status_msg = await message.reply_text("🔎 **جاري فحص الرابط ومعالجة البيانات...**")

    try:
        # تشغيل عملية التحميل في خيط منفصل (Thread) لمنع توقف البوت
        loop = asyncio.get_event_loop()
        await status_msg.edit_text("📥 **بدء التحميل باستخدام aria2c...**")
        
        info = await loop.run_in_executor(None, lambda: download_process(url))
        
        file_path = info['file_path']
        title = info['title']
        duration = info.get('duration', 0)
        performer = "Hyper V6 PRO"

        await status_msg.edit_text("📤 **جاري رفع الملف الصوتي، يرجى الانتظار...**")

        # إرسال الملف إلى المستخدم
        await message.reply_audio(
            audio=file_path,
            caption=f"🎵 **تم التحميل بواسطة بوت Hyper**\n\n📌 **العنوان:** {title}\n📡 **المصدر:** {SOURCE_CHANNEL}",
            title=title,
            performer=performer,
            duration=duration
        )

        # تنظيف المساحة (حذف الملف بعد الرفع)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        await status_msg.delete()

    except Exception as e:
        error_text = f"❌ **فشل التحميل!**\n\nالسبب:\n`{str(e)}`"
        await status_msg.edit_text(error_text)
        # طباعة الخطأ في تيرمكس للمراقبة
        print(f"Error: {e}")

def download_process(url):
    """دالة التحميل والمعالجة"""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        # تحديد المسار النهائي للملف بعد تحويله لـ MP3
        original_file = ydl.prepare_filename(info_dict)
        final_mp3 = os.path.splitext(original_file)[0] + ".mp3"
        
        return {
            'file_path': final_mp3,
            'title': info_dict.get('title', 'Unknown'),
            'duration': info_dict.get('duration', 0)
        }

# --- تشغيل البوت ---
if __name__ == "__main__":
    print("---------------------------------------")
    print("🚀 البوت V6 PRO ULTRA يعمل الآن على تيرمكس!")
    print(f"👤 المطور: {API_ID}")
    print("---------------------------------------")
    app.run()
