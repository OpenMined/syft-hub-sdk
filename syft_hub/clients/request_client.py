"""
Basic HTTP client wrapper (simplified - most functionality moved to syft-rpc)
"""
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RequestArgs:
    """Arguments for RPC requests."""
    def __init__(
        self,
        is_accounting: bool = False,
        skip_loader: bool = False,
        timeout: Optional[float] = None,
    ):
        self.is_accounting = is_accounting
        self.skip_loader = skip_loader
        self.timeout = timeout


class HTTPClient:
    """Basic HTTP client for non-RPC requests."""
    
    def __init__(self, timeout: float = 30.0):
        """Initialize HTTP client."""
        self.timeout = timeout
        self._client = None
    
    @property
    def client(self):
        """Get httpx client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get(self, url: str, **kwargs):
        """Make GET request."""
        return await self.client.get(url, **kwargs)
    
    async def post(self, url: str, data=None, json=None, headers=None, **kwargs):
        """Make POST request."""
        return await self.client.post(url, data=data, json=json, headers=headers, **kwargs)
