#!/usr/bin/env python3
"""
Escalation Notification System for PiscesER1 Marine Support Bot
"""

import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Any
from loguru import logger
from config import Config

class EscalationNotifier:
    """Handles escalation notifications to managers and technicians"""
    
    def __init__(self):
        self.support_email = Config.SUPPORT_EMAIL
        self.technician_email = Config.SDP_TECHNICIAN_EMAIL
        self.sdp_base_url = Config.SDP_BASE_URL
        self.sdp_api_key = Config.SDP_API_KEY
        
        # Escalation contacts (placeholder emails - update with real ones later)
        self.escalation_contacts = {
            "senior_manager": Config.SENIOR_MANAGER,
            "technical_lead": Config.TECHNICAL_LEAD, 
            "emergency_contact": Config.EMERGENCY_CONTACT
        }
        
        # Email configuration
        self.smtp_server = Config.SMTP_SERVER
        self.smtp_port = Config.SMTP_PORT
        self.smtp_username = Config.SMTP_USERNAME
        self.smtp_password = Config.SMTP_PASSWORD
    
    def send_notification(self, ticket, ai_response: str, escalation_type: str = "urgent"):
        """Send escalation notifications to relevant stakeholders"""
        
        logger.info(f"Sending escalation notification for ticket {ticket.ticket_id}")
        
        try:
            # 1. Email notifications
            self._send_email_notifications(ticket, ai_response, escalation_type)
            
            # 2. ServiceDesk Plus escalation (if supported)
            self._escalate_in_servicedesk_plus(ticket, escalation_type)
            
            # 3. Log escalation
            self._log_escalation(ticket, ai_response, escalation_type)
            
            logger.success(f"Escalation notifications sent for ticket {ticket.ticket_id}")
            
        except Exception as e:
            logger.error(f"Failed to send escalation notifications: {e}")
    
    def _send_email_notifications(self, ticket, ai_response: str, escalation_type: str):
        """Send email notifications to escalation contacts"""
        
        # Determine recipients based on escalation type
        if escalation_type == "safety_emergency":
            recipients = [
                self.escalation_contacts["emergency_contact"],
                self.escalation_contacts["senior_manager"],
                self.technician_email
            ]
            subject_prefix = "🚨 SAFETY EMERGENCY ESCALATION"
        elif escalation_type == "urgent":
            recipients = [
                self.escalation_contacts["senior_manager"],
                self.technician_email
            ]
            subject_prefix = "⚡ URGENT ESCALATION"
        else:
            recipients = [self.technician_email]
            subject_prefix = "📋 ESCALATION"
        
        # Create email content
        subject = f"{subject_prefix} - Ticket {ticket.ticket_id}: {ticket.subject}"
        
        email_body = self._create_escalation_email(ticket, ai_response, escalation_type)
        
        # Send emails
        for recipient in recipients:
            self._send_email(recipient, subject, email_body)
    
    def _create_escalation_email(self, ticket, ai_response: str, escalation_type: str) -> str:
        """Create escalation email content"""
        
        return f"""
URGENT ESCALATION - PiscesER1 Marine Support

Ticket Details:
- Ticket ID: {ticket.ticket_id}
- Customer: {ticket.customer_name}
- Email: {ticket.customer_email}
- Priority: {ticket.priority.value}
- Subject: {ticket.subject}
- Escalation Type: {escalation_type.upper()}
- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

Customer Message:
{ticket.description}

AI Response Generated:
{ai_response}

Required Actions:
1. Review the customer's urgent request immediately
2. Contact customer directly if safety is involved
3. Update ticket status in ServiceDesk Plus
4. Provide additional technical support if needed

ServiceDesk Plus Link:
{self.sdp_base_url.replace('/api/v3', '')}/requests/{ticket.ticket_id}

This is an automated escalation notification from the PiscesER1 Marine Support Bot.

Best regards,
PiscesER1 Marine Support Bot
"""
    
    def _send_email(self, recipient: str, subject: str, body: str):
        """Send email notification"""
        
        try:
            # Create message
            msg = MIMEMultipart()
            # Use configured username or support email as From address
            from_addr = self.smtp_username if self.smtp_username else self.support_email
            msg['From'] = from_addr
            msg['To'] = recipient
            msg['Subject'] = subject
            
            # Add body
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email - handle both authenticated and local mail servers
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            
            # Only use TLS and auth if credentials are provided (for cloud/external SMTP)
            if self.smtp_username and self.smtp_password:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
            
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Escalation email sent to {recipient}")
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
    
    def _escalate_in_servicedesk_plus(self, ticket, escalation_type: str):
        """Escalate ticket in ServiceDesk Plus system"""
        
        try:
            # Update ticket priority to highest
            update_data = {
                "input_data": {
                    "request": {
                        "priority": {"name": "Urgent"},
                        "status": {"name": "Escalated"},
                        "subject": f"[ESCALATED] {ticket.subject}"
                    }
                }
            }
            
            # Add escalation note
            escalation_note = f"""
ESCALATION NOTIFICATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Ticket automatically escalated by PiscesER1 Marine Support Bot.
Escalation Type: {escalation_type.upper()}
Customer: {ticket.customer_name}
Reason: Urgent safety/emergency issue detected

AI Response has been generated and posted.
Human intervention required for immediate assistance.

Please contact customer directly if safety is involved.
"""
            
            # Post escalation note
            self._post_escalation_note(ticket.ticket_id, escalation_note)
            
            # Update ticket (if API supports it)
            self._update_ticket_priority(ticket.ticket_id, update_data)
            
            logger.info(f"Ticket {ticket.ticket_id} escalated in ServiceDesk Plus")
            
        except Exception as e:
            logger.error(f"Failed to escalate ticket in ServiceDesk Plus: {e}")
    
    def _post_escalation_note(self, ticket_id: str, note: str):
        """Post escalation note to ServiceDesk Plus"""
        
        try:
            url = f"{self.sdp_base_url}/requests/{ticket_id}/notes"
            
            data = {
                "input_data": {
                    "note": {
                        "content": note,
                        "is_public": True,
                        "mark_first_response": False
                    }
                }
            }
            
            headers = {
                "authtoken": self.sdp_api_key,
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"Escalation note posted to ticket {ticket_id}")
            else:
                logger.warning(f"Failed to post escalation note: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error posting escalation note: {e}")
    
    def _update_ticket_priority(self, ticket_id: str, update_data: Dict[str, Any]):
        """Update ticket priority in ServiceDesk Plus"""
        
        try:
            url = f"{self.sdp_base_url}/requests/{ticket_id}"
            
            headers = {
                "authtoken": self.sdp_api_key,
                "Content-Type": "application/json"
            }
            
            response = requests.put(url, json=update_data, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"Ticket {ticket_id} priority updated to Urgent")
            else:
                logger.warning(f"Failed to update ticket priority: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error updating ticket priority: {e}")
    
    def _log_escalation(self, ticket, ai_response: str, escalation_type: str):
        """Log escalation for tracking and reporting"""
        
        escalation_log = {
            "ticket_id": ticket.ticket_id,
            "customer_name": ticket.customer_name,
            "customer_email": ticket.customer_email,
            "escalation_type": escalation_type,
            "escalated_at": datetime.now().isoformat(),
            "ai_response_length": len(ai_response)
        }
        
        logger.info(f"Escalation logged: {escalation_log}")

# Example usage function
def handle_escalation_example():
    """Example of how to use the escalation notifier"""
    
    # This would be called from the AI processor when escalation is detected
    notifier = EscalationNotifier()
    
    # Example ticket and response (from your demo)
    from models import Ticket, TicketPriority, TicketStatus
    from ai_processor import AIProcessor
    
    # Create example escalation ticket
    ticket = Ticket(
        ticket_id='PIS-2024-001',
        subject='GPS Navigation System Completely Dead - Emergency',
        description='Critical safety issue, 15 miles offshore, weather deteriorating',
        customer_name='Captain James Mitchell',
        customer_email='captain.j.mitchell@atlanticfishing.com',
        status=TicketStatus.OPEN,
        priority=TicketPriority.URGENT,
        department_id='MARINE_SUPPORT',
        created_time=datetime.now(),
        updated_time=datetime.now(),
        tags=['emergency', 'safety', 'gps']
    )
    
    # Generate AI response
    processor = AIProcessor()
    response = processor.generate_response(ticket)
    
    # Notify escalation
    if response and response.response_type == "escalation_offer":
        notifier.send_notification(ticket, response.response_text, "SAFETY_EMERGENCY")

if __name__ == "__main__":
    handle_escalation_example()
