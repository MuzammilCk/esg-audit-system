"""
Compliance Checker Tool

Analyzes ESG documents against regulatory frameworks.
Supports hybrid analysis: LLM-enhanced with rule-based fallback.
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

from services.agents.state import ComplianceFinding, AgentDecision

logger = logging.getLogger(__name__)

_USE_LLM = os.getenv("USE_LLM_ANALYSIS", "true").lower() == "true"


class RegulationFramework(ABC):
    """Abstract base class for regulation frameworks."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def regulations(self) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def check(self, text: str, metadata: Dict[str, Any]) -> List[ComplianceFinding]:
        pass


class CSRDFramework(RegulationFramework):
    """Corporate Sustainability Reporting Directive (EU) compliance checker."""
    
    @property
    def name(self) -> str:
        return "CSRD"
    
    @property
    def regulations(self) -> List[Dict[str, Any]]:
        return [
            {
                "code": "ESRS E1",
                "name": "Climate Change",
                "requirements": [
                    "GHG emissions disclosure (Scope 1, 2, 3)",
                    "Climate transition plan",
                    "Climate-related risks and opportunities",
                    "Energy consumption and mix",
                ],
                "keywords": [
                    "ghg", "emissions", "scope 1", "scope 2", "scope 3",
                    "carbon", "climate", "greenhouse gas", "co2", "net zero",
                    "transition plan", "energy consumption", "renewable"
                ],
            },
            {
                "code": "ESRS E2",
                "name": "Pollution",
                "requirements": [
                    "Pollution of air, water, and soil",
                    "Substances of concern",
                    "Pollution prevention and control",
                ],
                "keywords": [
                    "pollution", "air quality", "water quality", "soil",
                    "hazardous", "toxic", "waste", "emissions", "effluents"
                ],
            },
            {
                "code": "ESRS E3",
                "name": "Water and Marine Resources",
                "requirements": [
                    "Water consumption",
                    "Water-related impacts",
                    "Marine resources",
                ],
                "keywords": [
                    "water consumption", "water usage", "marine", "ocean",
                    "aquifer", "water stress", "water withdrawal"
                ],
            },
            {
                "code": "ESRS E4",
                "name": "Biodiversity and Ecosystems",
                "requirements": [
                    "Biodiversity impacts",
                    "Ecosystem services",
                    "Deforestation",
                ],
                "keywords": [
                    "biodiversity", "ecosystem", "species", "habitat",
                    "deforestation", "nature", "wildlife", "conservation"
                ],
            },
            {
                "code": "ESRS E5",
                "name": "Resource Use and Circular Economy",
                "requirements": [
                    "Resource efficiency",
                    "Waste management",
                    "Circular economy practices",
                ],
                "keywords": [
                    "circular economy", "recycling", "waste reduction",
                    "resource efficiency", "material", "reuse", "upcycle"
                ],
            },
            {
                "code": "ESRS S1",
                "name": "Own Workforce",
                "requirements": [
                    "Working conditions",
                    "Equal treatment",
                    "Health and safety",
                ],
                "keywords": [
                    "employee", "workforce", "health and safety", "diversity",
                    "inclusion", "training", "compensation", "working conditions"
                ],
            },
            {
                "code": "ESRS G1",
                "name": "Governance",
                "requirements": [
                    "Corporate governance",
                    "Business conduct",
                    "Anti-corruption",
                ],
                "keywords": [
                    "governance", "board", "ethics", "corruption", "bribery",
                    "compliance", "transparency", "whistleblower"
                ],
            },
        ]
    
    async def check(self, text: str, metadata: Dict[str, Any]) -> List[ComplianceFinding]:
        findings: List[ComplianceFinding] = []
        text_lower = text.lower()
        
        for reg in self.regulations:
            keyword_matches = 0
            matched_keywords = []
            
            for keyword in reg["keywords"]:
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                matches = re.findall(pattern, text_lower)
                if matches:
                    keyword_matches += len(matches)
                    matched_keywords.append(keyword)
            
            coverage = len(matched_keywords) / len(reg["keywords"]) if reg["keywords"] else 0
            
            if coverage >= 0.5:
                status = AgentDecision.APPROVE
                severity = "LOW"
                confidence = min(0.95, 0.6 + coverage * 0.35)
                remediation = None
            elif coverage >= 0.25:
                status = AgentDecision.REVIEW
                severity = "MEDIUM"
                confidence = 0.5 + coverage * 0.3
                remediation = f"Consider expanding disclosure on {reg['name']}"
            else:
                status = AgentDecision.REJECT
                severity = "HIGH"
                confidence = 0.4 + coverage * 0.3
                remediation = f"Missing required disclosures for {reg['name']} ({reg['code']})"
            
            evidence = f"Found {keyword_matches} keyword matches across {len(matched_keywords)}/{len(reg['keywords'])} relevant areas"
            
            findings.append(ComplianceFinding(
                regulation_code=reg["code"],
                regulation_name=reg["name"],
                requirement=", ".join(reg["requirements"][:2]),
                status=status,
                evidence=evidence,
                confidence=confidence,
                remediation=remediation,
                severity=severity,
            ))
        
        return findings


