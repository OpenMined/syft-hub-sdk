"""
Simplified RPC client using syft-rpc primitives
"""
import json
import logging
from typing import Dict, Any, Optional

from syft_rpc.rpc import send
from syft_core import Client as SyftClient
from syft_crypto import encrypt_message, decrypt_message, EncryptedPayload

from ..core.exceptions import NetworkError, RPCError, TransactionTokenCreationError, PollingTimeoutError
from .accounting_client import AccountingClient
from .request_client import RequestArgs

logger = logging.getLogger(__name__)


class SyftBoxRPCClient:
    """Simplified RPC client using syft-rpc primitives."""
    
    def __init__(
        self,
        syft_client: SyftClient,
        timeout: float = 300.0,
        max_poll_attempts: int = 100,
        poll_interval: float = 1.5,
        accounting_client: Optional[AccountingClient] = None,
    ):
        """Initialize RPC client.
        
        Args:
            syft_client: SyftBox core client (with encryption keys bootstrapped)
            timeout: Request timeout in seconds
            max_poll_attempts: Maximum polling attempts
            poll_interval: Seconds between polling attempts
            accounting_client: Optional accounting client
        """
        self.syft_client = syft_client
        self.timeout = timeout
        self.max_poll_attempts = max_poll_attempts
        self.poll_interval = poll_interval
        self.accounting_client = accounting_client or AccountingClient()
        self.from_email = syft_client.email

    async def close(self):
        """Close client resources."""
        pass  # syft-rpc handles cleanup
    
    async def call_rpc(
        self,
        syft_url: str,
        payload: Optional[Dict[str, Any]] = None,
        method: str = "POST",
        encrypt: bool = False,
        args: Optional[RequestArgs] = None,
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Make an RPC call using syft-rpc send().
        
        Args:
            syft_url: The syft:// URL to call
            payload: JSON payload to send
            method: HTTP method
            encrypt: Whether to encrypt the request using X3DH
            args: Additional request arguments
            timeout: Override timeout for this call (uses instance default if None)
            poll_interval: Override poll interval for this call (uses instance default if None)
            
        Returns:
            Response data (auto-decrypted if response was encrypted)
        """
        if args is None:
            args = RequestArgs()
        
        # Handle accounting token injection
        if args.is_accounting and payload is not None:
            payload = payload.copy()
            
            if self.accounting_client.is_configured():
                accounting_email = self.accounting_client.get_email()
                payload["user_email"] = accounting_email
                
                try:
                    recipient_email = syft_url.split('//')[1].split('/')[0]
                    transaction_token = await self.accounting_client.create_transaction_token(
                        recipient_email=recipient_email
                    )
                    payload["transaction_token"] = transaction_token
                except Exception as e:
                    raise TransactionTokenCreationError(
                        f"Failed to create accounting token: {e}",
                        recipient_email=recipient_email
                    )
            else:
                payload["user_email"] = self.from_email
        
        # Encrypt payload if requested using syft-crypto
        if encrypt and payload is not None:
            recipient = syft_url.split('//')[1].split('/')[0]
            
            logger.debug(f"Encrypting payload for {recipient}")
            
            encrypted_payload = encrypt_message(
                message=json.dumps(payload),
                to=recipient,
                client=self.syft_client,
                verbose=False
            )
            
            # Convert EncryptedPayload to dict for sending
            payload = json.loads(encrypted_payload.model_dump_json())
            
            logger.debug("Payload encrypted successfully")
        
        # Send request using syft-rpc (do NOT pass encrypt=True, we already encrypted)
        future = send(
            url=syft_url,
            method=method,
            body=payload,
            encrypt=False,  # Already encrypted above if needed
            client=self.syft_client,
            cache=False,
        )
        
        # Wait for response with configured timeout (use override if provided)
        effective_timeout = timeout if timeout is not None else self.timeout
        effective_poll_interval = poll_interval if poll_interval is not None else self.poll_interval
        
        try:
            response = future.wait(
                timeout=effective_timeout,
                poll_interval=effective_poll_interval
            )
            
            # Check response status
            if not response.is_success:
                error_msg = response.text() if response.body else f"Status {response.status_code}"
                raise RPCError(error_msg, syft_url)
            
            # Parse response
            response_data = response.json()
            
            # Auto-decrypt if response is encrypted
            if self._is_encrypted_payload(response_data):
                logger.debug("Detected encrypted response, decrypting")
                
                encrypted = EncryptedPayload(**response_data)
                decrypted = decrypt_message(
                    payload=encrypted,
                    client=self.syft_client,
                    verbose=False
                )
                
                response_data = json.loads(decrypted)
                logger.debug("Response decrypted successfully")
            
            return response_data
            
        except Exception as e:
            if "timeout" in str(e).lower():
                raise PollingTimeoutError(syft_url, self.max_poll_attempts, self.max_poll_attempts)
            raise NetworkError(f"RPC call failed: {e}", syft_url)
    
    def _is_encrypted_payload(self, data: Any) -> bool:
        """Check if response data is an EncryptedPayload.
        
        Args:
            data: Response data to check
            
        Returns:
            True if data is an encrypted payload
        """
        if not isinstance(data, dict):
            return False
        
        # EncryptedPayload has these required fields
        required_fields = ['ek', 'iv', 'ciphertext', 'tag', 'sender', 'receiver', 'version']
        return all(field in data for field in required_fields)
    
    # async def call_health(self, service_info: ServiceInfo) -> Dict[str, Any]:
    #     """Call health endpoint."""
    #     health_args = RequestArgs(is_accounting=False)
        
    #     url = make_url(
    #         service_info.datasite,
    #         service_info.name,
    #         "health"
    #     )
        
    #     return await self.call_rpc(
    #         str(url),
    #         payload=None,
    #         method="GET",
    #         args=health_args,
    #     )
    
    # async def call_chat(self, service_info: ServiceInfo, request_data: Dict[str, Any]) -> Dict[str, Any]:
    #     """Call chat endpoint."""
    #     # Override model to actual LLM model name
    #     if "model" in request_data:
    #         request_data = request_data.copy()
    #         request_data["model"] = "tinyllama:latest"
        
    #     chat_service = service_info.get_service_info(ServiceType.CHAT)
    #     is_free_service = chat_service and chat_service.pricing == 0.0
        
    #     chat_args = RequestArgs(is_accounting=not is_free_service)
        
    #     url = make_url(
    #         service_info.datasite,
    #         service_info.name,
    #         "chat"
    #     )
    #     logger.info(f"Chat request payload: {json.dumps(request_data, indent=2)}")
    #     return await self.call_rpc(
    #         str(url),
    #         payload=request_data,
    #         args=chat_args,
    #     )
    
    # async def call_search(self, service_info: ServiceInfo, request_data: Dict[str, Any]) -> Dict[str, Any]:
    #     """Call search endpoint."""
    #     search_service = service_info.get_service_info(ServiceType.SEARCH)
    #     is_free_service = search_service and search_service.pricing == 0.0
        
    #     search_args = RequestArgs(is_accounting=not is_free_service)
        
    #     url = make_url(
    #         service_info.datasite,
    #         service_info.name,
    #         "search"
    #     )
        
    #     return await self.call_rpc(
    #         str(url),
    #         payload=request_data,
    #         args=search_args,
    #     )
