"""
ServiceInfo data class and related utilities
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from pathlib import Path
from datetime import datetime

from ..core.types import ServiceItem, ServiceType, ServiceStatus, HealthStatus
from ..utils.theme import generate_adaptive_css


@dataclass
class ServiceInfo:
    """Complete information about a discovered SyftBox service."""
    
    # Basic metadata
    name: str = ""
    datasite: str = ""
    summary: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Service configuration
    services: List[ServiceItem] = field(default_factory=list)
    
    # Status information
    config_status: ServiceStatus = ServiceStatus.DISABLED
    health_status: Optional[HealthStatus] = None
    
    # Delegation information
    delegate_email: Optional[str] = None
    delegate_control_types: Optional[List[str]] = None
    
    # Technical details
    endpoints: Dict[str, Any] = field(default_factory=dict)
    rpc_schema: Dict[str, Any] = field(default_factory=dict)
    code_hash: Optional[str] = None
    version: Optional[str] = None
    
    # File system paths
    metadata_path: Optional[Path] = None
    rpc_schema_path: Optional[Path] = None
    
    # Timestamps
    publish_date: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    discovered_at: Optional[datetime] = None
    
    # Computed service URLs (populated at runtime)
    service_urls: Dict[ServiceType, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing."""
        # Set discovery timestamp
        if self.discovered_at is None:
            self.discovered_at = datetime.now()
        
        # Parse string dates if needed
        if isinstance(self.publish_date, str):
            try:
                self.publish_date = datetime.fromisoformat(self.publish_date.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                self.publish_date = None
    
    # Service-related properties
    
    @property
    def has_enabled_services(self) -> bool:
        """Check if service has any enabled services."""
        return any(service.enabled for service in self.services)
    
    @property
    def enabled_service_types(self) -> List[ServiceType]:
        """Get list of enabled service types."""
        return [service.type for service in self.services if service.enabled]
    
    @property
    def disabled_service_types(self) -> List[ServiceType]:
        """Get list of disabled service types."""
        return [service.type for service in self.services if not service.enabled]
    
    @property
    def all_service_types(self) -> List[ServiceType]:
        """Get list of all service types (enabled and disabled)."""
        return [service.type for service in self.services]
    
    def get_service_info(self, service_type: ServiceType) -> Optional[ServiceItem]:
        """Get service information for a specific service type."""
        for service in self.services:
            if service.type == service_type:
                return service
        return None
    
    def supports_service(self, service_type: ServiceType) -> bool:
        """Check if service supports and has enabled a specific service type."""
        service = self.get_service_info(service_type)
        return service is not None and service.enabled
    
    def has_service(self, service_type: ServiceType) -> bool:
        """Check if service has a service type (regardless of enabled status)."""
        return any(service.type == service_type for service in self.services)
    
    # Pricing-related properties
    @property
    def min_pricing(self) -> float:
        """Get minimum pricing across all enabled services."""
        enabled_services = [s for s in self.services if s.enabled]
        if not enabled_services:
            return 0.0
        return min(service.pricing for service in enabled_services)
    
    @property
    def max_pricing(self) -> float:
        """Get maximum pricing across all enabled services."""
        enabled_services = [s for s in self.services if s.enabled]
        if not enabled_services:
            return 0.0
        return max(service.pricing for service in enabled_services)
    
    @property
    def avg_pricing(self) -> float:
        """Get average pricing across all enabled services."""
        enabled_services = [s for s in self.services if s.enabled]
        if not enabled_services:
            return 0.0
        return sum(service.pricing for service in enabled_services) / len(enabled_services)
    
    @property
    def is_free(self) -> bool:
        """Check if all enabled services are free."""
        return self.max_pricing == 0.0
    
    @property
    def is_paid(self) -> bool:
        """Check if any enabled services require payment."""
        return self.max_pricing > 0.0
    
    def get_pricing_for_service(self, service_type: ServiceType) -> Optional[float]:
        """Get pricing for a specific service type."""
        service = self.get_service_info(service_type)
        return service.pricing if service else None
    
    # Status-related properties
    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy (online)."""
        return self.health_status == HealthStatus.ONLINE
    
    @property
    def is_available(self) -> bool:
        """Check if service is available (has enabled services and is healthy or health unknown)."""
        return (self.has_enabled_services and 
                (self.health_status is None or 
                 self.health_status in [HealthStatus.ONLINE, HealthStatus.UNKNOWN]))
    
    @property
    def is_active(self) -> bool:
        """Check if service is active (enabled services and active config status)."""
        return (self.has_enabled_services and 
                self.config_status == ServiceStatus.ACTIVE)
    
    # Delegate-related properties
    @property
    def has_delegate(self) -> bool:
        """Check if service has a delegate."""
        return self.delegate_email is not None
    
    @property
    def is_delegated(self) -> bool:
        """Alias for has_delegate."""
        return self.has_delegate
    
    def can_delegate_control(self, control_type: str) -> bool:
        """Check if delegate can perform specific control type."""
        if not self.has_delegate or not self.delegate_control_types:
            return False
        return control_type in self.delegate_control_types
    
    # Metadata-related properties
    @property
    def has_metadata_file(self) -> bool:
        """Check if service has an accessible metadata file."""
        return self.metadata_path is not None and self.metadata_path.exists()
    
    @property
    def has_rpc_schema(self) -> bool:
        """Check if service has an RPC schema."""
        return bool(self.rpc_schema) or (
            self.rpc_schema_path is not None and self.rpc_schema_path.exists()
        )
    
    @property
    def has_endpoints_documented(self) -> bool:
        """Check if service has documented endpoints."""
        return bool(self.endpoints)
    
    # Tag-related methods
    def has_tag(self, tag: str) -> bool:
        """Check if service has a specific tag (case-insensitive)."""
        return tag.lower() in [t.lower() for t in self.tags]
    
    def has_any_tags(self, tags: List[str]) -> bool:
        """Check if service has any of the specified tags."""
        service_tags = [t.lower() for t in self.tags]
        return any(tag.lower() in service_tags for tag in tags)
    
    def has_all_tags(self, tags: List[str]) -> bool:
        """Check if service has all of the specified tags."""
        service_tags = [t.lower() for t in self.tags]
        return all(tag.lower() in service_tags for tag in tags)
    
    def get_matching_tags(self, tags: List[str]) -> List[str]:
        """Get list of tags that match the provided tags."""
        service_tags_lower = {t.lower(): t for t in self.tags}
        return [service_tags_lower[tag.lower()] for tag in tags 
                if tag.lower() in service_tags_lower]
    
    # Utility methods
    def get_service_summary(self) -> Dict[str, Any]:
        """Get summary of services."""
        enabled = [s for s in self.services if s.enabled]
        disabled = [s for s in self.services if not s.enabled]
        
        return {
            'total_services': len(self.services),
            'enabled_services': len(enabled),
            'disabled_services': len(disabled),
            'enabled_types': [s.type.value for s in enabled],
            'disabled_types': [s.type.value for s in disabled],
            'min_price': self.min_pricing,
            'max_price': self.max_pricing,
            'avg_price': self.avg_pricing,
            'is_free': self.is_free
        }
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary of service status."""
        return {
            'config_status': self.config_status.value,
            'health_status': self.health_status.value if self.health_status else None,
            'is_available': self.is_available,
            'is_healthy': self.is_healthy,
            'is_active': self.is_active,
            'has_delegate': self.has_delegate,
            'delegate_email': self.delegate_email
        }
    
    def get_metadata_summary(self) -> Dict[str, Any]:
        """Get summary of metadata and file information."""
        return {
            'name': self.name,
            'datasite': self.datasite,
            'summary': self.summary,
            'tags': self.tags,
            'version': self.version,
            'code_hash': self.code_hash,
            'publish_date': self.publish_date.isoformat() if self.publish_date else None,
            'discovered_at': self.discovered_at.isoformat() if self.discovered_at else None,
            'has_metadata_file': self.has_metadata_file,
            'has_rpc_schema': self.has_rpc_schema,
            'has_endpoints_documented': self.has_endpoints_documented
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ServiceInfo to dictionary for serialization."""
        return {
            # Basic info
            'name': self.name,
            'datasite': self.datasite,
            'summary': self.summary,
            'description': self.description,
            'tags': self.tags,
            
            # Services
            'services': [
                {
                    'type': service.type.value,
                    'enabled': service.enabled,
                    'pricing': service.pricing,
                    'charge_type': service.charge_type.value
                }
                for service in self.services
            ],
            
            # Status
            'config_status': self.config_status.value,
            'health_status': self.health_status.value if self.health_status else None,
            
            # Delegate info
            'delegate_email': self.delegate_email,
            'delegate_control_types': self.delegate_control_types,
            
            # Technical details
            'endpoints': self.endpoints,
            'rpc_schema': self.rpc_schema,
            'code_hash': self.code_hash,
            'version': self.version,
            
            # Paths (as strings)
            'metadata_path': str(self.metadata_path) if self.metadata_path else None,
            'rpc_schema_path': str(self.rpc_schema_path) if self.rpc_schema_path else None,
            
            # Timestamps
            'publish_date': self.publish_date.isoformat() if self.publish_date else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'discovered_at': self.discovered_at.isoformat() if self.discovered_at else None,
            
            # Computed properties
            'min_pricing': self.min_pricing,
            'max_pricing': self.max_pricing,
            'is_free': self.is_free,
            'is_available': self.is_available,
            'has_enabled_services': self.has_enabled_services,
            'enabled_service_types': [st.value for st in self.enabled_service_types]
        }
    
    def __repr__(self) -> str:
        """String representation of ServiceInfo in client's __repr__ format."""
        # Get basic service info
        service_name = self.name
        datasite = self.datasite
        summary = self.summary
        status = self.config_status.value
        
        # Get enabled services with detailed info
        enabled_services = []
        total_cost = 0
        for service_item in self.services:
            if service_item.enabled:
                service_type = service_item.type.value
                pricing = f"${service_item.pricing:.3f}" if service_item.pricing > 0 else "Free"
                
                # Get available parameters for this service type
                params = []
                if service_type == "chat":
                    params = ["messages", "temperature", "max_tokens", "top_p"]
                elif service_type == "search":
                    params = ["message", "topK", "similarity_threshold"]
                
                param_str = f"({', '.join(params)})" if params else ""
                service_str = f"{service_type}{param_str} - {pricing}"
                enabled_services.append(service_str)
                total_cost += service_item.pricing
        
        services_str = "\n                  ".join(enabled_services) if enabled_services else "None"
        
        # Health status
        health_str = ""
        if self.health_status:
            health_map = {
                HealthStatus.ONLINE: "Online",
                HealthStatus.OFFLINE: "Offline", 
                HealthStatus.TIMEOUT: "Timeout",
                HealthStatus.UNKNOWN: "Unknown"
            }
            health_str = f" [{health_map.get(self.health_status, 'Unknown')}]"
        
        # Pricing info
        pricing_str = "Free" if total_cost == 0 else f"${total_cost:.2f}/request"
        
        # Tags (limit to 3-4 for display)
        tags_display = ""
        if self.tags:
            display_tags = self.tags[:4]
            tags_display = ", ".join(display_tags)
            if len(self.tags) > 4:
                tags_display += f" (+{len(self.tags) - 4} more)"
        
        # Build enhanced representation with better styling
        status_emoji = "✅" if status == "active" else "⚠️" if status == "inactive" else "📋"
        health_emoji = ""
        if self.health_status:
            health_emojis = {
                HealthStatus.ONLINE: "🟢",
                HealthStatus.OFFLINE: "🔴", 
                HealthStatus.TIMEOUT: "🟡",
                HealthStatus.UNKNOWN: "⚪"
            }
            health_emoji = health_emojis.get(self.health_status, "⚪")
        
        # Header with emojis and styling
        header = f"🔧 {service_name} Service {status_emoji} [{status}]{health_str} {health_emoji}".strip()
        
        # Add separator line
        separator = "=" * min(len(header.replace('🔧', '').replace(status_emoji, '').replace(health_emoji, '').strip()), 60)
        
        lines = [
            header,
            separator,
            "",
            f"📍 Datasite:       {datasite}",
            f"📝 Summary:        {summary}",
            "",
            "⚡ Available Services:",
        ]
        
        # Add each service with proper indentation and styling
        if enabled_services:
            for service in enabled_services:
                lines.append(f"   • {service}")
        else:
            lines.append("   • None")
        
        lines.extend([
            "",
            f"💰 Total Pricing:  {pricing_str}",
        ])
        
        if tags_display:
            lines.extend([
                f"🏷️  Tags:           {tags_display}",
            ])
        
        lines.extend([
            "",
            "💡 Quick Usage:",
            f"   service = client.load_service(\"{datasite}/{service_name}\")",
        ])
        
        return "\n".join(lines)
    
    def show(self) -> None:
        """Display service information as an HTML widget in notebooks."""
        try:
            from IPython.display import display, HTML
        except ImportError:
            # Fallback to text representation if not in a notebook
            print(self.__repr__())
            return
        
        # Get basic service info
        service_name = self.name
        datasite = self.datasite
        summary = self.summary
        description = self.description if self.description != self.summary else ""
        status = self.config_status.value
        
        # Get enabled services
        enabled_services = []
        total_cost = 0
        for service_item in self.services:
            if service_item.enabled:
                enabled_services.append(service_item.type.value.title())
                total_cost += service_item.pricing
        
        services_str = ", ".join(enabled_services) if enabled_services else "None"
        
        # Health status with styling
        health_class = ""
        health_text = ""
        if self.health_status:
            health_map = {
                HealthStatus.ONLINE: ("online", "Online"),
                HealthStatus.OFFLINE: ("offline", "Offline"), 
                HealthStatus.TIMEOUT: ("timeout", "Timeout"),
                HealthStatus.UNKNOWN: ("unknown", "Unknown")
            }
            health_class, health_text = health_map.get(self.health_status, ("unknown", "Unknown"))
            health_text = f" [{health_text}]"
        
        # Pricing info
        pricing_str = "Free" if total_cost == 0 else f"${total_cost:.2f}/request"
        pricing_class = "free" if total_cost == 0 else "paid"
        
        # Tags (limit for display)
        tags_display = ""
        if self.tags:
            display_tags = self.tags[:4]
            tags_display = ", ".join(display_tags)
            if len(self.tags) > 4:
                tags_display += f" (+{len(self.tags) - 4} more)"
        
        # Build HTML widget with adaptive theming
        # from ..utils.theme import generate_adaptive_css
        html = generate_adaptive_css('serviceinfo')
        html += f'''
        <div class="syft-widget">
            <div class="serviceinfo-widget">
                <div class="widget-title">
                    {service_name} Service {f'<span class="status-badge badge-{health_class}">{health_text.strip("[] ")}</span>' if health_text else ''}
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Status:</span>
                    <span class="status-value">{status}</span>
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Datasite:</span>
                    <span class="status-value">{datasite}</span>
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Summary:</span>
                    <span class="status-value">{summary}</span>
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Services:</span>
                    <span class="status-value">{services_str}</span>
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Pricing:</span>
                    <span class="status-value {pricing_class}">{pricing_str}</span>
                </div>
                
                {f'<div class="status-line" style="margin: 8px 16px;"><span class="status-label">Tags:</span><span class="status-value">{tags_display}</span></div>' if tags_display else ''}
                
                {f'<div class="status-line" style="margin: 8px 16px;"><span class="status-label">Description:</span></div>{self._render_description_as_markdown(description)}' if description else ''}
                
                <div class="widget-title" style="margin: 16px 0 12px 0;">
                    Available Services
                </div>
                {self._get_available_services_html()}
                
                <div class="widget-title" style="margin: 16px 0 12px 0;">
                    Quick Start
                </div>
                {self._get_quickstart_html()}
            </div>
        </div>
        '''
        
        display(HTML(html))
    
    def __str__(self) -> str:
        """Human-readable string representation."""
        health_indicator = ""
        if self.health_status:
            indicators = {
                HealthStatus.ONLINE: "✅",
                HealthStatus.OFFLINE: "❌",
                HealthStatus.TIMEOUT: "⏱️",
                HealthStatus.UNKNOWN: "❓"
            }
            health_indicator = f" {indicators.get(self.health_status, '❓')}"
        
        pricing = f"${self.min_pricing}" if self.min_pricing > 0 else "Free"
        
        return f"{self.name} by {self.datasite} ({pricing}){health_indicator}"
    
    def _get_usage_examples_html(self) -> str:
        """Get HTML-formatted usage examples for this service."""
        examples = []
        
        # Service object loading
        examples.append(f'<span class="command-code">service = client.load_service("{self.datasite}/{self.name}")</span>')
        examples.append("")
        
        # Add chat examples if supported
        if any(service.type.value == 'chat' and service.enabled for service in self.services):
            examples.extend([
                '<span class="comment"># Basic chat</span>',
                '<span class="command-code">response = service.chat(messages=[{"role": "user", "content": "Hello!"}])</span>',
                "",
                '<span class="comment"># Chat with parameters</span>',
                '<span class="command-code">response = service.chat(',
                '    messages=[{"role": "system", "content": "You are helpful"}],',
                '    temperature=0.7,',
                '    max_tokens=200',
                ')</span>',
                ""
            ])
        
        # Add search examples if supported
        if any(service.type.value == 'search' and service.enabled for service in self.services):
            examples.extend([
                '<span class="comment"># Basic search</span>',
                '<span class="command-code">results = service.search("machine learning")</span>',
                "",
                '<span class="comment"># Search with parameters</span>',
                '<span class="command-code">results = service.search(',
                '    message="latest AI research",',
                '    topK=10,',
                '    similarity_threshold=0.8',
                ')</span>',
                ""
            ])
        
        # Direct client usage
        examples.append('<span class="comment"># Using client directly</span>')
        
        if any(service.type.value == 'chat' and service.enabled for service in self.services):
            examples.extend([
                f'<span class="command-code">response = await client.chat(',
                f'    service_name="{self.datasite}/{self.name}",',
                f'    messages=[{{"role": "user", "content": "Hello!"}}]',
                f')</span>'
            ])
        
        if any(service.type.value == 'search' and service.enabled for service in self.services):
            if examples[-1] != '<span class="comment"># Using client directly</span>':
                examples.append("")
            examples.extend([
                f'<span class="command-code">results = await client.search(',
                f'    service_name="{self.datasite}/{self.name}",',
                f'    message="machine learning"',
                f')</span>'
            ])
        
        return '\n'.join(examples)
    
    def _get_available_services_html(self) -> str:
        """Get HTML-formatted available services display."""
        if not self.services:
            return '<div style="color: var(--syft-text-secondary, inherit); font-style: italic; opacity: 0.7;">No services configured</div>'
        
        enabled_services = [s for s in self.services if s.enabled]
        if not enabled_services:
            return '<div style="color: var(--syft-text-secondary, inherit); font-style: italic; opacity: 0.7;">No services enabled</div>'
        
        services_html = []
        for service in enabled_services:
            service_type = service.type.value
            cost_text = "Free" if service.pricing == 0 else f"${service.pricing:.3f}/request"
            cost_class = "free" if service.pricing == 0 else "paid"
            cost_color = "#28a745" if service.pricing == 0 else "#1976d2"
            
            # Get available parameters for this service type
            params = []
            descriptions = {}
            if service_type == "chat":
                params = ["messages", "temperature", "max_tokens", "top_p"]
                descriptions = {
                    "messages": "conversation messages",
                    "temperature": "randomness (0.0-1.0)",
                    "max_tokens": "response length limit",
                    "top_p": "nucleus sampling",
                }
            elif service_type == "search":
                params = ["message", "topK", "similarity_threshold"]
                descriptions = {
                    "message": "search query text",
                    "topK": "max results to return",
                    "similarity_threshold": "relevance cutoff",
                }
            
            # Build parameter list with descriptions
            param_items = []
            for param in params:
                desc = descriptions.get(param, "")
                param_items.append(f'<li style="margin: 3px 0;"><code style="color: var(--syft-text-primary, inherit); font-weight: 500; font-size: 11px;">{param}</code>: <span style="color: var(--syft-text-secondary, inherit);">{desc}</span></li>')
            
            param_html = f'<ul style="margin: 6px 0; padding-left: 16px; font-size: 12px;">{"".join(param_items)}</ul>' if param_items else ""
            
            services_html.append(
                f'<div style="margin: 12px 0;">'
                f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">'
                f'<span style="font-weight: 600; font-size: 14px; color: var(--syft-text-primary, inherit);">{service_type.title()} Service</span>'
                f'<span style="color: {cost_color}; font-weight: 600; font-size: 12px;">{cost_text}</span>'
                f'</div>'
                f'<div style="color: var(--syft-text-secondary, inherit); font-size: 12px; margin-bottom: 8px;">Available parameters:</div>'
                f'{param_html}'
                f'</div>'
            )
        
        # Wrap services with adjusted spacing for first/last items
        if services_html:
            # Remove top margin from first item and bottom margin from last item
            if len(services_html) > 0:
                # Update first item to remove top margin
                services_html[0] = services_html[0].replace('style="margin: 12px 0;"', 'style="margin: 0 0 12px 0;"')
                # Update last item to remove bottom margin
                services_html[-1] = services_html[-1].replace('style="margin: 12px 0;"', 'style="margin: 12px 0 0 0;"')
                # If there's only one item, remove both top and bottom margins
                if len(services_html) == 1:
                    services_html[0] = services_html[0].replace('style="margin: 12px 0 0 0;"', 'style="margin: 0;"')
            
            return f'<div>{"".join(services_html)}</div>'
        else:
            return ""
    
    def _get_quickstart_html(self) -> str:
        """Get HTML-formatted quickstart example with copy button."""
        if not self.services:
            return '<div style="color: var(--syft-text-secondary, inherit); font-style: italic; opacity: 0.7;">No services available</div>'
        
        enabled_services = [s for s in self.services if s.enabled]
        if not enabled_services:
            return '<div style="color: var(--syft-text-secondary, inherit); font-style: italic; opacity: 0.7;">No services enabled</div>'
        
        # Pick the first enabled service for the example
        primary_service = enabled_services[0]
        service_type = primary_service.type.value
        full_service_name = f"{self.datasite}/{self.name}"
        
        # Build end-to-end example based on service type
        code_parts = [
            f'# Load the service',
            f'service = client.load_service("{full_service_name}")',
            '',
        ]
        
        if service_type == "chat":
            code_parts.extend([
                '# Basic chat example',
                'response = await service.chat_async(',
                '    messages=[',
                '        {"role": "user", "content": "Hello! How can you help me?"}',
                '    ]',
                ')',
                'print(response.content)  # View the response',
                'print(f"Cost: ${response.cost}")  # Check cost',
                '',
                '# Advanced chat with parameters',
                'response = await service.chat_async(',
                '    messages=[',
                '        {"role": "system", "content": "You are a helpful assistant"},',
                '        {"role": "user", "content": "Explain machine learning"}',
                '    ],',
                '    temperature=0.7,',
                '    max_tokens=200',
                ')',
                'print(response.content)'
            ])
        elif service_type == "search":
            code_parts.extend([
                '# Basic search example',
                'results = await service.search_async("machine learning")',
                'for result in results:',
                '    print(f"Score: {result.score:.3f} - {result.content[:100]}...")',
                '',
                '# Advanced search with parameters',
                'results = await service.search_async(',
                '    message="artificial intelligence research",',
                '    topK=10,',
                '    similarity_threshold=0.8',
                ')',
                'print(f"Found {len(results)} results")',
                'for i, result in enumerate(results[:3], 1):',
                '    print(f"{i}. {result.content[:150]}...")'
            ])
        else:
            code_parts.extend([
                '# Basic usage',
                f'# Check available methods: dir(service)',
                f'# service.{service_type}(...)'
            ])
        
        code_text = "\\n".join(code_parts)
        code_display = "<br>".join(code_parts)
        
        return f'''<div class="code-block" style="padding: 12px; margin: 8px 0;">
    <span class="command-code" style="font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace; font-size: 12px; line-height: 1.5; color: var(--syft-text-primary, inherit);">{code_display}</span>
</div>'''
    
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
    
    def __eq__(self, other) -> bool:
        """Check equality based on name and datasite."""
        if not isinstance(other, ServiceInfo):
            return False
        return self.name == other.name and self.datasite == other.datasite
    
    def __hash__(self) -> int:
        """Hash based on name and datasite."""
        return hash((self.name, self.datasite))


# Utility functions for working with ServiceInfo objects
def group_services_by_datasite(services: List[ServiceInfo]) -> Dict[str, List[ServiceInfo]]:
    """Group services by datasite email."""
    groups = {}
    for service in services:
        if service.datasite not in groups:
            groups[service.datasite] = []
        groups[service.datasite].append(service)
    return groups


def group_services_by_service_type(services: List[ServiceInfo]) -> Dict[ServiceType, List[ServiceInfo]]:
    """Group services by service type."""
    groups = {}
    for service in services:
        for service_type in service.enabled_service_types:
            if service_type not in groups:
                groups[service_type] = []
            groups[service_type].append(service)
    return groups


def group_services_by_status(services: List[ServiceInfo]) -> Dict[str, List[ServiceInfo]]:
    """Group services by availability status."""
    groups = {
        'available': [],
        'unavailable': [],
        'unknown': []
    }
    
    for service in services:
        if service.is_available:
            groups['available'].append(service)
        elif service.health_status == HealthStatus.OFFLINE:
            groups['unavailable'].append(service)
        else:
            groups['unknown'].append(service)
    
    return groups


def sort_services_by_preference(
        services: List[ServiceInfo], 
        preference: str = "balanced"
    ) -> List[ServiceInfo]:
    """Sort services by preference (cheapest, paid, balanced)."""
    if preference == "cheapest":
        return sorted(services, key=lambda m: m.min_pricing)
    elif preference == "paid":
        return sorted(services, key=lambda m: m.max_pricing, reverse=True)
    elif preference == "balanced":
        def score(service):
            # Balance cost (lower is better) and quality indicators
            cost_score = 1.0 / (service.min_pricing + 0.01)
            
            # Quality indicators
            quality_score = 0
            quality_tags = {'paid', 'gpt4', 'claude', 'enterprise', 'high-quality'}
            quality_score += len(set(service.tags).intersection(quality_tags)) * 0.5
            
            # Health bonus
            if service.health_status == HealthStatus.ONLINE:
                quality_score += 1.0
            
            # Service variety bonus
            quality_score += len(service.enabled_service_types) * 0.2
            
            return cost_score + quality_score
        
        return sorted(services, key=score, reverse=True)
    else:
        return services


def filter_healthy_services(services: List[ServiceInfo]) -> List[ServiceInfo]:
    """Filter services to only include healthy ones."""
    return [service for service in services if service.is_healthy]


def filter_available_services(services: List[ServiceInfo]) -> List[ServiceInfo]:
    """Filter services to only include available ones."""
    return [service for service in services if service.is_available]


def get_service_statistics(services: List[ServiceInfo]) -> Dict[str, Any]:
    """Get comprehensive statistics about a list of services."""
    if not services:
        return {}
    
    # Basic counts
    total = len(services)
    enabled = len([m for m in services if m.has_enabled_services])
    healthy = len([m for m in services if m.is_healthy])
    free = len([m for m in services if m.is_free])
    paid = len([m for m in services if m.is_paid])
    
    # Service type counts
    service_counts = {}
    for service_type in ServiceType:
        service_counts[service_type.value] = len([
            m for m in services if m.supports_service(service_type)
        ])
    
    # Datasite statistics
    datasites = list(set(m.datasite for m in services))
    services_per_datasite = {}
    for datasite in datasites:
        services_per_datasite[datasite] = len([m for m in services if m.datasite == datasite])
    
    # Pricing statistics
    paid_services = [m for m in services if m.is_paid]
    pricing_stats = {}
    if paid_services:
        prices = [m.min_pricing for m in paid_services]
        pricing_stats = {
            'min_price': min(prices),
            'max_price': max(prices),
            'avg_price': sum(prices) / len(prices),
            'median_price': sorted(prices)[len(prices) // 2]
        }
    
    # Tag statistics
    all_tags = []
    for service in services:
        all_tags.extend(service.tags)
    
    tag_counts = {}
    for tag in all_tags:
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        'total_services': total,
        'enabled_services': enabled,
        'healthy_services': healthy,
        'free_services': free,
        'paid_services': paid,
        'service_counts': service_counts,
        'total_datasites': len(datasites),
        'avg_services_per_datasite': total / len(datasites) if datasites else 0,
        'top_datasites': sorted(services_per_datasite.items(), 
                           key=lambda x: x[1], reverse=True)[:5],
        'pricing_stats': pricing_stats,
        'total_tags': len(set(all_tags)),
        'top_tags': top_tags
    }