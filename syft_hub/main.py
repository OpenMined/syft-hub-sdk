"""
Main Syft Hub SDK client
"""
import json
import os
import asyncio
import concurrent.futures
import logging
import threading

from typing import List, Optional, Dict, Any, Union, Awaitable
from pathlib import Path
from dotenv import load_dotenv

from .core import Service, Pipeline
from .core.config import ConfigManager
from .core.types import ServiceType, HealthStatus, DocumentResult
from .core.exceptions import (
    AuthenticationError,
    ServiceNotFoundError,
    SyftBoxNotFoundError, 
    SyftBoxNotRunningError,
    ServiceNotSupportedError, 
    ValidationError,
)
from .discovery import FastScanner, MetadataParser, ServiceFilter, FilterCriteria
from .clients import SyftBoxRPCClient, AccountingClient, SyftBoxAuthClient
from .services import ChatService, SearchService, HealthMonitor, check_service_health, batch_health_check
from .models import ChatResponse, SearchResponse, DocumentResult, ServicesList, ServiceInfo
from .utils.formatting import format_services_table, format_service_details
from .utils.async_utils import detect_async_context, run_async_in_thread

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class Client:
    """Main client for discovering and using SyftBox AI services."""
    
    def __init__(
            self, 
            syftbox_config_path: Optional[Path] = None,
            cache_server_url: Optional[str] = None,
            accounting_client: Optional[AccountingClient] = None,
            _auto_setup_accounting: bool = True,
            _auto_health_check_threshold: int = 10
        ):
        """Initialize SyftBox client.
        
        Args:
            syftbox_config_path: Custom path to SyftBox config file
            cache_server_url: Override cache server URL
            accounting_client: Pre-configured AccountingClient instance
            _auto_setup_accounting: Whether to prompt for accounting setup when needed
            _auto_health_check_threshold: Max services for auto health checking
        """
        # Check SyftBox availability and config manager with custom path if provided
        self.config_manager = ConfigManager(syftbox_config_path)
        
        # Check if installed first
        if not self.config_manager.is_syftbox_installed():
            raise SyftBoxNotFoundError(self.config_manager.get_installation_instructions())

        # Then check if running  
        if not self.config_manager.is_syftbox_running():
            raise SyftBoxNotRunningError(self.config_manager.get_startup_instructions())
        
        # Store config for later use
        self.config = self.config_manager.config
        
        # Initialize account state
        self._account_configured = False

        # Set up SyftBox authentication client using the loaded config
        self.syftbox_auth_client, is_auth_configured = SyftBoxAuthClient.setup_auth_discovery(self.config)
        
        if is_auth_configured:
            logger.info(f"SyftBox authentication configured for {self.syftbox_auth_client.get_user_email()}")
        else:
            logger.info("Using guest mode - no SyftBox authentication found")

        # Set up accounting client - check for existing credentials
        if accounting_client:
            self.accounting_client = accounting_client
            if self.accounting_client.is_configured():
                self._account_configured = True
        else:
            # Inlined _setup_default_accounting logic
            client, is_configured = AccountingClient.setup_accounting_discovery()
            
            if is_configured:
                self._account_configured = True
                logger.info(f"Found existing accounting credentials for {client.get_email()}")
            else:
                """Display account setup instructions to user."""
                print("SyftBox Account Setup:")
                print("═" * 60)
                print("⚠️  No Active Accounting Account Found")
                print("")
                print("You are currently on the SyftBox Free tier. As a new user, you receive:")
                print("   → $20 in free credits to explore the network")
                print("   → Credits are for trial use only (not a payment method)")
                print("")
                print("To continue, choose one of the options below:")
                print("")
                print("  🆕 Create a new account:")
                print("      await client.register_accounting(email, password)")
                print("")
                print("  🔑 Connect an existing account:")
                print("      await client.connect_accounting(email, password)")
                print("")

            self.accounting_client = client
        
        # Set up RPC client
        server_url = cache_server_url or self.config.cache_server_url
        
        self.rpc_client = SyftBoxRPCClient(
            cache_server_url=server_url,
            accounting_client=self.accounting_client,
            syftbox_auth_client=self.syftbox_auth_client,
        )
        
        # Set up discovery services
        self._scanner = FastScanner(self.config)
        self._parser = MetadataParser()
        
        # Configuration
        self._auto_health_check_threshold = _auto_health_check_threshold
        self._auto_setup_accounting = _auto_setup_accounting
        
        # Optional health monitor
        self._health_monitor: Optional[HealthMonitor] = None

        # Load user email from config if not provided (from_email and self._account_configured)
        logger.info(f"Client initialized for {self.config.email}")
    
    def __dir__(self):
        """Control what appears in autocomplete suggestions.
        
        Returns only the main public methods that users should interact with.
        """
        return [
            # Display methods
            'show',
            'show_services',
            
            # Service discovery and usage
            'list_services',
            'load_service',
            'get_service',
            'chat',
            'chat_async',
            'search',
            'search_async',
            'get_service_params',
            'show_service',
            
            # RAG/Pipeline
            'pipeline',
            
            # Accounting
            'accounting_client',
            'register_accounting',
            'connect_accounting',
            'get_accounting_status',
            'is_accounting_configured',
            'get_account_info',
            
            # Health monitoring
            'check_service_health',
            'check_all_services_health',
            'start_health_monitoring',
            'stop_health_monitoring',
            
            # Properties
            'config',
            'config_manager',
            'rpc_client',
            
            # Helper methods
            'remove_duplicate_results',
            'format_search_context',
            
            # Maintenance
            'clear_cache',
            'close',
        ]
    
    async def close(self):
        """Close client and cleanup resources."""
        await self.rpc_client.close()
        if self._health_monitor:
            await self._health_monitor.stop_monitoring()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # Service Discovery Methods
    def list_services(self,
                    service_type: Optional[str] = None,
                    datasite: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    max_cost: Optional[float] = None,
                    free_only: bool = False,
                    health_check: str = "auto",
                    **filter_kwargs) -> List[ServiceInfo]:
        """Discover available services with filtering and optional health checking.
        
        Args:
            service_type: Filter by service type (chat, search)
            datasite: Filter by datasite email
            tags: Filter by tags (any match)
            max_cost: Maximum cost per request
            free_only: Only return free services (cost = 0)
            health_check: Health checking mode ("auto", "always", "never")
            **filter_kwargs: Additional filter criteria
            
        Returns:
            List of discovered and filtered services
        """
        # Scan for metadata files
        metadata_paths = self._scanner.scan_with_cache()
        
        # Parse services from metadata
        services = []
        for metadata_path in metadata_paths:
            try:
                service_info = self._parser.parse_service_from_files(metadata_path)
                services.append(service_info)
            except Exception as e:
                logger.debug(f"Failed to parse {metadata_path}: {e}")
                continue

        # Convert string to enum
        service_type_enum = None
        if service_type:
            try:
                service_type_enum = ServiceType(service_type.lower())
            except ValueError:
                logger.error(f"Invalid service_type: {service_type}")
                return []
        
        # Apply filters
        filter_criteria = FilterCriteria(
            service_type=service_type_enum,
            datasite=datasite,
            has_any_tags=tags,
            max_cost=max_cost,
            free_only=free_only,
            enabled_only=True,
            **filter_kwargs
        )
        
        service_filter = ServiceFilter(filter_criteria)
        filtered_services = service_filter.filter_services(services)
        
        # Determine if we should do health checking
        should_health_check = self._should_do_health_check(
            health_check, len(filtered_services)
        )
        
        if should_health_check:
            # Use thread-based approach to avoid event loop conflicts
            try:
                filtered_services = run_async_in_thread(
                    self._add_health_status(filtered_services)
                )
            except Exception as e:
                logger.warning(f"Health check failed: {e}. Continuing without health status.")
        
        logger.debug(f"Discovered {len(filtered_services)} services (health_check={should_health_check})")
        return ServicesList(filtered_services, self)
    
    def get_service(self, service_name: str) -> ServiceInfo:
        if not service_name:
            raise ValidationError("Valid service name (datasite/service_name) must be provided")
        datasite, name = service_name.split("/", 1)
        metadata_path = self._scanner.get_service_path(datasite, name)
        
        if not metadata_path:
            raise ServiceNotFoundError(f"'{service_name}'")
        
        return self._parser.parse_service_from_files(metadata_path)
    
    def load_service(self, service_name: str) -> Service:
        """Load a service by name and return Service object for interaction.
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
            
        Returns:
            Service object for object-oriented interaction
            
        Examples:
            # Load a chat service
            service = client.load_service("alice@example.com/gpt-assistant")
            response = service.chat(messages=[{"role": "user", "content": "Hello"}])
            
            # Load a search service
            search_service = client.load_service("bob@example.com/document-search")
            results = search_service.search(message="Python tutorial")
        """
        service_info = self.get_service(service_name)
        
        # Check health status if not already checked
        if service_info.health_status is None:
            try:
                from .services.health import check_service_health
                from .utils.async_utils import run_async_in_thread
                health_status = run_async_in_thread(
                    check_service_health(service_info, self.rpc_client, timeout=2.0)
                )
                service_info.health_status = health_status
            except Exception as e:
                logger.debug(f"Health check failed for {service_name}: {e}")
                # Leave health_status as None if check fails
        
        return Service(service_info, self)

    # Service Usage Methods 
    # @require_account
    async def chat_async(self,
            service_name: str,
            messages: str,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            **kwargs
        ) -> ChatResponse:
        """Chat with a specific service  (async version).
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
            messages: Message to send
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional service-specific parameters
            
        Returns:
            Chat response from the specified service
        
        Examples:
            # Basic chat
            response = await client.chat_async(
                "alice@example.com/gpt-assistant",
                "What is machine learning?"
            )
            
            # Chat with parameters
            response = await client.chat_async(
                "bob@example.com/creative-writer",
                "Write a poem about clouds",
                temperature=0.8,
                max_tokens=200
            )
        """
        # Find the specific service
        service = self.get_service(service_name)
        logger.info(f"Using service: {service.name} from datasite: {service.datasite}") 
        
        # Check if service is online by pinging it
        health_status = await check_service_health(service, self.rpc_client, timeout=3.0)
        if health_status == HealthStatus.OFFLINE:
            raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
        
        # Validate service supports chat
        if not service.supports_service(ServiceType.CHAT):
            raise ServiceNotSupportedError(service.name, "chat", service)

        # Build request parameters
        chat_params = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        # Remove None values
        chat_params = {k: v for k, v in chat_params.items() if v is not None}
        
        # Create service and make request
        chat_service = ChatService(service, self.rpc_client)
        return await chat_service.chat_with_params(chat_params)
    
    def chat_sync(
            self,
            service_name: str,
            messages: str,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            **kwargs
        ) -> ChatResponse:
        """Chat with a specific service.
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
            messages: Message to send
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional service-specific parameters
            
        Returns:
            Chat response from the specified service
        """
        
        # Use thread-based execution with its own event loop
        # This ensures the chat runs in a fresh event loop context
        async def _chat():
            # Find the specific service
            service = self.get_service(service_name)
            logger.info(f"Using service: {service.name} from datasite: {service.datasite}")
            
            # Check if service is online by pinging it
            health_status = await check_service_health(service, self.rpc_client, timeout=3.0)
            if health_status == HealthStatus.OFFLINE:
                raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
            
            # Validate service supports chat
            if not service.supports_service(ServiceType.CHAT):
                raise ServiceNotSupportedError(service.name, "chat", service)
            
            # Format messages if string provided
            formatted_messages = messages
            if isinstance(messages, str):
                formatted_messages = [{"role": "user", "content": messages}]
            
            # Build chat parameters
            chat_params = {
                "messages": formatted_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }
            
            # Remove None values
            chat_params = {k: v for k, v in chat_params.items() if v is not None}
            
            # Create a new ChatService with a fresh HTTP client for this event loop
            from .clients.request_client import HTTPClient
            from .services.chat import ChatService
            http_client = HTTPClient()
            try:
                rpc_client = SyftBoxRPCClient(
                    cache_server_url=self.rpc_client.base_url,
                    accounting_client=self.accounting_client,
                    http_client=http_client
                )
                chat_service = ChatService(service, rpc_client)
                return await chat_service.chat_with_params(chat_params)
            finally:
                await http_client.close()
        
        return run_async_in_thread(_chat())
    
    def chat(
            self,
            service_name: str,
            messages: str,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            **kwargs
        ) -> Union[ChatResponse, Awaitable[ChatResponse]]:
        """Smart chat method that adapts to the execution context.
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
            messages: Message to send
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional service-specific parameters
            
        Returns:
            ChatResponse (sync) or Awaitable[ChatResponse] (async)
            
        Examples:
            # In async context (Jupyter, async function):
            response = await client.chat("alice@example.com/gpt-assistant", "Hello")
            
            # In sync context:
            response = client.chat("bob@example.com/creative-writer", "Write a story")
            
            # With parameters:
            response = client.chat(
                "charlie@example.com/code-assistant",
                "Explain this Python function",
                temperature=0.3
            )
        """
        if detect_async_context():
            # Return coroutine - caller must await it
            return self.chat_async(service_name, messages, temperature, max_tokens, **kwargs)
        else:
            # Safe to use thread-based sync version
            return self.chat_sync(service_name, messages, temperature, max_tokens, **kwargs)

    def search_sync(
            self,
            service_name: str, 
            message: str,
            topK: Optional[int] = None,
            similarity_threshold: Optional[float] = None,
            **kwargs
        ) -> SearchResponse:
        """Search with a specific service (sync version).
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
            message: Search message
            topK: Maximum number of results
            similarity_threshold: Minimum similarity score
            **kwargs: Additional service-specific parameters
            
        Returns:
            Search response from the specified service
        """

        # Use thread-based execution with its own event loop
        # This ensures the search runs in a fresh event loop context
        async def _search():
            # Find the specific service
            service = self.get_service(service_name)
            logger.info(f"Using service: {service.name} from datasite: {service.datasite}") 
            
            # Check if service is online by pinging it
            health_status = await check_service_health(service, self.rpc_client, timeout=3.0)
            if health_status == HealthStatus.OFFLINE:
                raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
            
            # Validate service supports search
            if not service.supports_service(ServiceType.SEARCH):
                raise ServiceNotSupportedError(service.name, "search", service)
            
            # Build request parameters
            search_params = {
                "message": message,
                "topK": topK,
                "similarity_threshold": similarity_threshold,
                **kwargs
            }
            
            # Remove None values
            search_params = {k: v for k, v in search_params.items() if v is not None}
            
            # Create a new SearchService with a fresh HTTP client for this event loop
            from .clients.request_client import HTTPClient
            http_client = HTTPClient()
            try:
                rpc_client = SyftBoxRPCClient(
                    cache_server_url=self.rpc_client.base_url,
                    accounting_client=self.accounting_client,
                    http_client=http_client
                )
                search_service = SearchService(service, rpc_client)
                return await search_service.search_with_params(search_params)
            finally:
                await http_client.close()
        
        return run_async_in_thread(_search())
    
    async def search_async(
            self,
            service_name: str, 
            message: str,
            topK: Optional[int] = None,
            similarity_threshold: Optional[float] = None,
            **kwargs
        ) -> SearchResponse:
        """Search with a specific service.
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
            message: Search message
            topK: Maximum number of results
            similarity_threshold: Minimum similarity score
            **kwargs: Additional service-specific parameters
            
        Returns:
            Search response from the specified service
        
        Examples:
            # Basic search
            results = await client.search_async(
                "alice@example.com/document-search",
                "Python tutorial"
            )
            
            # Search with limits
            results = await client.search_async(
                "bob@example.com/code-search", 
                "machine learning algorithms",
                topK=5,
                similarity_threshold=0.7
            )
        """

        # Find the specific service
        service = self.get_service(service_name)
        logger.info(f"Using service: {service.name} from datasite: {service.datasite}") 
        
        # Check if service is online by pinging it
        health_status = await check_service_health(service, self.rpc_client, timeout=3.0)
        if health_status == HealthStatus.OFFLINE:
            raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
        
        # Validate service supports search
        if not service.supports_service(ServiceType.SEARCH):
            raise ServiceNotSupportedError(service.name, "search", service)
        
        # Build request parameters
        search_params = {
            "message": message,
            "topK": topK,
            "similarity_threshold": similarity_threshold,
            **kwargs
        }
        
        # Remove None values
        search_params = {k: v for k, v in search_params.items() if v is not None}
        
        # Create service and make request
        search_service = SearchService(service, self.rpc_client)
        return await search_service.search_with_params(search_params)

    def search(
            self,
            service_name: str, 
            message: str,
            topK: Optional[int] = None,
            similarity_threshold: Optional[float] = None,
            **kwargs
        ) -> Union[SearchResponse, Awaitable[SearchResponse]]:
        """Smart search method that adapts to the execution context.

        Args:
            service_name: Full service name in format 'datasite/service_name'
            message: Search message
            topK: Maximum number of results
            similarity_threshold: Minimum similarity score
            **kwargs: Additional service-specific parameters
            
        Returns:
            SearchResponse (sync) or Awaitable[SearchResponse] (async)
        
        Examples:
            # In async context (Jupyter, async function):
            results = await client.search("alice@example.com/document-search", "Python")
            
            # In sync context:
            results = client.search("bob@example.com/code-search", "algorithms")
            
            # With parameters:
            results = client.search(
                "charlie@example.com/wiki-search",
                "machine learning",
                topK=10,
                similarity_threshold=0.8
            )
        """
        if detect_async_context():
            # Return coroutine - caller must await it
            return self.search_async(service_name, message, topK, similarity_threshold, **kwargs)
        else:
            # Safe to use thread-based sync version
            return self.search_sync(service_name, message, topK, similarity_threshold, **kwargs)

    # Service Parameters
    def get_service_params(self, service_name: str) -> Dict[str, Any]:
        """Get available parameters for a specific service.
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
        
        Returns:
            Dictionary of available parameters for chat and search operations
        
        Examples:
            # Get parameters for a specific service
            params = client.get_service_params("alice@example.com/gpt-assistant")
            print(params["chat"])  # Shows available chat parameters
            print(params["search"])  # Shows available search parameters
        """
        service = self.get_service(service_name)
        if not service:
            raise ServiceNotFoundError(f"Service '{service_name}' not found")
        
        parameters = {}
        
        if service.endpoints and "components" in service.endpoints:
            schemas = service.endpoints["components"].get("schemas", {})
            
            # Extract chat parameters
            chat_request = schemas.get("ChatRequest", {})
            if chat_request:
                parameters["chat"] = self._extract_request_parameters(chat_request, schemas)
            
            # Extract search parameters  
            search_request = schemas.get("SearchRequest", {})
            if search_request:
                parameters["search"] = self._extract_request_parameters(search_request, schemas)
        
        return parameters

    # Display Methods 
    def _format_services(self, 
                   service_type: Optional[ServiceType] = None,
                   health_check: str = "auto",
                   format: str = "table") -> str:
        """List available services in a user-friendly format.
        
        Args:
            service_type: Optional service type filter
            health_check: Health checking mode ("auto", "always", "never")
            format: Output format ("table", "json", "summary")
            
        Returns:
            Formatted string with service information
        """
        services = self.list_services(
            service_type=service_type,
            health_check=health_check
        )
        
        if format == "table":
            return format_services_table(services)
        elif format == "json":
            service_dicts = [self._service_to_dict(service) for service in services]
            return json.dumps(service_dicts, indent=2)
        elif format == "summary":
            return self._format_services_summary(services)
        else:
            return [self._service_to_dict(service) for service in services]
    
    def show_service(self, service_name: str) -> None:
        """Show service information using an HTML widget (similar to client.show()).
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
        
        Examples:
            # Display information for a specific service
            client.show_service("alice@example.com/gpt-assistant")
            
            # Shows service details, parameters, and usage examples
            client.show_service("bob@example.com/document-search")
        """
        service = self.get_service(service_name)
        if not service:
            raise ServiceNotFoundError(f"Service '{service_name}' not found")
        
        service.show()
    
    # Health Monitoring Methods
    async def check_service_health(self, service_name: str, timeout: float = 2.0) -> HealthStatus:
        """Check health of a specific service.
        
        Args:
            service_name: Full service name in format 'datasite/service_name'
            timeout: Timeout for health check
            
        Returns:
            Health status of the service
        
        Examples:
            # Check if a service is online
            status = await client.check_service_health("alice@example.com/gpt-assistant")
            if status == HealthStatus.ONLINE:
                print("Service is ready to use")
            
            # Quick health check with short timeout
            status = await client.check_service_health(
                "bob@example.com/slow-service", 
                timeout=1.0
            )
        """
        service = self.get_service(service_name)
        if not service:
            raise ServiceNotFoundError(f"Service '{service_name}' not found")

        return await check_service_health(service, self.rpc_client, timeout)
    
    async def check_all_services_health(
            self, 
            service_type: Optional[ServiceType] = None,
            timeout: float = 2.0
        ) -> Dict[str, HealthStatus]:
        """Check health of all discovered services.
        
        Args:
            service_type: Optional service type filter
            timeout: Timeout per health check
            
        Returns:
            Dictionary mapping service names to health status
        """
        services = self.list_services(service_type=service_type, health_check="never")
        return await batch_health_check(services, self.rpc_client, timeout)
    
    def start_health_monitoring(
            self, 
            services: Optional[List[str]] = None,
            check_interval: float = 30.0
        ) -> HealthMonitor:
        """Start continuous health monitoring.
        
        Args:
            services: Optional list of service names to monitor (default: all chat/search services)
            check_interval: Seconds between health checks
            
        Returns:
            HealthMonitor instance
        """
        if self._health_monitor:
            logger.warning("Health monitoring already running")
            return self._health_monitor
        
        self._health_monitor = HealthMonitor(self.rpc_client, check_interval)
        
        # Add services to monitor
        if services:
            for service_name in services:
                service = self.get_service(service_name)
                if service:
                    self._health_monitor.add_service(service)
        else:
            # Monitor all enabled chat/search services
            all_services = self.list_services(health_check="never")
            for service in all_services:
                if service.supports_service(ServiceType.CHAT) or service.supports_service(ServiceType.SEARCH):
                    self._health_monitor.add_service(service)
        
        # Start monitoring
        asyncio.create_task(self._health_monitor.start_monitoring())
        
        return self._health_monitor
    
    async def stop_health_monitoring(self):
        """Stop health monitoring."""
        if self._health_monitor:
            await self._health_monitor.stop_monitoring()
            self._health_monitor = None

    # RAG pipeline methods
    def create_pipeline(self) -> Pipeline:
        """Create a new pipeline for RAG workflows.
        
        .. deprecated:: 1.0.0
            Use :func:`pipeline` instead for more convenient inline configuration.
        
        Returns:
            Empty Pipeline that requires further configuration
            
        Note:
            This method is deprecated. Use ``client.pipeline()`` with parameters
            for a more convenient experience.
        """
        import warnings
        warnings.warn(
            "create_pipeline() is deprecated and will be removed in v2.0. "
            "Use client.pipeline(data_sources=..., synthesizer=...) instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return Pipeline(client=self)

    def pipeline(self, data_sources: Optional[List[Union[str, Dict, 'Service']]] = None, 
                synthesizer: Optional[Union[str, Dict, 'Service']] = None, 
                context_format: Optional[str] = None) -> Pipeline:
        """Create and configure a pipeline for RAG/FedRAG workflows.
        
        Args:
            data_sources: List of search services to use as data sources. Each item can be:
                - str: Service name like "alice@example.com/docs"
                - dict: Service with params like {"name": "service", "topK": 10}
                - Service: Loaded service object from client.load_service()
            synthesizer: Chat service to use for synthesis. Can be:
                - str: Service name like "ai@openai.com/gpt-4"
                - dict: Service with params like {"name": "service", "temperature": 0.7}
                - Service: Loaded service object
            context_format: Format for search context injection (default: "simple")
                - "simple": Clean format with ## headers for each source
                - "frontend": Matches web app format with [filename] headers
        
        Returns:
            Configured Pipeline ready for execution with .run() or .run_async()
        
        Examples:
            # Simple usage
            result = client.pipeline(
                data_sources=["alice@example.com/docs", "bob@example.com/wiki"],
                synthesizer="ai@openai.com/gpt-4"
            ).run(messages=[{"role": "user", "content": "What is Python?"}])
            
            # With parameters and Service objects
            service = client.load_service("alice@example.com/docs")
            result = client.pipeline(
                data_sources=[service, {"name": "bob@example.com/wiki", "topK": 5}],
                synthesizer={"name": "ai@openai.com/gpt-4", "temperature": 0.7},
                context_format="frontend"
            ).run(messages=[{"role": "user", "content": "Compare these docs"}])
        """
        return Pipeline(
            client=self, 
            data_sources=data_sources, 
            synthesizer=synthesizer,
            context_format=context_format or "simple"
        )

    # Accounting Integration Methods
    async def _register_accounting_async(self, email: str, password: str, organization: Optional[str] = None):
        """Register a new accounting user (async)."""
        try:
            self.accounting_client.register_accounting(email, password, organization)
            self.accounting_client.save_credentials()
            await self._connect_accounting_async(email, password, self.accounting_client.accounting_url)
            logger.info("Accounting setup completed and connected successfully")
        except Exception as e:
            raise AuthenticationError(f"Accounting setup failed: {e}")

    def register_accounting(self, email: str, password: str, organization: Optional[str] = None):
        """Register a new accounting user (sync wrapper)."""
        return run_async_in_thread(
            self._register_accounting_async(email, password, organization)
        )

    async def _connect_accounting_async(self, email: str, password: str, accounting_url: Optional[str] = None, save_config: bool = True):
        """Setup accounting credentials (async)."""
        # Get service URL from environment if not provided
        if not accounting_url:
            accounting_url = self.accounting_client.accounting_url
            
        if accounting_url is None:
            accounting_url = os.getenv('SYFTBOX_ACCOUNTING_URL')

        if not accounting_url:
            raise ValueError(
                "Accounting service URL is required. Please either:\n"
                "1. Set SYFTBOX_ACCOUNTING_URL in your .env file, or\n"
                "2. Pass accounting_url parameter to this method"
            )
        
        try:
            # Configure the accounting client
            self.accounting_client.configure(accounting_url, email, password)
            
            # Save config if explicitly requested
            if save_config:
                self.accounting_client.save_credentials()

            logger.info(f"Accounting setup successful for {self.accounting_client.get_email()}")

        except Exception as e:
            raise AuthenticationError(f"Accounting setup failed: {e}")
        
    def connect_accounting(self, email: str, password: str, accounting_url: Optional[str] = None, save_config: bool = True):
        """Setup accounting credentials (sync wrapper)."""
        return run_async_in_thread(
            self._connect_accounting_async(email, password, accounting_url, save_config)
        )

    def is_accounting_configured(self) -> bool:
        """Check if accounting is properly configured."""
        return self.accounting_client.is_configured()

    async def _get_account_info_async(self) -> Dict[str, Any]:
        """Get account information and balance (async)."""
        if not self.is_accounting_configured():
            return {"error": "Accounting not configured"}
        
        try:
            return await self.accounting_client.get_account_info()
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {"error": str(e)}

    def get_account_info(self) -> Dict[str, Any]:
        """Get account information and balance (sync wrapper)."""
        if not self.is_accounting_configured():
            return {"error": "Accounting not configured"}
        
        try:
            return run_async_in_thread(self._get_account_info_async())
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {"error": str(e)}

    async def _get_accounting_status_async(self) -> str:
        """Show current accounting configuration status (async)."""
        if not self.is_accounting_configured():
            return (
                "Accounting not configured\n"
                "   Use client.connect_accounting() to configure payment services\n"
                "   Currently limited to free services only"
            )
        
        try:
            account_info = await self._get_account_info_async()

            if "error" in account_info:
                return (
                    f"Accounting configured but connection failed\n"
                    f"   Error: {account_info['error']}\n"
                    f"   May need to reconfigure credentials"
                )
            
            return (
                f"Accounting configured\n"
                f"   Email: {account_info['email']}\n" 
                f"   Balance: ${account_info['balance']}\n"
                f"   Can use both free and paid services"
            )
        except Exception as e:
            return (
                f"Accounting configured but connection failed\n"
                f"   Error: {e}\n"
                f"   May need to reconfigure credentials"
            )

    def get_accounting_status(self) -> str:
        """Show current accounting configuration status (sync wrapper)."""
        return run_async_in_thread(self._get_accounting_status_async())
    
    # Display Methods
    def show_services(self, health_check: str = "always", **kwargs) -> None:
        """Display available services using ServicesList's show_services method.
        
        Args:
            health_check: Health checking mode ("auto", "always", "never")
                - "always": Always check health status (shows real availability)
                - "never": Skip health checks (faster, shows Unknown)
                - "auto": Check only if ≤10 services (default threshold)
            **kwargs: Arguments to pass to ServicesList.show_services()
                page: Starting page number
                items_per_page: Services per page
                current_user_email: Current user's email for context
                save_to_file: Force save to file even in notebooks
                output_path: Custom output path for HTML file
                open_in_browser: Force open in browser even in Jupyter notebooks
        """
        try:
            services_list = self.list_services(health_check=health_check)
            # ServicesList has its own show_services method
            services_list.show_services(**kwargs)
        except Exception as e:
            logger.error(f"Failed to show services: {e}")
            # Fallback display
            from IPython.display import display, HTML
            html = '''
            <div style="font-family: system-ui, -apple-system, sans-serif; padding: 12px 0; color: #333;">
                <div style="font-size: 14px; font-weight: 600; margin-bottom: 12px;">Available Services</div>
                <div style="color: #999; font-style: italic; font-size: 13px;">
                    Error loading services. Make sure SyftBox is running.
                </div>
            </div>
            '''
            display(HTML(html))
    
    def show(self) -> None:
        """Display client status as an HTML widget."""
        from IPython.display import display, HTML
        
        # Get status information
        syftbox_status = "Running" if self.config_manager.is_syftbox_running() else "Not Running"
        syftbox_path = str(self.config.data_dir)
        cache_server = self.config.cache_server_url
        account_email = self.accounting_client.get_email() if self._account_configured else None
        
        # Count available services
        try:
            services = self.list_services()
            service_count = len(services) if services else 0
        except:
            service_count = 0
        
        # Build HTML widget with minimal notebook-like styling
        html = '''
        <style>
            .syfthub-widget {
                font-family: system-ui, -apple-system, sans-serif;
                padding: 12px 0;
                color: #333;
                line-height: 1.5;
            }
            .widget-title {
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 12px;
                color: #333;
            }
            .status-line {
                display: flex;
                align-items: center;
                margin: 6px 0;
                font-size: 13px;
            }
            .status-label {
                color: #666;
                min-width: 140px;
                margin-right: 12px;
            }
            .status-value {
                font-family: monospace;
                color: #333;
            }
            .status-badge {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 11px;
                margin-left: 8px;
            }
            .badge-ready {
                background: #d4edda;
                color: #155724;
            }
            .badge-not-ready {
                background: #f8d7da;
                color: #721c24;
            }
            .docs-section {
                margin-top: 16px;
                padding-top: 12px;
                border-top: 1px solid #e0e0e0;
                font-size: 12px;
                color: #666;
            }
            .command-code {
                font-family: monospace;
                background: #f5f5f5;
                padding: 1px 4px;
                border-radius: 2px;
                color: #333;
            }
        </style>
        '''
        
        # Determine badges
        syftbox_badge = '<span class="status-badge badge-ready">Running</span>' if syftbox_status == "Running" else '<span class="status-badge badge-not-ready">Not Running</span>'
        account_badge = '<span class="status-badge badge-ready">Configured</span>' if self._account_configured else '<span class="status-badge badge-not-ready">Not Configured</span>'
        
        html += f'''
        <div class="syfthub-widget">
            <div class="widget-title">
                SyftHub Client {syftbox_badge}
            </div>
            
            <div class="status-line">
                <span class="status-label">SyftBox Path:</span>
                <span class="status-value">{syftbox_path}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Cache Server:</span>
                <span class="status-value">{cache_server}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Account:</span>
                <span class="status-value">{account_email or "Not configured"}</span>
                {account_badge}
            </div>
            
            <div class="status-line">
                <span class="status-label">Services Found:</span>
                <span class="status-value">{service_count} services</span>
            </div>
            
            <div class="docs-section">
                <div style="margin-bottom: 8px; font-weight: 500;">Common operations:</div>
                <div style="line-height: 1.8;">
                    <span class="command-code">client.list_services()</span> — Discover available services<br>
                    <span class="command-code">client.chat("service", messages=[])</span> — Chat with a service<br>
                    <span class="command-code">client.search("service", "message")</span> — Search with a service<br>
                    <span class="command-code">client.register_accounting(email)</span> — Register accounting<br>
                    <span class="command-code">client.connect_accounting(email, password)</span> — Connect accounting
                </div>
            </div>
        </div>
        '''
        
        display(HTML(html))
    
    def __repr__(self) -> str:
        """Return a text representation of the client's status."""
        # Get status information
        syftbox_status = "Running" if self.config_manager.is_syftbox_running() else "Not Running"
        syftbox_path = str(self.config.data_dir)
        cache_server = self.config.cache_server_url
        account_email = self.accounting_client.get_email() if self._account_configured else None
        
        # Count available services
        try:
            services = self.list_services()
            service_count = len(services) if services else 0
        except:
            service_count = 0
        
        # Build text output
        lines = [
            f"SyftHub Client [{syftbox_status}]",
            f"",
            f"SyftBox Path:     {syftbox_path}",
            f"Cache Server:     {cache_server}",
            f"Account:          {account_email or 'Not configured'}",
            f"Services:         {service_count} services found",
            f"",
            f"Common operations:",
            f"  client.list_services()                    — Discover available services",
            f"  client.chat('datasite/service', messages=[])       — Chat with a service",
            f"  client.search('datasite/service', 'message')       — Search with a service",
            f"  client.register_accounting(email)         — Register account",
            f"  client.connect_accounting(email, password) — Connect account"
        ]
        
        return "\n".join(lines)
    
    def _repr_html_(self) -> str:
        """Display HTML widget in Jupyter environments - same as show()."""
        # Get status information
        syftbox_status = "Running" if self.config_manager.is_syftbox_running() else "Not Running"
        syftbox_path = str(self.config.data_dir)
        cache_server = self.config.cache_server_url
        account_email = self.accounting_client.get_email() if self._account_configured else None
        
        # Count available services
        try:
            services = self.list_services()
            service_count = len(services) if services else 0
        except:
            service_count = 0
        
        # Build HTML widget with minimal notebook-like styling (same as show())
        html = '''
        <style>
            .syfthub-widget {
                font-family: system-ui, -apple-system, sans-serif;
                padding: 12px 0;
                color: #333;
                line-height: 1.5;
            }
            .widget-title {
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 12px;
                color: #333;
            }
            .status-line {
                display: flex;
                align-items: center;
                margin: 6px 0;
                font-size: 13px;
            }
            .status-label {
                color: #666;
                min-width: 140px;
                margin-right: 12px;
            }
            .status-value {
                font-family: monospace;
                color: #333;
            }
            .status-badge {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 11px;
                margin-left: 8px;
            }
            .badge-ready {
                background: #d4edda;
                color: #155724;
            }
            .badge-not-ready {
                background: #f8d7da;
                color: #721c24;
            }
            .docs-section {
                margin-top: 16px;
                padding-top: 12px;
                border-top: 1px solid #e0e0e0;
                font-size: 12px;
                color: #666;
            }
            .command-code {
                font-family: monospace;
                background: #f5f5f5;
                padding: 1px 4px;
                border-radius: 2px;
                color: #333;
            }
        </style>
        '''
        
        # Determine badges
        syftbox_badge = '<span class="status-badge badge-ready">Running</span>' if syftbox_status == "Running" else '<span class="status-badge badge-not-ready">Not Running</span>'
        account_badge = '<span class="status-badge badge-ready">Configured</span>' if self._account_configured else '<span class="status-badge badge-not-ready">Not Configured</span>'
        
        html += f'''
        <div class="syfthub-widget">
            <div class="widget-title">
                SyftHub Client {syftbox_badge}
            </div>
            
            <div class="status-line">
                <span class="status-label">SyftBox Path:</span>
                <span class="status-value">{syftbox_path}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Cache Server:</span>
                <span class="status-value">{cache_server}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Account:</span>
                <span class="status-value">{account_email or "Not configured"}</span>
                {account_badge}
            </div>
            
            <div class="status-line">
                <span class="status-label">Services Found:</span>
                <span class="status-value">{service_count} services</span>
            </div>
            
            <div class="docs-section">
                <div style="margin-bottom: 8px; font-weight: 500;">Common operations:</div>
                <div style="line-height: 1.8;">
                    <span class="command-code">client.list_services()</span> — Discover available services<br>
                    <span class="command-code">client.chat("datasite/service", "message")</span> — Chat with a service<br>
                    <span class="command-code">client.search("datasite/service", "message")</span> — Search with a service<br>
                    <span class="command-code">client.register_accounting(email)</span> — Register account<br>
                    <span class="command-code">client.connect_accounting(email, password)</span> — Connect account
                </div>
            </div>
        </div>
        '''
        
        return html
    
    # Updated Service Usage Methods
    def clear_cache(self):
        """Clear the service discovery cache."""
        self._scanner.clear_cache()
    
    # Private helper methods
    def _extract_request_parameters(self, request_schema: Dict[str, Any], all_schemas: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters from request schema."""
        parameters = {}
        properties = request_schema.get("properties", {})
        required_fields = set(request_schema.get("required", []))
        
        # Skip system fields
        skip_fields = {"userEmail", "service", "messages", "query", "transactionToken"}
        
        for field_name, field_info in properties.items():
            if field_name in skip_fields:
                continue
                
            param_info = {
                "required": field_name in required_fields,
                "description": field_info.get("description", "")
            }
            
            # Handle direct type
            if "type" in field_info:
                param_info["type"] = field_info["type"]
                self._add_constraints(param_info, field_info)
            
            # Handle $ref
            elif "$ref" in field_info:
                ref_name = field_info["$ref"].split("/")[-1]
                if ref_name in all_schemas:
                    nested = self._extract_schema_properties(all_schemas[ref_name])
                    param_info.update(nested)
            
            # Handle anyOf (optional references)
            elif "anyOf" in field_info:
                for option in field_info["anyOf"]:
                    if "$ref" in option:
                        ref_name = option["$ref"].split("/")[-1]
                        if ref_name in all_schemas:
                            nested = self._extract_schema_properties(all_schemas[ref_name])
                            param_info.update(nested)
                            break
                    elif "type" in option and option["type"] != "null":
                        param_info["type"] = option["type"]
                        self._add_constraints(param_info, option)
            
            parameters[field_name] = param_info
        
        return parameters

    def _extract_schema_properties(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Extract properties from nested schema."""
        result = {"type": "object", "properties": {}}
        properties = schema.get("properties", {})
        
        for prop_name, prop_info in properties.items():
            if prop_name == "extensions":
                continue
                
            prop_data = {
                "description": prop_info.get("description", ""),
                "required": False
            }
            
            if "type" in prop_info:
                prop_data["type"] = prop_info["type"]
                self._add_constraints(prop_data, prop_info)
            elif "anyOf" in prop_info:
                for option in prop_info["anyOf"]:
                    if "type" in option and option["type"] != "null":
                        prop_data["type"] = option["type"]
                        self._add_constraints(prop_data, option)
                        break
            
            result["properties"][prop_name] = prop_data
        
        return result

    def _add_constraints(self, param_info: Dict[str, Any], field_info: Dict[str, Any]):
        """Add validation constraints to parameter info."""
        for constraint in ["minimum", "maximum", "enum", "format"]:
            if constraint in field_info:
                param_info[constraint] = field_info[constraint]

    def _should_do_health_check(self, health_check: str, service_count: int) -> bool:
        """Determine if health checking should be performed."""
        if health_check == "always":
            return True
        elif health_check == "never":
            return False
        elif health_check == "auto":
            return service_count <= self._auto_health_check_threshold
        else:
            raise ValueError(f"Invalid health_check value: {health_check}")
    
    async def _add_health_status(self, services: List[ServiceInfo]) -> List[ServiceInfo]:
        """Add health status to services."""
        health_status = await batch_health_check(services, self.rpc_client, timeout=2.0)
        
        for service in services:
            service.health_status = health_status.get(service.name, HealthStatus.UNKNOWN)
        
        return services
    
    def _service_to_dict(self, service: ServiceInfo) -> Dict[str, Any]:
        """Convert ServiceInfo to dictionary for JSON serialization."""
        return {
            "name": service.name,
            "datasite": service.datasite,
            "summary": service.summary,
            "description": service.description,
            "tags": service.tags,
            "services": [
                {
                    "type": service.type.value,
                    "enabled": service.enabled,
                    "pricing": service.pricing,
                    "charge_type": service.charge_type.value
                }
                for service in service.services
            ],
            "config_status": service.config_status.value,
            "health_status": service.health_status.value if service.health_status else None,
            "delegate_email": service.delegate_email,
            "min_pricing": service.min_pricing,
            "max_pricing": service.max_pricing
        }
    
    def _format_services_summary(self, services: List[ServiceInfo]) -> str:
        """Format services as a summary."""
        if not services:
            return "No services found."
        
        lines = [f"Found {len(services)} services:\n"]
        
        # Group by datasite
        by_datasite = {}
        for service in services:
            if service.datasite not in by_datasite:
                by_datasite[service.datasite] = []
            by_datasite[service.datasite].append(service)
        
        for datasite, datasite_services in sorted(by_datasite.items()):
            lines.append(f"📧 {datasite} ({len(datasite_services)} services)")
            
            for service in sorted(datasite_services, key=lambda m: m.name):
                services = ", ".join([s.type.value for s in service.services if s.enabled])
                pricing = f"${service.min_pricing}" if service.min_pricing > 0 else "Free"
                health = ""
                if service.health_status:
                    if service.health_status == HealthStatus.ONLINE:
                        health = " ✅"
                    elif service.health_status == HealthStatus.OFFLINE:
                        health = " ❌"
                    elif service.health_status == HealthStatus.TIMEOUT:
                        health = " ⏱️"
                
                lines.append(f"  • {service.name} ({services}) - {pricing}{health}")
            
            lines.append("")  # Empty line between datasites
        
        return "\n".join(lines)

    def format_search_context(self, results: List[DocumentResult], format_type: str = "simple") -> str:
        """Format search results as context for chat injection.
        
        Args:
            results: Search results to format
            format_type: "frontend" (matches web app) or "simple"
            
        Returns:
            Formatted context string
        """
        if not results:
            return ""
        
        if format_type == "frontend":
            # Match the exact frontend pattern: [filename]\nContent
            formatted_parts = []
            for result in results:
                filename = result.metadata.get("filename", "unknown") if result.metadata else "unknown"
                formatted_parts.append(f"[{filename}]\n{result.content}")
            
            return "\n\n".join(formatted_parts)
        
        elif format_type == "simple":
            # Cleaner format for direct SDK usage
            formatted_parts = []
            for i, result in enumerate(results, 1):
                source = result.metadata.get("filename", f"Source {i}") if result.metadata else f"Source {i}"
                formatted_parts.append(f"## {source}\n{result.content}")
            
            return "\n\n".join(formatted_parts)
        
        else:
            raise ValidationError(f"Unknown context format: {format_type}")

    def remove_duplicate_results(self, results: List[DocumentResult]) -> List[DocumentResult]:
        """Remove duplicate results based on content similarity.
        
        Args:
            results: List of search results
            
        Returns:
            Deduplicated list of results
        """
        if not results:
            return results
        
        # Simple deduplication based on content hash
        seen_hashes = set()
        unique_results = []
        
        for result in results:
            content_hash = hash(result.content.strip().lower())
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_results.append(result)
        
        return unique_results
    
    # TODO: Payment Handling - called internally before paid service use
    async def _ensure_payment_setup(self, service: ServiceInfo) -> Optional[str]:
        """Ensure payment is set up for a paid service.
        
        Args:
            service: Service that requires payment
            
        Returns:
            Transaction token if payment required, None if free
        """
        # Check if service requires payment
        service_info = None
        if service.supports_service(ServiceType.CHAT):
            service_info = service.get_service_info(ServiceType.CHAT)
        elif service.supports_service(ServiceType.SEARCH):
            service_info = service.get_service_info(ServiceType.SEARCH)
        
        # Early return for free services - skip all accounting logic entirely
        if not service_info or service_info.pricing == 0:
            return None  # Free service
        
        # Service requires payment - ensure accounting is set up
        if not self.is_accounting_configured():
            if self._auto_setup_accounting:
                print(f"\nPayment Required")
                print(f"Service '{service.name}' costs ${service_info.pricing} per request")
                print(f"Datasite: {service.datasite}")
                print(f"\nAccounting setup required for paid services.")
                
                try:
                    response = input("Would you like to set up accounting now? (y/n): ").lower().strip()
                    if response in ['y', 'yes']:
                        # Interactive setup would go here
                        print("Please use below to configure:\n")
                        print("     client.register_accounting(email, password) to configure.")
                        return None
                    else:
                        print("Payment setup skipped.")
                        return None
                except (EOFError, KeyboardInterrupt):
                    print("\nPayment setup cancelled.")
                    return None
            else:
                from .core.exceptions import PaymentError
                raise PaymentError(
                    f"Service '{service.name}' requires payment (${service_info.pricing}) "
                    "but accounting is not configured"
                )
        
        # Create transaction token????????
        try:
            token = await self.accounting_client.create_transaction_token(service.datasite)
            logger.info(f"Payment authorized: ${service_info.pricing} to {service.datasite}")
            return token
        except Exception as e:
            from .core.exceptions import PaymentError
            raise PaymentError(f"Failed to create payment token: {e}")
        