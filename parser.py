"""
Transaction parser for Helius webhook data
Determines BUY vs SELL from balance changes
WITH ENHANCED DEBUG LOGGING
"""

import logging
from typing import Optional, Dict, List
from decimal import Decimal
import requests
import json

logger = logging.getLogger(__name__)

# Known Solana tokens
SOL_MINT = "So11111111111111111111111111111111111111112"
WSOL_MINT = "So11111111111111111111111111111111111111112"


class TransactionParser:
    
    @staticmethod
    def fetch_token_metadata(token_mint: str) -> Dict:
        """
        Fetch token metadata from DexScreener or Jupiter API
        Returns symbol and name
        """
        # Try DexScreener FIRST (more accurate for pump.fun tokens)
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_mint}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('pairs') and len(data['pairs']) > 0:
                    pair = data['pairs'][0]
                    base_token = pair.get('baseToken', {})
                    symbol = base_token.get('symbol', 'UNKNOWN')
                    name = base_token.get('name', None)
                    if symbol != 'UNKNOWN':
                        logger.debug(f"Got token from DexScreener: {symbol}")
                        return {
                            'symbol': symbol,
                            'name': name
                        }
        except Exception as e:
            logger.debug(f"DexScreener API failed for {token_mint}: {e}")
        
        # Try Jupiter API as backup
        try:
            url = f"https://tokens.jup.ag/token/{token_mint}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                symbol = data.get('symbol', 'UNKNOWN')
                if symbol != 'UNKNOWN':
                    logger.debug(f"Got token from Jupiter: {symbol}")
                    return {
                        'symbol': symbol,
                        'name': data.get('name', None)
                    }
        except Exception as e:
            logger.debug(f"Jupiter API failed for {token_mint}: {e}")
        
        # Fallback to shortened mint address
        logger.warning(f"Could not fetch token metadata for {token_mint}, using mint prefix")
        return {
            'symbol': token_mint[:6],
            'name': None
        }
    
    @staticmethod
    def parse_transaction(tx_data: Dict, whale_address: str) -> Optional[Dict]:
        """
        Parse Helius transaction and determine if it's a BUY or SELL
        
        Returns Dict with:
        - type: 'BUY' or 'SELL'
        - token_mint: str
        - token_symbol: str
        - token_amount: float
        - sol_amount: float
        - whale_address: str
        - signature: str
        - timestamp: int
        """
        try:
            # Get transaction signature
            signature = tx_data.get('signature')
            if not signature:
                logger.warning("❌ FILTER: No signature in transaction")
                return None
            
            logger.info(f"🔍 PARSING TX: {signature[:16]}... for whale {whale_address[:8]}...")
            
            # Check if transaction failed
            if tx_data.get('err'):
                logger.debug(f"❌ FILTER: Failed transaction: {signature[:16]}...")
                return None
            
            # Get token balances (parsed by Helius)
            token_transfers = tx_data.get('tokenTransfers', [])
            native_transfers = tx_data.get('nativeTransfers', [])
            
            logger.debug(f"📊 TX DATA: {len(token_transfers)} token transfers, {len(native_transfers)} native transfers")
            
            if not token_transfers:
                logger.debug(f"❌ FILTER: No token transfers in tx: {signature[:16]}...")
                return None
            
            # Find balance changes for our whale
            whale_token_changes = []
            whale_sol_change = Decimal('0')
            
            # Parse token transfers
            for transfer in token_transfers:
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                amount = Decimal(str(transfer.get('tokenAmount', 0)))
                mint = transfer.get('mint', '')
                
                logger.debug(f"  📦 Token: {mint[:8]}... | From: {from_addr[:8]}... | To: {to_addr[:8]}... | Amount: {amount}")
                
                # CRITICAL FIX: Treat WSOL (wrapped SOL) as SOL, not as a token
                if mint in [SOL_MINT, WSOL_MINT]:
                    logger.debug(f"    💰 This is WSOL - treating as SOL transfer")
                    if from_addr == whale_address:
                        whale_sol_change -= amount
                        logger.debug(f"    ➡️ Whale SENT {amount} SOL (via WSOL)")
                    elif to_addr == whale_address:
                        whale_sol_change += amount
                        logger.debug(f"    ⬅️ Whale RECEIVED {amount} SOL (via WSOL)")
                    continue  # Skip adding to token changes
                
                # Track changes for our whale (non-SOL tokens only)
                if from_addr == whale_address:
                    # Whale sent token (negative change)
                    whale_token_changes.append({
                        'mint': mint,
                        'amount': -amount,
                        'decimals': transfer.get('decimals', 9)
                    })
                    logger.debug(f"    ➡️ Whale SENT {amount} of {mint[:8]}...")
                elif to_addr == whale_address:
                    # Whale received token (positive change)
                    whale_token_changes.append({
                        'mint': mint,
                        'amount': amount,
                        'decimals': transfer.get('decimals', 9)
                    })
                    logger.debug(f"    ⬅️ Whale RECEIVED {amount} of {mint[:8]}...")
            
            # Parse native SOL transfers
            for transfer in native_transfers:
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                amount = Decimal(str(transfer.get('amount', 0))) / Decimal('1000000000')  # Convert lamports to SOL
                
                logger.debug(f"  💰 SOL: From: {from_addr[:8]}... | To: {to_addr[:8]}... | Amount: {amount} SOL")
                
                if from_addr == whale_address:
                    whale_sol_change -= amount
                    logger.debug(f"    ➡️ Whale SENT {amount} SOL")
                elif to_addr == whale_address:
                    whale_sol_change += amount
                    logger.debug(f"    ⬅️ Whale RECEIVED {amount} SOL")
            
            logger.info(f"  📈 Whale Balance Changes: Token changes: {len(whale_token_changes)}, SOL change: {whale_sol_change}")
            
            # Determine BUY or SELL
            # BUY = SOL decreases AND token increases
            # SELL = token decreases AND SOL increases
            
            if not whale_token_changes:
                logger.warning(f"❌ FILTER: No token changes for whale in tx: {signature[:16]}...")
                return None
            
            # Find the token with the largest absolute balance change
            main_token = max(whale_token_changes, key=lambda x: abs(x['amount']))
            token_change = main_token['amount']
            token_mint = main_token['mint']
            token_decimals = main_token['decimals']
            
            logger.debug(f"  🎯 Main token: {token_mint[:8]}... | Change: {token_change}")
            
            # Determine trade type
            trade_type = None
            if token_change > 0 and whale_sol_change < 0:
                trade_type = 'BUY'
                token_amount = float(token_change)
                sol_amount = abs(float(whale_sol_change))
                logger.info(f"  ✅ IDENTIFIED: BUY - Token +{token_change}, SOL {whale_sol_change}")
            elif token_change < 0 and whale_sol_change > 0:
                trade_type = 'SELL'
                token_amount = abs(float(token_change))
                sol_amount = float(whale_sol_change)
                logger.info(f"  ✅ IDENTIFIED: SELL - Token {token_change}, SOL +{whale_sol_change}")
            else:
                logger.warning(f"❌ FILTER: Ambiguous transaction (token: {token_change}, SOL: {whale_sol_change}): {signature[:16]}...")
                logger.warning(f"  ⚠️ This might be a valid trade that we're missing! Review the logic.")
                return None
            
            # FIXED: Fetch actual token metadata from APIs
            token_symbol = "UNKNOWN"
            
            # First, try to get from Helius transaction data
            for transfer in token_transfers:
                if transfer.get('mint') == token_mint:
                    # Check if Helius provided token info
                    if 'tokenSymbol' in transfer:
                        token_symbol = transfer['tokenSymbol']
                        logger.debug(f"  🏷️ Token symbol from Helius: {token_symbol}")
                        break
            
            # If still unknown, fetch from external APIs
            if token_symbol == "UNKNOWN":
                logger.info(f"  🌐 Fetching token metadata for mint: {token_mint[:8]}...")
                metadata = TransactionParser.fetch_token_metadata(token_mint)
                token_symbol = metadata['symbol']
                logger.debug(f"  🏷️ Token symbol from API: {token_symbol}")
            
            result = {
                'type': trade_type,
                'token_mint': token_mint,
                'token_symbol': token_symbol,
                'token_amount': token_amount,
                'sol_amount': sol_amount,
                'whale_address': whale_address,
                'signature': signature,
                'timestamp': tx_data.get('timestamp', 0),
                'decimals': token_decimals
            }
            
            logger.info(f"✅ PARSED {trade_type}: {token_amount} {token_symbol} for {sol_amount} SOL by whale {whale_address[:8]}...")
            return result
            
        except Exception as e:
            logger.error(f"❌ ERROR parsing transaction: {e}", exc_info=True)
            return None
    
    @staticmethod
    def extract_token_info(tx_data: Dict, token_mint: str) -> Dict:
        """
        Extract additional token information from transaction
        Returns: symbol, name, metadata
        """
        info = {
            'symbol': 'UNKNOWN',
            'name': None,
            'decimals': 9
        }
        
        try:
            # Check token transfers for metadata
            token_transfers = tx_data.get('tokenTransfers', [])
            for transfer in token_transfers:
                if transfer.get('mint') == token_mint:
                    # Fixed: use tokenSymbol instead of tokenStandard
                    if 'tokenSymbol' in transfer:
                        info['symbol'] = transfer['tokenSymbol']
                    info['decimals'] = transfer.get('decimals', info['decimals'])
                    break
            
            # Check account data
            account_data = tx_data.get('accountData', [])
            for account in account_data:
                if account.get('account') == token_mint:
                    info['symbol'] = account.get('tokenSymbol', info['symbol'])
                    info['name'] = account.get('tokenName')
                    break
            
            # If still unknown, fetch from APIs
            if info['symbol'] == 'UNKNOWN':
                metadata = TransactionParser.fetch_token_metadata(token_mint)
                info['symbol'] = metadata['symbol']
                info['name'] = metadata['name']
        
        except Exception as e:
            logger.error(f"Error extracting token info: {e}")
        
        return info
