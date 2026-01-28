"""
Telegram message formatter for whale trades
Formats messages in Ray Purple style
"""

import logging
from typing import Dict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class MessageFormatter:
    
    @staticmethod
    def format_trade_message(trade: Dict, whale_label: str) -> tuple:
        """
        Format trade into Telegram message
        Returns: (message_text, reply_markup)
        """
        try:
            trade_type = trade['type']
            token_symbol = trade['token_symbol']
            token_amount = trade['token_amount']
            sol_amount = trade['sol_amount']
            token_mint = trade['token_mint']
            
            # Format numbers nicely
            token_amount_str = MessageFormatter._format_number(token_amount)
            sol_amount_str = MessageFormatter._format_number(sol_amount, decimals=3)
            
            # Emoji for trade type
            emoji = "🟢" if trade_type == "BUY" else "🔴"
            
            # Header
            header = f"{emoji} <b>{trade_type} {token_symbol} on PumpSwap</b>\n"
            
            # Whale label
            whale_line = f"<b>{whale_label}</b>\n\n"
            
            # Trade details
            if trade_type == "BUY":
                action = f"{whale_label} swapped {sol_amount_str} SOL for {token_amount_str} {token_symbol}"
            else:  # SELL
                action = f"{whale_label} swapped {token_amount_str} {token_symbol} for {sol_amount_str} SOL"
            
            # Estimate price (optional, basic calculation)
            try:
                if token_amount > 0:
                    price_per_token = sol_amount / token_amount
                    # Very rough USD estimate (assuming SOL = $100, adjust in real deployment)
                    price_usd = price_per_token * 100
                    price_line = f"\nAvg: ${MessageFormatter._format_number(price_usd, decimals=6)} (est)"
                else:
                    price_line = ""
            except:
                price_line = ""
            
            # Construct full message
            message = header + whale_line + action + price_line
            
            # Inline keyboard with TWO buttons only
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Dexscreener",
                        url=f"https://dexscreener.com/solana/{token_mint}"
                    ),
                    InlineKeyboardButton(
                        "Pump Address",
                        url=f"https://pump.fun/{token_mint}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            return message, reply_markup
            
        except Exception as e:
            logger.error(f"Error formatting message: {e}", exc_info=True)
            # Fallback message
            message = f"{emoji} {trade_type} detected for {whale_label}"
            return message, None
    
    @staticmethod
    def _format_number(num: float, decimals: int = 2) -> str:
        """Format number with appropriate decimals and commas"""
        if num >= 1_000_000:
            return f"{num/1_000_000:.{decimals}f}M"
        elif num >= 1_000:
            return f"{num/1_000:.{decimals}f}K"
        elif num >= 1:
            return f"{num:,.{decimals}f}"
        else:
            # For very small numbers, show more decimals
            return f"{num:.{min(decimals + 4, 8)}f}"
    
    @staticmethod
    def format_whales_list(whales: list) -> str:
        """Format list of whales for /whales command"""
        if not whales:
            return "No whales configured."
        
        message = "<b>🐋 Tracked Whales:</b>\n\n"
        
        for whale in whales:
            status = "✅ Active" if whale['active'] else "⏸️ Paused"
            address_short = whale['address'][:8] + "..." + whale['address'][-6:]
            message += f"<b>{whale['label']}</b>\n"
            message += f"Status: {status}\n"
            message += f"Address: <code>{address_short}</code>\n\n"
        
        return message
    
    @staticmethod
    def format_help_message() -> str:
        """Format help message"""
        return """<b>🐋 Whale Tracker Bot Commands</b>

<b>View Commands:</b>
/whales - List all tracked whales
/help - Show this help message

<b>Management Commands (Admin Only):</b>
/addwhale &lt;label&gt; &lt;address&gt; - Add new whale
/removewhale &lt;label/address&gt; - Remove whale
/pausewhale &lt;label/address&gt; - Pause tracking
/resumewhale &lt;label/address&gt; - Resume tracking
/pauseall - Pause all whales
/resumeall - Resume all whales

<b>Example:</b>
<code>/addwhale MyWhale ABC123...</code>
"""
