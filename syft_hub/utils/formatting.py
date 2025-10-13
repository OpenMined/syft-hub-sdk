"""
Formatting utilities for displaying service information
"""
import hashlib
from IPython.display import display, HTML
from typing import List, Optional
from datetime import datetime

from ..models.service_info import ServiceInfo
from ..core.types import HealthStatus


def format_services_table(services: List[ServiceInfo]) -> str:
    """Format services as a table.
    
    Args:
        services: List of services to display
        
    Returns:
        Formatted table string
    """
    if not services:
        return "No services found."
    
    # Calculate column widths
    name_width = max(len("Name"), max(len(service.name) for service in services), 15)
    datasite_width = max(len("Datasite"), max(len(service.datasite) for service in services), 15)
    services_width = max(len("Services"), max(len(_format_services(service)) for service in services), 10)
    summary_width = max(len("Summary"), max(len(service.summary[:30]) for service in services), 20)
    status_width = max(len("Status"), max(len(_format_status(service)) for service in services), 10)
    
    # Ensure minimum widths and maximum widths for readability
    name_width = min(max(name_width, 15), 25)
    datasite_width = min(max(datasite_width, 15), 30)
    services_width = min(max(services_width, 10), 15)
    summary_width = min(max(summary_width, 20), 40)
    status_width = min(max(status_width, 10), 15)
    
    # Build table
    lines = []
    
    # Header
    header = f"┌─{'─' * name_width}─┬─{'─' * datasite_width}─┬─{'─' * services_width}─┬─{'─' * summary_width}─┬─{'─' * status_width}─┐"
    lines.append(header)
    
    header_row = (f"│ {'Name':<{name_width}} │ {'Datasite':<{datasite_width}} │ "
                  f"{'Services':<{services_width}} │ {'Summary':<{summary_width}} │ {'Status':<{status_width}} │")
    lines.append(header_row)
    
    separator = f"├─{'─' * name_width}─┼─{'─' * datasite_width}─┼─{'─' * services_width}─┼─{'─' * summary_width}─┼─{'─' * status_width}─┤"
    lines.append(separator)
    
    # Data rows
    for service in services:
        name = _truncate(service.name, name_width)
        datasite = _truncate(service.datasite, datasite_width)
        services = _truncate(_format_services(service), services_width)
        summary = _truncate(service.summary, summary_width)
        status = _truncate(_format_status(service), status_width)
        
        row = (f"│ {name:<{name_width}} │ {datasite:<{datasite_width}} │ "
               f"{services:<{services_width}} │ {summary:<{summary_width}} │ {status:<{status_width}} │")
        lines.append(row)
    
    # Footer
    footer = f"└─{'─' * name_width}─┴─{'─' * datasite_width}─┴─{'─' * services_width}─┴─{'─' * summary_width}─┴─{'─' * status_width}─┘"
    lines.append(footer)
    
    # Add summary info
    total_services = len(services)
    health_checked = len([m for m in services if m.health_status is not None])
    
    if health_checked > 0:
        online = len([m for m in services if m.health_status == HealthStatus.ONLINE])
        lines.append(f"\nFound {total_services} services (health checks: {online}/{health_checked} online)")
    else:
        lines.append(f"\nFound {total_services} services")
    
    return "\n".join(lines)


def format_service_details(service: ServiceInfo) -> str:
    """Format detailed information about a single service.
    
    Args:
        service: Service to display details for
        
    Returns:
        Formatted details string
    """
    lines = []
    
    # Header
    lines.append("=" * 60)
    lines.append(f"Service: {service.name}")
    lines.append("=" * 60)
    
    # Basic info
    lines.append(f"Datasite: {service.datasite}")
    lines.append(f"Summary: {service.summary}")
    if service.description != service.summary:
        lines.append(f"Description: {service.description}")
    
    # Status
    lines.append(f"Config Status: {service.config_status.value}")
    if service.health_status:
        lines.append(f"Health Status: {_format_health_status(service.health_status)}")
    
    # Services
    lines.append("\nServices:")
    if service.services:
        for service_item in service.services:
            status = "✅ Enabled" if service_item.enabled else "❌ Disabled"
            pricing = f"${service_item.pricing}/{service_item.charge_type.value}" if service_item.pricing > 0 else "Free"
            lines.append(f"  • {service_item.type.value.title()}: {status} ({pricing})")
    else:
        lines.append("  No services defined")
    
    # Tags
    if service.tags:
        lines.append(f"\nTags: {', '.join(service.tags)}")
    
    # Delegate info
    if service.delegate_email:
        lines.append(f"\nDelegate: {service.delegate_email}")
    
    # Pricing summary
    if service.has_enabled_services:
        if service.min_pricing == service.max_pricing:
            if service.min_pricing == 0:
                lines.append("\nPricing: Free")
            else:
                lines.append(f"\nPricing: ${service.min_pricing}")
        else:
            lines.append(f"\nPricing: ${service.min_pricing} - ${service.max_pricing}")
    
    # File paths (for debugging)
    if service.metadata_path:
        lines.append(f"\nMetadata: {service.metadata_path}")
    if service.rpc_schema_path:
        lines.append(f"RPC Schema: {service.rpc_schema_path}")
    
    return "\n".join(lines)


