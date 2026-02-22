"""
Security API Service

FastAPI endpoints for preemptive cybersecurity operations.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.security import (
    HoneypotManager,
    PyRITRedTeamer,
    ThreatDetector,
)
from services.security.honeypot import HoneypotType, InteractionType
from services.security.redteam import RedTeamReport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_honeypot_manager: HoneypotManager | None = None
_red_teamer: PyRITRedTeamer | None = None
_threat_detector: ThreatDetector | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _honeypot_manager, _red_teamer, _threat_detector
    
    _honeypot_manager = HoneypotManager()
    
    _honeypot_manager.create_honeypot(HoneypotType.DATABASE)
    _honeypot_manager.create_honeypot(HoneypotType.ADMIN_PANEL)
    _honeypot_manager.create_honeypot(HoneypotType.FINANCIAL_DATA)
    _honeypot_manager.create_honeypot(HoneypotType.API_ENDPOINT)
    
    _red_teamer = PyRITRedTeamer(auto_mitigate=True)
    _threat_detector = ThreatDetector()
    
    logger.info("Security services initialized")
    yield


app = FastAPI(
    title="ESG Audit Security Service",
    version="1.0.0",
    description="Preemptive cybersecurity: Honeypot, Red Teaming, Threat Detection",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HoneypotInteractionRequest(BaseModel):
    honeypot_id: str
    interaction_type: str = Field(..., description="connection, authentication, data_access, etc.")
    source_ip: str
    source_port: int
    user_agent: Optional[str] = None
    request_data: Optional[str] = None


class HoneypotCreateRequest(BaseModel):
    honeypot_type: str = Field(..., description="database, api_endpoint, admin_panel, etc.")
    port: Optional[int] = None


class RedTeamRequest(BaseModel):
    attacks_per_strategy: int = Field(default=10, ge=1, le=100)


class ThreatEventRequest(BaseModel):
    event_type: str
    event_data: Dict[str, Any]


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok", "service": "security"}


# ==================== HONEYPOT ENDPOINTS ====================

@app.get("/api/honeypots")
async def list_honeypots():
    """List all active honeypots."""
    if _honeypot_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "honeypots": [
            {
                "id": hp_id,
                "type": hp.honeypot_type.value,
                "port": hp.port,
                "active": hp.active,
                "stats": hp.get_interaction_stats(),
            }
            for hp_id, hp in _honeypot_manager.honeypots.items()
        ]
    }


@app.post("/api/honeypots")
async def create_honeypot(request: HoneypotCreateRequest):
    """Create a new honeypot."""
    if _honeypot_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        hp_type = HoneypotType(request.honeypot_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid honeypot type. Valid types: {[t.value for t in HoneypotType]}"
        )
    
    honeypot = _honeypot_manager.create_honeypot(hp_type, request.port)
    
    return {
        "id": honeypot.honeypot_id,
        "type": honeypot.honeypot_type.value,
        "port": honeypot.port,
        "status": "created",
    }


@app.post("/api/honeypots/interact")
async def record_honeypot_interaction(request: HoneypotInteractionRequest):
    """Record an interaction with a honeypot (simulated or real)."""
    if _honeypot_manager is None or _threat_detector is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        interaction_type = InteractionType(request.interaction_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interaction type. Valid types: {[t.value for t in InteractionType]}"
        )
    
    interaction = _honeypot_manager.record_interaction(
        honeypot_id=request.honeypot_id,
        interaction_type=interaction_type,
        source_ip=request.source_ip,
        source_port=request.source_port,
        user_agent=request.user_agent,
        request_data=request.request_data,
    )
    
    if interaction:
        _threat_detector.analyze_event(
            event_type="honeypot",
            event_data={
                "source_ip": request.source_ip,
                "risk_score": interaction.risk_score,
                "threat_indicators": interaction.threat_indicators,
                "honeypot_type": interaction.honeypot_type.value,
            }
        )
    
    return {
        "interaction_id": interaction.interaction_id if interaction else None,
        "risk_score": interaction.risk_score if interaction else 0,
        "threat_indicators": interaction.threat_indicators if interaction else [],
    }


@app.get("/api/honeypots/threat-summary")
async def get_threat_summary():
    """Get threat summary from honeypots."""
    if _honeypot_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return _honeypot_manager.get_threat_summary()


@app.get("/api/honeypots/block-list")
async def get_block_list(threshold: float = 0.8):
    """Get list of IPs to block."""
    if _honeypot_manager is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "ips": _honeypot_manager.get_ips_to_block(threshold),
        "threshold": threshold,
    }


# ==================== RED TEAM ENDPOINTS ====================

@app.post("/api/redteam/run", response_model=RedTeamReport)
async def run_red_team_campaign(
    request: RedTeamRequest,
    background_tasks: BackgroundTasks,
):
    """Run a red team campaign against the system."""
    if _red_teamer is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    report = await _red_teamer.run_attack_campaign(
        attacks_per_strategy=request.attacks_per_strategy,
    )
    
    if _threat_detector:
        for result in _red_teamer.results[-10:]:
            _threat_detector.analyze_event(
                event_type="red_team",
                event_data={
                    "attack_type": result.attack_type.value,
                    "is_vulnerable": result.is_vulnerable,
                    "vulnerability_score": result.vulnerability_score,
                }
            )
    
    return report


@app.get("/api/redteam/metrics")
async def get_red_team_metrics():
    """Get red teaming metrics."""
    if _red_teamer is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return _red_teamer.get_metrics()


@app.get("/api/redteam/results")
async def get_red_team_results(limit: int = 50):
    """Get recent red team results."""
    if _red_teamer is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "results": [
            {
                "attack_id": r.attack_id,
                "attack_type": r.attack_type.value,
                "status": r.status.value,
                "is_vulnerable": r.is_vulnerable,
                "vulnerability_score": r.vulnerability_score,
                "timestamp": r.timestamp,
            }
            for r in _red_teamer.results[-limit:]
        ]
    }


# ==================== THREAT DETECTION ENDPOINTS ====================

@app.get("/api/threats/alerts")
async def get_threat_alerts(resolved: Optional[bool] = None):
    """Get threat alerts."""
    if _threat_detector is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if resolved is None:
        alerts = _threat_detector.alerts
    elif resolved:
        alerts = [a for a in _threat_detector.alerts if a.resolved]
    else:
        alerts = _threat_detector.get_active_alerts()
    
    return {
        "total": len(alerts),
        "alerts": _threat_detector.export_alerts()[:50],
    }


@app.post("/api/threats/analyze")
async def analyze_threat_event(request: ThreatEventRequest):
    """Analyze an event for threats."""
    if _threat_detector is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    alert = _threat_detector.analyze_event(
        event_type=request.event_type,
        event_data=request.event_data,
    )
    
    if alert:
        return {
            "threat_detected": True,
            "alert_id": alert.alert_id,
            "severity": alert.severity.value,
            "threat_type": alert.threat_type.value,
            "recommended_actions": alert.recommended_actions,
        }
    
    return {"threat_detected": False}


@app.get("/api/threats/metrics")
async def get_threat_metrics():
    """Get threat detection metrics."""
    if _threat_detector is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    metrics = _threat_detector.get_metrics()
    
    return {
        "total_alerts": metrics.total_alerts,
        "alerts_by_severity": metrics.alerts_by_severity,
        "alerts_by_type": metrics.alerts_by_type,
        "top_threat_sources": metrics.top_threat_sources,
        "threat_trend": metrics.threat_trend,
    }


@app.post("/api/threats/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Resolve a threat alert."""
    if _threat_detector is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    success = _threat_detector.resolve_alert(alert_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"status": "resolved", "alert_id": alert_id}


