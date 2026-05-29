import telebot
from googlesearch import search
import yt_dlp
from telebot import types
import os
from flask import Flask
from threading import Thread
import time
import random
import shutil 

# البيانات الخاصة بك التي تم دمجها في الكود مع التوكن الجديد
ToKen = '8277082493:AAEATsIymOchgqsI3QdGwLKD3NQ4xCrMH7s'  
bot = telebot.TeleBot(ToKen)

DEVELOPER_ID = 8456056018
API_ID = 27485469
API_HASH = "544459a0701b32741254945b08daebfe"
DEVELOPER_USER = "@Eror_7"
SOURCE_CHANNEL = "@lb2_c"

# تحديد المسار المطلق والكامل لملف الكوكيز لضمان العثور عليه في بيئة Hugging Face السحابية أو Replit
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_PATH = os.path.join(BASE_DIR, 'cookies.txt')

# تخزين مؤقت لحالات التحميل وروابط المستخدمين
user_download_requests = {}

# --- دالة مخصصة لخيارات yt-dlp المستقرة ---
def get_ydl_options(output_template):
    # البحث التلقائي والدقيق عن مسار ffmpeg بعد تثبيته عبر Nix في Replit
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        ffmpeg_dir = os.path.dirname(ffmpeg_path)
    else:
        # مسارات افتراضية بديلة في حال لم يعثر عليه shutil في المسار المباشر
        if os.path.exists('/home/runner/.nix-profile/bin/ffmpeg'):
            ffmpeg_dir = '/home/runner/.nix-profile/bin'
        elif os.path.exists('/run/current-system/sw/bin/ffmpeg'):
            ffmpeg_dir = '/run/current-system/sw/bin'
        else:
            ffmpeg_dir = '.' # المسار الحالي كخيار أخير

    return {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': output_template,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'ffmpeg_location': ffmpeg_dir, # تمرير المسار الصحيح المكتشف ديناميكياً
    }

# ----- إعداد الويب الصغير لمنع إيقاف البوت -----
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "البوت يعمل بنجاح وبدون توقف! 🚀"

def run_web_server():
    # تم تثبيت المنفذ هنا إلى 7860 ليتطابق مع نظام الاستضافة
    flask_app.run(host='0.0.0.0', port=7860, use_reloader=False)

def keep_alive():
    t = Thread(target=run_web_server)
    t.daemon = True
    t.start()
# ----------------------------------------------

# دالة لتحديث الرسائل المتحركة أثناء التحميل
def animate_loading(chat_id, message_id, base_text, stop_event):
    frames = ["⏳", "📥", "⚡", "✨"]
    i = 0
    while not stop_event.is_set():
        try:
            frame = frames[i % len(frames)]
            bot.edit_message_text(f"{frame} *{base_text}...*", chat_id, message_id, parse_mode='Markdown')
            i += 1
            time.sleep(1.5)
        except Exception:
            break

# دالة تنزيل الصوت من الرابط المباشر مع تفادي أخطاء دمج الغلاف والـ Metadata لضمان المعالجة المستقرة
def download_youtube_audio(url, user_id):
    unique_id = f"{user_id}_{int(time.time())}_{random.randint(100, 999)}"
    output_template = os.path.join(BASE_DIR, f'audio_{unique_id}.%(ext)s')
    final_mp3_path = os.path.join(BASE_DIR, f'audio_{unique_id}.mp3')
    
    ydl_ops = get_ydl_options(output_template)
    ydl_ops.update({
        'writethumbnail': False, 
        'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}
        ],
    })
    
    if os.path.exists(COOKIES_PATH):
        ydl_ops['cookiefile'] = COOKIES_PATH
        
    with yt_dlp.YoutubeDL(ydl_ops) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'Audio')
        
        if os.path.exists(final_mp3_path):
            return final_mp3_path, title
        else:
            for file in os.listdir(BASE_DIR):
                if file.startswith(f'audio_{unique_id}') and file.endswith('.mp3'):
                    return os.path.join(BASE_DIR, file), title
            raise FileNotFoundError("تعذر العثور على ملف الـ MP3 الذي تم إنشاؤه.")

# دالة تنزيل الفيديو من الرابط المباشر مع تجنب مشاكل الأسماء العربية والرموز المعقدة
def download_youtube_video(url, user_id):
    unique_id = f"{user_id}_{int(time.time())}_{random.randint(100, 999)}"
    output_template = os.path.join(BASE_DIR, f'video_{unique_id}.%(ext)s')
    final_mp4_path = os.path.join(BASE_DIR, f'video_{unique_id}.mp4')
    
    ydl_ops = get_ydl_options(output_template)
    ydl_ops.update({'format': 'best[ext=mp4]/best'})
    
    if os.path.exists(COOKIES_PATH):
        ydl_ops['cookiefile'] = COOKIES_PATH
        
    with yt_dlp.YoutubeDL(ydl_ops) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'Video')
        
        if os.path.exists(final_mp4_path):
            return final_mp4_path, title
        else:
            for file in os.listdir(BASE_DIR):
                if file.startswith(f'video_{unique_id}') and file.endswith('.mp4'):
                    return os.path.join(BASE_DIR, file), title
            raise FileNotFoundError("تعذر العثور على ملف الـ MP4 الذي تم إنشاؤه.")

