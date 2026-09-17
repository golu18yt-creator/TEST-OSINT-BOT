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
OWNER_PHONE_NUMBER = "8595900496"  # Apna 10-digit mobile number daalein

EXTERNAL_API_URL = os.environ.get(
    "EXTERNAL_API_URL",
    "https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup",
)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
user_states = {}
temp_lookup_data = {}
BOT_ACTIVE = True


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

    # Permanent purge for old channel settings
    cursor.execute("DELETE FROM settings WHERE key IN ('force_channel', 'force_channel_link')")

    default_settings = [
        (
            "welcome_msg",
            "⚡ <b>WELCOME TO OSINT INTELLIGENCE BOT</b> ⚡\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 <b>User:</b> {first_name}\n"
            "👑 <b>Owner:</b> @Kya_Karega_Jaanke\n"
            "⚡ <b>Status:</b> Active 🟢\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Fast, reliable & real-time phone number lookup system.</i>\n\n"
            "👇 <b>Select an option from the menu below:</b>",
        ),
        ("welcome_gif", ""),
        ("refer_reward", "3"),
        ("force_channel", ""),
        ("force_channel_link", ""),
    ]
    for key, val in default_settings:
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, val),
        )

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
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def clear_force_channel():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM settings WHERE key IN ('force_channel', 'force_channel_link')")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('force_channel', '')")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('force_channel_link', '')")
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
        return (
            False,
            f"🚫 <b>Code Expired!</b>\nReached limit of {max_uses} users.",
        )

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
    return (
        True,
        f"🎉 <b>Success!</b> Received <b>+{credits_to_add} Credits</b>!\n"
        f"<i>({claimed_count + 1}/{max_uses} users claimed)</i>",
    )


# ---------------------------------------------------------
# DUMMY HTTP SERVER (Render Web Service Fix)
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
            print(f"Server active on port {port}...")
            httpd.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")


# ---------------------------------------------------------
# TELEGRAM API HELPERS
# ---------------------------------------------------------
def get_owner_profile_media():
    url = f"{TELEGRAM_API_BASE}/getUserProfilePhotos"
    payload = {"user_id": SUPER_ADMIN_ID, "limit": 1}
    try:
        res = requests.post(url, json=payload, timeout=10).json()
        if res.get("ok") and res["result"]["total_count"] > 0:
            photo_sizes = res["result"]["photos"][0]
            best_quality = photo_sizes[-1]
            file_id = best_quality["file_id"]

            file_info_url = f"{TELEGRAM_API_BASE}/getFile"
            file_res = requests.post(
                file_info_url, json={"file_id": file_id}, timeout=10
            ).json()
            if file_res.get("ok"):
                file_path = file_res["result"].get("file_path", "")
                if file_path.endswith(".mp4"):
                    return {"type": "animation", "file_id": file_id}

            return {"type": "photo", "file_id": file_id}
    except Exception as e:
        print(f"Error fetching owner profile media: {e}")
    return None


def is_user_channel_member(user_id, channel_id):
    if not channel_id or channel_id.strip() == "":
        return True

    url = f"{TELEGRAM_API_BASE}/getChatMember"
    payload = {"chat_id": channel_id, "user_id": user_id}

    try:
        res = requests.post(url, json=payload, timeout=10).json()
        if res.get("ok"):
            status = res["result"]["status"]
            return status in ["creator", "administrator", "member"]
    except Exception as e:
        print(f"Error checking channel member: {e}")

    return False


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


def send_document(chat_id, file_bytes, filename, caption=""):
    url = f"{TELEGRAM_API_BASE}/sendDocument"
    files = {"document": (filename, file_bytes, "application/json")}
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"Error sending document: {e}")


def send_photo(
    chat_id, photo, caption="", reply_markup=None, parse_mode="HTML"
):
    url = f"{TELEGRAM_API_BASE}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": parse_mode,
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending photo: {e}")
        return None


