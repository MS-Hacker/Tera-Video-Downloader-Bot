# 🎬 TeraBox Telegram Bot — Full Deployment Guide

A Telegram bot that fetches & downloads public TeraBox video links and sends
them directly to your Telegram chat.

---

## 📁 Project Structure

```
terabox_bot/
├── bot.py            ← Main bot code
├── requirements.txt  ← Python dependencies
├── Procfile          ← For Railway/Heroku
├── runtime.txt       ← Python version
└── README.md         ← This file
```

---

## 🔑 STEP 1 — Create Your Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g. `TeraBox Downloader`)
4. Choose a username (must end in `bot`, e.g. `myterabox_bot`)
5. BotFather will give you a **token** like:
   ```
   7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. **Copy this token** — you'll need it in the next step.

---

## 🚀 STEP 2 — Deploy on Railway (FREE, Recommended)

Railway gives you a free always-on server — perfect for Telegram bots.

### 2a. Sign Up
- Go to **https://railway.app**
- Sign up with GitHub (free account)

### 2b. Upload Your Code to GitHub
1. Go to **https://github.com** → Create a new repository (e.g. `terabox-bot`)
2. Upload all 4 files: `bot.py`, `requirements.txt`, `Procfile`, `runtime.txt`

### 2c. Deploy on Railway
1. In Railway dashboard → click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Select your `terabox-bot` repo
4. Railway will detect it and start building

### 2d. Set Environment Variable
1. In Railway → go to your project → click **"Variables"** tab
2. Click **"New Variable"**
3. Set:
   - **Name:** `BOT_TOKEN`
   - **Value:** paste your BotFather token
4. Click **Add** → Railway will automatically restart

### 2e. Verify
- Go to the **"Deployments"** tab → you should see `✅ Active`
- Check the logs — you should see: `Bot is running...`

✅ **Your bot is now live 24/7!**

---

## 🖥️ STEP 2 (Alternative) — Run Locally on Your PC

If you just want to test on your own computer:

```bash
# 1. Install Python 3.10+ from https://python.org

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your token (Windows CMD)
set BOT_TOKEN=your_token_here

# 3. Set your token (Linux/Mac Terminal)
export BOT_TOKEN=your_token_here

# 4. Run the bot
python bot.py
```

The bot will run as long as your terminal is open.

---

## 🤖 STEP 3 — Use Your Bot

1. Open Telegram → search for your bot by its username
2. Send `/start`
3. Paste any **public** TeraBox link, e.g.:
   ```
   https://teraboxapp.com/s/xxxxxxxxxxxxx
   ```
4. The bot will:
   - Fetch the file info
   - If ≤ 50 MB → send the video directly in Telegram
   - If > 50 MB → send a direct download button

---

## ⚙️ How It Works

1. You send a TeraBox public link
2. Bot calls the **TeraBox public API** to get file metadata + download URL
3. For small videos → downloads and sends via Telegram
4. For large videos → gives you a direct download link button

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `BOT_TOKEN not set` | Make sure the env variable is set correctly |
| `Failed to fetch file info` | The link may be private, expired, or a folder |
| Bot not responding | Check Railway logs for errors |
| Video not sending | File may be > 50 MB; use the download button instead |

---

## 📝 Notes

- Only **public** TeraBox links work (no password-protected links)
- Telegram bots can only send files up to **50 MB** directly
- The bot uses TeraBox's own public API — no scraping required
- For personal use only; respect TeraBox's terms of service

---

## 💡 Optional Upgrades

- Add a database to track downloads per user
- Support multiple files / folders
- Add admin commands to whitelist users
- Use webhook mode instead of polling for faster responses
