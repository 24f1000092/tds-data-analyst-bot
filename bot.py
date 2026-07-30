import json
import time
import os
from threading import Thread

from flask import Flask
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

# ----------------------------
# Tiny web server for Render
# ----------------------------
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Telegram Bot is running!"

def run_web_server():
    web_app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

# Start web server in background
Thread(target=run_web_server, daemon=True).start()

# ----------------------------
# Environment Variables
# ----------------------------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
AIPIPE_TOKEN = os.environ["AIPIPE_TOKEN"]

LOG_URL = "https://raw.githubusercontent.com/24f1000092/tds-data-analyst-bot/refs/heads/main/run.jsonl"

client = OpenAI(
    base_url="https://aipipe.org/openai/v1",
    api_key=AIPIPE_TOKEN,
)

LOG_FILE = "run.jsonl"

# Store recent conversation history
conversation_history = {}


def log_event(event: dict):
    event["timestamp"] = time.time()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text

    log_event({
        "type": "incoming",
        "chat_id": chat_id,
        "text": user_text,
    })

    history = conversation_history.setdefault(chat_id, [])
    history.append({
        "role": "user",
        "content": user_text,
    })

    system_prompt = (
        "You are a careful data analyst.\n"
        "Always answer ONLY the user's LAST message.\n"
        "The user specifies the exact JSON structure required.\n"
        "Return exactly ONE valid JSON object.\n"
        "Do NOT add any extra keys.\n"
        "Do NOT add explanations.\n"
        "Do NOT wrap in markdown.\n"
        "If the requested JSON already contains 'answer' and 'log_url', preserve the "
        "'answer' exactly as requested. The application will overwrite 'log_url'."
    )

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "system", "content": system_prompt}] + history[-6:],
    )

    reply_text = response.choices[0].message.content.strip()

    history.append({
        "role": "assistant",
        "content": reply_text,
    })

    try:
        parsed = json.loads(reply_text)
    except json.JSONDecodeError:
        start = reply_text.find("{")
        end = reply_text.rfind("}")

        if start == -1 or end == -1:
            parsed = {
                "answer": reply_text
            }
        else:
            parsed = json.loads(reply_text[start:end + 1])

    parsed["log_url"] = LOG_URL

    final_reply = json.dumps(parsed)

    log_event({
        "type": "outgoing",
        "chat_id": chat_id,
        "text": final_reply,
    })

    await update.message.reply_text(final_reply)


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    print("Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