def send_animation(
    chat_id, animation_url, caption="", reply_markup=None, parse_mode="HTML"
):
    url = f"{TELEGRAM_API_BASE}/sendAnimation"
    payload = {
        "chat_id": chat_id,
        "animation": animation_url,
        "caption": caption,
        "parse_mode": parse_mode,
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Error sending animation: {e}")
        return None


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
# UPDATED API FETCH FUNCTION (With Auto Country Code)
# ---------------------------------------------------------
def fetch_phone_data(phone_number):
    clean_num = "".join(filter(str.isdigit, str(phone_number)))

    # Auto-add '91' prefix if 10-digit Indian number passed
    if len(clean_num) == 10:
        clean_num = "91" + clean_num

    base_endpoint = EXTERNAL_API_URL.split("?")[0]
    target_url = f"{base_endpoint}?number={clean_num}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    data.pop("credit", None)
                    data.pop("tag", None)

                    if not data or data.get("status") == "failed":
                        return {"status": "error", "message": "No information found for this number in OSINT database."}
                return data
            except Exception:
                return {"response": response.text}
        else:
            return {"status": "error", "message": f"Server Error ({response.status_code}). Try again later."}
    except Exception as e:
        return {"status": "error", "message": f"Connection timed out: {str(e)}"}


# ---------------------------------------------------------
# CALLBACK QUERY HANDLER
# ---------------------------------------------------------
def handle_callback_query(callback_query):
    query_id = callback_query["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    data = callback_query.get("data", "")

    if data.startswith("dl_json_"):
        phone_number = data.replace("dl_json_", "")
        json_data = temp_lookup_data.get(chat_id)

        if json_data:
            json_bytes = json.dumps(json_data, indent=4).encode("utf-8")
            file_stream = io.BytesIO(json_bytes)
            send_document(
                chat_id,
                file_stream,
                f"details_{phone_number}.json",
                f"📄 <b>Details File for {phone_number}</b>",
            )
            answer_callback_query(
                query_id, text="📥 JSON File sent successfully!"
            )
        else:
            answer_callback_query(
                query_id, text="⚠️ Data expired! Please search again."
            )


# ---------------------------------------------------------
# MESSAGE HANDLING LOGIC
# ---------------------------------------------------------
def handle_message(update):
    global BOT_ACTIVE

    if "callback_query" in update:
        handle_callback_query(update["callback_query"])
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

    is_banned = user[4] if (user and len(user) > 4) else 0

    if is_banned:
        send_message(
            chat_id,
            "❌ <b>Access Denied!</b> You are banned from using this bot.",
        )
        return

    if not BOT_ACTIVE and not is_admin:
        send_message(
            chat_id,
            "⚠️ <b>Bot Under Maintenance!</b> Please try again later.",
        )
        return

    keyboard_buttons = [
        [{"text": "📱 Phone Lookup"}, {"text": "🎁 Refer & Earn"}],
        [{"text": "💳 My Balance"}, {"text": "🎟️ Redeem Code"}],
    ]
    if is_admin:
        keyboard_buttons.append([{"text": "⚡ Admin Panel"}])

    reply_keyboard = {
        "keyboard": keyboard_buttons,
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

    # --- ADMIN PANEL ---
    if text == "⚡ Admin Panel" and is_admin:
        status_text = "🟢 ONLINE" if BOT_ACTIVE else "🔴 OFFLINE"
        ref_rew = get_setting("refer_reward") or "3"

        admin_info = (
            f"👑 <b>Admin Control Panel</b>\n"
            f"• Status: <b>{status_text}</b>\n"
            f"• Referral Reward: <b>{ref_rew} Credits</b>\n\n"
            "<b>⚙️ Admin Settings & Commands:</b>\n\n"
            "1️⃣ <b>Set Welcome Message:</b>\n"
            "• <code>/setmsg <text></code> - Customize Welcome Text\n"
            "• <code>/setgif <url></code> - Set Custom GIF URL\n\n"
            "2️⃣ <b>Make Redeem Code:</b>\n"
            "• <code>/createcode <CODE> <CREDITS> <LIMIT></code>\n\n"
            "3️⃣ <b>User Controls:</b>\n"
            "• <code>/makeadmin <USER_ID></code> | <code>/removeadmin <USER_ID></code>\n"
            "• <code>/botoff</code> | <code>/boton</code>\n"
            "• <code>/ban <id></code> | <code>/unban <id></code>\n"
            "• <code>/addcredits <id> <amt></code>"
        )
        send_message(chat_id, admin_info)
        return

    elif text.startswith("/makeadmin") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
            set_admin_role(target_id, 1)
            send_message(
                chat_id,
                f"👑 <b>New Admin Added!</b> User ID <code>{target_id}</code>.",
            )
        else:
            send_message(
                chat_id, "⚠️ <b>Usage:</b> <code>/makeadmin 1234567890</code>"
            )
        return

    elif text.startswith("/removeadmin") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            target_id = int(parts[1])
            set_admin_role(target_id, 0)
            send_message(
                chat_id,
                f"✅ <b>Admin Revoked!</b> User ID <code>{target_id}</code>.",
            )
        return

    elif text.startswith("/createcode") and is_admin:
        parts = text.split()
        if len(parts) >= 3 and parts[2].isdigit():
            code_str = parts[1].upper()
            cred_amt = int(parts[2])
            limit_amt = (
                int(parts[3])
                if (len(parts) > 3 and parts[3].isdigit())
                else 100
            )

            add_redeem_code(code_str, cred_amt, limit_amt)
            send_message(
                chat_id,
                f"✅ <b>Redeem Code Created!</b>\n\n"
                f"• <b>Code:</b> <code>{code_str}</code>\n"
                f"• <b>Credits:</b> +{cred_amt}\n"
                f"• <b>User Limit:</b> {limit_amt} Users",
            )
        else:
            send_message(
                chat_id,
                "⚠️ <b>Usage:</b> <code>/createcode OFFER50 50 100</code>",
            )
        return

    elif text.startswith("/setmsg") and is_admin:
        new_msg = text.replace("/setmsg", "").strip()
        if new_msg:
            set_setting("welcome_msg", new_msg)
            send_message(chat_id, "✅ <b>Welcome Message Updated!</b>")
        return

    elif text.startswith("/setgif") and is_admin:
        gif_url = text.replace("/setgif", "").strip()
        set_setting("welcome_gif", gif_url)
        send_message(
            chat_id, "✅ <b>Welcome GIF Updated!</b>" if gif_url else "✅ GIF Removed!"
        )
        return

    elif text.startswith("/setref") and is_admin:
        val = text.replace("/setref", "").strip()
        if val.isdigit():
            set_setting("refer_reward", val)
            send_message(
                chat_id, f"✅ <b>Referral Reward Updated to {val} Credits!</b>"
            )
        return

    elif text == "/boton" and is_admin:
        BOT_ACTIVE = True
        send_message(chat_id, "🟢 <b>Bot is ONLINE!</b>")
        return

    elif text == "/botoff" and is_admin:
        BOT_ACTIVE = False
        send_message(chat_id, "🔴 <b>Bot is OFFLINE!</b>")
        return

    elif text.startswith("/ban") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            set_ban_status(int(parts[1]), 1)
            send_message(chat_id, f"🚫 <b>User Banned:</b> <code>{parts[1]}</code>")
        return

    elif text.startswith("/unban") and is_admin:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            set_ban_status(int(parts[1]), 0)
            send_message(
                chat_id, f"✅ <b>User Unbanned:</b> <code>{parts[1]}</code>"
            )
        return

    elif text.startswith("/addcredits") and is_admin:
        parts = text.split()
        if len(parts) == 3 and parts[1].isdigit():
            update_credits(int(parts[1]), int(parts[2]))
            send_message(
                chat_id,
                f"✅ Added <b>{parts[2]} Credits</b> to <code>{parts[1]}</code>",
            )
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
        welcome_text = msg_template.format(
            first_name=first_name, owner_username=OWNER_USERNAME
        )

        owner_media = get_owner_profile_media()

        if gif_url:
            send_animation(
                chat_id,
                gif_url,
                caption=welcome_text,
                reply_markup=reply_keyboard,
            )
        elif owner_media:
            if owner_media["type"] == "animation":
                send_animation(
                    chat_id,
                    owner_media["file_id"],
                    caption=welcome_text,
                    reply_markup=reply_keyboard,
                )
            else:
                send_photo(
                    chat_id,
                    owner_media["file_id"],
                    caption=welcome_text,
                    reply_markup=reply_keyboard,
                )
        else:
            send_message(chat_id, welcome_text, reply_markup=reply_keyboard)

        user_states[chat_id] = None
        return

    elif text == "💳 My Balance":
        user_data = get_user(chat_id)
        credits = "∞ Unlimited" if is_admin else (user_data[1] if user_data else 0)
        role = "👑 Admin" if is_admin else "👤 Member"
        msg = f"💳 <b>Account Summary</b>\n\n• <b>Role:</b> {role}\n• <b>Credits:</b> {credits}"
        send_message(chat_id, msg)
        return

    elif text == "🎁 Refer & Earn":
        ref_reward = get_setting("refer_reward") or "3"
        ref_link = f"https://t.me/{BOT_USERNAME}?start=REF_{chat_id}"
        msg = f"🎁 <b>Referral Link:</b>\n<code>{ref_link}</code>\n\nGet +{ref_reward} credits per friend!"
        send_message(chat_id, msg)
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

    elif text == "📱 Phone Lookup":
        user_data = get_user(chat_id)
        credits = user_data[1] if user_data else 0

        if not is_admin and credits < 1:
            send_message(
                chat_id,
                "❌ <b>Out of Credits!</b> Use 🎁 Refer & Earn or 🎟️ Redeem Code.",
            )
            return

        bal_display = "∞ Unlimited" if is_admin else credits
        send_message(
            chat_id,
            f"📞 Send phone number (e.g., <code>9876543210</code> or <code>+919876543210</code>):\n<i>(Balance: {bal_display})</i>",
        )
        user_states[chat_id] = "awaiting_phone_number"
        return

    # --- LOOKUP LOGIC WITH COUNTRY CODE HANDLING ---
    elif (user_states.get(chat_id) == "awaiting_phone_number") or (text.replace("+", "").isdigit() and 10 <= len(text.replace("+", "")) <= 13):
        user_data = get_user(chat_id)
        credits = user_data[1] if user_data else 0

        if not is_admin and credits < 1:
            send_message(chat_id, "❌ <b>Out of credits!</b> Please earn or redeem credits to search.")
            user_states[chat_id] = None
            return

        clean_text = text.replace("+", "").strip()

        if clean_text.isdigit() and 10 <= len(clean_text) <= 13:
            if clean_text.endswith(OWNER_PHONE_NUMBER):
                roast_msg = (
                    "🤫 <b>Don't try to be oversmart, it's my owner! 😎👑</b>\n\n"
                    "<i>System Locked for this search! 🔥</i>"
                )
                send_message(chat_id, roast_msg)
                user_states[chat_id] = None
                return

            send_message(chat_id, f"🔍 <b>Searching OSINT database for:</b> <code>+{clean_text}</code>...")

            if not is_admin:
                update_credits(chat_id, -1)

            api_data = fetch_phone_data(clean_text)
            temp_lookup_data[chat_id] = api_data

            formatted_json = json.dumps(api_data, indent=2, ensure_ascii=False)

            info_msg = (
                f"📞 <b>Lookup Details for:</b> <code>+{clean_text}</code>\n\n"
                f"<pre>{formatted_json}</pre>\n\n"
                f"⚠️ <i>This result will auto-delete in 30 seconds for security!</i>"
            )

            download_btn = {
                "inline_keyboard": [
                    [
                        {
                            "text": "📥 Download JSON File",
                            "callback_data": f"dl_json_{clean_text}",
                        }
                    ]
                ]
            }

            send_auto_delete_message(
                chat_id, info_msg, delay=30, reply_markup=download_btn
            )
            user_states[chat_id] = None
        else:
            send_message(chat_id, "❌ <b>Invalid Format!</b> Send a valid number with country code (e.g., <code>919876543210</code> or <code>+919876543210</code>).")
        return

    else:
        send_message(
            chat_id, "Please select an option.", reply_markup=reply_keyboard
        )


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

        time.sleep(0.1)


if __name__ == "__main__":
    main()
