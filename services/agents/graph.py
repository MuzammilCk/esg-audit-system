"""
LangGraph Multiagent Audit Workflow

This module defines the DAG-based multiagent orchestration for ESG audit processing.
Uses LangGraph for deterministic state machine execution with checkpointing.
"""

import logging
from typing import Literal, TypedDict, Annotated, Sequence
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages

from services.agents.state import (
    AuditState,
    ProcessingStatus,
    AgentDecision,
    ProvenanceResult,
    PIIResult,
    ComplianceResult,
    DocumentMetadata,
)
from services.agents.nodes import (
    data_retrieval_node,
    provenance_verification_node,
    pii_masking_node,
    compliance_analysis_node,
    reporting_node,
    security_alert_node,
    human_review_node,
)

logger = logging.getLogger(__name__)


def _provenance_router(state: AuditState) -> Literal["security_alert", "pii_masking", "human_review"]:
    """
    Routes based on provenance verification result.
    
    - TAMPERED -> security_alert (critical failure)
    - SYNTHETIC_AI with low trust -> security_alert
    - UNSIGNED -> pii_masking (warning, continue)
    - VERIFIED -> pii_masking (normal flow)
    """
    provenance = state.provenance_result
    
    if provenance.status == "TAMPERED":
        logger.warning(f"[Router] Routing to security_alert - document tampered")
        return "security_alert"
    
    if provenance.status == "FAILURE" and provenance.trust_score < 0.3:
        logger.warning(f"[Router] Routing to security_alert - verification failure")
        return "security_alert"
    
    return "pii_masking"


def _security_router(state: AuditState) -> Literal["end", "pii_masking", "human_review"]:
    """
    Routes after security alert handling.
    
    - CRITICAL errors -> end
    - Warnings -> continue to pii_masking
    """
    has_critical_error = any(
        "TAMPERED" in err or "CRITICAL" in err 
        for err in state.errors
    )
    
    if has_critical_error:
        logger.warning(f"[Router] Critical security issue - terminating workflow")
        return "end"
    
    return "pii_masking"


def _compliance_router(state: AuditState) -> Literal["reporting", "human_review"]:
    """
    Routes based on compliance analysis result.
    
    - APPROVE with high confidence -> reporting
    - REVIEW or low confidence -> human_review
    - REJECT -> reporting (generate report with findings)
    """
    compliance = state.compliance_result
    
    if compliance.requires_human_review:
        logger.info(f"[Router] Routing to human_review - requires review")
        return "human_review"
    
    if compliance.overall_decision == AgentDecision.REVIEW:
        logger.info(f"[Router] Routing to human_review - review decision")
        return "human_review"
    
    return "reporting"


def _human_review_router(state: AuditState) -> Literal["reporting", "end"]:
    """
    Routes based on human review decision.
    
    - APPROVE -> reporting
    - REJECT -> reporting (generate rejection report)
    - No decision yet -> end (pause for human input)
    """
    human_decision = state.metadata.get("human_decision")
    
    if human_decision:
        return "reporting"
    
    return "end"


