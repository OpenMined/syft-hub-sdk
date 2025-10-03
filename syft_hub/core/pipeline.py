"""
Pipeline implementation for SyftBox NSAI SDK
Supports both inline and object-oriented RAG/FedRAG workflows
"""
import asyncio
import logging
import sys
from typing import List, Dict, Optional, Union, TYPE_CHECKING

from .types import ServiceType, ServiceSpec
from .exceptions import ValidationError, ServiceNotFoundError, ServiceNotSupportedError
from ..models.pipeline import PipelineResult
from ..utils.estimator import CostEstimator

if TYPE_CHECKING:
    from ..main import Client
    from .service import Service 

logger = logging.getLogger(__name__)

class PipelineOutputHandler:
    """Handles output collection and display for pipeline execution."""
    
    def __init__(self):
        self.messages = []
        self.in_jupyter = self._detect_jupyter()
    
    def _detect_jupyter(self):
        """Detect if we're running in Jupyter."""
        try:
            return 'ipykernel' in sys.modules or 'IPython' in sys.modules
        except:
            return False
    
    def print(self, *args, **kwargs):
        """Context-aware print that works in both Jupyter and regular Python."""
        message = ' '.join(str(arg) for arg in args)
        self.messages.append(message)
        
        if not self.in_jupyter:
            # In regular Python, print immediately
            print(*args, **kwargs)
    
    def get_output(self):
        """Get all collected output as a string."""
        return '\n'.join(self.messages)

# Global output handler for pipeline
_pipeline_output = PipelineOutputHandler()

def _jupyter_aware_print(*args, **kwargs):
    """Print function that works correctly in both Jupyter notebooks and regular Python contexts."""
    _pipeline_output.print(*args, **kwargs)

