"""
Wally v1.0.4 — Parser BUG FIX
Accurate swap detection: TRUE input asset, ignore dust, handle USDC
Fixes zero-value / dust alerts leaking through
Restores accountData as FALLBACK for PumpSwap routed SOL detection
DO NOT MODIFY FORMAT - LOCKED PRODUCTION VERSION
"""

import logging
import requests
from typing import Optional, Dict
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

# Known tokens
SOL_MINT = "So11111111111111111111111111111111111111112"
WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

LAMPORTS_PER_SOL = Decimal('1000000000')
DUST_THRESHOLD_SOL = Decimal('0.01')  # Ignore SOL movements below this
MIN_USD_VALUE = 1.0                    # Minimum USD value for a valid alert


class TransactionParser:
    
    _sol_price_cache = None
    _sol_price_timestamp = 0
    _token_cache = {}
    
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
        """Fetch token metadata from DexScreener API"""
        if mint in TransactionParser._token_cache:
            cached = TransactionParser._token_cache[mint]
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
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if data.get('pairs') and len(data['pairs']) > 0:
                pair = data['pairs'][0]
                base = pair.get('baseToken', {})
                quote = pair.get('quoteToken', {})
                
                if base.get('address', '').lower() == mint.lower():
                    token_info = base
                else:
                    token_info = quote
                
                result['symbol'] = token_info.get('symbol', 'UNKNOWN')
                result['name'] = token_info.get('name', '')
                result['market_cap'] = float(pair.get('marketCap', 0) or 0)
                
                created_at = pair.get('pairCreatedAt')
                if created_at:
                    try:
                        created_ts = int(created_at) / 1000
                        age_seconds = datetime.now().timestamp() - created_ts
                        result['age'] = TransactionParser._format_age(age_seconds)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Failed to get token metadata: {e}")
        
        if result['symbol'] == 'UNKNOWN':
            result['symbol'] = f"{mint[:4]}...{mint[-4:]}"
        
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
        Parse Helius transaction with ACCURATE swap detection
        
        FIX v1.0.4:
        - Detect TRUE input asset (USDC vs SOL)
        - Ignore dust SOL movements (< 0.01 SOL)
        - Handle routed swaps (Jupiter, PumpSwap)
        - REJECT zero-value, dust, and economically meaningless swaps
        - Use accountData as FALLBACK (not override) for PumpSwap SOL detection
        """
        try:
            signature = tx_data.get('signature')
            if not signature:
                return None
            
            if tx_data.get('transactionError') or tx_data.get('err'):
                return None
            
            token_transfers = tx_data.get('tokenTransfers', [])
            if not token_transfers:
                return None
            
            # =============================================================
            # STEP 1: Collect ALL token movements for this whale
            # =============================================================
            whale_movements = {
                'sol': Decimal('0'),
                'usdc': Decimal('0'),
                'usdt': Decimal('0'),
                'tokens': []  # Other tokens
            }
            
            for transfer in token_transfers:
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                mint = transfer.get('mint', '')
                amount = Decimal(str(transfer.get('tokenAmount', 0)))
                
                if from_addr == whale_address:
                    delta = -amount
                elif to_addr == whale_address:
                    delta = amount
                else:
                    continue
                
                # Categorize by token type
                if mint in [SOL_MINT, WSOL_MINT]:
                    whale_movements['sol'] += delta
                elif mint == USDC_MINT:
                    whale_movements['usdc'] += delta
                elif mint == USDT_MINT:
                    whale_movements['usdt'] += delta
                else:
                    whale_movements['tokens'].append({
                        'mint': mint,
                        'amount': delta,
                        'decimals': transfer.get('decimals', 9)
                    })
            
            # Also check native SOL transfers
            for transfer in tx_data.get('nativeTransfers', []):
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                amount_lamports = Decimal(str(transfer.get('amount', 0)))
                amount_sol = amount_lamports / LAMPORTS_PER_SOL
                
                if from_addr == whale_address:
                    whale_movements['sol'] -= amount_sol
                elif to_addr == whale_address:
                    whale_movements['sol'] += amount_sol
            
            # -----------------------------------------------------------------
            # FIX v1.0.4: accountData as FALLBACK only (not override)
            # -----------------------------------------------------------------
            # On PumpSwap and some Jupiter routes, SOL flows through WSOL
            # wrapping and program accounts in a way that doesn't always
            # show the whale address cleanly in tokenTransfers or
            # nativeTransfers. If those sources show near-zero SOL movement,
            # fall back to accountData's nativeBalanceChange — but ONLY if
            # that value is above the dust threshold (filtering out fee-only
            # balance changes like 0.000005 SOL).
            # -----------------------------------------------------------------
            if abs(whale_movements['sol']) < DUST_THRESHOLD_SOL:
                for account in tx_data.get('accountData', []):
                    if account.get('account') == whale_address:
                        balance_change = account.get('nativeBalanceChange', 0)
                        if balance_change != 0:
                            account_sol = Decimal(str(balance_change)) / LAMPORTS_PER_SOL
                            # Only use if above dust — this filters out fee-only
                            # changes (0.000005 SOL) that caused the original bug
                            if abs(account_sol) >= DUST_THRESHOLD_SOL:
                                logger.info(f"accountData fallback: {float(account_sol):.4f} SOL "
                                          f"(token/native showed {float(whale_movements['sol']):.6f} SOL)")
                                whale_movements['sol'] = account_sol
                        break
            
            # =============================================================
            # STEP 2: Find the output token (what whale received)
            # =============================================================
            if not whale_movements['tokens']:
                return None
            
            # Find token with positive balance (received)
            received_tokens = [t for t in whale_movements['tokens'] if t['amount'] > 0]
            sent_tokens = [t for t in whale_movements['tokens'] if t['amount'] < 0]
            
            if not received_tokens and not sent_tokens:
                return None
            
            # =============================================================
            # STEP 3: Determine BUY or SELL and TRUE input
            # =============================================================
            sol_change = whale_movements['sol']
            usdc_change = whale_movements['usdc']
            usdt_change = whale_movements['usdt']
            stable_change = usdc_change + usdt_change
            
            trade_type = None
            input_asset = None
            input_amount = Decimal('0')
            output_token = None
            output_amount = Decimal('0')
            
            if received_tokens:
                # Whale RECEIVED tokens = BUY
                trade_type = 'BUY'
                output_token = max(received_tokens, key=lambda x: abs(x['amount']))
                output_amount = abs(output_token['amount'])
                
                # Determine what was spent (TRUE input)
                # Priority: USDC/USDT > SOL (if SOL is dust, ignore it)
                
                if stable_change < -1:  # Spent more than $1 in stables
                    input_asset = 'USDC'
                    input_amount = abs(stable_change)
                elif abs(sol_change) >= DUST_THRESHOLD_SOL and sol_change < 0:
                    input_asset = 'SOL'
                    input_amount = abs(sol_change)
                elif stable_change < 0:  # Any stable spent
                    input_asset = 'USDC'
                    input_amount = abs(stable_change)
                else:
                    # =========================================================
                    # FIX v1.0.3+: REJECT instead of fallback
                    # =========================================================
                    # No meaningful SOL or stablecoin was spent — this is NOT
                    # a real swap. (Likely airdrop, token init, free claim.)
                    # =========================================================
                    logger.info(f"Skipping non-swap: tokens received but no SOL/stable spent "
                               f"(sol_change={sol_change}, stable_change={stable_change}) "
                               f"sig={signature[:16]}...")
                    return None
            
            elif sent_tokens:
                # Whale SENT tokens = SELL
                trade_type = 'SELL'
                output_token = max(sent_tokens, key=lambda x: abs(x['amount']))
                output_amount = abs(output_token['amount'])
                
                # Determine what was received
                if stable_change > 1:  # Received more than $1 in stables
                    input_asset = 'USDC'
                    input_amount = abs(stable_change)
                elif abs(sol_change) >= DUST_THRESHOLD_SOL and sol_change > 0:
                    input_asset = 'SOL'
                    input_amount = abs(sol_change)
                elif stable_change > 0:
                    input_asset = 'USDC'
                    input_amount = abs(stable_change)
                else:
                    # =========================================================
                    # FIX v1.0.3+: REJECT sells with no SOL/stable received too
                    # =========================================================
                    logger.info(f"Skipping non-swap: tokens sent but no SOL/stable received "
                               f"(sol_change={sol_change}, stable_change={stable_change}) "
                               f"sig={signature[:16]}...")
                    return None
            
            if not trade_type or not output_token:
                return None
            
            # =============================================================
            # STEP 4: Calculate USD value
            # =============================================================
            sol_price = TransactionParser._get_sol_price()
            
            if input_asset == 'USDC':
                usd_value = float(input_amount)  # USDC = USD 1:1
            else:
                usd_value = float(input_amount) * sol_price
            
            # =============================================================
            # FIX v1.0.3+: FINAL VALIDATION GATE
            # =============================================================
            # Reject any trade that still has economically meaningless values.
            # This is the last line of defense before an alert is sent.
            # =============================================================
            if float(input_amount) < float(DUST_THRESHOLD_SOL) and input_asset == 'SOL':
                logger.info(f"Filtered dust SOL swap: {float(input_amount):.6f} SOL, sig={signature[:16]}...")
                return None
            
            if usd_value < MIN_USD_VALUE:
                logger.info(f"Filtered low-value swap: ${usd_value:.2f}, sig={signature[:16]}...")
                return None
            
            # =============================================================
            # STEP 5: Get token metadata
            # =============================================================
            token_mint = output_token['mint']
            token_metadata = TransactionParser._get_token_metadata(token_mint)
            
            # =============================================================
            # STEP 6: Build result
            # =============================================================
            result = {
                'type': trade_type,
                'token_mint': token_mint,
                'token_symbol': token_metadata['symbol'],
                'token_amount': float(output_amount),
                'input_asset': input_asset,  # 'SOL' or 'USDC'
                'sol_amount': float(input_amount) if input_asset == 'SOL' else 0,
                'usdc_amount': float(input_amount) if input_asset == 'USDC' else 0,
                'input_amount': float(input_amount),
                'sol_price': sol_price,
                'usd_value': usd_value,
                'market_cap': token_metadata['market_cap'],
                'token_age': token_metadata['age'],
                'whale_address': whale_address,
                'signature': signature,
                'timestamp': tx_data.get('timestamp', 0),
                'decimals': output_token['decimals']
            }
            
            logger.info(f"Parsed {trade_type}: {float(output_amount):,.2f} {token_metadata['symbol']} "
                       f"for {float(input_amount):,.4f} {input_asset} (${usd_value:,.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing transaction: {e}", exc_info=True)
            return None
