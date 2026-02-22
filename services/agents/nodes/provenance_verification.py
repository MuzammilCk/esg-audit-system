"""
Provenance Verification Agent Node

Responsible for:
- C2PA cryptographic signature validation
- Digital provenance verification
- AI-generated content detection
- Trust score calculation
"""

import logging
import base64
from typing import Dict, Any

from services.agents.state import AuditState, ProcessingStatus, ProvenanceResult
from services.verification.c2pa_validator import C2PAValidator
from services.verification.models import ValidationStatus

logger = logging.getLogger(__name__)

_c2pa_validator: C2PAValidator | None = None


def _get_validator() -> C2PAValidator:
    global _c2pa_validator
    if _c2pa_validator is None:
        _c2pa_validator = C2PAValidator()
    return _c2pa_validator


async def provenance_verification_node(state: AuditState) -> Dict[str, Any]:
    """
    Provenance Verification Agent: Validates C2PA digital signatures.
    
    This agent:
    1. Checks for C2PA manifest in document
    2. Validates cryptographic signatures
    3. Detects AI-generated content
    4. Calculates trust score
    5. Routes based on trust level
    """
    logger.info(f"[Provenance Verification Agent] Processing thread: {state.thread_id}")
    
    updates: Dict[str, Any] = {
        "current_node": "provenance_verification",
    }
    
    try:
        state.add_audit_event("provenance_verification", "START", {
            "document_id": str(state.document_metadata.document_id),
        })
        
        raw_content = state.raw_content
        if not raw_content:
            updates["errors"] = [("[provenance_verification] No content to verify")]
            return updates
        
        try:
            raw_bytes = base64.b64decode(raw_content) if isinstance(raw_content, str) else raw_content
        except Exception:
            raw_bytes = raw_content.encode() if isinstance(raw_content, str) else raw_content
        
        validator = _get_validator()
        report = validator.validate_provenance(raw_bytes)
        
        provenance_result = ProvenanceResult(
            status=report.status.value,
            trust_score=report.trust_score,
            is_ai_generated=report.status == ValidationStatus.SYNTHETIC_AI,
            is_signed=report.status == ValidationStatus.VERIFIED,
            issuer=report.issuer,
            software_agent=report.software_agent,
            assertions=report.assertions,
            errors=report.errors,
        )
        
        updates["provenance_result"] = provenance_result
        
        if report.status == ValidationStatus.TAMPERED:
            updates["errors"] = [("[provenance_verification] Document has been tampered")]
            updates["status"] = ProcessingStatus.ERROR
        elif report.status == ValidationStatus.SYNTHETIC_AI:
            updates["warnings"] = [("[provenance_verification] Document appears to be AI-generated")]
        
        state.add_audit_event("provenance_verification", "COMPLETE", {
            "status": report.status.value,
            "trust_score": report.trust_score,
            "is_ai_generated": provenance_result.is_ai_generated,
        })
        
        logger.info(f"[Provenance Verification Agent] Trust score: {report.trust_score}")
        
    except Exception as e:
        logger.exception(f"[Provenance Verification Agent] Error during verification")
        updates["errors"] = [f"[provenance_verification] {str(e)}"]
        provenance_result = ProvenanceResult(
            status="FAILURE",
            trust_score=0.0,
            errors=[str(e)],
        )
        updates["provenance_result"] = provenance_result
    
    return updates
