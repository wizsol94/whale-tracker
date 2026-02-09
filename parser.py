"""
Wally v1.0.1 — Parser + Token Resolution Fix
Accurate SOL/USD calculations + Real token names
DO NOT MODIFY - LOCKED PRODUCTION VERSION
"""

import logging
import requests
from typing import Optional, Dict
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

# Known Solana tokens
SOL_MINT = "So11111111111111111111111111111111111111112"
WSOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = Decimal('1000000000')


class TransactionParser:
    
    _sol_price_cache = None
    _sol_price_timestamp = 0
    _token_cache = {}  # Cache token metadata
    
    @staticmethod
    def _get_sol_price() -> float:
        """Fetch current SOL price from CoinGecko"""
        import time
        now = time.time()
        
        if TransactionParser._sol_price_cache and (now - TransactionParser._sol_price_timestamp) < 30:
            return TransactionParser._sol_price_cache
        
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": "solana", "vs_currencies": "usd"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            price = float(data['solana']['usd'])
            
            TransactionParser._sol_price_cache = price
            TransactionParser._sol_price_timestamp = now
            return price
        except Exception as e:
            logger.error(f"Failed to get SOL price: {e}")
            return TransactionParser._sol_price_cache or 200.0
    
    @staticmethod
    def _get_token_metadata(mint: str) -> Dict:
        """
        Fetch token metadata from DexScreener API
        Returns: {symbol, name, market_cap, age}
        FIXES "Fungible" bug by getting real token name
        """
        # Check cache first
        if mint in TransactionParser._token_cache:
            cached = TransactionParser._token_cache[mint]
            # Cache for 5 minutes
            if cached.get('_cached_at', 0) > datetime.now().timestamp() - 300:
                return cached
        
        result = {
            'symbol': 'UNKNOWN',
            'name': None,
            'market_cap': 0,
            'age': '',
            '_cached_at': datetime.now().timestamp()
        }
        
        try:
            # DexScreener API - most reliable for Solana tokens
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if data.get('pairs') and len(data['pairs']) > 0:
                pair = data['pairs'][0]  # Get first/main pair
                
                # Get token info from baseToken or quoteToken
                base = pair.get('baseToken', {})
                quote = pair.get('quoteToken', {})
                
                # Determine which is our token
                if base.get('address', '').lower() == mint.lower():
                    token_info = base
                else:
                    token_info = quote
                
                result['symbol'] = token_info.get('symbol', 'UNKNOWN')
                result['name'] = token_info.get('name', '')
                
                # Market cap
                result['market_cap'] = float(pair.get('marketCap', 0) or 0)
                
                # Calculate age from pairCreatedAt
                created_at = pair.get('pairCreatedAt')
                if created_at:
                    try:
                        created_ts = int(created_at) / 1000  # Convert ms to seconds
                        age_seconds = datetime.now().timestamp() - created_ts
                        result['age'] = TransactionParser._format_age(age_seconds)
                    except:
                        pass
                
                logger.info(f"Token resolved: {mint[:8]}... = {result['symbol']}")
            
        except Exception as e:
            logger.error(f"Failed to get token metadata for {mint[:8]}...: {e}")
        
        # Try Jupiter API as fallback
        if result['symbol'] == 'UNKNOWN':
            try:
                url = f"https://token.jup.ag/strict"
                response = requests.get(url, timeout=5)
                tokens = response.json()
                
                for token in tokens:
                    if token.get('address') == mint:
                        result['symbol'] = token.get('symbol', 'UNKNOWN')
                        result['name'] = token.get('name', '')
                        logger.info(f"Token resolved via Jupiter: {mint[:8]}... = {result['symbol']}")
                        break
            except Exception as e:
                logger.debug(f"Jupiter fallback failed: {e}")
        
        # Cache result
        TransactionParser._token_cache[mint] = result
        return result
    
    @staticmethod
    def _format_age(seconds: float) -> str:
        """Format age as Xd Xh"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        
        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h"
        else:
            minutes = int(seconds // 60)
            return f"{minutes}m"
    
    @staticmethod
    def parse_transaction(tx_data: Dict, whale_address: str) -> Optional[Dict]:
        """
        Parse Helius transaction with accurate calculations
        + Real token name resolution (fixes "Fungible" bug)
        """
        try:
            signature = tx_data.get('signature')
            if not signature:
                logger.warning("No signature in transaction")
                return None
            
            if tx_data.get('transactionError') or tx_data.get('err'):
                logger.debug(f"Skipping failed transaction: {signature}")
                return None
            
            # Get SOL change from accountData (accurate method)
            whale_sol_change_lamports = Decimal('0')
            found_in_account_data = False
            
            for account in tx_data.get('accountData', []):
                if account.get('account') == whale_address:
                    found_in_account_data = True
                    balance_change = account.get('nativeBalanceChange', 0)
                    whale_sol_change_lamports = Decimal(str(balance_change))
                    break
            
            # Fallback to nativeTransfers
            if not found_in_account_data:
                for transfer in tx_data.get('nativeTransfers', []):
                    from_addr = transfer.get('fromUserAccount', '')
                    to_addr = transfer.get('toUserAccount', '')
                    amount = Decimal(str(transfer.get('amount', 0)))
                    
                    if from_addr == whale_address:
                        whale_sol_change_lamports -= amount
                    elif to_addr == whale_address:
                        whale_sol_change_lamports += amount
            
            whale_sol_change = whale_sol_change_lamports / LAMPORTS_PER_SOL
            
            # Parse token transfers
            token_transfers = tx_data.get('tokenTransfers', [])
            if not token_transfers:
                logger.debug(f"No token transfers in tx: {signature}")
                return None
            
            whale_token_changes = []
            
            for transfer in token_transfers:
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                mint = transfer.get('mint', '')
                
                if mint in [SOL_MINT, WSOL_MINT]:
                    continue
                
                token_amount = Decimal(str(transfer.get('tokenAmount', 0)))
                decimals = transfer.get('decimals', 9)
                
                if from_addr == whale_address:
                    whale_token_changes.append({
                        'mint': mint,
                        'amount': -token_amount,
                        'decimals': decimals
                    })
                elif to_addr == whale_address:
                    whale_token_changes.append({
                        'mint': mint,
                        'amount': token_amount,
                        'decimals': decimals
                    })
            
            if not whale_token_changes:
                logger.debug(f"No token changes for whale in tx: {signature}")
                return None
            
            # Get main token
            main_token = max(whale_token_changes, key=lambda x: abs(x['amount']))
            token_change = main_token['amount']
            token_mint = main_token['mint']
            token_decimals = main_token['decimals']
            
            # Determine BUY or SELL
            if token_change > 0 and whale_sol_change < 0:
                trade_type = 'BUY'
                token_amount = float(token_change)
                sol_amount = abs(float(whale_sol_change))
            elif token_change < 0 and whale_sol_change > 0:
                trade_type = 'SELL'
                token_amount = abs(float(token_change))
                sol_amount = float(whale_sol_change)
            else:
                logger.debug(f"Ambiguous tx: {signature}")
                return None
            
            # Get real SOL price
            sol_price = TransactionParser._get_sol_price()
            usd_value = sol_amount * sol_price
            
            # =====================================================
            # FIX: Get REAL token name (no more "Fungible")
            # =====================================================
            token_metadata = TransactionParser._get_token_metadata(token_mint)
            token_symbol = token_metadata['symbol']
            market_cap = token_metadata['market_cap']
            token_age = token_metadata['age']
            
            # If still UNKNOWN, do NOT show "Fungible"
            if token_symbol == 'UNKNOWN':
                # Last resort: use short mint address
                token_symbol = f"{token_mint[:4]}...{token_mint[-4:]}"
            
            result = {
                'type': trade_type,
                'token_mint': token_mint,
                'token_symbol': token_symbol,
                'token_amount': token_amount,
                'sol_amount': sol_amount,
                'sol_price': sol_price,
                'usd_value': usd_value,
                'market_cap': market_cap,
                'token_age': token_age,
                'whale_address': whale_address,
                'signature': signature,
                'timestamp': tx_data.get('timestamp', 0),
                'decimals': token_decimals
            }
            
            logger.info(f"Parsed {trade_type}: {token_amount:,.2f} {token_symbol} for {sol_amount:.4f} SOL (${usd_value:,.2f})")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing transaction: {e}", exc_info=True)
            return None
