"""
Wally v1.0.2 — Formatter BUG FIX
Handles USDC and SOL inputs correctly
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
        WALLY v1.0 CANONICAL FORMAT — DO NOT CHANGE LAYOUT
        v1.0.2: Handles USDC vs SOL input correctly
        """
        try:
            trade_type = trade['type']
            token_symbol = trade['token_symbol']
            token_amount = trade['token_amount']
            token_mint = trade['token_mint']
            whale_address = trade.get('whale_address', '')
            usd_value = trade.get('usd_value', 0)
            market_cap = trade.get('market_cap', 0)
            token_age = trade.get('token_age', '')
            
            # Determine input asset and amount
            input_asset = trade.get('input_asset', 'SOL')
            input_amount = trade.get('input_amount', 0)
            
            # If old format without input_asset, fallback
            if not input_amount:
                input_amount = trade.get('sol_amount', 0)
                input_asset = 'SOL'
            
            # Calculate avg price
            avg_price = 0
            if token_amount > 0 and usd_value > 0:
                avg_price = usd_value / token_amount
            
            # Format numbers
            input_str = MessageFormatter._format_input_amount(input_amount, input_asset)
            usd_str = MessageFormatter._format_usd(usd_value)
            token_str = MessageFormatter._format_token_amount(token_amount)
            avg_str = MessageFormatter._format_avg_price(avg_price)
            mc_str = MessageFormatter._format_market_cap(market_cap)
            
            # ACTION LINE
            emoji = "🟢" if trade_type == "BUY" else "🔴"
            action_line = f"{emoji} <b>{trade_type} {token_symbol} on PumpSwap</b> 🚀"
            
            # WALLET BLOCK
            solscan_wallet_url = f"https://solscan.io/account/{whale_address}"
            wallet_block = f"🐳 <b>{whale_label}</b>\n🔗 <a href=\"{solscan_wallet_url}\">Solscan</a>"
            
            # SWAP DETAILS - Show correct input asset
            if trade_type == "BUY":
                swap_line = f"{whale_label} swapped {input_str} (${usd_str}) for {token_str} {token_symbol}"
            else:
                swap_line = f"{whale_label} swapped {token_str} {token_symbol} for {input_str} (${usd_str})"
            
            avg_line = f"💰 Avg: ${avg_str}"
            
            mc_display = f"${mc_str}" if market_cap > 0 else "N/A"
            age_display = token_age if token_age else "N/A"
            mc_line = f"📊 MC: {mc_display} | ⏱ Seen: {age_display}"
            
            # CONTRACT BLOCK
            contract_block = f"📄 Contract:\n<code>{token_mint}</code>"
            
            # BUILD MESSAGE
            message = f"{action_line}\n\n{wallet_block}\n\n{swap_line}\n{avg_line}\n{mc_line}\n\n{contract_block}"
            
            # BUTTONS
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
    def _format_input_amount(amount: float, asset: str) -> str:
        """Format input amount with correct asset label"""
        if asset == 'USDC':
            # USDC shows as dollar amount
            if amount >= 1000:
                return f"{amount:,.0f} USDC"
            else:
                return f"{amount:,.2f} USDC"
        else:
            # SOL
            if amount >= 1000:
                return f"{amount:,.1f} SOL"
            elif amount >= 1:
                return f"{amount:,.2f} SOL"
            else:
                return f"{amount:,.4f} SOL"
    
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
        """Format list of whales"""
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
/wally - Show commands

<b>Admin Commands:</b>
/addwhale - Add whale
/removewhale - Remove whale
/pausewhale - Pause tracking
/resumewhale - Resume tracking
/pauseall - Pause all
/resumeall - Resume all
"""
