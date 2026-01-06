from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

class TicketStatus(str, Enum):
    OPEN = "Open"
    PENDING = "Pending"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
    CANCELLED = "Cancelled"

class TicketPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"
    CRITICAL = "Critical"

@dataclass
class Ticket:
    """ServiceDesk Plus Ticket Model"""
    ticket_id: str
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    customer_name: str
    customer_email: str
    department_id: str
    created_time: datetime
    updated_time: datetime
    assignee_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

@dataclass
class TicketResponse:
    """AI Generated Response Model"""
    ticket_id: str
    response_text: str
    confidence_score: float
    response_type: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ProcessedTicket:
    """Record of processed tickets to prevent duplicates"""
    ticket_id: str
    status: str
    processed_at: datetime = field(default_factory=datetime.utcnow)
    response_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class BotMetrics:
    """Bot performance metrics"""
    total_tickets_processed: int = 0
    successful_responses: int = 0
    failed_responses: int = 0
    average_response_time: float = 0.0
    last_run_time: Optional[datetime] = None
    uptime_hours: float = 0.0
