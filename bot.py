import os
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import UserNotParticipant

# --- إعدادات البوت الكاملة ---
API_ID = 27485469  
API_HASH = "544459a0701b32741254945b08daebfe" 
BOT_TOKEN = "8386513995:AAHBL3QdbshzTo-jLNq_jQQ7yV66ycSv8Rs" 
OWNER_ID = 8456056018 # الآيدي الخاص بك

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- نظام قاعدة البيانات SQLite ---
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    # جدول الإعدادات
    cursor.execute("""CREATE TABLE IF NOT EXISTS settings 
                      (key TEXT PRIMARY KEY, value TEXT)""")
    # جدول المستخدمين للإحصائيات والإذاعة
    cursor.execute("""CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY)""")
    # جدول قنوات الاشتراك
    cursor.execute("""CREATE TABLE IF NOT EXISTS fsub 
                      (channel TEXT PRIMARY KEY)""")
    conn.commit()
    conn.close()

def set_setting(key, value):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def add_user(user_id):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_users_count():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def add_fsub_db(channel):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO fsub (channel) VALUES (?)", (channel,))
    conn.commit()
    conn.close()

def del_fsub_db(channel):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM fsub WHERE channel = ?", (channel,))
    conn.commit()
    conn.close()

def get_fsub_list():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel FROM fsub")
    channels = [row[0] for row in cursor.fetchall()]
    conn.close()
    return channels

# تهيئة قاعدة البيانات عند التشغيل
init_db()

# متغيّر لتتبع حالة الإدخال المؤقتة
waiting_for_input = {}

# --- دالة التحقق من الاشتراك الإجباري ---
async def check_fsub(client, message):
    channels = get_fsub_list()
    if not channels:
        return True
    
    unsubscribed = []
    for channel in channels:
        try:
            await client.get_chat_member(channel, message.from_user.id)
        except UserNotParticipant:
            unsubscribed.append(channel)
        except Exception:
            pass 

    if unsubscribed:
        keys = []
        for ch in unsubscribed:
            keys.append([InlineKeyboardButton(f"اشترك هنا: {ch}", url=f"https://t.me/{ch.replace('@','')}")])
        keys.append([InlineKeyboardButton("تحقق من الاشتراك", callback_data="main_menu")])
        
        await message.reply_text(
            "**عذراً عزيزي، يجب عليك الاشتراك في قنوات البوت لتتمكن من استخدامه!**",
            reply_markup=InlineKeyboardMarkup(keys)
        )
        return False
    return True

# --- لوحة الأزرار الرئيسية ---
main_buttons = InlineKeyboardMarkup([
    [InlineKeyboardButton("المكتبات العامة", callback_data="general_libs")],
    [InlineKeyboardButton("مكتبات التداول", callback_data="trading_libs")],
    [InlineKeyboardButton("مكتبات التيليجرام", callback_data="tg_libs")],
    [InlineKeyboardButton("مكتبات الذكاء الاصطناعي", callback_data="ai_libs")],
    [InlineKeyboardButton("أوامر الترمكس", callback_data="termux_cmds")],
    [InlineKeyboardButton("قناة المطور", url="https://t.me/lb2_c")]
])

# لوحة تحكم المطور المحدثة
def get_admin_buttons():
    buttons = [
        [InlineKeyboardButton("تعيين نص الترحيب", callback_data="set_txt_welcome")],
        [InlineKeyboardButton("صورة الترحيب", callback_data="set_img_welcome")],
        [InlineKeyboardButton("صورة المكتبات العامة", callback_data="set_img_general")],
        [InlineKeyboardButton("صورة مكتبات التداول", callback_data="set_img_trading")],
        [InlineKeyboardButton("صورة الذكاء الاصطناعي", callback_data="set_img_ai")],
        [InlineKeyboardButton("صورة أوامر تيرمكس", callback_data="set_img_termux")],
        [InlineKeyboardButton("صورة لوحة التحكم", callback_data="set_img_admin")],
        [InlineKeyboardButton("إدارة الاشتراك الإجباري", callback_data="manage_fsub")],
        [InlineKeyboardButton("قسم الإذاعة 📢", callback_data="broadcast_section")],
        [InlineKeyboardButton("إحصائيات البوت 📊", callback_data="stats_action")],
        [InlineKeyboardButton("عودة للقائمة الرئيسية", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)

# زر العودة للقائمة الرئيسية
back_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton("عودة للقائمة الرئيسية", callback_data="main_menu")]
])

