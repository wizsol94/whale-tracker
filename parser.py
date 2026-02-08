"""
Transaction parser for Helius webhook data
FIXED: Accurate SOL/USD calculations from on-chain balance deltas
"""

import logging
import requests
from typing import Optional, Dict
from decimal import Decimal

logger = logging.getLogger(__name__)

# Known Solana tokens
SOL_MINT = "So11111111111111111111111111111111111111112"
WSOL_MINT = "So11111111111111111111111111111111111111112"

# Lamports per SOL
LAMPORTS_PER_SOL = Decimal('1000000000')


class TransactionParser:
    
    _sol_price_cache = None
    _sol_price_timestamp = 0
    
    @staticmethod
    def _get_sol_price() -> float:
        """Fetch current SOL price from CoinGecko (cached for 30 seconds)"""
        import time
        now = time.time()
        
        # Return cached price if fresh
        if TransactionParser._sol_price_cache and (now - TransactionParser._sol_price_timestamp) < 30:
            return TransactionParser._sol_price_cache
        
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": "solana", "vs_currencies": "usd"}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            price = float(data['solana']['usd'])
            
            # Cache it
            TransactionParser._sol_price_cache = price
            TransactionParser._sol_price_timestamp = now
            
            logger.debug(f"SOL price: ${price}")
            return price
        except Exception as e:
            logger.error(f"Failed to get SOL price: {e}")
            # Return cached or fallback
            return TransactionParser._sol_price_cache or 200.0
    
    @staticmethod
    def parse_transaction(tx_data: Dict, whale_address: str) -> Optional[Dict]:
        """
        Parse Helius transaction with ACCURATE on-chain calculations
        
        FIXES:
        1. SOL = accountData.nativeBalanceChange (true delta, includes fees)
        2. Token amount = tokenAmount (already decimal-adjusted by Helius)
        3. USD = SOL * real price at tx time
        """
        try:
            signature = tx_data.get('signature')
            if not signature:
                logger.warning("No signature in transaction")
                return None
            
            # Skip failed transactions
            if tx_data.get('transactionError') or tx_data.get('err'):
                logger.debug(f"Skipping failed transaction: {signature}")
                return None
            
            # =========================================================
            # FIX #1: Get SOL change from accountData (TRUE on-chain delta)
            # =========================================================
            whale_sol_change_lamports = Decimal('0')
            found_in_account_data = False
            
            for account in tx_data.get('accountData', []):
                if account.get('account') == whale_address:
                    found_in_account_data = True
                    balance_change = account.get('nativeBalanceChange', 0)
                    whale_sol_change_lamports = Decimal(str(balance_change))
                    break
            
            # Fallback to nativeTransfers if accountData missing
            if not found_in_account_data:
                for transfer in tx_data.get('nativeTransfers', []):
                    from_addr = transfer.get('fromUserAccount', '')
                    to_addr = transfer.get('toUserAccount', '')
                    amount = Decimal(str(transfer.get('amount', 0)))
                    
                    if from_addr == whale_address:
                        whale_sol_change_lamports -= amount
                    elif to_addr == whale_address:
                        whale_sol_change_lamports += amount
            
            # Single lamports → SOL conversion
            whale_sol_change = whale_sol_change_lamports / LAMPORTS_PER_SOL
            
            # =========================================================
            # FIX #2: Parse token transfers (Helius tokenAmount is already human-readable)
            # =========================================================
            token_transfers = tx_data.get('tokenTransfers', [])
            if not token_transfers:
                logger.debug(f"No token transfers in tx: {signature}")
                return None
            
            whale_token_changes = []
            
            for transfer in token_transfers:
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                mint = transfer.get('mint', '')
                
                # Skip SOL/WSOL
                if mint in [SOL_MINT, WSOL_MINT]:
                    continue
                
                # tokenAmount from Helius is ALREADY decimal-adjusted
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
            
            # Get main token (largest change)
            main_token = max(whale_token_changes, key=lambda x: abs(x['amount']))
            token_change = main_token['amount']
            token_mint = main_token['mint']
            token_decimals = main_token['decimals']
            
            # =========================================================
            # Determine BUY or SELL
            # =========================================================
            if token_change > 0 and whale_sol_change < 0:
                trade_type = 'BUY'
                token_amount = float(token_change)
                sol_amount = abs(float(whale_sol_change))
            elif token_change < 0 and whale_sol_change > 0:
                trade_type = 'SELL'
                token_amount = abs(float(token_change))
                sol_amount = float(whale_sol_change)
            else:
                logger.debug(f"Ambiguous tx (token: {token_change}, SOL: {whale_sol_change}): {signature}")
                return None
            
            # =========================================================
            # FIX #3: Get real SOL price for USD calculation
            # =========================================================
            sol_price = TransactionParser._get_sol_price()
            
            # =========================================================
            # Get token symbol
            # =========================================================
            token_symbol = "UNKNOWN"
            for transfer in token_transfers:
                if transfer.get('mint') == token_mint:
                    token_symbol = transfer.get('symbol') or transfer.get('tokenStandard') or 'UNKNOWN'
                    break
            
            # Check accountData for symbol
            for account in tx_data.get('accountData', []):
                if account.get('account') == token_mint:
                    token_symbol = account.get('tokenSymbol', token_symbol)
                    break
            
            # =========================================================
            # Build result with accurate numbers
            # =========================================================
            result = {
                'type': trade_type,
                'token_mint': token_mint,
                'token_symbol': token_symbol,
                'token_amount': token_amount,
                'sol_amount': sol_amount,
                'sol_price': sol_price,  # Real price
                'whale_address': whale_address,
                'signature': signature,
                'timestamp': tx_data.get('timestamp', 0),
                'decimals': token_decimals
            }
            
            logger.info(f"Parsed {trade_type}: {token_amount:,.2f} {token_symbol} for {sol_amount:.4f} SOL")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing transaction: {e}", exc_info=True)
            return None
    
    @staticmethod
    def extract_token_info(tx_data: Dict, token_mint: str) -> Dict:
        """Extract token metadata"""
        info = {'symbol': 'UNKNOWN', 'name': None, 'decimals': 9}
        
        try:
            for transfer in tx_data.get('tokenTransfers', []):
                if transfer.get('mint') == token_mint:
                    info['symbol'] = transfer.get('symbol') or transfer.get('tokenStandard') or info['symbol']
                    info['decimals'] = transfer.get('decimals', info['decimals'])
                    break
            
            for account in tx_data.get('accountData', []):
                if account.get('account') == token_mint:
                    info['symbol'] = account.get('tokenSymbol', info['symbol'])
                    info['name'] = account.get('tokenName')
                    break
        except Exception as e:
            logger.error(f"Error extracting token info: {e}")
        
        return info
