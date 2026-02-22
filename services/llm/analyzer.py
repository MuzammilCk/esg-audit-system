"""
LLM-Enhanced Compliance Analyzer

Integrates GPT-4 with the rule-based compliance checker for deeper analysis.
Provides intelligent reasoning and evidence extraction.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from services.llm.client import LLMClient, get_llm_client
from services.llm.prompts import (
    ComplianceAnalysisPrompt,
    EvidenceExtractionPrompt,
    GapAnalysisPrompt,
)
from services.llm.structured_output import (
    ComplianceAnalysisOutput,
    FindingOutput,
    FindingStatus,
    Severity,
)
from services.agents.state import ComplianceFinding, AgentDecision

logger = logging.getLogger(__name__)


class LLMComplianceAnalyzer:
    """
    LLM-enhanced compliance analyzer using GPT-4.
    
    Features:
    - Deep semantic analysis of ESG documents
    - Evidence extraction with citations
    - Gap identification
    - Remediation suggestions
    - Fallback to rule-based analysis
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        fallback_to_rules: bool = True,
        max_text_length: int = 12000,
    ):
        self._llm_client = llm_client
        self.fallback_to_rules = fallback_to_rules
        self.max_text_length = max_text_length
    
    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client
    
    async def analyze_compliance(
        self,
        text: str,
        regulations: List[str],
        metadata: Dict[str, Any],
    ) -> List[ComplianceFinding]:
        """
        Perform LLM-enhanced compliance analysis.
        
        Args:
            text: Document text to analyze
            regulations: List of regulation codes to check
            metadata: Document metadata
        
        Returns:
            List of ComplianceFinding objects
        """
        if not text or not text.strip():
            return []
        
        text = text[:self.max_text_length]
        
        try:
            llm_output = await self._run_llm_analysis(text, regulations, metadata)
            
            findings = self._convert_llm_output_to_findings(llm_output)
            
            logger.info(f"LLM analysis completed with {len(findings)} findings")
            return findings
            
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}")
            
            if self.fallback_to_rules:
                logger.info("Falling back to rule-based analysis")
                return await self._fallback_analysis(text, regulations, metadata)
            
            raise
    
    async def _run_llm_analysis(
        self,
        text: str,
        regulations: List[str],
        metadata: Dict[str, Any],
    ) -> ComplianceAnalysisOutput:
        """Run the LLM compliance analysis."""
        
        prompt = ComplianceAnalysisPrompt(
            document_text=text,
            regulations=regulations,
            metadata=metadata,
        )
        
        messages = [
            {"role": "system", "content": prompt.build_system_prompt()},
            {"role": "user", "content": prompt.build_user_prompt()},
        ]
        
        response = await self.llm_client.complete_structured(
            messages=messages,
            response_model=ComplianceAnalysisOutput,
            temperature=0.0,
        )
        
        return response.parsed
    
    async def extract_evidence(
        self,
        text: str,
        regulation_code: str,
        requirement: str,
    ) -> Dict[str, Any]:
        """
        Extract specific evidence for a regulation requirement.
        
        Args:
            text: Document text
            regulation_code: E.g., "ESRS E1"
            requirement: Specific requirement text
        
        Returns:
            Dict with extracted evidence
        """
        try:
            prompt = EvidenceExtractionPrompt(
                document_text=text[:8000],
                regulation_code=regulation_code,
                requirement=requirement,
            )
            
            messages = [
                {"role": "system", "content": prompt.build_system_prompt()},
                {"role": "user", "content": prompt.build_user_prompt()},
            ]
            
            response = await self.llm_client.complete(
                messages=messages,
                temperature=0.0,
            )
            
            return {
                "evidence_text": response.content,
                "tokens_used": response.tokens_total,
            }
            
        except Exception as e:
            logger.error(f"Evidence extraction failed: {e}")
            return {"evidence_text": "", "error": str(e)}
    
    async def analyze_gaps(
        self,
        text: str,
        regulation_requirements: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """
        Perform gap analysis between requirements and disclosures.
        
        Args:
            text: Document text
            regulation_requirements: Dict of regulation_code -> requirements
        
        Returns:
            Gap analysis results
        """
        try:
            prompt = GapAnalysisPrompt(
                document_text=text[:10000],
                regulation_requirements=regulation_requirements,
            )
            
            messages = [
                {"role": "system", "content": prompt.build_system_prompt()},
                {"role": "user", "content": prompt.build_user_prompt()},
            ]
            
            response = await self.llm_client.complete(
                messages=messages,
                temperature=0.0,
            )
            
            return {
                "gap_analysis": response.content,
                "tokens_used": response.tokens_total,
            }
            
        except Exception as e:
            logger.error(f"Gap analysis failed: {e}")
            return {"gap_analysis": "", "error": str(e)}
    
    def _convert_llm_output_to_findings(
        self,
        output: ComplianceAnalysisOutput,
    ) -> List[ComplianceFinding]:
        """Convert LLM structured output to ComplianceFinding objects."""
        findings = []
        
        for finding_output in output.findings:
            status = self._map_status(finding_output.status)
            severity = finding_output.severity.value if isinstance(finding_output.severity, Severity) else finding_output.severity
            
            evidence_text = ""
            if finding_output.evidence:
                evidence_parts = [e.text_segment for e in finding_output.evidence[:3]]
                evidence_text = " | ".join(evidence_parts[:500])
            else:
                evidence_text = finding_output.requirement
            
            finding = ComplianceFinding(
                regulation_code=finding_output.regulation_code,
                regulation_name=finding_output.regulation_name,
                requirement=finding_output.requirement,
                status=status,
                evidence=evidence_text,
                confidence=finding_output.confidence,
                remediation=finding_output.remediation,
                severity=severity,
            )
            
            findings.append(finding)
        
        return findings
    
    def _map_status(self, status: FindingStatus) -> AgentDecision:
        """Map LLM status to agent decision."""
        mapping = {
            FindingStatus.APPROVE: AgentDecision.APPROVE,
            FindingStatus.REJECT: AgentDecision.REJECT,
            FindingStatus.REVIEW: AgentDecision.REVIEW,
        }
        return mapping.get(status, AgentDecision.REVIEW)
    
    async def _fallback_analysis(
        self,
        text: str,
        regulations: List[str],
        metadata: Dict[str, Any],
    ) -> List[ComplianceFinding]:
        """Fallback to rule-based analysis when LLM fails."""
        from services.agents.tools.compliance_checker import ComplianceChecker
        
        checker = ComplianceChecker(frameworks=regulations)
        return await checker.analyze_compliance(text, metadata)


_llm_analyzer: LLMComplianceAnalyzer | None = None


def get_llm_analyzer() -> LLMComplianceAnalyzer:
    """Get or create the global LLM analyzer instance."""
    global _llm_analyzer
    
    if _llm_analyzer is None:
        _llm_analyzer = LLMComplianceAnalyzer()
    
    return _llm_analyzer