# --- معالج أمر البداية /start ---
@app.on_message(filters.command("start"))
async def start(client, message):
    # إضافة المستخدم للقاعدة للإحصائيات
    add_user(message.from_user.id)
    
    if not await check_fsub(client, message):
        return
        
    user_name = message.from_user.first_name
    user_id = message.from_user.id
    
    default_welcome = "أهلاً بك يا {user_name} في بوت المكتبات\n\nهذا البوت يوفر لك كل اختصارات تثبيت المكتبات البرمجية بضغطة واحدة.\n\n• ايدي حسابك: `{user_id}`\n• ايدي المطور المثبت: `{owner_id}`\n• مطور البوت: Hassan\n• قناة المطور: @lb2_c"
    welcome_text_raw = get_setting("welcome_text", default_welcome)
    welcome_text = welcome_text_raw.format(user_name=user_name, user_id=user_id, owner_id=OWNER_ID)
    
    welcome_img = get_setting("welcome_img")
    
    if welcome_img:
        await message.reply_photo(photo=welcome_img, caption=welcome_text, reply_markup=main_buttons)
    else:
        await message.reply_text(text=welcome_text, reply_markup=main_buttons)

# --- أمر المطور /admin ---
@app.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    admin_text = "**أهلاً بك في لوحة تحكم المطور.**\n\nيمكنك من هنا تعيين وتحديث صور ونصوص أقسام البوت وإدارة الاشتراك والإذاعة."
    admin_img = get_setting("admin_img")
    if admin_img:
        await message.reply_photo(photo=admin_img, caption=admin_text, reply_markup=get_admin_buttons())
    else:
        await message.reply_text(text=admin_text, reply_markup=get_admin_buttons())

# --- معالج الرسائل لاستقبال المدخلات ---
@app.on_message(filters.private & filters.user(OWNER_ID))
async def handle_inputs(client, message: Message):
    user_id = message.from_user.id
    if user_id in waiting_for_input:
        input_type, category = waiting_for_input[user_id]
        
        if input_type == "img":
            file_id = message.photo.file_id if message.photo else message.text
            if file_id:
                set_setting(f"{category}_img", file_id)
                await message.reply_text(f"**تم حفظ صورة قسم ({category}) بنجاح!**", reply_markup=get_admin_buttons())
            else:
                await message.reply_text("**خطأ: يرجى إرسال صورة أو رابط.**")
            del waiting_for_input[user_id]

        elif input_type == "txt":
            if message.text:
                set_setting(f"{category}_text", message.text)
                await message.reply_text(f"**تم تحديث نص قسم ({category}) بنجاح!**", reply_markup=get_admin_buttons())
                del waiting_for_input[user_id]

        elif input_type == "add_fsub":
            if message.text:
                channel = message.text if message.text.startswith("@") else f"@{message.text}"
                add_fsub_db(channel)
                await message.reply_text(f"**تم إضافة {channel} لقائمة الاشتراك.**", reply_markup=get_admin_buttons())
                del waiting_for_input[user_id]
        
        elif input_type == "broadcast":
            await message.reply_text("**جاري الإذاعة... يرجى الانتظار.**")
            users = get_all_users()
            success = 0
            failed = 0
            for u_id in users:
                try:
                    await message.copy(u_id)
                    success += 1
                except:
                    failed += 1
            await message.reply_text(f"**تمت الإذاعة بنجاح!**\n\n• تم الإرسال لـ: {success}\n• فشل (حظروا البوت): {failed}")
            del waiting_for_input[user_id]

