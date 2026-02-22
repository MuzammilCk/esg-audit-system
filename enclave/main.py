"""
Enclave Main Application

Entry point for the ESG Audit Enclave running in AWS Nitro Enclave.
Handles secure request processing in isolated memory.
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ENCLAVE_PORT = int(os.getenv("ENCLAVE_PORT", "5005"))


class EnclaveAuditService:
    """
    Main audit service running inside the Nitro Enclave.
    
    Provides secure processing of ESG audit requests with:
    - Hardware-isolated execution
    - Attestation-based key release
    - Encrypted communication
    """
    
    def __init__(self):
        self._initialized = False
        self._audit_graph = None
        self._crypto = None
    
    async def initialize(self) -> None:
        """Initialize the enclave service."""
        logger.info("Initializing Enclave Audit Service...")
        
        try:
            from enclave.attestation import AttestationService
            from enclave.crypto import EnclaveCrypto, KMSService
            
            attestation = AttestationService()
            attestation_doc = attestation.generate_attestation()
            logger.info("Attestation document generated")
            
            if os.getenv("AWS_KMS_KEY_ID"):
                kms = KMSService()
                logger.info("KMS service initialized")
            
            self._crypto = EnclaveCrypto()
            
            try:
                from services.agents import create_audit_graph
                
                self._audit_graph = create_audit_graph(
                    use_sqlite_checkpoint=False,
                )
                logger.info("Audit graph initialized")
            except ImportError:
                logger.warning("Audit graph not available - running in stub mode")
            
            self._initialized = True
            logger.info("Enclave initialization complete")
            
        except Exception as e:
            logger.error(f"Enclave initialization failed: {e}")
            raise
    
    async def process_audit_request(
        self,
        request: dict,
    ) -> dict:
        """
        Process an audit request securely within the enclave.
        
        Args:
            request: Audit request with document content and metadata
        
        Returns:
            Audit result with compliance findings
        """
        if not self._initialized:
            raise RuntimeError("Enclave not initialized")
        
        logger.info(f"Processing audit request: {request.get('request_id', 'unknown')}")
        
        try:
            if self._audit_graph:
                return await self._process_with_graph(request)
            else:
                return self._stub_response(request)
                
        except Exception as e:
            logger.error(f"Audit processing failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    
    async def _process_with_graph(self, request: dict) -> dict:
        """Process using LangGraph audit workflow."""
        from services.agents.state import DocumentMetadata
        
        metadata = DocumentMetadata(
            source_url=request.get("source_url", ""),
            original_filename=request.get("original_filename", ""),
            mime_type=request.get("mime_type", "text/plain"),
            supplier_id=request.get("supplier_id"),
            region=request.get("region"),
            reporting_period=request.get("reporting_period"),
        )
        
        final_state = await self._audit_graph.run_audit(
            raw_content=request.get("content", ""),
            metadata=metadata,
        )
        
        return {
            "status": "success",
            "thread_id": final_state.thread_id,
            "compliance_score": final_state.compliance_result.compliance_score,
            "overall_decision": final_state.compliance_result.overall_decision.value,
            "findings_count": len(final_state.compliance_result.findings),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def _stub_response(self, request: dict) -> dict:
        """Return stub response when audit graph is not available."""
        return {
            "status": "success",
            "message": "Enclave processing (stub mode)",
            "request_id": request.get("request_id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def health_check(self) -> dict:
        """Return health status."""
        return {
            "status": "ok" if self._initialized else "initializing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "enclave": True,
        }


async def main():
    """Main entry point for the enclave."""
    from enclave.communication import create_enclave_server
    
    service = EnclaveAuditService()
    await service.initialize()
    
    async def handle_request(payload: dict) -> dict:
        return await service.process_audit_request(payload)
    
    server = create_enclave_server(
        audit_handler=handle_request,
        port=ENCLAVE_PORT,
    )
    
    server.register_handler("HEALTH_CHECK", lambda _: service.health_check())
    
    logger.info(f"Starting enclave server on port {ENCLAVE_PORT}")
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
