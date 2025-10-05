"""
Parser for SyftBox service metadata
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.types import ServiceItem, ServiceType, PricingChargeType, ServiceStatus
from ..core.exceptions import MetadataParsingError
from ..models.service_info import ServiceInfo

logger = logging.getLogger(__name__)


class MetadataParser:
    """Parser for service metadata.json files."""
    
    @staticmethod
    def parse_metadata(metadata_path: Path) -> Dict[str, Any]:
        """Parse metadata.json file."""
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise MetadataParsingError(str(metadata_path), f"Invalid JSON: {e}")
        except Exception as e:
            raise MetadataParsingError(str(metadata_path), str(e))
    
    @staticmethod
    def validate_metadata(metadata: Dict[str, Any]) -> bool:
        """Validate required fields."""
        required = ["project_name", "author", "services"]
        
        for field in required:
            if field not in metadata:
                return False
        
        services = metadata.get("services", [])
        if not isinstance(services, list):
            return False
        
        for service in services:
            if not isinstance(service, dict) or "type" not in service:
                return False
        
        return True
    
    @staticmethod
    def extract_service_info_from_path(metadata_path: Path) -> Dict[str, str]:
        """Extract service information from metadata file path.
        
        Expected: datasites/{datasite}/public/routers/{service}/metadata.json
        """
        try:
            parts = metadata_path.parts
            
            if "datasites" not in parts:
                return {}
            
            idx = parts.index("datasites")
            
            if (len(parts) < idx + 6 or 
                parts[idx + 2] != "public" or 
                parts[idx + 3] != "routers" or 
                parts[idx + 5] != "metadata.json"):
                return {}
            
            datasite = parts[idx + 1]
            service_name = parts[idx + 4]
            
            if '@' not in datasite or not service_name:
                return {}
            
            return {
                "datasite": datasite,
                "service_name": service_name,
                "datasites_path": Path(*parts[:idx + 1])
            }
            
        except (ValueError, IndexError):
            return {}
    
    @classmethod
    def parse_services(cls, services_data: List[Dict]) -> List[ServiceItem]:
        """Parse services array from metadata."""
        services = []
        
        for service_data in services_data:
            try:
                service_type = ServiceType(service_data.get("type", "").lower())
                enabled = service_data.get("enabled", False)
                pricing = float(service_data.get("pricing", 0.0))
                
                charge_type_str = service_data.get("charge_type", "per_request").lower()
                try:
                    charge_type = PricingChargeType(charge_type_str)
                except ValueError:
                    charge_type = PricingChargeType.PER_REQUEST
                
                services.append(ServiceItem(
                    type=service_type,
                    enabled=enabled,
                    pricing=pricing,
                    charge_type=charge_type
                ))
                
            except (ValueError, TypeError):
                continue
        
        return services
    
    @classmethod
    def create_service_info(
        cls,
        metadata_path: Path,
        metadata: Dict[str, Any],
    ) -> ServiceInfo:
        """Create ServiceInfo from parsed metadata."""
        
        name = metadata.get("project_name", "")
        datasite = metadata.get("author", "")
        summary = metadata.get("summary", "")
        description = metadata.get("description", "")
        tags = metadata.get("tags", [])
        
        services = cls.parse_services(metadata.get("services", []))
        
        has_enabled = any(s.enabled for s in services)
        config_status = ServiceStatus.ACTIVE if has_enabled else ServiceStatus.DISABLED
        
        delegate_email = metadata.get("delegate_email")
        endpoints = metadata.get("documented_endpoints", {})
        
        # Parse publish date
        publish_date = None
        if "publish_date" in metadata:
            try:
                if isinstance(metadata["publish_date"], str):
                    publish_date = datetime.fromisoformat(
                        metadata["publish_date"].replace('Z', '+00:00')
                    )
            except (ValueError, TypeError):
                pass
        
        if publish_date is None and metadata_path.exists():
            try:
                publish_date = datetime.fromtimestamp(metadata_path.stat().st_mtime)
            except (OSError, ValueError):
                pass
        
        # Find RPC schema path
        rpc_schema_path = None
        service_info = cls.extract_service_info_from_path(metadata_path)
        
        if service_info:
            datasites_path = service_info["datasites_path"]
            datasite_email = service_info["datasite"]
            service_name = service_info["service_name"]
            
            # Path: datasites/{datasite}/app_data/{service}/rpc/rpc.schema.json
            potential_path = (
                datasites_path / datasite_email / "app_data" / 
                service_name / "rpc" / "rpc.schema.json"
            )
            
            if potential_path.exists():
                rpc_schema_path = potential_path
        
        return ServiceInfo(
            name=name,
            datasite=datasite,
            summary=summary,
            description=description,
            tags=tags,
            services=services,
            config_status=config_status,
            health_status=None,
            delegate_email=delegate_email,
            endpoints=endpoints,
            rpc_schema={},
            metadata_path=metadata_path,
            rpc_schema_path=rpc_schema_path,
            publish_date=publish_date
        )
    
    @classmethod
    def parse_service_from_files(cls, metadata_path: Path) -> ServiceInfo:
        """Parse a complete ServiceInfo from metadata file."""
        metadata = cls.parse_metadata(metadata_path)
        
        if not cls.validate_metadata(metadata):
            raise MetadataParsingError(
                str(metadata_path),
                "Missing required fields"
            )
        
        return cls.create_service_info(metadata_path, metadata)