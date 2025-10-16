# syft_hub/views/progress_widget.py

def get_progress_widget_html(completed: int, total: int, online_count: int) -> str:
    """Generate themed HTML for progress display."""
    progress_pct = int((completed / total) * 100)
    
    return f'''
    <style>
        #health-check-progress {{
            font-family: var(--vscode-editor-font-family, var(--jp-ui-font-family, monospace));
            padding: 8px;
            background: #f5f5f5;
            border-radius: 4px;
            margin: 4px 0;
            color: #333;
            transition: background-color 0.2s ease, color 0.2s ease;
        }}
        
        #health-check-progress .progress-text {{
            margin-bottom: 4px;
        }}
        
        #health-check-progress .progress-bar-container {{
            background: #e0e0e0;
            border-radius: 8px;
            height: 24px;
            position: relative;
            overflow: hidden;
        }}
        
        #health-check-progress .progress-bar-fill {{
            background: linear-gradient(90deg, #4CAF50, #45a049);
            height: 100%;
            width: {progress_pct}%;
            transition: width 0.3s;
        }}
        
        #health-check-progress .progress-bar-label {{
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }}
        
        /* Dark theme */
        @media (prefers-color-scheme: dark) {{
            #health-check-progress {{
                background: #2b2b2b !important;
                color: #f0f0f0 !important;
            }}
            #health-check-progress .progress-bar-container {{
                background: #363636 !important;
            }}
            #health-check-progress .progress-bar-label {{
                color: #f0f0f0 !important;
            }}
        }}
        
        body[data-theme="dark"] #health-check-progress,
        body.dark-theme #health-check-progress,
        body[data-vscode-theme-kind*="dark"] #health-check-progress,
        body.vscode-dark #health-check-progress {{
            background: #2b2b2b !important;
            color: #f0f0f0 !important;
        }}
        
        body[data-theme="dark"] #health-check-progress .progress-bar-container,
        body.dark-theme #health-check-progress .progress-bar-container,
        body[data-vscode-theme-kind*="dark"] #health-check-progress .progress-bar-container,
        body.vscode-dark #health-check-progress .progress-bar-container {{
            background: #363636 !important;
        }}
        
        body[data-theme="dark"] #health-check-progress .progress-bar-label,
        body.dark-theme #health-check-progress .progress-bar-label,
        body[data-vscode-theme-kind*="dark"] #health-check-progress .progress-bar-label,
        body.vscode-dark #health-check-progress .progress-bar-label {{
            color: #f0f0f0 !important;
        }}
    </style>
    
    <div id="health-check-progress">
        <div class="progress-text">🔍 Checking service health...</div>
        <div class="progress-bar-container">
            <div class="progress-bar-fill"></div>
            <div class="progress-bar-label">
                {completed}/{total} services | ✅ {online_count} online ({progress_pct}%)
            </div>
        </div>
    </div>
    '''