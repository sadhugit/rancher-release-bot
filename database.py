"""
Database management using SQLite
Stores release data and analysis results
"""

import aiosqlite
import json
from typing import Optional, List, Dict
from datetime import datetime

class Database:
    def __init__(self, config: dict):
        self.db_path = config['path']
        self.conn = None
    
    async def init_db(self):
        """Initialize database schema"""
        self.conn = await aiosqlite.connect(self.db_path)
        
        # Enable WAL mode for better concurrency
        await self.conn.execute("PRAGMA journal_mode=WAL")
        
        # Create releases table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS releases (
                version TEXT PRIMARY KEY,
                release_data TEXT NOT NULL,
                analysis TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create notifications table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL,
                channel TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (version) REFERENCES releases(version)
            )
        """)
        
        # Create indexes for faster queries
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_releases_created 
            ON releases(created_at DESC)
        """)
        
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notifications_version 
            ON notifications(version)
        """)
        
        await self.conn.commit()
        print("✅ Database initialized")
    
    async def store_release(
        self, 
        version: str, 
        release_data: Dict, 
        analysis: Dict
    ):
        """Store release and analysis"""
        await self.conn.execute("""
            INSERT OR REPLACE INTO releases 
            (version, release_data, analysis, updated_at)
            VALUES (?, ?, ?, ?)
        """, (
            version,
            json.dumps(release_data, ensure_ascii=False),
            json.dumps(analysis, ensure_ascii=False),
            datetime.now().isoformat()
        ))
        await self.conn.commit()
    
    async def get_release(self, version: str) -> Optional[Dict]:
        """Get release by version"""
        async with self.conn.execute(
            "SELECT * FROM releases WHERE version = ?", (version,)
        ) as cursor:
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'version': row[0],
                'release_data': json.loads(row[1]),
                'analysis': json.loads(row[2]),
                'created_at': row[3],
                'updated_at': row[4]
            }
    
    async def get_latest_release(self) -> Optional[Dict]:
        """Get most recent release"""
        async with self.conn.execute(
            "SELECT * FROM releases ORDER BY created_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'version': row[0],
                'release_data': json.loads(row[1]),
                'analysis': json.loads(row[2]),
                'created_at': row[3],
                'updated_at': row[4]
            }
    
    async def get_all_releases(self, limit: int = 100) -> List[Dict]:
        """Get all releases (limited)"""
        async with self.conn.execute(
            """SELECT version, analysis, created_at 
               FROM releases 
               ORDER BY created_at DESC 
               LIMIT ?""",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            
            return [
                {
                    'version': row[0],
                    'analysis': json.loads(row[1]),
                    'created_at': row[2]
                }
                for row in rows
            ]
    
    async def search_releases(self, query: str) -> List[Dict]:
        """Search releases by version or content"""
        search_pattern = f'%{query}%'
        
        async with self.conn.execute("""
            SELECT version, analysis, created_at 
            FROM releases 
            WHERE version LIKE ? 
               OR analysis LIKE ?
            ORDER BY created_at DESC
            LIMIT 50
        """, (search_pattern, search_pattern)) as cursor:
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                analysis = json.loads(row[1])
                results.append({
                    'version': row[0],
                    'summary': analysis.get('summary', 'No summary'),
                    'severity': analysis.get('severity', 'normal'),
                    'created_at': row[2]
                })
            
            return results
    
    async def record_notification(self, version: str, channel: str):
        """Record that a notification was sent"""
        await self.conn.execute("""
            INSERT INTO notifications (version, channel)
            VALUES (?, ?)
        """, (version, channel))
        await self.conn.commit()
    
    async def get_notification_history(
        self, 
        version: Optional[str] = None
    ) -> List[Dict]:
        """Get notification history"""
        if version:
            query = """
                SELECT * FROM notifications 
                WHERE version = ? 
                ORDER BY sent_at DESC
            """
            params = (version,)
        else:
            query = """
                SELECT * FROM notifications 
                ORDER BY sent_at DESC 
                LIMIT 100
            """
            params = ()
        
        async with self.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            
            return [
                {
                    'id': row[0],
                    'version': row[1],
                    'channel': row[2],
                    'sent_at': row[3]
                }
                for row in rows
            ]
    
    async def get_stats(self) -> Dict:
        """Get database statistics"""
        # Total releases
        async with self.conn.execute(
            "SELECT COUNT(*) FROM releases"
        ) as cursor:
            total_releases = (await cursor.fetchone())[0]
        
        # Total notifications
        async with self.conn.execute(
            "SELECT COUNT(*) FROM notifications"
        ) as cursor:
            total_notifications = (await cursor.fetchone())[0]
        
        # Latest release
        latest = await self.get_latest_release()
        
        return {
            'total_releases': total_releases,
            'total_notifications': total_notifications,
            'latest_release': latest['version'] if latest else None,
            'database_size_bytes': self._get_db_size()
        }
    
    def _get_db_size(self) -> int:
        """Get database file size in bytes"""
        try:
            import os
            return os.path.getsize(self.db_path)
        except:
            return 0
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            print("✅ Database connection closed")