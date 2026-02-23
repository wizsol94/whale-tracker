"""
Wally v1.0.1 — Whale Tracker Bot
LOCKED TO WHALE-TRACKING CHANNEL ONLY (Thread 164)
NO /help command — only /wally
FIX: Shared db instance passed to webhook handler
"""

import os
import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.error import TelegramError
from telegram.constants import ParseMode
import threading

from database import Database
from parser import TransactionParser
from formatter import MessageFormatter
from helius_handler import HeliusWebhookHandler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================================================================
# HARD-LOCKED CONSTANTS - ALERTS AND COMMANDS ONLY GO HERE
# =============================================================================
WHALE_TRACKING_CHAT_ID = -1003004536161  # WizTheoryLabs group
WHALE_TRACKING_THREAD_ID = 164            # Whale-Tracking topic (NOT General which is 1)
# =============================================================================

# Other configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_USER_IDS = [int(id.strip()) for id in os.getenv('ADMIN_USER_IDS', '').split(',') if id.strip()]
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', 5000))

# Initialize components
db = Database()
parser = TransactionParser()
formatter = MessageFormatter()


class WhaleTrackerBot:
    
    def __init__(self):
        self.bot = None
        self.application = None
        self.rate_limiter = asyncio.Semaphore(20)
    
    def _is_whale_tracking_channel(self, update: Update) -> bool:
        """Check if message is from Whale-Tracking channel (Thread 164) ONLY"""
        if not update.effective_chat or not update.message:
            return False
        
        chat_id = update.effective_chat.id
        thread_id = update.message.message_thread_id
        
        # Must be correct group AND correct thread
        if chat_id != WHALE_TRACKING_CHAT_ID:
            return False
        
        if thread_id != WHALE_TRACKING_THREAD_ID:
            return False
        
        return True
    
    async def initialize(self):
        """Initialize Telegram bot"""
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.bot = self.application.bot
        
        # Command handlers - ALL check channel before responding
        # NO /help command - only /wally
        self.application.add_handler(CommandHandler("wally", self.cmd_wally))
        self.application.add_handler(CommandHandler("whales", self.cmd_whales))
        self.application.add_handler(CommandHandler("addwhale", self.cmd_add_whale))
        self.application.add_handler(CommandHandler("removewhale", self.cmd_remove_whale))
        self.application.add_handler(CommandHandler("pausewhale", self.cmd_pause_whale))
        self.application.add_handler(CommandHandler("resumewhale", self.cmd_resume_whale))
        self.application.add_handler(CommandHandler("pauseall", self.cmd_pause_all))
        self.application.add_handler(CommandHandler("resumeall", self.cmd_resume_all))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        
        logger.info(f"Bot initialized")
        logger.info(f"🔒 LOCKED TO: Chat {WHALE_TRACKING_CHAT_ID} | Thread {WHALE_TRACKING_THREAD_ID}")
    
    async def send_whale_alert(self, message: str, reply_markup=None):
        """Send alert to Whale-Tracking channel ONLY"""
        try:
            await self.bot.send_message(
                chat_id=WHALE_TRACKING_CHAT_ID,
                message_thread_id=WHALE_TRACKING_THREAD_ID,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            logger.info(f"✅ Alert sent to Whale-Tracking")
            return True
        except TelegramError as e:
            logger.error(f"❌ Failed to send alert: {e}")
            return False
    
    async def process_transaction(self, tx_data: dict, whale_address: str):
        """Process incoming transaction from Helius webhook"""
        try:
            signature = tx_data.get('signature', 'unknown')
            
            if db.is_tx_processed(signature):
                logger.debug(f"Transaction already processed: {signature}")
                return
            
            whale = db.get_whale_by_address(whale_address)
            if not whale:
                logger.warning(f"Received transaction for unknown whale: {whale_address}")
                return
            
            if not whale['active']:
                logger.debug(f"Skipping transaction for paused whale: {whale['label']}")
                return
            
            trade = parser.parse_transaction(tx_data, whale_address)
            if not trade:
                logger.debug(f"Could not parse trade from transaction: {signature}")
                return
            
            message, reply_markup = formatter.format_trade_message(trade, whale['label'])
            
            async with self.rate_limiter:
                success = await self.send_whale_alert(message, reply_markup)
                if success:
                    logger.info(f"Posted {trade['type']} alert for {whale['label']}")
                    db.mark_tx_processed(signature)
            
        except Exception as e:
            logger.error(f"Error processing transaction: {e}", exc_info=True)
    
    # =========================================================================
    # COMMAND HANDLERS - ALL CHECK WHALE-TRACKING CHANNEL FIRST
    # =========================================================================
    
    async def cmd_wally(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /wally command - ONLY in Whale-Tracking channel"""
        if not self._is_whale_tracking_channel(update):
            return  # Silent ignore
        
        message = (
            "🐋 <b>Wally Whale Tracker</b>\n\n"
            "<b>Commands:</b>\n"
            "/wally - Show this menu\n"
            "/whales - List tracked whales\n"
            "/status - Bot status\n\n"
            "<b>Admin:</b>\n"
            "/addwhale - Add whale\n"
            "/removewhale - Remove whale\n"
            "/pausewhale - Pause alerts\n"
            "/resumewhale - Resume alerts\n"
            "/pauseall - Pause all\n"
            "/resumeall - Resume all"
        )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_whales(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /whales command"""
        if not self._is_whale_tracking_channel(update):
            return
        
        whales = db.get_all_whales()
        message = formatter.format_whales_list(whales)
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self._is_whale_tracking_channel(update):
            return
        
        whales = db.get_all_whales()
        active = sum(1 for w in whales if w['active'])
        
        message = (
            f"🐋 <b>Wally Status</b>\n\n"
            f"📊 Tracking: {len(whales)} whales ({active} active)\n"
            f"🔔 Alerts: {'ON' if active > 0 else 'OFF'}"
        )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_add_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addwhale command (admin only)"""
        if not self._is_whale_tracking_channel(update):
            return
        
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /addwhale <label> <address>")
            return
        
        label = context.args[0]
        address = context.args[1]
        
        if db.add_whale(label, address):
            await update.message.reply_text(f"✅ Added: {label}")
        else:
            await update.message.reply_text(f"❌ Already exists: {label}")
    
    async def cmd_remove_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /removewhale command (admin only)"""
        if not self._is_whale_tracking_channel(update):
            return
        
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /removewhale <label>")
            return
        
        identifier = context.args[0]
        if db.remove_whale(identifier):
            await update.message.reply_text(f"✅ Removed: {identifier}")
        else:
            await update.message.reply_text(f"❌ Not found: {identifier}")
    
    async def cmd_pause_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pausewhale command (admin only)"""
        if not self._is_whale_tracking_channel(update):
            return
        
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /pausewhale <label>")
            return
        
        identifier = context.args[0]
        if db.set_whale_active(identifier, False):
            await update.message.reply_text(f"⏸️ Paused: {identifier}")
        else:
            await update.message.reply_text(f"❌ Not found: {identifier}")
    
    async def cmd_resume_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resumewhale command (admin only)"""
        if not self._is_whale_tracking_channel(update):
            return
        
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /resumewhale <label>")
            return
        
        identifier = context.args[0]
        if db.set_whale_active(identifier, True):
            await update.message.reply_text(f"✅ Resumed: {identifier}")
        else:
            await update.message.reply_text(f"❌ Not found: {identifier}")
    
    async def cmd_pause_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pauseall command (admin only)"""
        if not self._is_whale_tracking_channel(update):
            return
        
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only")
            return
        
        count = db.pause_all_whales()
        await update.message.reply_text(f"⏸️ Paused all {count} whales")
    
    async def cmd_resume_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resumeall command (admin only)"""
        if not self._is_whale_tracking_channel(update):
            return
        
        user_id = update.effective_user.id
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only")
            return
        
        count = db.resume_all_whales()
        await update.message.reply_text(f"✅ Resumed all {count} whales")
    
    def run_telegram_bot(self):
        """Run Telegram bot (polling)"""
        logger.info("Starting Telegram bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def run_webhook_server(self):
        """Run Helius webhook server"""
        logger.info("Starting Helius webhook server...")
        # FIX: Pass shared db instance to webhook handler
        webhook_handler = HeliusWebhookHandler(on_transaction=self.process_transaction, db=db)
        webhook_handler.run(port=WEBHOOK_PORT)


def main():
    """Main entry point"""
    import nest_asyncio
    nest_asyncio.apply()
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    if not ADMIN_USER_IDS:
        logger.warning("ADMIN_USER_IDS not set!")
    
    logger.info("=" * 60)
    logger.info("🐋 WALLY WHALE TRACKER v1.0.1")
    logger.info("=" * 60)
    logger.info(f"🔒 LOCKED TO: Thread {WHALE_TRACKING_THREAD_ID} (Whale-Tracking)")
    logger.info(f"❌ /help removed — use /wally only")
    logger.info("=" * 60)
    
    bot = WhaleTrackerBot()
    asyncio.run(bot.initialize())
    
    webhook_thread = threading.Thread(target=bot.run_webhook_server, daemon=True)
    webhook_thread.start()
    
    bot.run_telegram_bot()


if __name__ == '__main__':
    main()
