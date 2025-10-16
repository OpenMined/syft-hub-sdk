"""
SyftBox Accounting Client for managing payments and transactions
"""
import json
import os
import logging

from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from syft_accounting_sdk import UserClient, ServiceException
    HAS_ACCOUNTING_SDK = True
except ImportError:
    # Create stub classes when accounting SDK is not available
    class UserClient:
        def __init__(self, *args, **kwargs):
            raise ImportError("syft-accounting-sdk is required for accounting features. Install with: pip install syft-accounting-sdk")
    
    class ServiceException(Exception):
        pass
    
    HAS_ACCOUNTING_SDK = False

from ..models.validation import UserAccountModel
from ..core.types import APIException
from ..core.exceptions import PaymentError, AuthenticationError
from ..core.settings import settings

logger = logging.getLogger(__name__)


class AccountingClient:
    """Client for handling accounting operations."""
    
    def __init__(self, 
                 accounting_url: str = None,
                 credentials: Optional[Dict[str, str]] = None
        ):
        """Initialize accounting client.
        
        Args:
            accounting_url: URL of the accounting service (defaults to settings)
            credentials: Dict with 'email', 'password', and optionally 'accounting_url'
        """
        # Use settings default if no URL provided
        self.accounting_url = accounting_url or settings.accounting_url
        self._credentials = credentials
        self._client = None
    
    def __dir__(self):
        """Control what appears in autocomplete suggestions.
        
        Returns only the main public methods that users should interact with.
        """
        return [
            # Display methods
            'show',
            
            # Account management
            'configure',
            'register_accounting',
            'create_accounting_user',
            'connect_accounting',
            'save_credentials',
            'get_account_balance',
            
            # Status and info
            'is_configured',
            'get_email',
            
            # Transactions
            'create_transaction',
            
            # Properties
            'accounting_url',
        ]

    def _create_accounting_user(
        self,
        email: str,
        password: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> UserAccountModel:
        """Create a user account on the service."""
        try:
            user, user_pwd = UserClient.create_user(
                url=self.accounting_url,
                organization=organization,
                email=email,
                password=password,
            )

            # Initialize _credentials if None
            if self._credentials is None:
                self._credentials = {}

            self._credentials['email'] = email
            self._credentials['password'] = user_pwd
            self._credentials['organization'] = organization

            return UserAccountModel(
                email=email,
                password=user_pwd,
                organization=organization,
                balance=getattr(user, 'balance', 0.0)  # Default to 0.0 if not available
            )
        except ServiceException as e:
            logger.error(
                f"Failed to create user account: {e.message} with {e.status_code}"
            )
            if e.status_code == 409:
                raise APIException(
                    f"User account already exists: {e.message}. Please use your existing password. If you forgot your password, email support@openmined.org with subject 'Forgot password'",
                    status_code=e.status_code,
                )
            else:
                raise APIException(
                    f"Failed to create user account: {e.message} with {e.status_code}",
                    status_code=e.status_code,
                )

    def register_accounting(self, email: str, password: Optional[str] = None, organization: Optional[str] = None) -> UserAccountModel:
        """Register a new accounting user account.
        
        Args:
            email: User email
            password: User password (optional, will be generated if not provided)
            organization: Organization name (optional)
            
        Returns:
            UserAccountModel with account details
        """
        return self._create_accounting_user(email, password, organization)
    
    async def create_accounting_user(self, email: str, password: Optional[str] = None, organization: Optional[str] = None) -> UserAccountModel:
        """Create a new accounting user account (async version).
        
        Args:
            email: User email
            password: User password (optional, will be generated if not provided)
            organization: Organization name (optional)
            
        Returns:
            UserAccountModel with account details
        """
        return self._create_accounting_user(email, password, organization)
    
    def connect_accounting(self, accounting_url: str, email: str, password: str):
        """Connect to accounting service with credentials.
        
        Args:
            accounting_url: Accounting service URL
            email: User email
            password: User password
        """
        self._configure(accounting_url, email, password)
    
    def configure(self, accounting_url: str, email: str, password: str):
        """Configure accounting client.
        
        Args:
            accounting_url: Accounting service URL
            email: User email
            password: User password
        """
        self._configure(accounting_url, email, password)
    
    def _configure(self, accounting_url: str, email: str, password: str):
        """Internal configure method.
        
        Args:
            accounting_url: Accounting service URL
            email: User email
            password: User password
        """
        self.accounting_url = accounting_url
        self._credentials = {
            "accounting_url": accounting_url,
            "email": email,
            "password": password
        }
        self._client = None  # Reset to recreate with new credentials
    
    def is_configured(self) -> bool:
        """Check if accounting client is configured."""
        return self._credentials is not None
    
    def get_email(self) -> Optional[str]:
        """Get accounting email."""
        return self._credentials["email"] if self._credentials else None
    
    @property
    def client(self) -> UserClient:
        """Get or create accounting client."""
        if self._client is None:
            # Try to get service URL from multiple sources
            accounting_url = self.accounting_url
            
            # Fallback to credentials if accounting_url not set
            if not accounting_url and self._credentials:
                accounting_url = self._credentials.get("accounting_url")
            
            if not accounting_url:
                raise AuthenticationError("No accounting service URL configured")
            
            if not self._credentials:
                raise AuthenticationError("No accounting credentials provided")
            
            try:
                self._client = UserClient(
                    url=accounting_url,
                    email=self._credentials["email"],
                    password=self._credentials["password"]
                )
            except ServiceException as e:
                raise AuthenticationError(f"Failed to create accounting client: {e}")
        
        return self._client
    
    def show(self) -> None:
        """Display service status as an HTML widget."""
        from IPython.display import display, HTML
        
        # Build HTML widget with minimal notebook-like styling
        html = '''
        <style>
            .accounting-widget {
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
                min-width: 100px;
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
        
        # Check current status
        is_configured = self.is_configured()
        email = self.get_email() if is_configured else None
        
        # Determine overall status
        if is_configured:
            overall_badge = '<span class="status-badge badge-ready">Configured</span>'
        else:
            overall_badge = '<span class="status-badge badge-not-ready">Not Configured</span>'
        
        html += f'''
        <div class="accounting-widget">
            <div class="widget-title">
                AccountingClient {overall_badge}
            </div>
            
            <div class="status-line">
                <span class="status-label">Service:</span>
                <span class="status-value">{self.accounting_url or "Not configured"}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">User:</span>
                <span class="status-value">{email or "Not configured"}</span>
            </div>
            
            <div class="status-line">
                <span class="status-label">Password:</span>
                <span class="status-value">{'••••••••' if is_configured else 'Not set'}</span>
            </div>
            
            <div class="docs-section">
                <div style="margin-bottom: 8px; font-weight: 500;">Common operations:</div>
                <div style="line-height: 1.8;">
                    <span class="command-code">client.connect_accounting(url, email, password)</span> — Connect with credentials<br>
                    <span class="command-code">client.register_accounting(email)</span> — Register new account<br>
                    <span class="command-code">client.get_account_balance()</span> — Check balance<br>
                </div>
            </div>
        </div>
        '''
        
        display(HTML(html))
    
    def __repr__(self) -> str:
        """Return a text representation of the client's status."""
        is_configured = self.is_configured()
        email = self.get_email() if is_configured else None
        
        # Determine overall status
        if is_configured:
            status = "[Configured]"
        else:
            status = "[Not Configured]"
        
        # Build text output similar to show()
        lines = [
            f"AccountingClient {status}",
            f"",
            f"Service:     {self.accounting_url or 'Not configured'}",
            f"User:        {email or 'Not configured'}",
            f"Password:    {'••••••••' if is_configured else 'Not set'}",
            f"",
            f"Common operations:",
            f"  client.connect_accounting(url, email, password)  — Connect with credentials",
            f"  client.register_accounting(email)               — Register new account",
            f"  client.get_account_balance()                    — Check balance"
        ]
        
        return "\n".join(lines)
    
    def _repr_html_(self) -> str:
        """Display HTML widget in Jupyter environments - same as show()."""
        from ..utils.theme import generate_adaptive_css
        from ..utils.formatting import display_text_with_copy_widget
        
        is_configured = self.is_configured()
        email = self.get_email() if is_configured else None
        
        # Determine overall status
        if is_configured:
            overall_badge = '<span class="status-badge badge-ready">Configured</span>'
        else:
            overall_badge = '<span class="status-badge badge-not-ready">Not Configured</span>'
        
        # Password display with copy button
        if is_configured and self._credentials and 'password' in self._credentials:
            password_html = display_text_with_copy_widget(
                self._credentials['password'],
                mask=False  # Set to True if you want to mask the password in widget
            )
        else:
            password_html = 'Not set'

        # Generate adaptive CSS for both light and dark themes
        html = generate_adaptive_css('accounting')
        
        html += f'''
        <div class="syft-widget">
            <div class="accounting-widget">
                <div class="widget-title">
                    AccountingClient {overall_badge}
                </div>
                
                <div class="status-line">
                    <span class="status-label">Service:</span>
                    <span class="status-value">{self.accounting_url or "Not configured"}</span>
                </div>
                
                <div class="status-line">
                    <span class="status-label">User:</span>
                    <span class="status-value">{email or "Not configured"}</span>
                </div>
                
                <div class="status-line">
                    <span class="status-label">Password:</span>
                    <span class="status-value">{password_html}</span>
                </div>
                
                <div class="docs-section">
                    <div style="margin-bottom: 8px; font-weight: 500;">Common operations:</div>
                    <div style="line-height: 1.8;">
                        <span class="command-code">client.connect_accounting(url, email, password)</span> — Connect with credentials<br>
                        <span class="command-code">client.register_accounting(email)</span> — Register new account<br>
                        <span class="command-code">client.get_account_balance()</span> — Check balance<br>
                    </div>
                </div>
            </div>
        </div>
        '''
        
        return html
    
    async def create_transaction_token(self, recipient_email: str) -> str:
        """Create a transaction token for paying a service datasite.
        
        Args:
            recipient_email: Email of the service datasite to pay
            
        Returns:
            Transaction token string
        """
        try:
            token = self.client.create_transaction_token(
                recipientEmail=recipient_email
            )
            return token
        except ServiceException as e:
            raise PaymentError(f"Failed to create transaction token: {e}")
    
    def get_account_balance(self) -> float:
        """Get current account balance (synchronous).
        
        Returns:
            Account balance
        """
        try:
            user_info = self.client.get_user_info()
            return user_info.balance
        except ServiceException as e:
            raise PaymentError(f"Failed to get account balance: {e}")
    
    async def _get_account_balance_async(self) -> float:
        """Get current account balance (asynchronous).
        
        Returns:
            Account balance
        """
        try:
            user_info = self.client.get_user_info()
            return user_info.balance
        except ServiceException as e:
            raise PaymentError(f"Failed to get account balance: {e}")
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get complete account information.
        
        Returns:
            Dictionary with account details
        """
        try:
            user_info = self.client.get_user_info()
            return {
                "email": self.get_email(),
                "balance": user_info.balance,
                "currency": "USD",  # This might come from user_info in future
                "account_id": getattr(user_info, 'id', None),
                "created_at": getattr(user_info, 'created_at', None)
            }
        except ServiceException as e:
            raise PaymentError(f"Failed to get account info: {e}")
    
    async def validate_credentials(self) -> bool:
        """Test if current credentials are valid.
        
        Returns:
            True if credentials work, False otherwise
        """
        try:
            self.client.get_user_info()
            return True
        except ServiceException:
            return False
    
    def save_credentials(self, config_path: Optional[str] = None):
        """Save credentials to a config file.
        
        WARNING: This saves sensitive credentials to disk. Only call this method
        if you have explicit user consent to save credentials.
        
        Args:
            config_path: Path to save config (default: ~/.syftbox/accounting.json)
        """
        self._save_credentials(config_path)
    
    def _save_credentials(self, config_path: Optional[str] = None):
        """Internal save credentials method.
        
        WARNING: This saves sensitive credentials to disk. Only call this method
        if you have explicit user consent to save credentials.
        
        Args:
            config_path: Path to save config (default: ~/.syftbox/accounting.json)
        """
        
        if not self._credentials:
            raise ValueError("No credentials to save")
        
        if config_path is None:
            config_dir = Path.home() / ".syftbox"
            config_dir.mkdir(exist_ok=True)
            config_path = config_dir / "accounting.json"
        
        try:
            config = {
                "service_url": self.accounting_url,
                "email": self._credentials["email"],
                "password": self._credentials["password"],
                "created_at": datetime.now().isoformat(),
            }
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Set restrictive permissions
            os.chmod(config_path, 0o600)
            
        except Exception as e:
            raise PaymentError(f"Failed to save credentials: {e}")
    
    @classmethod
    def setup_accounting_discovery(cls) -> tuple['AccountingClient', bool]:
        """Try to auto-discover credentials and return client + success status."""
        
        # Try environment variables
        try:
            client = cls.from_environment()
            return client, True  # Successfully configured
        except AuthenticationError:
            pass
        
        # Try config file
        try:
            client = cls.load_from_config()
            return client, True  # Successfully configured
        except AuthenticationError:
            pass
        
        # No credentials found - create client with default URL from settings
        return cls(), False  # Not configured

    @classmethod
    def load_from_config(cls, config_path: Optional[str] = None) -> 'AccountingClient':
        """Load accounting client from saved config.
        
        Args:
            config_path: Path to config file (default: ~/.syftbox/accounting.json)
            
        Returns:
            Configured AccountingClient
        """
        import json
        from pathlib import Path
        
        if config_path is None:
            config_path = Path.home() / ".syftbox" / "accounting.json"
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            client = cls()
            client._configure(
                accounting_url=config["service_url"],
                email=config["email"],
                password=config["password"]
            )
            return client
            
        except FileNotFoundError:
            raise AuthenticationError("No accounting config file found")
        except Exception as e:
            raise AuthenticationError(f"Failed to load config: {e}")
    
    @classmethod
    def from_environment(cls) -> 'AccountingClient':
        """Create accounting client from environment variables.
        
        Looks for:
        - SYFTBOX_ACCOUNTING_URL
        - SYFTBOX_ACCOUNTING_EMAIL  
        - SYFTBOX_ACCOUNTING_PASSWORD
        
        Returns:
            Configured AccountingClient
        """
        import os
        
        accounting_url = os.getenv("SYFTBOX_ACCOUNTING_URL")
        email = os.getenv("SYFTBOX_ACCOUNTING_EMAIL")
        password = os.getenv("SYFTBOX_ACCOUNTING_PASSWORD")
        
        if not all([email, password]):
            missing = []
            if not email: missing.append("SYFTBOX_ACCOUNTING_EMAIL") 
            if not password: missing.append("SYFTBOX_ACCOUNTING_PASSWORD")
            
            raise AuthenticationError(f"Missing environment variables: {', '.join(missing)}")
        
        client = cls()
        # Use provided URL or fall back to settings default
        effective_url = accounting_url or settings.accounting_url
        client._configure(effective_url, email, password)
        return client