def format_search_results(query: str, results: List[dict], max_content_length: int = 100) -> str:
    """Format search results for display.
    
    Args:
        query: Original search query
        results: List of search results
        max_content_length: Maximum length of content to show
        
    Returns:
        Formatted search results
    """
    lines = []
    
    lines.append(f"Search Results for: \"{query}\"")
    lines.append("=" * (len(query) + 20))
    
    if not results:
        lines.append("No results found.")
        return "\n".join(lines)
    
    for i, result in enumerate(results, 1):
        lines.append(f"\n{i}. Score: {result.get('score', 'N/A')}")
        
        # Content
        content = result.get('content', '')
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        lines.append(f"   {content}")
        
        # Metadata
        if result.get('metadata'):
            metadata = result['metadata']
            if isinstance(metadata, dict):
                if 'filename' in metadata:
                    lines.append(f"   Source: {metadata['filename']}")
                if 'url' in metadata:
                    lines.append(f"   URL: {metadata['url']}")
    
    return "\n".join(lines)


def format_chat_conversation(messages: List[dict]) -> str:
    """Format a chat conversation for display.
    
    Args:
        messages: List of chat messages
        
    Returns:
        Formatted conversation
    """
    lines = []
    
    for message in messages:
        role = message.get('role', 'unknown')
        content = message.get('content', '')
        timestamp = message.get('timestamp')
        
        # Format timestamp if available
        time_str = ""
        if timestamp:
            if isinstance(timestamp, datetime):
                time_str = f" ({timestamp.strftime('%H:%M:%S')})"
            else:
                time_str = f" ({timestamp})"
        
        # Format message
        if role == 'user':
            lines.append(f"👤 User{time_str}:")
            lines.append(f"   {content}")
        elif role == 'assistant':
            lines.append(f"🤖 Assistant{time_str}:")
            lines.append(f"   {content}")
        elif role == 'system':
            lines.append(f"⚙️  System{time_str}:")
            lines.append(f"   {content}")
        else:
            lines.append(f"❓ {role.title()}{time_str}:")
            lines.append(f"   {content}")
        
        lines.append("")  # Empty line between messages
    
    return "\n".join(lines)


def format_health_summary(health_status: dict) -> str:
    """Format health status summary.
    
    Args:
        health_status: Dictionary mapping service names to health status
        
    Returns:
        Formatted health summary
    """
    if not health_status:
        return "No health data available."
    
    lines = []
    lines.append("Health Status Summary")
    lines.append("=" * 30)
    
    # Count by status
    status_counts = {}
    for status in health_status.values():
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Overall stats
    total = len(health_status)
    online = status_counts.get(HealthStatus.ONLINE, 0)
    offline = status_counts.get(HealthStatus.OFFLINE, 0)
    timeout = status_counts.get(HealthStatus.TIMEOUT, 0)
    unknown = status_counts.get(HealthStatus.UNKNOWN, 0)
    
    lines.append(f"Total Services: {total}")
    lines.append(f"Online: {online} ✅")
    lines.append(f"Offline: {offline} ❌")
    lines.append(f"Timeout: {timeout} ⏱️")
    lines.append(f"Unknown: {unknown} ❓")
    
    # Detailed list
    lines.append("\nDetailed Status:")
    lines.append("-" * 30)
    
    for service_name, status in sorted(health_status.items()):
        status_str = _format_health_status(status)
        lines.append(f"{service_name}: {status_str}")
    
    return "\n".join(lines)


