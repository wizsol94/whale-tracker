"""
Helius webhook handler
Processes incoming transaction webhooks from Helius
"""

import logging
import asyncio
from flask import Flask, request, jsonify
from typing import Dict, Callable, Set

logger = logging.getLogger(__name__)

# Import database to get whale addresses
from database import Database

class HeliusWebhookHandler:
    
    def __init__(self, on_transaction: Callable):
        """
        Initialize webhook handler
        """
        self.on_transaction = on_transaction
        self.app = Flask(__name__)
        self.db = Database()
        self.setup_routes()
    
    def _get_whale_addresses(self) -> Set[str]:
        """Get all tracked whale addresses from database"""
        whales = self.db.get_all_whales()
        return {w['address'] for w in whales}
    
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
                
                # Get current whale addresses
                whale_addresses = self._get_whale_addresses()
                logger.info(f"Tracking {len(whale_addresses)} whale addresses")
                
                # Process each transaction
                for tx in transactions:
                    # Find which whale this transaction belongs to
                    whale_address = self._find_whale_in_transaction(tx, whale_addresses)
                    
                    if whale_address:
                        logger.info(f"✅ Found whale {whale_address[:12]}... in transaction")
                        # Process in background using thread
                        import threading
                        thread = threading.Thread(
                            target=lambda t=tx, w=whale_address: asyncio.run(self.on_transaction(t, w)),
                            daemon=True
                        )
                        thread.start()
                    else:
                        # Log what addresses we found for debugging
                        found_addresses = self._get_all_addresses_in_tx(tx)
                        logger.warning(f"No known whale found. Addresses in transaction: {[a[:10]+'...' for a in found_addresses[:10]]}")
                
                return jsonify({'status': 'received'}), 200
                
            except Exception as e:
                logger.error(f"Error processing webhook: {e}", exc_info=True)
                return jsonify({'error': 'Internal error'}), 500
    
    def _get_all_addresses_in_tx(self, tx_data: Dict) -> list:
        """Get all addresses mentioned in a transaction"""
        addresses = set()
        
        # From accountData
        for account in tx_data.get('accountData', []):
            if account.get('account'):
                addresses.add(account['account'])
        
        # From native transfers
        for transfer in tx_data.get('nativeTransfers', []):
            if transfer.get('fromUserAccount'):
                addresses.add(transfer['fromUserAccount'])
            if transfer.get('toUserAccount'):
                addresses.add(transfer['toUserAccount'])
        
        # From token transfers
        for transfer in tx_data.get('tokenTransfers', []):
            if transfer.get('fromUserAccount'):
                addresses.add(transfer['fromUserAccount'])
            if transfer.get('toUserAccount'):
                addresses.add(transfer['toUserAccount'])
        
        # From fee payer
        if tx_data.get('feePayer'):
            addresses.add(tx_data['feePayer'])
        
        return list(addresses)
    
    def _find_whale_in_transaction(self, tx_data: Dict, whale_addresses: Set[str]) -> str:
        """
        Find if any of our tracked whales are in this transaction
        """
        # Get all addresses in the transaction
        tx_addresses = self._get_all_addresses_in_tx(tx_data)
        
        # Check if any match our whales
        for addr in tx_addresses:
            if addr in whale_addresses:
                return addr
        
        return None
    
    def run(self, host: str = '0.0.0.0', port: int = 5000):
        """Run the Flask webhook server"""
        logger.info(f"Starting Helius webhook handler on {host}:{port}")
        self.app.run(host=host, port=port)
