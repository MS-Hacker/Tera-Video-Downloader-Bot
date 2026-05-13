import os
import re
import json
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
NDUS_COOKIE = os.environ.get("NDUS_COOKIE", "")
MAX_MB      = 45

TERABOX_DOMAINS = [
    "terabox.com","teraboxapp.com","terabox.app","1024terabox.com",
    "terafileshare.com","4funbox.com","mirrobox.com","nephobox.com",
    "freeterabox.com","www.terabox.com","www.1024terabox.com",
]

def is_terabox(url): return any(d in url for d in TERABOX_DOMAINS)

def human_size(b):
    for u in ["B","KB","MB","GB"]:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def extract_surl(url):
    m = re.search(r"[?&]surl=([^&]+)", url)
    if m: return m.group(1)
    m = re.search(r"/s/([^/?&#]+)", url)
    if m: return m.group(1)
    return None

def make_session(ndus):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    s.cookies.set("ndus", ndus, domain=".terabox.com")
    s.cookies.set("ndus", ndus, domain=".1024terabox.com")
    return s

def get_info(url, ndus):
    session = make_session(ndus)
    surl = extract_surl(url)
    if not surl:
        logger.warning("Could not extract surl from %s", url)
        return None

    # ── Step 1: get jsToken by visiting the share page ──────────────────────
    try:
        share_url = f"https://www.1024terabox.com/sharing/link?surl={surl}"
        r = session.get(share_url, timeout=15, allow_redirects=True)
        js_token = ""
        m = re.search(r'locals\.mixin\.jsToken\s*=\s*["\']([^"\']+)["\']', r.text)
        if m:
            js_token = m.group(1)
        else:
            m = re.search(r'"jsToken"\s*:\s*"([^"]+)"', r.text)
            if m: js_token = m.group(1)
        logger.info("jsToken: %s", js_token[:30] if js_token else "NOT FOUND")
    except Exception as e:
        logger.warning("Step 1 failed: %s", e)
        js_token = ""

    # ── Step 2: call shorturlinfo API ────────────────────────────────────────
    for base in ["https://www.1024terabox.com", "https://www.terabox.com", "https://teraboxapp.com"]:
        try:
            params = {"surl": surl, "web": "1", "channel": "dubox", "clienttype": "0"}
            if js_token:
                params["jsToken"] = js_token
            r = session.get(f"{base}/api/shorturlinfo", params=params,
                            headers={"Referer": f"{base}/"}, timeout=15)
            data = r.json()
            logger.info("shorturlinfo [%s]: errno=%s", base, data.get("errno"))

            if data.get("errno") == 0:
                files = data.get("list", [])
                if not files: continue
                f = files[0]
                dlink = f.get("dlink","")
                if dlink:
                    return {
                        "title": f.get("server_filename","video"),
                        "size":  int(f.get("size", 0)),
                        "download_url": dlink,
                    }
        except Exception as e:
            logger.warning("shorturlinfo [%s] failed: %s", base, e)

    # ── Step 3: try /api/share/videoinfo ────────────────────────────────────
    for base in ["https://www.1024terabox.com", "https://www.terabox.com"]:
        try:
            params = {"surl": surl, "type": "video"}
            r = session.get(f"{base}/api/share/videoinfo", params=params,
                            headers={"Referer": f"{base}/"}, timeout=15)
            data = r.json()
            logger.info("videoinfo [%s]: %s", base, str(data)[:200])
            vlist = data.get("vlist") or data.get("list", [])
            if vlist:
                v = vlist[0]
                dl = v.get("play_url") or v.get("dlink","")
                if dl:
                    return {
                        "title": v.get("server_filename","video"),
                        "size":  int(v.get("size",0)),
                        "download_url": dl,
                    }
        except Exception as e:
            logger.warning("videoinfo [%s] failed: %s", base, e)

    # ── Step 4: scrape dlink directly from page HTML ─────────────────────────
    try:
        for share_base in [
            f"https://www.1024terabox.com/sharing/link?surl={surl}",
            f"https://www.terabox.com/sharing/link?surl={surl}",
        ]:
            r = session.get(share_base, timeout=15)
            m = re.search(r'"dlink"\s*:\s*"(https?://[^"]+)"', r.text)
            if m:
                dlink = m.group(1).replace("\\u0026","&")
                title_m = re.search(r'"server_filename"\s*:\s*"([^"]+)"', r.text)
                size_m  = re.search(r'"size"\s*:\s*"?(\d+)"?', r.text)
                return {
                    "title": title_m.group(1) if title_m else "video",
                    "size":  int(size_m.group(1)) if size_m else 0,
                    "download_url": dlink,
                }
    except Exception as e:
        logger.warning("HTML scrape failed: %s", e)

    return None

# ── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = "✅ Cookie set — ready!" if NDUS_COOKIE else "⚠️ NDUS_COOKIE not configured (see /help)"
    await update.message.reply_text(
        f"👋 *TeraBox Downloader Bot*\n\n{ok}\n\nPaste any public TeraBox link to download!",
        parse_mode=ParseMode.MARKDOWN)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Setup*\n\n"
        "Add `NDUS_COOKIE` in Railway Variables:\n"
        "1. Go to terabox.com → login → play a video\n"
        "2. F12 → Application → Cookies → terabox.com\n"
        "3. Copy value of `ndus` cookie\n"
        "4. Paste as `NDUS_COOKIE` in Railway\n\n"
        "/start — check status", parse_mode=ParseMode.MARKDOWN)

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = [u for u in re.findall(r"https?://\S+", text) if is_terabox(u)]

    if not urls:
        await update.message.reply_text("❌ No TeraBox link found. Send a public TeraBox URL.")
        return

    if not NDUS_COOKIE:
        await update.message.reply_text(
            "⚠️ Bot needs `NDUS_COOKIE` configured in Railway. See /help",
            parse_mode=ParseMode.MARKDOWN)
        return

    url = urls[0]
    msg = await update.message.reply_text("🔍 Fetching info...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

    info = get_info(url, NDUS_COOKIE)

    if not info:
        await msg.edit_text(
            "❌ *Failed to fetch video.*\n\n"
            "Please try:\n"
            "• Make sure link is public (opens without login)\n"
            "• Refresh your `NDUS_COOKIE` in Railway (login to terabox.com again and get fresh cookie)\n"
            "• Try a different TeraBox link",
            parse_mode=ParseMode.MARKDOWN)
        return

    title   = info["title"]
    size    = info["size"]
    dlink   = info["download_url"]
    size_mb = size / (1024*1024) if size else 999
    caption = f"📁 *{title}*\n📦 `{human_size(size) if size else 'Unknown'}`"

    if 0 < size_mb <= MAX_MB:
        await msg.edit_text(f"⬇️ Downloading `{title}`...")
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_VIDEO)
        try:
            r = requests.get(dlink, headers={
                "User-Agent": "Mozilla/5.0",
                "Cookie": f"ndus={NDUS_COOKIE}",
            }, stream=True, timeout=120)
            r.raise_for_status()
            await context.bot.send_video(
                update.effective_chat.id, video=r.content,
                caption=caption, parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True)
            await msg.delete()
            return
        except Exception as e:
            logger.error("Send video failed: %s", e)

    kb = [[InlineKeyboardButton("⬇️ Download Video", url=dlink)]]
    note = "\n\n_Too large for Telegram — click below to download._" if size_mb > MAX_MB else "\n\n_Click below to download._"
    await msg.edit_text(caption + note, parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup(kb))

async def err(update, context): logger.error("Error:", exc_info=context.error)

def main():
    if not BOT_TOKEN: raise ValueError("BOT_TOKEN not set!")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_error_handler(err)
    logger.info("Bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
