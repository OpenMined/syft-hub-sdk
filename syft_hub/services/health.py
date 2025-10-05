"""
Health check utilities for SyftBox services
"""
import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

from syft_core import Client as SyftClient
from syft_rpc.rpc import send, make_url
from syft_rpc.protocol import SyftTimeoutError, SyftStatus

from ..core.types import HealthStatus
from ..models.service_info import ServiceInfo

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Continuous health monitoring for services."""
    
    def __init__(
            self, 
            syft_client: SyftClient,
            check_interval: float = 30.0
        ):
        """Initialize health monitor.
        
        Args:
            syft_client: Syft client for health checks
            check_interval: Seconds between health checks
        """
        self.syft_client = syft_client
        self.check_interval = check_interval
        self.monitored_services: List[ServiceInfo] = []
        self.health_status: Dict[str, HealthStatus] = {}
        self.last_check_time: Optional[float] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        self._callbacks: List[callable] = []
    
    def add_service(self, service_info: ServiceInfo):
        """Add a service to monitoring.
        
        Args:
            service_info: Service to monitor
        """
        if service_info not in self.monitored_services:
            self.monitored_services.append(service_info)
            logger.info(f"Added {service_info.name} to health monitoring")
    
    def remove_service(self, service_name: str):
        """Remove a service from monitoring.
        
        Args:
            service_name: Name of service to remove
        """
        self.monitored_services = [
            service for service in self.monitored_services 
            if service.name != service_name
        ]
        
        if service_name in self.health_status:
            del self.health_status[service_name]
        
        logger.info(f"Removed {service_name} from health monitoring")
    
    def add_callback(self, callback: callable):
        """Add callback for health status changes.
        
        Args:
            callback: Function to call when health status changes
                     Signature: callback(service_name: str, old_status: HealthStatus, new_status: HealthStatus)
        """
        self._callbacks.append(callback)
    
    async def check_all_services(self) -> Dict[str, HealthStatus]:
        """Check health of all monitored services.
        
        Returns:
            Current health status of all services
        """
        if not self.monitored_services:
            return {}
        
        new_status = await batch_health_check(
            self.monitored_services,
            self.syft_client,
            timeout=15.0
        )
        
        # Check for status changes and trigger callbacks
        for service_name, new_health in new_status.items():
            old_health = self.health_status.get(service_name)
            
            if old_health != new_health:
                logger.info(f"Health status changed for {service_name}: {old_health} -> {new_health}")
                
                # Trigger callbacks
                for callback in self._callbacks:
                    try:
                        callback(service_name, old_health, new_health)
                    except Exception as e:
                        logger.error(f"Health callback error: {e}")
        
        # Update stored status
        self.health_status.update(new_status)
        self.last_check_time = time.time()
        
        return self.health_status
    
    def get_service_health(self, service_name: str) -> Optional[HealthStatus]:
        """Get current health status of a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Current health status, or None if not monitored
        """
        return self.health_status.get(service_name)
    
    def get_healthy_services(self) -> List[str]:
        """Get list of currently healthy service names.
        
        Returns:
            List of service names that are online
        """
        return [
            service_name for service_name, status in self.health_status.items()
            if status == HealthStatus.ONLINE
        ]
    
    def get_unhealthy_services(self) -> List[str]:
        """Get list of currently unhealthy service names.
        
        Returns:
            List of service names that are offline or having issues
        """
        return [
            service_name for service_name, status in self.health_status.items()
            if status in [HealthStatus.OFFLINE, HealthStatus.TIMEOUT, HealthStatus.UNKNOWN]
        ]
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get summary of health status.
        
        Returns:
            Dictionary with health statistics
        """
        if not self.health_status:
            return {
                "total_services": 0,
                "healthy": 0,
                "unhealthy": 0,
                "unknown": 0,
                "last_check": None
            }
        
        status_counts = {}
        for status in self.health_status.values():
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_services": len(self.health_status),
            "healthy": status_counts.get(HealthStatus.ONLINE, 0),
            "unhealthy": (
                status_counts.get(HealthStatus.OFFLINE, 0) +
                status_counts.get(HealthStatus.TIMEOUT, 0)
            ),
            "unknown": status_counts.get(HealthStatus.UNKNOWN, 0),
            "last_check": self.last_check_time,
            "status_breakdown": {
                status.value: count for status, count in status_counts.items()
            }
        }
    
    async def start_monitoring(self):
        """Start continuous health monitoring."""
        if self._monitoring_task is not None:
            logger.warning("Health monitoring already running")
            return
        
        logger.info(f"Starting health monitoring with {self.check_interval}s interval")
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
    
    async def stop_monitoring(self):
        """Stop continuous health monitoring."""
        if self._monitoring_task is None:
            return
        
        logger.info("Stopping health monitoring")
        self._monitoring_task.cancel()
        
        try:
            await self._monitoring_task
        except asyncio.CancelledError:
            pass
        
        self._monitoring_task = None
    
    async def _monitoring_loop(self):
        """Internal monitoring loop."""
        try:
            while True:
                try:
                    await self.check_all_services()
                except Exception as e:
                    logger.error(f"Error in health monitoring loop: {e}")
                
                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            logger.info("Health monitoring cancelled")
            raise


