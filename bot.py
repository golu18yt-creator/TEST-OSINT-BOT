import os
import json
import sqlite3
import logging
import asyncio
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ---------------------------------------------------------
# Configurations
# ---------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8687879528:AAHOavqELOL_IVbcdN3-EX00II5EsnoYZLU")
ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_IDS", "8927308711").split(",") if i.strip() and i.strip().isdigit()]
OWNER_PHONE_NUMBER = os.getenv("OWNER_PHONE_NUMBER", "8595900496").strip()

# Dynamic Supabase API URL Handling
DEFAULT_API_URL = "https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup?number={value}"
EXTERNAL_API_TEMPLATE = os.getenv("EXTERNAL_API_URL", DEFAULT_API_URL)

DEFAULT_FREE_CREDITS = 5
REFERRAL_REWARD = 2

# Database Setup
conn = sqlite3.connect("bot_database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credits INTEGER,
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
    uses_left INTEGER
)
""")
conn.commit()

# Settings Helpers
def get_setting(key, default=""):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    return res[0] if res else default

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

if not get_setting("welcome_msg"):
    set_setting("welcome_msg", "Welcome to Phone Lookup Bot! Enter a 10-digit number to search.")
if not get_setting("bot_active"):
    set_setting("bot_active", "true")

# ---------------------------------------------------------
# Keep-Alive Web Server (Safe Port Binding)
# ---------------------------------------------------------
class WebServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def log_message(self, format, *args):
        return  # Disable verbose server logging

def start_web_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), WebServerHandler)
        server.serve_forever()
    except Exception as e:
        logging.error(f"Web server failed to start: {e}")

Thread(target=start_web_server, daemon=True).start()

# ---------------------------------------------------------
# API Fetch Function
# ---------------------------------------------------------
def fetch_phone_data(phone_number: str):
    try:
        if "{value}" in EXTERNAL_API_TEMPLATE:
            request_url = EXTERNAL_API_TEMPLATE.replace("{value}", phone_number)
            params = {}
        else:
            request_url = EXTERNAL_API_TEMPLATE
            params = {"number": phone_number}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        response = requests.get(request_url, params=params, headers=headers, timeout=15)

        if response.status_code != 200:
            return {"success": False, "error": f"API Error Code: {response.status_code}"}

        try:
            data = response.json()
        except Exception:
            return {"success": False, "error": "Invalid JSON format from API."}

        if isinstance(data, dict):
            if data.get("success") is False:
                err = data.get("error") or data.get("details") or "API Lookup Failed."
                return {"success": False, "error": str(err)}

            if "result" in data and isinstance(data["result"], dict):
                res = data["result"]
                if res.get("success") is False:
                    return {"success": False, "error": res.get("details", "Details not found.")}
                return {"success": True, "data": res}

            return {"success": True, "data": data}

        return {"success": True, "data": data}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "API Request timed out."}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Network Error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected Error: {str(e)}"}

# ---------------------------------------------------------
# User Helpers
# ---------------------------------------------------------
def is_admin(user_id):
    if user_id in ADMIN_IDS:
        return True
    cursor.execute("SELECT is_admin FROM users WHERE user_id=?", (user_id,))
    res = cursor.fetchone()
    return bool(res and res[0] == 1)

def get_user(user_id):
    cursor.execute("SELECT user_id, credits, referred_by, is_admin, is_banned FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def register_user(user_id, referred_by=None):
    user = get_user(user_id)
    if not user:
        admin_flag = 1 if user_id in ADMIN_IDS else 0
        cursor.execute(
            "INSERT INTO users (user_id, credits, referred_by, is_admin) VALUES (?, ?, ?, ?)",
            (user_id, DEFAULT_FREE_CREDITS, referred_by, admin_flag)
        )
        conn.commit()
        if referred_by and referred_by != user_id:
            cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (REFERRAL_REWARD, referred_by))
            conn.commit()

def check_force_sub(user_id, context):
    channel = get_setting("force_channel")
    if not channel:
        return True
    try:
        member = context.bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
    except Exception:
        pass
    return False

# ---------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    ref_id = int(args[0]) if args and args[0].isdigit() else None

    register_user(user_id, ref_id)
    welcome_text = get_setting("welcome_msg")

    user_is_admin = is_admin(user_id)
    user_data = get_user(user_id)
    credits_display = "Unlimited (Admin)" if user_is_admin else user_data[1]

    full_text = f"{welcome_text}\n\n💳 **Your Credits:** `{credits_display}`"
    await update.message.reply_text(full_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    user_is_admin = is_admin(user_id)

    if get_setting("bot_active") != "true" and not user_is_admin:
        await update.message.reply_text("⚠️ Bot is currently under maintenance.")
        return

    if not check_force_sub(user_id, context):
        channel = get_setting("force_channel")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Channel", url=f"https://t.me/{channel.replace('@', '')}")],
            [InlineKeyboardButton("Verify Joining", callback_data="check_join")]
        ])
        await update.message.reply_text("❌ Please join our channel to use this bot!", reply_markup=keyboard)
        return

    user = get_user(user_id)
    if not user:
        register_user(user_id)
        user = get_user(user_id)

    if user[4] == 1:
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    # 10-Digit Lookup Processing
    if text.isdigit() and len(text) == 10:
        if text == OWNER_PHONE_NUMBER:
            await update.message.reply_text("dont try to be oversmart its my owner 😈😎")
            return

        credits = user[1]

        if not user_is_admin and credits < 1:
            await update.message.reply_text("❌ You don't have enough credits! Invite friends or redeem a code.")
            return

        status_msg = await update.message.reply_text("🔎 Searching details... Please wait.")
        result = fetch_phone_data(text)

        if not result["success"]:
            await status_msg.edit_text(f"❌ Search Failed!\n\nReason: {result['error']}")
            return

        if not user_is_admin:
            cursor.execute("UPDATE users SET credits = credits - 1 WHERE user_id=?", (user_id,))
            conn.commit()

        formatted_data = json.dumps(result["data"], indent=2, ensure_ascii=False)
        response_text = f"📱 **Details Found for {text}:**\n\n```json\n{formatted_data[:1000]}\n```\n\n⚠️ Message auto-deletes in 30s."

        file_path = f"details_{text}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatted_data)

        sent_msg = await update.message.reply_text(
            response_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Download JSON File", callback_data=f"dl_{file_path}")]
            ])
        )
        await status_msg.delete()

        async def delete_later(msg_to_delete):
            await asyncio.sleep(30)
            try:
                await msg_to_delete.delete()
            except Exception:
                pass

        asyncio.create_task(delete_later(sent_msg))

# ---------------------------------------------------------
# Admin Controls
# ---------------------------------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Access Denied! Admin-only command.")
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    msg = (
        "⚙️ **Admin Control Panel**\n\n"
        f"👥 **Total Users:** `{total_users}`\n"
        f"🟢 **Bot Status:** `{get_setting('bot_active')}`\n"
        f"📢 **Force Sub Channel:** `{get_setting('force_channel', 'None')}`\n\n"
        "👑 **Admin Commands:**\n"
        "• `/createcode <code> <credits> <uses>` - Generate Promo Code\n"
        "• `/addchannel <@channel>` - Set Force Sub Channel\n"
        "• `/removechannel` - Clear Force Sub Channel\n"
        "• `/addcredits <user_id> <amount>` - Add Credits to User"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin Only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/addchannel @channelusername`", parse_mode="Markdown")
        return
    channel = context.args[0].strip()
    set_setting("force_channel", channel)
    await update.message.reply_text(f"✅ Force Sub Channel updated to: `{channel}`", parse_mode="Markdown")

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin Only!")
        return
    set_setting("force_channel", "")
    await update.message.reply_text("✅ Force Sub Channel removed successfully!")

async def create_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin Only!")
        return
    try:
        code = context.args[0].strip().upper()
        credits_val = int(context.args[1])
        uses = int(context.args[2])

        cursor.execute("INSERT OR REPLACE INTO redeem_codes VALUES (?, ?, ?)", (code, credits_val, uses))
        conn.commit()
        await update.message.reply_text(f"✅ Code `{code}` generated with `{credits_val}` credits for `{uses}` uses!", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("Usage: `/createcode <code> <credits> <uses>`", parse_mode="Markdown")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: `/redeem <code>`", parse_mode="Markdown")
        return

    code_text = context.args[0].strip().upper()
    cursor.execute("SELECT credits, uses_left FROM redeem_codes WHERE code=?", (code_text,))
    code_data = cursor.fetchone()

    if not code_data:
        await update.message.reply_text("❌ Invalid redeem code!")
        return

    credits_val, uses_left = code_data

    if uses_left < 1:
        await update.message.reply_text("❌ This redeem code has expired!")
        return

    cursor.execute("UPDATE redeem_codes SET uses_left = uses_left - 1 WHERE code=?", (code_text,))
    cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (credits_val, user_id))
    conn.commit()

    await update.message.reply_text(f"🎉 Code Redeemed! Added `{credits_val}` credits to your account.", parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("dl_"):
        file_path = query.data.replace("dl_", "")
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                await query.message.reply_document(InputFile(f, filename=file_path))
            os.remove(file_path)
        else:
            await query.message.reply_text("❌ File expired or removed.")
    elif query.data == "check_join":
        if check_force_sub(query.from_user.id, context):
            await query.message.edit_text("✅ Verification successful! Send a 10-digit number.")
        else:
            await query.message.reply_text("❌ You have not joined the channel yet!")

# ---------------------------------------------------------
# Main Execution
# ---------------------------------------------------------
def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("CRITICAL ERROR: BOT_TOKEN is missing or not configured correctly in Environment Variables.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("redeem", redeem))

    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("createcode", create_code))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("removechannel", remove_channel))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot started successfully...")
    app.run_polling()

if __name__ == "__main__":
    main()