# دالة البحث في جوجل
def google_search(query):
    links = []
    for result in search(query, num_results=4, lang='ar'):
        links.append(result)
    return links

# دالة البحث في جوجل بلاي
def google_play_search(query):
    links = []
    for result in search(query + " site:play.google.com", num_results=4, lang='ar'):
        links.append(result)
    return links

# دالة البحث في يوتيوب
def youtube_search(query):
    links = []
    ydl_opts = {'format': 'best', 'quiet': True, 'user_agent': 'Mozilla/5.0'}
    
    if os.path.exists(COOKIES_PATH):
        ydl_opts['cookiefile'] = COOKIES_PATH
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(f"ytsearch:{query}", download=False)
        for entry in result['entries']:
            links.append(entry['url'])
    return links

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    item_google = types.InlineKeyboardButton("- بحث في جوجل", callback_data="google_search")
    item_youtube = types.InlineKeyboardButton("- بحث في اليوتيوب", callback_data="youtube_search")
    item_google_play = types.InlineKeyboardButton("- بحث في جوجل بلي", callback_data="google_play_search")
    markup.add(item_google, item_youtube)
    markup.add(item_google_play)
    item_channel = types.InlineKeyboardButton("- قناة السورس 🧑🏻‍💻", url=f"https://t.me/{SOURCE_CHANNEL.replace('@','')}")
    markup.add(item_channel)
    bot.reply_to(message,'*- مرحباً بك عزيزي 🙋🏻‍♂️\n\n• يمكنك من خلال هذا البوت البحث عن ما تريده باستخدام الاقسام في الاسفل 🔥\nكل ما عليك هو اختيار القسم الذي تريد البحث فية وأرسل الكلمة للبحث عنها وسيتم إرسال النتائج اليك ✅ .\n\n• أو يمكنك إرسال رابط يوتيوب مباشر ليتم تحميله فوراً! 📥*', reply_markup=markup, parse_mode='Markdown')

# لوحة تحكم المطور
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id == DEVELOPER_ID:
        markup = types.InlineKeyboardMarkup()
        item_channel = types.InlineKeyboardButton("قناة السورس 📊", url=f"https://t.me/{SOURCE_CHANNEL.replace('@','')}")
        markup.add(item_channel)
        
        admin_text = (
            f"⚙️ *لوحة تحكم المطور الرئيسية*\n\n"
            f"• أهلاً بك يا مطورنا المتألق {DEVELOPER_USER}\n"
            f"• معرف المطور: `{DEVELOPER_ID}`\n"
            f"• حالة الاتصال بالسيرفر: ممتازة وعاملة 🚀\n"
            f"• حالة الـ Web Server: متصل على منفذ 7860 ✅"
        )
        bot.reply_to(message, admin_text, reply_markup=markup, parse_mode='Markdown')
    else:
        bot.reply_to(message, "⚠️ هذا الأمر مخصص للمطور فقط!")

