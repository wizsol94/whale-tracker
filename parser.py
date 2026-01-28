"""
Transaction parser for Helius webhook data
Determines BUY vs SELL from balance changes
"""

import logging
from typing import Optional, Dict, List
from decimal import Decimal

logger = logging.getLogger(__name__)

# Known Solana tokens
SOL_MINT = "So11111111111111111111111111111111111111112"
WSOL_MINT = "So11111111111111111111111111111111111111112"


class TransactionParser:
    
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
                logger.warning("No signature in transaction")
                return None
            
            # Check if transaction failed
            if tx_data.get('err'):
                logger.debug(f"Skipping failed transaction: {signature}")
                return None
            
            # Get token balances (parsed by Helius)
            token_transfers = tx_data.get('tokenTransfers', [])
            native_transfers = tx_data.get('nativeTransfers', [])
            
            if not token_transfers:
                logger.debug(f"No token transfers in tx: {signature}")
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
                
                # Track changes for our whale
                if from_addr == whale_address:
                    # Whale sent token (negative change)
                    whale_token_changes.append({
                        'mint': mint,
                        'amount': -amount,
                        'decimals': transfer.get('decimals', 9)
                    })
                elif to_addr == whale_address:
                    # Whale received token (positive change)
                    whale_token_changes.append({
                        'mint': mint,
                        'amount': amount,
                        'decimals': transfer.get('decimals', 9)
                    })
            
            # Parse native SOL transfers
            for transfer in native_transfers:
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                amount = Decimal(str(transfer.get('amount', 0))) / Decimal('1000000000')  # Convert lamports to SOL
                
                if from_addr == whale_address:
                    whale_sol_change -= amount
                elif to_addr == whale_address:
                    whale_sol_change += amount
            
            # Determine BUY or SELL
            # BUY = SOL decreases AND token increases
            # SELL = token decreases AND SOL increases
            
            if not whale_token_changes:
                logger.debug(f"No token changes for whale in tx: {signature}")
                return None
            
            # Find the token with the largest absolute balance change
            main_token = max(whale_token_changes, key=lambda x: abs(x['amount']))
            token_change = main_token['amount']
            token_mint = main_token['mint']
            token_decimals = main_token['decimals']
            
            # Skip if token mint is SOL/WSOL (we're tracking it separately)
            if token_mint in [SOL_MINT, WSOL_MINT]:
                logger.debug(f"Skipping SOL/WSOL token transfer: {signature}")
                return None
            
            # Determine trade type
            trade_type = None
            if token_change > 0 and whale_sol_change < 0:
                trade_type = 'BUY'
                token_amount = float(token_change)
                sol_amount = abs(float(whale_sol_change))
            elif token_change < 0 and whale_sol_change > 0:
                trade_type = 'SELL'
                token_amount = abs(float(token_change))
                sol_amount = float(whale_sol_change)
            else:
                logger.debug(f"Ambiguous transaction (token: {token_change}, SOL: {whale_sol_change}): {signature}")
                return None
            
            # Get token symbol from metadata if available
            token_symbol = "UNKNOWN"
            for transfer in token_transfers:
                if transfer.get('mint') == token_mint:
                    token_symbol = transfer.get('tokenStandard', 'UNKNOWN')
                    # Try to get symbol from metadata
                    if 'metadata' in tx_data:
                        # Helius sometimes includes token metadata
                        pass
                    break
            
            # Try to extract symbol from account data
            account_data = tx_data.get('accountData', [])
            for account in account_data:
                if account.get('account') == token_mint:
                    token_symbol = account.get('tokenSymbol', token_symbol)
                    break
            
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
            
            logger.info(f"Parsed {trade_type}: {token_amount} {token_symbol} for {sol_amount} SOL by whale {whale_address[:8]}...")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing transaction: {e}", exc_info=True)
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
                    info['symbol'] = transfer.get('tokenStandard', info['symbol'])
                    info['decimals'] = transfer.get('decimals', info['decimals'])
                    break
            
            # Check account data
            account_data = tx_data.get('accountData', [])
            for account in account_data:
                if account.get('account') == token_mint:
                    info['symbol'] = account.get('tokenSymbol', info['symbol'])
                    info['name'] = account.get('tokenName')
                    break
        
        except Exception as e:
            logger.error(f"Error extracting token info: {e}")
        
        return info
