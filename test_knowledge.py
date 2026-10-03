#!/usr/bin/env python3
"""Offline checks that PDFs load and the right articles are retrieved."""

import sys
from datetime import datetime

from loguru import logger

from knowledge_base import KnowledgeBase
from models import Ticket, TicketPriority, TicketStatus


CASES = [
    ("VPN will not connect, NetExtender error", ["vpn", "netextender"]),
    ("Need RDP to the main server", ["rdp", "remote", "mstsc"]),
    ("Server got hanged, how to run last known good configuration", ["last known", "server"]),
    ("How do I run the server in safe mode", ["safe mode"]),
    ("Need to upgrade RAM in the server", ["ram"]),
    ("Printer paper jam, not printing", ["printer"]),
    ("How to compress a PDF in Adobe Reader", ["pdf", "compress", "adobe"]),
    ("Cafeteria lunch menu", []),
]


def _print_result(query, hits, chunks):
    print(f"\nQ: {query}")
    print(f"   keywords: {hits or '{}'}")
    if not chunks:
        print("   sources: (none)")
        return
    for chunk in chunks[:3]:
        print(f"   -> {chunk.score:.2f}  {chunk.source}")


def test_retrieval():
    kb = KnowledgeBase()
    pdf_sources = {c.source for c in kb.chunks if c.source.lower().endswith(".pdf")}
    print(f"Chunks: {len(kb.chunks)}")
    print(f"PDF articles indexed: {len(pdf_sources)}")
    if len(pdf_sources) < 20:
        print("FAIL: expected most of the dropped PDFs to be indexed")
        return False

    passed = True
    for query, must_contain in CASES:
        hits = kb.match_keywords(query)
        chunks = kb.search(query)
        _print_result(query, hits, chunks)
        blob = " ".join(c.source.lower() + " " + c.title.lower() for c in chunks)
        if not must_contain:
            if chunks and kb.retrieval_score(chunks) >= 0.65:
                print("   FAIL: unrelated ticket should not look like a strong KB match")
                passed = False
            continue
        if not chunks:
            print("   FAIL: no KB hit")
            passed = False
            continue
        if not any(term in blob for term in must_contain):
            print(f"   FAIL: expected a source related to {must_contain}")
            passed = False
    return passed


def test_ai_reply():
    """Optional live Gemini check — skipped if the API key is missing."""
    from config import Config

    if not Config.GEMINI_API_KEY:
        print("\nSkipping live AI test (no GEMINI_API_KEY)")
        return True

    from ai_processor import AIProcessor

    processor = AIProcessor()
    ticket = Ticket(
        ticket_id="TEST-VPN-1",
        subject="VPN connection failed",
        description="NetExtender will not connect. Please help me reconnect the VPN.",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        customer_name="Test User",
        customer_email="test@example.com",
        department_id="IT",
        created_time=datetime.utcnow(),
        updated_time=datetime.utcnow(),
    )
    response = processor.generate_response(ticket)
    if not response:
        print("FAIL: AI returned no response")
        return False
    print("\nLive AI test")
    print(f"  type: {response.response_type}")
    print(f"  confidence: {response.confidence_score:.2f}")
    print(f"  sources: {response.metadata.get('kb_sources')}")
    print(f"  answer:\n{response.response_text[:500]}")
    sources = " ".join(response.metadata.get("kb_sources") or []).lower()
    if "vpn" not in sources:
        print("FAIL: VPN ticket did not retrieve a VPN article")
        return False
    return True


def main():
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    ok_retrieval = test_retrieval()
    ok_ai = test_ai_reply()
    if ok_retrieval and ok_ai:
        print("\nAll knowledge tests passed.")
        return 0
    print("\nKnowledge tests failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