def format_statistics(stats: dict) -> str:
    """Format service statistics for display.
    
    Args:
        stats: Statistics dictionary
        
    Returns:
        Formatted statistics
    """
    lines = []
    lines.append("Service Statistics")
    lines.append("=" * 20)
    
    lines.append(f"Total Services: {stats.get('total_services', 0)}")
    lines.append(f"Enabled Services: {stats.get('enabled_services', 0)}")
    lines.append(f"Disabled Services: {stats.get('disabled_services', 0)}")
    lines.append(f"Chat Services: {stats.get('chat_services', 0)}")
    lines.append(f"Search Services: {stats.get('search_services', 0)}")
    lines.append(f"Free Services: {stats.get('free_services', 0)}")
    lines.append(f"Paid Services: {stats.get('paid_services', 0)}")
    lines.append(f"Total Owners: {stats.get('total_datasites', 0)}")
    
    avg_services = stats.get('avg_services_per_datasite', 0)
    lines.append(f"Avg Services per Datasite: {avg_services:.1f}")
    
    # Top datasites
    top_datasites = stats.get('top_datasites', [])
    if top_datasites:
        lines.append("\nTop Service Owners:")
        for datasite, count in top_datasites:
            lines.append(f"  {datasite}: {count} services")
    
    return "\n".join(lines)


# Private helper functions

