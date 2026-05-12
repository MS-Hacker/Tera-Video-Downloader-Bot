import os
import re
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
NDUS_COOKIE = os.environ.get("NDUS_COOKIE", "")   # your TeraBox ndus cookie
MAX_DIRECT_MB = 45

TERABOX_DOMAINS = [
    "terabox.com", "teraboxapp.com", "terabox.app",
    "1024terabox.com", "terafileshare.com", "4funbox.com",
    "mirrobox.com", "nephobox.com", "freeterabox.com",
    "www.terabox.com", "www.teraboxapp.com", "www.1024terabox.com",
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_terabox_link(url: str) -> bool:
    return any(d in url for d in TERABOX_DOMAINS)

def human_size(b: int) -> str:
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def get_download_info(url: str, ndus: str):
    """
    Uses the terasnap.netlify.app API (same engine used by
    the popular TeraBox Web open-source project).
    Requires your personal ndus session cookie.
    """
    try:
        resp = requests.post(
            "https://terasnap.netlify.app/api/download",
            json={"link": url, "cookies": f"ndus={ndus}"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        data = resp.json()
        logger.info("terasnap response: %s", data)

        dl   = data.get("download_link", "")
        name = data.get("file_name", "video")
        size = data.get("size_bytes", 0)
        proxy = data.get("proxy_url", "")

        if dl:
            return {"title": name, "size": size, "download_url": dl, "proxy_url": proxy}
    except Exception as e:
        logger.warning("terasnap API failed: %s", e)

    return None

# ── Command Handlers ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cookie_set = "✅ Cookie configured — ready to download!" if NDUS_COOKIE else "⚠️ NDUS_COOKIE not set yet (see /help)"
    await update.message.reply_text(
        "👋 *Welcome to TeraBox Downloader Bot!*\n\n"
        f"{cookie_set}\n\n"
        "Just paste any *public TeraBox link* and I'll fetch the video for you.\n\n"
        "/help — setup guide",
        parse_mode=ParseMode.MARKDOWN,
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Help & Setup*\n\n"
        "*This bot needs your TeraBox session cookie (ndus) to work.*\n\n"
        "📋 *How to get your ndus cookie:*\n"
        "1. Open Chrome/Firefox → go to terabox.com\n"
        "2. Log in to your account\n"
        "3. Play any video (activates your session)\n"
        "4. Press F12 → Application tab → Cookies → terabox.com\n"
        "5. Find the cookie named `ndus` → copy its value\n\n"
        "🔧 *How to set it in Railway:*\n"
        "Variables tab → New Variable:\n"
        "Name: `NDUS_COOKIE`\n"
        "Value: paste the cookie value\n\n"
        f"• Files ≤ {MAX_DIRECT_MB} MB → sent directly in Telegram\n"
        "• Files > that → download button provided",
        parse_mode=ParseMode.MARKDOWN,
    )

# ── Message Handler ────────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = re.findall(r"https?://\S+", text)
    tb_urls = [u for u in urls if is_terabox_link(u)]

    if not tb_urls:
        await update.message.reply_text("❌ No TeraBox link detected. Please send a valid public TeraBox URL.")
        return

    if not NDUS_COOKIE:
        await update.message.reply_text(
            "⚠️ *Bot not configured yet.*\n\n"
            "The owner needs to add the `NDUS_COOKIE` variable in Railway.\n"
            "See /help for instructions.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    url = tb_urls[0]
    status = await update.message.reply_text("🔍 Fetching video info...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    info = get_download_info(url, NDUS_COOKIE)

    if not info:
        await status.edit_text(
            "❌ *Could not fetch this video.*\n\n"
            "• Make sure the link is public\n"
            "• Your ndus cookie may have expired — get a new one (see /help)\n"
            "• Try opening the link in your browser first",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    title    = info["title"]
    size     = info["size"]
    dlink    = info["download_url"]
    proxy    = info.get("proxy_url", "")
    size_str = human_size(size) if size else "Unknown"
    size_mb  = size / (1024 * 1024) if size else 999

    caption = f"📁 *{title}*\n📦 Size: `{size_str}`"

    # Try sending directly for small files
    if size_mb <= MAX_DIRECT_MB and size > 0:
        await status.edit_text(f"⬇️ Downloading `{title}`...")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VIDEO)
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Cookie": f"ndus={NDUS_COOKIE}",
            }
            r = requests.get(dlink, headers=headers, stream=True, timeout=120)
            r.raise_for_status()
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=r.content,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
            )
            await status.delete()
            return
        except Exception as e:
            logger.error("Direct send failed: %s", e)

    # Send download buttons
    buttons = []
    if dlink:
        buttons.append(InlineKeyboardButton("⬇️ Direct Download", url=dlink))
    if proxy:
        buttons.append(InlineKeyboardButton("🔗 Proxy Download", url=proxy))

    keyboard = [buttons] if buttons else []
    note = "\n\n_File too large to send via Telegram — use the buttons below._" if size_mb > MAX_DIRECT_MB else "\n\n_Use the button below to download._"

    await status.edit_text(
        caption + note,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )

# ── Error Handler ─────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Error:", exc_info=context.error)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set!")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
