import telebot
from telebot import types
from youtube_search import YoutubeSearch
import json
import os
import yt_dlp

# --- بيانات المطور الأساسية ---
# ملاحظة: تأكد من صحة التوكن والـ API والمعرفات أدناه
TOKEN = '8180650384:AAEMk7xiqf5uXaOUw0DXdYIsjko_bk4P_6M'
DEVELOPER_ID = 8456056018
API_ID = 35247597
API_HASH = 'ff0000a5175c6b79e322677e9a537a57'
SOURCE_CHANNEL = '@Tl2_2'
DEVELOPER_USER = '@lb2_c'

bot = telebot.TeleBot(TOKEN)
DATA_FILE = 'bot_settings.json'
user_states = {} 

# تحميل الإعدادات أو إنشاؤها
if not os.path.exists(DATA_FILE):
    default_settings = {
        "bot_status": True,
        "dev_user": "@lb2_c",
        "sub_channels": [],
        "sub_msg": "عذراً، يجب عليك الاشتراك في قنواتنا لاستخدام البوت.",
        "welcome_msg": "أهلاً بك في بوت تحميل الموسيقى من يوتيوب!",
        "welcome_photo": None,
        "notifications": True,
        "bot_name": "بوت الخدمة",
        "users": [],
        "groups": []
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(default_settings, f)

def load_settings():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_settings(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def is_authorized(message):
    uid = message.from_user.id if isinstance(message, (types.Message, types.CallbackQuery)) else message
    return uid == DEVELOPER_ID

def check_subscription(user_id):
    settings = load_settings()
    not_subbed = []
    for chan in settings.get('sub_channels', []):
        try:
            status = bot.get_chat_member(chan, user_id).status
            if status not in ['member', 'administrator', 'creator']:
                not_subbed.append(chan)
        except:
            continue
    return not_subbed

def register_user(message):
    data = load_settings()
    cid = message.chat.id
    if message.chat.type == 'private':
        if cid not in data.get('users', []):
            if 'users' not in data: data['users'] = []
            data['users'].append(cid)
            save_settings(data)
    else:
        if cid not in data.get('groups', []):
            if 'groups' not in data: data['groups'] = []
            data['groups'].append(cid)
            save_settings(data)

# --- 1. أمر البداية ---
@bot.message_handler(commands=['start'])
def start(message):
    register_user(message)
    settings = load_settings()
    
    not_subbed = check_subscription(message.from_user.id)

    if not_subbed:
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c in not_subbed:
            markup.add(types.InlineKeyboardButton(f"انضم للقناة 📢", url=f"https://t.me/{c.replace('@','')}"))
        markup.add(types.InlineKeyboardButton("تحقق من الاشتراك ✅", callback_data="verify_sub"))
        
        bot.send_message(message.chat.id, f"⚠️ **{settings['sub_msg']}**", reply_markup=markup, parse_mode="Markdown")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_help = types.InlineKeyboardButton('كيفية الاستخدام ℹ️', callback_data="services")
    btn_dev = types.InlineKeyboardButton('المطور 👤', url=f"https://t.me/{settings['dev_user'].replace('@','')}")
    markup.add(btn_help, btn_dev)
    
    welcome_text = f"**{settings['welcome_msg']}**\n\n" \
                   f"**مرحباً بك يا {message.from_user.first_name} في بوت {settings['bot_name']}.**\n" \
                   f"**أنا هنا لمساعدتك في العثور على المقاطع الصوتية وتحميلها من يوتيوب بجودة عالية.**"
    
    if settings.get('welcome_photo'):
        try:
            bot.send_photo(message.chat.id, settings['welcome_photo'], caption=welcome_text, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")

# --- 2. لوحة تحكم المطور ---
def show_admin_panel(chat_id, message_id=None):
    settings = load_settings()
    status_text = "🟢 مفعل" if settings.get('bot_status') else "🔴 معطل"
    notify_text = "🔔 مفعلة" if settings.get('notifications') else "🔕 معطلة"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        types.InlineKeyboardButton("قنوات الاشتراك 📢", callback_data="manage_subs"),
        types.InlineKeyboardButton("قسم الإذاعة 📣", callback_data="broadcast_sections"),
        types.InlineKeyboardButton("الإحصائيات 📊", callback_data="bot_stats"),
        types.InlineKeyboardButton(f"التنبيهات: {notify_text}", callback_data="toggle_notify"),
        types.InlineKeyboardButton(f"اسم البوت 📛", callback_data="manage_name"),
        types.InlineKeyboardButton(f"المطور 👤", callback_data="set_dev"),
        types.InlineKeyboardButton("رسالة الترحيب 📝", callback_data="manage_welcome"),
        types.InlineKeyboardButton("صورة الترحيب 🖼", callback_data="manage_photo"),
        types.InlineKeyboardButton("نسخة احتياطية 📂", callback_data="backup"),
        types.InlineKeyboardButton(f"الحالة: {status_text}", callback_data="toggle_status"),
        types.InlineKeyboardButton("إغلاق اللوحة ❌", callback_data="close_panel")
    ]
    markup.add(*btns)
    
    text = "**⚡ أهلاً بك في لوحة تحكم المطور**\n**تحكم في إعدادات البوت من خلال الأزرار أدناه:**"
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['admin'])
def admin_command(message):
    if not is_authorized(message): return
    if message.chat.type != 'private':
        bot.reply_to(message, "**❌ لوحة التحكم متاحة فقط في الخاص.**")
        return
    show_admin_panel(message.chat.id)

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    settings = load_settings()
    
    if call.data == "verify_sub":
        not_subbed = check_subscription(call.from_user.id)
        if not not_subbed:
            bot.answer_callback_query(call.id, "رائع! تم التحقق من اشتراكك بنجاح.", show_alert=True)
            bot.delete_message(call.message.chat.id, call.message.message_id)
            start(call.message)
        else:
            bot.answer_callback_query(call.id, "عذراً، لم تشترك في كافة القنوات المطلوبة!", show_alert=True)

    elif call.data == "services":
        bot.answer_callback_query(call.id)
        help_msg = "**How to use the bot:**\n\n**Send one of the shortcuts followed by the track name:**\n`يوت` , `y` , `yt` , `ewt` \n\n**Example:**\n`y Alan Walker` \n`يوت سورة الكهف`"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع 🔙", callback_data="back_to_start"))
        
        try:
            bot.edit_message_text(help_msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            try: bot.edit_message_caption(help_msg, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            except: pass
    
    elif call.data == "back_to_start":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_help = types.InlineKeyboardButton('كيفية الاستخدام ℹ️', callback_data="services")
        btn_dev = types.InlineKeyboardButton('المطور 👤', url=f"https://t.me/{settings['dev_user'].replace('@','')}")
        markup.add(btn_help, btn_dev)
        welcome_text = f"**{settings['welcome_msg']}**\n\n" \
                       f"**مرحباً بك يا {call.from_user.first_name} في بوت {settings['bot_name']}.**"
        
        try:
            bot.edit_message_text(welcome_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        except:
            try: bot.edit_message_caption(welcome_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            except: pass

    if not is_authorized(call): return

    elif call.data == "activate_from_group":
        settings['bot_status'] = True
        save_settings(settings)
        bot.answer_callback_query(call.id, "✅ تم تفعيل البوت بنجاح!", show_alert=True)
        bot.edit_message_text("**✅ تم تفعيل خدمات البوت بنجاح!**\n\n**أصبح البوت متاحاً الآن للاستخدام في كافة المجموعات والخاص.**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    elif call.data == "manage_name":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("تغيير الاسم ✏️", callback_data="set_name"),
            types.InlineKeyboardButton("حذف الاسم 🗑", callback_data="delete_name")
        )
        markup.add(
            types.InlineKeyboardButton("عرض الاسم 👀", callback_data="view_name"),
            types.InlineKeyboardButton("رجوع 🔙", callback_data="open_admin")
        )
        bot.edit_message_text(f"**🛠 إدارة هوية البوت (الاسم):**\n\n**اسم البوت الحالي هو:**\n└ `{settings['bot_name']}`\n\n**يمكنك تغيير الاسم ليظهر للمستخدمين في رسائل الترحيب.**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "delete_name":
        settings['bot_name'] = "بوت الخدمة"
        save_settings(settings)
        bot.answer_callback_query(call.id, "تم استعادة الاسم الافتراضي")
        show_admin_panel(call.message.chat.id, call.message.message_id)

    elif call.data == "view_name":
        bot.answer_callback_query(call.id, f"الاسم الحالي: {settings['bot_name']}", show_alert=True)

    elif call.data == "manage_welcome":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("تغيير النص ✏️", callback_data="set_welcome"),
            types.InlineKeyboardButton("حذف النص 🗑", callback_data="delete_welcome"),
            types.InlineKeyboardButton("عرض النص 👀", callback_data="view_welcome"),
            types.InlineKeyboardButton("رجوع 🔙", callback_data="open_admin")
        )
        bot.edit_message_text("**📝 إدارة رسالة الترحيب:**\n\n**قم باختيار أحد الخيارات أدناه لتعديل أو عرض نص الترحيب الخاص بالبوت.**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "delete_welcome":
        settings['welcome_msg'] = "أهلاً بك في بوت تحميل الموسيقى من يوتيوب!"
        save_settings(settings)
        bot.answer_callback_query(call.id, "تم استعادة الرسالة الافتراضية")
        show_admin_panel(call.message.chat.id, call.message.message_id)

    elif call.data == "view_welcome":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"**معاينة رسالة الترحيب الحالية:**\n\n**{settings['welcome_msg']}**", parse_mode="Markdown")

    elif call.data == "manage_photo":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📸 تعيين صورة جديدة", callback_data="set_photo"),
            types.InlineKeyboardButton("🗑 حذف الصورة الحالية", callback_data="delete_photo")
        )
        markup.add(types.InlineKeyboardButton("🔙 رجوع للوحة", callback_data="open_admin"))
        
        status_photo = "موجودة ومفعلة ✅" if settings.get('welcome_photo') else "غير محددة (نص فقط) ❌"
        bot.edit_message_text(f"**🖼 إعدادات صورة الترحيب:**\n\n**الحالة الحالية:** {status_photo}\n\n**ملاحظة:** الصورة تظهر للمستخدم عند إرسال أمر /start.", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "delete_photo":
        settings['welcome_photo'] = None
        save_settings(settings)
        bot.answer_callback_query(call.id, "تم حذف الصورة")
        show_admin_panel(call.message.chat.id, call.message.message_id)

    elif call.data == "bot_stats":
        bot.answer_callback_query(call.id)
        u_count = len(settings.get('users', []))
        g_count = len(settings.get('groups', []))
        total = u_count + g_count
        stats_text = (
            f"📊 **إحصائيات استخدام البوت**\n\n"
            f"👤 **المستخدمين في الخاص:** `{u_count}`\n"
            f"👥 **المجموعات والقنوات:** `{g_count}`\n"
            f"🌐 **إجمالي المشتركين:** `{total}`\n"
            f"━━━━━━━━━━━━━━━"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("تحديث الإحصائيات 🔄", callback_data="bot_stats"))
        markup.add(types.InlineKeyboardButton("رجوع للوحة 🔙", callback_data="open_admin"))
        bot.edit_message_text(stats_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "broadcast_sections":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 إذاعة لجميع المشتركين", callback_data="bc_all"),
            types.InlineKeyboardButton("👤 إذاعة للأفراد (خاص) فقط", callback_data="bc_users"),
            types.InlineKeyboardButton("👥 إذاعة للمجموعات فقط", callback_data="bc_groups"),
            types.InlineKeyboardButton("🔙 رجوع للوحة التحكم", callback_data="open_admin")
        )
        bot.edit_message_text("**📣 قسم الإذاعة والتوجيه:**\n\n**اختر الفئة المستهدفة لإرسال رسالتك إليها:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("bc_"):
        mode = call.data.split("_")[1]
        user_states[call.from_user.id] = f"waiting_for_bc_{mode}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("إلغاء الأمر ❌", callback_data="broadcast_sections"))
        bot.send_message(call.message.chat.id, "**✉️ قم بإرسال رسالة الإذاعة الآن:**\n\n*(يمكنك إرسال نص، صورة، فيديو، أو حتى توجيه رسالة)*", parse_mode="Markdown", reply_markup=markup)
        bot.answer_callback_query(call.id)

    elif call.data == "manage_subs":
        markup = types.InlineKeyboardMarkup(row_width=1)
        channels = settings.get('sub_channels', [])
        for i, ch in enumerate(channels):
            markup.add(types.InlineKeyboardButton(f"🗑 حذف القناة: {ch}", callback_data=f"del_sub_{i}"))
        
        if len(channels) < 3:
            markup.add(types.InlineKeyboardButton("➕ إضافة قناة جديدة", callback_data="add_sub"))
            
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="open_admin"))
        bot.edit_message_text(f"**الاشتراك الإجباري ({len(channels)}/3):**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "add_sub":
        user_states[call.from_user.id] = "waiting_for_sub"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("إلغاء ❌", callback_data="manage_subs"))
        bot.send_message(call.message.chat.id, "**أرسل معرف القناة الآن (مثال: @Tl2_2):**", parse_mode="Markdown", reply_markup=markup)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("del_sub_"):
        idx = int(call.data.split("_")[2])
        try:
            settings['sub_channels'].pop(idx)
            save_settings(settings)
            bot.answer_callback_query(call.id, "تم الحذف")
            show_admin_panel(call.message.chat.id, call.message.message_id)
        except: pass

    elif call.data == "open_admin":
        show_admin_panel(call.message.chat.id, call.message.message_id)

    elif call.data == "close_panel":
        bot.delete_message(call.message.chat.id, call.message.message_id)

    elif call.data == "toggle_status":
        settings['bot_status'] = not settings.get('bot_status', True)
        save_settings(settings)
        show_admin_panel(call.message.chat.id, call.message.message_id)
    
    elif call.data == "toggle_notify":
        settings['notifications'] = not settings.get('notifications', True)
        save_settings(settings)
        show_admin_panel(call.message.chat.id, call.message.message_id)

    elif call.data == "backup":
        with open(DATA_FILE, 'rb') as f:
            bot.send_document(call.message.chat.id, f, caption="**📂 نسخة احتياطية لإعدادات البوت**", parse_mode="Markdown")

    elif call.data in ["set_name", "set_dev", "set_welcome", "set_photo"]:
        states_map = {
            "set_name": ("waiting_for_name", "**✏️ أرسل الاسم الجديد للبوت الآن:**"),
            "set_dev": ("waiting_for_dev_user", "**👤 أرسل معرف المطور الجديد (مثال: @lb2_c):**"),
            "set_welcome": ("waiting_for_welcome", "**📝 أرسل نص الترحيب الجديد الآن:**"),
            "set_photo": ("waiting_for_photo", "**🖼 أرسل صورة الترحيب الجديدة الآن:**")
        }
        state, msg_text = states_map[call.data]
        user_states[call.from_user.id] = state
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("إلغاء ❌", callback_data="open_admin"))
        bot.send_message(call.message.chat.id, msg_text, parse_mode="Markdown", reply_markup=markup)

# --- 3. معالجة المدخلات ---
@bot.message_handler(content_types=['text', 'photo'], func=lambda message: is_authorized(message) and message.from_user.id in user_states)
def handle_developer_inputs(message):
    state = user_states[message.from_user.id]
    settings = load_settings()
    
    if state == "waiting_for_sub":
        if 'sub_channels' not in settings: settings['sub_channels'] = []
        if message.text and message.text.startswith("@"):
            settings['sub_channels'].append(message.text)
            bot.reply_to(message, "**✅ تم إضافة القناة بنجاح.**", parse_mode="Markdown")
        else:
            bot.reply_to(message, "**❌ خطأ: يجب أن يبدأ المعرف بـ @**", parse_mode="Markdown")
            return
    
    elif state.startswith("waiting_for_bc_"):
        mode = state.split("_")[3]
        targets = []
        if mode == "all": targets = settings.get('users', []) + settings.get('groups', [])
        elif mode == "users": targets = settings.get('users', [])
        elif mode == "groups": targets = settings.get('groups', [])
        
        count = 0
        bot.send_message(message.chat.id, f"**🚀 جاري الإذاعة إلى {len(targets)} محادثة...**", parse_mode="Markdown")
        for cid in targets:
            try:
                bot.copy_message(cid, message.chat.id, message.message_id)
                count += 1
            except: pass
        bot.send_message(message.chat.id, f"**✅ تم اكتمال الإذاعة بنجاح لـ {count} مشترك.**", parse_mode="Markdown")

    elif state == "waiting_for_name":
        settings['bot_name'] = message.text
        bot.reply_to(message, "**✅ تم تحديث اسم البوت بنجاح.**", parse_mode="Markdown")

    elif state == "waiting_for_dev_user":
        settings['dev_user'] = message.text
        bot.reply_to(message, "**✅ تم تحديث معرف المطور.**", parse_mode="Markdown")

    elif state == "waiting_for_welcome":
        settings['welcome_msg'] = message.text
        bot.reply_to(message, "**✅ تم تحديث نص الترحيب بنجاح.**", parse_mode="Markdown")

    elif state == "waiting_for_photo":
        if message.content_type == 'photo':
            settings['welcome_photo'] = message.photo[-1].file_id
            bot.reply_to(message, "**✅ تم تحديث صورة الترحيب بنجاح.**", parse_mode="Markdown")
        else:
            bot.reply_to(message, "**❌ يرجى إرسال صورة حصراً.**", parse_mode="Markdown")
            return

    save_settings(settings)
    del user_states[message.from_user.id]
    if message.chat.type == 'private':
        show_admin_panel(message.chat.id)

# --- 4. البحث وتحميل الصوت (تم التحديث لزيادة السرعة) ---
def progress_hook(d, message, sent_msg, title):
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%')
        bar_length = 8
        try:
            percent_clean = float(''.join(c for c in p if c.isdigit() or c == '.'))
            filled = int(percent_clean / (100 / bar_length))
        except:
            filled = 0
            
        bar = "●" * filled + "○" * (bar_length - filled)
        
        process_text = (
            f"**📥 Down: {bar} {p}**\n"
            f"**🎵 {title[:30]}...**\n"
            f"**⚡ Processing audio...**"
        )
        
        try:
            bot.edit_message_text(process_text, message.chat.id, sent_msg.message_id, parse_mode="Markdown")
        except: pass

@bot.message_handler(func=lambda message: message.text and any(message.text.lower().startswith(cmd) for cmd in ["يوت ", "y ", "yt ", "ewt "]))
def search_and_download(message):
    settings = load_settings()
    
    not_subbed = check_subscription(message.from_user.id)
    if not_subbed and not is_authorized(message):
        markup = types.InlineKeyboardMarkup(row_width=1)
        for c in not_subbed:
            markup.add(types.InlineKeyboardButton(f"انضم للقناة 📢", url=f"https://t.me/{c.replace('@','')}"))
        markup.add(types.InlineKeyboardButton("تحقق من الاشتراك ✅", callback_data="verify_sub"))
        bot.reply_to(message, f"⚠️ **{settings['sub_msg']}**", reply_markup=markup, parse_mode="Markdown")
        return

    if not settings.get('bot_status', True) and not is_authorized(message):
        bot.reply_to(message, "**عذراً، الخدمة تحت الصيانة حالياً.**", parse_mode="Markdown")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        bot.reply_to(message, "**⚠️ أرسل اسم المقطع.**\nمثال: `y Alan Walker` ", parse_mode="Markdown")
        return
    
    query = parts[1].strip()
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except: pass

    sent_msg = bot.send_message(message.chat.id, f"**🔍 Searching: {query}...**", parse_mode="Markdown")

    try:
        search_results = YoutubeSearch(query, max_results=1).to_dict()
        if not search_results:
            bot.edit_message_text(f"**❌ No results found.**", message.chat.id, sent_msg.message_id, parse_mode="Markdown")
            return

        video_info = search_results[0]
        video_url = "https://www.youtube.com" + video_info['url_suffix']
        file_id = video_info['id']
        title = video_info['title']

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"{file_id}.%(ext)s",
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'extract_flat': False,
            'geo_bypass': True,
            'cachedir': False,
            'progress_hooks': [lambda d: progress_hook(d, message, sent_msg, title)],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'external_downloader': 'aria2c',
            'external_downloader_args': ['-x', '16', '-s', '16', '-k', '1M'],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        final_file = f"{file_id}.mp3"
        if os.path.exists(final_file):
            bot.edit_message_text(f"**🚀 Uploading to Telegram...**", message.chat.id, sent_msg.message_id, parse_mode="Markdown")
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Source Channel 📢", url=f"https://t.me/{SOURCE_CHANNEL.replace('@','')}"))

            with open(final_file, 'rb') as audio:
                bot.send_audio(
                    message.chat.id, 
                    audio, 
                    title=title, 
                    performer=settings.get('bot_name', 'Hyper'),
                    reply_markup=markup,
                    timeout=120
                )
            bot.delete_message(message.chat.id, sent_msg.message_id)
            os.remove(final_file)
        else:
            raise Exception("File extraction failed.")

    except Exception as e:
        bot.edit_message_text(f"**⚠️ Process Failed:**\n`{str(e)}`", message.chat.id, sent_msg.message_id, parse_mode="Markdown")

# --- 5. أوامر الإدارة السريعة والردود ---
@bot.message_handler(func=lambda message: True)
def all_messages_handler(message):
    settings = load_settings()
    
    if message.text and settings.get('bot_name', '') in message.text:
        bot.reply_to(message, f"**نعم يا {message.from_user.first_name}، أنا بوت {settings['bot_name']} كيف يمكنني مساعدتك؟ ⚡**", parse_mode="Markdown")
        return

    if is_authorized(message):
        if message.text == "تفعيل":
            settings['bot_status'] = True
            save_settings(settings)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("قناة السورس 📢", url=f"https://t.me/{SOURCE_CHANNEL.replace('@','')}"))
            bot.reply_to(message, "**✅ تم تفعيل كافة خدمات البوت بنجاح!**", reply_markup=markup, parse_mode="Markdown")
            
        elif message.text == "تعطيل":
            settings['bot_status'] = False
            save_settings(settings)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("إعادة تشغيل 🔄", callback_data="activate_from_group"))
            bot.reply_to(message, "**🔴 تم تعطيل خدمات البوت، سيتم رفض كافة الطلبات الآن.**", reply_markup=markup, parse_mode="Markdown")
            
        elif message.text == "غادر":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("المطور 👤", url=f"https://t.me/{settings['dev_user'].replace('@','')}"))
            bot.reply_to(message, "**👋 بناءً على طلب المطور، سأقوم بمغادرة هذه الدردشة الآن. وداعاً!**", reply_markup=markup, parse_mode="Markdown")
            bot.leave_chat(message.chat.id)

print("Bot is running successfully with the new updates...")
bot.infinity_polling()