class AuditGraph:
    """
    LangGraph-based multiagent audit workflow orchestrator.
    
    Implements a DAG-based state machine with:
    - Conditional routing based on agent outputs
    - Checkpointing for persistence and recovery
    - Human-in-the-loop support
    """
    
    def __init__(self, use_sqlite_checkpoint: bool = False, checkpoint_path: str = "checkpoints.db"):
        self.use_sqlite_checkpoint = use_sqlite_checkpoint
        self.checkpoint_path = checkpoint_path
        self._checkpointer = None
        self.graph = self._build_graph()
    
    def _get_checkpointer(self):
        if self._checkpointer is None:
            if self.use_sqlite_checkpoint:
                import sqlite3
                conn = sqlite3.connect(self.checkpoint_path)
                self._checkpointer = SqliteSaver(conn)
            else:
                self._checkpointer = MemorySaver()
        return self._checkpointer
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph DAG for the audit workflow."""
        
        builder = StateGraph(AuditState)
        
        builder.add_node("data_retrieval", data_retrieval_node)
        builder.add_node("provenance_verification", provenance_verification_node)
        builder.add_node("security_alert", security_alert_node)
        builder.add_node("pii_masking", pii_masking_node)
        builder.add_node("compliance_analysis", compliance_analysis_node)
        builder.add_node("human_review", human_review_node)
        builder.add_node("reporting", reporting_node)
        
        builder.set_entry_point("data_retrieval")
        
        builder.add_edge("data_retrieval", "provenance_verification")
        
        builder.add_conditional_edges(
            "provenance_verification",
            _provenance_router,
            {
                "security_alert": "security_alert",
                "pii_masking": "pii_masking",
                "human_review": "human_review",
            },
        )
        
        builder.add_conditional_edges(
            "security_alert",
            _security_router,
            {
                "end": END,
                "pii_masking": "pii_masking",
                "human_review": "human_review",
            },
        )
        
        builder.add_edge("pii_masking", "compliance_analysis")
        
        builder.add_conditional_edges(
            "compliance_analysis",
            _compliance_router,
            {
                "reporting": "reporting",
                "human_review": "human_review",
            },
        )
        
        builder.add_conditional_edges(
            "human_review",
            _human_review_router,
            {
                "reporting": "reporting",
                "end": END,
            },
        )
        
        builder.add_edge("reporting", END)
        
        return builder.compile(checkpointer=self._get_checkpointer())
    
    async def run_audit(
        self,
        raw_content: str,
        metadata: DocumentMetadata,
        thread_id: str | None = None,
    ) -> AuditState:
        """
        Execute the full audit workflow.
        
        Args:
            raw_content: The document text/content to audit
            metadata: Document metadata
            thread_id: Optional thread ID for checkpointing
        
        Returns:
            Final AuditState with results
        """
        import uuid
        thread_id = thread_id or str(uuid.uuid4())
        
        initial_state = AuditState(
            thread_id=thread_id,
            status=ProcessingStatus.PENDING,
            document_metadata=metadata,
            raw_content=raw_content,
        )
        
        config = {"configurable": {"thread_id": thread_id}}
        
        logger.info(f"[AuditGraph] Starting audit workflow for thread: {thread_id}")
        
        try:
            final_state = await self.graph.ainvoke(initial_state, config)
            logger.info(f"[AuditGraph] Audit completed with status: {final_state.status}")
            return final_state
        except Exception as e:
            logger.exception(f"[AuditGraph] Audit workflow failed")
            raise
    
    async def resume_audit(
        self,
        thread_id: str,
        human_decision: str,
        reviewer: str = "unknown",
    ) -> AuditState:
        """
        Resume a paused audit workflow with human input.
        
        Args:
            thread_id: The thread ID to resume
            human_decision: APPROVE or REJECT
            reviewer: Reviewer identifier
        
        Returns:
            Final AuditState with results
        """
        config = {"configurable": {"thread_id": thread_id}}
        
        update_state = AuditState(
            metadata={
                "human_decision": human_decision,
                "reviewer": reviewer,
            }
        )
        
        logger.info(f"[AuditGraph] Resuming audit with human decision: {human_decision}")
        
        try:
            self.graph.update_state(config, update_state.model_dump())
            final_state = await self.graph.ainvoke(None, config)
            return final_state
        except Exception as e:
            logger.exception(f"[AuditGraph] Resume workflow failed")
            raise
    
    def get_state(self, thread_id: str) -> AuditState | None:
        """Get the current state for a thread."""
        config = {"configurable": {"thread_id": thread_id}}
        try:
            snapshot = self.graph.get_state(config)
            if snapshot and snapshot.values:
                return AuditState(**snapshot.values)
        except Exception:
            pass
        return None


def create_audit_graph(
    use_sqlite_checkpoint: bool = False,
    checkpoint_path: str = "checkpoints.db",
) -> AuditGraph:
    """
    Factory function to create an AuditGraph instance.
    
    Args:
        use_sqlite_checkpoint: If True, use SQLite for persistence
        checkpoint_path: Path to SQLite checkpoint database
    
    Returns:
        Configured AuditGraph instance
    """
    return AuditGraph(
        use_sqlite_checkpoint=use_sqlite_checkpoint,
        checkpoint_path=checkpoint_path,
    )