async def check_service_health(
    service_info: ServiceInfo, 
    syft_client: SyftClient, 
    timeout: float = 15.0, 
    show_spinner: bool = False,
    poll_interval: float = 0.25
) -> HealthStatus:
    """Check health of a single service.
    
    Args:
        service_info: Service to check
        syft_client: Syft client for making requests
        timeout: Timeout for health check
        show_spinner: Whether to show spinner (unused with syft-rpc)
        
    Returns:
        Health status of the service
    """
    try:
        # Build health check URL
        syft_url = make_url(
            datasite=service_info.datasite,
            app_name=service_info.name,
            endpoint="health"
        )
        
        # Send health check request
        future = send(
            url=syft_url,
            method="GET",
            client=syft_client,
            cache=False
        )
        
        # Wait for response (syft-rpc handles polling internally for 202 responses)
        # Use asyncio.to_thread to avoid blocking the event loop
        response = await asyncio.to_thread(
            future.wait, 
            timeout=timeout, 
            poll_interval=poll_interval
        )
        
        # Get status code
        status_code = response.status_code
        
        # Process the response body to properly complete the RPC cycle
        try:
            # Try to read the response body (use asyncio.to_thread to avoid blocking)
            body = await asyncio.to_thread(response.json)
            logger.debug(f"Service {service_info.name} health response: status={status_code}, body={body}")
        except Exception as e:
            # If JSON parsing fails, try text
            try:
                body = await asyncio.to_thread(response.text)
                logger.debug(f"Service {service_info.name} health response: status={status_code}, text={body}")
            except Exception as text_error:
                logger.debug(f"Could not read response body for {service_info.name}: {e}")
                body = None
        
        # Interpret response status codes:
        # - 2xx (success including 202) = service is healthy and responding correctly
        # - 401, 403 (auth errors) = service is alive but authentication issue, mark as online
        # - 404 (not found) = health endpoint doesn't exist, service not functional, mark as offline
        # - Other 4xx = service has client-side issues, mark as offline
        # - 5xx (server error) = service has internal problems, mark as offline
        if response.is_success:
            # 2xx: Service is healthy
            logger.info(f"Service {service_info.name} responded with {status_code} - marking ONLINE")
            return HealthStatus.ONLINE
        elif status_code in [401, 403]:
            # Authentication/authorization errors - service is running but needs auth
            logger.info(f"Service {service_info.name} responded with {status_code} (auth error but service is alive) - marking ONLINE")
            return HealthStatus.ONLINE
        else:
            # 404, other 4xx, 5xx or other error codes indicate service problems
            if status_code == 404:
                logger.warning(f"Service {service_info.name} returned {status_code} (health endpoint not found) - marking OFFLINE")
            elif 400 <= status_code < 500:
                logger.warning(f"Service {service_info.name} returned {status_code} (client error) - marking OFFLINE")
            else:
                logger.warning(f"Service {service_info.name} returned {status_code} (server error) - marking OFFLINE")
            return HealthStatus.OFFLINE
    
    except SyftTimeoutError:
        logger.warning(f"Service {service_info.name} timeout - marking OFFLINE")
        return HealthStatus.OFFLINE
    
    except Exception as e:
        error_msg = str(e).lower()
        
        # Network/connection errors mean service is offline
        if any(keyword in error_msg for keyword in [
            "connection refused", "connection reset", "connection error",
            "network", "unreachable", "timed out", "timeout",
            "permission denied", "not found", "404", "503", "forbidden"
        ]):
            logger.warning(f"Service {service_info.name}: {type(e).__name__}: {e} - marking OFFLINE")
            return HealthStatus.OFFLINE
        else:
            # Other errors might be temporary - mark as UNKNOWN
            logger.warning(f"Service {service_info.name} error ({type(e).__name__}: {e}) - marking UNKNOWN")
            return HealthStatus.UNKNOWN


async def batch_health_check(
    services: List[ServiceInfo],
    syft_client: SyftClient,
    timeout: float = 15.0,
    max_concurrent: int = 30
) -> Dict[str, HealthStatus]:
    """Check health of multiple services concurrently.
    
    Args:
        services: List of services to check
        syft_client: Syft client for making calls
        timeout: Timeout per health check
        max_concurrent: Maximum concurrent health checks
        
    Returns:
        Dictionary mapping service names to health status
    """
    if not services:
        return {}
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def check_single_service(service: ServiceInfo) -> Tuple[str, HealthStatus]:
        async with semaphore:
            logger.debug(f"Starting health check for {service.name}")
            health = await check_service_health(service, syft_client, timeout, show_spinner=False)
            logger.debug(f"Completed health check for {service.name}: {health}")
            return service.name, health
    
    # Start all health checks concurrently
    tasks = [check_single_service(service) for service in services]
    
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = time.time()
    
    logger.info(f"Batch health check completed in {end_time - start_time:.2f}s for {len(services)} services")
    
    # Process results
    health_status = {}
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Health check task failed: {result}")
            continue
        
        service_name, status = result
        health_status[service_name] = status
    
    return health_status


def format_health_status(status: HealthStatus) -> str:
    """Format health status for display.
    
    Args:
        status: Health status to format
        
    Returns:
        Formatted status string
    """
    status_text = {
        HealthStatus.ONLINE: "Online",
        HealthStatus.OFFLINE: "Offline",
        HealthStatus.TIMEOUT: "Timeout",
        HealthStatus.UNKNOWN: "Unknown",
        HealthStatus.NOT_APPLICABLE: "N/A"
    }
    
    return status_text.get(status, "Unknown")


async def get_service_response_time(
    service_info: ServiceInfo, 
    syft_client: SyftClient
) -> Optional[float]:
    """Measure response time for a service's health endpoint.
    
    Args:
        service_info: Service to test
        syft_client: Syft client for making calls
        
    Returns:
        Response time in seconds, or None if failed
    """
    try:
        start_time = time.time()
        await check_service_health(service_info, syft_client, timeout=10.0)
        end_time = time.time()
        return end_time - start_time
    except Exception:
        return None