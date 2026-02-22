"""
Integration Tests for ESG Audit System

These tests verify end-to-end functionality across all services.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
import tempfile
import os
import json
from datetime import datetime, timezone

from services.agents.state import (
    AuditState,
    ProcessingStatus,
    AgentDecision,
    DocumentMetadata,
    ProvenanceResult,
    PIIResult,
    ComplianceResult,
    ComplianceFinding,
    AuditReport,
)
from services.agents.graph import AuditGraph, create_audit_graph
from services.llm.client import LLMClient
from services.llm.structured_output import (
    ComplianceAnalysisOutput,
    FindingOutput,
    FindingStatus,
    Severity,
)
from services.vectorstore.embeddings import EmbeddingService, EmbeddingResult
from services.vectorstore.indexer import DocumentIndexer
from services.vectorstore.retriever import RAGRetriever
from services.security.honeypot import HoneypotManager, HoneypotAgent
from services.security.redteam import PyRITRedTeamer
from services.security.threat_detector import ThreatDetector


@pytest.fixture
def sample_metadata():
    """Sample document metadata for testing."""
    return DocumentMetadata(
        source_url="https://example.com/esg_report_2024.pdf",
        original_filename="sustainability_report_2024.pdf",
        mime_type="application/pdf",
        supplier_id="SUPP-001",
        region="EU",
        reporting_period="2024",
    )


@pytest.fixture
def sample_esg_document():
    """Sample ESG document content for testing."""
    return """
    Sustainability Report 2024
    
    Executive Summary
    
    Our company is committed to achieving net zero emissions by 2040. This report 
    outlines our environmental, social, and governance performance for the fiscal year 2024.
    
    Environmental Performance
    
    Greenhouse Gas Emissions
    - Scope 1 emissions: 15,000 tCO2e
    - Scope 2 emissions: 8,500 tCO2e (market-based)
    - Scope 3 emissions: 125,000 tCO2e (estimated)
    
    We have reduced our Scope 1 emissions by 12% compared to the previous year through
    the implementation of energy efficiency measures and transition to renewable energy sources.
    
    Energy Consumption
    - Total energy consumption: 85,000 MWh
    - Renewable energy share: 45%
    - Energy intensity: 0.12 MWh per unit produced
    
    Water Usage
    - Total water withdrawal: 2.5 million cubic meters
    - Water recycled: 35%
    
    Social Performance
    
    Employee Statistics
    - Total employees: 5,200
    - Female representation in leadership: 32%
    - Employee turnover rate: 8.5%
    
    Health and Safety
    - Lost time injury rate: 0.8 per million hours worked
    - Zero work-related fatalities
    
    Governance
    
    Board Composition
    - Independent directors: 60%
    - Board diversity: 40% women, 25% ethnic minorities
    
    Anti-Corruption
    - 100% of employees completed anti-corruption training
    - Zero confirmed corruption incidents
    
    Supply Chain
    - 85% of suppliers assessed for ESG compliance
    - 12 suppliers audited in 2024
    """


@pytest.fixture
def sample_non_compliant_document():
    """Sample non-compliant document for testing."""
    return """
    Annual Report 2024
    
    Financial Highlights
    
    Revenue increased by 15% year-over-year. Profit margins improved.
    
    Note: This document does not contain ESG-related disclosures as required
    by applicable regulations.
    """


@pytest.fixture
def mock_openai_embeddings():
    """Mock OpenAI embeddings."""
    return [[0.1] * 1536 for _ in range(10)]


@pytest.fixture
def mock_vector_store():
    """Mock Qdrant vector store."""
    store = Mock()
    store.initialize = AsyncMock()
    store.upsert_documents = AsyncMock(return_value=5)
    store.search = AsyncMock(return_value=[
        {
            "id": "chunk-1",
            "score": 0.85,
            "payload": {
                "content": "Sample regulatory context",
                "document_id": "reg-doc-1",
                "regulation_codes": ["ESRS E1"],
            },
        }
    ])
    store.delete_document = AsyncMock(return_value=True)
    return store


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for encrypted storage."""
    client = Mock()
    client.get = AsyncMock(return_value=b"encrypted_data")
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    client.exists = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_llm_response():
    """Mock LLM structured response for compliance analysis."""
    output = ComplianceAnalysisOutput(
        overall_status=FindingStatus.APPROVE,
        compliance_score=0.85,
        findings=[
            FindingOutput(
                regulation_code="ESRS E1",
                regulation_name="Climate Change",
                requirement="GHG emissions disclosure",
                status=FindingStatus.APPROVE,
                severity=Severity.LOW,
                confidence=0.9,
                evidence=[],
                gaps=[],
                remediation=None,
            ),
            FindingOutput(
                regulation_code="ESRS S1",
                regulation_name="Own Workforce",
                requirement="Employee disclosure",
                status=FindingStatus.APPROVE,
                severity=Severity.LOW,
                confidence=0.85,
                evidence=[],
                gaps=[],
                remediation=None,
            ),
        ],
        executive_summary="Document demonstrates good ESG compliance with minor gaps.",
        key_strengths=["Comprehensive GHG disclosure", "Clear workforce statistics"],
        key_gaps=["Scope 3 estimation methodology not detailed"],
        recommendations=["Add Scope 3 calculation methodology"],
        requires_human_review=False,
        reasoning="Document meets most CSRD requirements.",
    )
    
    response = Mock()
    response.parsed = output
    return response


@pytest.fixture
def audit_graph():
    """Create audit graph with memory checkpointing for tests."""
    with patch("services.agents.graph.SqliteSaver"):
        return create_audit_graph(use_sqlite_checkpoint=False)


@pytest.fixture
def temp_checkpoints_db():
    """Create temporary checkpoint database."""
    import tempfile
    import os
    import time
    
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        time.sleep(0.1)
        os.unlink(path)
    except PermissionError:
        pass
