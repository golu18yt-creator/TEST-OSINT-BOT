import http.server
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
BOT_USERNAME = os.environ.get(
    "BOT_USERNAME", "Tera_Osint_44bot"
)  # Without @ symbol
EXTERNAL_API_URL = os.environ.get(
    "EXTERNAL_API_URL",
    "https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup",
)

# Yahan apna Telegram User ID daalein (Main Admin)
SUPER_ADMIN_ID = 8927308711

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
user_states = {}
BOT_ACTIVE = True


# ---------------------------------------------------------
# DATABASE SETUP (SQLite)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Users table
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

    # Settings table for Dynamic Config
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Default Settings Insert
    default_settings = [
        ("welcome_msg", "✨ <b>WELCOME TO LOOKUP BOT</b> ✨\n\nHello {first_name}! 👋\nWelcome to fast & reliable lookup system."),
        ("welcome_gif", ""),  # Optional GIF Direct Link
        ("refer_reward", "3")
    ]
    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()


init_db()


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
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
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


def register_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
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


def set_admin_role(user_id, status=1):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_admin = ? WHERE user_id = ?", (status, user_id)
    )
    conn.commit()
    conn.close()


def set_ban_status(user_id, status=1):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_banned = ? WHERE user_id = ?", (status, user_id)
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------
# DUMMY HTTP SERVER
# ---------------------------------------------------------
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))

    class DummyHandler(http.server.SimpleHTTPRequestHandler):

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Bot Server Active!")

        def log_message(self, format, *args):
            return

    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", port), DummyHandler) as httpd:
            print(f"Dummy HTTP Server running on port {port}...")
            httpd.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")


# ---------------------------------------------------------
# TELEGRAM API HELPERS (MESSAGE & ANIMATION)
# ---------------------------------------------------------
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


