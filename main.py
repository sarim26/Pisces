#!/usr/bin/env python3
"""
PiscesER1 Marine Support Bot - Main Entry Point

This script provides the command-line interface for the automated customer support
ticket reply system for PiscesER1 Marine using ServiceDesk Plus and OpenAI.

Usage:
    python main.py --mode continuous --interval 5
    python main.py --mode once
    python main.py --test-connections
    python main.py --status
"""

import argparse
import sys
import signal
from loguru import logger
from support_bot import PiscesSupportBot
from config import Config

def setup_logging():
    """Setup logging configuration"""
    # Remove default handler
    logger.remove()
    
    # Add console handler with color
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=Config.LOG_LEVEL,
        colorize=True
    )
    
    # Add file handler
    logger.add(
        Config.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=Config.LOG_LEVEL,
        rotation="10 MB",
        retention="30 days",
        compression="zip"
    )

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully"""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

def test_connections():
    """Test all external connections"""
    logger.info("Testing external connections...")
    
    try:
        bot = PiscesSupportBot()
        
        # Test ServiceDesk Plus API
        logger.info("Testing ServiceDesk Plus API connection...")
        if bot.ticket_client.test_connection():
            logger.success("ServiceDesk Plus API connection successful")
        else:
            logger.error("ServiceDesk Plus API connection failed")
            return False
        
        # Test OpenAI API
        logger.info("Testing OpenAI API connection...")
        if bot.ai_processor.test_connection():
            logger.success("OpenAI API connection successful")
        else:
            logger.error("OpenAI API connection failed")
            return False
        
        logger.success("All connection tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False

def show_status():
    """Show current bot status"""
    try:
        bot = PiscesSupportBot()
        status = bot.get_status()
        
        print("\n" + "="*60)
        print("PISCESER1 MARINE SUPPORT BOT STATUS")
        print("="*60)
        
        print(f"Bot Running: {'Yes' if status['is_running'] else 'No'}")
        if status['start_time']:
            print(f"Start Time: {status['start_time']}")
        print(f"Uptime: {status['uptime_hours']:.2f} hours")
        print(f"Total Tickets Processed: {status['total_tickets_processed']}")
        print(f"Successful Responses: {status['successful_responses']}")
        print(f"Failed Responses: {status['failed_responses']}")
        print(f"Average Response Time: {status['average_response_time']:.2f} seconds")
        
        if status['last_run_time']:
            print(f"Last Run: {status['last_run_time']}")
        
        # Show recent activity
        recent_activity = bot.get_recent_activity(hours=24)
        if recent_activity:
            print(f"\nRecent Activity (Last 24 hours): {len(recent_activity)} responses")
        else:
            print("\nRecent Activity: No responses in the last 24 hours")
        
        print("="*60)
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")

def run_bot(mode: str, interval: int = None):
    """Run the support bot in the specified mode"""
    
    if not Config.validate_config():
        logger.error("Configuration validation failed. Please check your environment variables.")
        return False
    
    bot = PiscesSupportBot()
    
    try:
        if mode == "continuous":
            logger.info(f"Starting continuous mode with {interval}-minute intervals")
            bot.run_continuous(interval_minutes=interval)
        elif mode == "once":
            logger.info("Running bot once")
            success = bot.run_once()
            if success:
                logger.success("Single run completed successfully")
            else:
                logger.error("Single run failed")
            return success
        else:
            logger.error(f"Unknown mode: {mode}")
            return False
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        return False
    
    return True

def main():
    """Main entry point"""
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Setup logging
    setup_logging()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="PiscesER1 Marine Support Bot - Automated Customer Support System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode continuous --interval 5    # Run continuously every 5 minutes
  python main.py --mode once                       # Run once and exit
  python main.py --test-connections                # Test API connections
  python main.py --status                          # Show bot status
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["continuous", "once"],
        help="Bot operation mode"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=Config.CHECK_INTERVAL_MINUTES,
        help=f"Processing interval in minutes (default: {Config.CHECK_INTERVAL_MINUTES})"
    )
    
    parser.add_argument(
        "--test-connections",
        action="store_true",
        help="Test external API connections"
    )
    
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current bot status"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="PiscesER1 Marine Support Bot v1.0.0"
    )
    
    args = parser.parse_args()
    
    # Print banner
    print("="*60)
    print("PISCESER1 MARINE SUPPORT BOT")
    print("Automated Customer Support System")
    print("="*60)
    
    # Handle different modes
    if args.test_connections:
        success = test_connections()
        sys.exit(0 if success else 1)
    
    elif args.status:
        show_status()
        sys.exit(0)
    
    elif args.mode:
        success = run_bot(args.mode, args.interval)
        sys.exit(0 if success else 1)
    
    else:
        # Default to continuous mode
        logger.info("No mode specified, running in continuous mode")
        success = run_bot("continuous", args.interval)
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
