"""
Chat service client using syft-rpc
"""
import asyncio
import json
import logging
from typing import Dict, Any

from syft_core import Client as SyftClient
from syft_rpc.rpc import send, make_url
from syft_rpc.protocol import SyftStatus

from ..clients import AccountingClient, AuthClient
from ..core.decorators import ensure_syftbox_running
from ..core.types import ChatMessage, ServiceType
from ..core.exceptions import RPCError, ValidationError, ServiceNotSupportedError, TransactionTokenCreationError
from ..models.responses import ChatResponse
from ..models.service_info import ServiceInfo
from ..utils.spinner import AsyncSpinner

logger = logging.getLogger(__name__)


class ChatService:
    """Service client for chat services."""
    
    def __init__(
        self, 
        service_info: ServiceInfo,
        syft_client: SyftClient,
        accounting_client: AccountingClient,
        auth_client: AuthClient
    ):
        """Initialize chat service.
        
        Args:
            service_info: Information about the service
            syft_client: syft_core.Client instance
            accounting_client: AccountingClient instance
            auth_client: AuthClient instance
        """
        self.service_info = service_info
        self.syft_client = syft_client
        self.accounting_client = accounting_client
        self.auth_client = auth_client

        if not service_info.supports_service(ServiceType.CHAT):
            raise ServiceNotSupportedError(service_info.name, "chat", service_info)
        
        # Get user email from SyftBox auth (with guest fallback)
        self.from_email = self.auth_client.get_user_email()

    @ensure_syftbox_running
    async def chat_with_params(self, params: Dict[str, Any], encrypt: bool = False) -> ChatResponse:
        """Send chat request with parameters.
        
        Args:
            params: Dictionary of parameters including 'messages'
            encrypt: Whether to encrypt the request
            
        Returns:
            Chat response
        """
        if "messages" not in params:
            raise ValidationError("'messages' parameter is required")
        
        # Build syft URL
        syft_url = make_url(
            datasite=self.service_info.datasite,
            app_name=self.service_info.name,
            endpoint="chat"
        )

        # Extract standard parameters
        params = params.copy()
        messages = params.pop("messages")
        temperature = params.pop("temperature", 0.7)

        # Build payload
        payload = {
            "user_email": self.accounting_client.get_email(),
            "model": "tinyllama:latest",
            "messages": messages,
            "options": {"temperature": temperature}
        }
        
        # Add any additional service-specific parameters
        for key, value in params.items():
            payload["options"][key] = value

        # Add transaction token for paid services
        chat_service = self.service_info.get_service_info(ServiceType.CHAT)
        is_free_service = chat_service and chat_service.pricing == 0.0
        
        if not is_free_service and self.accounting_client.is_configured():
            try:
                # Use accounting email as sender when we have accounting tokens
                transaction_token = await self.accounting_client.create_transaction_token(
                    recipient_email=self.service_info.datasite
                )
                payload["transaction_token"] = transaction_token
                logger.debug(f"Added accounting token for {self.service_info.datasite}/{self.service_info.name}")
            except Exception as e:
                raise TransactionTokenCreationError(
                    f"Failed to create accounting token: {e}",
                    recipient_email=self.service_info.datasite
                )
        else:
            # Guest mode - use the current from_email
            payload["user_email"] = self.from_email
            logger.debug(f"Guest mode request to {self.service_info.datasite}/{self.service_info.name} - no accounting token available")

        # Add SyftBox authentication if available
        headers = {
            "Content-Type": "application/json"
        }
        auth_token = await self.auth_client.get_auth_token()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            headers["Accept"] = f"application/json"
            headers["suffix-sender"] = "true"
            headers["x-syft-url"] = f"{syft_url}"
            headers["x-syft-from"] = f"{self.from_email}"
        
        # Log the payload for debugging
        logger.debug(f"Sending chat request to {syft_url}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Encrypt: {encrypt}")
        
        # Wait for response
        spinner = AsyncSpinner("Waiting for service response")
        await spinner.start_async()
        try:
            # Send request using syft-rpc
            future = send(
                url=syft_url,
                method="POST",
                body=payload,
                headers=headers,
                client=self.syft_client,
                encrypt=encrypt,
                cache=False
            )

            # Run the blocking wait() in a thread pool to enable true parallelism
            response = await asyncio.to_thread(
                future.wait, 
                timeout=120.0, 
                poll_interval=0.5
            )
        finally:
            await spinner.stop_async("Response received")
        
        # Check status
        if response.status_code != SyftStatus.SYFT_200_OK:
            # Try to extract error details from response body
            error_details = f"Status code: {response.status_code}"
            try:
                error_body = response.json()
                
                if isinstance(error_body, dict):
                    # Extract error message from common error response formats
                    if "error" in error_body:
                        error_details = f"{response.status_code}: {error_body['error']}"
                    elif "message" in error_body:
                        error_details = f"{response.status_code}: {error_body['message']}"
                    elif "detail" in error_body:
                        error_details = f"{response.status_code}: {error_body['detail']}"
                    else:
                        error_details = f"{response.status_code}: {error_body}"
                else:
                    error_details = f"{response.status_code}: {error_body}"
            except Exception:
                # Try to get raw text from response
                try:
                    if hasattr(response, 'text') and callable(response.text):
                        error_details = f"{response.status_code}: {response.text()}"
                    elif hasattr(response, 'body'):
                        # Try to decode body if it's bytes
                        body = response.body
                        if isinstance(body, bytes):
                            error_details = f"{response.status_code}: {body.decode('utf-8', errors='replace')}"
                        else:
                            error_details = f"{response.status_code}: {body}"
                except Exception:
                    pass
            
            raise RPCError(
                f"Chat request failed: {error_details}",
                self.service_info.name
            )
        
        # Parse response using syft-rpc deserialization
        try:
            response_data = response.json()
            
            # Handle nested response format
            if "data" in response_data and "message" in response_data["data"]:
                message_data = response_data["data"]["message"]
                if "body" in message_data:
                    chat_response = ChatResponse.from_dict(message_data["body"])
                else:
                    chat_response = ChatResponse.from_dict(response_data)
            else:
                chat_response = ChatResponse.from_dict(response_data)
            
            # Store the original input messages in the response for display
            # The server response doesn't include them, so we add them here
            # Convert dictionary messages to ChatMessage objects
            chat_response.messages = [
                ChatMessage(
                    role=msg.get('role', 'user'),
                    content=msg.get('content', ''),
                    name=msg.get('name')
                ) for msg in messages
            ]
            
            return chat_response
            
        except Exception as e:
            logger.error(f"Failed to parse chat response: {e}")
            raise RPCError(f"Failed to parse chat response: {e}")
    
    @property
    def pricing(self) -> float:
        """Get pricing for chat service."""
        chat_service = self.service_info.get_service_info(ServiceType.CHAT)
        return chat_service.pricing if chat_service else 0.0
    
    @property
    def is_paid(self) -> bool:
        """Check if this is a paid service."""
        return self.pricing > 0.0