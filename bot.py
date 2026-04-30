import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import UserNotParticipant

# --- إعدادات البوت الكاملة ---
API_ID = 27485469  
API_HASH = "544459a0701b32741254945b08daebfe" 
BOT_TOKEN = "8386513995:AAHBL3QdbshzTo-jLNq_jQQ7yV66ycSv8Rs" 
OWNER_ID = 8456056018 # الآيدي الخاص بك

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# متغيّر لتخزين الإعدادات برمجياً
db = {
    "images": {
        "welcome": None,
        "general": None,
        "trading": None,
        "ai": None,
        "termux": None,
        "admin": None
    },
    "texts": {
        "welcome": "أهلاً بك يا {user_name} في بوت المكتبات 🚀\n\nهذا البوت يوفر لك كل اختصارات تثبيت المكتبات البرمجية بضغطة واحدة.\n\n• ايدي حسابك: `{user_id}`\n• ايدي المطور المثبت: `{owner_id}`\n• مطور البوت: Hassan\n• قناة المطور: @lb2_c"
    },
    "fsub": [] # لتخزين معرفات القنوات (بحد أقصى 3)
}

# متغيّر لتتبع حالة الإدخال
waiting_for_input = {}

# --- دالة التحقق من الاشتراك الإجباري ---
async def check_fsub(client, message):
    if not db["fsub"]:
        return True
    
    unsubscribed = []
    for channel in db["fsub"]:
        try:
            await client.get_chat_member(channel, message.from_user.id)
        except UserNotParticipant:
            unsubscribed.append(channel)
        except Exception:
            pass # في حال كانت القناة خاصة أو البوت ليس مشرفاً

    if unsubscribed:
        keys = []
        for ch in unsubscribed:
            keys.append([InlineKeyboardButton(f"اشترك هنا: {ch}", url=f"https://t.me/{ch.replace('@','')}")])
        keys.append([InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="main_menu")])
        
        await message.reply_text(
            "⚠️ **عذراً عزيزي، يجب عليك الاشتراك في قنوات البوت لتتمكن من استخدامه!**",
            reply_markup=InlineKeyboardMarkup(keys)
        )
        return False
    return True

# --- لوحة الأزرار الرئيسية ---
main_buttons = InlineKeyboardMarkup([
    [InlineKeyboardButton("📦 **المكتبات العامة**", callback_data="general_libs")],
    [InlineKeyboardButton("📉 **مكتبات التداول**", callback_data="trading_libs")],
    [InlineKeyboardButton("🤖 **مكتبات التيليجرام**", callback_data="tg_libs")],
    [InlineKeyboardButton("🧠 **مكتبات الذكاء الاصطناعي**", callback_data="ai_libs")],
    [InlineKeyboardButton("💻 **أوامر الترمكس**", callback_data="termux_cmds")],
    [InlineKeyboardButton("📢 **قناة المطور**", url="https://t.me/lb2_c")]
])

# لوحة تحكم المطور المحدثة
def get_admin_buttons():
    buttons = [
        [InlineKeyboardButton("📝 **تعيين نص الترحيب**", callback_data="set_txt_welcome")],
        [InlineKeyboardButton("🖼️ **صورة الترحيب**", callback_data="set_img_welcome")],
        [InlineKeyboardButton("🖼️ **صورة المكتبات العامة**", callback_data="set_img_general")],
        [InlineKeyboardButton("🖼️ **صورة مكتبات التداول**", callback_data="set_img_trading")],
        [InlineKeyboardButton("🖼️ **صورة الذكاء الاصطناعي**", callback_data="set_img_ai")],
        [InlineKeyboardButton("🖼️ **صورة أوامر تيرمكس**", callback_data="set_img_termux")],
        [InlineKeyboardButton("🖼️ **صورة لوحة التحكم**", callback_data="set_img_admin")],
        [InlineKeyboardButton("🔗 **إدارة الاشتراك الإجباري**", callback_data="manage_fsub")],
        [InlineKeyboardButton("⬅️ **عودة للقائمة الرئيسية**", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)

# زر العودة للقائمة الرئيسية
back_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ **عودة للقائمة الرئيسية**", callback_data="main_menu")]
])

# --- معالج أمر البداية /start ---
@app.on_message(filters.command("start"))
async def start(client, message):
    if not await check_fsub(client, message):
        return
        
    user_name = message.from_user.first_name
    user_id = message.from_user.id
    welcome_text = db["texts"]["welcome"].format(user_name=user_name, user_id=user_id, owner_id=OWNER_ID)
    
    if db["images"]["welcome"]:
        await message.reply_photo(photo=db["images"]["welcome"], caption=welcome_text, reply_markup=main_buttons)
    else:
        await message.reply_text(text=welcome_text, reply_markup=main_buttons)

