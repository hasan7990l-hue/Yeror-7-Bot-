from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# معلوماتك اللي دزيتها
API_ID = 27485469
API_HASH = "544459a0701b32741254945b08daebfe"
BOT_TOKEN = "8386513995:AAGW7m_uFICHtW292fMiwtFOhNmKN9hRT1w"
OWNER_ID = 8456056018
DEV_CHANNEL = "lb2_c"

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# كود تجميلي للمكتبات
libs_list = {
    "عامة": "pip install requests pandas numpy matplotlib Flask django opencv-python pillow",
    "تداول": "pip install TA-Lib pandas_ta MetaTrader5 deriv-api binary-api",
    "تليجرام": "pip install pyrogram tgcrypto telebot python-telegram-bot",
    "ذكاء اصطناعي": "pip install openai torch torchvision tensorflow gTTS",
    "ترمكس": "pkg update && pkg upgrade -y && pkg install python git nodejs -y"
}

@app.on_message(filters.command("start"))
async def start(client, message):
    text = (
        f"أهلاً بك يا {message.from_user.mention} في بوت المكتبات 🚀\n\n"
        "هذا البوت يوفر لك كل اختصارات تثبيت المكتبات البرمجية بضغطة واحدة.\n\n"
        "• مطور البوت: [Hassan](tg://user?id=8456056018)\n"
        f"• قناة المطور: @{DEV_CHANNEL}"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("المكتبات العامة 📦", callback_data="libs_عامة")],
        [InlineKeyboardButton("مكتبات التداول 📉", callback_data="libs_تداول")],
        [InlineKeyboardButton("مكتبات التيليجرام 🤖", callback_data="libs_تليجرام")],
        [InlineKeyboardButton("مكتبات الذكاء الاصطناعي 🧠", callback_data="libs_ذكاء اصطناعي")],
        [InlineKeyboardButton("أوامر الترمكس 💻", callback_data="libs_ترمكس")],
        [InlineKeyboardButton("قناة المطور 📣", url=f"https://t.me/{DEV_CHANNEL}")]
    ])
    await message.reply_text(text, reply_markup=buttons)

@app.on_callback_query()
async def callback(client, callback_query):
    data = callback_query.data
    if data.startswith("libs_"):
        category = data.split("_")[1]
        install_cmd = libs_list[category]
        
        response = (
            f"✅ **مكتبات فئة: {category}**\n\n"
            f"انسخ الكود أدناه وثبته:\n\n"
            f"`{install_cmd}`"
        )
        await callback_query.message.edit_text(response, parse_mode="markdown", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع 🔙", callback_data="back")]]))

    elif data == "back":
        await start(client, callback_query.message)

print("البوت شغال الآن على منصة Railway...")
app.run()
