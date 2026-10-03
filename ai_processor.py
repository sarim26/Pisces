import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from models import Ticket, TicketResponse
from config import Config
from escalation_notifier import EscalationNotifier
from knowledge_base import KnowledgeBase, KnowledgeChunk


class AIProcessor:
    """Generate support replies from the local knowledge base with a confidence score."""

    def __init__(self):
        import google.generativeai as genai

        genai.configure(api_key=Config.GEMINI_API_KEY)
        self._genai = genai
        self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        self.max_tokens = Config.GEMINI_MAX_TOKENS
        self.temperature = Config.GEMINI_TEMPERATURE
        self.knowledge_base = KnowledgeBase()
        self.escalation_notifier = EscalationNotifier()

    def generate_response(self, ticket: Ticket) -> Optional[TicketResponse]:
        """Match keywords, retrieve KB, answer from files, score confidence, escalate if needed."""
        try:
            start_time = time.time()
            ticket_text = f"{ticket.subject}\n{ticket.description}"
            keyword_hits = self.knowledge_base.match_keywords(ticket_text)
            chunks = self.knowledge_base.search(ticket_text)
            retrieval_score = self.knowledge_base.retrieval_score(chunks)

            logger.info(
                f"Ticket {ticket.ticket_id}: keywords={keyword_hits or '{}'} "
                f"kb_hits={len(chunks)} retrieval={retrieval_score:.2f}"
            )

            parsed, raw_text = self._ask_model(ticket, keyword_hits, chunks)
            generation_time = time.time() - start_time

            model_confidence = float(parsed.get("confidence", 0.0) or 0.0)
            model_confidence = max(0.0, min(model_confidence, 1.0))
            confidence = self._combine_confidence(
                retrieval_score=retrieval_score,
                model_confidence=model_confidence,
                keyword_hits=keyword_hits,
                chunks=chunks,
            )
            uncertainty = round(1.0 - confidence, 4)
            should_escalate = (
                bool(parsed.get("should_escalate"))
                or confidence < Config.CONFIDENCE_THRESHOLD
                or not chunks
            )

            answer = (parsed.get("answer") or "").strip()
            if should_escalate:
                answer = self._human_handoff_message(ticket, keyword_hits, parsed)
                response_type = "human_escalation"
            else:
                response_type = "knowledge_response"

            ticket_response = TicketResponse(
                ticket_id=ticket.ticket_id,
                response_text=answer,
                confidence_score=confidence,
                response_type=response_type,
                generated_at=datetime.utcnow(),
                metadata={
                    "ticket_type": ",".join(keyword_hits.keys()) or "unclassified",
                    "matched_keywords": keyword_hits,
                    "generation_time": generation_time,
                    "model_used": Config.GEMINI_MODEL,
                    "retrieval_score": retrieval_score,
                    "model_confidence": model_confidence,
                    "uncertainty": uncertainty,
                    "confidence_threshold": Config.CONFIDENCE_THRESHOLD,
                    "should_escalate": should_escalate,
                    "uncertainty_reason": parsed.get("uncertainty_reason", ""),
                    "kb_sources": [c.source for c in chunks],
                    "used_sources": parsed.get("used_sources") or [c.source for c in chunks],
                    "web_search": False,
                    "raw_model_excerpt": raw_text[:500],
                },
            )

            logger.info(
                f"Ticket {ticket.ticket_id} confidence={confidence:.2f} "
                f"uncertainty={uncertainty:.2f} escalate={should_escalate} "
                f"type={response_type}"
            )

            if should_escalate:
                self._handle_escalation_notification(ticket, ticket_response, answer)

            return ticket_response

        except Exception as e:
            logger.error(f"Error generating response for ticket {ticket.ticket_id}: {e}")
            return self._generate_fallback_response(ticket)

    def _ask_model(
        self,
        ticket: Ticket,
        keyword_hits: Dict[str, List[str]],
        chunks: List[KnowledgeChunk],
    ) -> Tuple[Dict[str, Any], str]:
        context = self.knowledge_base.format_context(chunks)
        prompt = self._build_prompt(ticket, keyword_hits, context)
        response = self.model.generate_content(
            prompt,
            generation_config=self._genai.types.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=min(self.temperature, 0.4),
            ),
        )
        raw_text = (response.text or "").strip()
        parsed = self._parse_model_json(raw_text)
        return parsed, raw_text

    def _build_prompt(
        self,
        ticket: Ticket,
        keyword_hits: Dict[str, List[str]],
        knowledge_context: str,
    ) -> str:
        keywords_line = (
            json.dumps(keyword_hits) if keyword_hits else "none (no asset keywords matched)"
        )
        kb_block = knowledge_context or "NO MATCHING KNOWLEDGE BASE ARTICLES."
        return f"""You are an IT support assistant for {Config.COMPANY_NAME}.
Servers and assets are in-house. Do not invent cloud/vendor steps that are not in the knowledge base.

PHASE 1 RULES:
- Answer ONLY using the knowledge-base excerpts below.
- Do not use the public internet.
- If the knowledge base does not cover the issue, set should_escalate=true and keep the answer short.
- Hardware/equipment tickets (printers, servers hung, PCs, peripherals) must follow the matching article.

Matched keywords: {keywords_line}

Ticket:
Subject: {ticket.subject}
Description: {ticket.description}
Customer: {ticket.customer_name} <{ticket.customer_email}>
Priority: {ticket.priority.value}

Knowledge base excerpts:
{kb_block}

Return ONLY valid JSON (no markdown fences) with this shape:
{{
  "answer": "customer-facing reply, professional, step-by-step if the KB supports it",
  "confidence": 0.0,
  "uncertainty_reason": "short reason",
  "should_escalate": false,
  "used_sources": ["filename.md"]
}}

confidence is 0.0 to 1.0:
- 0.85-1.0 clear KB match and complete steps
- 0.65-0.84 partial match
- below 0.65 missing info, multiple possible causes, or no KB hit (must escalate)
"""

    def _parse_model_json(self, raw_text: str) -> Dict[str, Any]:
        text = raw_text.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            logger.warning("Model did not return JSON; treating as low-confidence free text")
        return {
            "answer": raw_text,
            "confidence": 0.35,
            "uncertainty_reason": "Model output was not structured JSON",
            "should_escalate": True,
            "used_sources": [],
        }

    def _combine_confidence(
        self,
        retrieval_score: float,
        model_confidence: float,
        keyword_hits: Dict[str, List[str]],
        chunks: List[KnowledgeChunk],
    ) -> float:
        if not chunks:
            return min(model_confidence, 0.25)

        keyword_bonus = 0.1 if keyword_hits else 0.0
        combined = (0.45 * retrieval_score) + (0.45 * model_confidence) + keyword_bonus
        return round(max(0.0, min(combined, 1.0)), 4)

    def _human_handoff_message(
        self,
        ticket: Ticket,
        keyword_hits: Dict[str, List[str]],
        parsed: Dict[str, Any],
    ) -> str:
        topic = ", ".join(keyword_hits.keys()) if keyword_hits else "your request"
        reason = parsed.get("uncertainty_reason") or "the knowledge base does not have a confident match"
        return (
            f"Dear {ticket.customer_name},\n\n"
            f"Thank you for contacting {Config.COMPANY_NAME} support about {topic}.\n\n"
            f"We have logged ticket {ticket.ticket_id} and raised it to a technician "
            f"because {reason}. A team member will follow up shortly.\n\n"
            f"If this is urgent, contact {Config.SUPPORT_EMAIL}.\n\n"
            f"Best regards,\n"
            f"{Config.BOT_NAME}\n"
            f"{Config.COMPANY_NAME} Support Team"
        )

    def _generate_fallback_response(self, ticket: Ticket) -> TicketResponse:
        fallback_response = (
            f"Dear {ticket.customer_name},\n\n"
            f"Thank you for contacting {Config.COMPANY_NAME} support. We received your "
            f"inquiry regarding \"{ticket.subject}\" and have raised it to a technician.\n\n"
            f"If this is urgent, contact {Config.SUPPORT_EMAIL}.\n\n"
            f"Best regards,\n"
            f"{Config.BOT_NAME}\n"
            f"{Config.COMPANY_NAME} Support Team"
        )
        return TicketResponse(
            ticket_id=ticket.ticket_id,
            response_text=fallback_response,
            confidence_score=0.2,
            response_type="human_escalation",
            generated_at=datetime.utcnow(),
            metadata={
                "ticket_type": "fallback",
                "generation_time": 0.0,
                "model_used": "fallback",
                "uncertainty": 0.8,
                "should_escalate": True,
                "validation_message": "Fallback response generated due to AI error",
            },
        )

    def _handle_escalation_notification(
        self,
        ticket: Ticket,
        response: TicketResponse,
        response_text: str,
    ) -> None:
        try:
            content = f"{ticket.subject} {ticket.description}".lower()
            escalation_type = "GENERAL_ESCALATION"
            if any(k in content for k in ("safety", "dangerous", "emergency", "critical")):
                escalation_type = "SAFETY_EMERGENCY"
            elif any(k in content for k in ("urgent", "immediate", "asap", "server", "hung", "hanged")):
                escalation_type = "URGENT"

            self.escalation_notifier.send_notification(
                ticket=ticket,
                ai_response=(
                    f"{response_text}\n\n"
                    f"Confidence: {response.confidence_score:.0%}\n"
                    f"Uncertainty: {response.metadata.get('uncertainty', 0):.0%}\n"
                    f"Keywords: {response.metadata.get('matched_keywords')}\n"
                    f"Reason: {response.metadata.get('uncertainty_reason')}"
                ),
                escalation_type=escalation_type,
            )
            logger.info(
                f"Escalation notification sent for ticket {ticket.ticket_id} "
                f"(type: {escalation_type})"
            )
        except Exception as e:
            logger.error(
                f"Failed to send escalation notification for ticket {ticket.ticket_id}: {e}"
            )

    def test_connection(self) -> bool:
        """Test the connection to Gemini API"""
        try:
            response = self.model.generate_content(
                "Say hello",
                generation_config=self._genai.types.GenerationConfig(max_output_tokens=10),
            )
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.finish_reason == 2:
                    logger.warning(
                        "Gemini API test was blocked by safety filter, but API connection works"
                    )
                    return True
                if candidate.content and candidate.content.parts:
                    logger.info("Gemini API connection test successful")
                    return True
                logger.error("Gemini API connection test failed - no content in response")
                return False
            logger.error("Gemini API connection test failed - no candidates")
            return False
        except Exception as e:
            logger.error(f"Gemini API connection test failed: {e}")
            return False
