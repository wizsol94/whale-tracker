"""
Wally v1.0.1 — Canonical Restore (Text-Spec Locked)
Telegram message formatter for whale trades
DO NOT MODIFY FORMAT - LOCKED PRODUCTION VERSION
"""

import logging
from typing import Dict, Tuple, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class MessageFormatter:
    
    @staticmethod
    def format_trade_message(trade: Dict, whale_label: str) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
        """
        Format trade into Telegram message
        WALLY v1.0 CANONICAL FORMAT — DO NOT CHANGE
        """
        try:
            trade_type = trade['type']
            token_symbol = trade['token_symbol']
            token_amount = trade['token_amount']
            sol_amount = trade['sol_amount']
            token_mint = trade['token_mint']
            whale_address = trade.get('whale_address', '')
            usd_value = trade.get('usd_value', 0)
            sol_price = trade.get('sol_price', 200.0)
            market_cap = trade.get('market_cap', 0)
            token_age = trade.get('token_age', '')
            
            # Calculate USD if not provided
            if not usd_value and sol_amount and sol_price:
                usd_value = sol_amount * sol_price
            
            # Calculate avg price
            avg_price = 0
            if token_amount > 0:
                avg_price = usd_value / token_amount
            
            # Format numbers
            sol_str = MessageFormatter._format_sol(sol_amount)
            usd_str = MessageFormatter._format_usd(usd_value)
            token_str = MessageFormatter._format_token_amount(token_amount)
            avg_str = MessageFormatter._format_avg_price(avg_price)
            mc_str = MessageFormatter._format_market_cap(market_cap)
            
            # Build message lines
            lines = []
            
            # ACTION LINE
            emoji = "🟢" if trade_type == "BUY" else "🔴"
            lines.append(f"{emoji} <b>{trade_type} {token_symbol} on PumpSwap</b> 🚀")
            lines.append("")
            
            # WALLET BLOCK
            solscan_wallet_url = f"https://solscan.io/account/{whale_address}"
            lines.append(f"🐳 <b>{whale_label}</b> <a href=\"{solscan_wallet_url}\">🔗 Solscan</a>")
            lines.append("")
            
            # SWAP DETAILS
            if trade_type == "BUY":
                lines.append(f"{whale_label} swapped {sol_str} SOL (${usd_str}) for {token_str} {token_symbol}")
            else:
                lines.append(f"{whale_label} swapped {token_str} {token_symbol} for {sol_str} SOL (${usd_str})")
            lines.append("")
            
            # PRICE LINE
            lines.append(f"💵 Avg: ${avg_str}")
            lines.append("")
            
            # MARKET CONTEXT LINE
            if market_cap > 0 or token_age:
                mc_display = f"${mc_str}" if market_cap > 0 else "N/A"
                age_display = token_age if token_age else "N/A"
                lines.append(f"📊 MC: {mc_display} | ⏰ Seen: {age_display}")
                lines.append("")
            
            # CONTRACT BLOCK
            lines.append(f"📄 Contract:")
            lines.append(f"<code>{token_mint}</code>")
            
            message = "\n".join(lines)
            
            # BUTTONS (exactly two)
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
            emoji = "🟢" if trade.get('type') == "BUY" else "🔴"
            message = f"{emoji} {trade.get('type', 'TRADE')} detected for {whale_label}"
            return message, None
    
    @staticmethod
    def _format_sol(amount: float) -> str:
        """Format SOL amount"""
        if amount >= 1000:
            return f"{amount:,.1f}"
        elif amount >= 1:
            return f"{amount:,.2f}"
        else:
            return f"{amount:,.4f}"
    
    @staticmethod
    def _format_usd(amount: float) -> str:
        """Format USD amount"""
        if amount >= 1_000_000:
            return f"{amount/1_000_000:,.2f}M"
        elif amount >= 1_000:
            return f"{amount:,.0f}"
        else:
            return f"{amount:,.2f}"
    
    @staticmethod
    def _format_token_amount(amount: float) -> str:
        """Format token amount"""
        if amount >= 1_000_000_000:
            return f"{amount/1_000_000_000:,.2f}B"
        elif amount >= 1_000_000:
            return f"{amount/1_000_000:,.2f}M"
        elif amount >= 1_000:
            return f"{amount/1_000:,.2f}K"
        elif amount >= 1:
            return f"{amount:,.2f}"
        else:
            return f"{amount:,.6f}"
    
    @staticmethod
    def _format_avg_price(price: float) -> str:
        """Format average price"""
        if price >= 1:
            return f"{price:,.4f}"
        elif price >= 0.0001:
            return f"{price:,.6f}"
        elif price >= 0.00000001:
            return f"{price:,.10f}"
        else:
            return f"{price:.2e}"
    
    @staticmethod
    def _format_market_cap(mc: float) -> str:
        """Format market cap"""
        if mc >= 1_000_000_000:
            return f"{mc/1_000_000_000:,.2f}B"
        elif mc >= 1_000_000:
            return f"{mc/1_000_000:,.2f}M"
        elif mc >= 1_000:
            return f"{mc/1_000:,.1f}K"
        else:
            return f"{mc:,.0f}"
    
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
