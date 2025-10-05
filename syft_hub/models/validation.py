"""
Pydantic validation models for API requests and responses
"""
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import List, Optional, Dict, Any

from ..core.types import ServiceType, HealthStatus


class ChatMessageModel(BaseModel):
    """Pydantic model for chat messages."""
    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., min_length=1, max_length=50000, description="Message content")
    name: Optional[str] = Field(None, description="Optional author name")
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v not in ['user', 'assistant', 'system']:
            raise ValueError('Role must be user, assistant, or system')
        return v


class GenerationOptionsModel(BaseModel):
    """Pydantic model for generation options."""
    max_tokens: Optional[int] = Field(None, ge=1, le=100000, description="Maximum tokens to generate")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    stop_sequences: Optional[List[str]] = Field(None, description="Stop sequences for generation")
    
    class Config:
        extra = "allow"


class ChatRequestModel(BaseModel):
    """Pydantic model for chat requests."""
    user_email: EmailStr = Field(..., description="User email address")
    model: str = Field(..., min_length=1, max_length=100, description="Model name or identifier")
    messages: List[ChatMessageModel] = Field(..., min_length=1, description="Conversation messages")
    options: Optional[GenerationOptionsModel] = Field(None, description="Generation options")
    transaction_token: Optional[str] = Field(None, description="Payment token for paid services")
    request_id: Optional[str] = Field(None, description="Unique request identifier")


class SearchOptionsModel(BaseModel):
    """Pydantic model for search options."""
    limit: Optional[int] = Field(3, ge=1, le=100, description="Maximum results to return")
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum similarity score")
    include_metadata: Optional[bool] = Field(None, description="Include document metadata")
    include_embeddings: Optional[bool] = Field(None, description="Include vector embeddings")


class SearchRequestModel(BaseModel):
    """Pydantic model for search requests."""
    user_email: EmailStr = Field(..., description="User email address")
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    options: Optional[SearchOptionsModel] = Field(None, description="Search options")
    transaction_token: Optional[str] = Field(None, description="Payment token for paid services")
    request_id: Optional[str] = Field(None, description="Unique request identifier")


class HealthCheckRequestModel(BaseModel):
    """Pydantic model for health check requests."""
    user_email: EmailStr = Field(..., description="User email address")
    include_details: Optional[bool] = Field(False, description="Include detailed health information")
    timeout: Optional[float] = Field(5.0, ge=0.1, le=30.0, description="Request timeout in seconds")
    request_id: Optional[str] = Field(None, description="Unique request identifier")


# Response Models

class ChatUsageModel(BaseModel):
    """Token usage information."""
    prompt_tokens: int = Field(..., ge=0, description="Tokens in the prompt")
    completion_tokens: int = Field(..., ge=0, description="Tokens in the completion")
    total_tokens: int = Field(..., ge=0, description="Total tokens used")


class ChatResponseModel(BaseModel):
    """Pydantic model for chat responses."""
    id: str = Field(..., description="Unique response ID")
    model: str = Field(..., description="Service that generated the response")
    message: ChatMessageModel = Field(..., description="Generated message")
    finish_reason: Optional[str] = Field(None, description="Why generation stopped")
    usage: ChatUsageModel = Field(..., description="Token usage information")
    cost: Optional[float] = Field(None, ge=0, description="Cost of the request")
    provider_info: Optional[Dict[str, Any]] = Field(None, description="Provider-specific information")


class DocumentResultModel(BaseModel):
    """Document search result."""
    id: str = Field(..., description="Document identifier")
    score: float = Field(..., ge=0, le=1, description="Similarity score")
    content: str = Field(..., description="Document content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Document metadata")
    embedding: Optional[List[float]] = Field(None, description="Document embedding vector")


class SearchResponseModel(BaseModel):
    """Pydantic model for search responses."""
    id: str = Field(..., description="Unique response ID")
    query: str = Field(..., description="Original search query")
    results: List[DocumentResultModel] = Field(..., description="Search results")
    cost: Optional[float] = Field(None, ge=0, description="Cost of the request")
    provider_info: Optional[Dict[str, Any]] = Field(None, description="Provider-specific information")


class HealthResponseModel(BaseModel):
    """Pydantic model for health check responses."""
    id: str = Field(..., description="Unique response ID")
    project_name: str = Field(..., description="Name of the project/service")
    status: str = Field(..., description="Overall health status")
    services: Dict[str, Any] = Field(..., description="Status of individual services")
    uptime: Optional[float] = Field(None, description="Service uptime in seconds")
    version: Optional[str] = Field(None, description="Service version")


# Filter Models

class ServiceFilterModel(BaseModel):
    """Pydantic model for service filter criteria."""
    datasite: Optional[EmailStr] = Field(None, description="Filter by datasite email")
    tags: Optional[List[str]] = Field(None, max_length=20, description="Filter by tags")
    max_cost: Optional[float] = Field(None, ge=0, le=1000, description="Maximum cost filter")
    min_cost: Optional[float] = Field(None, ge=0, le=1000, description="Minimum cost filter")
    service_types: Optional[List[ServiceType]] = Field(None, description="Filter by service types")
    health_status: Optional[HealthStatus] = Field(None, description="Filter by health status")
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        if v is not None:
            # Validate each tag
            for tag in v:
                if not tag.strip() or len(tag) > 50:
                    raise ValueError('Invalid tag format')
        return v


class UserAccountModel(BaseModel):
    """User account information."""
    email: EmailStr = Field(..., description="User email address")
    balance: float = Field(ge=0.0, default=0.0, description="Account balance")
    password: str = Field(..., min_length=8, description="User password")
    organization: Optional[str] = Field(None, max_length=200, description="User organization")