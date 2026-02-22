"""
Parent Proxy Application

Runs on the parent EC2 instance and proxies API requests
to the enclave through vsock.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ENCLAVE_PORT = int(os.getenv("ENCLAVE_PORT", "5005"))
PARENT_PORT = int(os.getenv("PARENT_PORT", "8005"))

app = FastAPI(
    title="ESG Audit Parent Proxy",
    description="Proxies requests to Nitro Enclave for secure processing",
)


class EnclaveAuditRequest(BaseModel):
    content: str
    source_url: str = ""
    original_filename: str = ""
    mime_type: str = "text/plain"
    supplier_id: Optional[str] = None
    region: Optional[str] = None
    reporting_period: Optional[str] = None


class EnclaveAuditResponse(BaseModel):
    status: str
    thread_id: Optional[str] = None
    compliance_score: Optional[float] = None
    overall_decision: Optional[str] = None
    findings_count: Optional[int] = None
    timestamp: str
    enclave_processed: bool = True


def send_to_enclave(request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Send request to enclave via vsock."""
    try:
        import socket
        
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        
        VMADDR_CID_ANY = 0xFFFFFFFF
        sock.connect((VMADDR_CID_ANY, ENCLAVE_PORT))
        
        message = json.dumps({
            "type": request_type,
            "request_id": payload.get("request_id", ""),
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }) + "\n"
        
        sock.sendall(message.encode())
        
        response_data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_data += chunk
            if b"\n" in response_data:
                break
        
        sock.close()
        
        response = json.loads(response_data.decode().strip())
        
        if response.get("type") == "ERROR":
            raise Exception(response.get("payload", {}).get("error", "Enclave error"))
        
        return response.get("payload", {})
        
    except Exception as e:
        logger.error(f"Failed to communicate with enclave: {e}")
        raise


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "mode": "parent_proxy"}


@app.get("/enclave/health")
async def enclave_health():
    """Check enclave health."""
    try:
        result = send_to_enclave("HEALTH_CHECK", {})
        return result
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.post("/api/audit", response_model=EnclaveAuditResponse)
async def audit_document(request: EnclaveAuditRequest):
    """
    Submit document for audit processing in the enclave.
    
    The request is securely forwarded to the Nitro Enclave
    where all processing occurs in isolated memory.
    """
    try:
        payload = {
            "content": request.content,
            "source_url": request.source_url,
            "original_filename": request.original_filename,
            "mime_type": request.mime_type,
            "supplier_id": request.supplier_id,
            "region": request.region,
            "reporting_period": request.reporting_period,
        }
        
        result = send_to_enclave("REQUEST", payload)
        
        return EnclaveAuditResponse(
            status=result.get("status", "success"),
            thread_id=result.get("thread_id"),
            compliance_score=result.get("compliance_score"),
            overall_decision=result.get("overall_decision"),
            findings_count=result.get("findings_count"),
            timestamp=result.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "enclave_processed": False}
        )


@app.get("/api/audit/{thread_id}")
async def get_audit_status(thread_id: str):
    """Get status of a previous audit (placeholder)."""
    return {
        "thread_id": thread_id,
        "status": "completed",
        "message": "Query enclave directly for full status",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PARENT_PORT)
