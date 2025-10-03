"""
Chat service client using syft-rpc
"""
import asyncio
import logging
from typing import Dict, Any

from syft_rpc.rpc import send, make_url
from syft_rpc.protocol import SyftStatus

from ..clients import SyftBoxRPCClient
from ..core.types import ServiceType, ChatMessage
from ..core.exceptions import RPCError, ValidationError, ServiceNotSupportedError, TransactionTokenCreationError
from ..models.responses import ChatResponse
from ..models.service_info import ServiceInfo
from ..utils.spinner import AsyncSpinner

logger = logging.getLogger(__name__)


class ChatService:
    """Service client for chat services."""
    
    def __init__(self, service_info: ServiceInfo, rpc_client: SyftBoxRPCClient):
        """Initialize chat service.
        
        Args:
            service_info: Information about the service
            rpc_client: SyftBoxRPCClient instance
        """
        self.service_info = service_info
        self.rpc_client = rpc_client
        
        if not service_info.supports_service(ServiceType.CHAT):
            raise ServiceNotSupportedError(service_info.name, "chat", service_info)
    
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
        url = make_url(
            datasite=self.service_info.datasite,
            app_name=self.service_info.name,
            endpoint="chat"
        )

        # Build RPC payload with all parameters
        # Extract standard parameters
        params = params.copy()
        messages = params.pop("messages")
        temperature = params.pop("temperature", 0.7)
        # max_tokens = params.pop("max_tokens", None)
        account_email = self.rpc_client.accounting_client.get_email()
        # if "model" in request_data:
        #     request_data = request_data.copy()
        #     request_data["model"] = "tinyllama:latest"
        payload = {
            "user_email": account_email,
            "model": "tinyllama:latest" or self.service_info.name,
            "messages": messages,
            "options": {"temperature": temperature}
        }

        # Add generation options
        # options = {}
        # if temperature is not None:
        #     options["temperature"] = temperature
        # if max_tokens is not None:
        #     options["maxTokens"] = max_tokens
        
        # Add any additional service-specific parameters
        # Add any additional service-specific parameters
        for key, value in params.items():
            payload["options"][key] = value
        # for key, value in params.items():
        #     options[key] = value
        # logger
        
        # if options:
        #     payload["options"] = options

        # Add transaction token for paid services
        chat_service = self.service_info.get_service_info(ServiceType.CHAT)
        is_free_service = chat_service and chat_service.pricing == 0.0

        if not is_free_service and self.rpc_client.accounting_client.is_configured():
            try:
                recipient_email = self.service_info.datasite
                transaction_token = await self.rpc_client.accounting_client.create_transaction_token(
                    recipient_email=recipient_email
                )
                payload["transaction_token"] = transaction_token
            except Exception as e:
                raise TransactionTokenCreationError(
                    f"Failed to create accounting token: {e}",
                    recipient_email=recipient_email
                )

        # Send request using syft-rpc
        logger.info(f"Sending chat request to {url} with payload: {payload}")
        future = send(
            url=url,
            method="POST",
            body=payload,
            client=self.rpc_client.syft_client,
            encrypt=encrypt,
            cache=False  # Don't cache chat requests
        )
        
        # Wait for response - use asyncio.to_thread to avoid blocking the event loop
        spinner = AsyncSpinner("Waiting for service response")
        await spinner.start_async()
        try:
            # Run the blocking wait() in a thread pool to enable true parallelism
            response = await asyncio.to_thread(future.wait, timeout=120.0, poll_interval=0.5)
            logger.info(f"Chat response received from {self.service_info.datasite}/{self.service_info.name} (status: {response.status_code})")
        finally:
            # spinner.stop()
            await spinner.stop_async("Response received")
        
        # Check status
        if response.status_code != SyftStatus.SYFT_200_OK:
            raise RPCError(
                f"Chat request failed: {response.status_code}",
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