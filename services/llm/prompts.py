"""
Prompt Templates

Structured prompts for ESG compliance analysis with GPT-4.
Designed for zero-shot analysis with structured outputs.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ComplianceAnalysisPrompt:
    """Prompt for comprehensive compliance analysis."""
    
    document_text: str
    regulations: List[str]
    metadata: Dict[str, Any]
    
    def build_system_prompt(self) -> str:
        return """You are an expert ESG (Environmental, Social, Governance) compliance analyst specializing in regulatory frameworks including CSRD (EU Corporate Sustainability Reporting Directive), SEC Climate Disclosure Rules, and related standards.

Your role is to:
1. Analyze documents for compliance with specified regulations
2. Extract and evaluate evidence from the text
3. Identify gaps between requirements and disclosures
4. Provide clear, actionable remediation guidance
5. Assess confidence levels objectively

ANALYSIS PRINCIPLES:
- Be conservative: if evidence is ambiguous, mark as REVIEW
- Distinguish between explicit disclosures and implied information
- Consider materiality and stakeholder relevance
- Cross-reference related regulatory requirements
- Provide specific text citations for evidence

SCORING GUIDELINES:
- APPROVE: Clear, sufficient evidence of compliance
- REVIEW: Partial evidence, needs clarification or additional disclosure
- REJECT: Missing required disclosure or explicit non-compliance

CONFIDENCE LEVELS:
- 0.9-1.0: Explicit, unambiguous evidence
- 0.7-0.9: Clear evidence with minor interpretation
- 0.5-0.7: Moderate evidence, some assumptions
- 0.3-0.5: Weak evidence, significant interpretation
- 0.0-0.3: No evidence or contradictory evidence"""

    def build_user_prompt(self) -> str:
        reg_list = "\n".join([f"- {r}" for r in self.regulations])
        
        metadata_str = ""
        if self.metadata:
            relevant_keys = ["supplier_id", "region", "reporting_period", "source_url"]
            meta_parts = [f"- {k}: {self.metadata[k]}" for k in relevant_keys if self.metadata.get(k)]
            if meta_parts:
                metadata_str = f"\nDocument Metadata:\n" + "\n".join(meta_parts)
        
        return f"""Analyze the following ESG document for compliance with these regulations:

REGULATIONS TO CHECK:
{reg_list}
{metadata_str}

DOCUMENT CONTENT:
---
{self.document_text[:12000]}
---

Provide a comprehensive compliance analysis with:
1. Individual findings for each regulation
2. Extracted evidence with exact text citations
3. Identified gaps and remediation suggestions
4. Overall compliance score and status
5. Executive summary for stakeholders

Focus on producing accurate, defensible assessments suitable for third-party audit review."""


@dataclass
class EvidenceExtractionPrompt:
    """Prompt for extracting specific evidence from a document."""
    
    document_text: str
    regulation_code: str
    requirement: str
    
    def build_system_prompt(self) -> str:
        return """You are a precise evidence extraction specialist for ESG compliance documents. Your task is to identify and extract exact text segments that are relevant to specific regulatory requirements.

EXTRACTION RULES:
1. Only extract text that directly relates to the requirement
2. Preserve the exact wording (do not paraphrase)
3. Note the approximate location (page, section, paragraph)
4. Assess relevance objectively (0.0-1.0 scale)
5. Provide brief interpretation of how evidence relates to requirement

If no relevant evidence exists, return an empty evidence list with explanation."""

    def build_user_prompt(self) -> str:
        return f"""Extract evidence from the following document for this requirement:

REGULATION CODE: {self.regulation_code}
REQUIREMENT: {self.requirement}

DOCUMENT CONTENT:
---
{self.document_text[:8000]}
---

Find and extract all relevant text segments that address or relate to this requirement.
For each piece of evidence, provide the exact text, location, relevance score, and interpretation."""


@dataclass
class ReportGenerationPrompt:
    """Prompt for generating audit reports."""
    
    compliance_findings: List[Dict[str, Any]]
    document_metadata: Dict[str, Any]
    audit_trail: List[Dict[str, Any]]
    
    def build_system_prompt(self) -> str:
        return """You are an ESG audit report writer. Generate clear, professional audit reports that:
1. Summarize compliance status for executive stakeholders
2. Detail findings with evidence citations
3. Provide actionable recommendations prioritized by severity
4. Maintain audit-ready documentation standards
5. Use precise, objective language

REPORT STRUCTURE:
- Executive Summary (2-3 sentences)
- Compliance Overview (score, status, key metrics)
- Detailed Findings (by regulation)
- Recommendations (prioritized)
- Appendices (evidence, methodology)"""

    def build_user_prompt(self) -> str:
        findings_str = "\n".join([
            f"- {f.get('regulation_code')}: {f.get('status')} ({f.get('severity')})"
            for f in self.compliance_findings[:15]
        ])
        
        return f"""Generate an audit report based on the following analysis:

COMPLIANCE FINDINGS:
{findings_str}

DOCUMENT INFO:
- Source: {self.document_metadata.get('source_url', 'N/A')}
- Supplier: {self.document_metadata.get('supplier_id', 'N/A')}
- Region: {self.document_metadata.get('region', 'N/A')}
- Period: {self.document_metadata.get('reporting_period', 'N/A')}

AUDIT TRAIL SUMMARY:
{len(self.audit_trail)} processing steps recorded

Generate a comprehensive audit report suitable for stakeholder presentation."""


@dataclass 
class GapAnalysisPrompt:
    """Prompt for identifying compliance gaps."""
    
    document_text: str
    regulation_requirements: Dict[str, List[str]]
    
    def build_system_prompt(self) -> str:
        return """You are a compliance gap analyst. Identify specific gaps between regulatory requirements and document disclosures.

GAP ANALYSIS APPROACH:
1. Map each requirement to document content
2. Identify partial vs complete disclosures
3. Flag missing required elements
4. Assess materiality of each gap
5. Prioritize by regulatory risk

OUTPUT FORMAT:
For each gap, provide:
- Regulation code
- Missing requirement
- Materiality assessment
- Remediation urgency
- Suggested disclosure language"""

    def build_user_prompt(self) -> str:
        req_list = []
        for code, requirements in self.regulation_requirements.items():
            req_list.append(f"\n{code}:")
            req_list.extend([f"  - {r}" for r in requirements[:5]])
        
        requirements_str = "\n".join(req_list)
        
        return f"""Analyze the document for compliance gaps:

REQUIRED DISCLOSURES:
{requirements_str}

DOCUMENT CONTENT:
---
{self.document_text[:10000]}
---

Identify all gaps between requirements and actual disclosures. Prioritize by regulatory importance and materiality."""
