# 🐋 Solana Whale Tracker Bot - Complete Setup Guide

## 📋 Overview

This bot tracks Solana whale wallets using Helius and posts buy/sell alerts to your WizTheoryLabs Telegram group.

**Features:**
- Real-time whale transaction tracking via Helius webhooks
- Clean buy/sell alerts in Ray Purple style
- Admin commands to manage whales without redeploying
- Automatic deduplication
- Rate limiting to prevent spam

---

## 🎯 STEP 1: Get Your Telegram Bot Token

**1.** Open Telegram and search for **@BotFather**

**2.** Send `/newbot`

**3.** Follow prompts:
   - Bot name: `WizTheoryLabs Whale Tracker`
   - Username: `wiztheorylabs_whale_bot` (or similar, must be unique)

**4.** Copy the bot token (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

**5.** Save this token - you'll need it!

---

## 🎯 STEP 2: Get Your Telegram Chat ID

You need the chat ID of your WizTheoryLabs group.

**Method 1: Using Your Bot**

**1.** Add your bot to the WizTheoryLabs group:
   - Go to group
   - Add members → search for your bot
   - Add it

**2.** Send a message in the group: `/start`

**3.** Go to this URL in your browser (replace TOKEN with your bot token):
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```

**4.** Look for `"chat":{"id":-1001234567890` - that's your chat ID (includes the minus sign!)

**5.** Save this chat ID

**Method 2: Using @userinfobot**

**1.** Add @userinfobot to your WizTheoryLabs group

**2.** It will show the group chat ID

**3.** Remove the bot after

---

## 🎯 STEP 3: Make Bot an Admin in Your Group

**CRITICAL:** The bot MUST be an admin to post messages!

**1.** Go to WizTheoryLabs group

**2.** Tap group name → **Administrators**

**3.** Tap **Add Administrator**

**4.** Select your bot

**5.** Give it **only** these permissions:
   - ✅ Post Messages
   - ❌ Everything else can be OFF

**6.** Save

---

## 🎯 STEP 4: Get Your Telegram User ID (For Admin Commands)

**1.** Open Telegram and search for **@userinfobot**

**2.** Send `/start`

**3.** It will reply with your user ID (e.g., `123456789`)

**4.** Save this - you'll use it for ADMIN_USER_IDS

**5.** If you have multiple admins, get their user IDs too

---

## 🎯 STEP 5: Set Up Helius

**1.** Go to https://helius.dev

**2.** Sign up / Log in

**3.** Create a new project or use existing

**4.** Get your API key from dashboard

**5.** Go to **Webhooks** section

**6.** Click **Create Webhook**

**7.** Configure:
   - **Webhook Type:** Enhanced Transactions
   - **Account Addresses:** Add all 4 whale wallets:
     ```
     DNfuF1L62WWyW3pNakVkyGGFzVVhj4Yr52jSmdTyeBHm
     8zFZHuSRuDpuAR7J6FzwyF3vKNx4CVW3DFHJerQhc7Zd
     EwTNPYTuwxMzrvL19nzBsSLXdAoEmVBKkisN87csKgtt
     AVAZvHLR2PcWpDf8BXY4rVxNHYRBytycHkcB5z5QNXYm
     ```
   - **Webhook URL:** (You'll set this after deployment - see Step 7)
   - **Transaction Types:** Select "Any" or "SWAP" specifically

**8.** Save webhook (you'll update the URL after deployment)

---

## 🎯 STEP 6: Deploy to Railway

**1.** Go to https://railway.app and sign up/login

**2.** Click **"New Project"** → **"Deploy from GitHub repo"**

**3.** Connect your GitHub and create a new repo for this code

**4.** Upload all the bot files to your GitHub repo:
   - `whale_bot.py`
   - `database.py`
   - `parser.py`
   - `formatter.py`
   - `helius_handler.py`
   - `requirements.txt`

**5.** In Railway, select your repo

**6.** Railway will detect Python and deploy

**7.** Add environment variables in Railway settings:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=-1001234567890
   ADMIN_USER_IDS=123456789,987654321
   WEBHOOK_PORT=5000
   ```

**8.** Set **Start Command** in Railway:
   ```
   python whale_bot.py
   ```

**9.** Deploy!

---

## 🎯 STEP 7: Configure Helius Webhook URL

**1.** After Railway deploys, get your app's public URL:
   - Go to Railway → Your service → Settings → Domains
   - You'll see something like: `your-app.up.railway.app`

**2.** Your webhook URL is:
   ```
   https://your-app.up.railway.app/webhook
   ```

**3.** Go back to Helius dashboard → Webhooks

**4.** Edit your webhook

**5.** Set **Webhook URL** to your Railway URL + `/webhook`

**6.** Save

**7.** Test webhook:
   - Helius dashboard → Webhooks → Test
   - Should show 200 OK

---

## 🎯 STEP 8: Test Your Bot!

**1.** Go to your WizTheoryLabs Telegram group

**2.** Send: `/help`
   - Bot should respond with help message

**3.** Send: `/whales`
   - Should show list of tracked whales

**4.** Wait for a whale to make a trade!
   - When they do, bot will post alert automatically

**5.** Test admin commands:
   ```
   /pausewhale Gake
   /resumewhale Gake
   /whales
   ```

---

## 🛠️ Admin Commands Reference

**View Commands (Anyone):**
- `/whales` - List all tracked whales
- `/help` - Show help message

**Management Commands (Admin Only):**
- `/addwhale <label> <address>` - Add new whale
  - Example: `/addwhale MyWhale ABC123...`
  
- `/removewhale <label or address>` - Remove whale
  - Example: `/removewhale Gake`
  
- `/pausewhale <label or address>` - Pause tracking
  - Example: `/pausewhale Gake`
  
- `/resumewhale <label or address>` - Resume tracking
  - Example: `/resumewhale Gake`
  
- `/pauseall` - Pause all whales
  
- `/resumeall` - Resume all whales

---

## 📊 Message Format Example

```
🟢 BUY MEME on PumpSwap
Gake

Gake swapped 15.50 SOL for 1.2M MEME
Avg: $0.000013 (est)

[Dexscreener] [Pump Address]
```

---

## 🔧 Troubleshooting

**Bot doesn't respond to commands:**
- Check bot is admin in group
- Check TELEGRAM_CHAT_ID is correct (includes minus sign!)
- Check Railway logs for errors

**No whale alerts posting:**
- Check Helius webhook is configured correctly
- Check whale addresses in Helius match database
- Check Railway logs for errors
- Test Helius webhook from their dashboard

**"Admin only" errors:**
- Check your user ID is in ADMIN_USER_IDS
- Make sure IDs are comma-separated with NO spaces

**Webhook errors:**
- Check Railway app is running
- Check webhook URL is correct
- Check Helius webhook status in dashboard

---

## 📝 File Structure

```
whale_tracker/
├── whale_bot.py           # Main bot file
├── database.py            # SQLite whale management
├── parser.py              # Transaction parser (buy/sell logic)
├── formatter.py           # Telegram message formatter
├── helius_handler.py      # Helius webhook handler
├── requirements.txt       # Python dependencies
└── whale_tracker.db       # SQLite database (auto-created)
```

---

## 🚀 Expanding The Bot

**To add more whales:**
- Use `/addwhale` command (no redeployment needed!)
- OR add to Helius webhook manually

**To customize message format:**
- Edit `formatter.py` → `format_trade_message()`

**To add more features:**
- Bot is modular - easy to extend
- Add new commands in `whale_bot.py`
- Add new data sources in parser

---

## ✅ Success Checklist

- [ ] Bot token obtained from @BotFather
- [ ] Chat ID obtained for WizTheoryLabs group
- [ ] Bot added to group as admin
- [ ] Admin user IDs collected
- [ ] Helius account created + API key
- [ ] Helius webhook created with whale addresses
- [ ] Code deployed to Railway
- [ ] Environment variables set in Railway
- [ ] Helius webhook URL updated with Railway URL
- [ ] Bot responds to /help command
- [ ] Bot shows whales with /whales command
- [ ] Waiting for first whale trade alert!

---

## 🆘 Need Help?

**Check Railway logs:**
1. Railway dashboard → Your service → Logs
2. Look for ERROR messages
3. Shows what's failing

**Check Helius webhook:**
1. Helius dashboard → Webhooks
2. Check "Recent Deliveries"
3. Should show 200 OK responses

**Common fixes:**
- Restart Railway service
- Double-check environment variables
- Verify bot is admin in group
- Test Helius webhook manually

---

## 🎉 You're Done!

Your whale tracker is now live and will automatically post alerts when your tracked whales trade on Pump.fun/PumpSwap!

Enjoy your real-time whale tracking! 🐋💰
