"""
Search service client using syft-rpc
"""
import asyncio
import json
import logging
from typing import Dict, Any

from syft_core import Client as SyftClient
from syft_rpc.rpc import send, make_url
from syft_rpc.protocol import SyftStatus

from ..clients import AccountingClient, AuthClient
from ..core.types import ServiceType
from ..core.decorators import ensure_syftbox_running
from ..core.exceptions import RPCError, TransactionTokenCreationError, ValidationError, ServiceNotSupportedError
from ..models.responses import SearchResponse
from ..models.service_info import ServiceInfo
from ..utils.spinner import AsyncSpinner

logger = logging.getLogger(__name__)


class SearchService:
    """Service client for search services."""
    
    def __init__(
        self, 
        service_info: ServiceInfo,
        syft_client: SyftClient,
        accounting_client: AccountingClient,
        auth_client: AuthClient
    ):
        """Initialize search service.
        
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
        
        if not service_info.supports_service(ServiceType.SEARCH):
            raise ServiceNotSupportedError(service_info.name, "search", service_info)
        
        # Get user email from SyftBox auth (with guest fallback)
        self.from_email = self.auth_client.get_user_email()

    @ensure_syftbox_running
    async def search_with_params(self, params: Dict[str, Any], encrypt: bool = False) -> SearchResponse:
        """Send search request with parameters.
        
        Args:
            params: Dictionary of parameters including 'message'
            encrypt: Whether to encrypt the request
            
        Returns:
            Search response
        """
        # Validate required parameters
        if "message" not in params:
            raise ValidationError("'message' parameter is required")
        
        # Build syft URL
        syft_url = make_url(
            datasite=self.service_info.datasite,
            app_name=self.service_info.name,
            endpoint="search"
        )

        # Extract standard parameters (make copy to avoid mutating input)
        params = params.copy()
        message = params.pop("message")
        topK = params.pop("topK", 3)
        similarity_threshold = params.pop("similarity_threshold", None)
        
        # Build RPC payload with consistent authentication
        payload = {
            "user_email": self.accounting_client.get_email(),
            "query": message,
            "model": "tinyllama:latest" or self.service_info.name,
            "options": {"limit": topK}
        }
        
        if similarity_threshold is not None:
            payload["options"]["similarityThreshold"] = similarity_threshold
        
        # Add any additional service-specific parameters
        for key, value in params.items():
            payload["options"][key] = value

        search_service = self.service_info.get_service_info(ServiceType.SEARCH)
        is_free_service = search_service and search_service.pricing == 0.0

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
        headers = {}
        auth_token = await self.auth_client.get_auth_token()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            headers["Accept"] = f"application/json"
            headers["suffix-sender"] = "true"
            headers["x-syft-url"] = f"{syft_url}"
            headers["x-syft-from"] = f"{self.from_email}"

        # Wait for response
        spinner = AsyncSpinner("Waiting for service response")
        await spinner.start_async()
        try:
            # Send request using syft-rpc
            # NOTE: Pass the dict directly - syft-rpc's serialize() function will handle it
            # It uses GenericModel(**payload).model_dump_json() for dicts
            future = send(
                url=syft_url,
                method="POST",
                body=payload,
                headers=headers,
                client=self.syft_client,
                encrypt=encrypt,
                cache=False  # Don't cache search requests
            )
            
            # response = future.wait(timeout=120.0, poll_interval=1.5)
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
            except Exception as e:
                logger.debug(f"Could not parse error response body: {e}")
            
            raise RPCError(
                f"Search request failed: {error_details}",
                self.service_info.name
            )
        
        # Parse response
        try:
            response_data = response.json()
            
            # Handle nested response format
            if "data" in response_data and "message" in response_data["data"]:
                message_data = response_data["data"]["message"]
                if "body" in message_data:
                    return SearchResponse.from_dict(message_data["body"], message)
            
            return SearchResponse.from_dict(response_data, message)
            
        except Exception as e:
            logger.error(f"Failed to parse search response: {e}")
            raise RPCError(f"Failed to parse search response: {e}")
    
    @property
    def pricing(self) -> float:
        """Get pricing for search service."""
        search_service = self.service_info.get_service_info(ServiceType.SEARCH)
        return search_service.pricing if search_service else 0.0
    
    @property
    def is_paid(self) -> bool:
        """Check if this is a paid service."""
        return self.pricing > 0.0