"""
Honeypot Agent

Implements deceptive decoy systems to detect, track, and analyze
threat actors targeting the ESG audit infrastructure.

Based on the "Deceive" principle of preemptive cybersecurity.
"""

import os
import json
import logging
import hashlib
import secrets
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class HoneypotType(str, Enum):
    DATABASE = "database"
    API_ENDPOINT = "api_endpoint"
    FILE_SERVER = "file_server"
    ADMIN_PANEL = "admin_panel"
    FINANCIAL_DATA = "financial_data"
    SUPPLIER_PORTAL = "supplier_portal"


class InteractionType(str, Enum):
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    DATA_ACCESS = "data_access"
    FILE_DOWNLOAD = "file_download"
    API_CALL = "api_call"
    INJECTION_ATTEMPT = "injection_attempt"


@dataclass
class HoneypotInteraction:
    """Record of an interaction with a honeypot."""
    interaction_id: str
    honeypot_id: str
    honeypot_type: HoneypotType
    interaction_type: InteractionType
    timestamp: str
    source_ip: str
    source_port: int
    user_agent: Optional[str] = None
    request_data: Optional[str] = None
    response_given: Optional[str] = None
    threat_indicators: List[str] = field(default_factory=list)
    risk_score: float = 0.0
    fingerprint_hash: Optional[str] = None


@dataclass
class ThreatProfile:
    """Profile built from honeypot interactions."""
    source_ip: str
    first_seen: str
    last_seen: str
    total_interactions: int
    honeypots_triggered: List[str]
    techniques_used: List[str]
    risk_score: float
    is_known_threat: bool
    threat_intelligence_match: Optional[str] = None
    recommended_action: str = "monitor"


