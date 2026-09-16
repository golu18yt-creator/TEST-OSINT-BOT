import http.server
import json
import os
import socketserver
import threading
import time
import requests

# ---------------------------------------------------------
# CONFIGURATION VARIABLES
# ---------------------------------------------------------
# Code me token/URL yahan daal sakte hain, YA Render Environment Variables se read ho jayega
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8687879528:AAHOavqELOL_IVbcdN3-EX00II5EsnoYZLU")
EXTERNAL_API_URL = os.environ.get(
    "EXTERNAL_API_URL", ""https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup""
)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
user_states = {}


# ---------------------------------------------------------
# DUMMY HTTP SERVER (Render Port Binding)
# ---------------------------------------------------------
def run_dummy_server():
    # Render dynamic PORT auto-read karega (Default 8080)
    port = int(os.environ.get("PORT", 8080))

    class DummyHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Bot is alive!")

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
# TELEGRAM API HELPER FUNCTIONS
# ---------------------------------------------------------
def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    if not BOT_TOKEN or BOT_TOKEN == "YAHAN_BOT_TOKEN_DAALEIN":
        print("BOT_TOKEN is missing!")
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
# EXTERNAL API HELPER FUNCTION
# ---------------------------------------------------------
def fetch_phone_data(phone_number):
    if not EXTERNAL_API_URL or EXTERNAL_API_URL == "https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup?number={value}":
        return {"error": "EXTERNAL_API_URL configured nahi hai"}

    # Base URL se path fix karke direct number inject kar rahe hain
    base_url = "https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup"
    target_url = f"{base_url}?number={phone_number}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

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
                    "error_details": response.json()
                }
            except Exception:
                return {
                    "http_code": response.status_code,
                    "raw_response": response.text[:300]
                }

    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------
# MESSAGE HANDLING LOGIC
# ---------------------------------------------------------
def handle_message(update):
    if "message" not in update:
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    reply_keyboard = {
        "keyboard": [[{"text": "📱 Phone Lookup"}]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

    if text == "/start":
        welcome_msg = (
            "Welcome! Press the button below to lookup phone numbers."
        )
        send_message(chat_id, welcome_msg, reply_markup=reply_keyboard)
        user_states[chat_id] = None

    elif text == "📱 Phone Lookup":
        prompt_msg = "📞 Send 10 digit mobile number:"
        send_message(chat_id, prompt_msg)
        user_states[chat_id] = "awaiting_phone_number"

    elif user_states.get(chat_id) == "awaiting_phone_number":
        if text.isdigit() and len(text) == 10:
            send_message(chat_id, "🔍 Searching details, please wait...")

            api_data = fetch_phone_data(text)
            formatted_json = json.dumps(api_data, indent=2)
            response_msg = f"<pre>{formatted_json}</pre>"

            send_message(chat_id, response_msg, parse_mode="HTML")
            user_states[chat_id] = None
        else:
            error_msg = (
                "❌ <b>Invalid Input!</b>\n\n"
                "Please send a valid <b>10-digit numeric</b> mobile number."
            )
            send_message(chat_id, error_msg, parse_mode="HTML")

    else:
        fallback_msg = (
            "Please select an option from the keyboard or send /start."
        )
        send_message(chat_id, fallback_msg, reply_markup=reply_keyboard)


# ---------------------------------------------------------
# MAIN POLLING LOOP
# ---------------------------------------------------------
def main():
    # Start dummy HTTP server thread for Render
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()

    print("Bot starting polling loop...")
    offset = None

    while True:
        try:
            updates = get_updates(offset)
            if updates and updates.get("ok"):
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    handle_message(update)
        except Exception as e:
            print(f"Polling Exception: {e}")

        time.sleep(1)


    # ---------------------------------------------------------
# FIXED MAIN POLLING LOOP (NO MORE SPAM)
# ---------------------------------------------------------
def main():
    # Start dummy HTTP server thread for Render
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()

    print("Bot starting polling loop...")

    # Set initial offset to 0 so we only process fresh updates
    offset = None

    while True:
        try:
            updates = get_updates(offset)

            if updates and updates.get("ok"):
                results = updates.get("result", [])

                for update in results:
                    # Update offset BEFORE handling to prevent duplicates if handling crashes
                    offset = update["update_id"] + 1
                    handle_message(update)

        except Exception as e:
            print(f"Polling Exception: {e}")

        # Short pause to prevent hit rate limits
        time.sleep(0.5)


if __name__ == "__main__":
    main()
    
