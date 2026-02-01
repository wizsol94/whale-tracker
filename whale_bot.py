"""
Solana Whale Tracker Bot for WizTheoryLabs
Tracks whale transactions and posts to Telegram group
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

# Configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')  # WizTheoryLabs group chat ID
TELEGRAM_THREAD_ID = os.getenv('TELEGRAM_THREAD_ID')  # Whale Tracking topic ID (164)
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
        self.rate_limiter = asyncio.Semaphore(20)  # Max 20 messages per batch
    
    async def initialize(self):
        """Initialize Telegram bot"""
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.bot = self.application.bot
        
        # Add command handlers
        self.application.add_handler(CommandHandler("whales", self.cmd_whales))
        self.application.add_handler(CommandHandler("wally", self.cmd_wally))
        self.application.add_handler(CommandHandler("addwhale", self.cmd_add_whale))
        self.application.add_handler(CommandHandler("removewhale", self.cmd_remove_whale))
        self.application.add_handler(CommandHandler("pausewhale", self.cmd_pause_whale))
        self.application.add_handler(CommandHandler("resumewhale", self.cmd_resume_whale))
        self.application.add_handler(CommandHandler("pauseall", self.cmd_pause_all))
        self.application.add_handler(CommandHandler("resumeall", self.cmd_resume_all))
        
        logger.info("Bot initialized")
        if TELEGRAM_THREAD_ID:
            logger.info(f"Whale alerts will post to topic ID: {TELEGRAM_THREAD_ID}")
    
    async def process_transaction(self, tx_data: dict, whale_address: str):
        """Process incoming transaction from Helius webhook"""
        try:
            signature = tx_data.get('signature', 'unknown')
            
            # Check if already processed (deduplication)
            if db.is_tx_processed(signature):
                logger.debug(f"Transaction already processed: {signature}")
                return
            
            # Get whale info from database
            whale = db.get_whale_by_address(whale_address)
            if not whale:
                logger.warning(f"Received transaction for unknown whale: {whale_address}")
                return
            
            # Check if whale is active
            if not whale['active']:
                logger.debug(f"Skipping transaction for paused whale: {whale['label']}")
                return
            
            # Parse transaction
            trade = parser.parse_transaction(tx_data, whale_address)
            if not trade:
                logger.debug(f"Could not parse trade from transaction: {signature}")
                return
            
            # Format message
            message, reply_markup = formatter.format_trade_message(trade, whale['label'])
            
            # Send to Telegram group with rate limiting
            async with self.rate_limiter:
                try:
                    # FIXED: Add message_thread_id to post to specific topic
                    send_kwargs = {
                        'chat_id': TELEGRAM_CHAT_ID,
                        'text': message,
                        'parse_mode': ParseMode.HTML,
                        'reply_markup': reply_markup,
                        'disable_web_page_preview': True
                    }
                    
                    # Add thread_id if configured (posts to specific topic)
                    if TELEGRAM_THREAD_ID:
                        send_kwargs['message_thread_id'] = int(TELEGRAM_THREAD_ID)
                    
                    await self.bot.send_message(**send_kwargs)
                    logger.info(f"Posted {trade['type']} alert for {whale['label']} to topic {TELEGRAM_THREAD_ID or 'main chat'}")
                except TelegramError as e:
                    logger.error(f"Failed to send Telegram message: {e}")
                    # Don't mark as processed if send failed
                    return
            
            # Mark transaction as processed
            db.mark_tx_processed(signature)
            
        except Exception as e:
            logger.error(f"Error processing transaction: {e}", exc_info=True)
    
    # ========================================
    # TELEGRAM COMMAND HANDLERS
    # ========================================
    
    async def cmd_whales(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /whales command"""
        whales = db.get_all_whales()
        message = formatter.format_whales_list(whales)
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_add_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addwhale command (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only command")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /addwhale <label> <address>\n"
                "Example: /addwhale MyWhale ABC123..."
            )
            return
        
        label = context.args[0]
        address = context.args[1]
        
        if db.add_whale(label, address):
            await update.message.reply_text(f"✅ Added whale: {label}")
            logger.info(f"Admin {user_id} added whale: {label}")
        else:
            await update.message.reply_text(f"❌ Whale already exists: {label} or {address}")
    
    async def cmd_remove_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /removewhale command (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only command")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: /removewhale <label or address>\n"
                "Example: /removewhale Gake"
            )
            return
        
        identifier = context.args[0]
        
        if db.remove_whale(identifier):
            await update.message.reply_text(f"✅ Removed whale: {identifier}")
            logger.info(f"Admin {user_id} removed whale: {identifier}")
        else:
            await update.message.reply_text(f"❌ Whale not found: {identifier}")
    
    async def cmd_pause_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pausewhale command (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only command")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: /pausewhale <label or address>\n"
                "Example: /pausewhale Gake"
            )
            return
        
        identifier = context.args[0]
        
        if db.set_whale_active(identifier, False):
            await update.message.reply_text(f"⏸️ Paused whale: {identifier}")
            logger.info(f"Admin {user_id} paused whale: {identifier}")
        else:
            await update.message.reply_text(f"❌ Whale not found: {identifier}")
    
    async def cmd_resume_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resumewhale command (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only command")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text(
                "Usage: /resumewhale <label or address>\n"
                "Example: /resumewhale Gake"
            )
            return
        
        identifier = context.args[0]
        
        if db.set_whale_active(identifier, True):
            await update.message.reply_text(f"✅ Resumed whale: {identifier}")
            logger.info(f"Admin {user_id} resumed whale: {identifier}")
        else:
            await update.message.reply_text(f"❌ Whale not found: {identifier}")
    
    async def cmd_pause_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pauseall command (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only command")
            return
        
        count = db.pause_all_whales()
        await update.message.reply_text(f"⏸️ Paused all {count} whales")
        logger.info(f"Admin {user_id} paused all whales")
    
    async def cmd_resume_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resumeall command (admin only)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_USER_IDS:
            await update.message.reply_text("⛔ Admin only command")
            return
        
        count = db.resume_all_whales()
        await update.message.reply_text(f"✅ Resumed all {count} whales")
        logger.info(f"Admin {user_id} resumed all whales")
    
    async def cmd_wally(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /wally command - Show Wally whale tracker help"""
        message = formatter.format_wally_help()
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    def run_telegram_bot(self):
        """Run Telegram bot (polling)"""
        logger.info("Starting Telegram bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def run_webhook_server(self):
        """Run Helius webhook server"""
        logger.info("Starting Helius webhook server...")
        
        # Get known whale addresses from database
        whales = db.get_all_whales()
        known_addresses = {whale['address'] for whale in whales}
        logger.info(f"Tracking {len(known_addresses)} whale addresses")
        
        webhook_handler = HeliusWebhookHandler(
            on_transaction=self.process_transaction,
            known_whales=known_addresses
        )
        webhook_handler.run(port=WEBHOOK_PORT)


def main():
    """Main entry point"""
    # Fix for event loop issue
    import nest_asyncio
    nest_asyncio.apply()
    
    # Validate required environment variables
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    if not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set!")
        return
    
    if not ADMIN_USER_IDS:
        logger.warning("ADMIN_USER_IDS not set - no admin access!")
    
    # Create bot instance
    bot = WhaleTrackerBot()
    
    # Initialize bot
    asyncio.run(bot.initialize())
    
    # Run webhook server in separate thread
    webhook_thread = threading.Thread(target=bot.run_webhook_server, daemon=True)
    webhook_thread.start()
    
    # Run Telegram bot (blocks)
    bot.run_telegram_bot()


if __name__ == '__main__':
    main()
