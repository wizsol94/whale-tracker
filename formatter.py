"""
Telegram message formatter for whale trades
Formats messages in Ray Purple style with enhanced details
"""

import logging
from typing import Dict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MessageFormatter:
    
    @staticmethod
    def get_token_market_data(token_mint: str) -> Dict:
        """
        Fetch market cap and token age from DexScreener
        Returns: {market_cap, age_hours, age_days}
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_mint}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('pairs') and len(data['pairs']) > 0:
                    pair = data['pairs'][0]
                    
                    # Get market cap
                    market_cap = pair.get('fdv') or pair.get('marketCap', 0)
                    
                    # Get token creation time
                    pair_created_at = pair.get('pairCreatedAt')
                    age_hours = None
                    age_days = None
                    
                    if pair_created_at:
                        try:
                            created_time = datetime.fromtimestamp(pair_created_at / 1000, tz=timezone.utc)
                            current_time = datetime.now(timezone.utc)
                            age_delta = current_time - created_time
                            age_hours = int(age_delta.total_seconds() / 3600)
                            age_days = int(age_delta.days)
                        except:
                            pass
                    
                    return {
                        'market_cap': market_cap,
                        'age_hours': age_hours,
                        'age_days': age_days
                    }
        except Exception as e:
            logger.debug(f"Could not fetch market data for {token_mint}: {e}")
        
        return {'market_cap': None, 'age_hours': None, 'age_days': None}
    
    @staticmethod
    def format_market_cap(market_cap: float) -> str:
        """Format market cap nicely"""
        if market_cap >= 1_000_000:
            return f"${market_cap/1_000_000:.2f}M"
        elif market_cap >= 1_000:
            return f"${market_cap/1_000:.2f}K"
        else:
            return f"${market_cap:.2f}"
    
    @staticmethod
    def format_age(age_days: int, age_hours: int) -> str:
        """Format token age nicely"""
        if age_days is None or age_hours is None:
            return "Unknown"
        
        if age_days > 0:
            remaining_hours = age_hours % 24
            return f"{age_days}d {remaining_hours}h"
        else:
            return f"{age_hours}h"
    
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
            whale_address = trade['whale_address']
            
            # Format numbers nicely
            token_amount_str = MessageFormatter._format_number(token_amount)
            sol_amount_str = MessageFormatter._format_number(sol_amount, decimals=3)
            
            # Calculate USD value (using rough SOL price estimation)
            # In production, you'd want to fetch real-time SOL price
            SOL_PRICE_USD = 100  # Update this or fetch from API
            usd_value = sol_amount * SOL_PRICE_USD
            usd_value_str = MessageFormatter._format_number(usd_value, decimals=2)
            
            # Calculate token price
            price_per_token = 0
            try:
                if token_amount > 0:
                    price_per_token = sol_amount / token_amount
                    price_usd = price_per_token * SOL_PRICE_USD
                    price_line = f"💵 Avg: ${MessageFormatter._format_number(price_usd, decimals=8)}"
                else:
                    price_line = ""
            except:
                price_line = ""
            
            # Fetch market data
            market_data = MessageFormatter.get_token_market_data(token_mint)
            
            # Emoji for trade type
            if trade_type == "BUY":
                emoji = "🟢"
                action_emoji = "💸"
                action = f"{whale_label} swapped {sol_amount_str} SOL (${usd_value_str}) for {token_amount_str} {token_symbol}"
            else:  # SELL
                emoji = "🔴"
                action_emoji = "💰"
                action = f"{whale_label} swapped {token_amount_str} {token_symbol} for {sol_amount_str} SOL (${usd_value_str})"
            
            # Header with more emojis
            header = f"{emoji} <b>{trade_type} {token_symbol} on PumpSwap</b> 🚀\n\n"
            
            # Whale label with emoji and Solscan link
            whale_line = f"🐋 <b>{whale_label}</b>\n🔗 <a href=\"https://solscan.io/account/{whale_address}\">Solscan</a>\n\n"
            
            # Action line with emoji
            action_line = f"{action_emoji} {action}\n"
            
            # Price line
            if price_line:
                action_line += price_line + "\n"
            
            # Market cap and age line
            info_parts = []
            if market_data['market_cap']:
                mc_str = MessageFormatter.format_market_cap(market_data['market_cap'])
                info_parts.append(f"📊 MC: {mc_str}")
            
            if market_data['age_days'] is not None:
                age_str = MessageFormatter.format_age(market_data['age_days'], market_data['age_hours'])
                info_parts.append(f"⏰ Seen: {age_str}")
            
            if info_parts:
                market_line = " | ".join(info_parts) + "\n"
            else:
                market_line = ""
            
            # Contract address line with emoji
            contract_line = f"\n🧾 <b>Contract:</b>\n<code>{token_mint}</code>\n"
            
            # Construct full message
            message = header + whale_line + action_line + market_line + contract_line
            
            # Inline keyboard with buttons
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📈 Dexscreener",
                        url=f"https://dexscreener.com/solana/{token_mint}"
                    ),
                    InlineKeyboardButton(
                        "🎯 Pump.fun",
                        url=f"https://pump.fun/{token_mint}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            return message, reply_markup
            
        except Exception as e:
            logger.error(f"Error formatting message: {e}", exc_info=True)
            # Fallback message
            emoji = "🟢" if trade_type == "BUY" else "🔴"
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
            return "❌ No whales configured."
        
        message = "<b>🐋 Tracked Whales:</b>\n\n"
        
        for whale in whales:
            status = "✅ Active" if whale['active'] else "⏸️ Paused"
            address_short = whale['address'][:8] + "..." + whale['address'][-6:]
            message += f"<b>{whale['label']}</b>\n"
            message += f"Status: {status}\n"
            message += f"📍 Address: <code>{address_short}</code>\n\n"
        
        return message
    
    @staticmethod
    def format_help_message() -> str:
        """Format help message"""
        return """<b>🐋 Whale Tracker Bot Commands</b>

<b>📊 View Commands:</b>
/whales - List all tracked whales
/help - Show this help message

<b>⚙️ Management Commands (Admin Only):</b>
/addwhale &lt;label&gt; &lt;address&gt; - Add new whale
/removewhale &lt;label/address&gt; - Remove whale
/pausewhale &lt;label/address&gt; - Pause tracking
/resumewhale &lt;label/address&gt; - Resume tracking
/pauseall - Pause all whales
/resumeall - Resume all whales

<b>💡 Example:</b>
<code>/addwhale MyWhale ABC123...</code>
"""
