"""
Authorization and Access Control
Enforces chat allowlist and owner-only permissions
"""

import os
import logging
from typing import Set
from telegram import Update

logger = logging.getLogger(__name__)

class AuthManager:
    """Manages authorization for multi-chat bot"""
    
    def __init__(self):
        # Parse allowed chat IDs
        allowed_ids_str = os.getenv('ALLOWED_CHAT_IDS', '')
        self.allowed_chat_ids: Set[int] = set()
        
        if allowed_ids_str:
            try:
                self.allowed_chat_ids = {
                    int(id.strip()) 
                    for id in allowed_ids_str.split(',') 
                    if id.strip()
                }
                logger.info(f"Allowed chat IDs: {self.allowed_chat_ids}")
            except ValueError as e:
                logger.error(f"Invalid ALLOWED_CHAT_IDS: {e}")
                raise ValueError("ALLOWED_CHAT_IDS must be comma-separated integers")
        
        # Get owner user ID
        owner_id_str = os.getenv('OWNER_TELEGRAM_USER_ID', '')
        if not owner_id_str:
            raise ValueError("OWNER_TELEGRAM_USER_ID not set!")
        
        try:
            self.owner_user_id = int(owner_id_str)
            logger.info(f"Owner user ID: {self.owner_user_id}")
        except ValueError:
            raise ValueError("OWNER_TELEGRAM_USER_ID must be an integer")
    
    def is_chat_allowed(self, chat_id: int) -> bool:
        """Check if chat is in allowlist"""
        if not self.allowed_chat_ids:
            return True
        return chat_id in self.allowed_chat_ids
    
    def is_owner(self, user_id: int) -> bool:
        """Check if user is the bot owner"""
        return user_id == self.owner_user_id
    
    def get_chat_id_from_update(self, update: Update) -> int:
        """Extract chat_id from update"""
        if update.effective_chat:
            return update.effective_chat.id
        return None
    
    def get_user_id_from_update(self, update: Update) -> int:
        """Extract user_id from update"""
        if update.effective_user:
            return update.effective_user.id
        return None
