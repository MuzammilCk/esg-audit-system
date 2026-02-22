"""
End-to-End Audit Workflow Integration Tests

Tests the complete audit workflow from document ingestion to report generation.
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
from services.agents.graph import create_audit_graph


pytestmark = pytest.mark.integration


class TestEndToEndAuditWorkflow:
    """Tests for complete audit workflow execution."""
    
    @pytest.mark.asyncio
    async def test_full_audit_happy_path(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test complete audit workflow with compliant document."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-thread-123",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=sample_metadata,
                normalized_text=sample_esg_document,
                provenance_result=ProvenanceResult(
                    status="VERIFIED",
                    trust_score=1.0,
                    is_signed=True,
                ),
                pii_result=PIIResult(
                    masked_text=sample_esg_document,
                    entities_found=0,
                ),
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.85,
                    findings=[],
                    requires_human_review=False,
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=sample_metadata,
                thread_id="test-thread-123",
            )
            
            assert result.status == ProcessingStatus.COMPLIANT
            assert result.provenance_result.status == "VERIFIED"
            assert result.compliance_result.overall_decision == AgentDecision.APPROVE
            assert result.compliance_result.compliance_score >= 0.8
    
    @pytest.mark.asyncio
    async def test_audit_with_tampered_document(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test audit workflow when document fails provenance verification."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-thread-tampered",
                status=ProcessingStatus.ERROR,
                document_metadata=sample_metadata,
                raw_content=sample_esg_document,
                provenance_result=ProvenanceResult(
                    status="TAMPERED",
                    trust_score=0.0,
                    is_signed=False,
                ),
                errors=["[security_alert] DOCUMENT_TAMPERED: Cryptographic signature invalid"],
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=sample_metadata,
                thread_id="test-thread-tampered",
            )
            
            assert result.status == ProcessingStatus.ERROR
            assert result.provenance_result.status == "TAMPERED"
            assert len(result.errors) > 0
            assert any("TAMPERED" in err for err in result.errors)
    
    @pytest.mark.asyncio
    async def test_audit_requires_human_review(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test audit workflow when human review is required."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-thread-review",
                status=ProcessingStatus.REQUIRES_REVIEW,
                document_metadata=sample_metadata,
                normalized_text=sample_esg_document,
                provenance_result=ProvenanceResult(
                    status="VERIFIED",
                    trust_score=1.0,
                ),
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.REVIEW,
                    compliance_score=0.55,
                    findings=[],
                    requires_human_review=True,
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=sample_metadata,
                thread_id="test-thread-review",
            )
            
            assert result.status == ProcessingStatus.REQUIRES_REVIEW
            assert result.compliance_result.requires_human_review is True
    
    @pytest.mark.asyncio
    async def test_audit_resume_after_human_review(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test resuming audit workflow after human decision."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'update_state') as mock_update, \
             patch.object(graph.graph, 'ainvoke') as mock_invoke:
            
            mock_invoke.return_value = AuditState(
                thread_id="test-thread-resume",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=sample_metadata,
                normalized_text=sample_esg_document,
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.85,
                ),
                metadata={
                    "human_decision": "APPROVE",
                    "reviewer": "auditor@example.com",
                },
            )
            
            result = await graph.resume_audit(
                thread_id="test-thread-resume",
                human_decision="APPROVE",
                reviewer="auditor@example.com",
            )
            
            mock_update.assert_called_once()
            assert result.compliance_result.overall_decision == AgentDecision.APPROVE


class TestProvenanceVerificationIntegration:
    """Tests for provenance verification in the workflow."""
    
    @pytest.mark.asyncio
    async def test_unsigned_document_continues_with_warning(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test that unsigned documents continue processing with a warning."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-unsigned",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=sample_metadata,
                provenance_result=ProvenanceResult(
                    status="UNSIGNED",
                    trust_score=0.5,
                    is_signed=False,
                ),
                warnings=["[provenance_verification] Document is not digitally signed"],
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.8,
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=sample_metadata,
            )
            
            assert result.status == ProcessingStatus.COMPLIANT
            assert result.provenance_result.status == "UNSIGNED"
            assert len(result.warnings) > 0
    
    @pytest.mark.asyncio
    async def test_ai_generated_document_flagged(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test that AI-generated documents are flagged appropriately."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-ai-generated",
                status=ProcessingStatus.REQUIRES_REVIEW,
                document_metadata=sample_metadata,
                provenance_result=ProvenanceResult(
                    status="VERIFIED",
                    trust_score=0.7,
                    is_signed=True,
                    is_ai_generated=True,
                ),
                warnings=["[provenance_verification] Document appears to be AI-generated"],
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.REVIEW,
                    compliance_score=0.7,
                    requires_human_review=True,
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=sample_metadata,
            )
            
            assert result.provenance_result.is_ai_generated is True
            assert result.compliance_result.requires_human_review is True


class TestPIIMaskingIntegration:
    """Tests for PII masking in the workflow."""
    
    @pytest.mark.asyncio
    async def test_pii_masking_preserves_document_structure(
        self,
        sample_metadata,
    ):
        """Test that PII masking preserves document structure."""
        
        document_with_pii = """
        Sustainability Report 2024
        
        Contact: John Smith, CEO
        Email: john.smith@company.com
        Phone: +1-555-123-4567
        
        Employee data: Jane Doe, Head of Sustainability
        Location: 123 Main Street, New York, NY 10001
        """
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-pii",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=sample_metadata,
                pii_result=PIIResult(
                    masked_text="""
                    Sustainability Report 2024
                    
                    Contact: <PERSON_1>, CEO
                    Email: <EMAIL_ADDRESS_1>
                    Phone: <PHONE_NUMBER_1>
                    
                    Employee data: <PERSON_2>, Head of Sustainability
                    Location: <LOCATION_1>
                    """,
                    entities_found=5,
                    entity_types=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "LOCATION"],
                    mapping_key="pii:test-pii:entities",
                ),
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.8,
                ),
            )
            
            result = await graph.run_audit(
                raw_content=document_with_pii,
                metadata=sample_metadata,
            )
            
            assert result.pii_result.entities_found == 5
            assert "<PERSON_" in result.pii_result.masked_text
            assert "<EMAIL_ADDRESS_" in result.pii_result.masked_text
            assert "john.smith@company.com" not in result.pii_result.masked_text


class TestComplianceAnalysisIntegration:
    """Tests for compliance analysis in the workflow."""
    
    @pytest.mark.asyncio
    async def test_csrd_compliance_analysis(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test CSRD compliance analysis."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-csrd",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=sample_metadata,
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.85,
                    findings=[
                        ComplianceFinding(
                            regulation_code="ESRS E1",
                            regulation_name="Climate Change",
                            requirement="GHG emissions disclosure",
                            status=AgentDecision.APPROVE,
                            evidence="Scope 1, 2, 3 emissions reported",
                            confidence=0.9,
                            severity="LOW",
                        ),
                        ComplianceFinding(
                            regulation_code="ESRS S1",
                            regulation_name="Own Workforce",
                            requirement="Employee disclosure",
                            status=AgentDecision.APPROVE,
                            evidence="Employee statistics provided",
                            confidence=0.85,
                            severity="LOW",
                        ),
                        ComplianceFinding(
                            regulation_code="ESRS G1",
                            regulation_name="Governance",
                            requirement="Board composition",
                            status=AgentDecision.APPROVE,
                            evidence="Board diversity data provided",
                            confidence=0.8,
                            severity="LOW",
                        ),
                    ],
                    requires_human_review=False,
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=sample_metadata,
            )
            
            assert result.compliance_result.overall_decision == AgentDecision.APPROVE
            assert len(result.compliance_result.findings) == 3
            assert result.compliance_result.compliance_score >= 0.8
    
    @pytest.mark.asyncio
    async def test_non_compliant_document_analysis(
        self,
        sample_metadata,
        sample_non_compliant_document,
    ):
        """Test analysis of non-compliant document."""
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-non-compliant",
                status=ProcessingStatus.NON_COMPLIANT,
                document_metadata=sample_metadata,
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.REJECT,
                    compliance_score=0.25,
                    findings=[
                        ComplianceFinding(
                            regulation_code="ESRS E1",
                            regulation_name="Climate Change",
                            requirement="GHG emissions disclosure",
                            status=AgentDecision.REJECT,
                            evidence="No emissions data found",
                            confidence=0.95,
                            severity="HIGH",
                            remediation="Add GHG emissions disclosure (Scope 1, 2, 3)",
                        ),
                        ComplianceFinding(
                            regulation_code="ESRS S1",
                            regulation_name="Own Workforce",
                            requirement="Employee disclosure",
                            status=AgentDecision.REJECT,
                            evidence="No workforce data found",
                            confidence=0.95,
                            severity="HIGH",
                            remediation="Add employee statistics and diversity data",
                        ),
                    ],
                    requires_human_review=False,
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_non_compliant_document,
                metadata=sample_metadata,
            )
            
            assert result.status == ProcessingStatus.NON_COMPLIANT
            assert result.compliance_result.overall_decision == AgentDecision.REJECT
            assert result.compliance_result.compliance_score < 0.5


class TestAuditStatePersistence:
    """Tests for audit state persistence and recovery."""
    
    @pytest.mark.asyncio
    async def test_state_recovery_from_checkpoint(
        self,
        sample_metadata,
        sample_esg_document,
        temp_checkpoints_db,
    ):
        """Test recovering state from SQLite checkpoint."""
        
        with patch("services.agents.graph.SqliteSaver") as mock_saver:
            mock_saver_instance = Mock()
            mock_saver.return_value = mock_saver_instance
            
            graph = create_audit_graph(
                use_sqlite_checkpoint=True,
                checkpoint_path=temp_checkpoints_db,
            )
            
            with patch.object(graph.graph, 'ainvoke') as mock_invoke:
                mock_invoke.return_value = AuditState(
                    thread_id="persisted-thread",
                    status=ProcessingStatus.REQUIRES_REVIEW,
                    document_metadata=sample_metadata,
                    compliance_result=ComplianceResult(
                        overall_decision=AgentDecision.REVIEW,
                        compliance_score=0.6,
                        requires_human_review=True,
                    ),
                )
                
                result = await graph.run_audit(
                    raw_content=sample_esg_document,
                    metadata=sample_metadata,
                    thread_id="persisted-thread",
                )
                
                assert result.thread_id == "persisted-thread"
    
    @pytest.mark.asyncio
    async def test_get_state_returns_none_for_unknown_thread(self):
        """Test that get_state returns None for unknown thread."""
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'get_state', return_value=None):
            state = graph.get_state("unknown-thread-id")
            assert state is None
