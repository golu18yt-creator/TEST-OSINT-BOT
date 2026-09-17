import http.server
import io
import json
import os
import socketserver
import sqlite3
import threading
import time
import requests

# ---------------------------------------------------------
# CONFIGURATION VARIABLES
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8687879528:AAHOavqELOL_IVbcdN3-EX00II5EsnoYZLU")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Tera_Osint_44bot")
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "Kya_Karega_Jaanke")

SUPER_ADMIN_ID = 8927308711  # Aapki Admin User ID
OWNER_PHONE_NUMBER = "8595900496"  # Owner ka mobile number (Protection ke liye)

EXTERNAL_API_URL = os.environ.get(
    "EXTERNAL_API_URL",
    "https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup",
)

EXTERNAL_TG_API_URL = os.environ.get(
    "EXTERNAL_TG_API_URL",
    "https://tg2num-botadminshere.vercel.app/?id={value}",
)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
user_states = {}
BOT_ACTIVE = True  # Default bot active status


# ---------------------------------------------------------
# DATABASE SETUP (SQLite)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            credits INTEGER DEFAULT 5,
            referred_by INTEGER,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS force_channels (
            channel_id TEXT PRIMARY KEY,
            channel_link TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            credits INTEGER,
            max_uses INTEGER DEFAULT 100
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claimed_codes (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    """)

    default_settings = [
        (
            "welcome_msg",
            "⚡ <b>WELCOME TO OSINT INTELLIGENCE BOT</b> ⚡\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>User:</b> {first_name}\n"
            "👑 <b>Owner:</b> @Kya_Karega_Jaanke\n"
            "⚡ <b>Status:</b> Active 🟢\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Fast, reliable & real-time lookup system.</i>\n\n"
            "👇 <b>Select an option from the menu below:</b>",
        ),
        (
            "welcome_media",
            "https://media.giphy.com/media/3oKIPnAiaMCws8nOsE/giphy.gif",
        ),
        ("refer_reward", "3"),
    ]
    for key, val in default_settings:
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, val),
        )

    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------
# DATABASE HELPER FUNCTIONS
# ---------------------------------------------------------
def add_force_channel(channel_id, channel_link):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO force_channels (channel_id, channel_link) VALUES (?, ?)",
        (str(channel_id), channel_link),
    )
    conn.commit()
    conn.close()


def get_force_channels():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_link FROM force_channels")
    rows = cursor.fetchall()
    conn.close()
    return rows


def clear_force_channels():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM force_channels")
    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


def get_setting(key):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""


def set_setting(key, value):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, credits, referred_by, is_admin, is_banned FROM users WHERE user_id = ?",
        (user_id,),
    )
    user = cursor.fetchone()
    conn.close()
    return user


def make_user_admin(target_user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (target_user_id,))
    exists = cursor.fetchone()
    
    if exists:
        cursor.execute(
            "UPDATE users SET is_admin = 1, credits = 999999 WHERE user_id = ?",
            (target_user_id,),
        )
    else:
        cursor.execute(
            "INSERT INTO users (user_id, username, credits, referred_by, is_admin, is_banned) VALUES (?, ?, ?, ?, ?, ?)",
            (target_user_id, "AdminUser", 999999, None, 1, 0),
        )
    conn.commit()
    conn.close()


def register_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, is_admin FROM users WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()
    
    if existing:
        if user_id == SUPER_ADMIN_ID or existing[1] == 1:
            cursor.execute("UPDATE users SET credits = 999999, is_admin = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
        conn.close()
        return False

    is_admin = 1 if user_id == SUPER_ADMIN_ID else 0
    initial_credits = 999999 if is_admin else 5

    cursor.execute(
        "INSERT INTO users (user_id, username, credits, referred_by, is_admin, is_banned) VALUES (?, ?, ?, ?, ?, 0)",
        (user_id, username, initial_credits, referrer_id, is_admin),
    )

    if referrer_id and referrer_id != user_id:
        reward = int(get_setting("refer_reward") or 3)
        cursor.execute(
            "UPDATE users SET credits = credits + ? WHERE user_id = ?",
            (reward, referrer_id),
        )
        send_message(
            referrer_id,
            f"🎉 <b>New Referral!</b>\nA user joined via your link. <b>+{reward} Credits</b> added!",
        )

    conn.commit()
    conn.close()
    return True


def update_credits(user_id, amount):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id = ?",
        (amount, user_id),
    )
    conn.commit()
    conn.close()


def add_redeem_code(code, credits, max_uses=100):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO redeem_codes (code, credits, max_uses) VALUES (?, ?, ?)",
        (code.upper(), credits, max_uses),
    )
    conn.commit()
    conn.close()


def process_redeem_code(user_id, code):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    code = code.upper()
    cursor.execute(
        "SELECT credits, max_uses FROM redeem_codes WHERE code = ?", (code,)
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False, "❌ Invalid Redeem Code!"

    credits_to_add, max_uses = row[0], row[1]

    cursor.execute(
        "SELECT COUNT(*) FROM claimed_codes WHERE code = ?", (code,)
    )
    claimed_count = cursor.fetchone()[0]

    if claimed_count >= max_uses:
        conn.close()
        return False, f"🚫 <b>Code Expired!</b> Limit reached."

    cursor.execute(
        "SELECT 1 FROM claimed_codes WHERE user_id = ? AND code = ?",
        (user_id, code),
    )
    if cursor.fetchone():
        conn.close()
        return False, "⚠️ You have already redeemed this code!"

    cursor.execute(
        "INSERT INTO claimed_codes (user_id, code) VALUES (?, ?)",
        (user_id, code),
    )
    cursor.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id = ?",
        (credits_to_add, user_id),
    )

    conn.commit()
    conn.close()
    return True, f"🎉 <b>Success!</b> Received <b>+{credits_to_add} Credits</b>!"


# ---------------------------------------------------------
# DUMMY HTTP SERVER (Keeping Bot Awake 24/7)
# ---------------------------------------------------------
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))

    class DummyHandler(http.server.SimpleHTTPRequestHandler):

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Bot Server Active & Running 24/7!")

        def log_message(self, format, *args):
            return

    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", port), DummyHandler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")


# ---------------------------------------------------------
# TELEGRAM API HELPERS
# ---------------------------------------------------------
def check_user_joined_all(user_id):
    channels = get_force_channels()
    if not channels:
        return True

    url = f"{TELEGRAM_API_BASE}/getChatMember"

    for ch_id, ch_link in channels:
        payload = {"chat_id": ch_id, "user_id": user_id}
        try:
            res = requests.post(url, json=payload, timeout=5).json()
            if res.get("ok"):
                status = res["result"].get("status", "")
                if status not in ["creator", "administrator", "member"]:
                    return False
            else:
                return False
        except Exception:
            return False
    return True


def send_force_join_msg(chat_id):
    channels = get_force_channels()
    keyboard = []

    for idx, (ch_id, ch_link) in enumerate(channels, 1):
        keyboard.append([{"text": f"📢 Join Channel {idx}", "url": ch_link}])

    keyboard.append([{"text": "✅ Verify / Joined", "callback_data": "check_join"}])

    markup = {"inline_keyboard": keyboard}
    send_message(
        chat_id,
        "⚠️ <b>Access Denied!</b>\n\nBot use karne ke liye pehle niche diye gaye sabhi channels join karein:",
        reply_markup=markup,
    )


def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    if not BOT_TOKEN or BOT_TOKEN == "YAHAN_BOT_TOKEN_DAALEIN":
        return None

    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None


def send_welcome_media(chat_id, text, reply_markup=None):
    media_url = get_setting("welcome_media")
    parse_mode = "HTML"

    if not media_url:
        return send_message(chat_id, text, reply_markup=reply_markup)

    is_video = media_url.endswith(".mp4")
    endpoint = "sendAnimation" if not is_video else "sendVideo"
    field_name = "animation" if not is_video else "video"

    url = f"{TELEGRAM_API_BASE}/{endpoint}"
    payload = {
        "chat_id": chat_id,
        field_name: media_url,
        "caption": text,
        "parse_mode": parse_mode,
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload, timeout=15)
        res_json = response.json()
        if not res_json.get("ok"):
            return send_message(chat_id, text, reply_markup=reply_markup)
        return res_json
    except Exception:
        return send_message(chat_id, text, reply_markup=reply_markup)


def delete_message(chat_id, message_id):
    url = f"{TELEGRAM_API_BASE}/deleteMessage"
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error deleting message: {e}")


def send_auto_delete_message(chat_id, text, delay=30, reply_markup=None):
    res = send_message(chat_id, text, reply_markup=reply_markup)
    if res and res.get("ok"):
        msg_id = res["result"]["message_id"]

        def delete_task():
            time.sleep(delay)
            delete_message(chat_id, msg_id)

        threading.Thread(target=delete_task, daemon=True).start()


def answer_callback_query(callback_query_id, text=""):
    url = f"{TELEGRAM_API_BASE}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error answering callback query: {e}")


def get_updates(offset=None):
    if not BOT_TOKEN or BOT_TOKEN == "YAHAN_BOT_TOKEN_DAALEIN":
        return None

    url = f"{TELEGRAM_API_BASE}/getUpdates"
    params = {"timeout": 30, "offset": offset}

    try:
        response = requests.get(url, params=params, timeout=35)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error getting updates: {e}")

    return None


# ---------------------------------------------------------
# VALIDATION HELPERS
# ---------------------------------------------------------
def get_country_from_phone(phone_str):
    clean = "".join(filter(str.isdigit, str(phone_str)))
    if clean.startswith("91"):
        return "India 🇮🇳"
    elif clean.startswith("1"):
        return "United States / Canada 🇺🇸/🇨🇦"
    elif clean.startswith("44"):
        return "United Kingdom 🇬🇧"
    elif clean.startswith("92"):
        return "Pakistan 🇵🇰"
    elif clean.startswith("880"):
        return "Bangladesh 🇧🇩"
    elif clean.startswith("971"):
        return "United Arab Emirates 🇦🇪"
    elif clean.startswith("966"):
        return "Saudi Arabia 🇸🇦"
    elif clean.startswith("49"):
        return "Germany 🇩🇪"
    elif clean.startswith("33"):
        return "France 🇫🇷"
    elif clean.startswith("7"):
        return "Russia 🇷🇺"
    elif clean.startswith("55"):
        return "Brazil 🇧🇷"
    elif clean.startswith("52"):
        return "Mexico 🇲🇽"
    elif clean.startswith("81"):
        return "Japan 🇯🇵"
    elif clean.startswith("86"):
        return "China 🇨🇳"
    else:
        return "International / Global 🌐"


def is_virtual_or_fake_number(phone_str):
    clean = "".join(filter(str.isdigit, str(phone_str)))
    if len(clean) < 7 or len(clean) > 15:
        return True
    
    virtual_prefixes = ["800", "888", "877", "866", "855", "844", "833", "500"]
    for pre in virtual_prefixes:
        if clean.startswith(pre):
            return True
            
    if len(set(clean)) <= 2 and len(clean) > 5:
        return True
        
    return False


# ---------------------------------------------------------
# API LOOKUP FUNCTIONS
# ---------------------------------------------------------
def fetch_phone_data(phone_number):
    clean_num = "".join(filter(str.isdigit, str(phone_number)))
    if len(clean_num) == 10:
        clean_num = "91" + clean_num

    base_endpoint = EXTERNAL_API_URL.split("?")[0]
    target_url = f"{base_endpoint}?number={clean_num}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
        return {"status": "Error", "message": f"Server Error ({response.status_code})"}
    except Exception as e:
        return {"status": "Error", "message": f"Connection timed out: {str(e)}"}


def fetch_tg_to_num_data(tg_input):
    clean_input = tg_input.replace("@", "").strip()

    if not clean_input.isdigit():
        return {
            "status": "Invalid",
            "message": "❌ <b>Invalid ID!</b> Kripya sirf <b>Numeric Telegram ID</b> bhejein.",
        }

    target_url = EXTERNAL_TG_API_URL.format(value=clean_input)

    try:
        response = requests.get(target_url, timeout=20)
        if response.status_code == 200:
            data = response.json()
            phone = None
            username = "N/A"

            if isinstance(data, dict):
                phone = data.get("phone") or data.get("number") or data.get("result") or data.get("mobile") or data.get("phone_number")
                username = data.get("username", "N/A")
            elif isinstance(data, str) and len(data) > 5:
                phone = data

            if not phone:
                return {
                    "status": "Error",
                    "message": f"❌ Target ID <code>{clean_input}</code> ka real phone record database me nahi mila.",
                }

            phone_str = str(phone).strip()
            
            if is_virtual_or_fake_number(phone_str):
                return {
                    "status": "Error",
                    "message": f"🚫 <b>Lookup Blocked!</b> Target ID <code>{clean_input}</code> ka number ek <b>Virtual/Fake number</b> detect hua hai.",
                }

            country_name = get_country_from_phone(phone_str)

            return {
                "status": "Success",
                "telegram_id": clean_input,
                "username": username,
                "phone_number": f"+{phone_str}" if not phone_str.startswith("+") else phone_str,
                "country": country_name,
            }
            
        return {"status": "Error", "message": "⚠️ API Server Error! Target record fetch nahi ho saka."}
    except Exception as e:
        return {"status": "Error", "message": f"⚠️ Connection Error: {str(e)}"}


# ---------------------------------------------------------
# MESSAGE HANDLING LOGIC
# ---------------------------------------------------------
def handle_message(update):
    global BOT_ACTIVE

    if "callback_query" in update:
        if not BOT_ACTIVE:
            return
        query_id = update["callback_query"]["id"]
        chat_id = update["callback_query"]["message"]["chat"]["id"]
        data = update["callback_query"].get("data", "")

        if data == "check_join":
            if check_user_joined_all(chat_id):
                answer_callback_query(query_id, "✅ Verified! Send /start")
                send_message(chat_id, "🎉 Verified successfully! Click /start to continue.")
            else:
                answer_callback_query(query_id, "❌ Aapne abhi tak sabhi channels join nahi kiye hain!")
        return

    if "message" not in update:
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    username = message["chat"].get("username", "User")
    first_name = message["chat"].get("first_name", "Friend")

    is_admin = 1 if chat_id == SUPER_ADMIN_ID else 0
    user = get_user(chat_id)
    if user and len(user) > 3 and user[3] == 1:
        is_admin = 1

    # --- BOT ON / OFF CONTROLS (Admin Only) ---
    if text == "/botoff" and is_admin:
        BOT_ACTIVE = False
        send_message(chat_id, "🔴 <b>Bot is now OFF.</b> Saare users ke liye bot pause kar diya gaya hai. Koi response nahi diya jayega jab tak <code>/boton</code> na bhejein.")
        return

    if text == "/boton" and is_admin:
        BOT_ACTIVE = True
        send_message(chat_id, "🟢 <b>Bot is now ON!</b> Bot normal state me aa chuka hai aur fully operational hai.")
        return

    if not BOT_ACTIVE:
        return

    # Check Force Sub Channels for New/All Users
    if not is_admin and not check_user_joined_all(chat_id):
        send_force_join_msg(chat_id)
        return

    # Keyboard Layout
    keyboard_buttons = [
        [{"text": "📱 Phone Lookup"}, {"text": "👤 TG to Number"}],
        [{"text": "🎁 Refer & Earn"}, {"text": "💳 My Balance"}],
        [{"text": "🎟️ Redeem Code"}],
    ]
    if is_admin:
        keyboard_buttons.append([{"text": "⚡ Admin Panel"}])

    # --- ADMIN PANEL & COMMANDS ---
    if text == "⚡ Admin Panel" and is_admin:
        channels = get_force_channels()
        ch_text = "\n".join([f"• ID: <code>{c[0]}</code> | Link: {c[1]}" for c in channels]) if channels else "None"

        admin_info = (
            f"👑 <b>Admin Control Panel</b>\n\n"
            f"<b>📌 Active Force-Join Channels:</b>\n{ch_text}\n\n"
            f"<b>⚙️ Admin Commands:</b>\n"
            f"• <code>/botoff</code> - Turn off bot responses\n"
            f"• <code>/boton</code> - Turn on bot responses\n"
            f"• <code>/setwelcomemsg <TEXT></code> - Set Welcome text\n"
            f"• <code>/setgif</code> - Set Welcome MP4 Video link\n"
            f"• <code>/addchannel <CHANNEL_ID> <CHANNEL_LINK></code>\n"
            f"• <code>/clearchannels</code> - Remove all channels\n"
            f"• <code>/createcode <CODE> <CREDITS> <LIMIT></code>\n"
            f"• <code>/makeadmin <USER_ID></code> - Promote user to Admin\n"
            f"• <code>/broadcast <MESSAGE></code> - Send DM to all users"
        )
        send_message(chat_id, admin_info)
        return

    # Set Welcome Message Text Command
    elif text.startswith("/setwelcomemsg") and is_admin:
        new_msg = text.replace("/setwelcomemsg", "").strip()
        if new_msg:
            set_setting("welcome_msg", new_msg)
            send_message(chat_id, "✅ <b>Welcome message successfully updated!</b>")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/setwelcomemsg Your custom text here...</code>")
        return

    # --- /setgif COMMAND (Asks for MP4 video link) ---
    elif text == "/setgif" and is_admin:
        send_message(chat_id, "🎬 <b>Welcome MP4 Video Link bhejein:</b>\n(Kripya koi valid .mp4 video link ya GIF/Video URL bhejein)")
        user_states[chat_id] = "awaiting_setgif_link"
        return

    elif user_states.get(chat_id) == "awaiting_setgif_link" and is_admin:
        new_media = text.strip()
        if new_media.startswith("http"):
            set_setting("welcome_media", new_media)
            send_message(chat_id, "✅ <b>Welcome MP4 Video / Media successfully update ho gaya hai!</b> 🎉")
        else:
            send_message(chat_id, "❌ <b>Invalid Link!</b> Kripya ek valid URL bhejein.")
        user_states[chat_id] = None
        return

    elif text.startswith("/addchannel") and is_admin:
        parts = text.split(maxsplit=2)
        if len(parts) == 3 and parts[2].startswith("http"):
            ch_id, ch_link = parts[1], parts[2]
            add_force_channel(ch_id, ch_link)
            send_message(chat_id, f"✅ <b>Channel Added Successfully!</b>\nLink: {ch_link}")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/addchannel <channel_id> <channel_link></code>")
        return

    elif text == "/clearchannels" and is_admin:
        clear_force_channels()
        send_message(chat_id, "✅ <b>All Force-Sub channels cleared!</b>")
        return

    elif text.startswith("/createcode") and is_admin:
        parts = text.split()
        if len(parts) >= 3 and parts[2].isdigit():
            code_str = parts[1].upper()
            cred_amt = int(parts[2])
            limit_amt = int(parts[3]) if (len(parts) > 3 and parts[3].isdigit()) else 100
            add_redeem_code(code_str, cred_amt, limit_amt)
            send_message(chat_id, f"✅ <b>Redeem Code Created!</b>\nCode: <code>{code_str}</code> (+{cred_amt} Credits)")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/createcode OFFER50 50 100</code>")
        return

    elif text.startswith("/makeadmin") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
            make_user_admin(target_id)
            
            send_message(chat_id, f"✅ User <code>{target_id}</code> ko successfully <b>Admin</b> bana diya gaya hai!")
            
            admin_notify_msg = (
                "🎉 <b>CONGRATULATIONS!</b> 🎉\n\n"
                "👑 You are now an <b>Admin</b> of this bot!\n"
                "🛡️ <b>Role:</b> Administrator\n"
                "💳 <b>Credits:</b> ∞ Unlimited\n"
            )
            send_message(target_id, admin_notify_msg)
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/makeadmin <USER_ID></code>")
        return

    elif text.startswith("/broadcast") and is_admin:
        broadcast_msg = text.replace("/broadcast", "").strip()
        if not broadcast_msg:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/broadcast Your message here...</code>")
            return

        all_users = get_all_users()
        send_message(chat_id, f"🚀 <b>Broadcast started!</b> Sending to {len(all_users)} users...")

        def run_broadcast():
            success_count = 0
            fail_count = 0
            for uid in all_users:
                res = send_message(uid, f"📢 <b>Broadcast Message:</b>\n\n{broadcast_msg}")
                if res and res.get("ok"):
                    success_count += 1
                else:
                    fail_count += 1
                time.sleep(0.05)

            send_message(
                chat_id,
                f"✅ <b>Broadcast Completed!</b>\n\n"
                f"🟢 Success: {success_count}\n"
                f"🔴 Failed/Blocked: {fail_count}"
            )

        threading.Thread(target=run_broadcast, daemon=True).start()
        return

    # --- COMMAND: /start ---
    if text.startswith("/start"):
        referrer_id = None
        parts = text.split()
        if len(parts) > 1 and parts[1].startswith("REF_"):
            try:
                referrer_id = int(parts[1].replace("REF_", ""))
            except ValueError:
                referrer_id = None

        register_user(chat_id, username, referrer_id)
        
        curr_user = get_user(chat_id)
        is_current_admin = 1 if (chat_id == SUPER_ADMIN_ID or (curr_user and curr_user[3] == 1)) else 0

        keyboard_buttons = [
            [{"text": "📱 Phone Lookup"}, {"text": "👤 TG to Number"}],
            [{"text": "🎁 Refer & Earn"}, {"text": "💳 My Balance"}],
            [{"text": "🎟️ Redeem Code"}],
        ]
        if is_current_admin:
            keyboard_buttons.append([{"text": "⚡ Admin Panel"}])

        dynamic_keyboard = {
            "keyboard": keyboard_buttons,
            "resize_keyboard": True,
        }

        msg_template = get_setting("welcome_msg")
        welcome_text = msg_template.format(first_name=first_name)
        
        # Send Welcome Media along with text
        send_welcome_media(chat_id, welcome_text, reply_markup=dynamic_keyboard)
        return

    elif text == "💳 My Balance":
        user_data = get_user(chat_id)
        credits = "∞ Unlimited" if is_admin else (user_data[1] if user_data else 0)
        send_message(chat_id, f"💳 <b>Credits Balance:</b> {credits}")
        return

    elif text == "🎁 Refer & Earn":
        ref_reward = get_setting("refer_reward") or "3"
        ref_link = f"https://t.me/{BOT_USERNAME}?start=REF_{chat_id}"
        send_message(chat_id, f"🎁 <b>Refer & Earn:</b>\n<code>{ref_link}</code>\n\nGet +{ref_reward} credits per referral!")
        return

    elif text == "🎟️ Redeem Code":
        send_message(chat_id, "🎟️ <b>Send your Redeem Code below:</b>")
        user_states[chat_id] = "awaiting_redeem_code"
        return

    elif user_states.get(chat_id) == "awaiting_redeem_code":
        success, res_msg = process_redeem_code(chat_id, text)
        send_message(chat_id, res_msg)
        user_states[chat_id] = None
        return

    # --- FEATURE: STRICT TG TO NUMBER ---
    elif text == "👤 TG to Number":
        send_message(chat_id, "👤 <b>Send Target Telegram User ID:</b> (e.g., <code>123456789</code>)")
        user_states[chat_id] = "awaiting_tg_lookup"
        return

    elif user_states.get(chat_id) == "awaiting_tg_lookup":
        send_message(chat_id, f"🔍 <b>Scanning strict records for ID:</b> <code>{text}</code>...")
        res = fetch_tg_to_num_data(text)

        if res.get("status") == "Success":
            if not is_admin:
                update_credits(chat_id, -1)

            result_msg = (
                f"🎯 <b>TARGET RECORD FOUND SUCCESSFULLY!</b>\n\n"
                f"👤 <b>Telegram ID:</b> <code>{res['telegram_id']}</code>\n"
                f"🔗 <b>Username:</b> @{res['username']}\n"
                f"📞 <b>Phone Number:</b> <code>{res['phone_number']}</code>\n"
                f"🌍 <b>Country:</b> {res['country']}\n\n"
                f"⏳ <i>Auto-deleting message in 30 seconds.</i>"
            )
            send_auto_delete_message(chat_id, result_msg, delay=30)
        else:
            send_message(chat_id, res.get("message"))

        user_states[chat_id] = None
        return

    # --- FEATURE: PHONE LOOKUP & OWNER PROTECTION ---
    elif text == "📱 Phone Lookup":
        send_message(chat_id, "📞 <b>Send Target Mobile Number:</b> (e.g. <code>9876543210</code>)")
        user_states[chat_id] = "awaiting_phone_number"
        return

    elif user_states.get(chat_id) == "awaiting_phone_number":
        clean_text = text.replace("+", "").strip()

        if clean_text.endswith(OWNER_PHONE_NUMBER):
            send_message(chat_id, "Don't try to be oversmart that's my owner 😎🔥")
            user_states[chat_id] = None
            return

        send_message(chat_id, f"🔍 Searching details for: {text}...")
        if not is_admin:
            update_credits(chat_id, -1)

        api_data = fetch_phone_data(text)
        info_msg = (
            f"📞 <b>Exact Details for:</b> <code>{text}</code>\n\n"
            f"<pre>{json.dumps(api_data, indent=2, ensure_ascii=False)}</pre>\n\n"
            f"⏳ <i>Auto-deleting in 30 seconds!</i>"
        )
        send_auto_delete_message(chat_id, info_msg, delay=30)
        user_states[chat_id] = None
        return


def main():
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()

    print("Bot starting continuous polling loop (Always Awake Mode with Interactive /setgif)...")
    offset = None

    while True:
        try:
            updates = get_updates(offset)
            if updates and updates.get("ok"):
                results = updates.get("result", [])
                for update in results:
                    offset = update["update_id"] + 1
                    handle_message(update)
        except Exception as e:
            print(f"Polling Exception: {e}")

        time.sleep(0.1)


if __name__ == "__main__":
    main()
