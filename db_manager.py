"""
Multi-chat Database Manager with Postgres
Handles per-chat settings and whale tracking with complete isolation
"""

import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Postgres database manager with per-chat isolation"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set!")
        
        # Log DB connection info (safe)
        try:
            import psycopg2
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            cursor.execute("SELECT current_database(), version()")
            db_name, version = cursor.fetchone()
            logger.info(f"✅ DB connected OK: database={db_name}, version={version[:50]}")
            conn.close()
        except Exception as e:
            logger.error(f"❌ DB connection test failed: {e}")
            raise
        
        self._init_schema()
        logger.info("Database manager initialized")
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = psycopg2.connect(self.database_url)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id BIGINT PRIMARY KEY,
                    chat_name TEXT,
                    alerts_enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS whales (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    label TEXT NOT NULL,
                    address TEXT NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, address),
                    FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_transactions (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    signature TEXT NOT NULL,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, signature),
                    FOREIGN KEY (chat_id) REFERENCES chat_settings(chat_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_whales_chat_id ON whales(chat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_whales_address ON whales(address)")
            
            conn.commit()
            
            # Startup diagnostic: count whales
            cursor.execute("SELECT COUNT(*) FROM whales")
            total_whales = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT chat_id) FROM whales")
            distinct_chats = cursor.fetchone()[0]
            logger.info(f"[STARTUP] Total whales in DB: {total_whales} across {distinct_chats} chats")
    
    def get_db_fingerprint(self) -> Dict:
        """Get database fingerprint for verification"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get DB connection info
            cursor.execute("SELECT current_database(), inet_server_addr()::text, inet_server_port()")
            db_name, host, port = cursor.fetchone()
            
            # Get whale counts
            cursor.execute("SELECT COUNT(*) FROM whales")
            total_whales = cursor.fetchone()[0]
            
            # Get per-chat counts
            cursor.execute("SELECT chat_id, COUNT(*) FROM whales GROUP BY chat_id")
            chat_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            logger.info(f"[DB_FINGERPRINT] db={db_name}, host={host}, port={port}, total_whales={total_whales}")
            
            return {
                'database': db_name,
                'host': host or 'unix_socket',
                'port': port or 'N/A',
                'status': '✅ Connected',
                'total_whales': total_whales,
                'chat_whale_count': chat_counts
            }
    
    def get_or_create_chat_settings(self, chat_id: int, chat_name: str = None) -> Dict:
        """Get or create settings for a chat"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM chat_settings WHERE chat_id = %s", (chat_id,))
            settings = cursor.fetchone()
            
            if settings:
                if chat_name:
                    cursor.execute(
                        "UPDATE chat_settings SET chat_name = %s, updated_at = CURRENT_TIMESTAMP WHERE chat_id = %s",
                        (chat_name, chat_id)
                    )
                return dict(settings)
            
            cursor.execute(
                "INSERT INTO chat_settings (chat_id, chat_name, alerts_enabled) VALUES (%s, %s, TRUE) RETURNING *",
                (chat_id, chat_name)
            )
            return dict(cursor.fetchone())
    
    def set_alerts_enabled(self, chat_id: int, enabled: bool) -> bool:
        """Enable/disable alerts for a chat"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE chat_settings SET alerts_enabled = %s WHERE chat_id = %s",
                (enabled, chat_id)
            )
            return cursor.rowcount > 0
    
    def add_whale(self, chat_id: int, label: str, address: str) -> bool:
        """Add a whale for a specific chat"""
        logger.info(f"[ADD_WHALE] ===== START =====")
        logger.info(f"[ADD_WHALE] chat_id={chat_id} (type: {type(chat_id).__name__})")
        logger.info(f"[ADD_WHALE] label={label}")
        logger.info(f"[ADD_WHALE] address={address[:30]}...")
        logger.info(f"[ADD_WHALE] table=whales")
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if whale already exists FOR THIS CHAT
                check_query = "SELECT id, label FROM whales WHERE chat_id = %s AND (label = %s OR address = %s)"
                logger.info(f"[ADD_WHALE] CHECK query: {check_query}")
                logger.info(f"[ADD_WHALE] CHECK params: chat_id={chat_id}, label={label}, address={address[:20]}...")
                
                cursor.execute(check_query, (chat_id, label, address))
                existing = cursor.fetchone()
                
                logger.info(f"[ADD_WHALE] CHECK result: {'FOUND' if existing else 'NOT FOUND'} ({existing})")
                
                if existing:
                    logger.warning(f"[ADD_WHALE] ❌ Whale already exists in chat {chat_id}: {existing}")
                    return False
                
                # Insert new whale
                insert_query = "INSERT INTO whales (chat_id, label, address, active) VALUES (%s, %s, %s, TRUE) RETURNING id"
                logger.info(f"[ADD_WHALE] INSERT query: {insert_query}")
                
                cursor.execute(insert_query, (chat_id, label, address))
                whale_id = cursor.fetchone()[0]
                
                logger.info(f"[ADD_WHALE] ✅ INSERT successful: whale_id={whale_id}")
                
                # IMMEDIATE VERIFICATION
                cursor.execute("SELECT COUNT(*) FROM whales WHERE chat_id = %s", (chat_id,))
                count_after = cursor.fetchone()[0]
                logger.info(f"[ADD_WHALE] VERIFY: Total whales for chat_id={chat_id} is now {count_after}")
                
                # List all whales for this chat
                cursor.execute("SELECT id, label, address FROM whales WHERE chat_id = %s", (chat_id,))
                all_whales = cursor.fetchall()
                logger.info(f"[ADD_WHALE] VERIFY: All whales in chat {chat_id}:")
                for w in all_whales:
                    logger.info(f"[ADD_WHALE]   - id={w[0]}, label={w[1]}, addr={w[2][:20]}...")
                
                logger.info(f"[ADD_WHALE] ===== SUCCESS =====")
                return True
                
        except psycopg2.IntegrityError as e:
            logger.error(f"[ADD_WHALE] ❌ Integrity error: {e}")
            return False
        except Exception as e:
            logger.error(f"[ADD_WHALE] ❌ Unexpected error: {e}", exc_info=True)
            return False
    
    def get_whales_for_chat(self, chat_id: int) -> List[Dict]:
        """Get all whales for a specific chat"""
        logger.info(f"[GET_WHALES] ===== START =====")
        logger.info(f"[GET_WHALES] chat_id={chat_id} (type: {type(chat_id).__name__})")
        logger.info(f"[GET_WHALES] table=whales")
        
        query = "SELECT * FROM whales WHERE chat_id = %s ORDER BY added_at DESC"
        logger.info(f"[GET_WHALES] query: {query}")
        logger.info(f"[GET_WHALES] WHERE clause: chat_id = {chat_id}")
        
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, (chat_id,))
            results = [dict(row) for row in cursor.fetchall()]
            
            logger.info(f"[GET_WHALES] rows_returned={len(results)}")
            logger.info(f"[GET_WHALES] ✅ Found {len(results)} whales for chat_id={chat_id}")
            
            # Log each whale
            for i, whale in enumerate(results):
                logger.info(f"[GET_WHALES] whale[{i}]: id={whale['id']}, label={whale['label']}, addr={whale['address'][:20]}..., active={whale['active']}")
            
            if len(results) == 0:
                # Double-check: are there ANY whales in the table?
                cursor.execute("SELECT COUNT(*) FROM whales")
                total = cursor.fetchone()[0]
                logger.warning(f"[GET_WHALES] No whales for this chat, but {total} total whales exist in DB")
                
                # Show what chat_ids DO have whales
                cursor.execute("SELECT DISTINCT chat_id FROM whales")
                existing_chats = [row[0] for row in cursor.fetchall()]
                logger.warning(f"[GET_WHALES] Chats with whales: {existing_chats}")
            
            logger.info(f"[GET_WHALES] ===== END =====")
            return results
    
    def get_whale_by_address(self, address: str) -> List[Dict]:
        """Get all chats tracking this whale address"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM whales WHERE address = %s AND active = TRUE",
                (address,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def remove_whale(self, chat_id: int, identifier: str) -> bool:
        """Remove a whale by label or address"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM whales WHERE chat_id = %s AND (label = %s OR address = %s)",
                (chat_id, identifier, identifier)
            )
            return cursor.rowcount > 0
    
    def set_whale_active(self, chat_id: int, identifier: str, active: bool) -> bool:
        """Pause/resume a whale"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE whales SET active = %s WHERE chat_id = %s AND (label = %s OR address = %s)",
                (active, chat_id, identifier, identifier)
            )
            return cursor.rowcount > 0
    
    def pause_all_whales(self, chat_id: int) -> int:
        """Pause all whales for a chat"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE whales SET active = FALSE WHERE chat_id = %s", (chat_id,))
            return cursor.rowcount
    
    def resume_all_whales(self, chat_id: int) -> int:
        """Resume all whales for a chat"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE whales SET active = TRUE WHERE chat_id = %s", (chat_id,))
            return cursor.rowcount
    
    def is_tx_processed(self, chat_id: int, signature: str) -> bool:
        """Check if transaction already processed for this chat"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_transactions WHERE chat_id = %s AND signature = %s",
                (chat_id, signature)
            )
            return cursor.fetchone() is not None
    
    def mark_tx_processed(self, chat_id: int, signature: str):
        """Mark transaction as processed for this chat"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO processed_transactions (chat_id, signature) VALUES (%s, %s)",
                    (chat_id, signature)
                )
        except psycopg2.IntegrityError:
            pass