def send_animation(chat_id, animation_url, caption="", reply_markup=None, parse_mode="HTML"):
    if not BOT_TOKEN or BOT_TOKEN == "YAHAN_BOT_TOKEN_DAALEIN":
        return None

    url = f"{TELEGRAM_API_BASE}/sendAnimation"
    payload = {
        "chat_id": chat_id,
        "animation": animation_url,
        "caption": caption,
        "parse_mode": parse_mode
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending animation: {e}")
        return None


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
# EXTERNAL API HELPER
# ---------------------------------------------------------
def fetch_phone_data(phone_number):
    target_url = f"{EXTERNAL_API_URL}?number={phone_number}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        if response.status_code == 200:
            try:
                return response.json()
            except Exception:
                return {"response": response.text}
        else:
            try:
                return {
                    "http_code": response.status_code,
                    "error_details": response.json(),
                }
            except Exception:
                return {
                    "http_code": response.status_code,
                    "raw_response": response.text[:300],
                }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------
# MESSAGE HANDLING LOGIC
# ---------------------------------------------------------
def handle_message(update):
    global BOT_ACTIVE
    if "message" not in update:
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    username = message["chat"].get("username", "User")
    first_name = message["chat"].get("first_name", "Friend")

    user = get_user(chat_id)
    is_admin = user[3] if user else (1 if chat_id == SUPER_ADMIN_ID else 0)
    is_banned = user[4] if user else 0

    if is_banned:
        send_message(chat_id, "❌ <b>Access Denied!</b> You are banned from using this bot.")
        return

    if not BOT_ACTIVE and not is_admin:
        send_message(chat_id, "⚠️ <b>Bot Under Maintenance!</b> Please try again later.")
        return

    keyboard_buttons = [
        [{"text": "📱 Phone Lookup"}, {"text": "🎁 Refer & Earn"}],
        [{"text": "💳 My Balance"}],
    ]
    if is_admin:
        keyboard_buttons.append([{"text": "⚡ Admin Panel"}])

    reply_keyboard = {
        "keyboard": keyboard_buttons,
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

    # --- DYNAMIC ADMIN CONFIG COMMANDS ---
    if text.startswith("/setmsg") and is_admin:
        new_msg = text.replace("/setmsg", "").strip()
        if new_msg:
            set_setting("welcome_msg", new_msg)
            send_message(chat_id, "✅ <b>Welcome Message Updated!</b>")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/setmsg Your Welcome Text Here</code>")
        return

    elif text.startswith("/setgif") and is_admin:
        gif_url = text.replace("/setgif", "").strip()
        if gif_url:
            set_setting("welcome_gif", gif_url)
            send_message(chat_id, "✅ <b>Welcome GIF URL Updated!</b>")
        else:
            set_setting("welcome_gif", "")
            send_message(chat_id, "✅ <b>GIF Removed!</b> Welcome message will be sent as text.")
        return

    elif text.startswith("/setref") and is_admin:
        val = text.replace("/setref", "").strip()
        if val.isdigit():
            set_setting("refer_reward", val)
            send_message(chat_id, f"✅ <b>Referral Reward Updated to {val} Credits!</b>")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/setref 5</code>")
        return

    # --- BOT CONTROL COMMANDS ---
    elif text == "/boton" and is_admin:
        BOT_ACTIVE = True
        send_message(chat_id, "🟢 <b>Bot is now ONLINE!</b>")
        return

    elif text == "/botoff" and is_admin:
        BOT_ACTIVE = False
        send_message(chat_id, "🔴 <b>Bot is now OFFLINE!</b>")
        return

    elif text.startswith("/ban") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
            if target_id == chat_id:
                send_message(chat_id, "❌ You cannot ban yourself!")
                return
            set_ban_status(target_id, 1)
            send_message(chat_id, f"🚫 <b>User Banned:</b> <code>{target_id}</code>")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/ban <user_id></code>")
        return

    elif text.startswith("/unban") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
            set_ban_status(target_id, 0)
            send_message(chat_id, f"✅ <b>User Unbanned:</b> <code>{target_id}</code>")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/unban <user_id></code>")
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

        msg_template = get_setting("welcome_msg")
        gif_url = get_setting("welcome_gif")
        welcome_text = msg_template.format(first_name=first_name)

        if gif_url:
            send_animation(chat_id, gif_url, caption=welcome_text, reply_markup=reply_keyboard)
        else:
            send_message(chat_id, welcome_text, reply_markup=reply_keyboard)
        user_states[chat_id] = None

    elif text.startswith("/addcredits") and is_admin:
        parts = text.split()
        if len(parts) == 3 and parts[1].isdigit():
            target_id = int(parts[1])
            try:
                amt = int(parts[2])
                update_credits(target_id, amt)
                send_message(chat_id, f"✅ Added <b>{amt} Credits</b> to <code>{target_id}</code>")
            except ValueError:
                send_message(chat_id, "❌ Invalid amount!")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/addcredits <user_id> <amount></code>")

    elif text.startswith("/makeadmin") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
            set_admin_role(target_id, 1)
            send_message(chat_id, f"👑 User <code>{target_id}</code> is now Admin.")
        else:
            send_message(chat_id, "⚠️ <b>Usage:</b> <code>/makeadmin <user_id></code>")

    elif text == "⚡ Admin Panel" and is_admin:
        status_text = "🟢 ONLINE" if BOT_ACTIVE else "🔴 OFFLINE"
        ref_rew = get_setting("refer_reward") or "3"
        current_gif = get_setting("welcome_gif") or "None"
        
        admin_info = (
            f"👑 <b>Admin Control Panel</b>\n"
            f"• Status: <b>{status_text}</b>\n"
            f"• Referral Reward: <b>{ref_rew} Credits</b>\n"
            f"• GIF URL: <code>{current_gif}</code>\n\n"
            "<b>Dynamic Customization Commands:</b>\n"
            "• <code>/setmsg <text></code> - Change Welcome Text\n"
            "• <code>/setgif <url></code> - Set Welcome Anime GIF URL\n"
            "• <code>/setref <number></code> - Change Referral Reward Credits\n\n"
            "<b>Management Commands:</b>\n"
            "• <code>/botoff</code> / <code>/boton</code> - Toggle Bot State\n"
            "• <code>/ban <id></code> / <code>/unban <id></code> - Manage Users\n"
            "• <code>/addcredits <id> <amt></code> - Add Credits"
        )
        send_message(chat_id, admin_info)

    elif text == "💳 My Balance":
        user_data = get_user(chat_id)
        credits = user_data[1] if user_data else 0
        role = "👑 Admin" if is_admin else "👤 Member"
        msg = f"💳 <b>Account Summary</b>\n\n• <b>Role:</b> {role}\n• <b>Credits:</b> {credits}"
        send_message(chat_id, msg)

    elif text == "🎁 Refer & Earn":
        ref_reward = get_setting("refer_reward") or "3"
        ref_link = f"https://t.me/{BOT_USERNAME}?start=REF_{chat_id}"
        msg = f"🎁 <b>Referral Link:</b>\n<code>{ref_link}</code>\n\nGet +{ref_reward} credits per friend!"
        send_message(chat_id, msg)

    elif text == "📱 Phone Lookup":
        user_data = get_user(chat_id)
        credits = user_data[1] if user_data else 0

        if credits < 1:
            send_message(chat_id, "❌ <b>Out of Credits!</b> Use 🎁 Refer & Earn.")
            return

        send_message(chat_id, f"📞 Send 10-digit mobile number:\n<i>(Balance: {credits})</i>")
        user_states[chat_id] = "awaiting_phone_number"

    elif user_states.get(chat_id) == "awaiting_phone_number":
        user_data = get_user(chat_id)
        credits = user_data[1] if user_data else 0

        if credits < 1:
            send_message(chat_id, "❌ Out of credits!")
            user_states[chat_id] = None
            return

        if text.isdigit() and len(text) == 10:
            send_message(chat_id, "🔍 Searching details...")
            update_credits(chat_id, -1)

            api_data = fetch_phone_data(text)
            formatted_json = json.dumps(api_data, indent=2)
            send_message(chat_id, f"<pre>{formatted_json}</pre>")
            user_states[chat_id] = None
        else:
            send_message(chat_id, "❌ Send valid 10-digit number.")

    else:
        send_message(chat_id, "Please select an option.", reply_markup=reply_keyboard)


# ---------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------
def main():
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()

    print("Bot starting polling loop...")
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

        time.sleep(0.5)


if __name__ == "__main__":
    main()
