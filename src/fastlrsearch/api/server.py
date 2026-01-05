"""FastAPI server for Lightroom Classic integration.

Runs as an embedded daemon thread while the desktop app is active.
Loopback-only binding for security.
"""

import json
import os
import secrets
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware

from fastlrsearch.config import settings

# Server state
_server_thread: threading.Thread | None = None
_server_instance: uvicorn.Server | None = None
_session_token: str | None = None


def create_app() -> FastAPI:
    """Create FastAPI application."""
    from fastlrsearch.api.routes import router

    app = FastAPI(
        title="FastLRSearch API",
        description="Local API for Lightroom Classic integration",
        version="0.1.0",
    )

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Token validation middleware
    @app.middleware("http")
    async def validate_token(request: Request, call_next):
        # Skip token check for health endpoint
        if request.url.path == "/health":
            return await call_next(request)

        token = request.headers.get("X-App-Token")
        if token != _session_token:
            raise HTTPException(status_code=401, detail="Invalid or missing token")

        return await call_next(request)

    app.include_router(router)

    return app


def write_discovery_file(port: int, token: str):
    """Write API discovery file for Lightroom plugin.

    Args:
        port: Server port
        token: Session token
    """
    discovery_path = settings.api_discovery_path
    discovery_path.parent.mkdir(parents=True, exist_ok=True)

    discovery_data = {
        "port": port,
        "token": token,
        "pid": os.getpid(),
    }

    with open(discovery_path, "w") as f:
        json.dump(discovery_data, f, indent=2)

    print(f"Discovery file written to {discovery_path}")


def remove_discovery_file():
    """Remove API discovery file on shutdown."""
    discovery_path = settings.api_discovery_path
    if discovery_path.exists():
        discovery_path.unlink()


def _load_or_create_token() -> str:
    """Load existing token from discovery file or create a new one.

    Token persists across restarts for better UX with Lightroom plugin.
    """
    discovery_path = settings.api_discovery_path

    # Try to load existing token
    if discovery_path.exists():
        try:
            with open(discovery_path) as f:
                data = json.load(f)
                if "token" in data and data["token"]:
                    return data["token"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Generate new token if none exists
    return secrets.token_urlsafe(32)


def start_server(
    host: str | None = None,
    port: int | None = None,
) -> str:
    """Start the API server in a daemon thread.

    Args:
        host: Bind address (defaults to settings.api_host)
        port: Bind port (defaults to settings.api_port)

    Returns:
        Session token for authentication
    """
    global _server_thread, _server_instance, _session_token

    if _server_thread is not None and _server_thread.is_alive():
        assert _session_token is not None
        return _session_token

    host = host or settings.api_host
    port = port or settings.api_port

    # Load existing token or generate new one (persists across restarts)
    _session_token = _load_or_create_token()

    # Write discovery file
    write_discovery_file(port, _session_token)

    # Create app
    app = create_app()

    # Configure uvicorn
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    _server_instance = server

    # Start in daemon thread
    def run_server():
        server.run()

    _server_thread = threading.Thread(target=run_server, daemon=True)
    _server_thread.start()

    print(f"API server started at http://{host}:{port}")
    return _session_token


def stop_server():
    """Stop the API server."""
    global _server_thread, _server_instance, _session_token

    if _server_instance is not None:
        _server_instance.should_exit = True

    # Don't remove discovery file - keep token for next startup

    _server_thread = None
    _server_instance = None
    _session_token = None

    print("API server stopped")


def is_running() -> bool:
    """Check if server is running."""
    return _server_thread is not None and _server_thread.is_alive()


def get_session_token() -> str | None:
    """Get current session token."""
    return _session_token
