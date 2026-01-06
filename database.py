import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from loguru import logger
from models import ProcessedTicket, BotMetrics, TicketResponse
from config import Config

class DatabaseManager:
    """Database manager for storing bot data and preventing duplicate processing"""
    
    def __init__(self, db_path: str = "pisces_support_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create processed tickets table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processed_tickets (
                        ticket_id TEXT PRIMARY KEY,
                        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        response_id TEXT,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create ticket responses table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ticket_responses (
                        response_id TEXT PRIMARY KEY,
                        ticket_id TEXT NOT NULL,
                        response_text TEXT NOT NULL,
                        confidence_score REAL NOT NULL,
                        response_type TEXT NOT NULL,
                        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create bot metrics table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        total_tickets_processed INTEGER DEFAULT 0,
                        successful_responses INTEGER DEFAULT 0,
                        failed_responses INTEGER DEFAULT 0,
                        average_response_time REAL DEFAULT 0.0,
                        last_run_time TIMESTAMP,
                        uptime_hours REAL DEFAULT 0.0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for better performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_tickets_time ON processed_tickets(processed_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticket_responses_ticket ON ticket_responses(ticket_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticket_responses_time ON ticket_responses(generated_at)")
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def is_ticket_processed(self, ticket_id: str) -> bool:
        """Check if a ticket has already been processed"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM processed_tickets WHERE ticket_id = ?",
                    (ticket_id,)
                )
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            logger.error(f"Error checking if ticket {ticket_id} is processed: {e}")
            return False
    
    def mark_ticket_processed(self, processed_ticket: ProcessedTicket):
        """Mark a ticket as processed"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO processed_tickets 
                    (ticket_id, processed_at, response_id, status, error_message)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    processed_ticket.ticket_id,
                    processed_ticket.processed_at.isoformat(),
                    processed_ticket.response_id,
                    processed_ticket.status,
                    processed_ticket.error_message
                ))
                conn.commit()
                logger.info(f"Marked ticket {processed_ticket.ticket_id} as processed")
        except Exception as e:
            logger.error(f"Error marking ticket {processed_ticket.ticket_id} as processed: {e}")
    
    def save_ticket_response(self, response: TicketResponse):
        """Save a ticket response to the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO ticket_responses 
                    (response_id, ticket_id, response_text, confidence_score, response_type, generated_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"resp_{response.ticket_id}_{int(datetime.utcnow().timestamp())}",
                    response.ticket_id,
                    response.response_text,
                    response.confidence_score,
                    response.response_type,
                    response.generated_at.isoformat(),
                    json.dumps(response.metadata)
                ))
                conn.commit()
                logger.info(f"Saved response for ticket {response.ticket_id}")
        except Exception as e:
            logger.error(f"Error saving response for ticket {response.ticket_id}: {e}")
    
    def get_recent_responses(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent responses for analysis"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)
                cursor.execute("""
                    SELECT * FROM ticket_responses 
                    WHERE generated_at >= ?
                    ORDER BY generated_at DESC
                """, (cutoff_time.isoformat(),))
                
                columns = [description[0] for description in cursor.description]
                rows = cursor.fetchall()
                
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Error getting recent responses: {e}")
            return []
    
    def update_metrics(self, metrics: BotMetrics):
        """Update bot performance metrics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if metrics record exists
                cursor.execute("SELECT COUNT(*) FROM bot_metrics")
                count = cursor.fetchone()[0]
                
                if count == 0:
                    # Create initial metrics record
                    cursor.execute("""
                        INSERT INTO bot_metrics 
                        (total_tickets_processed, successful_responses, failed_responses, 
                         average_response_time, last_run_time, uptime_hours)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        metrics.total_tickets_processed,
                        metrics.successful_responses,
                        metrics.failed_responses,
                        metrics.average_response_time,
                        metrics.last_run_time.isoformat() if metrics.last_run_time else None,
                        metrics.uptime_hours
                    ))
                else:
                    # Update existing metrics
                    cursor.execute("""
                        UPDATE bot_metrics SET
                        total_tickets_processed = ?,
                        successful_responses = ?,
                        failed_responses = ?,
                        average_response_time = ?,
                        last_run_time = ?,
                        uptime_hours = ?,
                        updated_at = CURRENT_TIMESTAMP
                    """, (
                        metrics.total_tickets_processed,
                        metrics.successful_responses,
                        metrics.failed_responses,
                        metrics.average_response_time,
                        metrics.last_run_time.isoformat() if metrics.last_run_time else None,
                        metrics.uptime_hours
                    ))
                
                conn.commit()
                logger.info("Bot metrics updated successfully")
        except Exception as e:
            logger.error(f"Error updating bot metrics: {e}")
    
    def get_metrics(self) -> Optional[BotMetrics]:
        """Get current bot metrics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM bot_metrics ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                
                if row:
                    return BotMetrics(
                        total_tickets_processed=row[1],
                        successful_responses=row[2],
                        failed_responses=row[3],
                        average_response_time=row[4],
                        last_run_time=datetime.fromisoformat(row[5]) if row[5] else None,
                        uptime_hours=row[6]
                    )
                return None
        except Exception as e:
            logger.error(f"Error getting bot metrics: {e}")
            return None
    
    def cleanup_old_records(self, days: int = 30):
        """Clean up old records to prevent database bloat"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                # Clean up old processed tickets
                cursor.execute(
                    "DELETE FROM processed_tickets WHERE processed_at < ?",
                    (cutoff_date.isoformat(),)
                )
                
                # Clean up old responses
                cursor.execute(
                    "DELETE FROM ticket_responses WHERE generated_at < ?",
                    (cutoff_date.isoformat(),)
                )
                
                conn.commit()
                logger.info(f"Cleaned up records older than {days} days")
        except Exception as e:
            logger.error(f"Error cleaning up old records: {e}")
