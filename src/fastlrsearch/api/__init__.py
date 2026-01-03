"""HTTP API for Lightroom Classic integration.

Public API:
- start_server: Start API server in daemon thread
- stop_server: Stop API server
- is_running: Check if server is running
"""

from fastlrsearch.api.server import (
    get_session_token,
    is_running,
    start_server,
    stop_server,
)

__all__ = [
    "start_server",
    "stop_server",
    "is_running",
    "get_session_token",
]
