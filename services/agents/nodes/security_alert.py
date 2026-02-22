"""
Security Alert Agent Node

Responsible for:
- Handling security-relevant events
- Alerting on tampered documents
- Notifying on AI-generated content
- Logging security incidents
"""

import logging
from typing import Dict, Any
from datetime import datetime, timezone

from services.agents.state import AuditState, ProcessingStatus

logger = logging.getLogger(__name__)


async def security_alert_node(state: AuditState) -> Dict[str, Any]:
    """
    Security Alert Agent: Handles security-relevant events.
    
    This agent:
    1. Analyzes provenance failures
    2. Generates security alerts
    3. Logs incidents for audit
    4. Routes to appropriate handling
    """
    logger.info(f"[Security Alert Agent] Processing thread: {state.thread_id}")
    
    updates: Dict[str, Any] = {
        "current_node": "security_alert",
    }
    
    try:
        provenance = state.provenance_result
        
        alert_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "document_id": str(state.document_metadata.document_id),
            "source_url": state.document_metadata.source_url,
            "trust_score": provenance.trust_score,
            "status": provenance.status,
            "is_ai_generated": provenance.is_ai_generated,
            "is_signed": provenance.is_signed,
        }
        
        if provenance.status == "TAMPERED":
            alert_type = "DOCUMENT_TAMPERED"
            severity = "CRITICAL"
            message = "Document has been tampered with - cryptographic signature invalid"
            
            logger.critical(f"[Security Alert] {alert_type}: {message}")
            
            state.add_audit_event("security_alert", "ALERT", {
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
            })
            
            updates["errors"] = [(f"[security_alert] {message}")]
            updates["status"] = ProcessingStatus.ERROR
            
        elif provenance.is_ai_generated and not provenance.is_signed:
            alert_type = "AI_GENERATED_UNSIGNED"
            severity = "HIGH"
            message = "Document appears to be AI-generated without proper attribution"
            
            logger.warning(f"[Security Alert] {alert_type}: {message}")
            
            state.add_audit_event("security_alert", "WARNING", {
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
            })
            
            updates["warnings"] = [(f"[security_alert] {message}")]
            
        elif provenance.status == "UNSIGNED":
            alert_type = "UNSIGNED_DOCUMENT"
            severity = "MEDIUM"
            message = "Document lacks cryptographic provenance signature"
            
            logger.info(f"[Security Alert] {alert_type}: {message}")
            
            state.add_audit_event("security_alert", "INFO", {
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
            })
            
            updates["warnings"] = [(f"[security_alert] {message}")]
        
        updates["metadata"] = {"security_alert_processed": True}
        
    except Exception as e:
        logger.exception(f"[Security Alert Agent] Error processing security alert")
        updates["errors"] = [f"[security_alert] {str(e)}"]
    
    return updates
