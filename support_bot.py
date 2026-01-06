import time
from datetime import datetime, timedelta
from typing import List, Optional
from loguru import logger
from models import Ticket, TicketResponse, ProcessedTicket, BotMetrics
from config import Config
from servicedesk_client import ServiceDeskPlusClient
from ai_processor import AIProcessor
from database import DatabaseManager

class PiscesSupportBot:
    """Main support bot for PiscesER1 Marine"""
    
    def __init__(self):
        # Initialize ServiceDesk Plus client
        self.ticket_client = ServiceDeskPlusClient()
        logger.info("Using ServiceDesk Plus client")
            
        self.ai_processor = AIProcessor()
        self.db_manager = DatabaseManager()
        
        # Bot state
        self.is_running = False
        self.start_time = None
        self.metrics = BotMetrics()
        
        # Load existing metrics
        existing_metrics = self.db_manager.get_metrics()
        if existing_metrics:
            self.metrics = existing_metrics
        
        logger.info("PiscesER1 Marine Support Bot initialized")
    
    def start(self):
        """Start the support bot"""
        if self.is_running:
            logger.warning("Bot is already running")
            return
        
        self.is_running = True
        self.start_time = datetime.utcnow()
        logger.info("PiscesER1 Marine Support Bot started")
        
        try:
            # Test connections
            if not self._test_connections():
                logger.error("Connection tests failed. Bot cannot start.")
                return False
            
            # Initial cleanup
            self.db_manager.cleanup_old_records()
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            self.is_running = False
            return False
    
    def stop(self):
        """Stop the support bot"""
        if not self.is_running:
            logger.warning("Bot is not running")
            return
        
        self.is_running = False
        logger.info("PiscesER1 Marine Support Bot stopped")
        
        # Update final metrics
        self._update_metrics()
    
    def _test_connections(self) -> bool:
        """Test all external connections"""
        logger.info("Testing external connections...")
        
        # Test ServiceDesk Plus API
        if not self.ticket_client.test_connection():
            logger.error("ServiceDesk Plus API connection test failed")
            return False
        
        # Test Gemini API
        if not self.ai_processor.test_connection():
            logger.error("Gemini API connection test failed")
            return False
        
        logger.info("All connection tests passed")
        return True
    
    def process_tickets(self, max_tickets: Optional[int] = None) -> dict:
        """Process new tickets and generate responses"""
        
        if not self.is_running:
            logger.warning("Bot is not running")
            return {"success": False, "error": "Bot not running"}
        
        start_time = time.time()
        processed_count = 0
        success_count = 0
        error_count = 0
        
        try:
            # Fetch new tickets
            tickets = self.ticket_client.get_tickets(
                status="Open",
                limit=max_tickets or Config.MAX_TICKETS_PER_RUN
            )
            
            if not tickets:
                logger.info("No new tickets to process")
                return {
                    "success": True,
                    "processed": 0,
                    "successful": 0,
                    "errors": 0,
                    "duration": time.time() - start_time
                }
            
            logger.info(f"Found {len(tickets)} tickets to process")
            
            # Process each ticket
            for ticket in tickets:
                try:
                    # Check if already processed
                    if self.db_manager.is_ticket_processed(ticket.ticket_id):
                        logger.debug(f"Ticket {ticket.ticket_id} already processed, skipping")
                        continue
                    
                    # Process the ticket
                    result = self._process_single_ticket(ticket)
                    
                    if result["success"]:
                        success_count += 1
                        logger.info(f"Successfully processed ticket {ticket.ticket_id}")
                    else:
                        error_count += 1
                        logger.error(f"Failed to process ticket {ticket.ticket_id}: {result['error']}")
                    
                    processed_count += 1
                    
                    # Small delay between tickets to avoid overwhelming APIs
                    time.sleep(1)
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Unexpected error processing ticket {ticket.ticket_id}: {e}")
                    
                    # Mark as processed with error
                    self.db_manager.mark_ticket_processed(ProcessedTicket(
                        ticket_id=ticket.ticket_id,
                        status="error",
                        error_message=str(e)
                    ))
            
            # Update metrics
            self._update_processing_metrics(processed_count, success_count, error_count, time.time() - start_time)
            
            logger.info(f"Processing complete: {processed_count} processed, {success_count} successful, {error_count} errors")
            
            return {
                "success": True,
                "processed": processed_count,
                "successful": success_count,
                "errors": error_count,
                "duration": time.time() - start_time
            }
            
        except Exception as e:
            logger.error(f"Error in process_tickets: {e}")
            return {
                "success": False,
                "error": str(e),
                "processed": processed_count,
                "successful": success_count,
                "errors": error_count,
                "duration": time.time() - start_time
            }
    
    def _process_single_ticket(self, ticket: Ticket) -> dict:
        """Process a single ticket and generate response"""
        
        try:
            # Generate AI response
            response = self.ai_processor.generate_response(ticket)
            
            if not response:
                return {
                    "success": False,
                    "error": "Failed to generate AI response"
                }
            
            # Save response to database
            self.db_manager.save_ticket_response(response)
            
            # Send actual reply to customer (email)
            reply_success = self.ticket_client.send_reply_to_customer(
                ticket_id=ticket.ticket_id,
                response_text=response.response_text,
                subject=f"Re: {ticket.subject}"
            )
            
            if not reply_success:
                # If reply fails, try posting as a note instead (fallback)
                logger.warning(f"Reply failed for ticket {ticket.ticket_id}, falling back to note")
                note_success = self.ticket_client.post_ticket_response(
                    ticket_id=ticket.ticket_id,
                    response_text=response.response_text
                )
                if not note_success:
                    return {
                        "success": False,
                        "error": "Failed to send reply or post note to ServiceDesk Plus"
                    }
            
            # Mark ticket as processed
            self.db_manager.mark_ticket_processed(ProcessedTicket(
                ticket_id=ticket.ticket_id,
                response_id=response.ticket_id,
                status="completed"
            ))
            
            # Update ticket status if it's a fallback response
            if response.response_type == "fallback":
                self.ticket_client.update_ticket_status(ticket.ticket_id, "Pending")
            
            return {
                "success": True,
                "response_id": response.ticket_id,
                "confidence": response.confidence_score,
                "response_type": response.response_type
            }
            
        except Exception as e:
            logger.error(f"Error processing ticket {ticket.ticket_id}: {e}")
            
            # Mark as processed with error
            self.db_manager.mark_ticket_processed(ProcessedTicket(
                ticket_id=ticket.ticket_id,
                status="error",
                error_message=str(e)
            ))
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def _update_processing_metrics(self, processed: int, successful: int, errors: int, duration: float):
        """Update bot metrics after processing"""
        
        self.metrics.total_tickets_processed += processed
        self.metrics.successful_responses += successful
        self.metrics.failed_responses += errors
        self.metrics.last_run_time = datetime.utcnow()
        
        # Update average response time
        if successful > 0:
            current_avg = self.metrics.average_response_time
            total_responses = self.metrics.successful_responses + self.metrics.failed_responses
            new_avg = ((current_avg * (total_responses - successful)) + duration) / total_responses
            self.metrics.average_response_time = new_avg
        
        # Update uptime
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds() / 3600
            self.metrics.uptime_hours = uptime
        
        # Save to database
        self.db_manager.update_metrics(self.metrics)
    
    def _update_metrics(self):
        """Update final metrics when stopping"""
        if self.start_time:
            uptime = (datetime.utcnow() - self.start_time).total_seconds() / 3600
            self.metrics.uptime_hours = uptime
            self.db_manager.update_metrics(self.metrics)
    
    def get_status(self) -> dict:
        """Get current bot status"""
        return {
            "is_running": self.is_running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_hours": self.metrics.uptime_hours,
            "total_tickets_processed": self.metrics.total_tickets_processed,
            "successful_responses": self.metrics.successful_responses,
            "failed_responses": self.metrics.failed_responses,
            "average_response_time": self.metrics.average_response_time,
            "last_run_time": self.metrics.last_run_time.isoformat() if self.metrics.last_run_time else None
        }
    
    def get_recent_activity(self, hours: int = 24) -> List[dict]:
        """Get recent bot activity"""
        return self.db_manager.get_recent_responses(hours)
    
    def run_continuous(self, interval_minutes: Optional[int] = None):
        """Run the bot continuously with periodic processing"""
        
        if not self.start():
            logger.error("Failed to start bot")
            return
        
        interval = interval_minutes or Config.CHECK_INTERVAL_MINUTES
        
        logger.info(f"Starting continuous operation with {interval}-minute intervals")
        
        try:
            while self.is_running:
                # Process tickets
                result = self.process_tickets()
                
                if result["success"]:
                    logger.info(f"Processing cycle completed: {result}")
                else:
                    logger.error(f"Processing cycle failed: {result}")
                
                # Wait for next cycle
                logger.info(f"Waiting {interval} minutes until next processing cycle...")
                time.sleep(interval * 60)
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, stopping bot...")
        except Exception as e:
            logger.error(f"Unexpected error in continuous operation: {e}")
        finally:
            self.stop()
    
    def run_once(self):
        """Run the bot once for immediate processing"""
        
        if not self.start():
            logger.error("Failed to start bot")
            return False
        
        try:
            result = self.process_tickets()
            logger.info(f"Single run completed: {result}")
            return result["success"]
        finally:
            self.stop()
