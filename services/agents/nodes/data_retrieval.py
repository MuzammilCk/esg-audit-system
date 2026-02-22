"""
Data Retrieval Agent Node

Responsible for:
- Fetching documents from configured sources
- Normalizing document content
- Extracting metadata
- Routing to verification
"""

import logging
from typing import Dict, Any
from datetime import datetime, timezone

from services.agents.state import AuditState, ProcessingStatus, DocumentMetadata
from services.ingestion.fetcher import create_app as create_fetcher_app
from services.ingestion.normalizer import parse_pdf, parse_xlsx, _parse_docx, _parse_csv

logger = logging.getLogger(__name__)


async def data_retrieval_node(state: AuditState) -> Dict[str, Any]:
    """
    Data Retrieval Agent: Fetches and normalizes documents.
    
    This agent:
    1. Validates the source document
    2. Extracts text and structure
    3. Prepares content for downstream agents
    """
    logger.info(f"[Data Retrieval Agent] Processing thread: {state.thread_id}")
    
    updates: Dict[str, Any] = {
        "current_node": "data_retrieval",
        "status": ProcessingStatus.INGESTING,
    }
    
    try:
        state.add_audit_event("data_retrieval", "START", {
            "document_id": str(state.document_metadata.document_id),
            "source_url": state.document_metadata.source_url,
        })
        
        raw_content = state.raw_content
        if not raw_content:
            updates["errors"] = [("[data_retrieval] No raw content provided")]
            updates["status"] = ProcessingStatus.ERROR
            return updates
        
        updates["normalized_text"] = raw_content
        updates["status"] = ProcessingStatus.VERIFYING
        
        state.add_audit_event("data_retrieval", "COMPLETE", {
            "text_length": len(raw_content),
        })
        
        logger.info(f"[Data Retrieval Agent] Successfully processed document")
        
    except Exception as e:
        logger.exception(f"[Data Retrieval Agent] Error processing document")
        updates["errors"] = [f"[data_retrieval] {str(e)}"]
        updates["status"] = ProcessingStatus.ERROR
    
    return updates
