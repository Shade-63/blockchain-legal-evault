from pydantic import BaseModel
from typing import Optional

class DependencyStatus(BaseModel):
    healthy: bool
    error: Optional[str] = None

class DependenciesReport(BaseModel):
    database: DependencyStatus
    storage: DependencyStatus
    blockchain: DependencyStatus

class HealthResponse(BaseModel):
    status: str

class DependencyHealthResponse(BaseModel):
    status: str
    dependencies: DependenciesReport
