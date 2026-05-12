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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MAX_DIRECT_SIZE_MB = 45

TERABOX_DOMAINS = [
    "terabox.com", "teraboxapp.com", "terabox.app",
    "1024terabox.com", "terafileshare.com", "4funbox.com",
    "mirrobox.com", "nephobox.com", "freeterabox.com",
    "www.terabox.com", "www.teraboxapp.com", "www.1024terabox.com",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.terabox.app/",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_terabox_link(url: str) -> bool:
    return any(domain in url for domain in TERABOX_DOMAINS)

def human_size(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"

def get_terabox_info(url: str):
    """
    Try multiple methods to extract TeraBox download info.
    Returns dict: {title, size, download_url} or None
    """

    session = requests.Session()
    session.headers.update(HEADERS)

    # ── Method 1: terabox.app API ─────────────────────────────────────────────
    try:
        logger.info("Trying Method 1: terabox.app API")
        api = "https://www.terabox.app/api/shorturlinfo"
        surl = extract_surl(url)
        if surl:
            r = session.get(api, params={"surl": surl}, timeout=15)
            data = r.json()
            logger.info("Method 1 response: %s", data)
            result = parse_api_response(data)
            if result:
                return result
    except Exception as e:
        logger.warning("Method 1 failed: %s", e)

    # ── Method 2: 1024terabox API ─────────────────────────────────────────────
    try:
        logger.info("Trying Method 2: 1024terabox API")
        api = "https://www.1024terabox.com/api/shorturlinfo"
        surl = extract_surl(url)
        if surl:
            r = session.get(api, params={"surl": surl}, timeout=15)
            data = r.json()
            logger.info("Method 2 response: %s", data)
            result = parse_api_response(data)
            if result:
                return result
    except Exception as e:
        logger.warning("Method 2 failed: %s", e)

    # ── Method 3: Third-party terabox downloader API ──────────────────────────
    try:
        logger.info("Trying Method 3: third-party API")
        api = "https://terabox-downloader-direct-download-link-generator1.p.rapidapi.com/url"
        # Free fallback without RapidAPI key
        r = session.get(
            "https://ytshorts.savetube.me/api/v1/terabox-downloader",
            json={"url": url},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        data = r.json()
        logger.info("Method 3 response: %s", data)
        if data.get("response"):
            item = data["response"][0] if isinstance(data["response"], list) else data["response"]
            dlink = item.get("resolutions", {})
            # get highest quality
            dl_url = (
                dlink.get("Fast Download") or
                dlink.get("HD Video") or
                dlink.get("SD Video") or
                item.get("url", "")
            )
            if dl_url:
                return {
                    "title": item.get("title", "video"),
                    "size": 0,
                    "download_url": dl_url,
                }
    except Exception as e:
        logger.warning("Method 3 failed: %s", e)

    # ── Method 4: scrape the page directly ────────────────────────────────────
    try:
        logger.info("Trying Method 4: page scrape")
        r = session.get(url, timeout=15, allow_redirects=True)
        final_url = r.url

        # Extract jsToken and other params from page
        js_token_match = re.search(r'jsToken.*?"(.*?)"', r.text)
        log_id_match = re.search(r'logid.*?"(.*?)"', r.text)
        bdstoken_match = re.search(r'bdstoken.*?"(.*?)"', r.text)

        # Try to find direct video URLs in page source
        video_url_match = re.search(r'"dlink":"(https?://[^"]+)"', r.text)
        if video_url_match:
            dlink = video_url_match.group(1).replace("\\u0026", "&")
            title_match = re.search(r'"server_filename":"([^"]+)"', r.text)
            size_match = re.search(r'"size":"?(\d+)"?', r.text)
            return {
                "title": title_match.group(1) if title_match else "video",
                "size": int(size_match.group(1)) if size_match else 0,
                "download_url": dlink,
            }

        # Try alternative pattern
        video_url_match2 = re.search(r'downloadUrl["\s:]+(["\'])?(https?://[^\s"\'<>]+)', r.text)
        if video_url_match2:
            return {
                "title": "TeraBox Video",
                "size": 0,
                "download_url": video_url_match2.group(2),
            }

    except Exception as e:
        logger.warning("Method 4 failed: %s", e)

    # ── Method 5: teradownloader.com API ─────────────────────────────────────
    try:
        logger.info("Trying Method 5: teradownloader")
        r = session.post(
            "https://teradownloader.com/download",
            data={"url": url},
            headers={**HEADERS, "Referer": "https://teradownloader.com/"},
            timeout=20,
        )
        data = r.json()
        logger.info("Method 5 response: %s", data)
        dl = data.get("download_url") or data.get("url") or data.get("link")
        if dl:
            return {
                "title": data.get("filename", "video"),
                "size": data.get("size", 0),
                "download_url": dl,
            }
    except Exception as e:
        logger.warning("Method 5 failed: %s", e)

    return None


def extract_surl(url: str):
    match = re.search(r"[?&]surl=([^&]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/s/([^/?&#]+)", url)
    if match:
        return match.group(1)
    return None


def parse_api_response(data: dict):
    if not data:
        return None
    errno = data.get("errno", -1)
    if errno != 0:
        return None
    file_list = data.get("list", [])
    if not file_list:
        return None
    f = file_list[0]
    dlink = f.get("dlink") or f.get("downloadUrl", "")
    if not dlink:
        return None
    return {
        "title": f.get("server_filename", "video"),
        "size": int(f.get("size", 0)),
        "download_url": dlink,
    }


# ── Command Handlers ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Welcome to TeraBox Downloader Bot!*\n\n"
        "Send me any *public TeraBox link* and I'll get the video for you.\n\n"
        "📌 *Supported:*\n"
        "`terabox.com`, `teraboxapp.com`, `1024terabox.com` and more\n\n"
        "⚡ *How to use:*\n"
        "Just paste the link — no command needed!\n\n"
        "/help for more info."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *Help*\n\n"
        "*Commands:*\n"
        "/start — Welcome\n"
        "/help  — This message\n\n"
        "*How it works:*\n"
        "Paste any public TeraBox share link.\n\n"
        f"• Files ≤ {MAX_DIRECT_SIZE_MB} MB → sent as video in Telegram\n"
        f"• Files > {MAX_DIRECT_SIZE_MB} MB → direct download button\n\n"
        "*Only public links work.* Private/password links are not supported."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ── Message Handler ────────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = re.findall(r"https?://\S+", text)
    terabox_urls = [u for u in urls if is_terabox_link(u)]

    if not terabox_urls:
        await update.message.reply_text(
            "❌ No TeraBox link detected.\n\nPlease send a valid public TeraBox link."
        )
        return

    url = terabox_urls[0]
    status_msg = await update.message.reply_text("🔍 Fetching video info, please wait...")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    info = get_terabox_info(url)

    if not info or not info.get("download_url"):
        await status_msg.edit_text(
            "❌ *Could not fetch this video.*\n\n"
            "Possible reasons:\n"
            "• Link is private or expired\n"
            "• TeraBox blocked this request\n"
            "• Password-protected file\n\n"
            "💡 *Tip:* Make sure the link opens in your browser without login.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    title = info.get("title", "video")
    size = info.get("size", 0)
    dlink = info["download_url"]
    size_str = human_size(size) if size else "Unknown"
    size_mb = size / (1024 * 1024) if size else 0

    caption = f"📁 *{title}*\n📦 Size: `{size_str}`"

    should_direct_send = size_mb > 0 and size_mb <= MAX_DIRECT_SIZE_MB

    if should_direct_send:
        await status_msg.edit_text(f"⬇️ Downloading `{title}`...")
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VIDEO
        )
        try:
            dl_headers = {**HEADERS, "Referer": "https://www.terabox.app/"}
            video_resp = requests.get(dlink, headers=dl_headers, stream=True, timeout=120)
            video_resp.raise_for_status()
            content = video_resp.content

            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=content,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
            )
            await status_msg.delete()
            return
        except Exception as e:
            logger.error("Direct send failed: %s", e)
            # Fall through to link button

    # Send download link button
    keyboard = [[InlineKeyboardButton("⬇️ Download Video", url=dlink)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    note = ""
    if size_mb > MAX_DIRECT_SIZE_MB:
        note = "\n\n⚠️ _File too large to send via Telegram. Use the button below._"
    else:
        note = "\n\n_Click the button below to download._"

    await status_msg.edit_text(
        caption + note,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )


# ── Error Handler ─────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception:", exc_info=context.error)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