def _truncate(text: str, max_length: int) -> str:
    """Truncate text to fit in column."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def _format_services(service: ServiceInfo) -> str:
    """Format services list for table display."""
    enabled_services = [s.type.value for s in service.services if s.enabled]
    if not enabled_services:
        return "none"
    return ",".join(enabled_services)


def _format_status(service: ServiceInfo) -> str:
    """Format status column for table display."""
    base_status = service.config_status.value
    
    if not service.has_enabled_services:
        return "Disabled"
    
    if service.health_status is None:
        return base_status
    
    if service.health_status == HealthStatus.ONLINE:
        return f"{base_status} ✅"
    elif service.health_status == HealthStatus.OFFLINE:
        return f"{base_status} ❌"
    elif service.health_status == HealthStatus.TIMEOUT:
        return f"{base_status} ⏱️"
    else:
        return f"{base_status} ❓"


def _format_health_status(status: HealthStatus) -> str:
    """Format health status with emoji."""
    status_map = {
        HealthStatus.ONLINE: "Online ✅",
        HealthStatus.OFFLINE: "Offline ❌", 
        HealthStatus.TIMEOUT: "Timeout ⏱️",
        HealthStatus.UNKNOWN: "Unknown ❓",
        HealthStatus.NOT_APPLICABLE: "N/A ➖"
    }
    return status_map.get(status, f"{status.value} ❓")

def display_text_with_copy(text: str, label: str = None, mask: bool = False):
    """Display text inline with copy button.
    
    Args:
        text: The text to display and copy
        label: Label to show before the text (default: None, no label shown)
        mask: Whether to mask the displayed text (default: False)
    """
    # Generate unique ID from timestamp
    import time
    unique_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    
    # Display text (masked or plain)
    display_text = '••••••••' if mask else text
    
    # Label HTML (only if label provided)
    label_html = f'<span>{label}:</span>' if label else ''
    
    # SVG icons
    clipboard_icon = '''<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: middle;">
        <path d="M4 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V2z"/>
        <path d="M2 6a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-1H6a3 3 0 0 1-3-3V6H2z"/>
    </svg>'''
    
    checkmark_icon = '''<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: middle;">
        <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
    </svg>'''
    
    html = f'''
    <style>
        .pwd-line-{unique_id} {{
            font-family: system-ui, -apple-system, sans-serif;
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 8px 0;
            font-size: 14px;
        }}
        .pwd-text-{unique_id} {{
            font-family: monospace;
            color: #333;
            user-select: all;
            background-color: #f0f0f0;
            padding: 4px 8px;
            border-radius: var(--jp-border-radius);
        }}
        .copy-btn-{unique_id} {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 4px 8px;
            background: transparent;
            border: 1px solid #d0d0d0;
            border-radius: 3px;
            cursor: pointer;
            transition: all 0.2s;
            color: #666;
            min-width: 32px;
            height: 28px;
        }}
        .copy-btn-{unique_id}:hover {{
            background: #e8e8e8;
            border-color: #b0b0b0;
        }}
        .copy-btn-{unique_id}:active {{
            transform: scale(0.95);
        }}
        .copy-btn-{unique_id}.copied {{
            color: #16a34a;
            border-color: #16a34a;
        }}
        .warning-{unique_id} {{
            color: #d97706;
            font-size: 13px;
            margin-top: 4px;
        }}
    </style>
    
    <div>
        <div class="pwd-line-{unique_id}">
            {label_html}
            <span class="pwd-text-{unique_id}" id="pwd-{unique_id}">{display_text}</span>
            <button class="copy-btn-{unique_id}" id="btn-{unique_id}" onclick="copyPassword_{unique_id}()" title="Copy to clipboard">
                <span id="icon-{unique_id}">{clipboard_icon}</span>
            </button>
        </div>
    </div>
    
    <script>
    async function copyPassword_{unique_id}() {{
        // Always copy the actual text, not the masked version
        const actualText = `{text}`;
        const btn = document.getElementById('btn-{unique_id}');
        const icon = document.getElementById('icon-{unique_id}');
        
        try {{
            await navigator.clipboard.writeText(actualText);
            
            // Show success state
            btn.classList.add('copied');
            icon.innerHTML = `{checkmark_icon}`;
            
            // Revert after 2 seconds
            setTimeout(() => {{
                btn.classList.remove('copied');
                icon.innerHTML = `{clipboard_icon}`;
            }}, 2000);
        }} catch (err) {{
            console.error('Copy failed:', err);
            alert('Copy failed. Please select and copy the password manually.');
        }}
    }}
    </script>
    '''
    
    display(HTML(html))


def display_text_with_copy_widget(text: str, mask: bool = False) -> str:
    """Generate inline copy button HTML for widget display.
    
    Args:
        text: The text to display and copy
        mask: Whether to mask the displayed text (default: False)
        
    Returns:
        HTML string with text and inline copy button
    """
    # Generate unique ID from timestamp
    import time
    unique_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    
    # Display text (masked or plain)
    display_text = '••••••••' if mask else text
    
    clipboard_icon = '''<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
        <path d="M4 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V2z"/>
        <path d="M2 6a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-1H6a3 3 0 0 1-3-3V6H2z"/>
    </svg>'''
    
    checkmark_icon = '''<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
        <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
    </svg>'''
    
    html = f'''
    <style>
        .widget-pwd-wrapper-{unique_id} {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .widget-copy-btn-{unique_id} {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 2px 6px;
            background: transparent;
            border: 1px solid #d0d0d0;
            border-radius: 3px;
            cursor: pointer;
            transition: all 0.2s;
            color: #666;
            vertical-align: middle;
        }}
        .widget-copy-btn-{unique_id}:hover {{
            background: #e8e8e8;
            border-color: #b0b0b0;
        }}
        .widget-copy-btn-{unique_id}.copied {{
            color: #16a34a;
            border-color: #16a34a;
        }}
    </style>
    
    <span class="widget-pwd-wrapper-{unique_id}">
        <span id="widget-pwd-{unique_id}">{display_text}</span>
        <button class="widget-copy-btn-{unique_id}" id="widget-btn-{unique_id}" 
                onclick="copyWidgetPassword_{unique_id}()" title="Copy to clipboard">
            <span id="widget-icon-{unique_id}">{clipboard_icon}</span>
        </button>
    </span>
    
    <script>
    async function copyWidgetPassword_{unique_id}() {{
        // Always copy the actual text, not the masked version
        const actualText = `{text}`;
        const btn = document.getElementById('widget-btn-{unique_id}');
        const icon = document.getElementById('widget-icon-{unique_id}');
        
        try {{
            await navigator.clipboard.writeText(actualText);
            btn.classList.add('copied');
            icon.innerHTML = `{checkmark_icon}`;
            setTimeout(() => {{
                btn.classList.remove('copied');
                icon.innerHTML = `{clipboard_icon}`;
            }}, 2000);
        }} catch (err) {{
            console.error('Copy failed:', err);
        }}
    }}
    </script>
    '''
    
    return html