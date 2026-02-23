import sqlite3
import os
from datetime import datetime

class ThreatLogger:
    def __init__(self, db_filename="lensblock_audit.db"):
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_filename)
        self._initialize_db()

    def _initialize_db(self):
        """Creates the necessary SQLite tables if they do not exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS security_logs (
                    IncidentID INTEGER PRIMARY KEY AUTOINCREMENT,
                    Timestamp TEXT NOT NULL,
                    Threat_Type TEXT NOT NULL,
                    Confidence_Score REAL NOT NULL,
                    Duration REAL NOT NULL
                )
            ''')
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"Database initialization failed: {e}")

    def log_threat(self, threat_type: str, confidence_score: float, duration: float):
        """
        Logs a confirmed threat event to the local database.
        
        :param threat_type: Description of the threat (e.g., 'cell phone')
        :param confidence_score: The detection confidence (e.g., 0.85)
        :param duration: How long the threat was present in seconds
        """
        timestamp = datetime.now().isoformat()
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO security_logs (Timestamp, Threat_Type, Confidence_Score, Duration)
                VALUES (?, ?, ?, ?)
            ''', (timestamp, threat_type, confidence_score, duration))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"Failed to log threat: {e}")

    def get_recent_logs(self, limit=50):
        """Retrieves the most recent security logs."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM security_logs
                ORDER BY Timestamp DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        except sqlite3.Error as e:
            print(f"Failed to retrieve logs: {e}")
            return []