# --- معالج ضغطات الأزرار (Callback Query Handler) ---
@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name

    if user_id != OWNER_ID and data != "main_menu":
         if not await check_fsub(client, callback_query.message):
             return

    if data != "confirm_delete_fsub": 
        try: await callback_query.message.delete()
        except: pass

    if data == "main_menu":
        default_welcome = "أهلاً بك يا {user_name} في بوت المكتبات\n\nهذا البوت يوفر لك كل اختصارات تثبيت المكتبات البرمجية بضغطة واحدة."
        text = get_setting("welcome_text", default_welcome).format(user_name=user_name, user_id=user_id, owner_id=OWNER_ID)
        img = get_setting("welcome_img")
        if img:
            await client.send_photo(chat_id=callback_query.message.chat.id, photo=img, caption=text, reply_markup=main_buttons)
        else:
            await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=main_buttons)

    elif data == "general_libs":
        text = "**المكتبات العامة الأساسية:**\n\n`pip install requests`\n`pip install wheel`\n`pip install pandas`\n`pip install numpy`\n`pip install colorama`"
        img = get_setting("general_img")
        if img: await client.send_photo(callback_query.message.chat.id, img, caption=text, reply_markup=back_markup)
        else: await client.send_message(callback_query.message.chat.id, text, reply_markup=back_markup)

    elif data == "trading_libs":
        text = "**مكتبات التداول والخوارزميات:**\n\n`pip install TA-Lib`\n`pip install ccxt`\n`pip install MetaTrader5`\n`pip install yfinance`"
        img = get_setting("trading_img")
        if img: await client.send_photo(callback_query.message.chat.id, img, caption=text, reply_markup=back_markup)
        else: await client.send_message(callback_query.message.chat.id, text, reply_markup=back_markup)

    elif data == "tg_libs":
        text = "**مكتبات تطوير بوتات التيليجرام:**\n\n`pip install pyrogram`\n`pip install tgcrypto`\n`pip install telebot`\n`pip install python-telegram-bot`"
        await client.send_message(callback_query.message.chat.id, text, reply_markup=back_markup)

    elif data == "ai_libs":
        text = "**مكتبات الذكاء الاصطناعي:**\n\n`pip install openai`\n`pip install tensorflow`\n`pip install torch`\n`pip install scikit-learn`"
        img = get_setting("ai_img")
        if img: await client.send_photo(callback_query.message.chat.id, img, caption=text, reply_markup=back_markup)
        else: await client.send_message(callback_query.message.chat.id, text, reply_markup=back_markup)

    elif data == "termux_cmds":
        text = "**أوامر تهيئة الترمكس الأساسية:**\n\n`pkg update && pkg upgrade`\n`pkg install python`\n`pkg install git`\n`pkg install wget`"
        img = get_setting("termux_img")
        if img: await client.send_photo(callback_query.message.chat.id, img, caption=text, reply_markup=back_markup)
        else: await client.send_message(callback_query.message.chat.id, text, reply_markup=back_markup)

    # --- إدارة الاشتراك الإجباري ---
    elif data == "manage_fsub":
        channels = get_fsub_list()
        fsub_keys = []
        for ch in channels:
            fsub_keys.append([InlineKeyboardButton(f"حذف: {ch}", callback_data=f"del_fsub_{ch}")])
        if len(channels) < 3:
            fsub_keys.append([InlineKeyboardButton("إضافة قناة جديدة", callback_data="add_fsub_action")])
        fsub_keys.append([InlineKeyboardButton("عودة للوحة التحكم", callback_data="admin_back")])
        await client.send_message(callback_query.message.chat.id, f"**إدارة الاشتراك الإجباري ({len(channels)}/3):**", reply_markup=InlineKeyboardMarkup(fsub_keys))

    elif data == "add_fsub_action":
        waiting_for_input[user_id] = ("add_fsub", "none")
        await client.send_message(callback_query.message.chat.id, "**أرسل الآن معرف القناة (مثال: @lb2_c):**")

    elif data.startswith("del_fsub_"):
        ch = data.replace("del_fsub_", "")
        del_fsub_db(ch)
        await callback_query.answer(f"تم حذف {ch}")
        await callback_handler(client, type('obj', (object,), {'data': 'manage_fsub', 'from_user': callback_query.from_user, 'message': callback_query.message}))

    # --- الإحصائيات والإذاعة ---
    elif data == "stats_action":
        count = get_users_count()
        await callback_query.answer(f"عدد مستخدمي البوت: {count}", show_alert=True)
        # إعادة إظهار لوحة التحكم
        await callback_handler(client, type('obj', (object,), {'data': 'admin_back', 'from_user': callback_query.from_user, 'message': callback_query.message}))

    elif data == "broadcast_section":
        waiting_for_input[user_id] = ("broadcast", "none")
        await client.send_message(callback_query.message.chat.id, "**أرسل الآن الرسالة التي تريد إذاعتها (نص، صورة، فيديو، بصمة... إلخ):**")

    elif data == "admin_back":
        admin_text = "**أهلاً بك في لوحة تحكم المطور.**"
        img = get_setting("admin_img")
        if img: await client.send_photo(callback_query.message.chat.id, img, admin_text, reply_markup=get_admin_buttons())
        else: await client.send_message(callback_query.message.chat.id, admin_text, reply_markup=get_admin_buttons())

    elif data.startswith("set_img_"):
        category = data.replace("set_img_", "")
        waiting_for_input[user_id] = ("img", category)
        await client.send_message(callback_query.message.chat.id, f"**أرسل صورة أو رابط لقسم: {category}**")

    elif data == "set_txt_welcome":
        waiting_for_input[user_id] = ("txt", "welcome")
        await client.send_message(callback_query.message.chat.id, "**أرسل كليشة الترحيب الجديدة:**")

# --- بدء تشغيل البوت ---
if __name__ == "__main__":
    print("البوت يعمل بنجاح مع قاعدة البيانات ونظام الإذاعة...")
    app.run()
