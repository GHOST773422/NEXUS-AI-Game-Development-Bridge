"""NEXUS REST Router Entry Point (Delegates to core.nexus_core.rest_gateway)."""

from core.nexus_core.rest_gateway import (  # noqa: F401
    RestGatewayConfig,
    StdlibLoopbackHttpServer,
    create_fastapi_app,
    dispatch_rest_request,
)