# --- أمر المطور /admin ---
@app.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    admin_text = "🛠️ **أهلاً بك في لوحة تحكم المطور.**\n\nيمكنك من هنا تعيين وتحديث صور ونصوص أقسام البوت وإدارة الاشتراك."
    if db["images"]["admin"]:
        await message.reply_photo(photo=db["images"]["admin"], caption=admin_text, reply_markup=get_admin_buttons())
    else:
        await message.reply_text(text=admin_text, reply_markup=get_admin_buttons())

# --- معالج الرسائل لاستقبال المدخلات (صور أو نصوص) ---
@app.on_message(filters.private & filters.user(OWNER_ID))
async def handle_inputs(client, message):
    user_id = message.from_user.id
    if user_id in waiting_for_input:
        input_type, category = waiting_for_input[user_id]
        
        if input_type == "img":
            db["images"][category] = message.text
            await message.reply_text(f"✅ **تم تحديث صورة قسم ({category}) بنجاح!**", reply_markup=get_admin_buttons())
        elif input_type == "txt":
            db["texts"][category] = message.text
            await message.reply_text(f"✅ **تم تحديث نص قسم ({category}) بنجاح!**", reply_markup=get_admin_buttons())
        elif input_type == "add_fsub":
            channel = message.text if message.text.startswith("@") else f"@{message.text}"
            if channel not in db["fsub"]:
                db["fsub"].append(channel)
                await message.reply_text(f"✅ **تم إضافة القناة {channel} للاشتراك الإجباري.**", reply_markup=get_admin_buttons())
            else:
                await message.reply_text("⚠️ القناة مضافة بالفعل.")
            
        del waiting_for_input[user_id]

