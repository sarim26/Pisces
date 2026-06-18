import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for PiscesER1 Marine Support Bot"""
    
    # ServiceDesk Plus Configuration
    SDP_DEPLOYMENT = os.getenv("SDP_DEPLOYMENT", "on_premise")
    SDP_BASE_URL = os.getenv("SDP_BASE_URL")
    SDP_API_KEY = os.getenv("SDP_API_KEY")
    SDP_TECHNICIAN_EMAIL = os.getenv("SDP_TECHNICIAN_EMAIL")
    SDP_REQUESTER_DOMAIN = os.getenv("SDP_REQUESTER_DOMAIN")
    SDP_SITE_ID = os.getenv("SDP_SITE_ID")
    SDP_GROUP_ID = os.getenv("SDP_GROUP_ID")
    SDP_TECHNICIAN_ID = os.getenv("SDP_TECHNICIAN_ID")
    
    # OpenAI Configuration (active)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "4096"))
    OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    
    # Application Configuration
    BOT_NAME = "PiscesER1 Marine Support Bot"
    COMPANY_NAME = "PiscesER1 Marine"
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@pisceser1marine.com")
    
    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "pisces_support_bot.log")
    
    # Database Configuration
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///pisces_support_bot.db")
    
    # Scheduling Configuration
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))
    MAX_TICKETS_PER_RUN = int(os.getenv("MAX_TICKETS_PER_RUN", "10"))
    
    # Email Configuration for Escalations
    # For local mail servers, use your internal SMTP server (e.g., mail.yourdomain.local)
    # For cloud email, use smtp.gmail.com or your email provider's SMTP server
    SMTP_SERVER = os.getenv("SMTP_SERVER", "localhost")  # Default to localhost for local setups
    SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))  # Default port 25 for local mail servers
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    
    # Escalation Contacts
    EMERGENCY_CONTACT = os.getenv("EMERGENCY_CONTACT", "emergency.placeholder@pisceser1marine.com")
    SENIOR_MANAGER = os.getenv("SENIOR_MANAGER", "manager.placeholder@pisceser1marine.com")
    TECHNICAL_LEAD = os.getenv("TECHNICAL_LEAD", "tech.lead.placeholder@pisceser1marine.com")
    
    # AI Response Configuration
    RESPONSE_TEMPLATE = """
    You are a professional customer support representative for {company_name}, a leading marine equipment and services company.
    
    Company Information:
    - We specialize in marine safety equipment, navigation systems, and marine consulting services
    - Our customers include commercial fishing vessels, recreational boaters, and marine businesses
    - We pride ourselves on safety, reliability, and exceptional customer service
    
    Guidelines for responses:
    1. Be professional, courteous, and empathetic
    2. Address the customer's specific concern clearly
    3. Provide actionable solutions when possible
    4. If technical support is needed, ask for relevant details (vessel type, equipment model, etc.)
    5. Offer to escalate to human support if the issue is complex
    6. Always maintain a safety-first approach for marine-related issues
    7. Include our contact information: {support_email}
    
    Customer ticket: {ticket_content}
    
    Generate a helpful, professional response:
    """
    
    @classmethod
    def validate_config(cls) -> bool:
        """Validate that all required configuration is present"""
        required_vars = [
            cls.SDP_BASE_URL,
            cls.SDP_API_KEY,
            cls.OPENAI_API_KEY
        ]
        
        missing_vars = [var for var in required_vars if not var]
        
        if missing_vars:
            print(f"Missing required environment variables: {missing_vars}")
            return False
        
        return True
