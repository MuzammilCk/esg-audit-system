"""
VSocket Communication for AWS Nitro Enclaves

Implements secure communication between parent EC2 instance
and enclave using AF_VSOCK sockets.
"""

import os
import json
import socket
import logging
import asyncio
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

VSOCK_CID_ANY = -1
VSOCK_CID_HYPERVISOR = 0
VSOCK_CID_HOST = 3
VMADDR_CID_ANY = 0xFFFFFFFF


class MessageType(str, Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    ATTESTATION = "ATTESTATION"
    HEALTH_CHECK = "HEALTH_CHECK"


@dataclass
class EnclaveMessage:
    """Message structure for enclave communication."""
    type: MessageType
    request_id: str
    payload: Dict[str, Any]
    timestamp: str
    signature: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "request_id": self.request_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "signature": self.signature,
        })
    
    @classmethod
    def from_json(cls, data: str) -> "EnclaveMessage":
        parsed = json.loads(data)
        return cls(
            type=MessageType(parsed["type"]),
            request_id=parsed["request_id"],
            payload=parsed["payload"],
            timestamp=parsed["timestamp"],
            signature=parsed.get("signature"),
        )


class VSocketServer:
    """
    VSocket server running inside the enclave.
    
    Listens for requests from parent EC2 instance and
    routes them to appropriate handlers.
    """
    
    def __init__(
        self,
        port: int = 5005,
        host_cid: int = VSOCK_CID_ANY,
        max_connections: int = 10,
    ):
        self.port = port
        self.host_cid = host_cid
        self.max_connections = max_connections
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._socket = None
    
    def register_handler(
        self,
        message_type: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """Register a handler for a message type."""
        self._handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    async def start(self) -> None:
        """Start the vsocket server."""
        try:
            self._socket = socket.socket(
                socket.AF_VSOCK,
                socket.SOCK_STREAM,
            )
            self._socket.bind((VMADDR_CID_ANY, self.port))
            self._socket.listen(self.max_connections)
            self._socket.setblocking(False)
            self._running = True
            
            logger.info(f"VSocket server listening on port {self.port}")
            
            loop = asyncio.get_event_loop()
            
            while self._running:
                try:
                    client, addr = await loop.sock_accept(self._socket)
                    asyncio.create_task(self._handle_client(client, addr))
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error accepting connection: {e}")
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Failed to start vsocket server: {e}")
            raise
        finally:
            self._cleanup()
    
    async def stop(self) -> None:
        """Stop the vsocket server."""
        self._running = False
        self._cleanup()
    
    def _cleanup(self) -> None:
        if self._socket:
            self._socket.close()
            self._socket = None
    
    async def _handle_client(
        self,
        client: socket.socket,
        addr: tuple,
    ) -> None:
        """Handle a client connection."""
        try:
            loop = asyncio.get_event_loop()
            
            data = b""
            while True:
                chunk = await loop.sock_recv(client, 4096)
                if not chunk:
                    break
                data += chunk
                
                if b"\n" in data:
                    break
            
            if not data:
                return
            
            message_str = data.decode().strip()
            message = EnclaveMessage.from_json(message_str)
            
            response = await self._process_message(message)
            
            response_bytes = (response.to_json() + "\n").encode()
            await loop.sock_sendall(client, response_bytes)
            
        except Exception as e:
            logger.error(f"Error handling client: {e}")
            error_response = EnclaveMessage(
                type=MessageType.ERROR,
                request_id="error",
                payload={"error": str(e)},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            try:
                await loop.sock_sendall(client, (error_response.to_json() + "\n").encode())
            except Exception:
                pass
        finally:
            client.close()
    
    async def _process_message(self, message: EnclaveMessage) -> EnclaveMessage:
        """Process a message and return response."""
        handler = self._handlers.get(message.type.value)
        
        if handler:
            try:
                result = handler(message.payload)
                if asyncio.iscoroutine(result):
                    result = await result
                
                return EnclaveMessage(
                    type=MessageType.RESPONSE,
                    request_id=message.request_id,
                    payload=result,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            except Exception as e:
                return EnclaveMessage(
                    type=MessageType.ERROR,
                    request_id=message.request_id,
                    payload={"error": str(e)},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        else:
            return EnclaveMessage(
                type=MessageType.ERROR,
                request_id=message.request_id,
                payload={"error": f"No handler for message type: {message.type}"},
                timestamp=datetime.now(timezone.utc).isoformat(),
            )


class VSocketClient:
    """
    VSocket client running on the parent EC2 instance.
    
    Communicates with the enclave through vsock.
    """
    
    def __init__(
        self,
        enclave_cid: int = VSOCK_CID_ANY,
        port: int = 5005,
        timeout: float = 30.0,
    ):
        self.enclave_cid = enclave_cid
        self.port = port
        self.timeout = timeout
    
    async def send_request(
        self,
        request_type: str,
        payload: Dict[str, Any],
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a request to the enclave and wait for response.
        """
        import uuid
        from datetime import datetime, timezone
        
        request_id = request_id or str(uuid.uuid4())
        
        message = EnclaveMessage(
            type=MessageType(request_type),
            request_id=request_id,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        try:
            sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            
            sock.connect((VMADDR_CID_ANY, self.port))
            
            sock.sendall((message.to_json() + "\n").encode())
            
            response_data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:
                    break
            
            sock.close()
            
            response = EnclaveMessage.from_json(response_data.decode().strip())
            
            if response.type == MessageType.ERROR:
                raise Exception(response.payload.get("error", "Unknown error"))
            
            return response.payload
            
        except socket.timeout:
            raise TimeoutError(f"Enclave request timed out after {self.timeout}s")
        except Exception as e:
            raise ConnectionError(f"Failed to communicate with enclave: {e}")
    
    async def health_check(self) -> bool:
        """Check if enclave is healthy."""
        try:
            response = await self.send_request(
                request_type=MessageType.HEALTH_CHECK.value,
                payload={},
            )
            return response.get("status") == "ok"
        except Exception:
            return False


def create_enclave_server(
    audit_handler: Callable,
    port: int = 5005,
) -> VSocketServer:
    """Create and configure a vsocket server for the enclave."""
    server = VSocketServer(port=port)
    
    server.register_handler(MessageType.REQUEST.value, audit_handler)
    server.register_handler(
        MessageType.HEALTH_CHECK.value,
        lambda _: {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    )
    
    return server
