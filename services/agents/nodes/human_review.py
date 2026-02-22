"""
Human Review Agent Node

Responsible for:
- Escalating ambiguous cases
- Collecting human decisions
- Managing review queue
- Enabling human-in-the-loop workflows
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from services.agents.state import AuditState, ProcessingStatus, AgentDecision

logger = logging.getLogger(__name__)


async def human_review_node(state: AuditState) -> Dict[str, Any]:
    """
    Human Review Agent: Handles cases requiring human judgment.
    
    This agent:
    1. Pauses workflow for human review
    2. Provides context for reviewers
    3. Accepts human decisions
    4. Routes based on human input
    """
    logger.info(f"[Human Review Agent] Processing thread: {state.thread_id}")
    
    updates: Dict[str, Any] = {
        "current_node": "human_review",
    }
    
    try:
        compliance = state.compliance_result
        provenance = state.provenance_result
        
        review_context = {
            "document_id": str(state.document_metadata.document_id),
            "compliance_score": compliance.compliance_score,
            "compliance_decision": compliance.overall_decision.value,
            "provenance_trust_score": provenance.trust_score,
            "is_ai_generated": provenance.is_ai_generated,
            "critical_findings": [
                {
                    "regulation": f.regulation_code,
                    "severity": f.severity,
                    "issue": f.requirement,
                }
                for f in compliance.findings
                if f.severity in ("CRITICAL", "HIGH") and f.status != AgentDecision.APPROVE
            ],
            "reasoning": compliance.reasoning,
        }
        
        human_decision = state.metadata.get("human_decision")
        
        if human_decision:
            logger.info(f"[Human Review Agent] Received human decision: {human_decision}")
            
            state.add_audit_event("human_review", "DECISION_RECEIVED", {
                "decision": human_decision,
                "reviewer": state.metadata.get("reviewer", "unknown"),
            })
            
            if human_decision == "APPROVE":
                updates["status"] = ProcessingStatus.COMPLIANT
                updates["metadata"] = {"human_review_completed": True, "human_decision": "APPROVE"}
            elif human_decision == "REJECT":
                updates["status"] = ProcessingStatus.NON_COMPLIANT
                updates["metadata"] = {"human_review_completed": True, "human_decision": "REJECT"}
            else:
                updates["status"] = ProcessingStatus.REQUIRES_REVIEW
                updates["metadata"] = {"human_review_completed": False}
        else:
            logger.info("[Human Review Agent] Queuing for human review")
            
            state.add_audit_event("human_review", "QUEUED", review_context)
            
            updates["status"] = ProcessingStatus.REQUIRES_REVIEW
            updates["metadata"] = {
                "requires_human_review": True,
                "review_context": review_context,
            }
        
    except Exception as e:
        logger.exception(f"[Human Review Agent] Error in human review")
        updates["errors"] = [f"[human_review] {str(e)}"]
        updates["status"] = ProcessingStatus.ERROR
    
    return updates
