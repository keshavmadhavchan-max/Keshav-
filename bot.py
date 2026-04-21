import os
import json
import asyncio
import logging
import requests
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from openai import OpenAI

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8687974688:AAFG8SuN6Mzl3jIGqlPCgXknAyxXeGpzD2w"
OPENAI_API_KEY   = "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"
SOSOVALUE_KEY    = "SOSO-5704339642004799a694c9cd84442d5a"

SUBSCRIBERS_FILE = "subscribers.json"
SEND_TIMES       = ["08:00", "13:00", "19:00"]

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

openai_client = OpenAI(api_key=OPENAI_API_KEY)

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            return set(json.load(f))
    return set()

def save_subscribers(subs):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subs), f)

subscribers: set = load_subscribers()

def fetch_sosovalue_news() -> list[dict]:
    headers = {"Authorization": f"Bearer {SOSOVALUE_KEY}"}
    try:
        url = "https://api.sosovalue.com/api/v1/news/list"
        params = {"page": 1, "pageSize": 5, "lang": "en"}
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        if items:
            return items[:5]
    except Exception as e:
        log.warning(f"News endpoint failed: {e}")
    try:
        url2 = "https://api.sosovalue.com/api/v1/index/market"
        resp2 = requests.get(url2, headers=headers, timeout=10)
        resp2.raise_for_status()
        return [{"title": "Market Update", "content": json.dumps(resp2.json()), "source": "SoSoValue Market Index"}]
    except Exception as e:
        log.error(f"Fallback also failed: {e}")
        return []

def simplify_news(articles: list[dict]) -> str:
    if not articles:
        return "⚠️ No fresh crypto news right now. Check back soon!"
    raw = ""
    for i, a in enumerate(articles, 1):
        title   = a.get("title", a.get("name", "Update"))
        content = a.get("content", a.get("summary", a.get("description", str(a))))
        raw += f"{i}. {title}\n{content[:600]}\n\n"
    prompt = f"""You are a friendly crypto tutor explaining news to complete beginners AND casual followers.

Here are today's latest crypto news items:
{raw}

Please write a SHORT, SIMPLE daily digest with:
- A friendly intro line
- For each story: one emoji, plain-English headline, 2-sentence explanation a 12-year-old could understand, and 1 clear takeaway labelled "💡 What this means for you:"
- A closing motivational line

Avoid jargon. If you must use a technical term, explain it in brackets.
Keep the whole message under 600 words."""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"OpenAI error: {e}")
        return "⚠️ Could not simplify news right now. Please try again later."

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text(
        "👋 Welcome to *Daily Crypto News Simplifier*!\n\n"
        "I pull the latest crypto news from SoSoValue and explain it in plain, simple language — no jargon!\n\n"
        "📬 You'll get updates *3× a day* (8am, 1pm, 7pm UTC).\n\n"
        "Commands:\n"
        "/news — Get the latest news right now\n"
        "/stop — Unsubscribe from daily updates\n"
        "/help — Show this message again",
        parse_mode="Markdown"
    )

async def news_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Fetching & simplifying the latest crypto news... hang tight!")
    articles = fetch_sosovalue_news()
    message  = simplify_news(articles)
    header   = f"📰 *Crypto News Update* — {datetime.utcnow().strftime('%b %d, %H:%M UTC')}\n\n"
    await update.message.reply_text(header + message, parse_mode="Markdown")

async def stop_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.discard(chat_id)
    save_subscribers(subscribers)
    await update.message.reply_text("✅ You've unsubscribed. Type /start anytime to get updates again.")

async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Daily Crypto News Simplifier*\n\n"
        "/start — Subscribe to daily updates\n"
        "/news  — Get latest news right now\n"
        "/stop  — Unsubscribe\n"
        "/help  — Show this help",
        parse_mode="Markdown"
    )

async def broadcast(context: ContextTypes.DEFAULT_TYPE):
    if not subscribers:
        return
    articles = fetch_sosovalue_news()
    message  = simplify_news(articles)
    header   = f"📰 *Crypto News Update* — {datetime.utcnow().strftime('%b %d, %H:%M UTC')}\n\n"
    full_msg = header + message
    for chat_id in list(subscribers):
        try:
            await context.bot.send_message(chat_id=chat_id, text=full_msg, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Failed to send to {chat_id}: {e}")
            subscribers.discard(chat_id)
    save_subscribers(subscribers)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news",  news_command))
    app.add_handler(CommandHandler("stop",  stop_command))
    app.add_handler(CommandHandler("help",  help_command))
    job_queue = app.job_queue
    for t in SEND_TIMES:
        job_queue.run_daily(broadcast, time=datetime.strptime(t, "%H:%M").time())
    log.info("🚀 Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
