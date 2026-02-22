"""
Reporting Agent Node

Responsible for:
- Generating audit reports
- Summarizing findings
- Creating recommendations
- Formatting output for stakeholders
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone

from services.agents.state import (
    AuditState,
    AuditReport,
    ProcessingStatus,
    AgentDecision,
)

logger = logging.getLogger(__name__)


async def reporting_node(state: AuditState) -> Dict[str, Any]:
    """
    Reporting Agent: Generates comprehensive audit reports.
    
    This agent:
    1. Aggregates findings from all previous agents
    2. Creates structured audit report
    3. Generates recommendations
    4. Prepares stakeholder-ready output
    """
    logger.info(f"[Reporting Agent] Processing thread: {state.thread_id}")
    
    updates: Dict[str, Any] = {
        "current_node": "reporting",
    }
    
    try:
        state.add_audit_event("reporting", "START", {
            "document_id": str(state.document_metadata.document_id),
        })
        
        compliance = state.compliance_result
        provenance = state.provenance_result
        pii = state.pii_result
        metadata = state.document_metadata
        
        findings_summary = [
            {
                "regulation": f.regulation_code,
                "status": f.status.value,
                "severity": f.severity,
                "confidence": f.confidence,
            }
            for f in compliance.findings
        ]
        
        recommendations = _generate_recommendations(compliance.findings)
        
        audit_report = AuditReport(
            document_id=metadata.document_id,
            overall_status=state.status,
            compliance_decision=compliance.overall_decision,
            compliance_score=compliance.compliance_score,
            provenance_trust_score=provenance.trust_score,
            findings_summary=findings_summary,
            detailed_findings=compliance.findings,
            recommendations=recommendations,
            audit_trail=list(state.audit_trail),
        )
        
        updates["audit_report"] = audit_report
        
        if compliance.requires_human_review:
            updates["status"] = ProcessingStatus.REQUIRES_REVIEW
        elif compliance.overall_decision == AgentDecision.APPROVE:
            updates["status"] = ProcessingStatus.COMPLIANT
        else:
            updates["status"] = ProcessingStatus.NON_COMPLIANT
        
        state.add_audit_event("reporting", "COMPLETE", {
            "overall_status": updates["status"].value,
            "compliance_score": compliance.compliance_score,
        })
        
        logger.info(
            f"[Reporting Agent] Report generated - Status: {updates['status'].value}"
        )
        
    except Exception as e:
        logger.exception(f"[Reporting Agent] Error generating report")
        updates["errors"] = [f"[reporting] {str(e)}"]
        updates["status"] = ProcessingStatus.ERROR
    
    return updates


def _generate_recommendations(findings: List[Any]) -> List[str]:
    """Generate actionable recommendations based on findings."""
    recommendations = []
    
    for finding in findings:
        if finding.status != AgentDecision.APPROVE:
            if finding.remediation:
                recommendations.append(f"[{finding.regulation_code}] {finding.remediation}")
            elif finding.severity in ("CRITICAL", "HIGH"):
                recommendations.append(
                    f"[{finding.regulation_code}] Address {finding.requirement} - "
                    f"currently {finding.status.value}"
                )
    
    if not recommendations:
        recommendations.append("All compliance requirements met. Continue monitoring.")
    
    return recommendations[:10]
