"""
Decorators for SyftBox SDK
"""
import asyncio
import functools
import logging

from typing import Callable, Any

from syft_core import Client as SyftClient
from .exceptions import AuthenticationError, SyftBoxNotRunningError
from ..utils.async_utils import detect_async_context, run_async_in_thread

logger = logging.getLogger(__name__)
# Configuration for robust polling
MAX_WAIT_SECONDS = 10
POLL_INTERVAL_SECONDS = 0.5

def ensure_syftbox_running(func):
    """
    Decorator to check if the local SyftBox is running before executing
    an asynchronous service client method. Attempts automatic restart if 'syft-installer' 
    is available (i.e., installed via the [installer] extra).
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if not args:
            raise TypeError(f"'{func.__name__}' must be called as a method.")
            
        service_instance = args[0]
        syft_client = service_instance.syft_client

        # If the datasite is already available, proceed
        if syft_client.my_datasite.exists():
            return await func(*args, **kwargs) 
        
        try:
            # Attempting this import implements the "Optional Dependency" principle.
            import syft_installer as si
            
            logger.warning("SyftBox daemon is stopped. Attempting automatic restart via syft-installer.")

            # Use the public API method to start SyftBox if it's currently stopped.
            # This is non-blocking and attempts to start the daemon in the background.
            started_daemon = si.run_if_stopped() 

            if started_daemon:
                logger.info("SyftBox restart triggered. Polling for successful startup...")
                
                # Robust Polling Loop: Replaces fixed 'sleep(2)' with a timeout
                poll_attempts = int(MAX_WAIT_SECONDS / POLL_INTERVAL_SECONDS)
                
                for i in range(poll_attempts):
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    
                    if syft_client.my_datasite.exists():
                        logger.info("SyftBox successfully restarted. Retrying RPC request.")
                        return await func(*args, **kwargs)
                        
                # If the loop finishes without success
                raise SyftBoxNotRunningError(
                    f"Automatic restart failed after polling for {MAX_WAIT_SECONDS}s. Daemon is installed but won't start. Check installation and logs."
                )

            # Case: Installer is present, but run_if_stopped() returned False.
            elif not si.is_installed():
                # Provide a specific error if the installer package is installed but SyftBox isn't.
                raise SyftBoxNotRunningError(
                    "SyftBox is not installed. Daemon cannot be started. Run `import syft_installer as si; si.run()` to complete setup."
                )
            
            # Catch other unexpected errors from the installer itself
            else:
                 raise SyftBoxNotRunningError("SyftBox automatic restart failed due to an unknown installer error.")

        except ImportError:
            # Installer Not Present (Fail Gracefully) ---
            # This handles the "Default User" profile, providing clear instructions.
            manual_instructions = (
                "Local SyftBox is not running. The 'syft-installer' installer package is not installed. "
                "To enable automatic restart, install the extra dependency: "
                "pip install syft-hub-sdk[installer]"
            )
            raise SyftBoxNotRunningError(manual_instructions)

        except Exception as e:
            # Catch any other runtime error (e.g., permissions, bad configuration)
            raise SyftBoxNotRunningError(
                f"Automatic restart attempt failed with a runtime error: {type(e).__name__}: {e}. "
                "You may need to manually run `import syft_installer as si; si.status()` for diagnostics."
            )

    return wrapper

def require_account(func: Callable) -> Callable:
    """Decorator that requires account setup before service operations.
    
    Args:
        func: The function to decorate
        
    Returns:
        Wrapped function that checks account status
    """
    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs) -> Any:
        if not getattr(self, '_account_configured', False):
            raise AuthenticationError(
                "Account setup required before using services. "
                "Please run: await client.setup_accounting(email, password)"
            )
        return await func(self, *args, **kwargs)
    
    @functools.wraps(func)
    def sync_wrapper(self, *args, **kwargs) -> Any:
        if not getattr(self, '_account_configured', False):
            raise AuthenticationError(
                "Account setup required before using services. "
                "Please run: await client.setup_accounting(email, password)"
            )
        return func(self, *args, **kwargs)
    
    # Return appropriate wrapper based on whether function is async
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
    
def make_sync_wrapper(async_method):
    """
    Decorator factory to create thread-safe synchronous wrappers for async methods.
    
    Args:
        async_method: The async method to wrap
        
    Returns:
        A synchronous wrapper function
        
    Example:
        @make_sync_wrapper
        async def some_async_method(self, arg1, arg2):
            return await some_operation(arg1, arg2)
            
        # Creates: some_async_method_sync() that can be called synchronously
    """
    def sync_wrapper(self, *args, **kwargs):
        return run_async_in_thread(async_method(self, *args, **kwargs))
    
    # Preserve metadata
    sync_wrapper.__name__ = f"{async_method.__name__}_sync"
    sync_wrapper.__doc__ = f"Synchronous wrapper for {async_method.__name__}.\n\n{async_method.__doc__ or ''}"
    
    return sync_wrapper

def smart_async_wrapper(async_method):
    """
    Decorator that creates a "smart" method that adapts to the execution context.
    
    In async contexts: returns the awaitable coroutine
    In sync contexts: executes synchronously and returns the result
    
    Args:
        async_method: The async method to wrap
        
    Returns:
        A smart wrapper that adapts to the execution context
    """
    def smart_wrapper(self, *args, **kwargs):
        if detect_async_context():
            # Return coroutine - caller must await it
            return async_method(self, *args, **kwargs)
        else:
            # Execute synchronously using thread pool
            return run_async_in_thread(async_method(self, *args, **kwargs))
    
    # Preserve metadata
    smart_wrapper.__name__ = async_method.__name__.replace('_async', '')
    smart_wrapper.__doc__ = f"""Smart wrapper for {async_method.__name__} that adapts to execution context.
    
    In async contexts: returns awaitable coroutine
    In sync contexts: returns the actual result
    
    {async_method.__doc__ or ''}
    """
    
    return smart_wrapper