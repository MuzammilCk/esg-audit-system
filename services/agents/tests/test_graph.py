"""
Tests for LangGraph Multiagent Audit Workflow
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from services.agents.state import (
    AuditState,
    ProcessingStatus,
    AgentDecision,
    DocumentMetadata,
    ProvenanceResult,
    PIIResult,
    ComplianceResult,
    ComplianceFinding,
)
from services.agents.graph import (
    AuditGraph,
    create_audit_graph,
    _provenance_router,
    _security_router,
    _compliance_router,
    _human_review_router,
)


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        source_url="https://example.com/report.pdf",
        original_filename="sustainability_report_2024.pdf",
        mime_type="application/pdf",
        supplier_id="SUPP-001",
        region="EU",
        reporting_period="2024",
    )


@pytest.fixture
def sample_state(sample_metadata):
    return AuditState(
        thread_id="test-thread-123",
        status=ProcessingStatus.PENDING,
        document_metadata=sample_metadata,
        raw_content="This is a sample ESG report with GHG emissions data.",
    )


class TestStateModel:
    """Tests for the AuditState model."""
    
    def test_state_initialization(self, sample_metadata):
        state = AuditState(document_metadata=sample_metadata)
        
        assert state.status == ProcessingStatus.PENDING
        assert state.current_node == "START"
        assert len(state.errors) == 0
        assert len(state.warnings) == 0
    
    def test_add_audit_event(self, sample_state):
        sample_state.add_audit_event("test_node", "TEST_ACTION", {"key": "value"})
        
        assert len(sample_state.audit_trail) == 1
        event = sample_state.audit_trail[0]
        assert event["node"] == "test_node"
        assert event["action"] == "TEST_ACTION"
        assert event["details"]["key"] == "value"
    
    def test_set_error(self, sample_state):
        sample_state.set_error("test_node", "Something went wrong")
        
        assert len(sample_state.errors) == 1
        assert "[test_node]" in sample_state.errors[0]
        assert "Something went wrong" in sample_state.errors[0]


class TestRouters:
    """Tests for workflow routing functions."""
    
    def test_provenance_router_tampered(self, sample_state):
        sample_state.provenance_result = ProvenanceResult(
            status="TAMPERED",
            trust_score=0.0,
        )
        
        result = _provenance_router(sample_state)
        assert result == "security_alert"
    
    def test_provenance_router_verified(self, sample_state):
        sample_state.provenance_result = ProvenanceResult(
            status="VERIFIED",
            trust_score=1.0,
            is_signed=True,
        )
        
        result = _provenance_router(sample_state)
        assert result == "pii_masking"
    
    def test_provenance_router_unsigned(self, sample_state):
        sample_state.provenance_result = ProvenanceResult(
            status="UNSIGNED",
            trust_score=0.5,
        )
        
        result = _provenance_router(sample_state)
        assert result == "pii_masking"
    
    def test_security_router_critical(self, sample_state):
        sample_state.errors = ["[security_alert] DOCUMENT_TAMPERED"]
        
        result = _security_router(sample_state)
        assert result == "end"
    
    def test_security_router_warning(self, sample_state):
        sample_state.errors = []
        sample_state.warnings = ["[security_alert] UNSIGNED_DOCUMENT"]
        
        result = _security_router(sample_state)
        assert result == "pii_masking"
    
    def test_compliance_router_needs_review(self, sample_state):
        sample_state.compliance_result = ComplianceResult(
            overall_decision=AgentDecision.REVIEW,
            requires_human_review=True,
        )
        
        result = _compliance_router(sample_state)
        assert result == "human_review"
    
    def test_compliance_router_approved(self, sample_state):
        sample_state.compliance_result = ComplianceResult(
            overall_decision=AgentDecision.APPROVE,
            compliance_score=0.95,
            requires_human_review=False,
        )
        
        result = _compliance_router(sample_state)
        assert result == "reporting"
    
    def test_human_review_router_with_decision(self, sample_state):
        sample_state.metadata = {"human_decision": "APPROVE"}
        
        result = _human_review_router(sample_state)
        assert result == "reporting"
    
    def test_human_review_router_no_decision(self, sample_state):
        sample_state.metadata = {}
        
        result = _human_review_router(sample_state)
        assert result == "end"


class TestAuditGraph:
    """Tests for the AuditGraph class."""
    
    @pytest.fixture
    def audit_graph(self):
        with patch("services.agents.graph.SqliteSaver"), \
             patch("services.agents.graph.MemorySaver"):
            return create_audit_graph(use_sqlite_checkpoint=False)
    
    def test_graph_creation(self, audit_graph):
        assert audit_graph is not None
        assert audit_graph.graph is not None
    
    @pytest.mark.asyncio
    async def test_run_audit_success(self, audit_graph, sample_metadata):
        with patch.object(audit_graph.graph, 'ainvoke') as mock_invoke:
            mock_final_state = AuditState(
                thread_id="test-thread",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=sample_metadata,
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.9,
                ),
                provenance_result=ProvenanceResult(
                    status="VERIFIED",
                    trust_score=1.0,
                ),
            )
            mock_invoke.return_value = mock_final_state
            
            result = await audit_graph.run_audit(
                raw_content="Test content",
                metadata=sample_metadata,
            )
            
            assert result.status == ProcessingStatus.COMPLIANT
            assert result.compliance_result.overall_decision == AgentDecision.APPROVE


class TestComplianceFinding:
    """Tests for ComplianceFinding model."""
    
    def test_finding_creation(self):
        finding = ComplianceFinding(
            regulation_code="ESRS E1",
            regulation_name="Climate Change",
            requirement="GHG emissions disclosure",
            status=AgentDecision.APPROVE,
            evidence="Found emissions data",
            confidence=0.85,
            severity="LOW",
        )
        
        assert finding.regulation_code == "ESRS E1"
        assert finding.status == AgentDecision.APPROVE
        assert finding.confidence == 0.85
    
    def test_finding_with_remediation(self):
        finding = ComplianceFinding(
            regulation_code="ESRS S1",
            regulation_name="Own Workforce",
            requirement="Health and safety disclosure",
            status=AgentDecision.REJECT,
            evidence="No H&S data found",
            confidence=0.6,
            severity="HIGH",
            remediation="Add health and safety statistics",
        )
        
        assert finding.remediation is not None
        assert "health and safety" in finding.remediation.lower()
