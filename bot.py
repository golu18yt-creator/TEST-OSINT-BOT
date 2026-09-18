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
            
    if len(set(clean))
