"""
Helius webhook handler
Processes incoming transaction webhooks from Helius
"""

import logging
import asyncio
from flask import Flask, request, jsonify
from typing import Dict, Callable, Set

logger = logging.getLogger(__name__)


class HeliusWebhookHandler:
    
    def __init__(self, on_transaction: Callable, known_whales: Set[str] = None):
        """
        Initialize webhook handler
        
        Args:
            on_transaction: Async callback function to process transactions
                           Signature: async def callback(tx_data: Dict, whale_address: str)
            known_whales: Set of known whale addresses to match against
        """
        self.on_transaction = on_transaction
        self.known_whales = known_whales or set()
        self.app = Flask(__name__)
        self.setup_routes()
    
    def update_known_whales(self, whale_addresses: Set[str]):
        """Update the set of known whale addresses"""
        self.known_whales = whale_addresses
    
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/health', methods=['GET'])
        def health():
            """Health check endpoint"""
            return jsonify({'status': 'healthy'}), 200
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            """Main webhook endpoint for Helius"""
            try:
                data = request.get_json()
                
                if not data:
                    logger.warning("Received empty webhook payload")
                    return jsonify({'error': 'Empty payload'}), 400
                
                # Helius sends array of transactions
                transactions = data if isinstance(data, list) else [data]
                
                logger.info(f"Received {len(transactions)} transaction(s) from Helius")
                
                # Process each transaction asynchronously
                for tx in transactions:
                    # Get the wallet address this webhook is for
                    # Helius includes this in the webhook data
                    whale_address = self._extract_whale_address(tx)
                    
                    if whale_address:
                        # Process in background using thread to avoid event loop issues
                        import threading
                        thread = threading.Thread(
                            target=lambda t=tx, w=whale_address: asyncio.run(self.on_transaction(t, w)),
                            daemon=True
                        )
                        thread.start()
                    else:
                        logger.warning("Could not extract whale address from transaction")
                
                return jsonify({'status': 'received'}), 200
                
            except Exception as e:
                logger.error(f"Error processing webhook: {e}", exc_info=True)
                return jsonify({'error': 'Internal error'}), 500
    
    def _extract_whale_address(self, tx_data: Dict) -> str:
        """
        Extract the monitored wallet address from transaction
        Matches against known whale addresses from database
        """
        try:
            # Collect all addresses from the transaction
            all_addresses = set()
            
            # Method 1: Get fee payer (usually the transaction signer/whale)
            fee_payer = tx_data.get('feePayer')
            if fee_payer:
                all_addresses.add(fee_payer)
            
            # Method 2: Check account data for addresses with balance changes
            account_data = tx_data.get('accountData', [])
            for account in account_data:
                addr = account.get('account')
                if addr:
                    all_addresses.add(addr)
            
            # Method 3: Check native transfers
            native_transfers = tx_data.get('nativeTransfers', [])
            for transfer in native_transfers:
                from_addr = transfer.get('fromUserAccount')
                to_addr = transfer.get('toUserAccount')
                if from_addr:
                    all_addresses.add(from_addr)
                if to_addr:
                    all_addresses.add(to_addr)
            
            # Method 4: Check token transfers
            token_transfers = tx_data.get('tokenTransfers', [])
            for transfer in token_transfers:
                from_addr = transfer.get('fromUserAccount')
                to_addr = transfer.get('toUserAccount')
                if from_addr:
                    all_addresses.add(from_addr)
                if to_addr:
                    all_addresses.add(to_addr)
            
            # Method 5: Check transaction signature accounts
            transaction = tx_data.get('transaction', {})
            message = transaction.get('message', {})
            account_keys = message.get('accountKeys', [])
            for account_key in account_keys:
                if isinstance(account_key, dict):
                    pubkey = account_key.get('pubkey')
                    if pubkey:
                        all_addresses.add(pubkey)
                elif isinstance(account_key, str):
                    all_addresses.add(account_key)
            
            # Match against known whales
            for addr in all_addresses:
                if addr in self.known_whales:
                    logger.info(f"Matched whale address: {addr[:8]}...")
                    return addr
            
            # If no match found, log all addresses for debugging
            logger.warning(f"No known whale found. Addresses in transaction: {[addr[:8] + '...' for addr in all_addresses if addr]}")
            
        except Exception as e:
            logger.error(f"Error extracting whale address: {e}", exc_info=True)
        
        return None
    
    def run(self, host: str = '0.0.0.0', port: int = 5000):
        """Run the Flask webhook server"""
        logger.info(f"Starting Helius webhook handler on {host}:{port}")
        self.app.run(host=host, port=port)
