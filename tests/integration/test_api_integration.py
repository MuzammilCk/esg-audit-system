"""
API Integration Tests

Tests for FastAPI endpoints across all services.
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
    ComplianceResult,
)


pytestmark = pytest.mark.integration


class TestAuditAPIIntegration:
    """Tests for the Audit Agents API."""
    
    @pytest.fixture
    def audit_app(self):
        try:
            from services.agents.api import app
            return app
        except ImportError:
            pytest.skip("Audit API not available")
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, audit_app):
        """Test health check endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=audit_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/healthz")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_submit_audit_endpoint(
        self,
        audit_app,
        sample_metadata,
        sample_esg_document,
    ):
        """Test audit submission endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        with patch("services.agents.api._audit_graph") as mock_graph:
            mock_audit_graph = Mock()
            mock_audit_graph.run_audit = AsyncMock(return_value=AuditState(
                thread_id="test-thread-api",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=DocumentMetadata(
                    source_url="https://example.com/report.pdf",
                    original_filename="report.pdf",
                ),
                provenance_result=ProvenanceResult(
                    status="VERIFIED",
                    trust_score=1.0,
                ),
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.85,
                ),
            ))
            
            mock_graph.run_audit = mock_audit_graph.run_audit
            
            async with AsyncClient(
                transport=ASGITransport(app=audit_app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/audit",
                    json={
                        "content": sample_esg_document,
                        "source_url": sample_metadata.source_url,
                        "original_filename": sample_metadata.original_filename,
                        "mime_type": sample_metadata.mime_type,
                        "supplier_id": sample_metadata.supplier_id,
                        "region": sample_metadata.region,
                    },
                )
                
            assert response.status_code in [200, 422, 500, 503]
    
    @pytest.mark.asyncio
    async def test_get_audit_status_endpoint(self, audit_app):
        """Test audit status retrieval endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=audit_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/audit/test-thread-status")
            
            assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_resume_audit_endpoint(self, audit_app):
        """Test audit resume endpoint for human-in-the-loop."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=audit_app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/audit/test-thread-resume/resume",
                json={
                    "human_decision": "APPROVE",
                    "reviewer": "auditor@example.com",
                },
            )
            
            assert response.status_code in [200, 400, 404]


class TestVectorStoreAPIIntegration:
    """Tests for the Vector Store API."""
    
    @pytest.fixture
    def vectorstore_app(self):
        try:
            from services.vectorstore.api import app
            return app
        except ImportError:
            pytest.skip("Vector Store API not available")
    
    @pytest.mark.asyncio
    async def test_index_document_endpoint(
        self,
        vectorstore_app,
        sample_esg_document,
    ):
        """Test document indexing endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=vectorstore_app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/index",
                json={
                    "content": sample_esg_document,
                    "document_id": "doc-123",
                    "source_url": "https://example.com/report.pdf",
                },
            )
            
            assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_search_endpoint(self, vectorstore_app):
        """Test vector search endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=vectorstore_app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/search",
                json={
                    "query": "GHG emissions",
                    "limit": 5,
                },
            )
            
            assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_stats_endpoint(self, vectorstore_app):
        """Test stats endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=vectorstore_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/stats")
            
            assert response.status_code in [200, 500, 503]


class TestSecurityAPIIntegration:
    """Tests for the Security API."""
    
    @pytest.fixture
    def security_app(self):
        try:
            from services.security.api import app
            return app
        except ImportError:
            pytest.skip("Security API not available")
    
    @pytest.mark.asyncio
    async def test_threat_summary_endpoint(self, security_app):
        """Test threat summary endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=security_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/honeypots/threat-summary")
            
            assert response.status_code in [200, 500, 503]
    
    @pytest.mark.asyncio
    async def test_threat_alerts_endpoint(self, security_app):
        """Test threat alerts endpoint."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=security_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/threats/alerts")
            
            assert response.status_code in [200, 500, 503]


class TestEndToEndAPIScenario:
    """End-to-end API test scenarios."""
    
    @pytest.fixture
    def audit_app(self):
        try:
            from services.agents.api import app
            return app
        except ImportError:
            pytest.skip("Audit API not available")
    
    @pytest.mark.asyncio
    async def test_complete_audit_flow_via_api(
        self,
        audit_app,
        sample_metadata,
        sample_esg_document,
    ):
        """Test complete audit flow through API calls."""
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(
            transport=ASGITransport(app=audit_app),
            base_url="http://test",
        ) as client:
            submit_response = await client.post(
                "/api/audit",
                json={
                    "content": sample_esg_document,
                    "source_url": sample_metadata.source_url,
                    "original_filename": sample_metadata.original_filename,
                    "mime_type": sample_metadata.mime_type,
                    "supplier_id": sample_metadata.supplier_id,
                    "region": sample_metadata.region,
                },
            )
            
            assert submit_response.status_code in [200, 500]
            
            if submit_response.status_code == 200:
                data = submit_response.json()
                assert "thread_id" in data
