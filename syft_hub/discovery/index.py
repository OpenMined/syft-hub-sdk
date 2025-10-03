"""
Service indexing and caching system for fast lookups
"""
import json
import time
import threading
import logging

from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict

from ..models.service_info import ServiceInfo
from syft_core import Client as SyftClient
from ..core.types import ServiceType
from .scanner import ServiceScanner
from .parser import MetadataParser

logger = logging.getLogger(__name__)

class ServiceIndex:
    """In-memory index of discovered services for fast searching and filtering."""

    def __init__(self, client: SyftClient, cache_ttl: int = 300):
        """Initialize service index.
        
        Args:
            client: SyftBox client
            cache_ttl: Cache time-to-live in seconds
        """
        self.client = client
        self.scanner = ServiceScanner(client)
        self.parser = MetadataParser()
        self.cache_ttl = cache_ttl
        
        # Index data structures
        self._services: Dict[str, ServiceInfo] = {}  # name -> ServiceInfo
        self._by_datasite: Dict[str, List[str]] = defaultdict(list)  # datasite -> [service_names]
        self._by_service: Dict[ServiceType, List[str]] = defaultdict(list)  # service -> [service_names]
        self._by_tag: Dict[str, List[str]] = defaultdict(list)  # tag -> [service_names]
        self._by_pricing: Dict[str, List[str]] = defaultdict(list)  # pricing_tier -> [service_names]
        
        # Cache metadata
        self._last_updated: Optional[float] = None
        self._is_building: bool = False
        self._build_lock = threading.Lock()
    
    def build_index(self, force_refresh: bool = False) -> None:
        """Build or refresh the service index.
        
        Args:
            force_refresh: Force rebuild even if cache is valid
        """
        with self._build_lock:
            # Check if rebuild is needed
            if not force_refresh and self._is_cache_valid():
                logger.debug("Service index cache is valid, skipping rebuild")
                return
            
            if self._is_building:
                logger.debug("Index build already in progress")
                return
            
            self._is_building = True
            
            try:
                logger.info("Building service index...")
                start_time = time.time()
                
                # Clear existing index
                self._clear_index()
                
                # Scan for metadata files
                metadata_paths = self.scanner.scan_all_datasites()
                logger.debug(f"Found {len(metadata_paths)} metadata files")
                
                # Parse and index services
                indexed_count = 0
                for metadata_path in metadata_paths:
                    try:
                        service_info = self.parser.parse_service_from_files(metadata_path)
                        self._add_service_to_index(service_info)
                        indexed_count += 1
                    except Exception as e:
                        logger.debug(f"Failed to index {metadata_path}: {e}")
                        continue
                
                self._last_updated = time.time()
                build_time = self._last_updated - start_time
                
                logger.info(f"Service index built: {indexed_count} services in {build_time:.2f}s")
                
            finally:
                self._is_building = False
    
    def refresh_index(self) -> None:
        """Force refresh of the index."""
        self.build_index(force_refresh=True)
    
    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid."""
        if self._last_updated is None:
            return False
        
        age = time.time() - self._last_updated
        return age < self.cache_ttl
    
    def _clear_index(self) -> None:
        """Clear all index data structures."""
        self._services.clear()
        self._by_datasite.clear()
        self._by_service.clear()
        self._by_tag.clear()
        self._by_pricing.clear()
    
    def _add_service_to_index(self, service_info: ServiceInfo) -> None:
        """Add a service to all relevant indexes.
        
        Args:
            service_info: Service to add to index
        """
        name = service_info.name
        
        # Main service index
        self._services[name] = service_info
        
        # Datasite index
        self._by_datasite[service_info.datasite].append(name)
        
        # Service index
        for service in service_info.services:
            if service.enabled:
                self._by_service[service.type].append(name)
        
        # Tag index
        for tag in service_info.tags:
            self._by_tag[tag.lower()].append(name)
        
        # Pricing tier index
        pricing_tier = self._get_pricing_tier(service_info.min_pricing)
        self._by_pricing[pricing_tier].append(name)
    
    def _get_pricing_tier(self, price: float) -> str:
        """Categorize pricing into tiers."""
        if price == 0:
            return "free"
        elif price <= 0.01:
            return "budget"
        elif price <= 0.10:
            return "standard"
        else:
            return "paid"
    
    def get_service_by_name(self, name: str) -> Optional[ServiceInfo]:
        """Get service by exact name.
        
        Args:
            name: Service name
            
        Returns:
            ServiceInfo if found, None otherwise
        """
        self._ensure_index_built()
        return self._services.get(name)
    
    def get_services_by_datasite(self, datasite: str) -> List[ServiceInfo]:
        """Get all services by a specific datasite.
        
        Args:
            datasite: Datasite email
            
        Returns:
            List of services owned by the user
        """
        self._ensure_index_built()
        service_names = self._by_datasite.get(datasite, [])
        return [self._services[name] for name in service_names]
    
    def get_services_by_service(self, service_type: ServiceType) -> List[ServiceInfo]:
        """Get all services supporting a specific service.
        
        Args:
            service_type: Service type to filter by
            
        Returns:
            List of services supporting the service
        """
        self._ensure_index_built()
        service_names = self._by_service.get(service_type, [])
        return [self._services[name] for name in service_names]
    
    def get_services_by_tags(self, tags: List[str], match_all: bool = False) -> List[ServiceInfo]:
        """Get services by tags.
        
        Args:
            tags: List of tags to match
            match_all: If True, service must have ALL tags; if False, ANY tag
            
        Returns:
            List of matching services
        """
        self._ensure_index_built()
        
        if not tags:
            return list(self._services.values())
        
        # Normalize tags
        normalized_tags = [tag.lower() for tag in tags]
        
        if match_all:
            # Must have ALL tags (intersection)
            matching_names = None
            for tag in normalized_tags:
                tag_services = set(self._by_tag.get(tag, []))
                if matching_names is None:
                    matching_names = tag_services
                else:
                    matching_names = matching_names.intersection(tag_services)
            
            return [self._services[name] for name in (matching_names or [])]
        else:
            # Must have ANY tag (union)
            matching_names = set()
            for tag in normalized_tags:
                matching_names.update(self._by_tag.get(tag, []))
            
            return [self._services[name] for name in matching_names]
    
    def get_services_by_pricing_tier(self, tier: str) -> List[ServiceInfo]:
        """Get services by pricing tier.
        
        Args:
            tier: Pricing tier ("free", "budget", "standard", "paid")
            
        Returns:
            List of services in the pricing tier
        """
        self._ensure_index_built()
        service_names = self._by_pricing.get(tier, [])
        return [self._services[name] for name in service_names]
    
    def search_services(self, 
                     name_pattern: Optional[str] = None,
                     datasite: Optional[str] = None,
                     service_type: Optional[ServiceType] = None,
                     tags: Optional[List[str]] = None,
                     max_cost: Optional[float] = None,
                     free_only: bool = False,
                     **kwargs) -> List[ServiceInfo]:
        """Search services with multiple criteria.
        
        Args:
            name_pattern: Pattern to match in service names (case-insensitive)
            datasite: Filter by datasite email
            service_type: Filter by service type
            tags: Filter by tags
            max_cost: Maximum cost per request
            free_only: Only include free services
            **kwargs: Additional filter criteria
            
        Returns:
            List of matching services
        """
        self._ensure_index_built()
        
        # Start with all services
        candidates = list(self._services.values())
        
        # Apply filters progressively
        if datasite:
            candidates = [m for m in candidates if m.datasite == datasite]
        
        if service_type:
            candidates = [m for m in candidates if m.supports_service(service_type)]
        
        if tags:
            # Use tag index for efficiency
            tag_services = set()
            for service in self.get_services_by_tags(tags, match_all=False):
                tag_services.add(service.name)
            candidates = [m for m in candidates if m.name in tag_services]
        
        if free_only:
            candidates = [m for m in candidates if m.min_pricing == 0]
        elif max_cost is not None:
            candidates = [m for m in candidates if m.min_pricing <= max_cost]
        
        if name_pattern:
            pattern_lower = name_pattern.lower()
            candidates = [m for m in candidates if pattern_lower in m.name.lower()]
        
        return candidates
    
    def get_all_services(self) -> List[ServiceInfo]:
        """Get all indexed services.
        
        Returns:
            List of all services
        """
        self._ensure_index_built()
        return list(self._services.values())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get index statistics.
        
        Returns:
            Dictionary with statistics
        """
        self._ensure_index_built()
        
        total_services = len(self._services)
        
        # Count by service type
        service_counts = {}
        for service_type in ServiceType:
            service_counts[service_type.value] = len(self._by_service[service_type])
        
        # Count by pricing tier
        pricing_counts = {}
        for tier in ["free", "budget", "standard", "paid"]:
            pricing_counts[tier] = len(self._by_pricing[tier])
        
        # Top datasites
        top_datasites = sorted(
            [(datasite, len(services)) for datasite, services in self._by_datasite.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Top tags
        tag_counts = {tag: len(services) for tag, services in self._by_tag.items()}
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "total_services": total_services,
            "total_datasites": len(self._by_datasite),
            "total_tags": len(self._by_tag),
            "last_updated": self._last_updated,
            "cache_age_seconds": time.time() - self._last_updated if self._last_updated else None,
            "service_counts": service_counts,
            "pricing_counts": pricing_counts,
            "top_datasites": top_datasites,
            "top_tags": top_tags,
        }
    
    def _ensure_index_built(self) -> None:
        """Ensure the index is built before use."""
        if self._last_updated is None or not self._is_cache_valid():
            self.build_index()
    
    def list_datasites(self) -> List[str]:
        """Get list of all service datasites.
        
        Returns:
            Sorted list of datasite emails
        """
        self._ensure_index_built()
        return sorted(self._by_datasite.keys())
    
    def list_tags(self) -> List[str]:
        """Get list of all tags.
        
        Returns:
            Sorted list of unique tags
        """
        self._ensure_index_built()
        return sorted(self._by_tag.keys())
    
    def get_tag_popularity(self) -> Dict[str, int]:
        """Get tag usage statistics.
        
        Returns:
            Dictionary mapping tags to usage count
        """
        self._ensure_index_built()
        return {tag: len(services) for tag, services in self._by_tag.items()}
    
    def find_similar_services(self, service: ServiceInfo, limit: int = 5) -> List[ServiceInfo]:
        """Find services similar to the given service.
        
        Args:
            service: Reference service
            limit: Maximum number of similar services to return
            
        Returns:
            List of similar services, sorted by similarity
        """
        self._ensure_index_built()
        
        candidates = [m for m in self._services.values() if m.name != service.name]
        
        # Calculate similarity scores
        scored_services = []
        for candidate in candidates:
            score = self._calculate_similarity(service, candidate)
            if score > 0:
                scored_services.append((score, candidate))
        
        # Sort by similarity and return top results
        scored_services.sort(key=lambda x: x[0], reverse=True)
        return [service for score, service in scored_services[:limit]]
    
    def _calculate_similarity(self, service1: ServiceInfo, service2: ServiceInfo) -> float:
        """Calculate similarity score between two services.
        
        Args:
            service1: First service
            service2: Second service
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        score = 0.0
        
        # Same datasite bonus
        if service1.datasite == service2.datasite:
            score += 0.3
        
        # Service overlap
        services1 = set(s.type for s in service1.services if s.enabled)
        services2 = set(s.type for s in service2.services if s.enabled)
        
        if services1 and services2:
            service_overlap = len(services1.intersection(services2)) / len(services1.union(services2))
            score += 0.4 * service_overlap
        
        # Tag overlap
        tags1 = set(tag.lower() for tag in service1.tags)
        tags2 = set(tag.lower() for tag in service2.tags)
        
        if tags1 and tags2:
            tag_overlap = len(tags1.intersection(tags2)) / len(tags1.union(tags2))
            score += 0.3 * tag_overlap
        
        return score


class PersistentServiceIndex(ServiceIndex):
    """Service index with disk persistence for faster startup."""
    
    def __init__(self, client: SyftClient, cache_ttl: int = 300, cache_file: Optional[Path] = None):
        # super().__init__(client, cache_ttl)
        
        # if cache_file is None:
        #     cache_file = client.workspace.data_dir / ".cache" / "service_index.json"
    
        # self.cache_file = Path(cache_file)
        # self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        """Initialize persistent service index.
        
        Args:
            syftbox_config: SyftBox configuration
            cache_ttl: Cache time-to-live in seconds
            cache_file: Path to cache file (defaults to ~/.syftbox/service_index.json)
        """
        super().__init__(client, cache_ttl)
        
        if cache_file is None:
            cache_file = client.workspace.data_dir / ".cache" / "service_index.json"

        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    def build_index(self, force_refresh: bool = False) -> None:
        """Build index, trying to load from cache first."""
        with self._build_lock:
            # Try loading from cache first
            if not force_refresh and self._load_from_cache():
                logger.debug("Loaded service index from cache")
                return
            
            # Fall back to full rebuild
            super().build_index(force_refresh)
            
            # Save to cache
            self._save_to_cache()
    
    def _load_from_cache(self) -> bool:
        """Load index from cache file.
        
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not self.cache_file.exists():
                return False
            
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Check cache validity
            last_updated = cache_data.get("last_updated")
            if not last_updated:
                return False
            
            age = time.time() - last_updated
            if age >= self.cache_ttl:
                logger.debug("Cache file expired")
                return False
            
            # Restore index data
            self._services = {}
            services_data = cache_data.get("services", {})
            
            for name, service_data in services_data.items():
                # This is a simplified restoration - in practice you'd need
                # to properly deserialize ServiceInfo objects
                # For now, we'll skip cache loading and always rebuild
                pass
            
            return False  # Skip cache loading for now
            
        except Exception as e:
            logger.debug(f"Failed to load index cache: {e}")
            return False
    
    def _save_to_cache(self) -> None:
        """Save current index to cache file."""
        try:
            # Prepare cache data
            cache_data = {
                "last_updated": self._last_updated,
                "services": {},  # Simplified - would need proper serialization
                "metadata": {
                    "version": "1.0",
                    "total_services": len(self._services),
                    "cache_ttl": self.cache_ttl,
                }
            }
            
            # Save to file
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.debug(f"Saved service index cache to {self.cache_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save index cache: {e}")
    
    def clear_cache(self) -> None:
        """Clear the cache file."""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                logger.debug("Cleared service index cache")
        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")