"""
AWS Nitro Enclave Integration for Zero-Trust AI Processing

This module provides confidential computing capabilities by running
the LangGraph multiagent system within AWS Nitro Enclaves.

Architecture:
1. Parent EC2 instance receives API requests
2. Requests forwarded to enclave via vsock
3. Enclave performs attested computation in isolated memory
4. Results returned through secure channel
"""

from enclave.attestation import AttestationService, PCR_VALUES
from enclave.communication import VSocketServer, VSocketClient
from enclave.crypto import EnclaveCrypto, KMSService

__all__ = [
    "AttestationService",
    "PCR_VALUES",
    "VSocketServer",
    "VSocketClient",
    "EnclaveCrypto",
    "KMSService",
]
