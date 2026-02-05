"""
Simple SQLite Database for Whale Tracking
"""

import sqlite3
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "whales.db"):
        self.db_path = db_path
        self._init_db()
        self._seed_whales()
        logger.info("Database initialized")
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        """Initialize database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT UNIQUE NOT NULL,
                address TEXT UNIQUE NOT NULL,
                active INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_transactions (
                signature TEXT PRIMARY KEY,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _seed_whales(self):
        """Seed initial whales if table is empty"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM whales")
        count = cursor.fetchone()[0]
        
        if count == 0:
            initial_whales = [
                ("Gake", "DNfuF1L62WWyW3pNakVkyGGFzVVhj4Yr52jSmdTyeBHm"),
                ("GakeAlt", "EwTNPYTuwxMzrvL19nzBsSLXdAoEmVBKkisN87csKgtt"),
                ("TraderPow", "8zFZHuSRuDpuAR7J6FzwyF3vKNx4CVW3DFHJerQhc7Zd"),
                ("Ansem", "AVAZvHLR2PcWpDf8BXY4rVxNHYRBytycHkcB5z5QNXYm"),
            ]
            
            for label, address in initial_whales:
                try:
                    cursor.execute(
                        "INSERT INTO whales (label, address) VALUES (?, ?)",
                        (label, address)
                    )
                    logger.info(f"Seeded whale: {label}")
                except sqlite3.IntegrityError:
                    pass
            
            conn.commit()
        
        conn.close()
    
    def get_all_whales(self) -> List[Dict]:
        """Get all whales"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, label, address, active FROM whales")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {"id": r[0], "label": r[1], "address": r[2], "active": bool(r[3])}
            for r in rows
        ]
    
    def get_whale_by_address(self, address: str) -> Optional[Dict]:
        """Get whale by address"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, label, address, active FROM whales WHERE address = ?",
            (address,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {"id": row[0], "label": row[1], "address": row[2], "active": bool(row[3])}
        return None
    
    def add_whale(self, label: str, address: str) -> bool:
        """Add a new whale"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO whales (label, address) VALUES (?, ?)",
                (label, address)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def remove_whale(self, identifier: str) -> bool:
        """Remove whale by label or address"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM whales WHERE label = ? OR address = ?",
            (identifier, identifier)
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
    
    def set_whale_active(self, identifier: str, active: bool) -> bool:
        """Set whale active status"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE whales SET active = ? WHERE label = ? OR address = ?",
            (1 if active else 0, identifier, identifier)
        )
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return updated
    
    def pause_all_whales(self) -> int:
        """Pause all whales"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE whales SET active = 0")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count
    
    def resume_all_whales(self) -> int:
        """Resume all whales"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE whales SET active = 1")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count
    
    def is_tx_processed(self, signature: str) -> bool:
        """Check if transaction was already processed"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM processed_transactions WHERE signature = ?",
            (signature,)
        )
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    
    def mark_tx_processed(self, signature: str):
        """Mark transaction as processed"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO processed_transactions (signature) VALUES (?)",
                (signature,)
            )
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            pass
