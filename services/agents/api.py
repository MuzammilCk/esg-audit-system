"""
ESG Audit API Service

FastAPI service that exposes the LangGraph multiagent audit workflow.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.agents import create_audit_graph, AuditGraph, AuditState
from services.agents.state import (
    ProcessingStatus,
    AgentDecision,
    DocumentMetadata,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_audit_graph: AuditGraph | None = None
_pending_audits: Dict[str, AuditState] = {}


def get_audit_graph() -> AuditGraph:
    global _audit_graph
    if _audit_graph is None:
        use_sqlite = os.getenv("USE_SQLITE_CHECKPOINT", "false").lower() == "true"
        checkpoint_path = os.getenv("CHECKPOINT_PATH", "checkpoints.db")
        _audit_graph = create_audit_graph(
            use_sqlite_checkpoint=use_sqlite,
            checkpoint_path=checkpoint_path,
        )
    return _audit_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_audit_graph()
    logger.info("Audit graph initialized")
    yield


app = FastAPI(
    title="ESG Audit Multiagent System",
    version="1.0.0",
    description="Zero-Trust Multiagent ESG Audit and Compliance System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditRequest(BaseModel):
    content: str = Field(..., description="Document content to audit")
    source_url: str = Field(default="", description="Source URL of the document")
    original_filename: str = Field(default="", description="Original filename")
    mime_type: str = Field(default="text/plain", description="MIME type")
    supplier_id: Optional[str] = Field(default=None, description="Supplier identifier")
    region: Optional[str] = Field(default=None, description="Geographic region")
    reporting_period: Optional[str] = Field(default=None, description="Reporting period")


class AuditResponse(BaseModel):
    thread_id: str
    status: ProcessingStatus
    compliance_score: float
    compliance_decision: AgentDecision
    trust_score: float
    findings_count: int
    requires_review: bool
    report_id: Optional[str] = None


class AuditDetailResponse(BaseModel):
    thread_id: str
    status: ProcessingStatus
    document_id: str
    compliance_score: float
    compliance_decision: AgentDecision
    provenance_trust_score: float
    findings_summary: list
    recommendations: list
    requires_review: bool
    audit_trail: list


class ResumeRequest(BaseModel):
    human_decision: str = Field(..., description="APPROVE or REJECT")
    reviewer: str = Field(default="unknown", description="Reviewer identifier")


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok", "service": "audit-agents"}


@app.post("/api/audit", response_model=AuditResponse)
async def submit_audit(request: AuditRequest):
    """
    Submit a document for ESG compliance audit.
    
    The audit workflow:
    1. Data Retrieval Agent - Normalizes document
    2. Provenance Verification Agent - C2PA validation
    3. PII Masking Agent - Privacy protection
    4. Compliance Analysis Agent - CSRD/SEC analysis
    5. Reporting Agent - Generate audit report
    """
    try:
        graph = get_audit_graph()
        
        metadata = DocumentMetadata(
            source_url=request.source_url,
            original_filename=request.original_filename,
            mime_type=request.mime_type,
            supplier_id=request.supplier_id,
            region=request.region,
            reporting_period=request.reporting_period,
        )
        
        final_state = await graph.run_audit(
            raw_content=request.content,
            metadata=metadata,
        )
        
        compliance = final_state.compliance_result
        provenance = final_state.provenance_result
        
        return AuditResponse(
            thread_id=final_state.thread_id,
            status=final_state.status,
            compliance_score=compliance.compliance_score,
            compliance_decision=compliance.overall_decision,
            trust_score=provenance.trust_score,
            findings_count=len(compliance.findings),
            requires_review=compliance.requires_human_review,
            report_id=str(final_state.audit_report.report_id) if final_state.audit_report else None,
        )
        
    except Exception as e:
        logger.exception("Audit failed")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@app.get("/api/audit/{thread_id}", response_model=AuditDetailResponse)
async def get_audit_status(thread_id: str):
    """
    Get the detailed status and results of an audit.
    """
    graph = get_audit_graph()
    state = graph.get_state(thread_id)
    
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "Audit not found"})
    
    report = state.audit_report
    compliance = state.compliance_result
    
    return AuditDetailResponse(
        thread_id=state.thread_id,
        status=state.status,
        document_id=str(state.document_metadata.document_id),
        compliance_score=compliance.compliance_score,
        compliance_decision=compliance.overall_decision,
        provenance_trust_score=state.provenance_result.trust_score,
        findings_summary=report.findings_summary if report else [],
        recommendations=report.recommendations if report else [],
        requires_review=compliance.requires_human_review,
        audit_trail=list(state.audit_trail),
    )


@app.post("/api/audit/{thread_id}/resume", response_model=AuditResponse)
async def resume_audit(thread_id: str, request: ResumeRequest):
    """
    Resume a paused audit with human decision.
    
    Use this when an audit requires human review and
    a decision has been made.
    """
    if request.human_decision not in ("APPROVE", "REJECT"):
        raise HTTPException(
            status_code=400,
            detail={"error": "human_decision must be APPROVE or REJECT"},
        )
    
    graph = get_audit_graph()
    state = graph.get_state(thread_id)
    
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "Audit not found"})
    
    if state.status != ProcessingStatus.REQUIRES_REVIEW:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Audit is in {state.status} status, cannot resume"},
        )
    
    try:
        final_state = await graph.resume_audit(
            thread_id=thread_id,
            human_decision=request.human_decision,
            reviewer=request.reviewer,
        )
        
        compliance = final_state.compliance_result
        provenance = final_state.provenance_result
        
        return AuditResponse(
            thread_id=final_state.thread_id,
            status=final_state.status,
            compliance_score=compliance.compliance_score,
            compliance_decision=compliance.overall_decision,
            trust_score=provenance.trust_score,
            findings_count=len(compliance.findings),
            requires_review=compliance.requires_human_review,
            report_id=str(final_state.audit_report.report_id) if final_state.audit_report else None,
        )
        
    except Exception as e:
        logger.exception("Resume audit failed")
        raise HTTPException(status_code=500, detail={"error": str(e)})


@app.get("/api/audit/{thread_id}/report")
async def get_audit_report(thread_id: str):
    """
    Get the full audit report for a completed audit.
    """
    graph = get_audit_graph()
    state = graph.get_state(thread_id)
    
    if state is None:
        raise HTTPException(status_code=404, detail={"error": "Audit not found"})
    
    if state.audit_report is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "Audit report not yet generated"},
        )
    
    return state.audit_report.model_dump()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8003")))
