"""
Cost estimation utility for SyftBox NSAI SDK services
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from ..core.types import ServiceType, PricingChargeType
from ..core.exceptions import ValidationError

if TYPE_CHECKING:
    from ..models.service_info import ServiceInfo

class CostEstimator:
    """Utility class for estimating service costs across different service types"""
    
    @staticmethod
    def estimate_chat_cost(service_info: 'ServiceInfo', message_count: int = 1) -> float:
        """Estimate cost for a chat request.
        
        Args:
            service_info: Service information containing pricing details
            message_count: Number of messages to estimate cost for
            
        Returns:
            Estimated cost for the chat request
        """
        chat_service_info = service_info.get_service_info(ServiceType.CHAT)
        if not chat_service_info:
            return 0.0
        
        if chat_service_info.charge_type == PricingChargeType.PER_REQUEST:
            return chat_service_info.pricing * message_count
        else:
            return chat_service_info.pricing
    
    @staticmethod
    def estimate_search_cost(service_info: 'ServiceInfo', query_count: int = 1, result_limit: int = 3) -> float:
        """Estimate cost for search requests.
        
        Args:
            service_info: Service information containing pricing details
            query_count: Number of queries to estimate cost for
            result_limit: Maximum number of results per query
            
        Returns:
            Estimated cost for the search request
        """
        search_service_info = service_info.get_service_info(ServiceType.SEARCH)
        if not search_service_info:
            return 0.0
        
        if search_service_info.charge_type == PricingChargeType.PER_REQUEST:
            return search_service_info.pricing * query_count
        else:
            return search_service_info.pricing
    
    @staticmethod
    def estimate_service_cost(service_info: 'ServiceInfo', service_type: ServiceType, 
                            message_count: int = 1, query_count: int = 1, 
                            result_limit: int = 3) -> float:
        """Generic cost estimation for any service type.
        
        Args:
            service_info: Service information containing pricing details
            service_type: Type of service (CHAT or SEARCH)
            message_count: Number of messages (for chat services)
            query_count: Number of queries (for search services)
            result_limit: Maximum results per query (for search services)
            
        Returns:
            Estimated cost for the service request
        """
        if service_type == ServiceType.CHAT:
            return CostEstimator.estimate_chat_cost(service_info, message_count)
        elif service_type == ServiceType.SEARCH:
            return CostEstimator.estimate_search_cost(service_info, query_count, result_limit)
        else:
            raise ValidationError(f"Unsupported service type for cost estimation: {service_type}")
    
    @staticmethod
    def estimate_pipeline_cost(data_sources: list, synthesizer_service: 'ServiceInfo', 
                             message_count: int = 1) -> float:
        """Estimate total cost for a pipeline execution.
        
        Args:
            data_sources: List of (service_info, params) tuples for search services
            synthesizer_service: ServiceInfo for the chat synthesizer
            message_count: Number of messages for synthesis
            
        Returns:
            Total estimated cost for the pipeline
        """
        total_cost = 0.0
        
        # Estimate search costs for each data source
        for service_info, params in data_sources:
            topK = params.get('topK', 3)
            cost = CostEstimator.estimate_search_cost(service_info, query_count=1, result_limit=topK)
            total_cost += cost
        
        # Estimate synthesis cost
        cost = CostEstimator.estimate_chat_cost(synthesizer_service, message_count=message_count)
        total_cost += cost
        
        return total_cost