"""
Compliance Analysis Agent Node

Responsible for:
- ESG regulatory compliance checking
- CSRD/SEC framework analysis
- RAG-enhanced evidence retrieval
- Evidence extraction and validation
- Compliance score calculation
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone

from services.agents.state import (
    AuditState,
    ProcessingStatus,
    ComplianceResult,
    ComplianceFinding,
    AgentDecision,
)
from services.agents.tools.compliance_checker import ComplianceChecker

logger = logging.getLogger(__name__)

_compliance_checker: ComplianceChecker | None = None
_rag_retriever = None


def _get_checker() -> ComplianceChecker:
    global _compliance_checker
    if _compliance_checker is None:
        _compliance_checker = ComplianceChecker()
    return _compliance_checker


def _get_rag_retriever():
    global _rag_retriever
    if _rag_retriever is None:
        try:
            from services.vectorstore import get_rag_retriever
            _rag_retriever = get_rag_retriever()
        except Exception as e:
            logger.warning(f"RAG retriever not available: {e}")
    return _rag_retriever


async def compliance_analysis_node(state: AuditState) -> Dict[str, Any]:
    """
    Compliance Analysis Agent: Performs ESG regulatory compliance analysis.
    
    This agent:
    1. Extracts relevant ESG metrics from document
    2. Cross-references against CSRD/SEC regulations
    3. Retrieves relevant context from vector store (RAG)
    4. Identifies compliance gaps and violations
    5. Generates findings with evidence and remediation
    6. Calculates overall compliance score
    """
    logger.info(f"[Compliance Analysis Agent] Processing thread: {state.thread_id}")
    
    updates: Dict[str, Any] = {
        "current_node": "compliance_analysis",
        "status": ProcessingStatus.ANALYZING,
    }
    
    try:
        state.add_audit_event("compliance_analysis", "START", {
            "document_id": str(state.document_metadata.document_id),
        })
        
        text_to_analyze = state.normalized_text
        if not text_to_analyze:
            updates["errors"] = [("[compliance_analysis] No text to analyze")]
            updates["compliance_result"] = ComplianceResult(
                overall_decision=AgentDecision.REVIEW,
                reasoning="No content available for analysis",
            )
            return updates
        
        checker = _get_checker()
        
        metadata = state.document_metadata.model_dump()
        metadata["provenance_trust_score"] = state.provenance_result.trust_score
        metadata["is_ai_generated"] = state.provenance_result.is_ai_generated
        
        rag_context = await _retrieve_rag_context(state, text_to_analyze, metadata)
        
        if rag_context:
            text_to_analyze = _enhance_text_with_rag(text_to_analyze, rag_context)
            metadata["rag_enhanced"] = True
        
        findings = await checker.analyze_compliance(
            text=text_to_analyze,
            metadata=metadata,
        )
        
        if rag_context:
            findings = _enrich_findings_with_rag(findings, rag_context)
        
        compliant_count = sum(1 for f in findings if f.status == AgentDecision.APPROVE)
        total_findings = len(findings)
        
        compliance_score = compliant_count / total_findings if total_findings > 0 else 0.0
        
        if compliance_score >= 0.8:
            overall_decision = AgentDecision.APPROVE
            status = ProcessingStatus.COMPLIANT
        elif compliance_score >= 0.5:
            overall_decision = AgentDecision.REVIEW
            status = ProcessingStatus.REQUIRES_REVIEW
        else:
            overall_decision = AgentDecision.REJECT
            status = ProcessingStatus.NON_COMPLIANT
        
        requires_review = any(
            f.status == AgentDecision.REVIEW or f.severity == "HIGH"
            for f in findings
        )
        
        reasoning = _generate_reasoning(findings, compliance_score)
        
        compliance_result = ComplianceResult(
            overall_decision=overall_decision,
            findings=findings,
            compliance_score=compliance_score,
            regulations_checked=checker.get_regulations_checked(),
            reasoning=reasoning,
            requires_human_review=requires_review,
        )
        
        updates["compliance_result"] = compliance_result
        updates["status"] = status
        
        state.add_audit_event("compliance_analysis", "COMPLETE", {
            "compliance_score": compliance_score,
            "overall_decision": overall_decision.value,
            "findings_count": len(findings),
        })
        
        logger.info(
            f"[Compliance Analysis Agent] Score: {compliance_score:.2f}, "
            f"Decision: {overall_decision.value}"
        )
        
    except Exception as e:
        logger.exception(f"[Compliance Analysis Agent] Error during analysis")
        updates["errors"] = [f"[compliance_analysis] {str(e)}"]
        updates["status"] = ProcessingStatus.ERROR
        updates["compliance_result"] = ComplianceResult(
            overall_decision=AgentDecision.REVIEW,
            reasoning=f"Analysis failed: {str(e)}",
            requires_human_review=True,
        )
    
    return updates


def _generate_reasoning(findings: List[ComplianceFinding], score: float) -> str:
    """Generate a human-readable reasoning summary."""
    if not findings:
        return "No compliance findings generated."
    
    critical = [f for f in findings if f.severity == "CRITICAL"]
    high = [f for f in findings if f.severity == "HIGH"]
    
    parts = [f"Overall compliance score: {score:.1%}"]
    
    if critical:
        parts.append(f"Found {len(critical)} critical issue(s) requiring immediate attention.")
    if high:
        parts.append(f"Found {len(high)} high-severity issue(s).")
    
    compliant = [f for f in findings if f.status == AgentDecision.APPROVE]
    if compliant:
        parts.append(f"{len(compliant)} requirement(s) met with sufficient evidence.")
    
    return " ".join(parts)


async def _retrieve_rag_context(
    state: AuditState,
    text: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any] | None:
    """
    Retrieve relevant context from the vector store using RAG.
    """
    retriever = _get_rag_retriever()
    if retriever is None:
        return None
    
    try:
        filters = {}
        if metadata.get("supplier_id"):
            filters["supplier_id"] = metadata["supplier_id"]
        if metadata.get("region"):
            filters["region"] = metadata["region"]
        
        context = await retriever.retrieve(
            query=text[:500],
            limit=5,
            filters=filters if filters else None,
            method="hybrid",
        )
        
        return {
            "documents": context.documents,
            "total_score": context.total_score,
        }
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        return None


def _enhance_text_with_rag(text: str, rag_context: Dict[str, Any]) -> str:
    """
    Enhance the analysis text with retrieved RAG context.
    """
    if not rag_context.get("documents"):
        return text
    
    context_parts = []
    for doc in rag_context["documents"][:3]:
        content = doc.get("content", "")
        if content:
            context_parts.append(f"[Historical Context]: {content[:500]}")
    
    if context_parts:
        enhanced = "\n\n".join(context_parts) + "\n\n[Current Document]:\n" + text
        return enhanced
    
    return text


def _enrich_findings_with_rag(
    findings: List[ComplianceFinding],
    rag_context: Dict[str, Any],
) -> List[ComplianceFinding]:
    """
    Enrich compliance findings with RAG-retrieved evidence.
    """
    if not rag_context.get("documents"):
        return findings
    
    for finding in findings:
        relevant_docs = [
            doc for doc in rag_context["documents"]
            if finding.regulation_code in doc.get("content", "")
            or finding.regulation_code in str(doc.get("metadata", {}).get("regulation_codes", []))
        ]
        
        if relevant_docs:
            additional_evidence = f" (Cross-referenced with {len(relevant_docs)} historical documents)"
            finding.evidence += additional_evidence
    
    return findings
