"""
Tests for LLM Service Components
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json

from services.llm.client import LLMClient, LLMResponse, StructuredResponse
from services.llm.structured_output import (
    ComplianceAnalysisOutput,
    FindingOutput,
    FindingStatus,
    Severity,
)
from services.llm.prompts import ComplianceAnalysisPrompt, EvidenceExtractionPrompt
from services.llm.analyzer import LLMComplianceAnalyzer


class TestLLMClient:
    """Tests for the LLM client."""
    
    @pytest.fixture
    def mock_openai_client(self):
        client = Mock()
        client.chat = Mock()
        client.chat.completions = Mock()
        return client
    
    @pytest.fixture
    def llm_client(self):
        return LLMClient(
            api_key="test-key",
            model="gpt-4-turbo-preview",
            max_retries=1,
        )
    
    @pytest.mark.asyncio
    async def test_complete_success(self, llm_client):
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        
        with patch.object(llm_client, '_get_async_client') as mock_get_client:
            mock_async_client = AsyncMock()
            mock_async_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_async_client
            
            response = await llm_client.complete(
                messages=[{"role": "user", "content": "test"}]
            )
            
            assert response.content == "Test response"
            assert response.model == "gpt-4-turbo-preview"
            assert response.tokens_total == 15


class TestStructuredOutput:
    """Tests for structured output models."""
    
    def test_finding_output_creation(self):
        finding = FindingOutput(
            regulation_code="ESRS E1",
            regulation_name="Climate Change",
            requirement="GHG emissions disclosure",
            status=FindingStatus.APPROVE,
            severity=Severity.LOW,
            confidence=0.95,
            evidence=[],
            gaps=[],
            remediation=None,
        )
        
        assert finding.regulation_code == "ESRS E1"
        assert finding.status == FindingStatus.APPROVE
        assert finding.confidence == 0.95
    
    def test_compliance_analysis_output(self):
        findings = [
            FindingOutput(
                regulation_code="ESRS E1",
                regulation_name="Climate Change",
                requirement="Test requirement",
                status=FindingStatus.APPROVE,
                severity=Severity.LOW,
                confidence=0.9,
            )
        ]
        
        output = ComplianceAnalysisOutput(
            overall_status=FindingStatus.APPROVE,
            compliance_score=0.9,
            findings=findings,
            executive_summary="Test summary",
            key_strengths=["Good GHG disclosure"],
            key_gaps=[],
            recommendations=["Continue monitoring"],
            requires_human_review=False,
            reasoning="Test reasoning",
        )
        
        assert output.compliance_score == 0.9
        assert len(output.findings) == 1
        assert output.requires_human_review is False


class TestPrompts:
    """Tests for prompt templates."""
    
    def test_compliance_analysis_prompt(self):
        prompt = ComplianceAnalysisPrompt(
            document_text="Test document content about GHG emissions.",
            regulations=["ESRS E1", "SEC-GHG"],
            metadata={"supplier_id": "SUPP-001"},
        )
        
        system_prompt = prompt.build_system_prompt()
        user_prompt = prompt.build_user_prompt()
        
        assert "ESG" in system_prompt
        assert "compliance" in system_prompt.lower()
        assert "ESRS E1" in user_prompt
        assert "SUPP-001" in user_prompt
    
    def test_evidence_extraction_prompt(self):
        prompt = EvidenceExtractionPrompt(
            document_text="Document text",
            regulation_code="ESRS E1",
            requirement="GHG emissions disclosure",
        )
        
        system_prompt = prompt.build_system_prompt()
        user_prompt = prompt.build_user_prompt()
        
        assert "evidence" in system_prompt.lower()
        assert "ESRS E1" in user_prompt


class TestLLMComplianceAnalyzer:
    """Tests for the LLM compliance analyzer."""
    
    @pytest.fixture
    def mock_llm_client(self):
        client = Mock(spec=LLMClient)
        
        mock_output = ComplianceAnalysisOutput(
            overall_status=FindingStatus.APPROVE,
            compliance_score=0.85,
            findings=[
                FindingOutput(
                    regulation_code="ESRS E1",
                    regulation_name="Climate Change",
                    requirement="GHG disclosure",
                    status=FindingStatus.APPROVE,
                    severity=Severity.LOW,
                    confidence=0.9,
                )
            ],
            executive_summary="Test summary",
            key_strengths=[],
            key_gaps=[],
            recommendations=[],
            requires_human_review=False,
            reasoning="Test reasoning",
        )
        
        mock_structured_response = Mock()
        mock_structured_response.parsed = mock_output
        
        client.complete_structured = AsyncMock(return_value=mock_structured_response)
        
        return client
    
    @pytest.mark.asyncio
    async def test_analyze_compliance(self, mock_llm_client):
        analyzer = LLMComplianceAnalyzer(llm_client=mock_llm_client)
        
        findings = await analyzer.analyze_compliance(
            text="Test document with GHG emissions data.",
            regulations=["ESRS E1"],
            metadata={},
        )
        
        assert len(findings) == 1
        assert findings[0].regulation_code == "ESRS E1"
    
    @pytest.mark.asyncio
    async def test_fallback_on_failure(self):
        mock_client = Mock(spec=LLMClient)
        mock_client.complete_structured = AsyncMock(side_effect=Exception("API Error"))
        
        analyzer = LLMComplianceAnalyzer(
            llm_client=mock_client,
            fallback_to_rules=True,
        )
        
        text = "This document covers GHG emissions and climate change."
        findings = await analyzer.analyze_compliance(
            text=text,
            regulations=["ESRS E1"],
            metadata={},
        )
        
        assert len(findings) > 0
