

from typing import List
from datetime import datetime

from ..core.types import DocumentResult
from ..models.responses import ChatResponse

class PipelineResult:
    """Result from pipeline execution"""
    def __init__(self, query: str = None, response: ChatResponse = None, search_results: List[DocumentResult] = None, cost: float = 0.0):
        self.query = query
        self.response = response
        self.search_results = search_results or []
        self.cost = cost
        self.content = response.message.content if response and response.message else ""
        self.timestamp = datetime.now()
    
    def __str__(self):
        return self.content
    
    def __repr__(self):
        """Display pipeline result with rich formatting in Jupyter or text in terminal."""
        try:
            # Check if we're actually in an interactive IPython/Jupyter environment
            import sys
            if 'ipykernel' in sys.modules or 'IPython.kernel' in sys.modules:
                from IPython.display import display, HTML
                # In Jupyter notebook - show HTML widget
                self._display_rich()
                return ""  # Return empty string to avoid double output
            else:
                # Not in notebook - return text representation
                return self._get_text_representation()
        except:
            # Fallback to text representation
            return self._get_text_representation()
    
    def _get_text_representation(self):
        """Get text representation of the pipeline result."""
        lines = [
            "Pipeline Result [Complete]",
            "",
        ]
        
        # Show query if available
        if self.query:
            query_lines = self.query.split('\n')
            if len(query_lines) > 1:
                lines.append("Query:")
                for line in query_lines[:3]:  # Show first 3 lines
                    lines.append(f"  {line}")
                if len(query_lines) > 3:
                    lines.append("  ...")
            else:
                lines.append(f"Query:           {self.query[:100] + '...' if len(self.query) > 100 else self.query}")
            lines.append("")
        
        # Show response content with markdown formatting
        if self.content:
            # Try to format markdown for terminal display
            try:
                # Import markdown2 for text-based markdown rendering
                import markdown2
                # Convert markdown to HTML first
                html_content = markdown2.markdown(
                    self.content,
                    extras=['fenced-code-blocks', 'tables', 'break-on-newline', 'code-friendly']
                )
                # Then convert HTML to plain text with basic formatting
                from html.parser import HTMLParser
                
                class MarkdownTextFormatter(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.text = []
                        self.in_code = False
                        self.in_pre = False
                        self.list_level = 0
                        
                    def handle_starttag(self, tag, attrs):
                        if tag == 'h1':
                            self.text.append('\n# ')
                        elif tag == 'h2':
                            self.text.append('\n## ')
                        elif tag == 'h3':
                            self.text.append('\n### ')
                        elif tag == 'p':
                            self.text.append('\n')
                        elif tag == 'br':
                            self.text.append('\n')
                        elif tag == 'ul' or tag == 'ol':
                            self.list_level += 1
                        elif tag == 'li':
                            self.text.append('\n' + '  ' * (self.list_level - 1) + '• ')
                        elif tag == 'code':
                            self.in_code = True
                            self.text.append('`')
                        elif tag == 'pre':
                            self.in_pre = True
                            self.text.append('\n```\n')
                        elif tag == 'strong' or tag == 'b':
                            self.text.append('**')
                        elif tag == 'em' or tag == 'i':
                            self.text.append('*')
                        elif tag == 'blockquote':
                            self.text.append('\n> ')
                    
                    def handle_endtag(self, tag):
                        if tag in ['h1', 'h2', 'h3', 'p']:
                            self.text.append('\n')
                        elif tag == 'ul' or tag == 'ol':
                            self.list_level -= 1
                        elif tag == 'code':
                            self.in_code = False
                            self.text.append('`')
                        elif tag == 'pre':
                            self.in_pre = False
                            self.text.append('\n```\n')
                        elif tag == 'strong' or tag == 'b':
                            self.text.append('**')
                        elif tag == 'em' or tag == 'i':
                            self.text.append('*')
                    
                    def handle_data(self, data):
                        if self.in_pre:
                            self.text.append(data)
                        else:
                            self.text.append(data.strip() if not self.in_code else data)
                    
                    def get_text(self):
                        return ''.join(self.text).strip()
                
                parser = MarkdownTextFormatter()
                parser.feed(html_content)
                formatted_content = parser.get_text()
                
                # Truncate if too long
                if len(formatted_content) > 1000:
                    formatted_content = formatted_content[:1000] + "\n... (truncated)"
                
                # Add formatted content with proper indentation
                content_lines = formatted_content.split('\n')
                lines.append("Response:")
                for line in content_lines[:20]:  # Show first 20 lines
                    lines.append(f"  {line}")
                if len(content_lines) > 20:
                    lines.append("  ... (truncated)")
                    
            except ImportError:
                # Fallback to simple display if markdown2 is not available
                content_preview = self.content[:500] + "..." if len(self.content) > 500 else self.content
                content_lines = content_preview.split('\n')
                lines.append("Response:")
                for line in content_lines[:10]:  # Show first 10 lines
                    lines.append(f"  {line}")
                if len(content_lines) > 10:
                    lines.append("  ...")
            except Exception:
                # Ultimate fallback
                content_preview = self.content[:200] + "..." if len(self.content) > 200 else self.content
                content_lines = content_preview.split('\n')
                if len(content_lines) > 1:
                    lines.append("Response:")
                    for line in content_lines[:5]:  # Show first 5 lines
                        lines.append(f"  {line}")
                    if len(content_lines) > 5:
                        lines.append("  ...")
                else:
                    lines.append(f"Response:        {content_preview}")
        else:
            lines.append("Response:        [No response generated]")
        
        lines.append("")
        
        # Show search results summary
        if self.search_results:
            lines.append(f"Search Results:  {len(self.search_results)} document{'s' if len(self.search_results) != 1 else ''} found")
            
            # Group sources by datasite
            sources_by_site = {}
            for result in self.search_results:
                if result.metadata:
                    filename = result.metadata.get('filename', 'Unknown')
                    datasite = result.metadata.get('datasite', 'Unknown')
                    if datasite not in sources_by_site:
                        sources_by_site[datasite] = []
                    sources_by_site[datasite].append((filename, result.score))
            
            # Show grouped sources
            for datasite, files in sources_by_site.items():
                lines.append(f"  From {datasite}:")
                for filename, score in files[:2]:  # Show top 2 per datasite
                    lines.append(f"    • {filename} (score: {score:.3f})")
                if len(files) > 2:
                    lines.append(f"    ... and {len(files) - 2} more")
        else:
            lines.append("Search Results:  No documents found")
        
        lines.append("")
        
        # Show execution details
        lines.append("Execution Details:")
        lines.append(f"  Total Cost:    ${self.cost:.4f}")
        
        # Show model info
        if self.response:
            if hasattr(self.response, 'model') and self.response.model:
                lines.append(f"  Model:         {self.response.model}")
            
            # Show token usage if available
            if hasattr(self.response, 'usage') and self.response.usage:
                usage = self.response.usage
                if usage.total_tokens > 0:
                    lines.append(f"  Tokens Used:   {usage.total_tokens:,} total")
                    if usage.prompt_tokens > 0 and usage.completion_tokens > 0:
                        lines.append(f"                 ({usage.prompt_tokens:,} prompt + {usage.completion_tokens:,} completion)")
        
        # Show timestamp
        if hasattr(self, 'timestamp'):
            lines.append(f"  Completed:     {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(lines)
    
    def _display_rich(self):
        """Display rich HTML representation in Jupyter notebook."""
        try:
            from IPython.display import display, HTML
            import markdown2
            import html
            import uuid
        except ImportError:
            try:
                from IPython.display import display, HTML
            except ImportError:
                return
        
        # Prepare query display to match SearchResponse style
        if self.query:
            import html
            escaped_query = html.escape(self.query)
            query_html = f"""
            <div class="status-line">
                <span class="status-label">Query:</span>
                <span class="status-value">{escaped_query}</span>
            </div>
            """
        else:
            query_html = ""
        
        # Prepare response content with markdown rendering
        if self.content:
            try:
                # Try to render as markdown
                import markdown2
                # Convert markdown to HTML with extras for better formatting
                formatted_content = markdown2.markdown(
                    self.content,
                    extras=['fenced-code-blocks', 'tables', 'break-on-newline', 'code-friendly']
                )
                # Truncate if too long
                if len(formatted_content) > 5000:
                    formatted_content = formatted_content[:5000] + '...<br><em>(truncated)</em>'
            except:
                # Fallback to simple HTML escaping
                import html
                escaped_content = html.escape(self.content)
                formatted_content = escaped_content.replace('\n', '<br>')
                if len(formatted_content) > 2000:
                    formatted_content = formatted_content[:2000] + '...<br><em>(truncated)</em>'
        else:
            formatted_content = '<em>No response generated</em>'
        
        # Prepare search results HTML: collapsible, show all on toggle
        widget_id = str(uuid.uuid4())[:8]
        search_results_html = ""
        if self.search_results:
            # Toggle control
            toggle_text = f"See sources ({len(self.search_results)})"
            search_results_html += f"""
            <div class='sources-toggle' onclick='toggleSources_{widget_id}()' style='cursor: pointer; user-select: none; margin: 4px 0;'>
                <span id='sources-toggle-icon-{widget_id}'>▶</span>
                <span id='sources-toggle-text-{widget_id}' style='color: var(--syft-primary, #0066cc); margin-left: 4px;'>{toggle_text}</span>
            </div>
            <div id='sources-list-{widget_id}' class='sources-list' style='display: none;'>
            """
            for i, result in enumerate(self.search_results, 1):
                filename = result.metadata.get('filename', 'Unknown') if result.metadata else 'Unknown'
                content = result.content[:100] + "..." if len(result.content) > 100 else result.content
                content = html.escape(content)
                search_results_html += f"""
                <div class='source-item'>
                    <div class='source-header'>
                        <span class='source-name'>{i}. {filename}</span>
                        <span class='source-score'>Score: {result.score:.3f}</span>
                    </div>
                    <div class='source-preview'>{content}</div>
                </div>
                """
            search_results_html += "</div>"
            # JS toggle function for this widget instance
            search_results_html += f"""
            <script>
            function toggleSources_{widget_id}() {{
                var list = document.getElementById('sources-list-{widget_id}');
                var icon = document.getElementById('sources-toggle-icon-{widget_id}');
                var text = document.getElementById('sources-toggle-text-{widget_id}');
                if (list.style.display === 'none') {{
                    list.style.display = 'block';
                    icon.textContent = '▼';
                    text.textContent = 'Hide sources';
                }} else {{
                    list.style.display = 'none';
                    icon.textContent = '▶';
                    text.textContent = 'See sources ({len(self.search_results)})';
                }}
            }}
            </script>
            """
        else:
            search_results_html = "<div class='no-sources'>No documents found</div>"
        
        # Prepare execution details
        execution_details = []
        
        # Cost
        cost_class = "free" if self.cost == 0 else "paid"
        execution_details.append(f'<span class="pipeline-cost {cost_class}">Cost: ${self.cost:.4f}</span>')

        
        # Token usage
        if self.response and hasattr(self.response, 'usage') and self.response.usage:
            usage = self.response.usage
            if usage.total_tokens > 0:
                execution_details.append(f'<span class="pipeline-tokens">Tokens: {usage.total_tokens:,}</span>')
        
        # Timestamp
        if hasattr(self, 'timestamp'):
            execution_details.append(f'<span class="pipeline-time">{self.timestamp.strftime("%H:%M:%S")}</span>')
        
        execution_html = ' • '.join(execution_details)
        
        # Build complete HTML with SearchResponse-style colors  
        from ..utils.theme import generate_adaptive_css, get_current_theme
        
        # Get current theme for dark mode support
        current_theme = get_current_theme()
        theme_attr = f'data-theme="{current_theme}"' if current_theme else ''
        
        adaptive_css = generate_adaptive_css('pipeline-result')
        
        html_content = adaptive_css + f'''
        <div class="syft-widget" {theme_attr}>
        <style>
            .pipeline-result-widget {{
                font-family: system-ui, -apple-system, sans-serif;
                padding: 12px 0;
                color: var(--syft-text-color, #333);
                line-height: 1.5;
                border: 1px solid var(--syft-border-color, #e0e0e0);
                border-radius: 6px;
                background: var(--syft-bg-color, #fafafa);
                padding: 16px;
                margin: 8px 0;
            }}
            .widget-title {{
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 12px;
                color: var(--syft-text-color, #333);
            }}
            .status-line {{
                display: flex;
                align-items: flex-start;
                margin: 6px 0;
                font-size: 11px;
            }}
            .status-label {{
                color: var(--syft-text-color, #666);
                opacity: 0.8;
                min-width: 100px;
                margin-right: 12px;
                flex-shrink: 0;
            }}
            .status-value {{
                font-family: monospace;
                color: var(--syft-text-color, #333);
                word-break: break-word;
            }}
            .status-badge {{
                display: inline-block;
                padding: 2px 8px;
                border-radius: 3px;
                font-size: 11px;
                margin-left: 8px;
                background: #d4edda;
                color: #155724;
            }}
            
            /* Dark theme for status badges */
            .syft-widget[data-theme="dark"] .status-badge.badge-complete,
            .syft-widget[data-theme="dark"] .status-badge.badge-ready {{
                background: #0d4f14 !important;
                color: #7bc97f !important;
            }}
            .pipeline-query-content {{
                background: var(--syft-bg-color, #f8f9fa);
                border: 1px solid var(--syft-border-color, #e9ecef);
                border-radius: 4px;
                padding: 8px;
                font-family: inherit;
                font-size: 11px;
                color: var(--syft-text-color, #495057);
                white-space: pre-wrap;
                max-height: 60px;
                overflow: hidden;
                margin-top: 4px;
            }}
            .pipeline-response-content {{
                background: var(--syft-bg-color, #f8f9fa);
                border: 1px solid var(--syft-border-color, #e9ecef);
                border-radius: 4px;
                padding: 8px;
                font-family: inherit;
                font-size: 11px;
                color: var(--syft-text-color, #495057);
                max-height: 400px;
                overflow-y: auto;
                margin-top: 4px;
            }}
        </style>
        <style>
            /* Dark theme overrides for pipeline response content */
            .syft-widget[data-theme="dark"] .pipeline-query-content,
            .theme-dark .pipeline-query-content,
            body[theme="dark"] .pipeline-query-content,
            body[data-jp-theme-name*="dark"] .pipeline-query-content,
            body[data-vscode-theme-kind*="dark"] .pipeline-query-content,
            body.vscode-dark .pipeline-query-content,
            body.vs-dark .pipeline-query-content,
            html[data-theme="dark"] .pipeline-query-content,
            html.dark .pipeline-query-content,
            body.dark .pipeline-query-content,
            .jp-mod-dark .pipeline-query-content {{
                background: #363636 !important;
                border: 1px solid #4a4a4a !important;
                color: #f0f0f0 !important;
            }}
            
            .syft-widget[data-theme="dark"] .pipeline-response-content,
            .theme-dark .pipeline-response-content,
            body[theme="dark"] .pipeline-response-content,
            body[data-jp-theme-name*="dark"] .pipeline-response-content,
            body[data-vscode-theme-kind*="dark"] .pipeline-response-content,
            body.vscode-dark .pipeline-response-content,
            body.vs-dark .pipeline-response-content,
            html[data-theme="dark"] .pipeline-response-content,
            html.dark .pipeline-response-content,
            body.dark .pipeline-response-content,
            .jp-mod-dark .pipeline-response-content {{
                background: #363636 !important;
                border: 1px solid #4a4a4a !important;
                color: #f0f0f0 !important;
            }}
            
            /* Fix markdown content colors in dark theme */
            .syft-widget[data-theme="dark"] .pipeline-response-content h1,
            .syft-widget[data-theme="dark"] .pipeline-response-content h2,
            .syft-widget[data-theme="dark"] .pipeline-response-content h3,
            .theme-dark .pipeline-response-content h1,
            .theme-dark .pipeline-response-content h2,
            .theme-dark .pipeline-response-content h3,
            body[theme="dark"] .pipeline-response-content h1,
            body[theme="dark"] .pipeline-response-content h2,
            body[theme="dark"] .pipeline-response-content h3,
            body[data-jp-theme-name*="dark"] .pipeline-response-content h1,
            body[data-jp-theme-name*="dark"] .pipeline-response-content h2,
            body[data-jp-theme-name*="dark"] .pipeline-response-content h3,
            body[data-vscode-theme-kind*="dark"] .pipeline-response-content h1,
            body[data-vscode-theme-kind*="dark"] .pipeline-response-content h2,
            body[data-vscode-theme-kind*="dark"] .pipeline-response-content h3,
            body.vscode-dark .pipeline-response-content h1,
            body.vscode-dark .pipeline-response-content h2,
            body.vscode-dark .pipeline-response-content h3,
            body.vs-dark .pipeline-response-content h1,
            body.vs-dark .pipeline-response-content h2,
            body.vs-dark .pipeline-response-content h3,
            html[data-theme="dark"] .pipeline-response-content h1,
            html[data-theme="dark"] .pipeline-response-content h2,
            html[data-theme="dark"] .pipeline-response-content h3,
            html.dark .pipeline-response-content h1,
            html.dark .pipeline-response-content h2,
            html.dark .pipeline-response-content h3,
            body.dark .pipeline-response-content h1,
            body.dark .pipeline-response-content h2,
            body.dark .pipeline-response-content h3,
            .jp-mod-dark .pipeline-response-content h1,
            .jp-mod-dark .pipeline-response-content h2,
            .jp-mod-dark .pipeline-response-content h3 {{
                color: #f0f0f0 !important;
            }}
            
            .syft-widget[data-theme="dark"] .pipeline-response-content code,
            .theme-dark .pipeline-response-content code,
            body[theme="dark"] .pipeline-response-content code,
            body[data-jp-theme-name*="dark"] .pipeline-response-content code,
            body[data-vscode-theme-kind*="dark"] .pipeline-response-content code,
            body.vscode-dark .pipeline-response-content code,
            body.vs-dark .pipeline-response-content code,
            html[data-theme="dark"] .pipeline-response-content code,
            html.dark .pipeline-response-content code,
            body.dark .pipeline-response-content code,
            .jp-mod-dark .pipeline-response-content code {{
                background: #2b2b2b !important;
                color: #f5f5f5 !important;
            }}
            
            /* Dark mode overrides for sources */
            .syft-widget[data-theme="dark"] .source-item,
            .theme-dark .source-item,
            body[theme="dark"] .source-item,
            body[data-jp-theme-name*="dark"] .source-item,
            body[data-vscode-theme-kind*="dark"] .source-item,
            body.vscode-dark .source-item,
            body.vs-dark .source-item,
            html[data-theme="dark"] .source-item,
            html.dark .source-item,
            body.dark .source-item,
            .jp-mod-dark .source-item {{
                background: #363636 !important;
                border: 1px solid #4a4a4a !important;
            }}
            
            .syft-widget[data-theme="dark"] .source-name,
            .theme-dark .source-name,
            body[theme="dark"] .source-name,
            body[data-jp-theme-name*="dark"] .source-name,
            body[data-vscode-theme-kind*="dark"] .source-name,
            body.vscode-dark .source-name,
            body.vs-dark .source-name,
            html[data-theme="dark"] .source-name,
            html.dark .source-name,
            body.dark .source-name,
            .jp-mod-dark .source-name {{
                color: #f0f0f0 !important;
            }}
            
            .syft-widget[data-theme="dark"] .source-score,
            .theme-dark .source-score,
            body[theme="dark"] .source-score,
            body[data-jp-theme-name*="dark"] .source-score,
            body[data-vscode-theme-kind*="dark"] .source-score,
            body.vscode-dark .source-score,
            body.vs-dark .source-score,
            html[data-theme="dark"] .source-score,
            html.dark .source-score,
            body.dark .source-score,
            .jp-mod-dark .source-score {{
                color: #c0c0c0 !important;
            }}
            
            .syft-widget[data-theme="dark"] .source-preview,
            .theme-dark .source-preview,
            body[theme="dark"] .source-preview,
            body[data-jp-theme-name*="dark"] .source-preview,
            body[data-vscode-theme-kind*="dark"] .source-preview,
            body.vscode-dark .source-preview,
            body.vs-dark .source-preview,
            html[data-theme="dark"] .source-preview,
            html.dark .source-preview,
            body.dark .source-preview,
            .jp-mod-dark .source-preview {{
                color: #f0f0f0 !important;
            }}
            
            .syft-widget[data-theme="dark"] .more-sources,
            .theme-dark .more-sources,
            body[theme="dark"] .more-sources,
            body[data-jp-theme-name*="dark"] .more-sources,
            body[data-vscode-theme-kind*="dark"] .more-sources,
            body.vscode-dark .more-sources,
            body.vs-dark .more-sources,
            html[data-theme="dark"] .more-sources,
            html.dark .more-sources,
            body.dark .more-sources,
            .jp-mod-dark .more-sources {{
                color: #c0c0c0 !important;
            }}
            
            .syft-widget[data-theme="dark"] .no-sources,
            .theme-dark .no-sources,
            body[theme="dark"] .no-sources,
            body[data-jp-theme-name*="dark"] .no-sources,
            body[data-vscode-theme-kind*="dark"] .no-sources,
            body.vscode-dark .no-sources,
            body.vs-dark .no-sources,
            html[data-theme="dark"] .no-sources,
            html.dark .no-sources,
            body.dark .no-sources,
            .jp-mod-dark .no-sources {{
                background: #363636 !important;
                border: 1px solid #4a4a4a !important;
                color: #c0c0c0 !important;
            }}
            
            /* Markdown styles matching SearchResponse theme */
            .pipeline-response-content h1 {{ font-size: 1.3em; margin: 0.5em 0; color: #495057; }}
            .pipeline-response-content h2 {{ font-size: 1.2em; margin: 0.5em 0; color: #495057; }}
            .pipeline-response-content h3 {{ font-size: 1.1em; margin: 0.5em 0; color: #495057; }}
            .pipeline-response-content p {{ margin: 0.5em 0; }}
            .pipeline-response-content ul, .pipeline-response-content ol {{ margin: 0.5em 0; padding-left: 1.2em; }}
            .pipeline-response-content li {{ margin: 0.2em 0; }}
            .pipeline-response-content code {{ background: #e9ecef; padding: 1px 3px; border-radius: 2px; font-family: monospace; font-size: 0.9em; }}
            .pipeline-response-content pre {{ background: #495057; color: #f8f9fa; padding: 8px; border-radius: 3px; overflow-x: auto; }}
            .pipeline-response-content pre code {{ background: none; color: inherit; padding: 0; }}
            .pipeline-response-content blockquote {{ border-left: 3px solid #6c757d; margin: 0.5em 0; padding-left: 0.8em; color: #6c757d; }}
            .pipeline-response-content strong {{ font-weight: 600; color: #495057; }}
            .pipeline-response-content em {{ font-style: italic; }}
            .sources-list {{
                margin-top: 8px;
            }}
            .source-item {{
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
                padding: 8px;
                margin: 4px 0;
            }}
            .source-header {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 4px;
                font-size: 11px;
            }}
            .source-name {{
                font-weight: 600;
                color: #495057;
            }}
            .source-score {{
                color: #6c757d;
                font-family: monospace;
            }}
            .source-preview {{
                font-size: 11px;
                color: #495057;
                white-space: pre-wrap;
                max-height: 60px;
                overflow: hidden;
            }}
            .more-sources {{
                font-size: 11px;
                color: #6c757d;
                font-style: italic;
                text-align: center;
                padding: 4px;
            }}
            .no-sources {{
                font-size: 11px;
                color: #6c757d;
                font-style: italic;
                text-align: center;
                padding: 8px;
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
            }}
        </style>
        
        <div class="pipeline-result-widget">
            <div class="widget-title">
                Pipeline Result <span class="status-badge">Complete</span>
            </div>
            
            {query_html}
            
            <div class="status-line">
                <span class="status-label">Response:</span>
            </div>
            <div class="pipeline-response-content">{formatted_content}</div>
            
            <div class="status-line">
                <span class="status-label">Sources:</span>
                <span class="status-value">{len(self.search_results)} document{'s' if len(self.search_results) != 1 else ''} found</span>
            </div>
            {search_results_html}
            
            <div class="status-line">
                <span class="status-label">Cost:</span>
                <span class="status-value">{execution_html}</span>
            </div>
        </div>
        '''
        
        display(HTML(html_content))