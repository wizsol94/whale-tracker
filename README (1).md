# 🐋 Solana Whale Tracker Bot

Real-time Solana whale tracking bot for Telegram using Helius.

## Features

- 🔍 Tracks 4 whale wallets on Solana
- 📊 Posts clean buy/sell alerts to Telegram
- 🎨 Ray Purple-style formatting
- 🛠️ Admin commands to manage whales
- 🔄 Automatic deduplication
- ⚡ Rate limiting built-in

## Quick Start

1. **Read the full setup guide:** `SETUP_GUIDE.md`

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   - Copy `.env.example` to `.env`
   - Fill in your values

4. **Run locally (testing):**
   ```bash
   python whale_bot.py
   ```

5. **Deploy to Railway** (recommended for production)

## Default Tracked Whales

- **Gake** - `DNfuF1L62WWyW3pNakVkyGGFzVVhj4Yr52jSmdTyeBHm`
- **Trader Pow** - `8zFZHuSRuDpuAR7J6FzwyF3vKNx4CVW3DFHJerQhc7Zd`
- **Gake.Alt** - `EwTNPYTuwxMzrvL19nzBsSLXdAoEmVBKkisN87csKgtt`
- **Ansem** - `AVAZvHLR2PcWpDf8BXY4rVxNHYRBytycHkcB5z5QNXYm`

## Admin Commands

```
/whales              - List tracked whales
/addwhale            - Add new whale
/removewhale         - Remove whale
/pausewhale          - Pause whale tracking
/resumewhale         - Resume whale tracking
/pauseall            - Pause all
/resumeall           - Resume all
/help                - Show help
```

## Architecture

```
whale_bot.py          → Main bot + Telegram commands
helius_handler.py     → Webhook server for Helius
parser.py             → Transaction parser (buy/sell logic)
formatter.py          → Message formatter
database.py           → SQLite whale management
```

## Message Format

```
🟢 BUY TOKEN on PumpSwap
Whale Name

Whale Name swapped 10.5 SOL for 500K TOKEN
Avg: $0.000021 (est)

[Dexscreener] [Pump Address]
```

## Requirements

- Python 3.9+
- Telegram Bot Token
- Helius API Key
- Telegram Group (bot must be admin)
- Railway account (for deployment)

## Documentation

- **Complete Setup:** `SETUP_GUIDE.md`
- **Environment Variables:** `.env.example`

## Support

- Check Railway logs for errors
- Verify Helius webhook configuration
- Ensure bot is admin in Telegram group
- Test commands with /help first

## License

Built for WizTheoryLabs 🧙‍♂️
