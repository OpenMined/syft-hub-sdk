"""
SyftBox authentication client
"""
import logging
from typing import Optional
from datetime import datetime, timedelta

from syft_core import Client as SyftClient

from ..core.exceptions import AuthenticationError
from .request_client import HTTPClient

logger = logging.getLogger(__name__)


class AuthClient:
    """Client for SyftBox authentication using refresh tokens."""
    
    def __init__(self, syft_client: Optional[SyftClient] = None):
        """Initialize auth client.
        
        Args:
            syft_client: SyftBox core client with config
        """
        self.client = syft_client
        self._auth_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._http_client: Optional[HTTPClient] = None
    
    @property
    def http_client(self) -> HTTPClient:
        """Get HTTP client."""
        if self._http_client is None:
            self._http_client = HTTPClient()
        return self._http_client
    
    async def close(self):
        """Close client."""
        if self._http_client:
            await self._http_client.close()
            self._http_client = None
    
    def is_authenticated(self) -> bool:
        """Check if authenticated."""
        if not self.client or not self.client.config:
            return False
        
        return (
            hasattr(self.client.config, 'refresh_token') and
            self.client.config.refresh_token is not None and
            len(self.client.config.refresh_token.strip()) > 0
        )
    
    def get_user_email(self) -> str:
        """Get user email or guest."""
        if self.is_authenticated():
            return self.client.email
        return "guest@syftbox.net"
    
    async def get_auth_token(self) -> Optional[str]:
        """Get valid auth token."""
        if not self.is_authenticated():
            return None
        
        if self._is_token_valid():
            return self._auth_token
        
        try:
            await self._refresh_auth_token()
            return self._auth_token
        except Exception as e:
            logger.warning(f"Failed to refresh token: {e}")
            self._clear_cached_token()
            return None
    
    async def _refresh_auth_token(self):
        """Refresh auth token."""
        if not self.client or not self.client.config.refresh_token:
            raise AuthenticationError("No refresh token")
        
        refresh_url = f"{self.client.config.server_url}auth/refresh"
        response = await self.http_client.post(
                refresh_url,
                json={"refreshToken": self.client.config.refresh_token},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
        
        if response.status_code == 200:
            data = response.json()
            self._auth_token = data.get("accessToken")
            expires_in = data.get("expiresIn", 3600)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
        else:
            raise AuthenticationError(f"Token refresh failed: {response.status_code}")
    
    def _is_token_valid(self) -> bool:
        """Check if token valid."""
        if not self._auth_token or not self._token_expires_at:
            return False
        return datetime.now() < self._token_expires_at
    
    def _clear_cached_token(self):
        """Clear cached token."""
        self._auth_token = None
        self._token_expires_at = None
    
    @classmethod
    def setup_auth_discovery(cls, syft_client: SyftClient) -> tuple['AuthClient', bool]:
        """Auto-discover authentication."""
        auth_client = cls(syft_client)
        return auth_client, auth_client.is_authenticated()