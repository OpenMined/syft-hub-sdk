"""
Service class for object-oriented service interaction
"""
from typing import List, TYPE_CHECKING

from ..core.types import ServiceType
from ..models.service_info import ServiceInfo
from .exceptions import ServiceNotSupportedError

if TYPE_CHECKING:
    from ..main import Client

class Service:
    """Object-oriented interface for a loaded SyftBox service."""
    
    def __init__(self, service_info: ServiceInfo, client: 'Client'):
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
        
        # Get comprehensive examples from show_example()
        example_text = self.show_example()
        
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
        
        # Build comprehensive HTML widget reusing existing CSS classes
        html = f'''
        <style>
            .service-obj-widget {{
                font-family: system-ui, -apple-system, sans-serif;
                padding: 16px 0;
                color: #333;
                line-height: 1.5;
                max-width: 900px;
            }}
            .service-obj-title {{
                font-size: 16px;
                font-weight: 600;
                margin-bottom: 8px;
                color: #333;
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .service-obj-status-line {{
                display: flex;
                align-items: center;
                margin: 6px 0;
                font-size: 13px;
            }}
            .service-obj-status-label {{
                color: #666;
                min-width: 140px;
                margin-right: 12px;
                font-weight: 500;
            }}
            .service-obj-status-value {{
                font-family: monospace;
                color: #333;
                font-size: 12px;
            }}
            .service-obj-status-badge {{
                display: inline-block;
                padding: 3px 8px;
                border-radius: 12px;
                font-size: 11px;
                font-weight: 500;
                margin-left: 8px;
            }}
            .service-obj-badge-ready {{
                background: #d4edda;
                color: #155724;
            }}
            .service-obj-badge-not-ready {{
                background: #f8d7da;
                color: #721c24;
            }}
            .service-obj-badge-online {{
                background: #d4edda;
                color: #155724;
            }}
            .service-obj-badge-offline {{
                background: #f8d7da;
                color: #721c24;
            }}
            .service-obj-badge-timeout {{
                background: #fff3cd;
                color: #856404;
            }}
            .service-obj-badge-unknown {{
                background: #e2e3e5;
                color: #6c757d;
            }}
            .service-obj-docs-section {{
                margin-top: 20px;
                padding: 16px;
                border-top: 1px solid #e0e0e0;
                font-size: 12px;
                color: #666;
            }}
            .service-obj-section-header {{
                font-size: 13px;
                font-weight: 600;
                margin-bottom: 12px;
                color: #495057;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .service-obj-command-code {{
                font-family: Monaco, 'Courier New', monospace;
                background: #f5f5f5;
                padding: 8px 12px;
                border-radius: 4px;
                color: #0066cc;
                margin: 4px 0;
                display: block;
                border-left: 3px solid #007bff;
            }}
            .service-obj-command-code[style*="display: inline"] {{
                display: inline !important;
                padding: 1px 4px;
                margin: 0;
                border-left: none;
                border-radius: 2px;
                font-size: 11px;
            }}
            .service-obj-description {{
                font-size: 13px;
                line-height: 1.6;
                color: #555;
                margin: 12px 0;
                padding: 12px;
                background: #fff;
                border-radius: 4px;
                border: 1px solid #e9ecef;
            }}
            .service-obj-services-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 12px;
                margin: 12px 0;
            }}
            .service-obj-service-card {{
                padding: 12px;
                background: #fff;
                border-radius: 6px;
                border: 1px solid #e9ecef;
                border-left: 4px solid #28a745;
            }}
            .service-obj-service-card.paid {{
                border-left-color: #dc3545;
            }}
            .service-obj-service-card-title {{
                font-weight: 600;
                color: #495057;
                margin-bottom: 4px;
            }}
            .service-obj-service-card-cost {{
                font-size: 11px;
                font-weight: 500;
                padding: 2px 6px;
                border-radius: 3px;
                background: #e8f5e8;
                color: #2d5a2d;
            }}
            .service-obj-service-card-cost.paid {{
                background: #ffe6e6;
                color: #cc0000;
            }}
            .command-code {{
                font-family: Monaco, 'Courier New', monospace;
                background: #f5f5f5;
                padding: 1px 4px;
                border-radius: 2px;
                color: #0066cc;
                font-size: 11px;
            }}
        </style>
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
            
            {f'<div class="service-obj-description"><strong>Description:</strong><br>{description}</div>' if description else ''}
            
            <div class="service-obj-docs-section">
                <div class="service-obj-section-header">Available Services</div>
                <div class="service-obj-services-grid">
                    {services_html.replace('class="service-item"', 'class="service-obj-service-card"').replace('class="service-type"', 'class="service-obj-service-card-title"').replace('class="service-cost', 'class="service-obj-service-card-cost')}
                </div>
            </div>
            
            <div class="service-obj-docs-section">
                <div class="service-obj-section-header">Usage Examples</div>
                
                <div class="service-obj-command-code" style="white-space: pre-wrap; line-height: 1.4; padding: 16px; font-size: 12px; margin-bottom: 16px;"><span style="color: #6c757d;"># Load the service</span>
service = client.load_service('{datasite}/{service_name}')
{chat_example_html if self.supports_chat else ''}{search_example_html if self.supports_search else ''}</div>

                <div style="margin-top: 20px; font-size: 12px; color: #666;">
                    <div style="font-weight: 500; margin-bottom: 8px;">Available operations:</div>
                    <div style="line-height: 1.8;">
                        {f'<span class="command-code">service.chat(messages=[], temperature=None, max_tokens=None)</span> — Chat with service {"✅" if service_info.is_healthy else "❌" if service_info.health_status and not service_info.is_healthy else ""}<br>' if self.supports_chat else ''}
                        {f'<span class="command-code">service.search(message, topK=None, similarity_threshold=None)</span> — Search with service {"✅" if service_info.is_healthy else "❌" if service_info.health_status and not service_info.is_healthy else ""}' if self.supports_search else ''}
                    </div>
                </div>
            </div>
        </div>
        '''
        
        display(HTML(html))
    
    def __repr__(self) -> str:
        """Display service using show() method - same display for both service and service.show()."""
        try:
            from IPython.display import display, HTML
            # In notebook environment, call show() which displays the HTML widget
            self.show()
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
        
        # Check if service is online
        if self._service_info.health_status == HealthStatus.OFFLINE:
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
        
        # Check if service is online
        if self._service_info.health_status == HealthStatus.OFFLINE:
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
        
        # Check if service is online
        if self._service_info.health_status == HealthStatus.OFFLINE:
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
        
        # Check if service is online
        if self._service_info.health_status == HealthStatus.OFFLINE:
            raise ServiceNotFoundError("The node is offline. Please retry or find a different service to use")
        
        if not self.supports_search:
            raise ServiceNotSupportedError(f"Service '{self.name}' doesn't support search")
        return await self._client.search_async(self.full_name, message, **kwargs)
    
    def show_example(self) -> str:
        """Show usage examples for this service.
        
        Returns:
            Formatted usage examples
        """
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
                "# Basic chat",
                'response = service.chat(',
                '    messages=[',
                '        {"role": "user", "content": "Hello! How are you?"}',
                '    ]',
                ')',
                "",
                "# Chat with parameters",
                'response = service.chat(',
                '    messages=[',
                '        {"role": "system", "content": "You are a helpful assistant"},',
                '        {"role": "user", "content": "Write a story"}',
                '    ],',
                '    temperature=0.7,',
                '    max_tokens=200',
                ')',
                ""
            ])
        
        if self.supports_search:
            examples.extend([
                "# Basic search",
                'results = service.search("machine learning")',
                "",
                "# Search with parameters", 
                'results = service.search(',
                '    message="latest AI research",',
                '    topK=10,',
                '    similarity_threshold=0.8',
                ')',
                ""
            ])
        
        # Direct client examples
        examples.append("## Using client directly:")
        
        if self.supports_chat:
            examples.extend([
                "# Basic chat",
                f'response = await client.chat(',
                f'    service_name="{self.full_name}",',
                f'    messages=[',
                f'        {{"role": "user", "content": "Hello! How are you?"}}',
                f'    ]',
                f')',
                ""
            ])
        
        if self.supports_search:
            examples.extend([
                "# Basic search",
                f'results = await client.search(',
                f'    service_name="{self.full_name}",',
                f'    message="machine learning"',
                f')',
                ""
            ])
        
        # Add pricing info
        if self.cost > 0:
            examples.append(f"# Cost: ${self.cost} per request")
        else:
            examples.append("# Cost: Free")
        
        return "\n".join(examples)