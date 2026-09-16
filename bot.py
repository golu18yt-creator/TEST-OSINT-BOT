import http.server
import json
import socketserver
import threading
import time
import requests

# ---------------------------------------------------------
# CONFIGURATION VARIABLES
# ---------------------------------------------------------
# Leave your Bot Token and External API URL here
BOT_TOKEN = "8687879528:AAHOavqELOL_IVbcdN3-EX00II5EsnoYZLU"
EXTERNAL_API_URL = "https://nmdllpezcocquamhgpmb.supabase.co/functions/v1/lookup?number={value}"

# Admin  ID  { put your Telegram Numeric ID}
ADMIN_ID =  8927308711

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Dictionary to track user states (e.g., waiting for phone number)
user_states = {}


# ---------------------------------------------------------
# DUMMY HTTP SERVER (Runs in a background thread)
# ---------------------------------------------------------
def run_dummy_server(port=8080):
    """
    Starts a simple dummy HTTP server to bind to a port if hosting
    on platforms like Render or Koyeb that require a web process.
    """

    class DummyHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Bot is alive!")

        def log_message(self, format, *args):
            # Suppress server logs to keep console output clean
            return

    try:
        with socketserver.TCPServer(("", port), DummyHandler) as httpd:
            print(f"Dummy HTTP Server running on port {port}...")
            httpd.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")


# ---------------------------------------------------------
# TELEGRAM API HELPER FUNCTIONS
# ---------------------------------------------------------
def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """
    Sends a message to a specific Telegram chat using the Telegram Bot API.
    """
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None


def get_updates(offset=None):
    """
    Fetches new updates from Telegram using long polling.
    """
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
    """
    Calls the external API using the phone number and returns the response JSON.
    """
    try:
        # Append phone_number to query params or path as per your external API setup
        # Example assumes the API accepts 'number' parameter or formatted URL
        response = requests.get(
            EXTERNAL_API_URL, params={"number": phone_number}, timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned status code {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------
# MESSAGE HANDLING LOGIC
# ---------------------------------------------------------
def handle_message(update):
    """
    Processes an incoming message update from Telegram.
    """
    if "message" not in update:
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # Define custom keyboard
    reply_keyboard = {
        "keyboard": [[{"text": "📱 Phone Lookup"}]],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }

    # Command: /start
    if text == "/start":
        welcome_msg = (
            "Welcome! Press the button below to lookup phone numbers."
        )
        send_message(chat_id, welcome_msg, reply_markup=reply_keyboard)
        user_states[chat_id] = None  # Reset state

    # Button Press: 📱 Phone Lookup
    elif text == "📱 Phone Lookup":
        prompt_msg = "📞 Send 10 digit mobile number:"
        send_message(chat_id, prompt_msg)
        user_states[chat_id] = "awaiting_phone_number"

    # Input state: Waiting for phone number
    elif user_states.get(chat_id) == "awaiting_phone_number":
        # Validate if input is exactly a 10-digit numeric string
        if text.isdigit() and len(text) == 10:
            send_message(chat_id, "🔍 Searching details, please wait...")

            # Call external API
            api_data = fetch_phone_data(text)

            # Format JSON response inside <pre> tag
            formatted_json = json.dumps(api_data, indent=2)
            response_msg = f"<pre>{formatted_json}</pre>"

            send_message(chat_id, response_msg, parse_mode="HTML")

            # Reset user state after processing
            user_states[chat_id] = None
        else:
            # Error message for invalid input
            error_msg = (
                "❌ <b>Invalid Input!</b>\n\n"
                "Please send a valid <b>10-digit numeric</b> mobile number."
            )
            send_message(chat_id, error_msg, parse_mode="HTML")

    # Generic fallback
    else:
        fallback_msg = (
            "Please select an option from the keyboard or send /start."
        )
        send_message(chat_id, fallback_msg, reply_markup=reply_keyboard)


# ---------------------------------------------------------
# MAIN BOT LOOP
# ---------------------------------------------------------
def main():
    if not BOT_TOKEN:
        print("WARNING: BOT_TOKEN is blank. Please enter your Telegram token.")

    # Start dummy HTTP server in a separate thread
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()

    print("Bot is running using long-polling...")

    offset = None

    while True:
        updates = get_updates(offset)

        if updates and updates.get("ok"):
            for update in updates.get("result", []):
                # Update offset to confirm receipt of the update
                offset = update["update_id"] + 1

                # Handle the received message update
                handle_message(update)

        # Brief sleep to avoid hitting CPU limits in case of errors
        time.sleep(1)


if __name__ == "__bot.py__":
    bot.py()
