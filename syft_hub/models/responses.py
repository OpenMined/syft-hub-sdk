"""
Response data classes for SyftBox services
"""
import uuid
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..core.types import ChatMessage, ChatUsage, DocumentResult

class ResponseStatus(Enum):
    """Response status values."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    TIMEOUT = "timeout"


class FinishReason(Enum):
    """Reasons why generation finished."""
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"

@dataclass
class BaseResponse:
    """Base class for all responses."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ResponseStatus = ResponseStatus.SUCCESS
    timestamp: datetime = field(default_factory=datetime.now)
    cost: Optional[float] = None
    provider_info: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

@dataclass
class ChatResponse(BaseResponse):
    """Chat response data class."""
    model: str = ""
    message: Optional[ChatMessage] = None
    messages: List[ChatMessage] = field(default_factory=list)  # Store original messages
    usage: Optional[ChatUsage] = None
    finish_reason: Optional[str] = None
    logprobs: Optional[Dict[str, Any]] = None  # Changed from Dict[str, float] to Any

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatResponse':
        """Create ChatResponse from dictionary."""
        # Parse message
        message_data = data.get('message', {})
        message = ChatMessage(
            role=message_data.get('role', 'assistant'),
            content=message_data.get('content', ''),
            name=message_data.get('name')
        )
        
        # Parse usage
        usage_data = data.get('usage', {})
        usage = ChatUsage(
            prompt_tokens=usage_data.get('promptTokens', 0),
            completion_tokens=usage_data.get('completionTokens', 0),
            total_tokens=usage_data.get('totalTokens', 0)
        )
        
        # Parse messages list if available
        messages_list = []
        if 'messages' in data and data['messages']:
            messages_list = [
                ChatMessage(
                    role=msg.get('role', 'user'),
                    content=msg.get('content', ''),
                    name=msg.get('name')
                ) for msg in data['messages']
            ]
        
        cost = data.get('cost')
        
        # Detect timeout/failure: 0 tokens and free (no cost)
        status = ResponseStatus.SUCCESS
        if usage.total_tokens == 0 and (cost is None or cost == 0):
            status = ResponseStatus.TIMEOUT
            print("⚠️  Warning: This call did not succeed. We recommend you to retry shortly.")
        
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            model=data.get('model', 'unknown'),
            message=message,
            messages=messages_list,
            usage=usage,
            finish_reason=data.get('finishReason'),  # camelCase from endpoint
            cost=cost,
            provider_info=data.get('providerInfo'),  # camelCase from endpoint
            logprobs=data.get('logprobs'),  # Direct assignment, no nested extraction
            status=status
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "id": self.id,
            "model": self.model,
            "message": {
                "role": self.message.role if self.message else "assistant",
                "content": self.message.content if self.message else "",
            },
            "messages": [
                {"role": msg.role, "content": msg.content, "name": msg.name} 
                for msg in self.messages
            ] if self.messages else [],
            "finish_reason": self.finish_reason,
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens if self.usage else 0,
                "completion_tokens": self.usage.completion_tokens if self.usage else 0,
                "total_tokens": self.usage.total_tokens if self.usage else 0
            },
            "cost": self.cost,
            "provider_info": self.provider_info,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "logprobs": self.logprobs
        }
        
        # Add message name if present
        if self.message and self.message.name:
            result["message"]["name"] = self.message.name
            
        return result

    def __str__(self) -> str:
        """Return just the message content for easy printing."""
        return self.message.content if self.message else ""
    
    def __repr__(self) -> str:
        """Return user-friendly chat response display similar to service repr."""
        try:
            from IPython.display import display, HTML
            # In notebook environment, show rich display
            self._display_rich()
            return ""  # Return empty string to avoid double output
        except ImportError:
            # Not in notebook - provide comprehensive text representation
            lines = [
                f"Chat Response [{self.status.value.title()}]",
                "",
                f"Model:           {self.model}",
            ]
            
            if self.message:
                # Show content preview (first 100 chars)
                content_preview = self.message.content[:100] + "..." if len(self.message.content) > 100 else self.message.content
                lines.append(f"Content:         {content_preview}")
                lines.append(f"Role:            {self.message.role}")
            
            if self.usage:
                lines.append(f"Tokens:          {self.usage.total_tokens} total ({self.usage.prompt_tokens} prompt + {self.usage.completion_tokens} completion)")
            
            if self.cost is not None:
                lines.append(f"Cost:            ${self.cost:.4f}")
            
            if self.finish_reason:
                lines.append(f"Finish Reason:   {self.finish_reason}")
                
            lines.append(f"Timestamp:       {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
            return "\n".join(lines)
    
    def _display_rich(self) -> None:
        """Display rich HTML representation in Jupyter notebooks."""
        from IPython.display import display, HTML
        
        # Status badge styling
        status_class = "badge-ready" if self.status.value == "success" else "badge-not-ready"
        
        # Content preview with markdown rendering
        content_preview = ""
        if self.message:
            content = self.message.content
            # Render content as markdown with length limits
            content_preview = self._render_content_as_markdown(content, max_length=2000)
        
        # Usage info
        usage_text = ""
        if self.usage:
            usage_text = f"{self.usage.total_tokens} tokens ({self.usage.prompt_tokens} + {self.usage.completion_tokens})"
        
        # Cost info
        cost_text = f"${self.cost:.4f}" if self.cost is not None else "Free"
        
        from ..utils.theme import generate_adaptive_css
        
        html = generate_adaptive_css('chat-response')
        html += f"""
        <div class="syft-widget">
            <div class="chat-response-widget">
                <div class="widget-title">
                Chat Response <span class="status-badge {status_class}">{self.status.value.title()}</span>
            </div>
            
            <div class="widget-title" style="margin: 16px 0 12px 0;">
                Messages
            </div>
            {self._render_messages_html()}
            
            <div class="widget-title" style="margin: 16px 0 12px 0;">
                Response
            </div>
            {content_preview}
            
            <div class="status-line">
                <span class="status-label">Usage:</span>
                <span class="status-value">{usage_text}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Cost:</span>
                <span class="status-value">{cost_text}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Timestamp:</span>
                <span class="status-value">{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</span>
            </div>
        </div>
        """
        
        display(HTML(html))
    
    def _render_messages_html(self) -> str:
        """Render the conversation messages as HTML."""
        if not self.messages:
            return '<div style="margin: 12px 16px; font-size: 12px; line-height: 1.4; color: inherit; opacity: 0.7;">No messages to display</div>'
        
        messages_html = ""
        for i, msg in enumerate(self.messages):
            role_label = "User" if msg.role == "user" else "Assistant" if msg.role == "assistant" else "System"
            
            # Simple text content without markdown rendering for cleaner display
            content_text = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
            
            messages_html += f'''
            <div style="margin: 4px 16px; font-size: 12px; line-height: 1.4;">
                <span style="font-weight: 500; color: var(--syft-text-primary, inherit); opacity: 0.8;">{role_label}:</span>
                <span style="color: var(--syft-text-primary, inherit); margin-left: 8px;">{content_text}</span>
            </div>
            '''
        
        return messages_html
    
    def _render_content_as_markdown(self, content: str, max_length: int = 2000) -> str:
        """Render content as markdown HTML with length limits.
        
        Args:
            content: Raw content text that may contain markdown
            max_length: Maximum length for the rendered content
            
        Returns:
            HTML string with markdown rendered and wrapped in styled container
        """
        if not content:
            return ""
        
        try:
            # Try to render as markdown
            import markdown2
            # Convert markdown to HTML with extras for better formatting
            formatted_content = markdown2.markdown(
                content,
                extras=['fenced-code-blocks', 'tables', 'break-on-newline', 'code-friendly']
            )
            # Truncate if too long
            if len(formatted_content) > max_length:
                formatted_content = formatted_content[:max_length] + '...<br><em>(truncated)</em>'
        except ImportError:
            # Fallback to simple HTML escaping if markdown2 not available
            import html
            escaped_content = html.escape(content)
            formatted_content = escaped_content.replace('\n', '<br>')
            # Truncate if too long
            if len(formatted_content) > max_length:
                formatted_content = formatted_content[:max_length] + '...<br><em>(truncated)</em>'
        except Exception:
            # Fallback to simple HTML escaping on any error
            import html
            escaped_content = html.escape(content)
            formatted_content = escaped_content.replace('\n', '<br>')
            # Truncate if too long
            if len(formatted_content) > max_length:
                formatted_content = formatted_content[:max_length] + '...<br><em>(truncated)</em>'
        
        # Wrap in styled container with margins and proper font size
        return f'''<div class="markdown-content" style="margin: 12px 16px; font-size: 12px; line-height: 1.4; color: var(--syft-text-primary, inherit);">{formatted_content}</div>'''

@dataclass
class Query:
    """Query information with content and embedding."""
    content: str = ""
    embedding: Optional[List[float]] = None
    
    def __str__(self) -> str:
        """Return the query content as string for backward compatibility."""
        return self.content

@dataclass
class SearchResponse(BaseResponse):
    """Search response data class."""
    query: Query = field(default_factory=lambda: Query())
    results: List[DocumentResult] = field(default_factory=list)
    embedding_model: Optional[str] = None
    similarity_metric: Optional[str] = None

    @classmethod
    def from_dict(cls, response_data: Dict[str, Any], original_query: str) -> 'SearchResponse':
        """Create SearchResponse from RPC response data.
        
        Expects schema.py format with camelCase fields:
        {
            "id": "uuid-string",
            "query": "search query", 
            "queryEmbedding": [...],  # Optional query embedding
            "embeddingModel": "model-name",  # Optional embedding model
            "similarityMetric": "cosine",  # Optional similarity metric
            "results": [
                {
                    "id": "doc-id",
                    "score": 0.95,
                    "content": "document content",
                    "metadata": {...},
                    "embedding": [...]
                }
            ],
            "providerInfo": {...},  # camelCase from endpoint
            "cost": 0.1
        }
        """
        results = []
        
        results_data = response_data.get('results', [])
        for result_data in results_data:
            result = DocumentResult(
                id=result_data.get('id', str(uuid.uuid4())),
                score=float(result_data.get('score', 0.0)),
                content=result_data.get('content', ''),
                metadata=result_data.get('metadata'),
                embedding=result_data.get('embedding')
            )
            results.append(result)
        
        # Extract query information
        query_content = response_data.get('query', original_query)
        query_embedding = response_data.get('queryEmbedding')  # camelCase from endpoint
        query_obj = Query(
            content=query_content,
            embedding=query_embedding
        )
        
        return cls(
            id=response_data.get('id', str(uuid.uuid4())),
            query=query_obj,
            results=results,
            cost=response_data.get('cost'),
            provider_info=response_data.get('providerInfo'),  # camelCase from endpoint
            embedding_model=response_data.get('embeddingModel'),  # camelCase from endpoint
            similarity_metric=response_data.get('similarityMetric')  # camelCase from endpoint
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "query": self.query.content if isinstance(self.query, Query) else self.query,
            "query_embedding": self.query.embedding if isinstance(self.query, Query) else None,
            "embedding_model": self.embedding_model,
            "similarity_metric": self.similarity_metric,
            "results": [
                {
                    "id": result.id,
                    "score": result.score,
                    "content": result.content,
                    "metadata": result.metadata,
                    "embedding": result.embedding
                }
                for result in self.results
            ],
            "provider_info": self.provider_info,
            "cost": self.cost,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat()
        }

    def __str__(self) -> str:
        """Return formatted search results for easy printing."""
        if not self.results:
            return "No results found."
        
        query_content = self.query.content if isinstance(self.query, Query) else self.query
        parts = [f"Search results for: '{query_content}'"]
        for i, result in enumerate(self.results, 1):
            parts.append(f"\n{i}. Score: {result.score:.3f}")
            parts.append(f"   {result.content[:100]}{'...' if len(result.content) > 100 else ''}")
        
        return "\n".join(parts)

    def __repr__(self) -> str:
        """Return user-friendly search response display similar to pipeline result."""
        try:
            from IPython.display import display, HTML
            # In notebook environment, show rich display
            self._display_rich()
            return ""  # Return empty string to avoid double output
        except ImportError:
            # Not in notebook - provide comprehensive text representation
            lines = [
                f"Search Response [{self.status.value.title()}]",
                "",
            ]
            
            # Show query
            query_content = self.query.content if isinstance(self.query, Query) else self.query
            lines.append(f"Query:           {query_content}")
            lines.append("")
            
            # Show results count and top results
            if self.results:
                lines.append(f"Results Found:   {len(self.results)} documents")
                
                # Show top 3 results with scores
                lines.append(f"Top Results:")
                for i, result in enumerate(self.results[:3], 1):
                    content_preview = result.content[:100] + "..." if len(result.content) > 100 else result.content
                    lines.append(f"  {i}. Score {result.score:.3f}: {content_preview}")
                
                if len(self.results) > 3:
                    lines.append(f"  ... and {len(self.results) - 3} more results")
                    
            else:
                lines.append(f"Results Found:   No documents found")
            
            lines.append("")
            
            # Show cost if available
            if self.cost is not None:
                lines.append(f"Total Cost:      ${self.cost:.4f}")
            
            # Show timestamp
            lines.append(f"Timestamp:       {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
            return "\n".join(lines)
    
    def _display_rich(self) -> None:
        """Display rich HTML representation in Jupyter notebooks."""
        from IPython.display import display, HTML
        import uuid
        
        # Status badge styling
        status_class = "badge-ready" if self.status.value == "success" else "badge-not-ready"
        
        # Generate unique ID for this widget instance
        widget_id = str(uuid.uuid4())[:8]
        
        # Results preview
        results_preview = ""
        if self.results:
            results_preview = f"<div class='results-list'>"
            # Show first 3 results
            for i, result in enumerate(self.results[:3], 1):
                content = result.content[:150] + "..." if len(result.content) > 150 else result.content
                results_preview += f"""
                <div class='result-item'>
                    <div class='result-header'>
                        <span class='result-rank'>{i}.</span>
                        <span class='result-score'>Score: {result.score:.3f}</span>
                    </div>
                    <div class='result-content'>{content}</div>
                </div>
                """
            
            # Add collapsable section for remaining results
            if len(self.results) > 3:
                results_preview += f"""
                <div class='more-results-toggle' onclick='toggleResults_{widget_id}()' style='cursor: pointer; user-select: none;'>
                    <span id='toggle-icon-{widget_id}'>▶</span> <span id='toggle-text-{widget_id}'>Show {len(self.results) - 3} more result(s)</span>
                </div>
                <div id='extra-results-{widget_id}' class='extra-results' style='display: none;'>
                """
                # Add remaining results
                for i, result in enumerate(self.results[3:], 4):
                    content = result.content[:150] + "..." if len(result.content) > 150 else result.content
                    results_preview += f"""
                    <div class='result-item'>
                        <div class='result-header'>
                            <span class='result-rank'>{i}.</span>
                            <span class='result-score'>Score: {result.score:.3f}</span>
                        </div>
                        <div class='result-content'>{content}</div>
                    </div>
                    """
                results_preview += "</div>"
                
            results_preview += "</div>"
        else:
            results_preview = "<div class='no-results'>No documents found</div>"
        
        # Cost info
        cost_text = f"${self.cost:.4f}" if self.cost is not None else "Free"
        
        from ..utils.theme import generate_adaptive_css
        
        # Custom styles for search results
        search_styles = {
            '.results-list': {
                'margin-top': '8px'
            },
            '.result-item': {
                'padding': '8px',
                'margin': '4px 0',
                'border-radius': '4px'
            },
            '.result-header': {
                'display': 'flex',
                'justify-content': 'space-between',
                'margin-bottom': '4px',
                'font-size': '11px'
            },
            '.result-rank': {
                'font-weight': '600'
            },
            '.result-score': {
                'font-family': 'monospace'
            },
            '.result-content': {
                'font-size': '11px',
                'white-space': 'pre-wrap',
                'max-height': '60px',
                'overflow': 'hidden'
            },
            '.more-results-toggle': {
                'font-size': '11px',
                'text-align': 'center',
                'padding': '8px 4px',
                'margin': '4px 0',
                'color': 'var(--syft-primary, #0066cc)',
                'transition': 'opacity 0.2s'
            },
            '.more-results-toggle:hover': {
                'opacity': '0.7'
            },
            '.extra-results': {
                'margin-top': '4px'
            },
            '.no-results': {
                'font-size': '11px',
                'font-style': 'italic',
                'text-align': 'center',
                'padding': '8px',
                'border-radius': '4px'
            }
        }
        
        html = generate_adaptive_css('search-response', search_styles)
        
        # Add JavaScript toggle function
        html += f"""
        <script>
        function toggleResults_{widget_id}() {{
            var extraResults = document.getElementById('extra-results-{widget_id}');
            var icon = document.getElementById('toggle-icon-{widget_id}');
            var text = document.getElementById('toggle-text-{widget_id}');
            
            if (extraResults.style.display === 'none') {{
                extraResults.style.display = 'block';
                icon.textContent = '▼';
                text.textContent = 'Hide {len(self.results) - 3} result(s)';
            }} else {{
                extraResults.style.display = 'none';
                icon.textContent = '▶';
                text.textContent = 'Show {len(self.results) - 3} result(s)';
            }}
        }}
        </script>
        """
        
        # Build optional status lines
        optional_lines = ""
        if self.embedding_model:
            optional_lines += f'<div class="status-line"><span class="status-label">Embedding Model:</span><span class="status-value">{self.embedding_model}</span></div>\n            '
        if self.similarity_metric:
            optional_lines += f'<div class="status-line"><span class="status-label">Similarity Metric:</span><span class="status-value">{self.similarity_metric}</span></div>\n            '
        if isinstance(self.query, Query) and self.query.embedding:
            optional_lines += f'<div class="status-line"><span class="status-label">Query Embedding:</span><span class="status-value">{len(self.query.embedding)} dimensions</span></div>\n            '
        
        html += f"""
        <div class="syft-widget">
            <div class="search-response-widget">
                <div class="widget-title">
                Search Response <span class="status-badge {status_class}">{self.status.value.title()}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Query:</span>
                <span class="status-value">{self.query.content if isinstance(self.query, Query) else self.query}</span>
            </div>
            
            {optional_lines}
            <div class="status-line">
                <span class="status-label">Results:</span>
                <span class="status-value">{len(self.results)} documents found</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Cost:</span>
                <span class="status-value">{cost_text}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Timestamp:</span>
                <span class="status-value">{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</span>
            </div>
            
            {results_preview}
        </div>
        """
        
        display(HTML(html))

@dataclass
class HealthResponse(BaseResponse):
    """Health check response data class."""
    project_name: str = ""
    services: Dict[str, Any] = field(default_factory=dict)
    health_status: str = ""  # Separate from BaseResponse.status to avoid confusion
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HealthResponse':
        """Create HealthResponse from dictionary.
        
        Expects endpoint format with camelCase:
        {
            "status": "ok",
            "projectName": "my-project",  # camelCase from endpoint
            "services": {...}
        }
        """
        # Determine ResponseStatus from health status
        health_status = data.get('status', 'unknown')
        response_status = ResponseStatus.SUCCESS if health_status.lower() in ['ok', 'healthy', 'up'] else ResponseStatus.ERROR
        
        return cls(
            id=str(uuid.uuid4()),
            status=response_status,
            health_status=health_status,
            project_name=data.get('projectName', 'unknown'),  # camelCase from endpoint
            services=data.get('services', {}),
            provider_info=data  # Store full response as provider info
        )
    
    def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return self.status == ResponseStatus.SUCCESS
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "status": self.health_status,  # Use the actual health status from endpoint
            "project_name": self.project_name,
            "services": self.services,
            "response_status": self.status.value,  # Include BaseResponse status separately
            "timestamp": self.timestamp.isoformat()
        }

@dataclass
class ErrorResponse(BaseResponse):
    """Error response data class."""
    error_code: str = ""
    error_message: str = ""
    error_details: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        self.status = ResponseStatus.ERROR
    
    @classmethod
    def from_exception(cls, exception: Exception, request_id: Optional[str] = None) -> 'ErrorResponse':
        """Create ErrorResponse from exception."""
        return cls(
            id=request_id or str(uuid.uuid4()),
            error_code=exception.__class__.__name__,
            error_message=str(exception),
            error_details=getattr(exception, 'details', None)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "status": self.status.value,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class AsyncResponse(BaseResponse):
    """Response for asynchronous operations."""
    request_id: str = ""
    poll_url: Optional[str] = None
    estimated_completion_time: Optional[datetime] = None

    def __post_init__(self):
        self.status = ResponseStatus.PENDING
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AsyncResponse':
        """Create AsyncResponse from dictionary."""
        return cls(
            id=str(uuid.uuid4()),
            request_id=data.get('request_id', ''),
            poll_url=data.get('data', {}).get('poll_url'),
            estimated_completion_time=None  # Could parse from data if available
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "status": self.status.value,
            "request_id": self.request_id,
            "poll_url": self.poll_url,
            "estimated_completion_time": self.estimated_completion_time.isoformat() if self.estimated_completion_time else None,
            "timestamp": self.timestamp.isoformat()
        }

# Factory functions for creating responses
def create_successful_chat_response(model: str, content: str, **kwargs) -> ChatResponse:
    """Create a successful chat response."""
    return ChatResponse(
        id=str(uuid.uuid4()),
        model=model,
        message=ChatMessage(role="assistant", content=content),
        usage=ChatUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        **kwargs
    )

def create_successful_search_response(query: str, results: List[DocumentResult], **kwargs) -> SearchResponse:
    """Create a successful search response."""
    query_obj = Query(content=query) if isinstance(query, str) else query
    return SearchResponse(
        id=str(uuid.uuid4()),
        query=query_obj,
        results=results,
        **kwargs
    )

def create_error_response(error_message: str, error_code: str = "ERROR", **kwargs) -> ErrorResponse:
    """Create an error response."""
    return ErrorResponse(
        id=str(uuid.uuid4()),
        error_code=error_code,
        error_message=error_message,
        **kwargs
    )

def create_health_response(project_name: str, is_healthy: bool = True, **kwargs) -> HealthResponse:
    """Create a health check response."""
    return HealthResponse(
        id=str(uuid.uuid4()),
        status=ResponseStatus.SUCCESS if is_healthy else ResponseStatus.ERROR,
        health_status="ok" if is_healthy else "error",
        project_name=project_name,
        services={"status": "ok" if is_healthy else "error"},
        **kwargs
    )

# Response parsers for different formats
class ResponseParser:
    """Parser for converting raw responses to typed response objects."""
    
    @staticmethod
    def parse_chat_response(data: Dict[str, Any]) -> ChatResponse:
        """Parse chat response from raw data."""
        return ChatResponse.from_dict(data)
    
    @staticmethod
    def parse_search_response(data: Dict[str, Any], query: str) -> SearchResponse:
        """Parse search response from raw data."""
        return SearchResponse.from_dict(data, query)
    
    @staticmethod
    def parse_health_response(data: Dict[str, Any]) -> HealthResponse:
        """Parse health response from raw data."""
        return HealthResponse.from_dict(data)
    
    @staticmethod
    def parse_error_response(data: Dict[str, Any]) -> ErrorResponse:
        """Parse error response from raw data."""
        return ErrorResponse(
            id=str(uuid.uuid4()),
            error_code=data.get('error_code', 'UNKNOWN_ERROR'),
            error_message=data.get('message', data.get('error', 'Unknown error')),
            error_details=data.get('details')
        )
    
    @staticmethod
    def parse_async_response(data: Dict[str, Any]) -> AsyncResponse:
        """Parse async response from raw data."""
        return AsyncResponse.from_dict(data)