class HoneypotAgent:
    """
    Individual honeypot decoy.
    
    Simulates a vulnerable system component to attract and
    analyze potential attackers.
    """
    
    def __init__(
        self,
        honeypot_id: str,
        honeypot_type: HoneypotType,
        port: int,
        fake_data: Optional[Dict[str, Any]] = None,
    ):
        self.honeypot_id = honeypot_id
        self.honeypot_type = honeypot_type
        self.port = port
        self.fake_data = fake_data or self._generate_fake_data()
        self.interactions: List[HoneypotInteraction] = []
        self.active = True
        self._credentials = self._generate_fake_credentials()
    
    def _generate_fake_data(self) -> Dict[str, Any]:
        """Generate realistic-looking fake data for the honeypot."""
        if self.honeypot_type == HoneypotType.DATABASE:
            return {
                "tables": ["suppliers", "emissions_data", "financial_records", "compliance_docs"],
                "fake_records": 15000,
                "last_backup": datetime.now(timezone.utc).isoformat(),
            }
        elif self.honeypot_type == HoneypotType.FINANCIAL_DATA:
            return {
                "quarterly_reports": ["Q1_2024.pdf", "Q2_2024.pdf"],
                "revenue_data": {"amount": "CONFIDENTIAL"},
                "audit_status": "pending_review",
            }
        elif self.honeypot_type == HoneypotType.ADMIN_PANEL:
            return {
                "admin_users": 5,
                "pending_approvals": 12,
                "system_status": "operational",
                "last_login": datetime.now(timezone.utc).isoformat(),
            }
        elif self.honeypot_type == HoneypotType.SUPPLIER_PORTAL:
            return {
                "active_suppliers": 250,
                "pending_documents": 45,
                "compliance_rate": "87%",
            }
        else:
            return {"data": "sensitive", "access": "restricted"}
    
    def _generate_fake_credentials(self) -> Dict[str, str]:
        """Generate fake credentials that trigger alerts when used."""
        return {
            "admin": secrets.token_urlsafe(16),
            "esg_auditor": secrets.token_urlsafe(16),
            "api_service": secrets.token_urlsafe(16),
        }
    
    def record_interaction(
        self,
        interaction_type: InteractionType,
        source_ip: str,
        source_port: int,
        request_data: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> HoneypotInteraction:
        """
        Record an interaction with the honeypot.
        
        Returns the interaction record for further analysis.
        """
        interaction_id = secrets.token_urlsafe(16)
        
        threat_indicators = self._analyze_for_threats(
            interaction_type, request_data
        )
        
        risk_score = self._calculate_risk_score(
            interaction_type, threat_indicators
        )
        
        response_given = self._generate_deceptive_response(interaction_type)
        
        fingerprint = self._generate_fingerprint(source_ip, user_agent, request_data)
        
        interaction = HoneypotInteraction(
            interaction_id=interaction_id,
            honeypot_id=self.honeypot_id,
            honeypot_type=self.honeypot_type,
            interaction_type=interaction_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_ip=source_ip,
            source_port=source_port,
            user_agent=user_agent,
            request_data=request_data[:500] if request_data else None,
            response_given=response_given,
            threat_indicators=threat_indicators,
            risk_score=risk_score,
            fingerprint_hash=fingerprint,
        )
        
        self.interactions.append(interaction)
        
        logger.warning(
            f"[HONEYPOT] Interaction recorded on {self.honeypot_type.value} "
            f"from {source_ip} - Risk: {risk_score:.2f}"
        )
        
        return interaction
    
    def _analyze_for_threats(
        self,
        interaction_type: InteractionType,
        request_data: Optional[str],
    ) -> List[str]:
        """Analyze interaction for threat indicators."""
        indicators = []
        
        if request_data:
            request_lower = request_data.lower()
            
            sqli_patterns = ["'", "or 1=1", "union select", "--", "; drop", "exec("]
            for pattern in sqli_patterns:
                if pattern in request_lower:
                    indicators.append(f"SQL_INJECTION_ATTEMPT:{pattern}")
            
            xss_patterns = ["<script", "javascript:", "onerror=", "onload="]
            for pattern in xss_patterns:
                if pattern in request_lower:
                    indicators.append(f"XSS_ATTEMPT:{pattern}")
            
            path_patterns = ["../", "..\\", "/etc/passwd", "/etc/shadow", "c:\\windows"]
            for pattern in path_patterns:
                if pattern in request_lower:
                    indicators.append(f"PATH_TRAVERSAL:{pattern}")
            
            cmd_patterns = ["; rm", "| cat", "& whoami", "`id`", "$(cat"]
            for pattern in cmd_patterns:
                if pattern in request_lower:
                    indicators.append(f"COMMAND_INJECTION:{pattern}")
        
        if interaction_type == InteractionType.AUTHENTICATION:
            indicators.append("CREDENTIAL_STUFFING_ATTEMPT")
        
        return indicators
    
    def _calculate_risk_score(
        self,
        interaction_type: InteractionType,
        threat_indicators: List[str],
    ) -> float:
        """Calculate risk score for the interaction."""
        base_scores = {
            InteractionType.CONNECTION: 0.1,
            InteractionType.AUTHENTICATION: 0.3,
            InteractionType.DATA_ACCESS: 0.5,
            InteractionType.FILE_DOWNLOAD: 0.6,
            InteractionType.API_CALL: 0.3,
            InteractionType.INJECTION_ATTEMPT: 0.9,
        }
        
        score = base_scores.get(interaction_type, 0.2)
        
        for indicator in threat_indicators:
            if "INJECTION" in indicator:
                score += 0.2
            elif "TRAVERSAL" in indicator:
                score += 0.25
            elif "STUFFING" in indicator:
                score += 0.15
        
        return min(1.0, score)
    
    def _generate_deceptive_response(
        self,
        interaction_type: InteractionType,
    ) -> str:
        """Generate a realistic but fake response to delay attackers."""
        if interaction_type == InteractionType.AUTHENTICATION:
            return json.dumps({
                "status": "pending",
                "message": "Verifying credentials...",
                "mfa_required": True,
                "delay": "30s",
            })
        elif interaction_type == InteractionType.DATA_ACCESS:
            return json.dumps({
                "status": "error",
                "message": "Database connection timeout",
                "retry_after": 60,
            })
        else:
            return json.dumps({
                "status": "processing",
                "request_id": secrets.token_urlsafe(8),
            })
    
    def _generate_fingerprint(
        self,
        source_ip: str,
        user_agent: Optional[str],
        request_data: Optional[str],
    ) -> str:
        """Generate a fingerprint hash for tracking attackers."""
        fingerprint_data = f"{source_ip}:{user_agent or ''}:{request_data[:100] if request_data else ''}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
    
    def get_interaction_stats(self) -> Dict[str, Any]:
        """Get statistics about interactions with this honeypot."""
        if not self.interactions:
            return {"total": 0}
        
        return {
            "total": len(self.interactions),
            "unique_ips": len(set(i.source_ip for i in self.interactions)),
            "avg_risk_score": sum(i.risk_score for i in self.interactions) / len(self.interactions),
            "threat_types": list(set(
                indicator.split(":")[0]
                for i in self.interactions
                for indicator in i.threat_indicators
            )),
            "last_interaction": self.interactions[-1].timestamp if self.interactions else None,
        }


class HoneypotManager:
    """
    Manages multiple honeypot agents and correlates threat data.
    
    Implements centralized monitoring and alerting.
    """
    
    def __init__(self):
        self.honeypots: Dict[str, HoneypotAgent] = {}
        self.threat_profiles: Dict[str, ThreatProfile] = {}
        self.alerts: List[Dict[str, Any]] = []
    
    def create_honeypot(
        self,
        honeypot_type: HoneypotType,
        port: Optional[int] = None,
    ) -> HoneypotAgent:
        """Create and register a new honeypot."""
        honeypot_id = f"hp_{honeypot_type.value}_{secrets.token_urlsafe(4)}"
        
        default_ports = {
            HoneypotType.DATABASE: 5432,
            HoneypotType.API_ENDPOINT: 8080,
            HoneypotType.FILE_SERVER: 21,
            HoneypotType.ADMIN_PANEL: 443,
            HoneypotType.FINANCIAL_DATA: 3306,
            HoneypotType.SUPPLIER_PORTAL: 8443,
        }
        
        port = port or default_ports.get(honeypot_type, 8080)
        
        honeypot = HoneypotAgent(
            honeypot_id=honeypot_id,
            honeypot_type=honeypot_type,
            port=port,
        )
        
        self.honeypots[honeypot_id] = honeypot
        
        logger.info(f"[HONEYPOT] Created {honeypot_type.value} on port {port}")
        
        return honeypot
    
    def record_interaction(
        self,
        honeypot_id: str,
        interaction_type: InteractionType,
        source_ip: str,
        source_port: int,
        **kwargs,
    ) -> Optional[HoneypotInteraction]:
        """Record an interaction and update threat profiles."""
        honeypot = self.honeypots.get(honeypot_id)
        if not honeypot:
            logger.error(f"Unknown honeypot: {honeypot_id}")
            return None
        
        interaction = honeypot.record_interaction(
            interaction_type=interaction_type,
            source_ip=source_ip,
            source_port=source_port,
            **kwargs,
        )
        
        self._update_threat_profile(interaction)
        
        if interaction.risk_score >= 0.7:
            self._generate_alert(interaction)
        
        return interaction
    
    def _update_threat_profile(self, interaction: HoneypotInteraction) -> None:
        """Update or create threat profile for the source IP."""
        ip = interaction.source_ip
        
        if ip not in self.threat_profiles:
            self.threat_profiles[ip] = ThreatProfile(
                source_ip=ip,
                first_seen=interaction.timestamp,
                last_seen=interaction.timestamp,
                total_interactions=1,
                honeypots_triggered=[interaction.honeypot_id],
                techniques_used=interaction.threat_indicators,
                risk_score=interaction.risk_score,
                is_known_threat=False,
            )
        else:
            profile = self.threat_profiles[ip]
            profile.last_seen = interaction.timestamp
            profile.total_interactions += 1
            
            if interaction.honeypot_id not in profile.honeypots_triggered:
                profile.honeypots_triggered.append(interaction.honeypot_id)
            
            for indicator in interaction.threat_indicators:
                if indicator not in profile.techniques_used:
                    profile.techniques_used.append(indicator)
            
            profile.risk_score = min(1.0, profile.risk_score + interaction.risk_score * 0.1)
            
            if profile.risk_score >= 0.8:
                profile.is_known_threat = True
                profile.recommended_action = "block"
    
    def _generate_alert(self, interaction: HoneypotInteraction) -> None:
        """Generate a security alert for high-risk interactions."""
        alert = {
            "alert_id": secrets.token_urlsafe(8),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "HIGH" if interaction.risk_score >= 0.9 else "MEDIUM",
            "source_ip": interaction.source_ip,
            "honeypot_type": interaction.honeypot_type.value,
            "threat_indicators": interaction.threat_indicators,
            "risk_score": interaction.risk_score,
            "fingerprint": interaction.fingerprint_hash,
            "recommended_action": "investigate_and_block",
        }
        
        self.alerts.append(alert)
        
        logger.critical(
            f"[SECURITY ALERT] High-risk interaction from {interaction.source_ip} "
            f"- Indicators: {interaction.threat_indicators}"
        )
    
    def get_threat_summary(self) -> Dict[str, Any]:
        """Get overall threat summary."""
        return {
            "total_honeypots": len(self.honeypots),
            "total_interactions": sum(
                len(h.interactions) for h in self.honeypots.values()
            ),
            "unique_threat_actors": len(self.threat_profiles),
            "known_threats": sum(
                1 for p in self.threat_profiles.values() if p.is_known_threat
            ),
            "active_alerts": len([a for a in self.alerts if a["severity"] == "HIGH"]),
            "top_threat_ips": sorted(
                self.threat_profiles.values(),
                key=lambda p: p.risk_score,
                reverse=True,
            )[:5],
        }
    
    def get_ips_to_block(self, threshold: float = 0.8) -> List[str]:
        """Get list of IPs that should be blocked."""
        return [
            ip for ip, profile in self.threat_profiles.items()
            if profile.risk_score >= threshold
        ]
