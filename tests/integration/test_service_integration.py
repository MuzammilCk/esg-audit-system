"""
Service Integration Tests

Tests integration between different services in the ESG audit system.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio

from services.agents.state import (
    AuditState,
    ProcessingStatus,
    AgentDecision,
    DocumentMetadata,
    ComplianceResult,
    ComplianceFinding,
)
from services.agents.graph import create_audit_graph
from services.vectorstore.embeddings import EmbeddingService, EmbeddingResult
from services.vectorstore.indexer import DocumentIndexer, TextChunker
from services.vectorstore.retriever import RAGRetriever
from services.llm.client import LLMClient
from services.llm.analyzer import LLMComplianceAnalyzer
from services.llm.structured_output import (
    ComplianceAnalysisOutput,
    FindingOutput,
    FindingStatus,
    Severity,
)


pytestmark = pytest.mark.integration


class TestAgentsVectorStoreIntegration:
    """Tests for agents + vector store integration."""
    
    @pytest.mark.asyncio
    async def test_rag_context_enriches_compliance_analysis(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test that RAG retrieval enriches compliance analysis."""
        
        mock_vector_store = Mock()
        mock_vector_store.hybrid_search = AsyncMock(return_value=[
            Mock(
                id="chunk-1",
                content="ESRS E1 requires disclosure of Scope 1, 2, and 3 GHG emissions",
                hybrid_score=0.92,
                dense_score=0.90,
                sparse_score=0.95,
                metadata={"regulation_codes": ["ESRS E1"]},
            ),
            Mock(
                id="chunk-2",
                content="SEC Climate Rules require disclosure of climate-related risks",
                hybrid_score=0.88,
                dense_score=0.85,
                sparse_score=0.90,
                metadata={"regulation_codes": ["SEC-GHG"]},
            ),
        ])
        
        with patch("services.vectorstore.retriever.get_vector_store", return_value=mock_vector_store):
            retriever = RAGRetriever()
            
            context = await retriever.retrieve(
                query="GHG emissions disclosure requirements",
                filters={"regulation_codes": ["ESRS E1"]},
                limit=5,
            )
            
            assert len(context.documents) == 2
            assert context.documents[0]["score"] >= 0.85
    
    @pytest.mark.asyncio
    async def test_document_indexing_before_audit(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test that documents are indexed before compliance analysis."""
        
        mock_embedding_service = Mock(spec=EmbeddingService)
        mock_embedding_service.embed_documents = AsyncMock(return_value=[
            [0.1] * 1536 for _ in range(5)
        ])
        
        mock_vector_store = Mock()
        mock_vector_store.upsert_documents = AsyncMock(return_value=5)
        mock_vector_store.initialize = AsyncMock()
        
        indexer = DocumentIndexer(vector_store=mock_vector_store)
        
        result = await indexer.index_document(
            content=sample_esg_document,
            metadata={
                "document_id": "test-doc-123",
                "source_url": sample_metadata.source_url,
                "original_filename": sample_metadata.original_filename,
            },
        )
        
        assert result.document_id == "test-doc-123"
        assert result.chunks_indexed == 5
        mock_vector_store.upsert_documents.assert_called_once()


class TestAgentsLLMIntegration:
    """Tests for agents + LLM integration."""
    
    @pytest.mark.asyncio
    async def test_llm_compliance_analyzer_called_in_workflow(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test that LLM analyzer is called during compliance analysis node."""
        
        mock_llm_client = Mock(spec=LLMClient)
        
        mock_output = ComplianceAnalysisOutput(
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
                    remediation=None,
                ),
            ],
            executive_summary="Good compliance",
            key_strengths=["GHG data present"],
            key_gaps=[],
            recommendations=[],
            requires_human_review=False,
            reasoning="Document meets requirements",
        )
        
        mock_response = Mock()
        mock_response.parsed = mock_output
        mock_llm_client.complete_structured = AsyncMock(return_value=mock_response)
        
        analyzer = LLMComplianceAnalyzer(llm_client=mock_llm_client)
        
        findings = await analyzer.analyze_compliance(
            text=sample_esg_document,
            regulations=["ESRS E1", "ESRS S1"],
            metadata={"supplier_id": sample_metadata.supplier_id},
        )
        
        assert len(findings) > 0
        mock_llm_client.complete_structured.assert_called()
    
    @pytest.mark.asyncio
    async def test_llm_fallback_to_rules_on_failure(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test that LLM analyzer falls back to rules-based on API failure."""
        
        mock_llm_client = Mock(spec=LLMClient)
        mock_llm_client.complete_structured = AsyncMock(side_effect=Exception("API Error"))
        
        analyzer = LLMComplianceAnalyzer(
            llm_client=mock_llm_client,
            fallback_to_rules=True,
        )
        
        findings = await analyzer.analyze_compliance(
            text=sample_esg_document,
            regulations=["ESRS E1"],
            metadata={},
        )
        
        assert len(findings) > 0


class TestVectorStoreLLMIntegration:
    """Tests for vector store + LLM integration."""
    
    @pytest.mark.asyncio
    async def test_embeddings_generated_for_indexing(
        self,
        sample_esg_document,
    ):
        """Test that embeddings are generated when indexing documents."""
        
        mock_openai_provider = Mock()
        mock_openai_provider.embed_documents = AsyncMock(return_value=EmbeddingResult(
            embeddings=[[0.1] * 1536 for _ in range(3)],
            model="text-embedding-3-small",
            dimensions=1536,
            tokens_used=500,
        ))
        
        embedding_service = EmbeddingService(provider="openai")
        embedding_service._provider = mock_openai_provider
        
        chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        chunks = chunker.chunk_text(sample_esg_document, {"document_id": "test"})
        
        result = await embedding_service.embed_documents([c.content for c in chunks])
        
        assert len(result.embeddings) == 3
        assert result.tokens_used == 500
    
    @pytest.mark.asyncio
    async def test_query_embedding_for_retrieval(
        self,
    ):
        """Test that query embeddings are generated for semantic search."""
        
        mock_openai_provider = Mock()
        mock_openai_provider.embed_query = AsyncMock(return_value=[0.1] * 1536)
        
        embedding_service = EmbeddingService(provider="openai")
        embedding_service._provider = mock_openai_provider
        
        embedding = await embedding_service.embed_query("GHG emissions disclosure requirements")
        
        assert len(embedding) == 1536
        mock_openai_provider.embed_query.assert_called_once()


class TestSecurityIntegration:
    """Tests for security service integration."""
    
    @pytest.mark.asyncio
    async def test_honeypot_detects_suspicious_input(
        self,
    ):
        """Test that honeypot detects suspicious input patterns."""
        from services.security.honeypot import HoneypotAgent, HoneypotType, InteractionType
        
        honeypot = HoneypotAgent(
            honeypot_id="test-db-honeypot",
            honeypot_type=HoneypotType.DATABASE,
            port=5432,
        )
        
        interaction = honeypot.record_interaction(
            interaction_type=InteractionType.INJECTION_ATTEMPT,
            source_ip="192.168.1.100",
            source_port=54321,
            request_data="'; DROP TABLE users; --",
        )
        
        assert interaction.risk_score >= 0.5
        assert len(interaction.threat_indicators) > 0
    
    @pytest.mark.asyncio
    async def test_honeypot_manager_correlation(
        self,
    ):
        """Test honeypot manager correlates threat data."""
        from services.security.honeypot import HoneypotManager, HoneypotType, InteractionType
        
        manager = HoneypotManager()
        honeypot = manager.create_honeypot(HoneypotType.ADMIN_PANEL)
        
        interaction = manager.record_interaction(
            honeypot_id=honeypot.honeypot_id,
            interaction_type=InteractionType.AUTHENTICATION,
            source_ip="10.0.0.50",
            source_port=443,
        )
        
        summary = manager.get_threat_summary()
        assert summary["total_honeypots"] == 1


class TestMultiRegionCompliance:
    """Tests for multi-region compliance analysis."""
    
    @pytest.mark.asyncio
    async def test_eu_csrd_compliance(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test CSRD compliance analysis for EU documents."""
        
        eu_metadata = DocumentMetadata(
            source_url="https://eu-company.com/report.pdf",
            original_filename="esg_report_2024.pdf",
            mime_type="application/pdf",
            supplier_id="EU-SUPP-001",
            region="EU",
            reporting_period="2024",
        )
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-eu-csrd",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=eu_metadata,
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.85,
                    findings=[],
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=eu_metadata,
            )
            
            assert result.document_metadata.region == "EU"
    
    @pytest.mark.asyncio
    async def test_us_sec_compliance(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test SEC compliance analysis for US documents."""
        
        us_metadata = DocumentMetadata(
            source_url="https://us-company.com/report.pdf",
            original_filename="climate_disclosure.pdf",
            mime_type="application/pdf",
            supplier_id="US-SUPP-001",
            region="US",
            reporting_period="2024",
        )
        
        graph = create_audit_graph(use_sqlite_checkpoint=False)
        
        with patch.object(graph.graph, 'ainvoke') as mock_invoke:
            mock_invoke.return_value = AuditState(
                thread_id="test-us-sec",
                status=ProcessingStatus.COMPLIANT,
                document_metadata=us_metadata,
                compliance_result=ComplianceResult(
                    overall_decision=AgentDecision.APPROVE,
                    compliance_score=0.80,
                    findings=[],
                ),
            )
            
            result = await graph.run_audit(
                raw_content=sample_esg_document,
                metadata=us_metadata,
            )
            
            assert result.document_metadata.region == "US"


class TestErrorHandlingIntegration:
    """Tests for error handling across services."""
    
    @pytest.mark.asyncio
    async def test_vector_store_unavailable_graceful_degradation(
        self,
        sample_metadata,
        sample_esg_document,
    ):
        """Test graceful degradation when vector store is unavailable."""
        
        mock_vector_store = Mock()
        mock_vector_store.hybrid_search = AsyncMock(side_effect=Exception("Connection refused"))
        
        with patch("services.vectorstore.retriever.get_vector_store", return_value=mock_vector_store):
            retriever = RAGRetriever()
            
            context = await retriever.retrieve(
                query="test query",
                filters={},
                limit=5,
            )
            
            assert context.documents == []
            assert context.total_score == 0
    
    @pytest.mark.asyncio
    async def test_llm_rate_limiting_retry(
        self,
    ):
        """Test that LLM client retries on rate limiting."""
        
        mock_llm_client = LLMClient(
            api_key="test-key",
            model="gpt-4-turbo-preview",
            max_retries=3,
        )
        
        call_count = 0
        
        async def mock_complete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Rate limit exceeded")
            
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Success"
            mock_response.model = "gpt-4-turbo-preview"
            mock_response.usage = Mock(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )
            return mock_response
        
        with patch.object(mock_llm_client, '_get_async_client') as mock_get_client:
            mock_async_client = AsyncMock()
            mock_async_client.chat.completions.create = mock_complete
            mock_get_client.return_value = mock_async_client
            
            response = await mock_llm_client.complete(
                messages=[{"role": "user", "content": "test"}]
            )
            
            assert call_count == 3
