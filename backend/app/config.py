from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    debug: bool = True
    
    # Auth
    jwt_secret: str = "super_secure_jwt_secret_key_for_evault_development"
    
    # PostgreSQL
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/evault"
    
    # MinIO
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "evault-documents"
    
    # Blockchain
    blockchain_rpc_url: str = "http://localhost:8545"
    blockchain_private_key: str = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    contract_address: str = "0x5FbDB2315678afecb367f032d93F642f64180aa3"

    # Public Verification URL
    public_verify_base_url: str = "http://localhost:5173"
    bypass_startup_validation: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