class Pipeline:
    """Pipeline for structured RAG/FedRAG workflows.
    
    Provides a streamlined way to combine multiple search services (data sources)
    with chat services (synthesizers) to create powerful RAG/FedRAG applications.
    """
    
    def __init__(
            self, 
            client: 'Client', 
            data_sources: Optional[List[Union[str, Dict, 'Service']]] = None,
            synthesizer: Optional[Union[str, Dict, 'Service']] = None,
            context_format: str = "simple"
        ):
        """Initialize the pipeline with data sources and synthesizer.
        
        Args:
            client: SyftBox client instance
            data_sources: List of search services for data retrieval. Each item can be:
                - str: Service name like "alice@example.com/docs" 
                - dict: Service with params like {"name": "service", "topK": 10}
                - Service: Loaded service object from client.load_service()
            synthesizer: Chat service for response generation. Can be:
                - str: Service name like "ai@openai.com/gpt-4"
                - dict: Service with params like {"name": "service", "temperature": 0.7}
                - Service: Loaded service object
            context_format: Format for injecting search context (default: "simple")
                - "simple": Clean format with ## headers for each source document
                - "frontend": Compact [filename] format matching web application
        """
        self.client = client
        self.data_sources: List[ServiceSpec] = []
        self.synthesizer: Optional[ServiceSpec] = None
        self.context_format = context_format
            
        # Handle inline initialization
        if data_sources:
            for source in data_sources:
                if isinstance(source, str):
                    self.data_sources.append(ServiceSpec(name=source, params={}))
                elif hasattr(source, 'full_name'):  # Service object
                    self.data_sources.append(ServiceSpec(name=source.full_name, params={}))
                elif isinstance(source, dict):
                    name = source.pop('name')
                    self.data_sources.append(ServiceSpec(name=name, params=source))
                else:
                    raise ValidationError(f"Invalid data source format: {source}. Expected str (service name), dict (service with params), or Service object.")

        if synthesizer:
            if isinstance(synthesizer, str):
                self.synthesizer = ServiceSpec(name=synthesizer, params={})
            elif hasattr(synthesizer, 'full_name'):  # Service object
                self.synthesizer = ServiceSpec(name=synthesizer.full_name, params={})
            elif isinstance(synthesizer, dict):
                name = synthesizer.pop('name')
                self.synthesizer = ServiceSpec(name=name, params=synthesizer)
            else:
                raise ValidationError(f"Invalid synthesizer format: {synthesizer}. Expected str (service name), dict (service with params), or Service object.")
    
    def __repr__(self) -> str:
        """Display pipeline configuration and usage examples."""
        try:
            from IPython.display import display, HTML
            # In notebook environment, show HTML widget
            self._show_html_widget()
            return ""  # Return empty string to avoid double output
        except ImportError:
            # Not in notebook - provide comprehensive text representation
            return self._get_text_representation()
    
    def _get_text_representation(self) -> str:
        """Get text representation of the pipeline."""
        # Determine pipeline status
        is_configured = bool(self.data_sources and self.synthesizer)
        status = "Configured" if is_configured else "Incomplete"
        status_emoji = "✅" if is_configured else "⚠️"
        
        # Header with styling
        header = f"🔗 RAG Pipeline {status_emoji} [{status}]"
        separator = "=" * min(len(header.replace('🔗', '').replace(status_emoji, '').strip()), 60)
        
        lines = [
            header,
            separator,
            "",
            f"📊 Data Sources:   {len(self.data_sources)} sources",
        ]
        
        # List data sources with better styling
        if self.data_sources:
            for i, source in enumerate(self.data_sources, 1):
                params_str = ""
                if source.params:
                    key_params = [f"{k}={v}" for k, v in list(source.params.items())[:2]]
                    params_str = f" ({', '.join(key_params)})"
                lines.append(f"   {i}. 📄 {source.name}{params_str}")
        else:
            lines.append("   • None configured")
        
        lines.append("")
        
        # Synthesizer info with emoji
        synthesizer_name = self.synthesizer.name if self.synthesizer else "None configured"
        synthesizer_info = f"🤖 Synthesizer:    {synthesizer_name}"
        if self.synthesizer and self.synthesizer.params:
            key_params = [f"{k}={v}" for k, v in list(self.synthesizer.params.items())[:2]]
            synthesizer_info += f" ({', '.join(key_params)})"
        lines.append(synthesizer_info)
        
        lines.extend([
            f"📝 Context Format: {self.context_format}",
            "",
        ])
        
        # Cost estimation with emoji
        try:
            estimated_cost = self.estimate_cost()
            cost_str = f"${estimated_cost:.4f}" if estimated_cost > 0 else "Free"
            lines.append(f"💰 Estimated Cost: {cost_str} per execution")
        except:
            lines.append("💰 Estimated Cost: Unable to calculate")
        
        lines.extend([
            "",
            "💡 Usage Examples:",
        ])
        
        if status == "Configured":
            lines.extend([
                "   ▶️  Execute pipeline:",
                "      result = pipeline.run([",
                "          {'role': 'user', 'content': 'Your question here'}",
                "      ])",
                "",
                "   ⚡ Execute asynchronously:", 
                "      result = await pipeline.run_async([",
                "          {'role': 'user', 'content': 'Your question here'}",
                "      ])",
                "",
                "   📤 Access results:",
                "      print(result.response.content)  # Synthesized response",
                "      print(result.search_results)    # Source documents", 
                "      print(f'Cost: ${result.cost}')  # Execution cost"
            ])
        else:
            lines.extend([
                "   🔧 Add data sources first:",
                "      pipeline.add_source('alice@example.com/docs')",
                "      pipeline.set_synthesizer('ai@openai.com/gpt-4')",
                "",
                "   🚀 Or create configured pipeline directly:",
                "      pipeline = client.pipeline(",
                "      data_sources=['alice@example.com/docs'],",
                "      synthesizer='ai@openai.com/gpt-4'",
                "  )"
            ])
        
        return "\n".join(lines)
    
    def _show_html_widget(self) -> None:
        """Show HTML widget in notebook environment."""
        try:
            from IPython.display import display, HTML
        except ImportError:
            return
        
        # Determine pipeline status and styling
        is_configured = bool(self.data_sources and self.synthesizer)
        status_text = "Configured" if is_configured else "Incomplete"
        status_class = "configured" if is_configured else "incomplete"
        
        # Build data sources HTML with better structure
        sources_html = ""
        if self.data_sources:
            sources_items = []
            for i, source in enumerate(self.data_sources, 1):
                params_str = ""
                if source.params:
                    params_list = [f"{k}={v}" for k, v in list(source.params.items())[:2]]
                    params_str = f" <span style='color: #666; font-size: 11px;'>({', '.join(params_list)})</span>"
                sources_items.append(
                    f'<div style="margin: 8px 0; padding: 12px; background: var(--syft-secondary-bg, #f8f9fa); border-radius: 4px; border-left: 3px solid var(--syft-border-color, #e1e1e1);">'
                    f'<span style="font-weight: 500; color: var(--syft-text-primary, #333);">{i}. {source.name}</span>{params_str}'
                    f'</div>'
                )
            sources_html = ''.join(sources_items)
        else:
            sources_html = '<div style="padding: 12px; color: var(--syft-text-secondary, #666); font-style: italic;">No data sources configured</div>'
        
        # Build synthesizer HTML
        synthesizer_html = ""
        if self.synthesizer:
            params_str = ""
            if self.synthesizer.params:
                params_list = [f"{k}={v}" for k, v in list(self.synthesizer.params.items())[:2]]
                params_str = f" <span style='color: #666; font-size: 11px;'>({', '.join(params_list)})</span>"
            synthesizer_html = f'<div style="margin: 8px 0; padding: 12px; background: var(--syft-secondary-bg, #f8f9fa); border-radius: 4px; border-left: 3px solid var(--syft-border-color, #e1e1e1);"><span style="font-weight: 500; color: var(--syft-text-primary, #333);">{self.synthesizer.name}</span>{params_str}</div>'
        else:
            synthesizer_html = '<div style="padding: 12px; color: var(--syft-text-secondary, #666); font-style: italic;">No synthesizer configured</div>'
        
        # Cost estimation
        try:
            estimated_cost = self.estimate_cost()
            cost_display = f"${estimated_cost:.4f}" if estimated_cost > 0 else "Free"
        except:
            cost_display = "Unable to calculate"
        
        # Usage examples based on configuration
        if is_configured:
            usage_examples = """# Execute pipeline
result = pipeline.run([
    {'role': 'user', 'content': 'Your question here'}
])

# Access results  
print(result.response.content)  # Synthesized response
print(result.search_results)    # Source documents
print(f'Cost: ${result.cost}')  # Execution cost"""
        else:
            usage_examples = """# Add components
pipeline.add_source('alice@example.com/docs')
pipeline.set_synthesizer('ai@openai.com/gpt-4')

# Or create configured pipeline directly
pipeline = client.pipeline(
    data_sources=['alice@example.com/docs'],
    synthesizer='ai@openai.com/gpt-4'
)"""
        
        from ..utils.theme import generate_adaptive_css
        
        html = generate_adaptive_css('pipeline')
        html += f'''
        <div class="syft-widget">
            <div class="pipeline-widget">
                <div class="widget-title">
                    RAG Pipeline <span class="status-badge {status_class}">{status_text}</span>
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Context Format:</span>
                    <span class="status-value">{self.context_format}</span>
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Estimated Cost:</span>
                    <span class="status-value" style="color: {'#28a745' if 'Free' in cost_display else '#1976d2'}; font-weight: 600;">{cost_display} per execution</span>
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Data Sources:</span>
                    <span class="status-value">{len(self.data_sources)} configured</span>
                </div>
                <div style="margin: 0 16px;">
                    {sources_html}
                </div>
                
                <div class="status-line" style="margin: 8px 16px;">
                    <span class="status-label">Synthesizer:</span>
                    <span class="status-value">{"Configured" if self.synthesizer else "Not configured"}</span>
                </div>
                <div style="margin: 0 16px;">
                    {synthesizer_html}
                </div>
                
                <div class="widget-title" style="margin: 16px 0 12px 0;">
                    Usage Examples
                </div>
                {self._build_usage_examples_html(usage_examples)}
            </div>
        </div>
        '''
        
        display(HTML(html))
    
    def _build_usage_examples_html(self, usage_examples: str) -> str:
        """Build HTML for usage examples with copy button."""
        # Split examples into lines
        lines = usage_examples.strip().split('\n')
        code_display = "<br>".join(lines)
        
        
        return f'''<div class="code-block" style="padding: 12px; margin: 0;">
    <span class="command-code" style="font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace; font-size: 12px; line-height: 1.5; color: var(--syft-text-primary, inherit);">{code_display}</span>
</div>'''
    
    def add_source(self, service_name: str, **params) -> 'Pipeline':
        """Add a data source service with parameters"""
        self.data_sources.append(ServiceSpec(name=service_name, params=params))
        return self
    
    def set_synthesizer(self, service_name: str, **params) -> 'Pipeline':
        """Set the synthesizer service with parameters"""
        self.synthesizer = ServiceSpec(name=service_name, params=params)
        return self
    
    def validate(self, skip_health_check: bool = False) -> bool:
        """Check that all services exist, are reachable, and support required operations
        
        Args:
            skip_health_check: If True, skip health checks during validation (used during pipeline creation)
        """
        if not self.data_sources:
            raise ValidationError("No data sources configured")
        
        if not self.synthesizer:
            raise ValidationError("No synthesizer configured")
        
        # Validate data sources
        for source_spec in self.data_sources:
            try:
                service = self.client.load_service(source_spec.name, skip_health_check=skip_health_check)
                if not service.supports_search:
                    raise ServiceNotSupportedError(service.name, "search", service._service_info)
            except ServiceNotFoundError:
                raise ValidationError(f"Data source service '{source_spec.name}' not found")
        
        # Validate synthesizer
        try:
            service = self.client.load_service(self.synthesizer.name, skip_health_check=skip_health_check)
            if not service.supports_chat:
                raise ServiceNotSupportedError(service.name, "chat", service._service_info)
        except ServiceNotFoundError:
            raise ValidationError(f"Synthesizer service '{self.synthesizer.name}' not found")
        
        return True
    
    def estimate_cost(self, message_count: int = 1) -> float:
        """Estimate total cost for pipeline execution"""
        
        # Prepare data sources for cost estimation
        data_sources = []
        for source_spec in self.data_sources:
            try:
                # Skip health check during cost estimation (creation-time operation)
                service = self.client.load_service(source_spec.name, skip_health_check=True)
                data_sources.append((service._service_info, source_spec.params))
            except ServiceNotFoundError:
                logger.warning(f"Service '{source_spec.name}' not found during cost estimation")
                continue
        
        # Get synthesizer service
        synthesizer_service = None
        if self.synthesizer:
            try:
                # Skip health check during cost estimation (creation-time operation)
                service = self.client.load_service(self.synthesizer.name, skip_health_check=True)
                synthesizer_service = service._service_info
            except ServiceNotFoundError:
                logger.warning(f"Synthesizer service '{self.synthesizer.name}' not found during cost estimation")
        
        if not data_sources or not synthesizer_service:
            return 0.0
        
        # Estimate cost
        return CostEstimator.estimate_pipeline_cost(
            data_sources=data_sources,
            synthesizer_service=synthesizer_service,
            message_count=message_count
        )
    
    def run(self, messages: List[Dict[str, str]], continue_without_results: bool = False) -> PipelineResult:
        """Execute the pipeline synchronously
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            continue_without_results: If True, automatically continue synthesis even if no search results found.
                                    If False (default), prompts user when no results found.
        """
        from ..utils.async_utils import detect_async_context, run_async_in_thread
        
        if detect_async_context():
            # In Jupyter or other async context, capture output and display it properly
            _pipeline_output.messages.clear()  # Clear previous messages
            result = run_async_in_thread(self.run_async(messages, continue_without_results))
            
            # Display captured output in current Jupyter cell
            if _pipeline_output.in_jupyter and _pipeline_output.messages:
                try:
                    output_text = _pipeline_output.get_output()
                    print(output_text)  # Use regular print to display in current cell
                except:
                    pass
            
            return result
        else:
            # In regular sync context, use asyncio.run
            return asyncio.run(self.run_async(messages, continue_without_results))
    
    async def run_async(self, messages: List[Dict[str, str]], continue_without_results: bool = False) -> PipelineResult:
        """Execute the pipeline asynchronously with parallel search execution
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            continue_without_results: If True, automatically continue synthesis even if no search results found.
                                    If False (default), prompts user when no results found.
        """
        # Validate pipeline first
        self.validate()
        
        # Extract search query from messages
        if not messages:
            raise ValidationError("No messages provided")
        
        # Use the last user message as the search query
        search_query = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                search_query = msg.get("content")
                break
        
        if not search_query:
            raise ValidationError("No user message found for search query")
        
        # Execute searches in parallel
        search_tasks = []
        for source_spec in self.data_sources:
            task = self._execute_search(source_spec, search_query)
            search_tasks.append(task)
        
        # Wait for all searches to complete
        search_results_list = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Process search results and handle errors
        all_search_results = []
        total_cost = 0.0
        
        # Print search progress header
        _jupyter_aware_print(f"\n📊 Searching {len(self.data_sources)} data source(s)...")
        
        for i, result in enumerate(search_results_list):
            source_name = self.data_sources[i].name
            
            if isinstance(result, Exception):
                logger.warning(f"Search failed for source {source_name}: {result}")
                _jupyter_aware_print(f"❌ {source_name}: Search failed - {result}")
                continue
            
            search_response, cost = result
            num_results = len(search_response.results)
            
            # Print summary for this source
            if num_results > 0:
                _jupyter_aware_print(f"✅ {source_name}: Found {num_results} result(s)")
                # Show top result preview
                if search_response.results:
                    top_result = search_response.results[0]
                    preview = top_result.content[:100] + "..." if len(top_result.content) > 100 else top_result.content
            else:
                _jupyter_aware_print(f"⚠️  {source_name}: No results found")
            
            all_search_results.extend(search_response.results)
            total_cost += cost
        
        if not all_search_results:
            if not continue_without_results:
                # Interactive prompt
                _jupyter_aware_print("\n⚠️  No search results found from data sources")
                _jupyter_aware_print("Options: Continue with predictions without sources or cancel")
                
                try:
                    response = input("Continue without search results? (y/n): ").lower().strip()
                    if response not in ['y', 'yes']:
                        _jupyter_aware_print("Pipeline cancelled.")
                        raise ValidationError("Pipeline cancelled by user - no search results available")
                except (EOFError, KeyboardInterrupt):
                    _jupyter_aware_print("\nPipeline cancelled.")
                    raise ValidationError("Pipeline cancelled by user - no search results available")
            
            _jupyter_aware_print("Continuing with synthesis without search context...")
            logger.warning("All data source searches failed or returned empty results")
        
        # Remove duplicate results
        unique_results = self.client.remove_duplicate_results(all_search_results)
        
        # Print search summary
        _jupyter_aware_print(f"📋 Search Summary: {len(unique_results)} result(s)")
        
        # Format search context for synthesizer
        context = self.client.format_search_context(unique_results, self.context_format)
        
        # Prepare messages with context
        enhanced_messages = self._prepare_enhanced_messages(messages, context)
        
        # Print synthesis start
        _jupyter_aware_print(f"\n🤖 Synthesizing response with {self.synthesizer.name}...")
        
        # Execute synthesis
        synthesizer_cost, chat_response = await self._execute_synthesis(enhanced_messages)
        total_cost += synthesizer_cost
        
        # Print synthesis result
        if chat_response and chat_response.message:
            # Show preview of the response
            content = chat_response.message.content
            preview = content[:200] + "..." if len(content) > 200 else content
            _jupyter_aware_print(f"✅ Response generated ({len(content)} chars)")
        else:
            _jupyter_aware_print(f"⚠️  No response generated")
        
        # Print cost summary
        
        return PipelineResult(
            query=search_query,
            response=chat_response,
            search_results=unique_results,
            cost=total_cost
        )
    
    async def _execute_search(self, source_spec: ServiceSpec, query: str):
        """Execute search on a single data source"""
        try:
            # Get service info but use the service's own search method
            # This ensures the service uses its own properly initialized context
            service = self.client.load_service(source_spec.name)
            
            # Use the service's search_async method directly
            # This avoids creating a new SearchService with potentially mismatched event loop
            response = await service.search_async(
                message=query,
                **source_spec.params
            )

            # Estimate cost
            topK = source_spec.params.get('topK', len(response.results))
            cost = CostEstimator.estimate_search_cost(service._service_info, query_count=1, result_limit=topK)
            
            return response, cost
            
        except Exception as e:
            logger.error(f"Search failed for {source_spec.name}: {e}")
            raise
    
    async def _execute_synthesis(self, messages: List[Dict[str, str]]):
        """Execute synthesis with the enhanced messages"""
        try:
            # Load service and use its chat_async method directly
            service = self.client.load_service(self.synthesizer.name)
            
            # Debug: Log what we're sending
            logger.debug(f"Sending {len(messages)} messages to synthesizer")
            logger.debug(f"Synthesizer params: {self.synthesizer.params}")
            
            # Execute chat using the service's method
            response = await service.chat_async(
                messages=messages,
                **self.synthesizer.params
            )
            
            # Debug: Log what we received
            logger.debug(f"Received response type: {type(response)}")
            if response:
                logger.debug(f"Response has message: {hasattr(response, 'message')}")
                if hasattr(response, 'message') and response.message:
                    logger.debug(f"Message content length: {len(response.message.content) if response.message.content else 0}")
            
            # Estimate cost
            cost = CostEstimator.estimate_chat_cost(service._service_info, message_count=len(messages))
            
            return cost, response
            
        except Exception as e:
            logger.error(f"Synthesis failed for {self.synthesizer.name}: {e}")
            raise
    
    def _prepare_enhanced_messages(self, original_messages: List[Dict[str, str]], context: str) -> List[Dict[str, str]]:
        """Prepare messages with search context injected"""
        if not context.strip():
            return original_messages
        
        # Find the last user message and enhance it with context
        enhanced_messages = []
        context_injected = False
        
        for msg in original_messages:
            if msg.get("role") == "user" and not context_injected:
                # Inject context before the user's message
                enhanced_content = f"Context:\n{context}\n\nUser Question: {msg.get('content', '')}"
                enhanced_messages.append({
                    "role": "user",
                    "content": enhanced_content
                })
                context_injected = True
            else:
                enhanced_messages.append(msg)
        
        # If no user message found, add context as system message
        if not context_injected:
            enhanced_messages.insert(0, {
                "role": "system", 
                "content": f"Use this context to answer questions:\n{context}"
            })
        
        return enhanced_messages