import requests
import time
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from loguru import logger
from models import Ticket, TicketStatus, TicketPriority
from config import Config

class ServiceDeskPlusClient:
    """ServiceDesk Plus API client for ticket management"""
    
    def _parse_timestamp(self, time_data) -> datetime:
        """Parse timestamp from ServiceDesk Plus API (handles multiple formats)"""
        if isinstance(time_data, dict):
            value = time_data.get("value", time_data.get("display_value", ""))
        else:
            value = time_data
        
        # Handle Unix timestamp in milliseconds (common in SDP API)
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            timestamp_ms = int(value)
            # If timestamp is in milliseconds (13 digits), convert to seconds
            if timestamp_ms > 10000000000:
                timestamp_ms = timestamp_ms / 1000
            return datetime.fromtimestamp(timestamp_ms)
        
        # Handle ISO format strings
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
            
            # Try common date formats
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S"]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        
        # Fallback to current time if parsing fails
        logger.warning(f"Could not parse timestamp: {time_data}, using current time")
        return datetime.utcnow()
    
    def __init__(self):
        self.base_url = Config.SDP_BASE_URL.rstrip('/')
        self.api_key = Config.SDP_API_KEY
        self.technician_email = Config.SDP_TECHNICIAN_EMAIL
        self.site_id = Config.SDP_SITE_ID
        self.group_id = Config.SDP_GROUP_ID
        self.technician_id = Config.SDP_TECHNICIAN_ID

        # Legacy /sdpapi base URL (host:port without the /api/v3 suffix).
        # The v3 REST API has no email-reply operation, so the legacy
        # REPLY_REQUEST operation is used to actually email the requester.
        self.legacy_base_url = self.base_url
        for suffix in ("/api/v3", "/api/v1", "/sdpapi"):
            if self.legacy_base_url.endswith(suffix):
                self.legacy_base_url = self.legacy_base_url[: -len(suffix)]
                break
        self.legacy_base_url = self.legacy_base_url.rstrip("/")

        self.session = requests.Session()
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests

    @staticmethod
    def _extract_requester_email(requester: Optional[Dict[str, Any]],
                                 ticket_data: Optional[Dict[str, Any]] = None) -> str:
        """Extract requester email from SDP ticket/requester payloads.

        The list endpoint often returns requester with only id/name; the email
        may appear under alternate keys or only on the single-ticket GET.
        """
        requester = requester or {}

        for key in ("email_id", "email", "primary_email", "mail"):
            value = requester.get(key)
            if value and str(value).strip():
                return str(value).strip()

        if ticket_data:
            for key in ("requester_email", "txt_email", "email_id"):
                value = ticket_data.get(key)
                if value and str(value).strip():
                    return str(value).strip()

        return ""

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        """Return value when it is a dict; otherwise an empty dict."""
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _nested_field_name(parent: Optional[Dict[str, Any]], key: str,
                           default: str) -> str:
        """Read nested {key: {name: ...}} fields safely when values may be null."""
        nested = ServiceDeskPlusClient._safe_dict(
            ServiceDeskPlusClient._safe_dict(parent).get(key)
        )
        return nested.get("name", default) or default

    def resolve_requester_email(self, ticket_id: str,
                                ticket: Optional[Ticket] = None) -> str:
        """Return requester email, fetching full ticket details if needed."""
        if ticket and ticket.customer_email and ticket.customer_email.strip():
            return ticket.customer_email.strip()

        details = self.get_ticket_details(ticket_id)
        if details and details.customer_email and details.customer_email.strip():
            logger.info(f"Resolved requester email for ticket {ticket_id} via ticket details")
            return details.customer_email.strip()

        legacy_email = self._get_requester_email_legacy(ticket_id)
        if legacy_email:
            logger.info(f"Resolved requester email for ticket {ticket_id} via legacy GET_REQUEST")
            return legacy_email

        return ""

    def _get_requester_email_legacy(self, ticket_id: str) -> str:
        """Fetch requester email via legacy GET_REQUEST when v3 omits it."""
        url = f"{self.legacy_base_url}/sdpapi/request/{ticket_id}"
        form_data = {
            "OPERATION_NAME": "GET_REQUEST",
            "TECHNICIAN_KEY": self.api_key,
        }

        response_body = self._make_legacy_request(url, form_data)
        if not response_body:
            return ""

        email_keys = (
            "requesteremail", "requester_email", "email_id", "emailid",
            "email", "requester mail", "requestermail"
        )

        try:
            root = ET.fromstring(response_body)
            for param in root.iter("parameter"):
                name_el = param.find("name")
                value_el = param.find("value")
                if name_el is None or value_el is None:
                    continue
                name = (name_el.text or "").strip().lower()
                value = (value_el.text or "").strip()
                if value and name in email_keys:
                    return value
                if value and "email" in name and "@" in value:
                    return value
        except ET.ParseError:
            pass

        match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", response_body)
        return match.group(0) if match else ""
        
    def _rate_limit(self):
        """Implement rate limiting to avoid API throttling"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make authenticated API request with rate limiting"""
        try:
            self._rate_limit()
            
            url = f"{self.base_url}/{endpoint}"
            headers = {
                "authtoken": self.api_key,
                "Content-Type": "application/json"
            }
            
            # Add optional headers
            if self.technician_email:
                headers["technician_email"] = self.technician_email
            
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                timeout=30,  # 30 second timeout
                **kwargs
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceDesk Plus API request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in ServiceDesk Plus API request: {e}")
            return None

    @staticmethod
    def _build_legacy_input_xml(fields: Dict[str, str]) -> str:
        """Build the legacy /sdpapi INPUT_DATA XML payload.

        Produces:
            <Operation><Details>
                <parameter><name>key</name><value>val</value></parameter>
                ...
            </Details></Operation>
        ElementTree handles XML-escaping of values automatically.
        """
        operation = ET.Element("Operation")
        details = ET.SubElement(operation, "Details")
        for key, value in fields.items():
            parameter = ET.SubElement(details, "parameter")
            ET.SubElement(parameter, "name").text = key
            ET.SubElement(parameter, "value").text = value if value is not None else ""
        return ET.tostring(operation, encoding="unicode")

    def _make_legacy_request(self, url: str, data: Dict[str, Any]) -> Optional[str]:
        """Make a request to the legacy /sdpapi endpoint (form-encoded).

        Returns the raw response body text on success, or None on failure.
        Authentication is handled via the TECHNICIAN_KEY form field, so no
        authtoken header is sent here.
        """
        try:
            self._rate_limit()

            response = self.session.post(url, data=data, timeout=30)
            response.raise_for_status()
            return response.text

        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceDesk Plus legacy API request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in ServiceDesk Plus legacy API request: {e}")
            return None

    def get_tickets(self, status: str = "Open", limit: int = 50) -> List[Ticket]:
        """Fetch tickets from ServiceDesk Plus"""
        try:
            endpoint = "requests"
            # Remove search_fields - this API version doesn't support it
            params = {
                "input_data": f'{{"list_info": {{"start_index": 1, "row_count": {limit}, "sort_fields": [{{"field": "created_time", "order": "desc"}}]}}}}'
            }
            
            response_data = self._make_request("GET", endpoint, params=params)
            
            if not response_data or "requests" not in response_data:
                logger.warning("No ticket data received from ServiceDesk Plus API")
                return []
            
            tickets = []
            for ticket_data in response_data["requests"]:
                try:
                    # Extract requester information
                    requester = self._safe_dict(ticket_data.get("requester"))
                    customer_name = requester.get("name", "Unknown")
                    customer_email = self._extract_requester_email(requester, ticket_data)
                    
                    # Parse timestamps (handles multiple formats from SDP API)
                    created_time = self._parse_timestamp(ticket_data.get("created_time", {}))
                    updated_time = self._parse_timestamp(ticket_data.get("modified_time", {}))
                    
                    # Map SDP status to our enum (handle None values)
                    status_obj = ticket_data.get("status")
                    sdp_status = status_obj.get("name", "Open") if status_obj else "Open"
                    mapped_status = self._map_status(sdp_status)
                    
                    # Map SDP priority to our enum (handle None values)
                    priority_obj = ticket_data.get("priority")
                    sdp_priority = priority_obj.get("name", "Medium") if priority_obj else "Medium"
                    mapped_priority = self._map_priority(sdp_priority)
                    
                    # Extract optional nested fields safely
                    site_obj = ticket_data.get("site")
                    department_id = str(site_obj.get("id", "")) if site_obj else ""
                    
                    technician_obj = ticket_data.get("technician")
                    assignee_id = str(technician_obj.get("id", "")) if technician_obj else None
                    
                    category_obj = ticket_data.get("category")
                    tags = category_obj.get("name", "").split(",") if category_obj and category_obj.get("name") else []
                    
                    ticket = Ticket(
                        ticket_id=str(ticket_data["id"]),
                        subject=ticket_data.get("subject", "No Subject"),
                        description=ticket_data.get("description", ""),
                        status=mapped_status,
                        priority=mapped_priority,
                        customer_name=customer_name,
                        customer_email=customer_email,
                        department_id=department_id,
                        created_time=created_time,
                        updated_time=updated_time,
                        assignee_id=assignee_id,
                        tags=tags
                    )
                    tickets.append(ticket)
                    
                except Exception as e:
                    logger.error(f"Error parsing ticket {ticket_data.get('id', 'unknown')}: {e}")
                    continue
            
            # Filter by status after fetching (since search_fields doesn't work)
            if status:
                # Map status to what ServiceDesk Plus uses
                status_filter_map = {
                    "Open": ["Open", "Assigned", "In Progress"],
                    "Pending": ["Pending"],
                    "Resolved": ["Resolved"],
                    "Closed": ["Closed"],
                    "Cancelled": ["Cancelled"]
                }
                valid_statuses = status_filter_map.get(status, [status])
                tickets = [t for t in tickets if t.status.value in valid_statuses]
            
            logger.info(f"Successfully fetched {len(tickets)} tickets from ServiceDesk Plus (filtered by status: {status})")
            return tickets
            
        except Exception as e:
            logger.error(f"Error fetching tickets from ServiceDesk Plus: {e}")
            return []
    
    def _map_status(self, sdp_status: str) -> TicketStatus:
        """Map ServiceDesk Plus status to our TicketStatus enum"""
        status_mapping = {
            "Open": TicketStatus.OPEN,
            "Assigned": TicketStatus.OPEN,
            "In Progress": TicketStatus.OPEN,
            "Pending": TicketStatus.PENDING,
            "Resolved": TicketStatus.RESOLVED,
            "Closed": TicketStatus.CLOSED,
            "Cancelled": TicketStatus.CANCELLED
        }
        return status_mapping.get(sdp_status, TicketStatus.OPEN)
    
    def _map_priority(self, sdp_priority: str) -> TicketPriority:
        """Map ServiceDesk Plus priority to our TicketPriority enum"""
        priority_mapping = {
            "Critical": TicketPriority.CRITICAL,
            "High": TicketPriority.HIGH,
            "Medium": TicketPriority.MEDIUM,
            "Low": TicketPriority.LOW
        }
        return priority_mapping.get(sdp_priority, TicketPriority.MEDIUM)
    
    def post_ticket_response(self, ticket_id: str, response_text: str, is_public: bool = True) -> bool:
        """Post a response/note to a ticket (internal note only, not sent to customer)"""
        try:
            endpoint = f"requests/{ticket_id}/notes"
            
            # ServiceDesk Plus API requires input_data wrapper
            note_data = {
                "note": {
                    "description": response_text,
                    "show_to_requester": is_public,
                    "notify_technician": False,
                    "add_to_linked_requests": False
                }
            }
            
            # Use input_data as form parameter (SDP API requirement)
            params = {"input_data": json.dumps(note_data)}
            response_data = self._make_request("POST", endpoint, params=params)
            
            if response_data:
                logger.info(f"Successfully posted note to ServiceDesk Plus ticket {ticket_id}")
                return True
            else:
                logger.error(f"Failed to post note to ServiceDesk Plus ticket {ticket_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error posting note to ServiceDesk Plus ticket {ticket_id}: {e}")
            return False
    
    def add_resolution(self, ticket_id: str, response_text: str) -> bool:
        """Add the response text to the request's Resolution tab.

        This stores the content on the ticket but does NOT, by itself,
        reliably email the requester. Use send_reply_to_customer() to email.
        """
        try:
            endpoint = f"requests/{ticket_id}/resolutions"

            resolution_data = {
                "resolution": {
                    "content": response_text
                }
            }

            # Use input_data as form parameter (SDP API requirement)
            params = {"input_data": json.dumps(resolution_data)}
            response_data = self._make_request("POST", endpoint, params=params)

            if response_data:
                logger.info(f"Successfully added resolution to ticket {ticket_id}")
                return True
            else:
                logger.error(f"Failed to add resolution for ticket {ticket_id}")
                return False

        except Exception as e:
            logger.error(f"Error adding resolution for ticket {ticket_id}: {e}")
            return False

    def send_reply_to_customer(self, ticket_id: str, response_text: str,
                               to_email: Optional[str] = None,
                               subject: Optional[str] = None) -> bool:
        """Send an email reply to the requester (the "Reply" action).

        Mirrors clicking Reply in the request's conversation/description tab,
        which delivers an email to the requester. The v3 REST API does not
        expose an email-reply operation, so the legacy REPLY_REQUEST operation
        on the /sdpapi endpoint is used.
        """
        try:
            if not to_email:
                logger.warning(
                    f"No requester email available for ticket {ticket_id}; "
                    f"cannot send email reply"
                )
                return False

            url = f"{self.legacy_base_url}/sdpapi/request/{ticket_id}"

            # The legacy /sdpapi REPLY_REQUEST operation expects INPUT_DATA as
            # XML (<Operation><Details><parameter>...). JSON or extra params
            # (e.g. format=json) trigger SDP's request-validation/security
            # filter and get rejected with an HTML error page.
            input_xml = self._build_legacy_input_xml({
                "to": to_email,
                "subject": subject or f"Re: Request {ticket_id}",
                "description": response_text
            })

            form_data = {
                "OPERATION_NAME": "REPLY_REQUEST",
                "TECHNICIAN_KEY": self.api_key,
                "INPUT_DATA": input_xml
            }

            response_body = self._make_legacy_request(url, form_data)

            if response_body is None:
                logger.error(f"Failed to send email reply for ticket {ticket_id}")
                return False

            # The REPLY_REQUEST operation reports a status in its body
            # (JSON or XML). Treat an explicit success marker as success and
            # an explicit failure marker as failure; log the body either way.
            body_lower = response_body.lower()
            if "failed" in body_lower or "failure" in body_lower:
                logger.error(
                    f"Reply operation reported failure for ticket {ticket_id}: "
                    f"{response_body}"
                )
                return False

            if "success" in body_lower:
                logger.info(
                    f"Successfully sent email reply to customer for ticket {ticket_id}"
                )
                return True

            # No explicit marker: log the body so the outcome can be verified.
            logger.warning(
                f"Reply operation returned an unrecognized response for "
                f"ticket {ticket_id}: {response_body}"
            )
            return False

        except Exception as e:
            logger.error(f"Error sending email reply for ticket {ticket_id}: {e}")
            return False
    
    def update_ticket_status(self, ticket_id: str, status: str) -> bool:
        """Update ticket status"""
        try:
            endpoint = f"requests/{ticket_id}"
            
            # Map our status to SDP status
            sdp_status = self._map_status_to_sdp(status)
            
            request_data = {
                "request": {
                    "status": {
                        "name": sdp_status
                    }
                }
            }
            
            # Use input_data as form parameter (SDP API requirement)
            params = {"input_data": json.dumps(request_data)}
            response_data = self._make_request("PUT", endpoint, params=params)
            
            if response_data:
                logger.info(f"Successfully updated ServiceDesk Plus ticket {ticket_id} status to {sdp_status}")
                return True
            else:
                logger.error(f"Failed to update ServiceDesk Plus ticket {ticket_id} status")
                return False
                
        except Exception as e:
            logger.error(f"Error updating ServiceDesk Plus ticket {ticket_id} status: {e}")
            return False
    
    def _map_status_to_sdp(self, status: str) -> str:
        """Map our status to ServiceDesk Plus status"""
        status_mapping = {
            "Open": "Open",
            "Pending": "Pending",
            "Resolved": "Resolved",
            "Closed": "Closed",
            "Cancelled": "Cancelled"
        }
        return status_mapping.get(status, "Open")
    
    def get_ticket_details(self, ticket_id: str) -> Optional[Ticket]:
        """Get detailed information about a specific ticket"""
        try:
            endpoint = f"requests/{ticket_id}"
            
            response_data = self._make_request("GET", endpoint)
            
            if not response_data:
                return None

            ticket_data = self._safe_dict(response_data.get("request"))
            if not ticket_data:
                logger.warning(f"No request payload in ticket details for {ticket_id}")
                return None

            # Extract requester information
            requester = self._safe_dict(ticket_data.get("requester"))
            customer_name = requester.get("name", "Unknown")
            customer_email = self._extract_requester_email(requester, ticket_data)

            # Parse timestamps (handles multiple formats from SDP API)
            created_time = self._parse_timestamp(ticket_data.get("created_time", {}))
            updated_time = self._parse_timestamp(ticket_data.get("modified_time", {}))

            # Map status and priority (SDP may return null nested objects)
            sdp_status = self._nested_field_name(ticket_data, "status", "Open")
            mapped_status = self._map_status(sdp_status)

            sdp_priority = self._nested_field_name(ticket_data, "priority", "Medium")
            mapped_priority = self._map_priority(sdp_priority)

            site = self._safe_dict(ticket_data.get("site"))
            technician = self._safe_dict(ticket_data.get("technician"))
            category = self._safe_dict(ticket_data.get("category"))

            ticket = Ticket(
                ticket_id=str(ticket_data["id"]),
                subject=ticket_data.get("subject", "No Subject"),
                description=ticket_data.get("description", ""),
                status=mapped_status,
                priority=mapped_priority,
                customer_name=customer_name,
                customer_email=customer_email,
                department_id=str(site.get("id", "")),
                created_time=created_time,
                updated_time=updated_time,
                assignee_id=str(technician.get("id", "")) if technician.get("id") else None,
                tags=category.get("name", "").split(",") if category.get("name") else []
            )
            
            return ticket
            
        except Exception as e:
            logger.error(f"Error fetching ServiceDesk Plus ticket details for {ticket_id}: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test the connection to ServiceDesk Plus API"""
        try:
            # Try to fetch a single ticket to test the connection
            tickets = self.get_tickets(limit=1)
            if tickets is not None:
                logger.info("ServiceDesk Plus API connection test successful")
                return True
            else:
                logger.error("ServiceDesk Plus API connection test failed")
                return False
        except Exception as e:
            logger.error(f"ServiceDesk Plus API connection test failed: {e}")
            return False