# ميزة استقبال الروابط المباشرة وعرض قائمة اختيار الصيغة (صوت / فيديو)
@bot.message_handler(regexp=r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/\S+")
def handle_youtube_link(message):
    url = message.text
    user_id = message.from_user.id
    user_download_requests[user_id] = url
    
    markup = types.InlineKeyboardMarkup()
    btn_audio = types.InlineKeyboardButton("🎵 تحميل كملف صوتي", callback_data="download_as_audio")
    btn_video = types.InlineKeyboardButton("🎥 تحميل كفيديو", callback_data="download_as_video")
    btn_channel = types.InlineKeyboardButton("🧑🏻‍💻 قناة السورس", url=f"https://t.me/{SOURCE_CHANNEL.replace('@','')}")
    
    markup.add(btn_audio, btn_video)
    markup.add(btn_channel)
    
    bot.reply_to(message, "⚙️ *اختر الصيغة التي تود تحميل الملف بها:*", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    user_id = call.from_user.id
    
    if call.data == "google_search":
        bot.send_message(call.message.chat.id, '*- أرسل كلمة البحث في Google:*', parse_mode='Markdown')
        bot.register_next_step_handler(call.message, search_in_google)
        
    elif call.data == "youtube_search":
        bot.send_message(call.message.chat.id, '*- أرسل كلمة البحث في YouTube:*', parse_mode='Markdown')
        bot.register_next_step_handler(call.message, search_in_youtube)
        
    elif call.data == "google_play_search":
        bot.send_message(call.message.chat.id, '*- أرسل كلمة البحث في Google Play:*', parse_mode='Markdown')
        bot.register_next_step_handler(call.message, search_in_google_play)
        
    elif call.data == "download_as_audio":
        if user_id in user_download_requests:
            url = user_download_requests[user_id]
            del user_download_requests[user_id]
            
            wait_msg = bot.send_message(call.message.chat.id, "⏳ *جاري بدء عملية معالجة الصوت...*", parse_mode='Markdown')
            
            from threading import Event
            stop_anim = Event()
            anim_thread = Thread(target=animate_loading, args=(call.message.chat.id, wait_msg.message_id, "جاري تحميل ومعالجة الملف الصوتي", stop_anim))
            anim_thread.start()
            
            try:
                file_path, title = download_youtube_audio(url, user_id)
                stop_anim.set()
                anim_thread.join()
                
                bot.send_chat_action(call.message.chat.id, 'upload_document')
                with open(file_path, 'rb') as audio:
                    bot.send_audio(call.message.chat.id, audio, caption=f"🎵 {title}\n\nDeveloper: {DEVELOPER_USER}\nSource: {SOURCE_CHANNEL}")
                
                bot.delete_message(call.message.chat.id, wait_msg.message_id)
                if os.path.exists(file_path): os.remove(file_path)
                    
            except Exception as e:
                stop_anim.set()
                bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء تحميل الصوت: {e}\n\n💡 تأكد من تحديث yt-dlp واستخدام وكيل (User-Agent) صحيح.")
        else:
            bot.send_message(call.message.chat.id, "⚠️ انتهت صلاحية هذا الطلب، الرجاء إرسال الرابط مجدداً.")
            
    elif call.data == "download_as_video":
        if user_id in user_download_requests:
            url = user_download_requests[user_id]
            del user_download_requests[user_id]
            
            wait_msg = bot.send_message(call.message.chat.id, "⏳ *جاري بدء عملية معالجة الفيديو...*", parse_mode='Markdown')
            
            from threading import Event
            stop_anim = Event()
            anim_thread = Thread(target=animate_loading, args=(call.message.chat.id, wait_msg.message_id, "جاري تحميل ومعالجة مقطع الفيديو الآن", stop_anim))
            anim_thread.start()
            
            try:
                file_path, title = download_youtube_video(url, user_id)
                stop_anim.set()
                anim_thread.join()
                
                bot.send_chat_action(call.message.chat.id, 'upload_video')
                with open(file_path, 'rb') as video:
                    bot.send_video(call.message.chat.id, video, caption=f"🎥 {title}\n\nDeveloper: {DEVELOPER_USER}\nSource: {SOURCE_CHANNEL}")
                
                bot.delete_message(call.message.chat.id, wait_msg.message_id)
                if os.path.exists(file_path): os.remove(file_path)
                    
            except Exception as e:
                stop_anim.set()
                bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء تحميل الفيديو: {e}")
        else:
            bot.send_message(call.message.chat.id, "⚠️ انتهت صلاحية هذا الطلب، الرجاء إرسال الرابط مجدداً.")

def search_in_google(message):
    user_input = message.text
    search_msg = bot.send_message(message.chat.id, '*- جاري البحث... 🔍*', parse_mode='Markdown')
    search_results = google_search(user_input)
    bot.delete_message(message.chat.id, search_msg.message_id)
    for link in search_results: bot.send_message(message.chat.id, link)

def search_in_google_play(message):
    user_input = message.text
    search_msg = bot.send_message(message.chat.id, '*- جاري البحث... 🔍*', parse_mode='Markdown')
    search_results = google_play_search(user_input)
    bot.delete_message(message.chat.id, search_msg.message_id)
    for link in search_results: bot.send_message(message.chat.id, link)

def search_in_youtube(message):
    user_input = message.text
    search_msg = bot.send_message(message.chat.id, '*- جاري البحث... 🔍*', parse_mode='Markdown')
    search_results = youtube_search(user_input)
    bot.delete_message(message.chat.id, search_msg.message_id)
    for link in search_results: bot.send_message(message.chat.id, link)

def run_bot_polling():
    while True:
        try: bot.polling(none_stop=True, timeout=90, long_polling_timeout=90)
        except Exception: time.sleep(5)

def start_search_bot():
    keep_alive()
    t_bot = Thread(target=run_bot_polling)
    t_bot.daemon = True
    t_bot.start()

start_search_bot()

if __name__ == "__main__":
    while True: time.sleep(3600)
