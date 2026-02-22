from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Annotated
from uuid import UUID, uuid4
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from langgraph.graph import add_messages


class AgentDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REVIEW = "REVIEW"
    ESCALATE = "ESCALATE"


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    VERIFYING = "VERIFYING"
    ANALYZING = "ANALYZING"
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    ERROR = "ERROR"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class DocumentMetadata(BaseModel):
    document_id: UUID = Field(default_factory=uuid4)
    source_url: str = ""
    original_filename: str = ""
    mime_type: str = ""
    file_size: int = 0
    upload_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    supplier_id: Optional[str] = None
    region: Optional[str] = None
    reporting_period: Optional[str] = None


class ProvenanceResult(BaseModel):
    status: str = "PENDING"
    trust_score: float = 0.0
    is_ai_generated: bool = False
    is_signed: bool = False
    issuer: Optional[str] = None
    software_agent: Optional[str] = None
    assertions: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class PIIResult(BaseModel):
    masked_text: str = ""
    entities_found: int = 0
    entity_types: List[str] = Field(default_factory=list)
    mapping_key: Optional[str] = None
    success: bool = True


class ComplianceFinding(BaseModel):
    regulation_code: str
    regulation_name: str
    requirement: str
    status: AgentDecision
    evidence: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    remediation: Optional[str] = None
    severity: str = "MEDIUM"


class ComplianceResult(BaseModel):
    overall_decision: AgentDecision = AgentDecision.REVIEW
    findings: List[ComplianceFinding] = Field(default_factory=list)
    compliance_score: float = 0.0
    regulations_checked: List[str] = Field(default_factory=list)
    reasoning: str = ""
    requires_human_review: bool = False


class AuditReport(BaseModel):
    report_id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_status: ProcessingStatus = ProcessingStatus.PENDING
    compliance_decision: AgentDecision = AgentDecision.REVIEW
    compliance_score: float = 0.0
    provenance_trust_score: float = 0.0
    findings_summary: List[Dict[str, Any]] = Field(default_factory=list)
    detailed_findings: List[ComplianceFinding] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(left)
    result.update(right)
    return result


class AuditState(BaseModel):
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    status: ProcessingStatus = ProcessingStatus.PENDING
    
    document_metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    raw_content: str = ""
    normalized_text: str = ""
    
    provenance_result: ProvenanceResult = Field(default_factory=ProvenanceResult)
    pii_result: PIIResult = Field(default_factory=PIIResult)
    compliance_result: ComplianceResult = Field(default_factory=ComplianceResult)
    audit_report: Optional[AuditReport] = None
    
    current_node: str = "START"
    errors: Annotated[List[str], add_messages] = Field(default_factory=list)
    warnings: Annotated[List[str], add_messages] = Field(default_factory=list)
    audit_trail: Annotated[List[Dict[str, Any]], add_messages] = Field(default_factory=list)
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def add_audit_event(self, node: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "action": action,
            "details": details or {},
        }
        self.audit_trail.append(event)
    
    def set_error(self, node: str, error: str) -> None:
        self.errors.append(f"[{node}] {error}")
        self.add_audit_event(node, "ERROR", {"error": error})
    
    class Config:
        arbitrary_types_allowed = True
