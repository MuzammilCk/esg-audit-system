from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ValidationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNSIGNED = "UNSIGNED"
    TAMPERED = "TAMPERED"
    SYNTHETIC_AI = "SYNTHETIC_AI"
    FAILURE = "FAILURE"  # Fallback for processing errors

class ProvenanceReport(BaseModel):
    status: ValidationStatus
    trust_score: float = Field(..., ge=0.0, le=1.0, description="Trust score from 0.0 to 1.0")
    issuer: Optional[str] = Field(None, description="Signer or Issuer of the credential")
    creation_time: Optional[str] = Field(None, description="Timestamp of the signature")
    software_agent: Optional[str] = Field(None, description="Software used to create/edit")
    assertions: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted C2PA assertions")
    ingredients: List[Dict[str, Any]] = Field(default_factory=list, description="Source ingredients")
    errors: List[str] = Field(default_factory=list, description="Validation errors if any")
