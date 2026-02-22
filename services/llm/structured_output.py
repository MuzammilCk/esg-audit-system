"""
Structured Output Models

Pydantic models for structured LLM responses.
Ensures type-safe parsing of compliance analysis outputs.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class FindingStatus(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REVIEW = "REVIEW"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceOutput(BaseModel):
    """Extracted evidence from document."""
    text_segment: str = Field(..., description="Exact text from document")
    location: str = Field(..., description="Location description (page, section, etc.)")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance to requirement")
    interpretation: str = Field(..., description="How this evidence relates to the requirement")


class FindingOutput(BaseModel):
    """Single compliance finding."""
    regulation_code: str = Field(..., description="E.g., ESRS E1, SEC-GHG")
    regulation_name: str = Field(..., description="Full name of regulation")
    requirement: str = Field(..., description="Specific requirement being checked")
    status: FindingStatus = Field(..., description="Compliance status")
    severity: Severity = Field(..., description="Issue severity if not compliant")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in assessment")
    evidence: List[EvidenceOutput] = Field(default_factory=list, description="Supporting evidence")
    gaps: List[str] = Field(default_factory=list, description="Identified gaps")
    remediation: Optional[str] = Field(None, description="Suggested remediation if applicable")
    cross_references: List[str] = Field(default_factory=list, description="Related regulations")


class ComplianceAnalysisOutput(BaseModel):
    """Complete compliance analysis output."""
    overall_status: FindingStatus = Field(..., description="Overall compliance status")
    compliance_score: float = Field(..., ge=0.0, le=1.0, description="Overall score 0-1")
    findings: List[FindingOutput] = Field(..., description="Individual findings")
    executive_summary: str = Field(..., description="Brief summary for stakeholders")
    key_strengths: List[str] = Field(default_factory=list, description="Areas of strong compliance")
    key_gaps: List[str] = Field(default_factory=list, description="Critical gaps identified")
    recommendations: List[str] = Field(default_factory=list, description="Priority recommendations")
    requires_human_review: bool = Field(..., description="Flag for human review")
    reasoning: str = Field(..., description="Detailed reasoning for the assessment")


class DocumentSummaryOutput(BaseModel):
    """Summary of an ESG document."""
    document_type: str = Field(..., description="Type of ESG document")
    reporting_period: Optional[str] = Field(None, description="Period covered")
    scope: List[str] = Field(default_factory=list, description="Topics covered")
    key_metrics: Dict[str, Any] = Field(default_factory=dict, description="Extracted metrics")
    organizations_mentioned: List[str] = Field(default_factory=list, description="Entities mentioned")
    regulations_addressed: List[str] = Field(default_factory=list, description="Regulations covered")
    confidence: float = Field(..., ge=0.0, le=1.0)


class RiskAssessmentOutput(BaseModel):
    """Risk assessment for a document."""
    overall_risk_level: Severity = Field(..., description="Overall risk level")
    regulatory_risks: List[Dict[str, Any]] = Field(default_factory=list, description="Regulatory risk items")
    reputational_risks: List[Dict[str, Any]] = Field(default_factory=list, description="Reputational risk items")
    financial_risks: List[Dict[str, Any]] = Field(default_factory=list, description="Financial risk items")
    mitigation_suggestions: List[str] = Field(default_factory=list, description="Risk mitigation suggestions")
