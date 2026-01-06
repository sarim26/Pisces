import google.generativeai as genai
import time
from datetime import datetime
from typing import Optional, Dict, Any
from loguru import logger
from models import Ticket, TicketResponse
from config import Config
from escalation_notifier import EscalationNotifier

class AIProcessor:
    """AI processor for generating customer support responses"""
    
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        self.max_tokens = Config.GEMINI_MAX_TOKENS
        self.temperature = Config.GEMINI_TEMPERATURE
        
        # Initialize escalation notifier
        self.escalation_notifier = EscalationNotifier()
        
        # Response templates for different scenarios
        self.escalation_keywords = [
            "urgent", "emergency", "broken", "not working", "faulty", "defective",
            "safety", "dangerous", "critical", "immediate", "asap", "help needed"
        ]
        
        self.technical_keywords = [
            "installation", "setup", "configuration", "manual", "specifications",
            "compatibility", "integration", "api", "software", "firmware"
        ]
    
    def _detect_ticket_type(self, ticket: Ticket) -> str:
        """Detect the type of ticket for better response generation"""
        content = f"{ticket.subject} {ticket.description}".lower()
        
        # Check for escalation indicators
        if any(keyword in content for keyword in self.escalation_keywords):
            return "escalation"
        
        # Check for technical support
        if any(keyword in content for keyword in self.technical_keywords):
            return "technical"
        
        # Check priority
        if ticket.priority.value in ["High", "Urgent"]:
            return "high_priority"
        
        return "general"
    
    def _build_prompt(self, ticket: Ticket, ticket_type: str) -> str:
        """Build a context-aware prompt for the AI model"""
        
        # Base template
        base_prompt = Config.RESPONSE_TEMPLATE.format(
            company_name=Config.COMPANY_NAME,
            support_email=Config.SUPPORT_EMAIL,
            ticket_content=f"Subject: {ticket.subject}\nDescription: {ticket.description}"
        )
        
        # Add type-specific instructions
        if ticket_type == "escalation":
            base_prompt += "\n\nIMPORTANT: This appears to be an urgent issue. Provide immediate assistance and offer to escalate to human support if needed."
        
        elif ticket_type == "technical":
            base_prompt += "\n\nThis is a technical support request. Provide detailed, step-by-step guidance and ask for specific technical details if needed."
        
        elif ticket_type == "high_priority":
            base_prompt += "\n\nThis is a high-priority ticket. Provide prompt, thorough assistance and ensure the customer feels their concern is being addressed immediately."
        
        # Add customer context
        base_prompt += f"\n\nCustomer Information:\n- Name: {ticket.customer_name}\n- Email: {ticket.customer_email}\n- Priority: {ticket.priority.value}\n- Tags: {', '.join(ticket.tags) if ticket.tags else 'None'}"
        
        return base_prompt
    
    def _validate_response(self, response_text: str) -> tuple[bool, str]:
        """Validate the generated response for quality and appropriateness"""
        
        # Check for minimum length
        if len(response_text.strip()) < 50:
            return False, "Response too short"
        
        # Check for maximum length
        if len(response_text) > 3000:
            return False, "Response too long"
        
        # Check for inappropriate content
        inappropriate_phrases = [
            "i don't know", "i can't help", "i'm not sure", "i cannot",
            "sorry, i can't", "unfortunately, i can't"
        ]
        
        response_lower = response_text.lower()
        if any(phrase in response_lower for phrase in inappropriate_phrases):
            return False, "Response contains unhelpful phrases"
        
        # Check for professional tone
        if response_text.count("!") > 3:
            return False, "Response contains too many exclamation marks"
        
        return True, "Response validated successfully"
    
    def generate_response(self, ticket: Ticket) -> Optional[TicketResponse]:
        """Generate an AI response for a customer support ticket"""
        
        try:
            start_time = time.time()
            
            # Detect ticket type
            ticket_type = self._detect_ticket_type(ticket)
            logger.info(f"Detected ticket type: {ticket_type} for ticket {ticket.ticket_id}")
            
            # Build prompt
            prompt = self._build_prompt(ticket, ticket_type)
            
            # Generate response using Gemini
            system_prompt = "You are a professional customer support representative for PiscesER1 Marine. Always be helpful, accurate, and professional."
            full_prompt = f"{system_prompt}\n\n{prompt}"
            
            response = self.model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=0.9
                )
            )
            
            response_text = response.text.strip()
            generation_time = time.time() - start_time
            
            # Validate response
            is_valid, validation_message = self._validate_response(response_text)
            
            if not is_valid:
                logger.warning(f"Response validation failed for ticket {ticket.ticket_id}: {validation_message}")
                # Try to generate a fallback response
                return self._generate_fallback_response(ticket)
            
            # Calculate confidence score based on various factors
            confidence_score = self._calculate_confidence_score(
                response_text, ticket_type, generation_time
            )
            
            # Determine response type
            response_type = self._determine_response_type(ticket_type, confidence_score)
            
            # Create response object
            ticket_response = TicketResponse(
                ticket_id=ticket.ticket_id,
                response_text=response_text,
                confidence_score=confidence_score,
                response_type=response_type,
                generated_at=datetime.utcnow(),
                metadata={
                    "ticket_type": ticket_type,
                    "generation_time": generation_time,
                    "model_used": Config.GEMINI_MODEL,  # Store model name string, not object
                    "validation_message": validation_message
                }
            )
            
            logger.info(f"Successfully generated response for ticket {ticket.ticket_id} "
                       f"(confidence: {confidence_score:.2f}, type: {response_type})")
            
            # Send escalation notifications if needed
            if ticket_type == "escalation":
                self._handle_escalation_notification(ticket, ticket_response, response_text)
            
            return ticket_response
            
        except Exception as e:
            logger.error(f"Error generating response for ticket {ticket.ticket_id}: {e}")
            return self._generate_fallback_response(ticket)
    
    def _generate_fallback_response(self, ticket: Ticket) -> TicketResponse:
        """Generate a fallback response when AI generation fails"""
        
        fallback_response = f"""Dear {ticket.customer_name},

Thank you for contacting PiscesER1 Marine support. We have received your inquiry regarding "{ticket.subject}".

Our support team is currently reviewing your request and will provide a detailed response shortly. We understand the importance of your inquiry and appreciate your patience.

If this is an urgent matter, please don't hesitate to contact us directly at {Config.SUPPORT_EMAIL} or call our support line.

Best regards,
{Config.BOT_NAME}
{Config.COMPANY_NAME} Support Team"""

        return TicketResponse(
            ticket_id=ticket.ticket_id,
            response_text=fallback_response,
            confidence_score=0.5,  # Lower confidence for fallback
            response_type="fallback",
            generated_at=datetime.utcnow(),
            metadata={
                "ticket_type": "fallback",
                "generation_time": 0.0,
                "model_used": "fallback",
                "validation_message": "Fallback response generated due to AI error"
            }
        )
    
    def _calculate_confidence_score(self, response_text: str, ticket_type: str, generation_time: float) -> float:
        """Calculate confidence score for the generated response"""
        
        base_score = 0.7
        
        # Adjust based on response length (optimal length gets higher score)
        length_score = min(len(response_text) / 500, 1.0) * 0.2
        
        # Adjust based on generation time (faster is better, but not too fast)
        if 1.0 <= generation_time <= 10.0:
            time_score = 0.1
        else:
            time_score = 0.05
        
        # Adjust based on ticket type
        type_score = 0.1 if ticket_type in ["general", "technical"] else 0.05
        
        # Check for professional indicators
        professional_indicators = [
            "thank you", "appreciate", "understand", "assist", "help",
            "contact", "support", "regards", "best regards"
        ]
        
        response_lower = response_text.lower()
        professional_score = sum(0.02 for indicator in professional_indicators 
                               if indicator in response_lower)
        professional_score = min(professional_score, 0.1)
        
        total_score = base_score + length_score + time_score + type_score + professional_score
        
        return min(total_score, 1.0)
    
    def _determine_response_type(self, ticket_type: str, confidence_score: float) -> str:
        """Determine the type of response based on ticket type and confidence"""
        
        if confidence_score < 0.6:
            return "fallback"
        
        if ticket_type == "escalation":
            return "escalation_offer"
        
        if ticket_type == "technical":
            return "technical_support"
        
        if ticket_type == "high_priority":
            return "high_priority"
        
        return "auto_response"
    
    def _handle_escalation_notification(self, ticket: Ticket, response: TicketResponse, response_text: str):
        """Handle escalation notifications for urgent tickets"""
        try:
            # Determine escalation type based on keywords
            content = f"{ticket.subject} {ticket.description}".lower()
            
            escalation_type = "GENERAL_ESCALATION"
            if any(keyword in content for keyword in ["safety", "dangerous", "emergency", "critical"]):
                escalation_type = "SAFETY_EMERGENCY"
            elif any(keyword in content for keyword in ["urgent", "immediate", "asap"]):
                escalation_type = "URGENT"
            
            # Send notification
            self.escalation_notifier.send_notification(
                ticket=ticket,
                ai_response=response_text,
                escalation_type=escalation_type
            )
            
            logger.info(f"Escalation notification sent for ticket {ticket.ticket_id} (type: {escalation_type})")
            
        except Exception as e:
            logger.error(f"Failed to send escalation notification for ticket {ticket.ticket_id}: {e}")
    
    def test_connection(self) -> bool:
        """Test the connection to Gemini API"""
        try:
            response = self.model.generate_content(
                "Say hello",
                generation_config=genai.types.GenerationConfig(max_output_tokens=10)
            )
            
            # Handle safety filters - check if response has content
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                # Check finish_reason - 2 means SAFETY filter blocked it
                if candidate.finish_reason == 2:
                    logger.warning("Gemini API test was blocked by safety filter, but API connection works")
                    return True  # API works, just content was filtered
                elif candidate.content and candidate.content.parts:
                    logger.info("Gemini API connection test successful")
                    return True
                else:
                    logger.error("Gemini API connection test failed - no content in response")
                    return False
            else:
                logger.error("Gemini API connection test failed - no candidates")
                return False
                
        except Exception as e:
            logger.error(f"Gemini API connection test failed: {e}")
            return False
