"""
Health check utilities for SyftBox services
"""
import asyncio
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

from ..core.types import HealthStatus
from ..core.exceptions import HealthCheckError, NetworkError, RPCError
from ..clients.rpc_client import SyftBoxRPCClient
from ..models.service_info import ServiceInfo

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Continuous health monitoring for services."""
    
    def __init__(self, rpc_client: SyftBoxRPCClient, check_interval: float = 30.0):
        """Initialize health monitor.
        
        Args:
            rpc_client: RPC client for health checks
            check_interval: Seconds between health checks
        """
        self.rpc_client = rpc_client
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
            self.rpc_client,
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
        rpc_client: SyftBoxRPCClient,
        timeout: float = 15.0,
        show_spinner: bool = True,
        max_poll_attempts: int = 20,
        poll_interval: float = 0.25
    ) -> HealthStatus:
    """Check health of a single service.
    
    Args:
        service_info: Service to check
        rpc_client: RPC client for making calls
        timeout: Timeout in seconds for health check
        
    Returns:
        Health status of the service
    """
    try:
        # Use syft-rpc directly to check initial response without polling
        from syft_rpc.rpc import make_url, send
        from syft_rpc.protocol import SyftStatus
        
        url = make_url(
            datasite=service_info.datasite,
            app_name=service_info.name,
            endpoint="health"
        )
        
        logger.debug(f"🔍 Checking health for {service_info.datasite}/{service_info.name} at URL: {url}")
        
        # Send health check request
        future = send(
            url=url,
            method="GET",
            body=None,
            client=rpc_client.syft_client,
            encrypt=False,
            cache=False
        )
        
        # For health checks, just wait for initial response (200 or 202 means service is alive)
        # Run the blocking wait() call in an executor to avoid blocking the event loop
        import concurrent.futures
        loop = asyncio.get_event_loop()
        
        try:
            # Run blocking wait() in thread pool executor for true parallelism
            with concurrent.futures.ThreadPoolExecutor() as executor:
                response = await loop.run_in_executor(
                    executor,
                    lambda: future.wait(timeout=timeout, poll_interval=poll_interval)
                )
            
            # If we got any response from the service (200, 202, or even 400), it means it's online
            # 400 = Bad Request, which means service is responding, just didn't like our request format
            if response.status_code in [SyftStatus.OK, SyftStatus.ACCEPTED, 400]:
                if response.status_code == 400:
                    logger.info(f"✅ Service {service_info.datasite}/{service_info.name} responded with {response.status_code} (Bad Request but service is alive) - marking ONLINE")
                else:
                    logger.info(f"✅ Service {service_info.datasite}/{service_info.name} responded with {response.status_code} - marking ONLINE")
                return HealthStatus.ONLINE
            else:
                # Other error codes (500, 503, etc.) indicate service problems
                logger.warning(f"❌ Service {service_info.datasite}/{service_info.name} responded with status {response.status_code} - marking OFFLINE")
                return HealthStatus.OFFLINE
                
        except Exception as wait_error:
            # If waiting fails, check if we got an initial response before timeout
            error_str = str(wait_error).lower()
            if "timeout" in error_str or "timed out" in error_str:
                logger.warning(f"⏱️  Service {service_info.name} timed out after {timeout}s - marking OFFLINE")
                return HealthStatus.OFFLINE
            # Log the actual error before re-raising
            logger.warning(f"❌ Service {service_info.name} wait error: {type(wait_error).__name__}: {wait_error}")
            raise  # Re-raise to be caught by outer exception handlers
        
        # Parse health response - try multiple formats (only reached if we got 200)
        response_data = response.json()
        if isinstance(response_data, dict):
            # We already know service is online if we reach here (got 200)
            # Just validate the response has some content
            logger.debug(f"Service {service_info.name} returned valid response - confirmed ONLINE")
            return HealthStatus.ONLINE
    
    except asyncio.TimeoutError:
        # Timeout means service didn't respond in time (no 200/202 received or polling timed out)
        logger.warning(f"⏱️  Service {service_info.name} asyncio timeout - marking OFFLINE")
        return HealthStatus.OFFLINE
    except (NetworkError, RPCError) as e:
        error_msg = str(e).lower()
        
        # Network/connection errors mean service is offline
        if any(keyword in error_msg for keyword in [
            "connection refused", "connection reset", "connection error",
            "network", "unreachable", "timed out", "timeout",
            "permission denied", "not found", "404", "503"
        ]):
            logger.warning(f"❌ Service {service_info.name}: {type(e).__name__}: {e} - marking OFFLINE")
            return HealthStatus.OFFLINE
        else:
            # Other RPC errors might be temporary issues - mark as UNKNOWN
            logger.warning(f"❓ Service {service_info.name} error ({type(e).__name__}: {e}) - marking UNKNOWN")
            return HealthStatus.UNKNOWN
    except Exception as e:
        # Unexpected errors (like import errors) - mark as UNKNOWN
        logger.warning(f"❓ Unexpected error in health check for {service_info.name}: {type(e).__name__}: {e}")
        return HealthStatus.UNKNOWN
    
async def batch_health_check(
        services: List[ServiceInfo],
        rpc_client: SyftBoxRPCClient,
        timeout: float = 15.0,
        max_concurrent: int = 10
    ) -> Dict[str, HealthStatus]:
    """Check health of multiple services concurrently.
    
    Args:
        services: List of services to check
        rpc_client: RPC client for making calls
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
            health = await check_service_health(service, rpc_client, timeout)
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
        Formatted status string with emoji
    """
    status_icons = {
        HealthStatus.ONLINE: "✅",
        HealthStatus.OFFLINE: "❌",
        HealthStatus.TIMEOUT: "⏱️",
        HealthStatus.UNKNOWN: "❓",
        HealthStatus.NOT_APPLICABLE: "➖"
    }
    
    icon = status_icons.get(status, "❓")
    return f"{status.value.title()} {icon}"

async def get_service_response_time(service_info: ServiceInfo, 
                                 rpc_client: SyftBoxRPCClient) -> Optional[float]:
    """Measure response time for a service's health endpoint.
    
    Args:
        service_info: Service to test
        rpc_client: RPC client for making calls
        
    Returns:
        Response time in seconds, or None if failed
    """
    try:
        start_time = time.time()
        await check_service_health(service_info, rpc_client, timeout=10.0)
        end_time = time.time()
        return end_time - start_time
    except Exception:
        return None