# --- معالج ضغطات الأزرار (Callback Query Handler) ---
@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name

    # التحقق من الاشتراك قبل تنفيذ الأوامر لغير المطورين
    if user_id != OWNER_ID and data != "main_menu":
         if not await check_fsub(client, callback_query.message):
             return

    # نظام نظافة الشات
    if data != "confirm_delete_fsub": # لا نحذف الرسالة عند طلب التأكيد للسماح بالرجوع
        try:
            await callback_query.message.delete()
        except:
            pass

    if data == "main_menu":
        text = db["texts"]["welcome"].format(user_name=user_name, user_id=user_id, owner_id=OWNER_ID)
        if db["images"]["welcome"]:
            await client.send_photo(chat_id=callback_query.message.chat.id, photo=db["images"]["welcome"], caption=text, reply_markup=main_buttons)
        else:
            await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=main_buttons)

    elif data == "general_libs":
        text = (
            "📦 **المكتبات العامة الأساسية:**\n\n"
            "**لمس الكود للنسخ:**\n"
            "`pip install requests`\n"
            "`pip install wheel`\n"
            "`pip install pandas`\n"
            "`pip install numpy`\n"
            "`pip install colorama`"
        )
        if db["images"]["general"]:
            await client.send_photo(chat_id=callback_query.message.chat.id, photo=db["images"]["general"], caption=text, reply_markup=back_markup)
        else:
            await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=back_markup)

    elif data == "trading_libs":
        text = (
            "📉 **مكتبات التداول والخوارزميات:**\n\n"
            "**لمس الكود للنسخ:**\n"
            "`pip install TA-Lib`\n"
            "`pip install ccxt`\n"
            "`pip install MetaTrader5`\n"
            "`pip install yfinance`"
        )
        if db["images"]["trading"]:
            await client.send_photo(chat_id=callback_query.message.chat.id, photo=db["images"]["trading"], caption=text, reply_markup=back_markup)
        else:
            await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=back_markup)

    elif data == "tg_libs":
        text = (
            "🤖 **مكتبات تطوير بوتات التيليجرام:**\n\n"
            "**لمس الكود للنسخ:**\n"
            "`pip install pyrogram`\n"
            "`pip install tgcrypto`\n"
            "`pip install telebot`\n"
            "`pip install python-telegram-bot`"
        )
        await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=back_markup)

    elif data == "ai_libs":
        text = (
            "🧠 **مكتبات الذكاء الاصطناعي:**\n\n"
            "**لمس الكود للنسخ:**\n"
            "`pip install openai`\n"
            "`pip install tensorflow`\n"
            "`pip install torch`\n"
            "`pip install scikit-learn`"
        )
        if db["images"]["ai"]:
            await client.send_photo(chat_id=callback_query.message.chat.id, photo=db["images"]["ai"], caption=text, reply_markup=back_markup)
        else:
            await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=back_markup)

    elif data == "termux_cmds":
        text = (
            "💻 **أوامر تهيئة الترمكس الأساسية:**\n\n"
            "**لمس الكود للنسخ:**\n"
            "`pkg update && pkg upgrade`\n"
            "`pkg install python`\n"
            "`pkg install git`\n"
            "`pkg install wget`"
        )
        if db["images"]["termux"]:
            await client.send_photo(chat_id=callback_query.message.chat.id, photo=db["images"]["termux"], caption=text, reply_markup=back_markup)
        else:
            await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=back_markup)

    # --- إدارة الاشتراك الإجباري (المطور فقط) ---
    elif data == "manage_fsub":
        fsub_keys = []
        for ch in db["fsub"]:
            fsub_keys.append([InlineKeyboardButton(f"❌ حذف: {ch}", callback_data=f"del_fsub_{ch}")])
        
        if len(db["fsub"]) < 3:
            fsub_keys.append([InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="add_fsub_action")])
        
        fsub_keys.append([InlineKeyboardButton("⬅️ عودة للوحة التحكم", callback_data="admin_back")])
        
        await client.send_message(
            chat_id=callback_query.message.chat.id,
            text=f"🔗 **إدارة الاشتراك الإجباري**\n\nالقنوات المضافة حالياً ({len(db['fsub'])}/3):",
            reply_markup=InlineKeyboardMarkup(fsub_keys)
        )

    elif data == "add_fsub_action":
        waiting_for_input[user_id] = ("add_fsub", "none")
        await callback_query.answer("أرسل الآن معرف القناة (مثال: @lb2_c)", show_alert=True)
        await client.send_message(chat_id=callback_query.message.chat.id, text="📝 **من فضلك أرسل معرف القناة الآن:**")

    elif data.startswith("del_fsub_"):
        channel_to_del = data.replace("del_fsub_", "")
        del_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ حذف الآن", callback_data=f"confirm_delete_fsub_{channel_to_del}")],
            [InlineKeyboardButton("⬅️ تراجع (رجوع)", callback_data="manage_fsub")]
        ])
        await client.send_message(
            chat_id=callback_query.message.chat.id,
            text=f"⚠️ **شروط الحذف:**\n\nهل أنت متأكد من رغبتك في حذف القناة {channel_to_del} من نظام الاشتراك الإجباري؟\nسيتمكن المستخدمون من دخول البوت دون الاشتراك فيها بعد الحذف.",
            reply_markup=del_markup
        )

    elif data.startswith("confirm_delete_fsub_"):
        channel_to_del = data.replace("confirm_delete_fsub_", "")
        if channel_to_del in db["fsub"]:
            db["fsub"].remove(channel_to_del)
            await callback_query.answer(f"✅ تم حذف {channel_to_del}", show_alert=True)
        await callback_query.message.delete()
        # العودة للقائمة
        await callback_handler(client, type('obj', (object,), {'data': 'manage_fsub', 'from_user': callback_query.from_user, 'message': callback_query.message}))

    elif data == "admin_back":
        admin_text = "🛠️ **أهلاً بك في لوحة تحكم المطور.**"
        if db["images"]["admin"]:
            await client.send_photo(chat_id=callback_query.message.chat.id, photo=db["images"]["admin"], caption=admin_text, reply_markup=get_admin_buttons())
        else:
            await client.send_message(chat_id=callback_query.message.chat.id, text=admin_text, reply_markup=get_admin_buttons())

    # معالجات أزرار الإعدادات الأصلية
    elif data.startswith("set_img_"):
        category = data.replace("set_img_", "")
        waiting_for_input[user_id] = ("img", category)
        await callback_query.answer("أرسل الآن رابط الصورة الجديد...", show_alert=True)
        await client.send_message(chat_id=callback_query.message.chat.id, text=f"📸 **من فضلك أرسل رابط الصورة لقسم: {category}**")

    elif data == "set_txt_welcome":
        waiting_for_input[user_id] = ("txt", "welcome")
        await callback_query.answer("أرسل الآن نص الترحيب الجديد...", show_alert=True)
        await client.send_message(chat_id=callback_query.message.chat.id, text="📝 **أرسل الكليشة الجديدة.\nيمكنك استخدام {user_name} و {user_id} و {owner_id} داخل النص.**")

# --- بدء تشغيل البوت ---
if __name__ == "__main__":
    print("البوت يعمل الآن بنجاح على سيرفر Railway...")
    app.run()
