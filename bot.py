import os
import re
import logging
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode, ChatAction

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Terabox API endpoint (free public API - no key needed)
TERABOX_API = "https://teraboxapp.com/api/shorturlinfo"
TERABOX_API2 = "https://www.terabox.app/api/shorturlinfo"

# Max file size Telegram allows via sendVideo (50 MB for bots)
MAX_DIRECT_SIZE_MB = 50

# ── Helpers ───────────────────────────────────────────────────────────────────
TERABOX_DOMAINS = [
    "terabox.com", "teraboxapp.com", "terabox.app",
    "1024terabox.com", "terafileshare.com", "4funbox.com",
    "mirrobox.com", "nephobox.com", "freeterabox.com",
    "www.terabox.com", "www.teraboxapp.com",
]

def is_terabox_link(url: str) -> bool:
    return any(domain in url for domain in TERABOX_DOMAINS)

def extract_surl(url: str):
    """Extract the short URL token from a TeraBox share link."""
    match = re.search(r"[?&]surl=([^&]+)", url)
    if match:
        return match.group(1)
    # Handle /s/XXXX style links
    match = re.search(r"/s/([^/?&]+)", url)
    if match:
        return match.group(1)
    return None

def fetch_terabox_info(url: str):
    """
    Call the public TeraBox info API and return file details.
    Returns dict with keys: title, size, download_url, thumbnail
    """
    surl = extract_surl(url)
    if not surl:
        # Try direct URL as surl
        surl = url

    params = {"surl": surl}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://teraboxapp.com/",
    }

    for api_url in [TERABOX_API, TERABOX_API2]:
        try:
            resp = requests.get(api_url, params=params, headers=headers, timeout=20)
            data = resp.json()
            logger.info("TeraBox API response: %s", data)

            if data.get("errno") == 0:
                file_list = data.get("list", [])
                if not file_list:
                    continue
                f = file_list[0]
                return {
                    "title": f.get("server_filename", "video"),
                    "size": int(f.get("size", 0)),
                    "download_url": f.get("dlink") or f.get("downloadUrl", ""),
                    "thumbnail": f.get("thumbs", {}).get("url3", ""),
                    "is_dir": f.get("isdir", 0),
                }
        except Exception as e:
            logger.warning("API %s failed: %s", api_url, e)

    return None

def human_size(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"

# ── Command Handlers ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Welcome to TeraBox Downloader Bot!*\n\n"
        "Simply send me any *public TeraBox link* and I'll download the video for you.\n\n"
        "📌 *Supported domains:*\n"
        "`terabox.com`, `teraboxapp.com`, `1024terabox.com`, and more.\n\n"
        "⚡ *How to use:*\n"
        "1. Copy a public TeraBox share link\n"
        "2. Paste it here\n"
        "3. I'll fetch and send you the video!\n\n"
        "Use /help for more info."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *Help*\n\n"
        "*Commands:*\n"
        "/start — Welcome message\n"
        "/help  — This help message\n\n"
        "*Usage:*\n"
        "Just paste a TeraBox public link — no command needed.\n\n"
        "*Limits:*\n"
        f"• Files ≤ {MAX_DIRECT_SIZE_MB} MB → sent directly as video\n"
        f"• Files > {MAX_DIRECT_SIZE_MB} MB → you'll get a direct download link\n\n"
        "*Note:* Only *public* links work. Private/password-protected links are not supported."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ── Message Handler ────────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Extract URL from message
    urls = re.findall(r"https?://\S+", text)
    terabox_urls = [u for u in urls if is_terabox_link(u)]

    if not terabox_urls:
        await update.message.reply_text(
            "❌ No TeraBox link detected.\n\nPlease send a valid TeraBox share URL."
        )
        return

    url = terabox_urls[0]
    status_msg = await update.message.reply_text("🔍 Fetching file info...")

    # Show typing action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    info = fetch_terabox_info(url)

    if not info:
        await status_msg.edit_text(
            "❌ *Failed to fetch file info.*\n\n"
            "Possible reasons:\n"
            "• The link is private or expired\n"
            "• TeraBox API is temporarily down\n"
            "• The link format is not supported\n\n"
            "Please try a different link.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    title = info["title"]
    size = info["size"]
    dlink = info["download_url"]
    thumb = info["thumbnail"]

    if not dlink:
        await status_msg.edit_text(
            "❌ Could not extract a download link from this file.\n"
            "It may be a folder or a non-video file."
        )
        return

    size_mb = size / (1024 * 1024)
    size_str = human_size(size)

    caption = (
        f"📁 *{title}*\n"
        f"📦 Size: `{size_str}`\n"
    )

    if size_mb <= MAX_DIRECT_SIZE_MB and size > 0:
        # Try to send directly
        await status_msg.edit_text(f"⬇️ Downloading `{title}`...")
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VIDEO
        )
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            video_resp = requests.get(dlink, headers=headers, stream=True, timeout=60)
            video_resp.raise_for_status()

            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_resp.content,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
            )
            await status_msg.delete()

        except Exception as e:
            logger.error("Direct send failed: %s", e)
            # Fallback: send link
            keyboard = [[InlineKeyboardButton("⬇️ Download Video", url=dlink)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text(
                caption + "\n⚠️ _Direct send failed. Use the button below to download._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
    else:
        # File too large or size unknown — send download link
        keyboard = [[InlineKeyboardButton("⬇️ Download Video", url=dlink)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        note = (
            "\n⚠️ _File is too large to send directly via Telegram._\n"
            "_Click the button below to download it._"
            if size_mb > MAX_DIRECT_SIZE_MB
            else "\n_Click the button below to download._"
        )
        await status_msg.edit_text(
            caption + note,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )

# ── Error Handler ─────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise ValueError("Please set your BOT_TOKEN environment variable!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()