class SECFramework(RegulationFramework):
    """SEC Climate Disclosure Rules (US) compliance checker."""
    
    @property
    def name(self) -> str:
        return "SEC"
    
    @property
    def regulations(self) -> List[Dict[str, Any]]:
        return [
            {
                "code": "SEC-GHG",
                "name": "Greenhouse Gas Emissions",
                "requirements": [
                    "Scope 1 and Scope 2 emissions",
                    "Emission calculation methodology",
                    "Third-party assurance for material emissions",
                ],
                "keywords": [
                    "scope 1", "scope 2", "ghg", "emissions", "carbon footprint",
                    "methodology", "verification", "assurance"
                ],
            },
            {
                "code": "SEC-CLIMATE-RISK",
                "name": "Climate-Related Risks",
                "requirements": [
                    "Physical risks identification",
                    "Transition risks identification",
                    "Risk mitigation strategies",
                ],
                "keywords": [
                    "physical risk", "transition risk", "climate risk",
                    "mitigation", "adaptation", "scenario analysis"
                ],
            },
            {
                "code": "SEC-GOVERNANCE",
                "name": "Climate Governance",
                "requirements": [
                    "Board oversight of climate risks",
                    "Management role in climate assessment",
                ],
                "keywords": [
                    "board oversight", "climate governance", "risk management",
                    "climate committee", "esg committee"
                ],
            },
            {
                "code": "SEC-TARGETS",
                "name": "Climate Targets and Goals",
                "requirements": [
                    "Emission reduction targets",
                    "Net-zero commitments",
                    "Progress tracking",
                ],
                "keywords": [
                    "target", "net zero", "reduction goal", "science-based target",
                    "sbti", "carbon neutral", "decarbonization"
                ],
            },
        ]
    
    async def check(self, text: str, metadata: Dict[str, Any]) -> List[ComplianceFinding]:
        findings: List[ComplianceFinding] = []
        text_lower = text.lower()
        
        for reg in self.regulations:
            keyword_matches = 0
            matched_keywords = []
            
            for keyword in reg["keywords"]:
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                matches = re.findall(pattern, text_lower)
                if matches:
                    keyword_matches += len(matches)
                    matched_keywords.append(keyword)
            
            coverage = len(matched_keywords) / len(reg["keywords"]) if reg["keywords"] else 0
            
            if coverage >= 0.5:
                status = AgentDecision.APPROVE
                severity = "LOW"
                confidence = min(0.95, 0.6 + coverage * 0.35)
                remediation = None
            elif coverage >= 0.25:
                status = AgentDecision.REVIEW
                severity = "MEDIUM"
                confidence = 0.5 + coverage * 0.3
                remediation = f"Enhance disclosure for {reg['name']}"
            else:
                status = AgentDecision.REJECT
                severity = "HIGH"
                confidence = 0.4 + coverage * 0.3
                remediation = f"Missing required disclosure: {reg['name']} ({reg['code']})"
            
            evidence = f"Keyword coverage: {coverage:.0%} ({len(matched_keywords)}/{len(reg['keywords'])} areas)"
            
            findings.append(ComplianceFinding(
                regulation_code=reg["code"],
                regulation_name=reg["name"],
                requirement=", ".join(reg["requirements"][:2]),
                status=status,
                evidence=evidence,
                confidence=confidence,
                remediation=remediation,
                severity=severity,
            ))
        
        return findings


class ComplianceChecker:
    """
    Main compliance checker that orchestrates multiple regulatory frameworks.
    
    Supports hybrid analysis:
    - LLM-enhanced: Uses GPT-4 for deep semantic analysis
    - Rule-based: Keyword matching with coverage scoring
    """
    
    def __init__(
        self,
        frameworks: Optional[List[str]] = None,
        use_llm: Optional[bool] = None,
    ):
        self.frameworks: List[RegulationFramework] = []
        self.use_llm = use_llm if use_llm is not None else _USE_LLM
        self._llm_analyzer = None
        
        available = {
            "CSRD": CSRDFramework,
            "SEC": SECFramework,
        }
        
        if frameworks:
            for fw in frameworks:
                if fw.upper() in available:
                    self.frameworks.append(available[fw.upper()]())
        else:
            self.frameworks = [CSRDFramework(), SECFramework()]
        
        self._regulations_checked: List[str] = []
    
    def get_regulations_checked(self) -> List[str]:
        return self._regulations_checked
    
    def _get_llm_analyzer(self):
        """Lazy-load the LLM analyzer."""
        if self._llm_analyzer is None and self.use_llm:
            try:
                from services.llm import get_llm_analyzer
                self._llm_analyzer = get_llm_analyzer()
            except Exception as e:
                logger.warning(f"Could not load LLM analyzer: {e}")
                self._llm_analyzer = None
        return self._llm_analyzer
    
    async def analyze_compliance(
        self,
        text: str,
        metadata: Dict[str, Any],
    ) -> List[ComplianceFinding]:
        """
        Analyze document text against all configured regulatory frameworks.
        
        Uses LLM-enhanced analysis if available, falls back to rule-based.
        """
        all_findings: List[ComplianceFinding] = []
        self._regulations_checked = []
        
        llm_analyzer = self._get_llm_analyzer()
        
        if llm_analyzer and self.use_llm:
            try:
                logger.info("Running LLM-enhanced compliance analysis")
                
                regulation_codes = []
                for framework in self.frameworks:
                    regulation_codes.extend([r["code"] for r in framework.regulations])
                
                all_findings = await llm_analyzer.analyze_compliance(
                    text=text,
                    regulations=regulation_codes,
                    metadata=metadata,
                )
                
                for framework in self.frameworks:
                    self._regulations_checked.extend([
                        f"{framework.name}: {r['code']}" 
                        for r in framework.regulations
                    ])
                
                return all_findings
                
            except Exception as e:
                logger.warning(f"LLM analysis failed, falling back to rules: {e}")
        
        logger.info("Running rule-based compliance analysis")
        
        for framework in self.frameworks:
            logger.info(f"Running compliance check: {framework.name}")
            findings = await framework.check(text, metadata)
            all_findings.extend(findings)
            self._regulations_checked.extend([
                f"{framework.name}: {r['code']}" 
                for r in framework.regulations
            ])
        
        return all_findings
