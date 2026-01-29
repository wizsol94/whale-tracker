"""
Helius webhook handler
Processes incoming transaction webhooks from Helius
"""

import logging
import asyncio
from flask import Flask, request, jsonify
from typing import Dict, Callable

logger = logging.getLogger(__name__)


class HeliusWebhookHandler:
    
    def __init__(self, on_transaction: Callable):
        """
        Initialize webhook handler
        
        Args:
            on_transaction: Async callback function to process transactions
                           Signature: async def callback(tx_data: Dict, whale_address: str)
        """
        self.on_transaction = on_transaction
        self.app = Flask(__name__)
        self.setup_routes()
    
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
        Helius includes account keys and we need to identify our whale
        """
        try:
            # Method 1: Check account keys
            account_keys = tx_data.get('accountData', [])
            if account_keys:
                # The first signer is usually the whale we're tracking
                for account in account_keys:
                    if account.get('nativeBalanceChange', 0) != 0:
                        return account.get('account', '')
            
            # Method 2: Check native transfers
            native_transfers = tx_data.get('nativeTransfers', [])
            if native_transfers:
                for transfer in native_transfers:
                    # Return the first address involved
                    from_addr = transfer.get('fromUserAccount')
                    if from_addr:
                        return from_addr
            
            # Method 3: Check token transfers
            token_transfers = tx_data.get('tokenTransfers', [])
            if token_transfers:
                for transfer in token_transfers:
                    from_addr = transfer.get('fromUserAccount')
                    if from_addr:
                        return from_addr
            
            # Method 4: Check transaction accounts
            tx_accounts = tx_data.get('transaction', {}).get('message', {}).get('accountKeys', [])
            if tx_accounts:
                return tx_accounts[0].get('pubkey', '')
            
        except Exception as e:
            logger.error(f"Error extracting whale address: {e}")
        
        return None
    
    def run(self, host: str = '0.0.0.0', port: int = 5000):
        """Run the Flask webhook server"""
        logger.info(f"Starting Helius webhook handler on {host}:{port}")
        self.app.run(host=host, port=port)
