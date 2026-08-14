from fastapi import APIRouter, status
from app.database import check_db_connection
from app.config import settings
from app.schemas.health import HealthResponse, DependencyHealthResponse, DependenciesReport, DependencyStatus
import boto3
from botocore.config import Config
from web3 import Web3

router = APIRouter()

def check_storage_connection() -> tuple[bool, str | None]:
    """
    Checks connection to MinIO / S3.
    """
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            config=Config(
                signature_version="s3v4",
                connect_timeout=2,
                retries={"max_attempts": 0}
            )
        )
        # Fast query to list buckets to verify auth/connectivity
        s3.list_buckets()
        return True, None
    except Exception as e:
        return False, str(e)

def check_blockchain_connection() -> tuple[bool, str | None]:
    """
    Checks connection to the local EVM node.
    """
    try:
        w3 = Web3(Web3.HTTPProvider(
            settings.blockchain_rpc_url,
            request_kwargs={"timeout": 2}
        ))
        if w3.is_connected():
            return True, None
        return False, "Unable to establish connection to EVM RPC provider."
    except Exception as e:
        return False, str(e)

@router.get("/health", response_model=HealthResponse)
def get_health():
    """
    Liveness probe. Returns 200 OK if FastAPI app is running.
    """
    return HealthResponse(status="ok")

@router.get("/health/dependencies", response_model=DependencyHealthResponse)
def get_dependency_health():
    """
    Readiness probe. Checks Postgres, MinIO, and local EVM.
    Returns status="healthy" only if ALL dependencies are responsive.
    """
    db_ok, db_err = check_db_connection()
    storage_ok, storage_err = check_storage_connection()
    blockchain_ok, blockchain_err = check_blockchain_connection()

    all_ok = db_ok and storage_ok and blockchain_ok
    status_str = "healthy" if all_ok else "unhealthy"

    report = DependenciesReport(
        database=DependencyStatus(healthy=db_ok, error=db_err),
        storage=DependencyStatus(healthy=storage_ok, error=storage_err),
        blockchain=DependencyStatus(healthy=blockchain_ok, error=blockchain_err)
    )

    return DependencyHealthResponse(status=status_str, dependencies=report)
