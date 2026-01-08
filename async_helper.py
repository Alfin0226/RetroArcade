"""
Async helper module for running async code from sync pygame main loop.
Provides a dedicated event loop in a separate thread for database operations.
"""
from __future__ import annotations
import asyncio
import threading
from typing import Any, Coroutine

# Global event loop for all async database operations
_async_loop: asyncio.AbstractEventLoop | None = None
_async_thread: threading.Thread | None = None


def start_async_loop() -> None:
    """Start a dedicated event loop in a separate thread."""
    global _async_loop, _async_thread
    if _async_loop is not None:
        return
    
    def run_loop():
        global _async_loop
        _async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_async_loop)
        _async_loop.run_forever()
    
    _async_thread = threading.Thread(target=run_loop, daemon=True)
    _async_thread.start()
    # Wait for loop to be ready
    import time
    while _async_loop is None:
        time.sleep(0.01)


def run_async(coro: Coroutine) -> Any:
    """Run an async coroutine from sync code using the dedicated async event loop."""
    global _async_loop
    if _async_loop is None:
        start_async_loop()
    
    future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
    return future.result(timeout=30)  # 30 second timeout


def stop_async_loop() -> None:
    """Stop the async event loop."""
    global _async_loop
    if _async_loop is not None:
        _async_loop.call_soon_threadsafe(_async_loop.stop)
