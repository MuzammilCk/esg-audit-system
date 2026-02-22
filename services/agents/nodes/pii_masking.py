"""
PII Masking Agent Node

Responsible for:
- Detecting PII entities in document text
- Algorithmically masking sensitive data
- Storing reversible mappings securely
- Preserving semantic context for LLM reasoning
"""

import logging
import uuid
from typing import Dict, Any

from services.agents.state import AuditState, PIIResult
from services.privacy.presidio_masker import PIIMasker
from services.privacy.redis_manager import RedisManager

logger = logging.getLogger(__name__)

_pii_masker: PIIMasker | None = None


def _get_masker() -> PIIMasker | None:
    global _pii_masker
    if _pii_masker is None:
        import os
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            encryption_key = os.getenv("ENCRYPTION_KEY")
            
            redis_manager = RedisManager(
                host=redis_host,
                port=redis_port,
                encryption_key=encryption_key,
            )
            _pii_masker = PIIMasker(redis_manager)
        except Exception as e:
            logger.warning(f"Could not initialize PII masker: {e}")
            return None
    return _pii_masker


async def pii_masking_node(state: AuditState) -> Dict[str, Any]:
    """
    PII Masking Agent: Detects and masks personally identifiable information.
    
    This agent:
    1. Scans text for PII entities (names, emails, locations, etc.)
    2. Replaces PII with semantic placeholders
    3. Stores encrypted mapping for restoration
    4. Preserves document structure and meaning
    """
    logger.info(f"[PII Masking Agent] Processing thread: {state.thread_id}")
    
    updates: Dict[str, Any] = {
        "current_node": "pii_masking",
    }
    
    try:
        state.add_audit_event("pii_masking", "START", {
            "document_id": str(state.document_metadata.document_id),
        })
        
        text_to_mask = state.normalized_text or state.raw_content
        if not text_to_mask:
            updates["pii_result"] = PIIResult(success=True)
            return updates
        
        masker = _get_masker()
        
        if masker is None:
            logger.warning("[PII Masking Agent] Masker unavailable, passing through")
            updates["pii_result"] = PIIResult(
                masked_text=text_to_mask,
                success=True,
            )
            updates["warnings"] = [("[pii_masking] PII masking service unavailable")]
            return updates
        
        doc_id = str(state.document_metadata.document_id)
        masked_text, success = masker.mask_text(text_to_mask, doc_id)
        
        entity_types = []
        import re
        placeholders = re.findall(r'<(\w+)_(\d+)>', masked_text)
        entity_types = list(set(p[0] for p in placeholders))
        
        pii_result = PIIResult(
            masked_text=masked_text,
            entities_found=len(placeholders),
            entity_types=entity_types,
            mapping_key=f"pii:{doc_id}",
            success=success,
        )
        
        updates["pii_result"] = pii_result
        updates["normalized_text"] = masked_text
        
        state.add_audit_event("pii_masking", "COMPLETE", {
            "entities_found": pii_result.entities_found,
            "entity_types": entity_types,
        })
        
        logger.info(f"[PII Masking Agent] Masked {pii_result.entities_found} entities")
        
    except Exception as e:
        logger.exception(f"[PII Masking Agent] Error during masking")
        updates["errors"] = [f"[pii_masking] {str(e)}"]
        updates["pii_result"] = PIIResult(
            success=False,
        )
    
    return updates
