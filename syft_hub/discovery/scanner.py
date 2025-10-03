"""
File system scanner for discovering SyftBox services across datasites
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

from syft_core import Client as SyftClient

logger = logging.getLogger(__name__)


class ServiceScanner:
    """Scanner for discovering services across SyftBox datasites."""
    
    def __init__(self, syft_client: SyftClient):
        """Initialize scanner with syft-core client.
        
        Args:
            syft_client: SyftBox core client instance
        """
        self.client = syft_client
        self.datasites_path = syft_client.workspace.datasites

    def scan_all_datasites(self, exclude_current_user: bool = False) -> List[Path]:
        """Scan all datasites for published services.
        
        Args:
            exclude_current_user: If True, skip current user's datasite
            
        Returns:
            List of paths to metadata.json files
        """
        if not self.datasites_path.exists():
            logger.warning(f"Datasites directory not found: {self.datasites_path}")
            return []
        
        metadata_paths = []
        current_user_email = self.client.email if exclude_current_user else None
        
        for datasite_dir in self.datasites_path.iterdir():
            if not datasite_dir.is_dir():
                continue
            
            if current_user_email and datasite_dir.name == current_user_email:
                continue
            
            if '@' not in datasite_dir.name:
                continue
            
            try:
                paths = self.scan_datasite(datasite_dir.name)
                metadata_paths.extend(paths)
            except Exception as e:
                logger.warning(f"Error scanning datasite {datasite_dir.name}: {e}")
        
        logger.debug(f"Found {len(metadata_paths)} services")
        return metadata_paths
    
    def scan_datasite(self, datasite: str) -> List[Path]:
        """Scan a specific datasite for published services.
        
        Args:
            datasite: Email of the datasite
            
        Returns:
            List of paths to metadata.json files
        """
        # Path: datasites/{datasite}/public/routers/
        routers_path = self.datasites_path / datasite / "public" / "routers"

        if not routers_path.exists():
            return []
        
        metadata_paths = []
        
        for service_dir in routers_path.iterdir():
            if not service_dir.is_dir():
                continue
            
            metadata_path = service_dir / "metadata.json"
            if metadata_path.exists() and self.is_valid_metadata_file(metadata_path):
                metadata_paths.append(metadata_path)
        
        return metadata_paths
    
    def is_valid_metadata_file(self, metadata_path: Path) -> bool:
        """Check if a metadata.json file is valid and readable."""
        try:
            if not metadata_path.exists() or metadata_path.stat().st_size == 0:
                return False
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                json.load(f)
            
            return True
        except (json.JSONDecodeError, PermissionError, OSError):
            return False


class FastScanner:
    """Optimized scanner with caching."""
    
    def __init__(self, syft_client: SyftClient):
        """Initialize fast scanner.
        
        Args:
            syft_client: SyftBox core client instance
        """
        self.client = syft_client
        self.datasites_path = syft_client.workspace.datasites
        self._cache: Optional[Dict[str, List[Path]]] = None
    
    def scan_with_cache(self, force_refresh: bool = False) -> List[Path]:
        """Scan with caching for better performance."""
        if self._cache is None or force_refresh:
            scanner = ServiceScanner(self.client)
            all_paths = scanner.scan_all_datasites()
            
            # Cache by datasite
            self._cache = {}
            for path in all_paths:
                try:
                    # Extract datasite from path
                    datasite = path.parent.parent.parent.parent.name
                    if datasite not in self._cache:
                        self._cache[datasite] = []
                    self._cache[datasite].append(path)
                except (IndexError, AttributeError):
                    continue
            
            logger.debug(f"Cached {len(all_paths)} services")
        
        # Flatten cache
        all_paths = []
        for paths in self._cache.values():
            all_paths.extend(paths)
        
        return all_paths
    
    def get_service_path(self, datasite: str, service_name: str) -> Optional[Path]:
        """Get direct path to a specific service's metadata file."""
        metadata_path = (
            self.datasites_path / datasite / "public" / "routers" / 
            service_name / "metadata.json"
        )
        return metadata_path if metadata_path.exists() else None
    
    def clear_cache(self):
        """Clear the service cache."""
        self._cache = None