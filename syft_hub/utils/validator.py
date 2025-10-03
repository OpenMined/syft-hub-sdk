"""
Shared validation utilities for SyftBox components
"""
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlparse

from syft_core.url import SyftBoxURL

# Simple patterns - no need for constants file
EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'


class ValidationError(Exception):
    """Validation error exception."""
    pass


class EmailValidator:
    """Email validation utilities."""
    
    @staticmethod
    def is_valid_email(email: str) -> bool:
        """Validate email format."""
        return validate_email(email)
    
    @staticmethod
    def validate_email(email: str, field_name: str = "email") -> str:
        """Validate email and raise error if invalid."""
        if not email:
            raise ValidationError(f"{field_name} is required")
            
        cleaned_email = email.strip()
        
        if not validate_email(cleaned_email):
            raise ValidationError(f"Invalid {field_name} format: {email}")
            
        return cleaned_email


class URLValidator:
    """URL validation utilities."""
    
    @staticmethod
    def is_valid_http_url(url: str) -> bool:
        """Validate HTTP/HTTPS URL format."""
        return validate_http_url(url)
    
    @staticmethod
    def is_valid_syft_url(syft_url: str) -> bool:
        """Validate syft:// URL format."""
        return validate_syft_url(syft_url)
    
    @staticmethod
    def normalize_server_url(url: str) -> str:
        """Normalize server URL format."""
        if not url:
            raise ValidationError("Server URL is required")
        
        normalized = url.strip().rstrip('/')
        
        if not normalized.startswith(('http://', 'https://')):
            normalized = 'https://' + normalized
        
        if not URLValidator.is_valid_http_url(normalized):
            raise ValidationError(f"Invalid server URL format: {url}")
        
        return normalized


class PathValidator:
    """Path validation utilities."""
    
    @staticmethod
    def validate_directory_exists(path: Path, description: str) -> None:
        """Validate that a directory exists."""
        if not path.exists():
            raise ValidationError(f"{description} directory does not exist: {path}")
        
        if not path.is_dir():
            raise ValidationError(f"{description} path is not a directory: {path}")
    
    @staticmethod
    def validate_file_exists(path: Path, description: str) -> None:
        """Validate that a file exists."""
        if not path.exists():
            raise ValidationError(f"{description} file does not exist: {path}")
        
        if not path.is_file():
            raise ValidationError(f"{description} path is not a file: {path}")


def validate_email(email: str) -> bool:
    """Validate email address format."""
    if not email or not isinstance(email, str):
        return False
    
    email = email.strip()
    
    if not re.match(EMAIL_PATTERN, email):
        return False
        
    if len(email) > 254:  # RFC 5321 limit
        return False
        
    try:
        local, domain = email.rsplit('@', 1)
        if len(local) > 64:
            return False
    except ValueError:
        return False
        
    return True


def validate_syft_url(url: str) -> bool:
    """Validate syft:// URL format."""
    try:
        SyftBoxURL(url)
        return True
    except:
        return False


def validate_http_url(url: str) -> bool:
    """Validate HTTP/HTTPS URL format."""
    if not url or not isinstance(url, str):
        return False
    
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and parsed.netloc
    except Exception:
        return False


def validate_service_name(name: str) -> bool:
    """Validate service name format."""
    if not name or not isinstance(name, str):
        return False
    
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, name)) and 1 <= len(name) <= 100