# ==================== SECURITY DASHBOARD ====================

@app.get("/api/security/dashboard")
async def get_security_dashboard():
    """Get comprehensive security dashboard data."""
    if any(x is None for x in [_honeypot_manager, _red_teamer, _threat_detector]):
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "honeypots": {
            "total": len(_honeypot_manager.honeypots),
            "threat_summary": _honeypot_manager.get_threat_summary(),
        },
        "red_team": _red_teamer.get_metrics(),
        "threats": {
            "active_alerts": len(_threat_detector.get_active_alerts()),
            "metrics": _threat_detector.get_metrics(),
        },
        "overall_risk_level": _calculate_overall_risk(),
    }


def _calculate_overall_risk() -> str:
    """Calculate overall system risk level."""
    if _threat_detector is None:
        return "unknown"
    
    active_alerts = len(_threat_detector.get_active_alerts())
    critical_count = sum(
        1 for a in _threat_detector.alerts
        if a.severity.value == "CRITICAL" and not a.resolved
    )
    
    if critical_count > 0:
        return "CRITICAL"
    elif active_alerts > 10:
        return "HIGH"
    elif active_alerts > 5:
        return "MEDIUM"
    elif active_alerts > 0:
        return "LOW"
    else:
        return "NORMAL"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8006")))
