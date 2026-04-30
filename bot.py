import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# --- إعدادات البوت الكاملة ---
# ملاحظة: تم تحديث التوكن بناءً على رسالتك الأخيرة
API_ID = 27485469  
API_HASH = "544459a0701b32741254945b08daebfe" 
BOT_TOKEN = "8386513995:AAHBL3QdbshzTo-jLNq_jQQ7yV66ycSv8Rs" # التوكن الجديد
OWNER_ID = 8456056018 # الآيدي الخاص بك

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- لوحة الأزرار الرئيسية ---
main_buttons = InlineKeyboardMarkup([
    [InlineKeyboardButton("📦 المكتبات العامة", callback_data="general_libs")],
    [InlineKeyboardButton("📉 مكتبات التداول", callback_data="trading_libs")],
    [InlineKeyboardButton("🤖 مكتبات التيليجرام", callback_data="tg_libs")],
    [InlineKeyboardButton("🧠 مكتبات الذكاء الاصطناعي", callback_data="ai_libs")],
    [InlineKeyboardButton("💻 أوامر الترمكس", callback_data="termux_cmds")],
    [InlineKeyboardButton("📢 قناة المطور", url="https://t.me/lb2_c")]
])

# زر العودة للقائمة الرئيسية
back_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ عودة للقائمة الرئيسية", callback_data="main_menu")]
])

# --- معالج أمر البداية /start ---
@app.on_message(filters.command("start"))
async def start(client, message):
    user_name = message.from_user.first_name
    user_id = message.from_user.id
    welcome_text = (
        f"أهلاً بك يا {user_name} في بوت المكتبات 🚀\n\n"
        "هذا البوت يوفر لك كل اختصارات تثبيت المكتبات البرمجية بضغطة واحدة.\n\n"
        f"• ايدي حسابك: `{user_id}`\n"
        f"• ايدي المطور المثبت: `{OWNER_ID}`\n"
        "• مطور البوت: Hassan\n"
        "• قناة المطور: @lb2_c"
    )
    
    # تم تغيير reply_photo إلى reply_text لإزالة الاعتماد على الروابط
    await message.reply_text(
        text=welcome_text,
        reply_markup=main_buttons
    )

# --- معالج ضغطات الأزرار (Callback Query Handler) ---
@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data

    if data == "main_menu":
        # تم استخدام edit_message_text بدلاً من edit_message_caption لأن الرسالة أصبحت نصية
        await callback_query.edit_message_text(
            text="أهلاً بك في القائمة الرئيسية للمكتبات 🚀\nاختر القسم الذي تريده من الأسفل:",
            reply_markup=main_buttons
        )

    elif data == "general_libs":
        text = (
            "📦 **المكتبات العامة الأساسية:**\n\n"
            "لمس الكود للنسخ:\n"
            "`pip install requests`\n"
            "`pip install wheel`\n"
            "`pip install pandas`\n"
            "`pip install numpy`\n"
            "`pip install colorama`"
        )
        await callback_query.edit_message_text(text=text, reply_markup=back_markup)

    elif data == "trading_libs":
        text = (
            "📉 **مكتبات التداول والخوارزميات:**\n\n"
            "`pip install TA-Lib`\n"
            "`pip install ccxt`\n"
            "`pip install MetaTrader5`\n"
            "`pip install yfinance`"
        )
        await callback_query.edit_message_text(text=text, reply_markup=back_markup)

    elif data == "tg_libs":
        text = (
            "🤖 **مكتبات تطوير بوتات التيليجرام:**\n\n"
            "`pip install pyrogram`\n"
            "`pip install tgcrypto`\n"
            "`pip install telebot`\n"
            "`pip install python-telegram-bot`"
        )
        await callback_query.edit_message_text(text=text, reply_markup=back_markup)

    elif data == "ai_libs":
        text = (
            "🧠 **مكتبات الذكاء الاصطناعي:**\n\n"
            "`pip install openai`\n"
            "`pip install tensorflow`\n"
            "`pip install torch`\n"
            "`pip install scikit-learn`"
        )
        await callback_query.edit_message_text(text=text, reply_markup=back_markup)

    elif data == "termux_cmds":
        text = (
            "💻 **أوامر تهيئة الترمكس الأساسية:**\n\n"
            "`pkg update && pkg upgrade`\n"
            "`pkg install python`\n"
            "`pkg install git`\n"
            "`pkg install wget`"
        )
        await callback_query.edit_message_text(text=text, reply_markup=back_markup)

# --- بدء تشغيل البوت ---
if __name__ == "__main__":
    print("البوت يعمل الآن بنجاح على سيرفر Railway...")
    app.run()
