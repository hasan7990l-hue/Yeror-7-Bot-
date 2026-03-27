import io, logging, asyncio, sys, os, base64
import google.generativeai as genai
from telethon import TelegramClient, events

# ضبط تشفير اللغة العربية
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ==========================================
# بيانات الاعتماد (EROR-7 Projects)
# ==========================================
API_ID = 27485469
API_HASH = '544459a0701b32741254945b08daebfe'
BOT_TOKEN = '8217717390:AAGsekYq5_wvyC23I48UobKnHQK3-SkiH6o'
GEMINI_API_KEY = "AIzaSyDkm0AKk4sECKdhzAOEpLXELQNML41XcZ4"

# إعداد ذكاء Gemini الاصطناعي
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- الرسالة الترحيبية ---
START_TEXT = (
    "🛡️ **نظام EROR-7 TRADING AI جاهز!**\n\n"
    "أهلاً بك.. أنا بوت ذكاء اصطناعي مطور بواسطة Gemini. 🇮🇶\n\n"
    "📈 **أرسل صورة شارت:** للتحليل الفني.\n"
    "💬 **سولف وياي:** بأي موضوع وسأجيبك بلهجة عراقية.\n\n"
    "👨‍💻 **المطور:** @Eror_7"
)

# ==========================================
# وظائف الذكاء الاصطناعي (Gemini Cloud)
# ==========================================

async def gemini_chat(prompt):
    """الدردشة باستخدام Gemini"""
    try:
        full_prompt = f"أنت مساعد ذكي اسمك EROR-7، جاوب المستخدم بلهجة عراقية قحة ومختصرة: {prompt}"
        response = model.generate_content(full_prompt)
        return response.text if response.text else "والله يا ذهب ما عرفت شأجاوبك! 😂"
    except Exception as e:
        return f"⚠️ عيوني اكو مشكلة بالربط: {str(e)}"

async def gemini_vision(image_data):
    """تحليل الصور باستخدام Gemini"""
    try:
        prompt = "حلل هذا الشارت الخاص بخيارات التداول (Binary Options). وضح الاتجاه (Trend) والدعم والمقاومة. اجعل الإجابة مختصرة وباللغة العربية."
        response = model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': image_data}])
        return f"🚀 **تحليل EROR-7 الذكي:**\n\n{response.text}"
    except Exception as e:
        return "❌ فشل التحليل، حاول مرة ثانية."

# ==========================================
# تشغيل البوت والفعاليات
# ==========================================
client = TelegramClient('eror7_session', API_ID, API_HASH)

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond(START_TEXT)

@client.on(events.NewMessage)
async def handle_all(event):
    if event.photo:
        loading = await event.respond("🔍 **جاري فحص الشارت... انتظر ثواني...**")
        photo_bytes = await event.download_media(file=bytes)
        res = await gemini_vision(photo_bytes)
        await loading.edit(res)
        
    elif event.is_private and event.text and not event.text.startswith('/'):
        loading = await event.respond("🌀 **جاري التفكير...**")
        res = await gemini_chat(event.text)
        await loading.edit(res)

async def main():
    print("-----------------------------------------")
    print("⚡ EROR-7 SYSTEM IS RUNNING ON GEMINI ⚡")
    print("-----------------------------------------")
    await client.start(bot_token=BOT_TOKEN)
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
