"""
Database module for whale tracker bot
Manages whale wallets and processed transactions
"""

import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = 'whale_tracker.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Whales table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT UNIQUE NOT NULL,
                address TEXT UNIQUE NOT NULL,
                active INTEGER DEFAULT 1,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Processed transactions (deduplication)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_txs (
                signature TEXT PRIMARY KEY,
                processed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default whales
        default_whales = [
            ('Gake', 'DNfuF1L62WWyW3pNakVkyGGFzVVhj4Yr52jSmdTyeBHm'),
            ('Trader Pow', '8zFZHuSRuDpuAR7J6FzwyF3vKNx4CVW3DFHJerQhc7Zd'),
            ('Gake.Alt', 'EwTNPYTuwxMzrvL19nzBsSLXdAoEmVBKkisN87csKgtt'),
            ('Ansem', 'AVAZvHLR2PcWpDf8BXY4rVxNHYRBytycHkcB5z5QNXYm')
        ]
        
        for label, address in default_whales:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO whales (label, address) VALUES (?, ?)",
                    (label, address)
                )
            except Exception as e:
                logger.error(f"Error inserting default whale {label}: {e}")
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    def get_all_whales(self) -> List[Dict]:
        """Get all whales"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM whales ORDER BY label")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_active_whales(self) -> List[Dict]:
        """Get only active whales"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM whales WHERE active = 1 ORDER BY label")
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_whale_by_address(self, address: str) -> Optional[Dict]:
        """Get whale by address"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM whales WHERE address = ?", (address,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_whale_by_label(self, label: str) -> Optional[Dict]:
        """Get whale by label"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM whales WHERE label = ? COLLATE NOCASE", (label,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def add_whale(self, label: str, address: str) -> bool:
        """Add new whale"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO whales (label, address) VALUES (?, ?)",
                (label, address)
            )
            conn.commit()
            conn.close()
            logger.info(f"Added whale: {label} ({address})")
            return True
        except sqlite3.IntegrityError:
            logger.error(f"Whale already exists: {label} or {address}")
            return False
    
    def remove_whale(self, identifier: str) -> bool:
        """Remove whale by label or address"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM whales WHERE label = ? COLLATE NOCASE OR address = ?",
            (identifier, identifier)
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if deleted:
            logger.info(f"Removed whale: {identifier}")
        return deleted
    
    def set_whale_active(self, identifier: str, active: bool) -> bool:
        """Activate or deactivate whale"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE whales SET active = ? WHERE label = ? COLLATE NOCASE OR address = ?",
            (1 if active else 0, identifier, identifier)
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if updated:
            status = "activated" if active else "paused"
            logger.info(f"Whale {identifier} {status}")
        return updated
    
    def pause_all_whales(self):
        """Pause all whales"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE whales SET active = 0")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info(f"Paused all whales ({count})")
        return count
    
    def resume_all_whales(self):
        """Resume all whales"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE whales SET active = 1")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info(f"Resumed all whales ({count})")
        return count
    
    def is_tx_processed(self, signature: str) -> bool:
        """Check if transaction already processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_txs WHERE signature = ?", (signature,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    
    def mark_tx_processed(self, signature: str):
        """Mark transaction as processed"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO processed_txs (signature) VALUES (?)",
                (signature,)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error marking tx as processed: {e}")
    
    def cleanup_old_txs(self, days: int = 7):
        """Clean up old processed transactions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM processed_txs WHERE processed_at < datetime('now', '-' || ? || ' days')",
            (days,)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old transactions")
