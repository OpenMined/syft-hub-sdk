"""
Service class for object-oriented service interaction
"""
from typing import List, TYPE_CHECKING

from ..core.types import ServiceType
# from ..models.service_info import ServiceInfo
from .exceptions import ServiceNotSupportedError

if TYPE_CHECKING:
    from ..main import Client
    from ..models.service_info import ServiceInfo

class Service:
    """Object-oriented interface for a loaded SyftBox service."""
    
    def __init__(self, service_info: 'ServiceInfo', client: 'Client'):
        self._service_info = service_info
        self._client = client
    
    # Properties
    @property
    def name(self) -> str:
        """Service name (without datasite prefix)."""
        return self._service_info.name
    
    @property
    def datasite(self) -> str:
        """Datasite email that owns this service."""
        return self._service_info.datasite
    
    @property
    def full_name(self) -> str:
        """Full service identifier: datasite/name."""
        return f"{self.datasite}/{self.name}"
    
    @property
    def cost(self) -> float:
        """Minimum cost per request for this service."""
        return self._service_info.min_pricing
    
    @property
    def supports_chat(self) -> bool:
        """Whether this service supports chat operations."""
        return self._service_info.supports_service(ServiceType.CHAT)
    
    @property
    def supports_search(self) -> bool:
        """Whether this service supports search operations."""
        return self._service_info.supports_service(ServiceType.SEARCH)
    
    @property
    def summary(self) -> str:
        """Brief description of the service."""
        return self._service_info.summary or ""
    
    @property
    def tags(self) -> List[str]:
        """Tags associated with this service."""
        return self._service_info.tags or []
    
    def __contains__(self, capability: str) -> bool:
        """Support 'chat' in service or 'search' in service syntax."""
        if capability == 'chat':
            return self.supports_chat
        elif capability == 'search':
            return self.supports_search
        return False
    
    def show(self) -> None:
        """Display comprehensive service information as an HTML widget in notebooks."""
        try:
            from IPython.display import display, HTML
        except ImportError:
            # Fallback to text representation if not in a notebook
            print(self.__repr__())
            return
        
        # Get service info
        service_info = self._service_info
        service_name = service_info.name
        datasite = service_info.datasite
        summary = service_info.summary
        description = service_info.description if service_info.description != summary else ""
        status = service_info.config_status.value
        
        # Get enabled services with details
        enabled_services = []
        total_cost = 0
        for service_item in service_info.services:
            if service_item.enabled:
                enabled_services.append({
                    'type': service_item.type.value.title(),
                    'cost': service_item.pricing,
                    'charge_type': service_item.charge_type.value
                })
                total_cost += service_item.pricing
        
        # Health status
        health_class = ""
        health_text = ""
        if service_info.health_status:
            from ..core.types import HealthStatus
            health_map = {
                HealthStatus.ONLINE: ("online", "Online"),
                HealthStatus.OFFLINE: ("offline", "Offline"), 
                HealthStatus.TIMEOUT: ("timeout", "Timeout"),
                HealthStatus.UNKNOWN: ("unknown", "Unknown")
            }
            health_class, health_text = health_map.get(service_info.health_status, ("unknown", "Unknown"))
        
        # Pricing info
        pricing_str = "Free" if total_cost == 0 else f"${total_cost:.2f}/request"
        pricing_class = "free" if total_cost == 0 else "paid"
        
        # Tags
        tags_display = ", ".join(service_info.tags) if service_info.tags else "None"
        
        # Technical details
        version = service_info.version or "Not specified"
        code_hash = service_info.code_hash[:12] + "..." if service_info.code_hash else "Not available"
        publish_date = service_info.publish_date.strftime("%Y-%m-%d") if service_info.publish_date else "Unknown"
        
        # Delegate info
        delegate_info = ""
        if service_info.delegate_email:
            delegate_info = f"<div class='service-label'>Delegate:</div><div class='service-value'>{service_info.delegate_email}</div>"
        
        # Services details HTML
        services_html = ""
        if enabled_services:
            for service in enabled_services:
                cost_text = f"${service['cost']:.2f}/{service['charge_type']}" if service['cost'] > 0 else "Free"
                cost_class = "paid" if service['cost'] > 0 else "free"
                services_html += f'<div class="service-item"><span class="service-type">{service["type"]}</span> <span class="service-cost {cost_class}">{cost_text}</span></div>'
        else:
            services_html = '<div class="service-item">No enabled services</div>'
        
        
        # Parse examples for better HTML display
        chat_examples = []
        search_examples = []
        if self.supports_chat:
            chat_examples = [
                f'service.chat("Hello! How are you?")',
                f'service.chat(messages=[{{"role": "user", "content": "Write a story"}}], temperature=0.7, max_tokens=200)',
                f'client.chat("{datasite}/{service_name}", "Hello!")'
            ]
        
        if self.supports_search:
            search_examples = [
                f'service.search("machine learning")',
                f'service.search(message="latest AI research", topK=10, similarity_threshold=0.8)',
                f'client.search("{datasite}/{service_name}", "machine learning")'
            ]
        
        
        # Create HTML example strings with proper newlines
        chat_example_html = '''
<span style="color: #6c757d;"># Chat with parameters</span>
response = service.chat(
    messages=[
        {"role": "user", "content": "Write a short story about AI"}
    ],
    temperature=0.7,
    max_tokens=200
)
print(response.content)'''

        search_example_html = '''

<span style="color: #6c757d;"># Search with the service</span>
results = service.search("machine learning")
for result in results:
    print(result.content, result.score)

<span style="color: #6c757d;"># Search with parameters</span>
results = service.search(
    message="latest AI research", 
    topK=10,
    similarity_threshold=0.8
)'''
        
        # Build comprehensive HTML widget with adaptive theming
        from ..utils.theme import generate_adaptive_css
        
        # Custom styles specific to service widgets
        service_styles = {
            '.service-obj-widget': {
                'max-width': '900px',
                'padding': '16px 0',
                'font-family': 'system-ui, -apple-system, sans-serif',
                'line-height': '1.5'
            },
            '.service-obj-title': {
                'font-size': '16px',
                'font-weight': '600',
                'margin-bottom': '8px',
                'display': 'flex',
                'align-items': 'center',
                'gap': '12px'
            },
            '.service-obj-status-line': {
                'display': 'flex',
                'align-items': 'center',
                'margin': '6px 0',
                'font-size': '11px'
            },
            '.service-obj-status-label': {
                'min-width': '140px',
                'margin-right': '12px',
                'font-weight': '500'
            },
            '.service-obj-status-value': {
                'font-family': 'monospace',
                'font-size': '11px'
            },
            '.service-obj-status-badge': {
                'display': 'inline-block',
                'padding': '3px 8px',
                'border-radius': '12px',
                'font-size': '11px',
                'font-weight': '500',
                'margin-left': '8px'
            },
            '.service-obj-docs-section': {
                'margin-top': '20px',
                'padding': '16px',
                'border-top': '1px solid var(--border-color, #e0e0e0)',
                'font-size': '11px'
            },
            '.service-obj-section-header': {
                'font-size': '13px',
                'font-weight': '600',
                'margin-bottom': '12px',
                'text-transform': 'uppercase',
                'letter-spacing': '0.5px'
            },
            '.service-obj-command-code': {
                'font-family': 'Monaco, "Courier New", monospace',
                'padding': '8px 12px',
                'border-radius': '4px',
                'margin': '4px 0',
                'display': 'block',
                'border-left': '3px solid var(--accent-color, #007bff)'
            },
            '.service-obj-description': {
                'font-size': '11px',
                'line-height': '1.6',
                'margin': '12px 0',
                'padding': '12px',
                'border-radius': '4px',
                'border': '1px solid var(--border-color, #e9ecef)'
            }
        }
        
        html = generate_adaptive_css('service-obj', service_styles)
        
        html += f'''
        <div class="syft-widget">
            <div class="service-obj-widget">
                <div class="service-obj-title">
                {service_name} Service{f' <span class="service-obj-status-badge service-obj-badge-{health_class}">{health_text}</span>' if health_text else ""}
            </div>
            
            <div class="service-obj-status-line">
                <span class="service-obj-status-label">Datasite:</span>
                <span class="service-obj-status-value">{datasite}</span>
            </div>
            <div class="service-obj-status-line">
                <span class="service-obj-status-label">Summary:</span>
                <span class="service-obj-status-value">{summary}</span>
            </div>
            <div class="service-obj-status-line">
                <span class="service-obj-status-label">Total Cost:</span>
                <span class="service-obj-status-value" style="color: {'#28a745' if total_cost == 0 else '#dc3545'}; font-weight: 600;">{pricing_str}</span>
            </div>
            <div class="service-obj-status-line">
                <span class="service-obj-status-label">Tags:</span>
                <span class="service-obj-status-value">{tags_display}</span>
            </div>
            <div class="service-obj-status-line">
                <span class="service-obj-status-label">Version:</span>
                <span class="service-obj-status-value">{version}</span>
            </div>
            <div class="service-obj-status-line">
                <span class="service-obj-status-label">Published:</span>
                <span class="service-obj-status-value">{publish_date}</span>
            </div>
            {f'<div class="service-obj-status-line"><span class="service-obj-status-label">Delegate:</span><span class="service-obj-status-value">{service_info.delegate_email}</span></div>' if service_info.delegate_email else ''}
            
            {f'<div class="service-obj-description"><strong>Description:</strong></div>{self._render_description_as_markdown(description)}' if description else ''}
            
            <div class="service-obj-docs-section">
                <div class="service-obj-section-header">Available Services</div>
                <div class="service-obj-services-grid">
                    {services_html.replace('class="service-item"', 'class="service-obj-service-card"').replace('class="service-type"', 'class="service-obj-service-card-title"').replace('class="service-cost', 'class="service-obj-service-card-cost')}
                </div>
            </div>
            
            <div class="service-obj-docs-section">
                <div class="service-obj-section-header">For Usage Examples</div>
                <div style="margin-top: 12px; font-size: 11px; color: #666; padding: 8px; background: var(--syft-secondary-bg, #f8f9fa); border-radius: 4px;">
                    Call <span class="command-code">service.show_example()</span> to see detailed usage examples
                </div>
            </div>
        </div>
        '''
        
        display(HTML(html))
    
    def __repr__(self) -> str:
        """Display service info only (no usage examples) when service object is displayed directly."""
        try:
            from IPython.display import display, HTML
            # In notebook environment, show just the service info using ServiceInfo's show method
            self._service_info.show()
            return ""  # Return empty string to avoid double output
        except ImportError:
            # Not in notebook - provide comprehensive text representation
            service_info = self._service_info
            
            # Basic info with health status like client's "Running"
            health_status_text = ""
            if service_info.health_status:
                from ..core.types import HealthStatus
                if service_info.health_status == HealthStatus.ONLINE:
                    health_status_text = " [Online]"
                elif service_info.health_status == HealthStatus.OFFLINE:
                    health_status_text = " [Offline]"
                elif service_info.health_status == HealthStatus.TIMEOUT:
                    health_status_text = " [Timeout]"
            
            lines = [
                f"{self.name} Service{health_status_text}",
                "",
                f"Datasite:         {self.datasite}",
                f"Summary:          {service_info.summary}",
            ]
            
            # Services
            enabled_services = []
            total_cost = 0
            for service_item in service_info.services:
                if service_item.enabled:
                    cost_str = f"${service_item.pricing:.2f}" if service_item.pricing > 0 else "Free"
                    enabled_services.append(f"{service_item.type.value.title()} ({cost_str})")
                    total_cost += service_item.pricing
            
            services_str = ", ".join(enabled_services) if enabled_services else "None"
            lines.append(f"Services:         {services_str}")
            
            # Overall pricing
            pricing_str = "Free" if total_cost == 0 else f"${total_cost:.2f}/request"
            lines.append(f"Total Cost:       {pricing_str}")
            
            # Health status
            if service_info.health_status:
                from ..core.types import HealthStatus
                health_map = {
                    HealthStatus.ONLINE: "✅ Online",
                    HealthStatus.OFFLINE: "❌ Offline", 
                    HealthStatus.TIMEOUT: "⏱️ Timeout",
                    HealthStatus.UNKNOWN: "❓ Unknown"
                }
                health_str = health_map.get(service_info.health_status, "❓ Unknown")
                lines.append(f"Health:           {health_str}")
            
            # Tags
            if service_info.tags:
                tags_display = ", ".join(service_info.tags[:4])
                if len(service_info.tags) > 4:
                    tags_display += f" (+{len(service_info.tags) - 4} more)"
                lines.append(f"Tags:             {tags_display}")
            
            # Technical details
            if service_info.version:
                lines.append(f"Version:          {service_info.version}")
            
            if service_info.delegate_email:
                lines.append(f"Delegate:         {service_info.delegate_email}")
            
            # Usage examples
            lines.extend([
                "",
                "Usage examples:",
                f"  service = client.load_service('{self.full_name}')",
            ])
            
            if self.supports_chat:
                health_icon = "✅" if service_info.is_healthy else "❌" if service_info.health_status and not service_info.is_healthy else ""
                health_display = f" {health_icon}" if health_icon else ""
                lines.append(f"  service.chat(messages=[...])              — Chat with service{health_display}")
            if self.supports_search:
                health_icon = "✅" if service_info.is_healthy else "❌" if service_info.health_status and not service_info.is_healthy else ""
                health_display = f" {health_icon}" if health_icon else ""
                lines.append(f"  service.search('message')                 — Search with service{health_display}")
            
            return "\n".join(lines)
    
    
    # Service methods (always present, error if not supported)
    def chat(self, messages, **kwargs):
        """Chat with this service synchronously.
        
        Args:
            messages: Chat messages to send
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
            
        Returns:
            ChatResponse from the service
            
        Raises:
            ServiceNotSupportedError: If service doesn't support chat
        """
        from ..core.types import HealthStatus
        from ..core.exceptions import ServiceNotFoundError
        
        # Check if service is online - if cached status is offline, perform fresh health check
        if self._service_info.health_status == HealthStatus.OFFLINE:
            # Perform fresh health check to see if service came back online
            try:
                from ..services.health import check_service_health
                from ..utils.async_utils import run_async_in_thread
                # Use longer timeout for chat health checks as chat services may take longer to respond
                health_status = run_async_in_thread(
                    check_service_health(self._service_info, self._client.syft_client, timeout=5.0, poll_interval=0.5)
                )
                self._service_info.health_status = health_status
                
                # If still offline after fresh check, raise error
                if health_status == HealthStatus.OFFLINE:
                    raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
                    
            except Exception as e:
                # If health check fails, assume still offline
                raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
        
        if not self.supports_chat:
            raise ServiceNotSupportedError(f"Service '{self.name}' doesn't support chat")
        return self._client.chat(self.full_name, messages, **kwargs)
    
    async def chat_async(self, messages, **kwargs):
        """Chat with this service asynchronously.
        
        Args:
            messages: Chat messages to send
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
            
        Returns:
            ChatResponse from the service
            
        Raises:
            ServiceNotSupportedError: If service doesn't support chat
        """
        from ..core.types import HealthStatus
        from ..core.exceptions import ServiceNotFoundError
        
        # Check if service is online - if cached status is offline, perform fresh health check
        if self._service_info.health_status == HealthStatus.OFFLINE:
            # Perform fresh health check to see if service came back online
            from ..services.health import check_service_health
            # Use longer timeout for chat health checks as chat services may take longer to respond
            health_status = await check_service_health(self._service_info, self._client.syft_client, timeout=5.0, poll_interval=0.5)
            self._service_info.health_status = health_status
            
            # If still offline after fresh check, raise error
            if health_status == HealthStatus.OFFLINE:
                raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
        
        if not self.supports_chat:
            raise ServiceNotSupportedError(f"Service '{self.name}' doesn't support chat")
        return await self._client.chat_async(self.full_name, messages, **kwargs)
    
    def search(self, message, **kwargs):
        """Search with this service synchronously.
        
        Args:
            message: Search query
            **kwargs: Additional parameters (topK, similarity_threshold, etc.)
            
        Returns:
            SearchResponse from the service
            
        Raises:
            ServiceNotSupportedError: If service doesn't support search
        """
        from ..core.types import HealthStatus
        from ..core.exceptions import ServiceNotFoundError
        
        # Check if service is online - if cached status is offline, perform fresh health check
        if self._service_info.health_status == HealthStatus.OFFLINE:
            # Perform fresh health check to see if service came back online
            try:
                from ..services.health import check_service_health
                from ..utils.async_utils import run_async_in_thread
                health_status = run_async_in_thread(
                    check_service_health(self._service_info, self._client.syft_client, timeout=3.0)
                )
                self._service_info.health_status = health_status
                
                # If still offline after fresh check, raise error
                if health_status == HealthStatus.OFFLINE:
                    raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
                    
            except Exception as e:
                # If health check fails, assume still offline
                raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
        
        if not self.supports_search:
            raise ServiceNotSupportedError(f"Service '{self.name}' doesn't support search")
        return self._client.search(self.full_name, message, **kwargs)
    
    async def search_async(self, message, **kwargs):
        """Search with this service asynchronously.
        
        Args:
            message: Search query
            **kwargs: Additional parameters (topK, similarity_threshold, etc.)
            
        Returns:
            SearchResponse from the service
            
        Raises:
            ServiceNotSupportedError: If service doesn't support search
        """
        from ..core.types import HealthStatus
        from ..core.exceptions import ServiceNotFoundError
        
        # Check if service is online - if cached status is offline, perform fresh health check
        if self._service_info.health_status == HealthStatus.OFFLINE:
            # Perform fresh health check to see if service came back online
            from ..services.health import check_service_health
            health_status = await check_service_health(self._service_info, self._client.syft_client, timeout=3.0)
            self._service_info.health_status = health_status
            
            # If still offline after fresh check, raise error
            if health_status == HealthStatus.OFFLINE:
                raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
        
        if not self.supports_search:
            raise ServiceNotSupportedError(f"Service '{self.name}' doesn't support search")
        return await self._client.search_async(self.full_name, message, **kwargs)
    
    def show_example(self) -> None:
        """Show usage examples for this service.
        
        Displays formatted HTML examples in notebooks, similar to ServiceInfo.show().
        """
        try:
            from IPython.display import display, HTML
        except ImportError:
            # Fallback to text representation if not in a notebook
            print(self._get_text_examples())
            return
        
        # Generate HTML widget with the same theming as ServiceInfo
        from ..utils.theme import generate_adaptive_css
        
        html = generate_adaptive_css('examples')
        html += self._get_html_examples()
        
        display(HTML(html))
    
    def _get_text_examples(self) -> str:
        """Get text-formatted usage examples."""
        examples = []
        examples.append(f"# Usage examples for {self.name}")
        examples.append(f"# Datasite: {self.datasite}")
        examples.append("")
        
        # Object-oriented examples (using Service object)
        examples.append("## Using Service object:")
        examples.append(f'service = client.load_service("{self.full_name}")')
        examples.append("")
        
        if self.supports_chat:
            examples.extend([
                "# Basic chat - complete example",
                'response = service.chat(',
                '    messages=[',
                '        {"role": "user", "content": "Hello! How can you help me?"}',
                '    ]',
                ')',
                'print(response.content)  # Access the response text',
                'print(f"Cost: ${response.cost}")  # Check the cost',
                "",
                "# Advanced chat with parameters",
                'response = service.chat(',
                '    messages=[',
                '        {"role": "system", "content": "You are a helpful AI assistant"},',
                '        {"role": "user", "content": "Explain quantum computing"}',
                '    ],',
                '    temperature=0.7,',
                '    max_tokens=500',
                ')',
                'print(response.content)',
                'print(f"Tokens used: {response.usage.total_tokens}")',
                ""
            ])
        
        if self.supports_search:
            examples.extend([
                "# Basic search - complete example",
                'results = service.search("machine learning algorithms")',
                'for result in results:',
                '    print(f"Score: {result.score:.3f} - {result.content[:100]}...")',
                'print(f"Total results: {len(results)}")',
                "",
                "# Advanced search with parameters", 
                'results = service.search(',
                '    message="latest developments in quantum computing",',
                '    topK=15,',
                '    similarity_threshold=0.75',
                ')',
                'print(f"Found {len(results)} relevant documents")',
                'for i, result in enumerate(results[:3], 1):',
                '    print(f"{i}. {result.content[:150]}... (Score: {result.score:.3f})")',
                ""
            ])
        
        # Direct client examples
        examples.append("## Using client directly:")
        
        if self.supports_chat:
            examples.extend([
                "# Basic chat - direct client approach",
                f'response = await client.chat(',
                f'    service_name="{self.full_name}",',
                f'    messages=[',
                f'        {{"role": "user", "content": "Hello! How can you help me?"}}',
                f'    ]',
                f')',
                'print(response.content)',
                'print(f"Cost: ${response.cost}")',
                ""
            ])
        
        if self.supports_search:
            examples.extend([
                "# Basic search - direct client approach",
                f'results = await client.search(',
                f'    service_name="{self.full_name}",',
                f'    message="machine learning algorithms"',
                f')',
                'for result in results:',
                '    print(f"Score: {result.score:.3f} - {result.content[:100]}...")',
                ""
            ])
        
        # Add pricing info
        if self.cost > 0:
            examples.append(f"# Cost: ${self.cost} per request")
        else:
            examples.append("# Cost: Free")
        
        return "\n".join(examples)
    
    def _get_html_examples(self) -> str:
        """Get HTML-formatted usage examples."""
        # Pricing info
        pricing_str = "Free" if self.cost == 0 else f"${self.cost} per request"
        pricing_class = "free" if self.cost == 0 else "paid"
        
        # Build simple HTML widget
        html = f'''
        <div class="syft-widget">
            <div class="examples-widget">
                <div class="widget-title">
                    Usage Examples: {self.name}
                </div>
                
                <div class="status-line">
                    <span class="status-label">Datasite:</span>
                    <span class="status-value">{self.datasite}</span>
                </div>
                
                <div class="status-line">
                    <span class="status-label">Cost:</span>
                    <span class="status-value {pricing_class}">{pricing_str}</span>
                </div>
        '''
        
        # Via Service Object section
        if self.supports_chat or self.supports_search:
            html += '''
                <div class="status-line">
                    <span class="status-label">Via Service Object:</span>
                </div>
            '''
            
            # Build combined code block for service object
            service_code_parts = [f'service = client.load_service("{self.full_name}")']
            
            # Add chat examples if supported
            if self.supports_chat:
                service_code_parts.extend([
                    "",
                    "# Basic chat - complete example",
                    f'response = await service.chat_async(messages=[{{"role": "user", "content": "Hello! How can you help me?"}}])',
                    'print(response.content)  # Access the response text',
                    'print(f"Cost: ${response.cost}")  # Check the cost',
                    "",
                    "# Advanced chat with parameters",
                    'response = service.chat(',
                    '    messages=[',
                    '        {"role": "system", "content": "You are a helpful AI assistant"},',
                    '        {"role": "user", "content": "Explain quantum computing"}',
                    '    ],',
                    '    temperature=0.7,',
                    '    max_tokens=500',
                    ')',
                    'print(response.content)',
                    'print(f"Tokens used: {response.usage.total_tokens}")'
                ])
            
            # Add search examples if supported
            if self.supports_search:
                if self.supports_chat:
                    service_code_parts.append("")
                service_code_parts.extend([
                    "# Basic search - complete example",
                    'results = await service.search("machine learning algorithms")',
                    'for result in results:',
                    '    print(f"Score: {result.score:.3f} - {result.content[:100]}...")',
                    'print(f"Total results: {len(results)}")',
                    "",
                    "# Advanced search with parameters",
                    'results = service.search(',
                    '    message="latest developments in quantum computing",',
                    '    topK=15,',
                    '    similarity_threshold=0.75',
                    ')',
                    'print(f"Found {len(results)} relevant documents")',
                    'for i, result in enumerate(results[:3], 1):',
                    '    print(f"{i}. {result.content[:150]}... (Score: {result.score:.3f})")'
                ])
            
            service_code = "\\n".join(service_code_parts)
            service_code_display = "<br>".join(service_code_parts)
            
            
            html += f'''<div class="code-block">
<span class="command-code">{service_code_display}</span>
</div>'''
        
        # Via Client section
        if self.supports_chat or self.supports_search:
            html += '''
                <div class="status-line">
                    <span class="status-label">Via Client:</span>
                </div>
            '''
            
            # Build combined code block for client
            client_code_parts = []
            
            # Add chat examples if supported
            if self.supports_chat:
                client_code_parts.extend([
                    "# Basic chat - direct client approach",
                    f'response = client.chat_sync(',
                    f'    service_name="{self.full_name}",',
                    f'    messages=[{{"role": "user", "content": "Hello! How can you help me?"}}]',
                    f')',
                    'print(response.content)',
                    'print(f"Cost: ${response.cost}")'
                ])
            
            # Add search examples if supported
            if self.supports_search:
                if self.supports_chat:
                    client_code_parts.extend(["", ""])
                client_code_parts.extend([
                    "# Basic search - direct client approach",
                    f'results = client.search_sync(',
                    f'    service_name="{self.full_name}",',
                    f'    message="machine learning algorithms"',
                    f')',
                    'for result in results:',
                    '    print(f"Score: {result.score:.3f} - {result.content[:100]}...")'
                ])
            
            client_code = "\\n".join(client_code_parts)
            client_code_display = "<br>".join(client_code_parts)
            
            
            html += f'''<div class="code-block">
<span class="command-code">{client_code_display}</span>
</div>'''
        
        html += f'''
            </div>
        </div>
        '''
        
        return html
    
    def _render_description_as_markdown(self, description: str) -> str:
        """Render description content as markdown HTML.
        
        Args:
            description: Raw description text that may contain markdown
            
        Returns:
            HTML string with markdown rendered and wrapped in styled container
        """
        if not description:
            return ""
        
        try:
            # Try to render as markdown
            import markdown2
            # Convert markdown to HTML with extras for better formatting
            content = markdown2.markdown(
                description,
                extras=['fenced-code-blocks', 'tables', 'break-on-newline', 'code-friendly']
            )
        except ImportError:
            # Fallback to simple HTML escaping if markdown2 not available
            import html
            content = html.escape(description).replace('\n', '<br>')
        except Exception:
            # Fallback to simple HTML escaping on any error
            import html
            content = html.escape(description).replace('\n', '<br>')
        
        # Wrap in styled container with margins and proper font size
        return f'''<div class="markdown-content" style="margin: 8px 16px; font-size: 12px; line-height: 1.4; color: var(--syft-text-primary, inherit);">{content}</div>'''