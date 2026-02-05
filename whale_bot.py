"""
Multi-Chat Solana Whale Tracker Bot
Supports multiple isolated groups with owner-only controls
"""

import os
import logging
import asyncio
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.error import TelegramError
from telegram.constants import ParseMode
import threading

from db_manager import DatabaseManager
from auth_manager import AuthManager
from parser import TransactionParser
from formatter import MessageFormatter
from helius_handler import HeliusWebhookHandler

# BUILD VERIFICATION
BUILD_ID = "2026-02-04-23:45:00-MULTICHAT-FIX"
BUILD_TIMESTAMP = datetime.now().isoformat()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', 5000))

db = DatabaseManager()
auth = AuthManager()
parser = TransactionParser()
formatter = MessageFormatter()


class MultiChatWhaleBot:
    """Multi-chat whale tracker with per-chat isolation"""
    
    def __init__(self):
        self.bot = None
        self.application = None
        self.rate_limiter = asyncio.Semaphore(20)
    
    async def initialize(self):
        """Initialize Telegram bot"""
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.bot = self.application.bot
        
        auth_filter = filters.Chat(chat_id=list(auth.allowed_chat_ids)) if auth.allowed_chat_ids else filters.ALL
        
        self.application.add_handler(CommandHandler("start", self.cmd_start, filters=auth_filter))
        self.application.add_handler(CommandHandler("help", self.cmd_help, filters=auth_filter))
        self.application.add_handler(CommandHandler("version", self.cmd_version, filters=auth_filter))
        self.application.add_handler(CommandHandler("status", self.cmd_status, filters=auth_filter))
        self.application.add_handler(CommandHandler("getchatid", self.cmd_get_chat_id, filters=auth_filter))
        self.application.add_handler(CommandHandler("whales", self.cmd_whales, filters=auth_filter))
        self.application.add_handler(CommandHandler("addwhale", self.cmd_add_whale, filters=auth_filter))
        self.application.add_handler(CommandHandler("removewhale", self.cmd_remove_whale, filters=auth_filter))
        self.application.add_handler(CommandHandler("pausewhale", self.cmd_pause_whale, filters=auth_filter))
        self.application.add_handler(CommandHandler("resumewhale", self.cmd_resume_whale, filters=auth_filter))
        self.application.add_handler(CommandHandler("pauseall", self.cmd_pause_all, filters=auth_filter))
        self.application.add_handler(CommandHandler("resumeall", self.cmd_resume_all, filters=auth_filter))
        self.application.add_handler(CommandHandler("alertson", self.cmd_alerts_on, filters=auth_filter))
        self.application.add_handler(CommandHandler("alertsoff", self.cmd_alerts_off, filters=auth_filter))
        
        self.application.add_handler(MessageHandler(filters.ALL, self.handle_unauthorized))
        
        logger.info("Bot initialized with multi-chat support")
    
    async def handle_unauthorized(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages from unauthorized chats"""
        chat_id = auth.get_chat_id_from_update(update)
        if not auth.is_chat_allowed(chat_id):
            await update.message.reply_text(
                "⛔ Wally is not authorized for this chat.\n\n"
                "This bot only operates in pre-approved groups."
            )
            logger.warning(f"Unauthorized access attempt from chat {chat_id}")
    
    async def process_transaction(self, tx_data: dict, whale_address: str):
        """Process incoming transaction from Helius webhook"""
        try:
            signature = tx_data.get('signature', 'unknown')
            whale_entries = db.get_whale_by_address(whale_address)
            
            if not whale_entries:
                return
            
            trade = parser.parse_transaction(tx_data, whale_address)
            if not trade:
                return
            
            for whale_entry in whale_entries:
                chat_id = whale_entry['chat_id']
                
                if db.is_tx_processed(chat_id, signature):
                    continue
                
                settings = db.get_or_create_chat_settings(chat_id)
                if not settings['alerts_enabled'] or not whale_entry['active']:
                    continue
                
                message, reply_markup = formatter.format_trade_message(trade, whale_entry['label'])
                
                async with self.rate_limiter:
                    try:
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=ParseMode.HTML,
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
                        logger.info(f"Posted alert for {whale_entry['label']} to chat {chat_id}")
                    except TelegramError as e:
                        logger.error(f"Failed to send to chat {chat_id}: {e}")
                        continue
                
                db.mark_tx_processed(chat_id, signature)
        
        except Exception as e:
            logger.error(f"Error processing transaction: {e}", exc_info=True)
    
    def _check_owner(self, update: Update) -> bool:
        """Check if user is owner"""
        user_id = auth.get_user_id_from_update(update)
        return auth.is_owner(user_id)
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "Private"
        db.get_or_create_chat_settings(chat_id, chat_name)
        await update.message.reply_text(
            "🐋 <b>Wally Whale Tracker</b>\n\nUse /help for commands.",
            parse_mode=ParseMode.HTML
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        message = formatter.format_help_message()
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_version(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /version command - show build info and DB status"""
        chat_id = update.effective_chat.id
        
        # Get DB fingerprint
        db_info = db.get_db_fingerprint()
        
        message = (
            f"🔧 <b>Wally Version Info</b>\n\n"
            f"<b>Build ID:</b> <code>{BUILD_ID}</code>\n"
            f"<b>Started:</b> {BUILD_TIMESTAMP[:19]}\n"
            f"<b>Environment:</b> Railway\n\n"
            f"<b>Database:</b>\n"
            f"  Name: <code>{db_info['database']}</code>\n"
            f"  Host: <code>{db_info['host']}</code>\n"
            f"  Port: <code>{db_info['port']}</code>\n"
            f"  Status: {db_info['status']}\n\n"
            f"<b>Your Chat ID:</b> <code>{chat_id}</code>\n"
            f"<b>Whales in DB:</b> {db_info['total_whales']} total\n"
            f"<b>Whales in this chat:</b> {db_info['chat_whale_count'].get(chat_id, 0)}"
        )
        
        logger.info(f"[CMD_VERSION] chat_id={chat_id}, build={BUILD_ID}, db={db_info['database']}")
        
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "Private"
        settings = db.get_or_create_chat_settings(chat_id, chat_name)
        whales = db.get_whales_for_chat(chat_id)
        alerts_status = "🟢 ON" if settings['alerts_enabled'] else "🔴 OFF"
        active = sum(1 for w in whales if w['active'])
        
        message = (
            f"📊 <b>Chat Status</b>\n\n"
            f"<b>Chat:</b> {chat_name}\n"
            f"<b>Chat ID:</b> <code>{chat_id}</code>\n"
            f"<b>Alerts:</b> {alerts_status}\n"
            f"<b>Tracked Whales:</b> {len(whales)} ({active} active)"
        )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_get_chat_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /getchatid command"""
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "Private"
        message = (
            f"📋 <b>Chat Information</b>\n\n"
            f"<b>Name:</b> {chat_name}\n"
            f"<b>Chat ID:</b> <code>{chat_id}</code>\n\n"
            f"<i>Add to ALLOWED_CHAT_IDS in Railway</i>"
        )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_whales(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /whales command"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        logger.info(f"[CMD_WHALES] chat_id={chat_id}, user_id={user_id}")
        
        whales = db.get_whales_for_chat(chat_id)
        message = formatter.format_whales_list(whales)
        
        logger.info(f"[CMD_WHALES] Returning {len(whales)} whales to user")
        
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    
    async def cmd_add_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /addwhale command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        # Clean args: remove duplicate command tokens
        args = [arg for arg in context.args if not arg.startswith('/')]
        
        logger.info(f"[CMD_ADDWHALE] chat_id={chat_id}, user_id={user_id}, args={args}")
        
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /addwhale <label> <address>\n"
                "Example: /addwhale Gake DNfuF1L6..."
            )
            return
        
        label = args[0]
        address = args[1]
        
        logger.info(f"[CMD_ADDWHALE] Attempting to add: label={label}, address={address[:20]}...")
        
        if db.add_whale(chat_id, label, address):
            await update.message.reply_text(f"✅ Added whale: {label}")
            logger.info(f"[CMD_ADDWHALE] ✅ Success: {label} added to chat {chat_id}")
        else:
            await update.message.reply_text(f"❌ Whale already exists in this chat")
            logger.warning(f"[CMD_ADDWHALE] ❌ Failed: {label} already exists in chat {chat_id}")
    
    async def cmd_remove_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /removewhale command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /removewhale <label>")
            return
        
        chat_id = update.effective_chat.id
        identifier = context.args[0]
        
        if db.remove_whale(chat_id, identifier):
            await update.message.reply_text(f"✅ Removed: {identifier}")
        else:
            await update.message.reply_text(f"❌ Not found: {identifier}")
    
    async def cmd_pause_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pausewhale command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /pausewhale <label>")
            return
        
        chat_id = update.effective_chat.id
        if db.set_whale_active(chat_id, context.args[0], False):
            await update.message.reply_text(f"⏸️ Paused: {context.args[0]}")
        else:
            await update.message.reply_text(f"❌ Not found")
    
    async def cmd_resume_whale(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resumewhale command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Usage: /resumewhale <label>")
            return
        
        chat_id = update.effective_chat.id
        if db.set_whale_active(chat_id, context.args[0], True):
            await update.message.reply_text(f"✅ Resumed: {context.args[0]}")
        else:
            await update.message.reply_text(f"❌ Not found")
    
    async def cmd_pause_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pauseall command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        count = db.pause_all_whales(update.effective_chat.id)
        await update.message.reply_text(f"⏸️ Paused all {count} whales")
    
    async def cmd_resume_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resumeall command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        count = db.resume_all_whales(update.effective_chat.id)
        await update.message.reply_text(f"✅ Resumed all {count} whales")
    
    async def cmd_alerts_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alertson command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        db.set_alerts_enabled(update.effective_chat.id, True)
        await update.message.reply_text("🔔 Alerts enabled")
    
    async def cmd_alerts_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alertsoff command (owner only)"""
        if not self._check_owner(update):
            await update.message.reply_text("⛔ Only the owner can change Wally settings")
            return
        
        db.set_alerts_enabled(update.effective_chat.id, False)
        await update.message.reply_text("🔕 Alerts disabled")
    
    def run_telegram_bot(self):
        """Run Telegram bot"""
        logger.info("Starting Telegram bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def run_webhook_server(self):
        """Run Helius webhook server"""
        logger.info("Starting webhook server...")
        webhook_handler = HeliusWebhookHandler(on_transaction=self.process_transaction)
        webhook_handler.run(port=WEBHOOK_PORT)


def main():
    """Main entry point"""
    import nest_asyncio
    nest_asyncio.apply()
    
    # Log build info
    logger.info("=" * 60)
    logger.info(f"🚀 WALLY WHALE TRACKER STARTING")
    logger.info(f"📦 BUILD_ID: {BUILD_ID}")
    logger.info(f"🕐 BUILD_TIMESTAMP: {BUILD_TIMESTAMP}")
    logger.info("=" * 60)
    
    if not TELEGRAM_BOT_TOKEN or not os.getenv('DATABASE_URL') or not os.getenv('OWNER_TELEGRAM_USER_ID'):
        logger.error("Missing required environment variables!")
        return
    
    logger.info(f"Allowed chats: {auth.allowed_chat_ids or 'ALL'}")
    logger.info(f"Owner ID: {auth.owner_user_id}")
    
    bot = MultiChatWhaleBot()
    asyncio.run(bot.initialize())
    
    webhook_thread = threading.Thread(target=bot.run_webhook_server, daemon=True)
    webhook_thread.start()
    
    bot.run_telegram_bot()


if __name__ == '__main__':
    main()
