from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, auth, cases, documents, verify, integration
import logging
import sys

# Configure basic logging structure
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app")

app = FastAPI(
    title="Legal eVault API",
    description="Blockchain-backed legal-record integrity and provenance system.",
    version="0.1.0"
)

@app.on_event("startup")
def startup_event():
    """
    Validates blockchain RPC connection, contract code, and owner wallet match.
    Fails startup if registry settings are mismatched.
    """
    import os
    from app.config import settings
    
    # Check if bypass is requested via settings or env
    is_bypass_requested = settings.bypass_startup_validation or os.getenv("BYPASS_STARTUP_VALIDATION") == "true"
    
    if is_bypass_requested:
        if settings.app_env.lower() in ("production", "prod"):
            logger.critical("Security Violation: Startup registry validation bypass is prohibited in production environment!")
            sys.exit(1)
        else:
            logger.warning("WARNING: Startup registry validation bypassed. This is ONLY allowed in test/development scenarios.")
            return

    from app.services.blockchain import BlockchainAdapter
    try:
        adapter = BlockchainAdapter()
        adapter.startup_validation()
        logger.info("Startup Registry Validation completed successfully.")
    except Exception as e:
        logger.critical(f"CRITICAL: Startup Registry Validation Failed: {str(e)}")
        sys.exit(1)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restricted in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# Health is mounted twice: root (for uptime/k8s probes) and /api/v1 (for API clients)
app.include_router(health.router, tags=["Health"])
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(auth.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(verify.router, prefix="/api/v1")
app.include_router(integration.router, prefix="/api/v1")

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException

@app.exception_handler(FastAPIHTTPException)
async def custom_http_exception_handler(request: Request, exc: FastAPIHTTPException):
    detail_str = str(exc.detail) if exc.detail is not None else ""
    error_code = "GENERIC_ERROR"
    if detail_str == "AUTHORIZATION_INTEGRITY_FAILURE":
        error_code = "AUTHORIZATION_INTEGRITY_FAILURE"
    elif detail_str.startswith("AUTHORIZATION_UNAVAILABLE"):
        error_code = "AUTHORIZATION_UNAVAILABLE"
    elif exc.status_code == 403:
        error_code = "DOCUMENT_ACCESS_DENIED"
    elif exc.status_code == 404:
        error_code = "RECORD_NOT_FOUND"
    elif exc.status_code == 400:
        error_code = "BAD_REQUEST"
        
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": {
                "code": error_code,
                "message": exc.detail,
                "request_id": request.headers.get("x-request-id", "unknown")
            }
        }
    )

